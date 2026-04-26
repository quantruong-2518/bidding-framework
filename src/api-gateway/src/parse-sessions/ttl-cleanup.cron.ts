import { Injectable, Logger } from '@nestjs/common';
import { Cron, CronExpression } from '@nestjs/schedule';
import { ParseSessionsService } from './parse-sessions.service';

/**
 * S0.5 Wave 2B — hourly TTL cleanup.
 *
 * Decision 10 sets a 7-day TTL on parse sessions. This cron runs every hour
 * and:
 *   1. Asks `ParseSessionsService.findExpired()` for sessions whose
 *      `expires_at < now()` AND status ∈ (PARSING, READY) — terminal
 *      states are exempt (CONFIRMED owns the bid; ABANDONED already
 *      cleaned MinIO).
 *   2. For each row: `markAbandoned(sid)` which deletes the MinIO prefix
 *      and flips status to ABANDONED.
 *
 * Failure isolation: each session is wrapped in its own try/catch so a
 * single-session failure (e.g. MinIO 403) doesn't block the rest of the
 * batch. The next hourly tick will retry; if MinIO stays sad indefinitely
 * the row sits in ABANDONED with a `parse_error` summary so an oncall can
 * intervene.
 *
 * Config: set `PARSE_SESSION_TTL_CRON_DISABLED=1` to turn the cron off in
 * environments where the cleanup is owned by another job (e.g. a Kubernetes
 * CronJob in production).
 */
@Injectable()
export class ParseSessionTtlCleanupCron {
  private readonly logger = new Logger(ParseSessionTtlCleanupCron.name);
  private readonly disabled: boolean;

  constructor(private readonly sessions: ParseSessionsService) {
    this.disabled = process.env.PARSE_SESSION_TTL_CRON_DISABLED === '1';
    if (this.disabled) {
      this.logger.warn(
        'Parse-session TTL cleanup cron disabled via PARSE_SESSION_TTL_CRON_DISABLED=1',
      );
    }
  }

  @Cron(CronExpression.EVERY_HOUR, {
    name: 'parse-session-ttl-cleanup',
    timeZone: 'UTC',
  })
  async runHourly(): Promise<void> {
    if (this.disabled) return;
    await this.sweepOnce();
  }

  /**
   * Public entry-point so tests + admin endpoints can invoke the same code
   * path without waiting for the cron tick. Returns aggregated counters for
   * observability (logs already published per-session).
   */
  async sweepOnce(): Promise<{
    scanned: number;
    abandoned: number;
    errors: number;
  }> {
    const expired = await this.sessions.findExpired();
    if (expired.length === 0) {
      this.logger.debug('TTL sweep: no expired parse sessions');
      return { scanned: 0, abandoned: 0, errors: 0 };
    }
    let abandoned = 0;
    let errors = 0;
    for (const session of expired) {
      try {
        await this.sessions.markAbandoned(session.id);
        abandoned += 1;
        this.logger.log(
          `TTL sweep: abandoned parse_session ${session.id} (tenant=${session.tenantId}, expired=${session.expiresAt})`,
        );
      } catch (err) {
        errors += 1;
        this.logger.warn(
          `TTL sweep: failed to abandon ${session.id}: ${(err as Error).message}`,
        );
      }
    }
    return { scanned: expired.length, abandoned, errors };
  }
}
