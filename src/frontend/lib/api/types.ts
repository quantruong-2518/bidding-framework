/**
 * Shared DTOs + Zod schemas mirroring the NestJS api-gateway contract
 * (see src/api-gateway/src/bids and workflows for source of truth).
 */
import { z } from 'zod';
import type { WorkflowState } from '@/lib/utils/state-palette';

export const BidProfile = z.enum(['S', 'M', 'L', 'XL']);
export type BidProfile = z.infer<typeof BidProfile>;

export const BidStatus = z.enum([
  'DRAFT',
  'TRIAGED',
  'IN_PROGRESS',
  'WON',
  'LOST',
]);
export type BidStatus = z.infer<typeof BidStatus>;

export const BidSchema = z.object({
  id: z.string(),
  clientName: z.string(),
  industry: z.string(),
  region: z.string(),
  deadline: z.string(),
  scopeSummary: z.string(),
  technologyKeywords: z.array(z.string()),
  estimatedProfile: BidProfile,
  status: BidStatus,
  workflowId: z.string().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type Bid = z.infer<typeof BidSchema>;

export const CreateBidSchema = z.object({
  clientName: z.string().min(1, 'Client name is required').max(200),
  industry: z.string().min(1, 'Industry is required').max(100),
  region: z.string().min(1, 'Region is required').max(100),
  deadline: z.string().min(1, 'Deadline is required'),
  scopeSummary: z.string().max(5000).default(''),
  technologyKeywords: z
    .array(z.string().min(1))
    .min(1, 'Add at least one technology keyword'),
  estimatedProfile: BidProfile.optional(),
});
export type CreateBidInput = z.infer<typeof CreateBidSchema>;

export const UpdateBidSchema = CreateBidSchema.partial().extend({
  status: BidStatus.optional(),
});
export type UpdateBidInput = z.infer<typeof UpdateBidSchema>;

export const TriageSignalSchema = z.object({
  approved: z.boolean(),
  reviewer: z.string().min(1).max(200),
  notes: z.string().max(5000).optional(),
  bidProfileOverride: BidProfile.optional(),
});
export type TriageSignalInput = z.infer<typeof TriageSignalSchema>;

// --- Phase 2.4 human review signal -----------------------------------------

export const ReviewVerdict = z.enum([
  'APPROVED',
  'REJECTED',
  'CHANGES_REQUESTED',
]);
export type ReviewVerdict = z.infer<typeof ReviewVerdict>;

export const ReviewerRole = z.enum([
  'bid_manager',
  'ba',
  'sa',
  'qc',
  'domain_expert',
  'solution_lead',
]);
export type ReviewerRole = z.infer<typeof ReviewerRole>;

export const ReviewCommentSeverity = z.enum(['NIT', 'MINOR', 'MAJOR', 'BLOCKER']);
export type ReviewCommentSeverity = z.infer<typeof ReviewCommentSeverity>;

export const ReviewTargetState = z.enum(['S2', 'S5', 'S6', 'S8']);
export type ReviewTargetState = z.infer<typeof ReviewTargetState>;

export const ReviewCommentSchema = z.object({
  section: z.string().min(1).max(200),
  severity: ReviewCommentSeverity,
  message: z.string().min(1).max(5000),
  targetState: ReviewTargetState.optional(),
});
export type ReviewCommentInput = z.infer<typeof ReviewCommentSchema>;

export const ReviewSignalSchema = z.object({
  verdict: ReviewVerdict,
  reviewer: z.string().min(1).max(200),
  reviewerRole: ReviewerRole,
  comments: z.array(ReviewCommentSchema).max(50).default([]),
  notes: z.string().max(5000).optional(),
});
export type ReviewSignalInput = z.infer<typeof ReviewSignalSchema>;

/**
 * Mirrors Python BidState fields we care about in the UI. Fields are optional
 * because early states only populate a subset.
 */
export interface BidCard {
  client_name?: string;
  industry?: string;
  region?: string;
  deadline?: string;
  scope_summary?: string;
  technology_keywords?: string[];
  estimated_profile?: BidProfile;
  requirements_raw?: string[];
}

/**
 * Matches Python `workflows.models.TriageDecision` emitted by S1.
 *
 * `overall_score` is 0–100; `score_breakdown` holds per-criterion sub-scores
 * (typically 0–1). The review signal (`approved`, `reviewer`, `notes`) is a
 * separate payload the frontend sends — not part of this read-only artifact.
 */
export interface Triage {
  recommendation?: 'BID' | 'NO_BID';
  overall_score?: number;
  score_breakdown?: Record<string, number>;
  rationale?: string;
}

export interface ScopingWorkstream {
  id: string;
  name: string;
  requirements?: string[];
  estimated_effort_md?: number;
}

export interface Scoping {
  workstreams?: ScopingWorkstream[];
  summary?: string;
}

// ---------------------------------------------------------------------------
// Phase 2.1 artifact shapes — snake_case to match the Python payload emitted
// by the Temporal workflow (`src/ai-service/workflows/artifacts.py`). Fields
// on each draft are a subset — expand as the UI starts rendering more.
// ---------------------------------------------------------------------------

export interface FunctionalRequirement {
  id: string;
  title: string;
  description: string;
  priority: 'MUST' | 'SHOULD' | 'COULD' | 'WONT';
  rationale: string;
}

export interface RiskItem {
  title: string;
  likelihood: string;
  impact: string;
  mitigation: string;
}

export interface BusinessRequirementsDraft {
  bid_id: string;
  executive_summary: string;
  business_objectives: string[];
  scope: { in_scope: string[]; out_of_scope: string[] };
  functional_requirements: FunctionalRequirement[];
  assumptions: string[];
  constraints: string[];
  success_criteria: string[];
  risks: RiskItem[];
  confidence: number;
  sources: string[];
}

export interface TechStackChoice {
  layer: string;
  choice: string;
  rationale: string;
}

export interface ArchitecturePattern {
  name: string;
  description: string;
  applies_to: string[];
}

export interface TechnicalRisk {
  title: string;
  likelihood: string;
  impact: string;
  mitigation: string;
}

export interface SolutionArchitectureDraft {
  bid_id: string;
  tech_stack: TechStackChoice[];
  architecture_patterns: ArchitecturePattern[];
  nfr_targets: Record<string, string>;
  technical_risks: TechnicalRisk[];
  integrations: string[];
  confidence: number;
  sources: string[];
}

export interface ComplianceItem {
  framework: string;
  requirement: string;
  applies: boolean;
  notes?: string;
}

export interface DomainPractice {
  title: string;
  description: string;
}

export interface DomainNotes {
  bid_id: string;
  industry: string;
  compliance: ComplianceItem[];
  best_practices: DomainPractice[];
  industry_constraints: string[];
  glossary: Record<string, string>;
  confidence: number;
  sources: string[];
}

export interface ConvergenceReport {
  bid_id: string;
  unified_summary: string;
  readiness: Record<string, number>;
  conflicts: Array<{
    streams: string[];
    topic: string;
    description: string;
    severity: 'LOW' | 'MEDIUM' | 'HIGH';
    proposed_resolution: string;
  }>;
  open_questions: string[];
}

export interface HLDComponent {
  name: string;
  responsibility: string;
  depends_on: string[];
}

export interface HLDDraft {
  bid_id: string;
  architecture_overview: string;
  components: HLDComponent[];
  data_flows: string[];
  integration_points: string[];
  security_approach: string;
  deployment_model: string;
}

export interface WBSItem {
  id: string;
  name: string;
  parent_id: string | null;
  effort_md: number;
  owner_role?: string | null;
  depends_on: string[];
}

export interface WBSDraft {
  bid_id: string;
  items: WBSItem[];
  total_effort_md: number;
  timeline_weeks: number;
  critical_path: string[];
}

export interface PricingLine {
  label: string;
  amount: number;
  unit: string;
  notes?: string;
}

export interface PricingDraft {
  bid_id: string;
  model: 'fixed_price' | 'time_and_materials' | 'hybrid';
  currency: string;
  lines: PricingLine[];
  subtotal: number;
  margin_pct: number;
  total: number;
  scenarios: Record<string, number>;
  notes: string;
}

export interface ProposalSection {
  heading: string;
  body_markdown: string;
  sourced_from: string[];
}

export interface ProposalPackage {
  bid_id: string;
  title: string;
  sections: ProposalSection[];
  appendices: string[];
  consistency_checks: Record<string, boolean>;
}

export interface ReviewRecord {
  bid_id: string;
  reviewer_role: string;
  reviewer: string;
  verdict: 'APPROVED' | 'REJECTED' | 'CHANGES_REQUESTED';
  comments: Array<{
    section: string;
    severity: 'NIT' | 'MINOR' | 'MAJOR' | 'BLOCKER';
    message: string;
    target_state?: string | null;
  }>;
  reviewed_at: string;
}

export interface LoopBack {
  round: number;
  target_state: 'S2' | 'S5' | 'S6' | 'S8';
  reason: string;
  at: string;
}

export interface SubmissionRecord {
  bid_id: string;
  submitted_at: string;
  channel: string;
  confirmation_id: string | null;
  package_checksum: string | null;
  checklist: Record<string, boolean>;
}

export interface Lesson {
  title: string;
  category: 'win_pattern' | 'loss_pattern' | 'estimation' | 'process';
  detail: string;
}

export interface RetrospectiveDraft {
  bid_id: string;
  outcome: 'WIN' | 'LOSS' | 'PENDING';
  lessons: Lesson[];
  kb_updates: string[];
}

export interface WorkflowTrigger {
  bid: Bid;
  workflow: {
    workflow_id: string;
    run_id?: string;
    status?: string;
  };
}

export interface WorkflowStatus {
  workflow_id: string;
  status: string;
  state?: WorkflowState;
  current_state?: WorkflowState;
  bid_card?: BidCard;
  triage?: Triage;
  scoping?: Scoping;
  profile?: BidProfile;
  // Phase 2.1 artifacts — populated as the workflow walks the DAG.
  ba_draft?: BusinessRequirementsDraft;
  sa_draft?: SolutionArchitectureDraft;
  domain_notes?: DomainNotes;
  convergence?: ConvergenceReport;
  hld?: HLDDraft;
  wbs?: WBSDraft;
  pricing?: PricingDraft;
  proposal_package?: ProposalPackage;
  reviews?: ReviewRecord[];
  submission?: SubmissionRecord;
  retrospective?: RetrospectiveDraft;
  loop_back_history?: LoopBack[];
  [key: string]: unknown;
}

export interface AuthUser {
  sub: string;
  username: string;
  email?: string;
  roles: string[];
}

// ---------------------------------------------------------------------------
// S0.5 Wave 3 — parse session schemas. Mirrors the NestJS DTOs in
// `src/api-gateway/src/parse-sessions/dto/{preview-response,confirm-request,
// upload-files}.dto.ts`. These shapes round-trip through MinIO + Postgres
// before reaching the UI; we re-validate at the network boundary so a stale
// or partially-failed parse session can't crash the panel.
// ---------------------------------------------------------------------------

export const ParseSessionStatusEnum = z.enum([
  'PARSING',
  'READY',
  'CONFIRMED',
  'ABANDONED',
  'FAILED',
]);
export type ParseSessionStatus = z.infer<typeof ParseSessionStatusEnum>;

export const BidProfileEnum = z.enum(['S', 'M', 'L', 'XL']);
export type BidProfileLevel = z.infer<typeof BidProfileEnum>;

export const LanguageEnum = z.enum(['en', 'vi']);
export type Language = z.infer<typeof LanguageEnum>;

export const AtomPreviewItemSchema = z.object({
  id: z.string(),
  type: z.enum([
    'functional',
    'nfr',
    'technical',
    'compliance',
    'timeline',
    'unclear',
  ]),
  priority: z.enum(['MUST', 'SHOULD', 'COULD', 'WONT']),
  category: z.string(),
  source_file: z.string(),
  body_md: z.string(),
  confidence: z.number(),
  split_recommended: z.boolean().optional(),
});
export type AtomPreviewItem = z.infer<typeof AtomPreviewItemSchema>;

export const SourcePreviewItemSchema = z.object({
  file_id: z.string(),
  original_name: z.string(),
  mime: z.string(),
  page_count: z.number().nullable().optional(),
  role: z.string(),
  language: z.string(),
  parsed_to: z.string(),
  atoms_extracted: z.number(),
});
export type SourcePreviewItem = z.infer<typeof SourcePreviewItemSchema>;

export const ConflictItemSchema = z.object({
  id: z.string(),
  description: z.string(),
  atom_ids: z.array(z.string()),
  severity: z.enum(['low', 'medium', 'high']).optional(),
});
export type ConflictItem = z.infer<typeof ConflictItemSchema>;

export const SuggestedBidCardSchema = z.object({
  name: z.string(),
  client_name: z.string(),
  industry: z.string(),
  region: z.string(),
  deadline: z.string(),
  scope_summary: z.string(),
  estimated_profile: BidProfileEnum,
  language: LanguageEnum,
  technology_keywords: z.array(z.string()),
});
export type SuggestedBidCard = z.infer<typeof SuggestedBidCardSchema>;

export const ContextPreviewSchema = z.object({
  anchor_md: z.string(),
  summary_md: z.string(),
  open_questions: z.array(z.string()),
});
export type ContextPreview = z.infer<typeof ContextPreviewSchema>;

export const AtomsPreviewSchema = z.object({
  total: z.number(),
  by_type: z.record(z.string(), z.number()),
  by_priority: z.record(z.string(), z.number()),
  low_confidence_count: z.number(),
  sample: z.array(AtomPreviewItemSchema),
});
export type AtomsPreview = z.infer<typeof AtomsPreviewSchema>;

export const SuggestedWorkflowSchema = z.object({
  profile: BidProfileEnum,
  pipeline: z.array(z.string()),
  estimated_total_token_cost_usd: z.number(),
  estimated_duration_hours: z.number(),
  review_gate: z.object({
    reviewer_count: z.number(),
    timeout_hours: z.number(),
    max_rounds: z.number(),
  }),
});
export type SuggestedWorkflow = z.infer<typeof SuggestedWorkflowSchema>;

export const PreviewResponseSchema = z.object({
  session_id: z.string(),
  status: ParseSessionStatusEnum,
  progress: z
    .object({ stage: z.string(), percent: z.number() })
    .optional(),
  parse_error: z.string().optional(),
  suggested_bid_card: SuggestedBidCardSchema.nullable(),
  context_preview: ContextPreviewSchema,
  atoms_preview: AtomsPreviewSchema,
  sources_preview: z.array(SourcePreviewItemSchema),
  conflicts_detected: z.array(ConflictItemSchema),
  suggested_workflow: SuggestedWorkflowSchema.nullable(),
  current_state: z.enum(['AWAITING_CONFIRM', 'CONFIRMED', 'ABANDONED']),
  expires_at: z.string(),
});
export type PreviewResponse = z.infer<typeof PreviewResponseSchema>;

/**
 * Frontmatter patch sent on confirm. The backend re-validates against the
 * canonical Pydantic `AtomFrontmatter` (the `patch` field is loose on
 * purpose so we can ship priority/category/tags/text edits without a
 * schema bump on every UX iteration).
 */
export const AtomEditSchema = z.object({
  id: z.string().min(1).max(64),
  patch: z.record(z.string(), z.unknown()),
});
export type AtomEdit = z.infer<typeof AtomEditSchema>;

export const ConfirmRequestSchema = z.object({
  client_name: z.string().min(1).max(200).optional(),
  industry: z.string().min(1).max(100).optional(),
  region: z.string().min(1).max(100).optional(),
  deadline: z.string().optional(),
  profile_override: BidProfileEnum.optional(),
  name: z.string().min(1).max(200).optional(),
  atom_edits: z.array(AtomEditSchema).max(2_000).optional(),
  atom_rejects: z.array(z.string()).max(2_000).optional(),
});
export type ConfirmRequest = z.infer<typeof ConfirmRequestSchema>;

export const ConfirmResponseSchema = z.object({
  bid_id: z.string(),
  workflow_id: z.string(),
  vault_path: z.string(),
  trace_id: z.string().optional(),
});
export type ConfirmResponse = z.infer<typeof ConfirmResponseSchema>;
