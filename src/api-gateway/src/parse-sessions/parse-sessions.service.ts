import {
  ConflictException,
  Injectable,
  Logger,
  NotFoundException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, type EntityManager } from 'typeorm';
import { v4 as uuidv4 } from 'uuid';
import { ObjectStoreService } from '../object-store/object-store.service';
import {
  ParseSession,
  type ParseSessionStatus,
} from './parse-session.entity';

/**
 * S0.5 Wave 2B — CRUD + state-machine guard for `parse_sessions`.
 *
 * The service is intentionally thin: writers (create / setStatus / setResult /
 * markAbandoned) enforce the {@link ParseSession} state machine and own the
 * MinIO cleanup contract. Read methods (getById / findExpired) return naked
 * entities; the controller is responsible for shaping `PreviewResponseDto`.
 *
 * State machine (Decision 10):
 *
 *   PARSING ──▶ READY ──▶ CONFIRMED
 *      │          │
 *      ▼          ▼
 *   FAILED    ABANDONED
 *
 * `setStatus()` is the canonical mutator for transitions. `setResult()` is
 * called by the parse pipeline (driven from the AI-service callback or — in
 * the deterministic stub path — from `MaterializeService`) once parse output
 * is ready. Both clamp `updatedAt`.
 *
 * MinIO bucket name comes from `OBJECT_STORE_BUCKET_BIDS` env (default
 * `bid-originals`) so production + test runs can target separate buckets.
 */
@Injectable()
export class ParseSessionsService {
  private readonly logger = new Logger(ParseSessionsService.name);
  private readonly bucket: string;
  private readonly ttlMs: number;

  constructor(
    @InjectRepository(ParseSession)
    private readonly repo: Repository<ParseSession>,
    private readonly objectStore: ObjectStoreService,
  ) {
    this.bucket = process.env.OBJECT_STORE_BUCKET_BIDS ?? 'bid-originals';
    // Default 7d (Decision 10) — overridable for tests.
    const days = Number(process.env.PARSE_SESSION_TTL_DAYS ?? 7);
    this.ttlMs = days * 24 * 60 * 60 * 1_000;
  }

  /** Bucket name for MinIO objects (originals + materialised vault). */
  getBucket(): string {
    return this.bucket;
  }

  /** Storage prefix where the controller saves originals while parsing. */
  parseSessionPrefix(sid: string): string {
    return `parse_sessions/${sid}/`;
  }

  /**
   * Create a row in PARSING state. Returns the saved entity.
   *
   * @param tenantId  Tenant id from the multipart payload.
   * @param userId    Caller's username / sub (for audit + RBAC).
   */
  async createSession(tenantId: string, userId: string): Promise<ParseSession> {
    const id = uuidv4();
    const now = new Date();
    const expiresAt = new Date(now.getTime() + this.ttlMs);
    const entity = this.repo.create({
      id,
      tenantId,
      userId,
      status: 'PARSING' as ParseSessionStatus,
      suggestedBidCard: null,
      atoms: null,
      anchorMd: null,
      summaryMd: null,
      manifest: null,
      conflicts: null,
      openQuestions: null,
      parseError: null,
      expiresAt: expiresAt.toISOString(),
      confirmedBidId: null,
      confirmedAt: null,
      confirmedBy: null,
    });
    return this.repo.save(entity);
  }

  /**
   * Transition a session's status. Throws when the move is not allowed by
   * the lifecycle (Decision 10):
   *   PARSING → READY | FAILED
   *   READY   → CONFIRMED | ABANDONED
   *   terminal states (CONFIRMED / ABANDONED / FAILED) → no further moves
   *
   * For CONFIRMED transitions specifically, prefer the
   * {@link MaterializeService} path which sets the bid id + timestamp inside
   * the same DB transaction. This method is exposed for the simpler
   * READY → ABANDONED + PARSING → READY/FAILED flows.
   */
  async setStatus(
    sid: string,
    status: ParseSessionStatus,
    error?: string,
    em?: EntityManager,
  ): Promise<ParseSession> {
    const repo = em ? em.getRepository(ParseSession) : this.repo;
    const session = await repo.findOne({ where: { id: sid } });
    if (!session) {
      throw new NotFoundException(`parse_session ${sid} not found`);
    }
    this.assertTransition(session.status, status);
    session.status = status;
    if (status === 'FAILED' && error) session.parseError = error;
    return repo.save(session);
  }

