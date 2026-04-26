import type { ParseSessionStatus } from '../parse-session.entity';

/**
 * S0.5 Wave 2B — exact §3.6 PreviewResponse contract for
 * ``GET /bids/parse/:sid/preview``.
 *
 * Plain TypeScript interfaces (no class-validator) — this is a *response*
 * shape, not a validated input. Consumers (frontend Zod schema) verify on
 * their side.
 */

export interface SuggestedBidCardPreview {
  name: string;
  client_name: string;
  industry: string;
  region: string;
  /** ISO-8601 date string. */
  deadline: string;
  scope_summary: string;
  estimated_profile: 'S' | 'M' | 'L' | 'XL';
  language: 'en' | 'vi';
  technology_keywords: string[];
}

export interface AtomPreviewItem {
  id: string;
  type:
    | 'functional'
    | 'nfr'
    | 'technical'
    | 'compliance'
    | 'timeline'
    | 'unclear';
  priority: 'MUST' | 'SHOULD' | 'COULD' | 'WONT';
  category: string;
  source_file: string;
  body_md: string;
  confidence: number;
  split_recommended?: boolean;
}

export interface SourcePreviewItem {
  file_id: string;
  original_name: string;
  mime: string;
  page_count?: number | null;
  role: string;
  language: string;
  parsed_to: string;
  atoms_extracted: number;
}

export interface ConflictItem {
  id: string;
  description: string;
  atom_ids: string[];
  severity?: 'low' | 'medium' | 'high';
}

export interface SuggestedWorkflow {
  profile: 'S' | 'M' | 'L' | 'XL';
  pipeline: string[];
  estimated_total_token_cost_usd: number;
  estimated_duration_hours: number;
  review_gate: {
    reviewer_count: number;
    timeout_hours: number;
    max_rounds: number;
  };
}

export interface PreviewResponseDto {
  session_id: string;
  status: ParseSessionStatus;

  /** Populated only when ``status === 'PARSING'``. */
  progress?: { stage: string; percent: number };

  /** Populated only when ``status === 'FAILED'``. */
  parse_error?: string;

  suggested_bid_card: SuggestedBidCardPreview | null;

  context_preview: {
    anchor_md: string;
    summary_md: string;
    open_questions: string[];
  };

  atoms_preview: {
    total: number;
    by_type: Record<string, number>;
    by_priority: Record<string, number>;
    low_confidence_count: number;
    sample: AtomPreviewItem[];
  };

  sources_preview: SourcePreviewItem[];

  conflicts_detected: ConflictItem[];

  suggested_workflow: SuggestedWorkflow | null;

  current_state: 'AWAITING_CONFIRM' | 'CONFIRMED' | 'ABANDONED';
  /** ISO-8601 string. */
  expires_at: string;
}
