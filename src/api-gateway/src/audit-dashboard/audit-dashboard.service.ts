import { Injectable, Logger, NotFoundException } from '@nestjs/common';
import { BidsService } from '../bids/bids.service';
import { AuditLogAggregator } from './aggregators/audit-log.aggregator';
import { LangfuseAggregator } from './aggregators/langfuse.aggregator';
import { TemporalAggregator } from './aggregators/temporal.aggregator';
import { TtlCache } from './cache';
import type {
  BidAuditDetail,
  BidCostBreakdown,
  CostsQuery,
  CostsResponse,
  DashboardSummary,
  DecisionTrailEntry,
  SummaryQuery,
} from './types';

const EMPTY_COSTS: BidCostBreakdown = {
  totalUsd: 0,
  byAgent: {},
  byModel: {},
  generationCount: 0,
  latencyP95Ms: 0,
};

/**
 * Stitches decision-trail + workflow history + Langfuse costs into the two
 * dashboard responses. Every upstream call is resilient: a failure adds
 * an entry to `warnings[]` but never turns into a 5xx. The caller sees
 * what the surviving sources returned.
 *
 * Caching is intentionally coarse: a 5-minute TTL per query signature
 * keyed off the normalised input. Admin use hits the same endpoint every
 * page refresh; caching amortises the upstream cost.
 */
@Injectable()
export class AuditDashboardService {
  private readonly logger = new Logger(AuditDashboardService.name);
  private readonly detailCache = new TtlCache<BidAuditDetail>({ ttlMs: 300_000 });
  private readonly summaryCache = new TtlCache<DashboardSummary>({ ttlMs: 300_000 });
  private readonly costsCache = new TtlCache<CostsResponse>({ ttlMs: 300_000 });

  constructor(
    private readonly bids: BidsService,
    private readonly auditLogs: AuditLogAggregator,
    private readonly langfuse: LangfuseAggregator,
    private readonly temporal: TemporalAggregator,
  ) {}

  async getBidDetail(bidId: string): Promise<BidAuditDetail> {
    return this.detailCache.getOrLoad(`bid:${bidId}`, async () => {
      const warnings: string[] = [];
      let bid: Awaited<ReturnType<BidsService['findOne']>> | null = null;
      try {
        bid = await this.bids.findOne(bidId);
      } catch (err) {
        if (err instanceof NotFoundException) throw err;
        warnings.push(`bids.findOne failed: ${(err as Error).message}`);
      }

      const [decisionTrailResult, historyResult, costsResult] =
        await Promise.allSettled([
          this.auditLogs.forBid(bidId),
          this.temporal.forWorkflow(bid?.workflowId ?? null),
          this.langfuse.forBid(bidId),
        ]);

      const decisionTrail =
        decisionTrailResult.status === 'fulfilled' ? decisionTrailResult.value : [];
      if (decisionTrailResult.status === 'rejected') {
        warnings.push(
          `audit_log read failed: ${(decisionTrailResult.reason as Error).message}`,
        );
      }

      const history =
        historyResult.status === 'fulfilled'
          ? historyResult.value
          : { events: [], warning: (historyResult.reason as Error).message };
      if (history.warning) warnings.push(history.warning);

      const cost =
        costsResult.status === 'fulfilled'
          ? costsResult.value
          : { costs: EMPTY_COSTS, warning: (costsResult.reason as Error).message };
      if (cost.warning) warnings.push(cost.warning);

      const completedAction = decisionTrail
        .slice()
        .reverse()
        .find((d) => d.action.includes('workflow'));
      return {
        bidId,
        workflowId: bid?.workflowId ?? null,
        summary: {
          status: bid?.status ?? 'unknown',
          createdAt: bid?.createdAt ?? null,
          completedAt: bid?.updatedAt ?? null,
          totalDurationMs:
            bid?.createdAt && completedAction
              ? new Date(completedAction.timestamp).getTime() -
                new Date(bid.createdAt).getTime()
              : null,
        },
        decisionTrail,
        workflowHistory: history.events,
        costs: cost.costs,
        warnings,
      };
    });
  }

