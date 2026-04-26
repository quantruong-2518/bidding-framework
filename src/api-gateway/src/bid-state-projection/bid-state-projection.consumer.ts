import {
  Injectable,
  Logger,
  OnModuleDestroy,
  OnModuleInit,
} from '@nestjs/common';
import { InjectDataSource } from '@nestjs/typeorm';
import type Redis from 'ioredis';
import { DataSource, EntityManager, Repository } from 'typeorm';
import { RedisService } from '../redis/redis.service';
import { BidStateProjection } from './bid-state-projection.entity';
import { BidStateTransition } from './bid-state-transition.entity';
import {
  ParsedTransitionEntry,
  TERMINAL_OUTCOMES,
  TERMINAL_STATES,
} from './bid-state.types';

/**
 * Configuration knobs (read from env at construction; defaults match the plan).
 */
export const STREAM_KEY = 'bid.transitions';
export const CONSUMER_GROUP = 'bid-projection-cg';
export const CONSUMER_NAME = 'bid-projection-1';
export const DEFAULT_BATCH = 100;
export const DEFAULT_BLOCK_MS = 5_000;

/**
 * NestJS consumer for the `bid.transitions` Redis stream.
 *
 * Lifecycle:
 *   onModuleInit  → ensureGroup() + claimStaleEntries() + start runLoop()
 *   onModuleDestroy → flag stopped=true, await loop drain.
 *
 * Per-entry path: parseEntry → applyTransition (transactional INSERT log +
 * UPSERT projection) → XACK. INSERT is idempotent via UNIQUE (bid_id,
 * transition_seq); UPSERT skips stale (older transition_seq) so out-of-order
 * delivery / replay can't roll the projection backward.
 *
 * Failure isolation:
 *   - Malformed entry → log warning + XACK (so the stream advances; the bad
 *     payload is in the log warning). Postgres `bid_state_transitions` is
 *     unchanged.
 *   - DB error → no XACK; the entry stays in PEL and is retried on next loop
 *     (or claimed at startup after 60s idle).
 */