  /**
   * Persist parser output — typically called once by the AI-service result
   * callback when the parse finishes. Flips status to READY when payload is
   * complete (atoms != null AND suggested_bid_card != null), else leaves
   * status alone so a partial heartbeat doesn't prematurely unlock confirm.
   */
  async setResult(
    sid: string,
    payload: {
      suggestedBidCard?: Record<string, unknown> | null;
      atoms?: unknown[] | null;
      anchorMd?: string | null;
      summaryMd?: string | null;
      manifest?: Record<string, unknown> | null;
      conflicts?: unknown[] | null;
      openQuestions?: unknown[] | null;
      flipToReady?: boolean;
    },
  ): Promise<ParseSession> {
    const session = await this.repo.findOne({ where: { id: sid } });
    if (!session) {
      throw new NotFoundException(`parse_session ${sid} not found`);
    }
    if (session.status !== 'PARSING' && session.status !== 'READY') {
      throw new ConflictException(
        `parse_session ${sid} is ${session.status}; setResult() only valid pre-confirm`,
      );
    }
    if (payload.suggestedBidCard !== undefined) {
      session.suggestedBidCard = payload.suggestedBidCard;
    }
    if (payload.atoms !== undefined) session.atoms = payload.atoms;
    if (payload.anchorMd !== undefined) session.anchorMd = payload.anchorMd;
    if (payload.summaryMd !== undefined) session.summaryMd = payload.summaryMd;
    if (payload.manifest !== undefined) session.manifest = payload.manifest;
    if (payload.conflicts !== undefined) session.conflicts = payload.conflicts;
    if (payload.openQuestions !== undefined) {
      session.openQuestions = payload.openQuestions;
    }
    if (payload.flipToReady && session.status === 'PARSING') {
      session.status = 'READY';
    }
    return this.repo.save(session);
  }

  /**
   * Load a session by id. Throws 404 when missing OR when expired and not
   * yet confirmed (the row may exist but logically dead — frontend retry
   * should ask the user to re-upload).
   */
  async getById(sid: string, opts?: { allowExpired?: boolean }): Promise<ParseSession> {
    const session = await this.repo.findOne({ where: { id: sid } });
    if (!session) {
      throw new NotFoundException(`parse_session ${sid} not found`);
    }
    if (
      !opts?.allowExpired &&
      this.isExpired(session) &&
      (session.status === 'PARSING' || session.status === 'READY')
    ) {
      throw new NotFoundException(
        `parse_session ${sid} expired at ${session.expiresAt}`,
      );
    }
    return session;
  }

  /**
   * Return every session whose `expires_at` lapsed AND status is still
   * pre-terminal — matches the partial index the migration created.
   */
  async findExpired(now: Date = new Date()): Promise<ParseSession[]> {
    const rows = await this.repo.find({
      where: [{ status: 'PARSING' }, { status: 'READY' }],
    });
    return rows.filter((row) => row.expiresAt < now.toISOString());
  }

  /**
   * Mark a session ABANDONED + delete its MinIO prefix. Idempotent: an
   * already-abandoned (or already-confirmed) session is a no-op for the
   * caller — we still attempt the MinIO delete in case a previous run
   * crashed mid-cleanup.
   *
   * @returns The number of MinIO keys deleted (zero in stub mode or when
   *          there's nothing left to delete).
   */
  async markAbandoned(sid: string): Promise<{ deleted: number; status: ParseSessionStatus }> {
    const session = await this.repo.findOne({ where: { id: sid } });
    if (!session) {
      throw new NotFoundException(`parse_session ${sid} not found`);
    }
    let deleted = 0;
    try {
      deleted = await this.objectStore.deletePrefix(
        this.bucket,
        this.parseSessionPrefix(sid),
      );
    } catch (err) {
      // We still flip the status — the row pointing at orphan MinIO objects
      // is worse than orphan MinIO objects pointing at no row, because the
      // cleanup cron would otherwise try forever.
      this.logger.warn(
        `MinIO deletePrefix failed for ${sid}: ${(err as Error).message}; ` +
          'flagging session ABANDONED anyway',
      );
    }
    if (session.status === 'CONFIRMED') {
      // Confirmed sessions own no parse_sessions/<sid>/ prefix any more —
      // the MinIO blobs were renamed under bids/<bid_id>/. Refuse to flip.
      throw new ConflictException(
        `parse_session ${sid} already CONFIRMED; cannot abandon`,
      );
    }
    if (session.status !== 'ABANDONED') {
      session.status = 'ABANDONED';
      await this.repo.save(session);
    }
    return { deleted, status: session.status };
  }

  /**
   * State-machine guard. Throws ConflictException for illegal moves so the
   * controller surfaces a 409 rather than a 500.
   *
   * Allowed:
   *   PARSING → READY | FAILED
   *   READY   → CONFIRMED | ABANDONED
   *
   * Refused (terminal): CONFIRMED / ABANDONED / FAILED → anything.
   */
  assertTransition(
    from: ParseSessionStatus,
    to: ParseSessionStatus,
  ): void {
    const allowed: Record<ParseSessionStatus, ReadonlySet<ParseSessionStatus>> = {
      PARSING: new Set(['READY', 'FAILED']),
      READY: new Set(['CONFIRMED', 'ABANDONED']),
      CONFIRMED: new Set(),
      ABANDONED: new Set(),
      FAILED: new Set(),
    };
    if (!allowed[from].has(to)) {
      throw new ConflictException(
        `parse_session transition ${from} → ${to} not allowed`,
      );
    }
  }

  /** True when `expires_at < now` regardless of status. */
  isExpired(session: ParseSession, now: Date = new Date()): boolean {
    return session.expiresAt < now.toISOString();
  }
}
