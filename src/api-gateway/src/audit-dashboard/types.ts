/**
 * Contracts emitted by the audit-dashboard module.
 *
 * Every aggregation endpoint tolerates partial upstream failure — when one
 * of Temporal / Langfuse / Postgres is unreachable the response carries a
 * `warnings: string[]` list explaining what was missing, and the affected
 * fields degrade to zeros / empty arrays. The dashboard never throws 5xx
 * for an aggregation miss; the user sees what we could load.
 */

/** One row from the `audit_log` table, shaped for UI consumption. */
export interface DecisionTrailEntry {
  timestamp: string; // ISO-8601
  action: string; // HTTP route template — e.g. "POST /bids/:id/workflow"
  actor: {
    userSub: string;
    username: string;
    roles: string[];
  };
  resourceType: string;
  resourceId: string | null;
  statusCode: number;
  metadata: Record<string, unknown> | null;
}

/** One event from Temporal Visibility (shape intentionally loose). */
export interface WorkflowHistoryEvent {
  eventId: number;
  eventType: string;
  timestamp: string;
  attributes: Record<string, unknown>;
}

/** Cost breakdown for a single bid, derived from Langfuse generations. */
export interface BidCostBreakdown {
  totalUsd: number;
  byAgent: Record<string, number>; // 'ba' | 'sa' | 'domain' | 'other'
  byModel: Record<string, number>;
  generationCount: number;
  latencyP95Ms: number;
}

export interface BidAuditDetail {
  bidId: string;
  workflowId: string | null;
  summary: {
    status: string;
    createdAt: string | null;
    completedAt: string | null;
    totalDurationMs: number | null;
  };
  decisionTrail: DecisionTrailEntry[];
  workflowHistory: WorkflowHistoryEvent[];
  costs: BidCostBreakdown;
  warnings: string[];
}

export interface SummaryQuery {
  from: string; // ISO date YYYY-MM-DD
  to: string; // ISO date YYYY-MM-DD (inclusive)
  role?: string;
  status?: string;
  profile?: string;
  client?: string;
  page?: number;
  limit?: number;
}

export interface DashboardSummary {
  dateRange: { from: string; to: string };
  totals: {
    bids: number;
    completed: number; // Bid.status === 'WON'
    rejected: number; // Bid.status === 'LOST'
    inProgress: number; // Bid.status === 'TRIAGED' | 'IN_PROGRESS' | 'DRAFT'
  };
  costUsd: {
    total: number;
    avgPerBid: number;
  };
  agentCost: {
    ba: number;
    sa: number;
    domain: number;
  };
  byDay: Array<{ date: string; bidCount: number; costUsd: number }>;
  /** Newest-first sample (up to 10). `costUsd` is fanned out per bid via
   * Langfuse when configured; defaults to 0 when Langfuse is unwired or
   * the per-bid lookup fails (lookup failure surfaces in `warnings[]`
   * with a single dedup'd entry, not one per bid). */
  recentBids: Array<{
    bidId: string;
    clientName: string;
    status: string;
    costUsd: number;
  }>;
  recentDecisions: Array<
    DecisionTrailEntry & { bidId: string | null }
  >;
  warnings: string[];
}

export interface CostsQuery {
  from: string;
  to: string;
  groupBy?: 'bid' | 'state' | 'agent';
}

export interface CostsResponse {
  dateRange: { from: string; to: string };
  groupBy: 'bid' | 'state' | 'agent';
  buckets: Array<{ key: string; totalUsd: number; generationCount: number }>;
  warnings: string[];
}
