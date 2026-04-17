import { apiFetch } from './client';
import type {
  Bid,
  CreateBidInput,
  UpdateBidInput,
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

export function getWorkflowStatus(id: string): Promise<WorkflowStatus> {
  return apiFetch<WorkflowStatus>(
    `/bids/${encodeURIComponent(id)}/workflow/status`,
  );
}
