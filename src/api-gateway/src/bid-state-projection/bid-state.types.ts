/**
 * Conv-16a — terminal-state list shared by consumer + service.
 *
 * Mirrors `BidWorkflow` in ai-service. When a new terminal state is added on
 * the workflow side, mirror it here AND extend `terminal-detection.spec.ts`.
 */
export const TERMINAL_STATES: ReadonlySet<string> = new Set([
  'S11_DONE',
  'S9_BLOCKED',
  'S1_NO_BID',
]);

/**
 * Outcome-tag derivation per terminal state (used by Bid post-mortem queries).
 */
export const TERMINAL_OUTCOMES: Readonly<Record<string, string>> = {
  S11_DONE: 'COMPLETED',
  S9_BLOCKED: 'BLOCKED',
  S1_NO_BID: 'NO_BID',
};

/**
 * Stream entry parsed off the `bid.transitions` Redis stream. Mirrors the
 * `_stream_fields` helper in `ai-service/activities/state_transition.py`.
 */
export interface ParsedTransitionEntry {
  bidId: string;
  workflowId: string;
  transitionSeq: number;
  tenantId: string;
  fromState: string | null;
  toState: string;
  profile: string;
  artifactKeys: string[];
  occurredAt: string;
  llmCostDelta: number | null;
}

/**
 * Read-side response shape for `GET /bids/:id/state`. Independently typed
 * from the entity so internal field renames don't break the API.
 */
export interface BidStateView {
  bidId: string;
  workflowId: string;
  tenantId: string;
  currentState: string;
  profile: string;
  clientName: string;
  industry: string;
  lastTransitionSeq: number;
  lastTransitionAt: string;
  artifactsDone: Record<string, string>;
  isTerminal: boolean;
  outcome: string | null;
  totalLlmCostUsd: number;
  updatedAt: string;
}
