/**
 * Workflow state palette. Maps each Temporal BidState literal to a label,
 * description, and color token. Source of truth for anything rendering
 * workflow state (badges, graph nodes, timeline).
 */

export type WorkflowState =
  | 'S0'
  | 'S1'
  | 'S1_NO_BID'
  | 'S2'
  | 'S2_DONE'
  | 'S3'
  | 'S4'
  | 'S5'
  | 'S6'
  | 'S7'
  | 'S8'
  | 'S9'
  | 'S9_BLOCKED'
  | 'S10'
  | 'S11'
  | 'S11_DONE';

export type NodeKind =
  | 'S0'
  | 'S1'
  | 'S2'
  | 'S3a'
  | 'S3b'
  | 'S3c'
  | 'S4'
  | 'S5'
  | 'S6'
  | 'S7'
  | 'S8'
  | 'S9'
  | 'S10'
  | 'S11';

export type StatusTone =
  | 'neutral'
  | 'active'
  | 'done'
  | 'warning'
  | 'danger'
  | 'pending';

export interface StateMeta {
  state: WorkflowState;
  label: string;
  description: string;
  tone: StatusTone;
}

export const STATE_PALETTE: Record<WorkflowState, StateMeta> = {
  S0: {
    state: 'S0',
    label: 'Intake',
    description: 'Parse RFP metadata and build the Bid Card.',
    tone: 'neutral',
  },
  S1: {
    state: 'S1',
    label: 'Triage',
    description: 'Score the opportunity and wait for Bid Manager decision.',
    tone: 'active',
  },
  S1_NO_BID: {
    state: 'S1_NO_BID',
    label: 'No-Bid',
    description: 'Triage ended with a decision not to pursue this bid.',
    tone: 'danger',
  },
  S2: {
    state: 'S2',
    label: 'Scoping (in-flight)',
    description: 'Breaking scope into workstreams.',
    tone: 'active',
  },
  S2_DONE: {
    state: 'S2_DONE',
    label: 'Scoping Complete',
    description: 'Scope decomposed; ready to dispatch parallel streams.',
    tone: 'done',
  },
  S3: {
    state: 'S3',
    label: 'Parallel Streams',
    description: 'S3a Business, S3b Technical, S3c Domain running in parallel.',
    tone: 'active',
  },
  S4: {
    state: 'S4',
    label: 'Convergence',
    description: 'Reconcile stream outputs into a single view.',
    tone: 'neutral',
  },
  S5: {
    state: 'S5',
    label: 'Solution Design',
    description: 'High-level design and architecture decisions.',
    tone: 'neutral',
  },
  S6: {
    state: 'S6',
    label: 'WBS + Estimation',
    description: 'Work breakdown and effort estimation.',
    tone: 'neutral',
  },
  S7: {
    state: 'S7',
    label: 'Commercial Strategy',
    description: 'Pricing, terms, and commercial model.',
    tone: 'neutral',
  },
  S8: {
    state: 'S8',
    label: 'Assembly',
    description: 'Assemble the proposal document.',
    tone: 'neutral',
  },
  S9: {
    state: 'S9',
    label: 'Review Gate',
    description: 'Reviewer approval — can loop back on rejection.',
    tone: 'warning',
  },
  S9_BLOCKED: {
    state: 'S9_BLOCKED',
    label: 'Review Blocked',
    description: 'Review gate exceeded max rounds or was rejected outright.',
    tone: 'danger',
  },
  S10: {
    state: 'S10',
    label: 'Submission',
    description: 'Deliver the final proposal to the client.',
    tone: 'done',
  },
  S11: {
    state: 'S11',
    label: 'Retrospective',
    description: 'Capture lessons learned back into the Knowledge Base.',
    tone: 'done',
  },
  S11_DONE: {
    state: 'S11_DONE',
    label: 'Retrospective Complete',
    description: 'Pipeline complete; retrospective filed back to KB.',
    tone: 'done',
  },
};

/**
 * Tone → Tailwind classes (background/border/text).
 * Used by StatusBadge and WorkflowGraph.
 */
export const TONE_CLASSES: Record<StatusTone, string> = {
  neutral: 'bg-muted text-muted-foreground border-border',
  active: 'bg-primary/10 text-primary border-primary',
  done: 'bg-success/10 text-success border-success',
  warning: 'bg-warning/10 text-warning-foreground border-warning',
  danger: 'bg-destructive/10 text-destructive border-destructive',
  pending: 'bg-muted/40 text-muted-foreground border-dashed border-border',
};

/** Order used by the vertical graph layout (non-branching main path). */
export const MAIN_FLOW: NodeKind[] = [
  'S0',
  'S1',
  'S2',
  'S4',
  'S5',
  'S6',
  'S7',
  'S8',
  'S9',
  'S10',
  'S11',
];

/** Siblings placed horizontally at the S3 row. */
export const PARALLEL_STREAMS: NodeKind[] = ['S3a', 'S3b', 'S3c'];

/** Map a node kind onto the current WorkflowState literal. */
export function nodeKindToState(kind: NodeKind): WorkflowState {
  if (kind === 'S3a' || kind === 'S3b' || kind === 'S3c') return 'S3';
  return kind as WorkflowState;
}

export function getStateMeta(state: WorkflowState | null | undefined): StateMeta | null {
  if (!state) return null;
  return STATE_PALETTE[state] ?? null;
}

export function stateLabel(state: WorkflowState | null | undefined): string {
  return getStateMeta(state)?.label ?? 'Unknown';
}
