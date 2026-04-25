import { apiFetch, apiBaseUrl } from './client';
import { useAuthStore } from '@/lib/auth/store';

export interface DecisionTrailEntry {
  timestamp: string;
  action: string;
  actor: { userSub: string; username: string; roles: string[] };
  resourceType: string;
  resourceId: string | null;
  statusCode: number;
  metadata: Record<string, unknown> | null;
}

export interface WorkflowHistoryEvent {
  eventId: number;
  eventType: string;
  timestamp: string;
  attributes: Record<string, unknown>;
}

export interface BidCostBreakdown {
  totalUsd: number;
  byAgent: Record<string, number>;
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

export interface DashboardSummary {
  dateRange: { from: string; to: string };
  totals: {
    bids: number;
    completed: number;
    rejected: number;
    blocked: number;
  };
  costUsd: { total: number; avgPerBid: number; p95PerBid: number };
  agentCost: { ba: number; sa: number; domain: number };
  byDay: Array<{ date: string; bidCount: number; costUsd: number }>;
  topBids: Array<{ bidId: string; clientName: string; costUsd: number }>;
  recentDecisions: Array<DecisionTrailEntry & { bidId: string | null }>;
  warnings: string[];
}

export interface SummaryFilters {
  from?: string;
  to?: string;
  role?: string;
  status?: string;
  profile?: string;
  client?: string;
}

function buildQuery(filters: SummaryFilters): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== null && v !== '') params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

export async function fetchBidAudit(bidId: string): Promise<BidAuditDetail> {
  return apiFetch<BidAuditDetail>(
    `/bids/${encodeURIComponent(bidId)}/audit`,
  );
}

export async function fetchSummary(
  filters: SummaryFilters = {},
): Promise<DashboardSummary> {
  return apiFetch<DashboardSummary>(
    `/dashboard/audit${buildQuery(filters)}`,
  );
}

/**
 * Build the URL the browser should GET to download the CSV. Auth is
 * picked up by the server via the token header the caller adds; used
 * directly in an `<a download>` or programmatic fetch.
 */
export function buildCsvUrl(filters: SummaryFilters = {}): string {
  return `${apiBaseUrl()}/dashboard/audit.csv${buildQuery(filters)}`;
}

/** Trigger a CSV download via blob so the access token rides along. */
export async function downloadCsv(filters: SummaryFilters = {}): Promise<void> {
  const token = useAuthStore.getState().accessToken;
  const headers: Record<string, string> = { Accept: 'text/csv' };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(buildCsvUrl(filters), { headers });
  if (!res.ok) throw new Error(`CSV export failed: ${res.status}`);
  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = href;
  a.download = 'audit-summary.csv';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(href);
}
