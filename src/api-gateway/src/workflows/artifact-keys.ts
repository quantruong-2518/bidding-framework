/**
 * Canonical list of artifact keys exposed by `BidState`.
 *
 * Kept in a leaf module so both `AclService` (which validates keys against
 * this list) and `WorkflowsController` (which re-exports it for the DTO
 * layer) can import without a circular reference.
 *
 * Keep in sync with `src/ai-service/workflows/acl.py::ArtifactKey`.
 */
export const ARTIFACT_KEYS = [
  'bid_card',
  'triage',
  'scoping',
  'ba_draft',
  'sa_draft',
  'domain_notes',
  'convergence',
  'hld',
  'wbs',
  'pricing',
  'proposal_package',
  'reviews',
  'submission',
  'retrospective',
] as const;

export type ArtifactKey = (typeof ARTIFACT_KEYS)[number];
