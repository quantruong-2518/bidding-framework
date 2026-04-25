import { Injectable, Logger } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { LRUCache } from 'lru-cache';
import { Repository } from 'typeorm';
import { AuditLog } from './audit-log.entity';

export interface AuditRecord {
  userSub: string;
  username: string;
  roles: string[];
  action: string;
  resourceType: string;
  resourceId: string | null;
  statusCode: number;
  metadata?: Record<string, unknown> | null;
}

/** Window inside which an identical (user, GET, resource, 2xx/3xx) row is suppressed. */
const DEDUPE_WINDOW_MS = 30_000;
/** Cache size cap — bounds memory if many distinct keys arrive in the window. */
const DEDUPE_MAX_ENTRIES = 5_000;

/**
 * Persists role-gated HTTP activity to the `audit_log` table.
 *
 * Fire-and-forget by design: `record()` never throws. A DB failure is logged
 * but the originating request is NOT impacted — availability > audit fidelity.
 * Phase 3.3 audit dashboard queries this table.
 *
 * **Dedupe (defence-in-depth, post-3.3 hardening):** identical GET 2xx/3xx
 * rows from the same actor on the same resource collapse into one row inside
 * a 30 s window. The original incident — a frontend poller spraying 5 760
 * `GET /workflow/status` rows per day — is solved at the route level via
 * `@SkipAudit()`. This cache catches the next route that forgets to opt out.
 *
 * State-changing methods (POST/PATCH/DELETE) and error responses (≥400) are
 * NEVER deduped — they're security-relevant signals where redundancy is
 * preferred to silent loss.
 */
@Injectable()
export class AuditService {
  private readonly logger = new Logger(AuditService.name);
  private readonly dedupeCache: LRUCache<string, true>;

  constructor(
    @InjectRepository(AuditLog)
    private readonly repo: Repository<AuditLog>,
  ) {
    this.dedupeCache = new LRUCache<string, true>({
      max: DEDUPE_MAX_ENTRIES,
      ttl: DEDUPE_WINDOW_MS,
    });
  }

  async record(entry: AuditRecord): Promise<void> {
    if (shouldDedupe(entry)) {
      const key = dedupeKey(entry);
      if (this.dedupeCache.has(key)) {
        return;
      }
      this.dedupeCache.set(key, true);
    }

    try {
      const row = this.repo.create({
        userSub: entry.userSub,
        username: entry.username,
        roles: entry.roles,
        action: entry.action,
        resourceType: entry.resourceType,
        resourceId: entry.resourceId,
        statusCode: entry.statusCode,
        metadata: entry.metadata ?? null,
      });
      await this.repo.save(row);
    } catch (err) {
      this.logger.warn(
        `audit.record failed (swallowed): ${(err as Error).message}`,
      );
    }
  }

  /** Test-only: drops the in-memory dedupe window between specs. */
  clearDedupeCacheForTest(): void {
    this.dedupeCache.clear();
  }
}

function shouldDedupe(entry: AuditRecord): boolean {
  return entry.action.startsWith('GET ') && entry.statusCode < 400;
}

function dedupeKey(entry: AuditRecord): string {
  return [
    entry.userSub,
    entry.action,
    entry.resourceId ?? '',
    entry.statusCode,
  ].join('|');
}
