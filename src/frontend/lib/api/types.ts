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
  scopeSummary: z.string().max(2000).default(''),
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
  notes: z.string().max(2000).optional(),
  bidProfileOverride: BidProfile.optional(),
});
export type TriageSignalInput = z.infer<typeof TriageSignalSchema>;

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

export interface TriageScore {
  label?: string;
  score?: number;
  notes?: string;
}

export interface Triage {
  recommend?: 'bid' | 'no-bid';
  confidence?: number;
  scores?: TriageScore[];
  rationale?: string;
  approved?: boolean;
  reviewer?: string;
  notes?: string;
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
  [key: string]: unknown;
}

export interface AuthUser {
  sub: string;
  username: string;
  email?: string;
  roles: string[];
}