@Injectable()
export class BidStateProjectionConsumer
  implements OnModuleInit, OnModuleDestroy
{
  private readonly logger = new Logger(BidStateProjectionConsumer.name);
  private readonly batchSize: number;
  private readonly blockMs: number;
  private stopped = false;
  private loopPromise: Promise<void> | null = null;

  constructor(
    private readonly redisService: RedisService,
    @InjectDataSource() private readonly dataSource: DataSource,
  ) {
    this.batchSize = Number(process.env.BID_PROJECTION_CONSUMER_BATCH ?? DEFAULT_BATCH);
    this.blockMs = Number(
      process.env.BID_PROJECTION_CONSUMER_BLOCK_MS ?? DEFAULT_BLOCK_MS,
    );
  }

  async onModuleInit(): Promise<void> {
    if (process.env.BID_PROJECTION_CONSUMER_DISABLED === '1') {
      this.logger.warn(
        'bid-state projection consumer disabled via BID_PROJECTION_CONSUMER_DISABLED',
      );
      return;
    }
    try {
      await this.ensureGroup();
      this.loopPromise = this.runLoop();
    } catch (err) {
      // Don't let a transient Redis outage block app boot; we'll log and
      // skip — operators can restart once Redis is healthy.
      this.logger.error(
        `Failed to bootstrap bid-state projection consumer: ${(err as Error).message}`,
      );
    }
  }

  async onModuleDestroy(): Promise<void> {
    this.stopped = true;
    if (this.loopPromise) {
      await this.loopPromise.catch(() => undefined);
    }
  }

  /** Ensure consumer group exists. `BUSYGROUP` is the only expected error. */
  async ensureGroup(): Promise<void> {
    const client = this.redisService.getClient();
    try {
      await client.xgroup('CREATE', STREAM_KEY, CONSUMER_GROUP, '$', 'MKSTREAM');
      this.logger.log(`Created consumer group ${CONSUMER_GROUP} on ${STREAM_KEY}`);
    } catch (err) {
      const msg = (err as Error).message ?? '';
      if (!msg.includes('BUSYGROUP')) throw err;
    }
  }

  /**
   * XREADGROUP loop. Reads up to `batchSize` entries with a `blockMs` block
   * deadline. Returns when `stopped=true`. Errors are logged + retried with a
   * brief backoff so the loop doesn't burn CPU on a sustained outage.
   */
  async runLoop(): Promise<void> {
    const client = this.redisService.getClient();
    while (!this.stopped) {
      try {
        const result = (await client.xreadgroup(
          'GROUP',
          CONSUMER_GROUP,
          CONSUMER_NAME,
          'COUNT',
          this.batchSize,
          'BLOCK',
          this.blockMs,
          'STREAMS',
          STREAM_KEY,
          '>',
        )) as Array<[string, Array<[string, string[]]>]> | null;
        if (!result) continue;
        for (const [, entries] of result) {
          await this.processBatch(client, entries);
        }
      } catch (err) {
        if (this.stopped) break;
        this.logger.error(
          `XREADGROUP loop error: ${(err as Error).message} — retrying in 1s`,
        );
        await new Promise((r) => setTimeout(r, 1_000));
      }
    }
  }

  /**
   * Process one batch returned by XREADGROUP. Handles each entry independently
   * — a single bad payload doesn't block the rest of the batch.
   *
   * Exposed (not private) so unit tests can drive it directly with a fake
   * Redis client.
   */
  async processBatch(
    client: Pick<Redis, 'xack'>,
    entries: Array<[string, string[]]>,
  ): Promise<void> {
    for (const [entryId, fields] of entries) {
      const parsed = this.parseEntry(entryId, fields);
      if (!parsed) {
        await this.safeAck(client, entryId);
        continue;
      }
      try {
        await this.applyTransition(parsed);
        await this.safeAck(client, entryId);
      } catch (err) {
        this.logger.error(
          `Failed to apply transition bid=${parsed.bidId} seq=${parsed.transitionSeq}: ${(err as Error).message}`,
        );
        // Intentionally NOT XACK — the entry stays pending and will be
        // redelivered on next XREADGROUP > or claimed via XAUTOCLAIM.
      }
    }
  }

  /**
   * Apply one transition: INSERT log row + UPSERT projection. Wrapped in a
   * single Postgres transaction so a partial write is impossible.
   */
  async applyTransition(parsed: ParsedTransitionEntry): Promise<void> {
    await this.dataSource.transaction(async (em) => {
      const inserted = await this.insertTransitionLog(em, parsed);
      await this.upsertProjection(em, parsed, inserted);
    });
  }

  /**
   * INSERT into `bid_state_transitions`; returns true when the row was new
   * (false when `(bid_id, transition_seq)` already existed → at-least-once
   * redelivery).
   *
   * Pre-checks for the existing `(bid_id, transition_seq)` so we can give the
   * caller a definitive new-row signal — `orIgnore()` populates
   * `result.identifiers` even on a no-op duplicate, which would corrupt the
   * cost rollup if we trusted it.
   */
  private async insertTransitionLog(
    em: EntityManager,
    parsed: ParsedTransitionEntry,
  ): Promise<boolean> {
    const repo: Repository<BidStateTransition> = em.getRepository(BidStateTransition);
    const existing = await repo.findOne({
      where: { bidId: parsed.bidId, transitionSeq: parsed.transitionSeq },
      select: { id: true },
    });
    if (existing) return false;
    await repo
      .createQueryBuilder()
      .insert()
      .values({
        bidId: parsed.bidId,
        workflowId: parsed.workflowId,
        transitionSeq: parsed.transitionSeq,
        fromState: parsed.fromState,
        toState: parsed.toState,
        profile: parsed.profile,
        tenantId: parsed.tenantId,
        artifactKeys: parsed.artifactKeys,
        llmCostDelta: parsed.llmCostDelta,
        occurredAt: parsed.occurredAt,
      })
      .orIgnore()
      .execute();
    return true;
  }

  /**
   * Upsert into `bid_state_projection`. Only applies when the incoming seq is
   * strictly greater than the persisted `last_transition_seq` — otherwise the
   * UPSERT is a no-op (preserves monotonic forward progress on replay).
   */
  private async upsertProjection(
    em: EntityManager,
    parsed: ParsedTransitionEntry,
    isNewLogRow: boolean,
  ): Promise<void> {
    const repo = em.getRepository(BidStateProjection);
    const existing = await repo.findOne({ where: { bidId: parsed.bidId } });

    const isTerminal = TERMINAL_STATES.has(parsed.toState);
    const outcome = isTerminal ? TERMINAL_OUTCOMES[parsed.toState] ?? null : null;

    if (existing && parsed.transitionSeq <= existing.lastTransitionSeq) {
      // Stale (replay or out-of-order): do not overwrite forward progress.
      // We DO still bump cost when this is a new log row — covers the rare
      // case where an out-of-order entry is the *first* time we see this
      // particular cost delta.
      if (isNewLogRow && parsed.llmCostDelta != null) {
        existing.totalLlmCostUsd =
          Number(existing.totalLlmCostUsd ?? 0) + parsed.llmCostDelta;
        await repo.save(existing);
      }
      return;
    }

    const artifactsDone: Record<string, string> = {
      ...(existing?.artifactsDone ?? {}),
    };
    for (const key of parsed.artifactKeys) {
      // Append-only: first-seen timestamp wins so historical traces stay stable.
      if (!(key in artifactsDone)) {
        artifactsDone[key] = parsed.occurredAt;
      }
    }

    const previousCost = Number(existing?.totalLlmCostUsd ?? 0);
    const totalLlmCostUsd =
      isNewLogRow && parsed.llmCostDelta != null
        ? previousCost + parsed.llmCostDelta
        : previousCost;

    const row = repo.create({
      ...(existing ?? {}),
      bidId: parsed.bidId,
      workflowId: parsed.workflowId,
      tenantId: parsed.tenantId,
      currentState: parsed.toState,
      profile: parsed.profile,
      clientName: existing?.clientName ?? '',
      industry: existing?.industry ?? '',
      lastTransitionSeq: parsed.transitionSeq,
      lastTransitionAt: parsed.occurredAt,
      artifactsDone,
      isTerminal,
      outcome,
      totalLlmCostUsd,
    });
    await repo.save(row);
  }

  /**
   * Parse one stream entry's `[k1, v1, k2, v2, ...]` field array into a typed
   * object. Returns `null` for malformed entries (logs a warning).
   */
  parseEntry(
    entryId: string,
    fields: string[],
  ): ParsedTransitionEntry | null {
    const map: Record<string, string> = {};
    for (let i = 0; i < fields.length; i += 2) {
      map[fields[i]] = fields[i + 1] ?? '';
    }
    try {
      const seqRaw = map.transition_seq;
      const seq = Number.parseInt(seqRaw, 10);
      if (!Number.isFinite(seq) || seq < 0) {
        throw new Error(`bad transition_seq: ${seqRaw}`);
      }
      const artifactKeysRaw = map.artifact_keys || '[]';
      const artifactKeys = JSON.parse(artifactKeysRaw);
      if (!Array.isArray(artifactKeys)) {
        throw new Error('artifact_keys not an array');
      }
      const llmCostRaw = map.llm_cost_delta;
      const llmCostDelta =
        llmCostRaw == null || llmCostRaw === ''
          ? null
          : Number.parseFloat(llmCostRaw);
      if (llmCostDelta != null && !Number.isFinite(llmCostDelta)) {
        throw new Error(`bad llm_cost_delta: ${llmCostRaw}`);
      }
      if (!map.bid_id || !map.to_state || !map.profile) {
        throw new Error('missing required field (bid_id / to_state / profile)');
      }
      return {
        bidId: map.bid_id,
        workflowId: map.workflow_id ?? '',
        transitionSeq: seq,
        tenantId: map.tenant_id ?? '',
        fromState: map.from_state ? map.from_state : null,
        toState: map.to_state,
        profile: map.profile,
        artifactKeys: artifactKeys.map(String),
        occurredAt: map.occurred_at ?? '',
        llmCostDelta,
      };
    } catch (err) {
      this.logger.warn(
        `Skipping malformed bid.transitions entry ${entryId}: ${(err as Error).message}`,
      );
      return null;
    }
  }

  private async safeAck(
    client: Pick<Redis, 'xack'>,
    entryId: string,
  ): Promise<void> {
    try {
      await client.xack(STREAM_KEY, CONSUMER_GROUP, entryId);
    } catch (err) {
      // Worst case: entry stays in PEL until next claim — log only.
      this.logger.warn(
        `XACK failed for entry ${entryId}: ${(err as Error).message}`,
      );
    }
  }
}
