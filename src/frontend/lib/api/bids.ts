import { apiFetch } from './client';
import type {
  Bid,
  CreateBidInput,
  UpdateBidInput,
  ReviewSignalInput,
  TriageSignalInput,
  WorkflowStatus,
  WorkflowTrigger,
} from './types';

export function listBids(): Promise<Bid[]> {
  return apiFetch<Bid[]>('/bids');
}

export function getBid(id: string): Promise<Bid> {
  return apiFetch<Bid>(`/bids/${encodeURIComponent(id)}`);
}

export function createBid(input: CreateBidInput): Promise<Bid> {
  return apiFetch<Bid>('/bids', { method: 'POST', body: input });
}

export function updateBid(id: string, input: UpdateBidInput): Promise<Bid> {
  return apiFetch<Bid>(`/bids/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: input,
  });
}

export function deleteBid(id: string): Promise<void> {
  return apiFetch<void>(`/bids/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export function triggerWorkflow(id: string): Promise<WorkflowTrigger> {
  return apiFetch<WorkflowTrigger>(
    `/bids/${encodeURIComponent(id)}/workflow`,
    { method: 'POST' },
  );
}

export function sendTriageSignal(
  id: string,
  input: TriageSignalInput,
): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(
    `/bids/${encodeURIComponent(id)}/workflow/triage-signal`,
    { method: 'POST', body: input },
  );
}

export function sendReviewSignal(
  id: string,
  input: ReviewSignalInput,
): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(
    `/bids/${encodeURIComponent(id)}/workflow/review-signal`,
    { method: 'POST', body: input },
  );
}

export function getWorkflowStatus(id: string): Promise<WorkflowStatus> {
  return apiFetch<WorkflowStatus>(
    `/bids/${encodeURIComponent(id)}/workflow/status`,
  );
}

/**
 * Fetch a single named artifact from the workflow state. Use this when a panel
 * needs fresh data without pulling the full `WorkflowStatus` envelope. The
 * type values match the Python `BidState` keys — see
 * `src/api-gateway/src/workflows/workflows.controller.ts::ARTIFACT_KEYS`.
 */
export function getWorkflowArtifact<T>(
  id: string,
  type: string,
): Promise<T> {
  return apiFetch<T>(
    `/bids/${encodeURIComponent(id)}/workflow/artifacts/${encodeURIComponent(type)}`,
  );
}

/**
 * Phase 3.5 — fetch the Langfuse trace URL for a bid. 404 when the
 * observability stack isn't configured (LANGFUSE_WEB_URL unset on the
 * gateway); callers should hide the link in that case.
 */
export function getBidTraceUrl(id: string): Promise<{ url: string }> {
  return apiFetch<{ url: string }>(
    `/bids/${encodeURIComponent(id)}/trace-url`,
  );
}
