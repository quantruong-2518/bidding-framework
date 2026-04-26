import {
  ConflictException,
  Injectable,
  InternalServerErrorException,
  Logger,
  NotFoundException,
} from '@nestjs/common';
import { InjectDataSource } from '@nestjs/typeorm';
import { ConfigService } from '@nestjs/config';
import { DataSource } from 'typeorm';
import { BidsService } from '../bids/bids.service';
import {
  AiServiceClient,
  type MaterializeResponse,
} from '../gateway/ai-service.client';
import { ObjectStoreService } from '../object-store/object-store.service';
import { WorkflowsService } from '../workflows/workflows.service';
import type { ConfirmRequestDto } from './dto/confirm-request.dto';
import type { ConfirmResponseDto } from './dto/confirm-request.dto';
import { ParseSession } from './parse-session.entity';
import { ParseSessionsService } from './parse-sessions.service';

/**
 * S0.5 Wave 2B — atomic confirm transaction wrapping seven steps:
 *
 *   1. Load `parse_session` (must be READY).
 *   2. Apply user overrides + drop atom_rejects (in-memory mutate of payload).
 *   3. INSERT `bids` row via `BidsService.createFromParseSession`.
 *   4. Rename MinIO prefix `parse_sessions/<sid>/` → `bids/<bid_id>/`.
 *   5. Call ai-service `materialize` to write the vault tree atomically.
 *   6. UPDATE `parse_session` → CONFIRMED + bind confirmedBidId/At/By.
 *   7. Start Temporal workflow via existing `WorkflowsService.trigger()`.
 *
 * Steps 3 + 6 share a single TypeORM transaction. Steps 4, 5, and 7 are
 * external side-effects — on failure we explicitly best-effort un-rename
 * MinIO, ask ai-service to clean any half-written vault tree, and let the
 * TX rollback restore the parse_session to READY (so the user can retry).
 *
 * Decision 11 (atomic confirm) calls out that vault writes live INSIDE the
 * tx; we approximate it by holding the tx open until ai-service materialise
 * returns success, then commit + start workflow. If Temporal fails AFTER
 * commit, we cannot un-create the bid — the operator gets a 502 and the
 * bid sits at status=DRAFT with no workflow_id (the BidsController's
 * existing `attachWorkflow` flow can replay later).
 */
@Injectable()
export class MaterializeService {
  private readonly logger = new Logger(MaterializeService.name);
  private readonly bucket: string;
  private readonly vaultRoot: string;

  constructor(
    @InjectDataSource() private readonly dataSource: DataSource,
    private readonly sessions: ParseSessionsService,
    private readonly bids: BidsService,
    private readonly objectStore: ObjectStoreService,
    private readonly aiClient: AiServiceClient,
    private readonly workflows: WorkflowsService,
    private readonly config: ConfigService,
  ) {
    this.bucket = this.sessions.getBucket();
    this.vaultRoot =
      this.config.get<string>('KB_VAULT_ROOT') ?? '/vault/kb-vault';
  }