  async getSummary(query: SummaryQuery): Promise<DashboardSummary> {
    const key = summaryKey(query);
    return this.summaryCache.getOrLoad(key, async () => {
      const warnings: string[] = [];
      const from = new Date(`${query.from}T00:00:00.000Z`);
      const to = new Date(`${query.to}T23:59:59.999Z`);
      if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) {
        throw new Error(`invalid date range: ${query.from}..${query.to}`);
      }

      const [recentResult, distinctResult, costResult, bidListResult] =
        await Promise.allSettled([
          this.auditLogs.recent({
            from,
            to,
            role: query.role,
            limit: query.limit ?? 25,
          }),
          this.auditLogs.distinctBidCount({ from, to }),
          this.langfuse.aggregateRange({ from, to }),
          this.bids.findAll(),
        ]);

      const recent =
        recentResult.status === 'fulfilled' ? recentResult.value : [];
      if (recentResult.status === 'rejected') {
        warnings.push(
          `audit_log recent failed: ${(recentResult.reason as Error).message}`,
        );
      }

      const distinctBids =
        distinctResult.status === 'fulfilled' ? distinctResult.value : 0;
      if (distinctResult.status === 'rejected') {
        warnings.push(
          `audit_log count failed: ${(distinctResult.reason as Error).message}`,
        );
      }

      const costs =
        costResult.status === 'fulfilled'
          ? costResult.value
          : {
              total: 0,
              byAgent: {},
              byDay: {},
              warning: (costResult.reason as Error).message,
            };
      if (costs.warning) warnings.push(costs.warning);

      const allBids =
        bidListResult.status === 'fulfilled' ? bidListResult.value : [];
      if (bidListResult.status === 'rejected') {
        warnings.push(
          `bids.findAll failed: ${(bidListResult.reason as Error).message}`,
        );
      }

      const inRange = allBids.filter((b) => {
        const t = new Date(b.createdAt).getTime();
        return !Number.isNaN(t) && t >= from.getTime() && t <= to.getTime();
      });
      const filtered = inRange.filter((b) => {
        if (query.status && b.status !== query.status) return false;
        if (query.profile && b.estimatedProfile !== query.profile) return false;
        if (
          query.client &&
          !b.clientName.toLowerCase().includes(query.client.toLowerCase())
        )
          return false;
        return true;
      });

      const totals = {
        bids: filtered.length,
        completed: filtered.filter((b) => b.status === 'WON').length,
        rejected: filtered.filter((b) => b.status === 'LOST').length,
        blocked: filtered.filter((b) => b.status === 'DRAFT').length,
      };

      const byDay = Object.entries(costs.byDay).map(([date, costUsd]) => ({
        date,
        costUsd: costUsd as number,
        bidCount: filtered.filter((b) => b.createdAt.startsWith(date)).length,
      }));

      const topBids = filtered
        .slice(0, 10)
        .map((b) => ({
          bidId: b.id,
          clientName: b.clientName,
          costUsd: 0, // per-bid breakdown requires an N-query loop; Phase 3.4 if ops ask.
        }));

      const bidCount = filtered.length || 1;
      return {
        dateRange: { from: query.from, to: query.to },
        totals: { ...totals, bids: distinctBids || totals.bids },
        costUsd: {
          total: costs.total,
          avgPerBid: costs.total / bidCount,
          p95PerBid: 0,
        },
        agentCost: {
          ba: costs.byAgent.ba ?? 0,
          sa: costs.byAgent.sa ?? 0,
          domain: costs.byAgent.domain ?? 0,
        },
        byDay,
        topBids,
        recentDecisions: recent.map((r) => ({
          ...r,
          bidId: r.resourceId,
        })),
        warnings,
      };
    });
  }

  async getCosts(query: CostsQuery): Promise<CostsResponse> {
    const key = costsKey(query);
    return this.costsCache.getOrLoad(key, async () => {
      const warnings: string[] = [];
      const from = new Date(`${query.from}T00:00:00.000Z`);
      const to = new Date(`${query.to}T23:59:59.999Z`);
      const groupBy = query.groupBy ?? 'agent';

      const range = await this.langfuse.aggregateRange({ from, to });
      if (range.warning) warnings.push(range.warning);

      const source =
        groupBy === 'agent'
          ? range.byAgent
          : groupBy === 'bid'
            ? {} // real per-bid grouping needs a separate Langfuse query; deferred.
            : {};
      if (groupBy === 'bid' || groupBy === 'state') {
        warnings.push(
          `group-by '${groupBy}' not wired yet — falling back to empty buckets.`,
        );
      }

      const buckets = Object.entries(source).map(([k, v]) => ({
        key: k,
        totalUsd: v as number,
        generationCount: 0,
      }));
      buckets.sort((a, b) => b.totalUsd - a.totalUsd);

      return {
        dateRange: { from: query.from, to: query.to },
        groupBy,
        buckets,
        warnings,
      };
    });
  }

  /** Collapse a summary into a flat CSV (dashboard ops export). */
  summaryToCsv(summary: DashboardSummary): string {
    const header = [
      'date',
      'bid_count',
      'cost_usd',
    ];
    const lines = [header.join(',')];
    for (const row of summary.byDay) {
      lines.push(
        [row.date, row.bidCount, row.costUsd.toFixed(4)].map(csvCell).join(','),
      );
    }
    const footer = [
      '',
      `# totals.bids=${summary.totals.bids}`,
      `# totals.completed=${summary.totals.completed}`,
      `# totals.rejected=${summary.totals.rejected}`,
      `# totals.blocked=${summary.totals.blocked}`,
      `# cost.total_usd=${summary.costUsd.total.toFixed(4)}`,
      `# warnings=${summary.warnings.length}`,
    ];
    return [...lines, ...footer].join('\n');
  }
}

function summaryKey(q: SummaryQuery): string {
  return [
    q.from,
    q.to,
    q.role ?? '',
    q.status ?? '',
    q.profile ?? '',
    q.client ?? '',
    q.page ?? 0,
    q.limit ?? 25,
  ].join('|');
}

function costsKey(q: CostsQuery): string {
  return [q.from, q.to, q.groupBy ?? 'agent'].join('|');
}

function csvCell(value: unknown): string {
  const s = String(value ?? '');
  if (s.includes(',') || s.includes('"') || s.includes('\n')) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}
