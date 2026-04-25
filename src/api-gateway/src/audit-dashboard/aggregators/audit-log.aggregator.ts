import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Between, Repository } from 'typeorm';
import { AuditLog } from '../../audit/audit-log.entity';
import type { DecisionTrailEntry } from '../types';

/**
 * Reads decision-trail rows from the `audit_log` table populated by
 * `AuditInterceptor`.
 *
 * The audit rows record HTTP activity (route template + user + status code);
 * this aggregator reshapes them for the dashboard. No join with `bids` —
 * `resourceId` already holds the bid UUID for every role-gated bid route.
 */
@Injectable()
export class AuditLogAggregator {
  constructor(
    @InjectRepository(AuditLog)
    private readonly repo: Repository<AuditLog>,
  ) {}

  /** Decision trail for a single bid — ordered oldest-first. */
  async forBid(bidId: string): Promise<DecisionTrailEntry[]> {
    const rows = await this.repo.find({
      where: { resourceId: bidId },
      order: { timestamp: 'ASC' },
      take: 500,
    });
    return rows.map(toEntry);
  }

  /**
   * Decision rows inside a date range, filtered by optional role/action.
   * Ordered newest-first; capped at `limit` (default 100).
   */
  async recent(range: {
    from: Date;
    to: Date;
    role?: string;
    limit?: number;
  }): Promise<DecisionTrailEntry[]> {
    const rows = await this.repo.find({
      where: { timestamp: Between(range.from, range.to) as unknown as Date },
      order: { timestamp: 'DESC' },
      take: range.limit ?? 100,
    });
    const filtered = range.role
      ? rows.filter((r) => Array.isArray(r.roles) && r.roles.includes(range.role!))
      : rows;
    return filtered.map(toEntry);
  }

  /** Count of distinct bids touched in the range (for summary totals). */
  async distinctBidCount(range: { from: Date; to: Date }): Promise<number> {
    const qb = this.repo
      .createQueryBuilder('al')
      .select('COUNT(DISTINCT al.resource_id)', 'n')
      .where('al.timestamp BETWEEN :from AND :to', {
        from: range.from,
        to: range.to,
      })
      .andWhere('al.resource_id IS NOT NULL');
    const result = await qb.getRawOne<{ n: string }>();
    return Number(result?.n ?? 0);
  }
}

function toEntry(row: AuditLog): DecisionTrailEntry {
  return {
    timestamp:
      row.timestamp instanceof Date
        ? row.timestamp.toISOString()
        : String(row.timestamp),
    action: row.action,
    actor: {
      userSub: row.userSub,
      username: row.username,
      roles: Array.isArray(row.roles) ? row.roles : [],
    },
    resourceType: row.resourceType,
    resourceId: row.resourceId,
    statusCode: row.statusCode,
    metadata: row.metadata ?? null,
  };
}