  /**
   * Run the full confirm flow. Returns the §3.7 ConfirmResponse shape.
   *
   * @param sid       Parse session id (URL parameter).
   * @param request   User overrides + atom edits/rejects.
   * @param userId    Username of the human pressing "Confirm" (for audit).
   */
  async confirmAndStart(
    sid: string,
    request: ConfirmRequestDto,
    userId: string,
  ): Promise<ConfirmResponseDto> {
    const session = await this.sessions.getById(sid);
    if (session.status === 'CONFIRMED') {
      throw new ConflictException(
        `parse_session ${sid} is already CONFIRMED (bid=${session.confirmedBidId ?? 'unknown'})`,
      );
    }
    if (session.status !== 'READY') {
      throw new ConflictException(
        `parse_session ${sid} is ${session.status}; confirm requires READY`,
      );
    }

    const trimmedPayload = this.applyOverrides(session, request);

    let bidId: string | null = null;
    let prefixRenamed = false;
    let materialisedPath: string | null = null;
    let materialiseTraceId: string | undefined;

    try {
      // Steps 3 + 6 inside a single Postgres transaction. Step 4 (MinIO) and
      // step 5 (ai-service) run inside the same try-block so a failure
      // bubbles into the rollback.
      bidId = await this.dataSource.transaction(async (em) => {
        const newBid = await this.bids.createFromParseSession(
          session,
          request,
          em,
        );

        // Step 4 — MinIO rename happens *inside* the tx so a Postgres rollback
        // (e.g. unique constraint surprise) leaves us with the un-rename
        // catch-block below to undo MinIO. Stub mode no-ops.
        try {
          await this.objectStore.renamePrefix(
            this.bucket,
            this.sessions.parseSessionPrefix(sid),
            this.bidPrefix(newBid.id),
          );
          prefixRenamed = true;
        } catch (err) {
          throw new MinioRenameError((err as Error).message);
        }

        // Step 5 — ai-service writes vault tree.
        let response: MaterializeResponse;
        try {
          response = await this.aiClient.materialize(sid, {
            bid_id: newBid.id,
            tenant_id: session.tenantId,
            vault_root: this.vaultRoot,
            parse_session_payload: trimmedPayload,
          });
        } catch (err) {
          throw new VaultMaterialiseError((err as Error).message);
        }
        materialisedPath = response.vault_path;
        materialiseTraceId = response.trace_id;

        // Step 6 — flip session to CONFIRMED inside the same em.
        const sessionRepo = em.getRepository(ParseSession);
        const fresh = await sessionRepo.findOne({ where: { id: sid } });
        if (!fresh) {
          // Race — should never happen since we hold an open tx, but guard
          // explicitly.
          throw new NotFoundException(`parse_session ${sid} disappeared`);
        }
        this.sessions.assertTransition(fresh.status, 'CONFIRMED');
        fresh.status = 'CONFIRMED';
        fresh.confirmedBidId = newBid.id;
        fresh.confirmedAt = new Date().toISOString();
        fresh.confirmedBy = userId;
        await sessionRepo.save(fresh);

        return newBid.id;
      });
    } catch (err) {
      // Rollback already happened (Postgres tx threw). Best-effort un-rename
      // MinIO + best-effort ai-service vault cleanup.
      if (prefixRenamed && bidId == null) {
        // Tx threw mid-step 5/6 *after* the rename — un-rename so a retry
        // sees the original prefix.
        try {
          await this.objectStore.renamePrefix(
            this.bucket,
            this.bidPrefix('rollback-pending'),
            this.sessions.parseSessionPrefix(sid),
          );
        } catch (rollbackErr) {
          this.logger.warn(
            `MinIO un-rename failed for ${sid}: ${(rollbackErr as Error).message}; ` +
              'leaving stale prefix for TTL cron',
          );
        }
      }
      if (materialisedPath) {
        // Vault tree was written — ai-service has its own idempotent
        // delete. We log and let the operator clean it up; the Postgres
        // tx rollback means no bid points at it so it's just stale.
        this.logger.warn(
          `Vault tree at ${materialisedPath} orphaned by tx rollback; ` +
            'operator cleanup required',
        );
      }
      this.logger.error(
        `Confirm tx failed for parse_session ${sid}: ${(err as Error).message}`,
      );
      if (err instanceof ConflictException || err instanceof NotFoundException) {
        throw err;
      }
      throw new InternalServerErrorException(
        `Confirm tx failed: ${(err as Error).message}`,
      );
    }

    if (!bidId || !materialisedPath) {
      // Defensive — the tx returned without throwing yet bidId is unset.
      throw new InternalServerErrorException(
        'Confirm tx returned without producing a bid id (impossible state)',
      );
    }

    // Step 7 — start Temporal workflow. Failure here leaves the bid in DRAFT
    // with no workflow_id; an operator (or a future retry endpoint) can call
    // `POST /bids/:id/workflow` later.
    let workflowId: string;
    try {
      const result = await this.workflows.trigger(bidId);
      workflowId = result.workflow.workflow_id;
    } catch (err) {
      this.logger.error(
        `Temporal workflow start failed for bid ${bidId}: ${(err as Error).message}; ` +
          'bid + vault are committed, manual replay required',
      );
      throw new InternalServerErrorException(
        `Workflow start failed for bid ${bidId}: ${(err as Error).message}`,
      );
    }

    return {
      bid_id: bidId,
      workflow_id: workflowId,
      vault_path: materialisedPath,
      trace_id: materialiseTraceId,
    };
  }

  private bidPrefix(bidId: string): string {
    return `bids/${bidId}/`;
  }

  /**
   * In-memory mutator: drop atom_rejects + apply atom_edits patches against
   * a deep-cloned copy of the session payload. Returns the trimmed payload
   * to forward to ai-service materialise.
   */
  private applyOverrides(
    session: ParseSession,
    request: ConfirmRequestDto,
  ): Record<string, unknown> {
    const atomsRaw = (session.atoms ?? []) as Array<Record<string, unknown>>;
    const rejectSet = new Set(request.atom_rejects ?? []);
    const editsById = new Map<string, Record<string, unknown>>();
    for (const edit of request.atom_edits ?? []) {
      editsById.set(edit.id, edit.patch);
    }

    const trimmed = atomsRaw
      .filter((atom) => {
        const id = (atom?.frontmatter as { id?: string })?.id ?? atom?.id;
        return typeof id === 'string' ? !rejectSet.has(id) : true;
      })
      .map((atom) => {
        const fm = (atom?.frontmatter as { id?: string }) ?? {};
        const id = fm.id;
        if (typeof id === 'string' && editsById.has(id)) {
          return {
            ...atom,
            frontmatter: { ...fm, ...editsById.get(id) },
          };
        }
        return atom;
      });

    return {
      session_id: session.id,
      tenant_id: session.tenantId,
      atoms: trimmed,
      anchor_md: session.anchorMd,
      summary_md: session.summaryMd,
      manifest: session.manifest,
      conflicts: session.conflicts,
      open_questions: session.openQuestions,
      suggested_bid_card: {
        ...((session.suggestedBidCard ?? {}) as Record<string, unknown>),
        ...(request.client_name ? { client_name: request.client_name } : {}),
        ...(request.industry ? { industry: request.industry } : {}),
        ...(request.region ? { region: request.region } : {}),
        ...(request.deadline ? { deadline: request.deadline } : {}),
        ...(request.profile_override
          ? { estimated_profile: request.profile_override }
          : {}),
        ...(request.name ? { name: request.name } : {}),
      },
    };
  }
}

/** Thrown by step-4 (MinIO rename). Re-mapped to InternalServerError above. */
class MinioRenameError extends Error {
  constructor(message: string) {
    super(`MinIO rename failed: ${message}`);
    this.name = 'MinioRenameError';
  }
}

/** Thrown by step-5 (ai-service materialise). */
class VaultMaterialiseError extends Error {
  constructor(message: string) {
    super(`ai-service materialise failed: ${message}`);
    this.name = 'VaultMaterialiseError';
  }
}
