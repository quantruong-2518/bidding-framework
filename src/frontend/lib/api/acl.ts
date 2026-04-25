import { apiFetch } from './client';

/** Matches `src/ai-service/workflows/acl.py::ArtifactKey`. */
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

export type AclMap = Record<ArtifactKey, readonly string[]>;

/**
 * Conservative offline ACL — every artifact visible only to admin. Used as
 * the first-render baseline while the live fetch resolves. The page doesn't
 * *hide* panels preemptively based on this; it just returns False for every
 * non-admin role, which is the safe default before login or on fetch failure.
 */
export const FALLBACK_ACL: AclMap = {
  bid_card: ['admin'],
  triage: ['admin'],
  scoping: ['admin'],
  ba_draft: ['admin'],
  sa_draft: ['admin'],
  domain_notes: ['admin'],
  convergence: ['admin'],
  hld: ['admin'],
  wbs: ['admin'],
  pricing: ['admin'],
  proposal_package: ['admin'],
  reviews: ['admin'],
  submission: ['admin'],
  retrospective: ['admin'],
};

export async function fetchAcl(): Promise<AclMap> {
  return apiFetch<AclMap>('/acl/artifacts');
}

/** Admin is a wildcard; every other role must appear in the artifact's list. */
export function hasArtifactAccess(
  acl: AclMap | null | undefined,
  roles: readonly string[] | null | undefined,
  key: ArtifactKey,
): boolean {
  const roleSet = new Set((roles ?? []).filter(Boolean));
  if (roleSet.has('admin')) return true;
  const allowed = acl?.[key];
  if (!allowed) return false;
  for (const r of allowed) {
    if (roleSet.has(r)) return true;
  }
  return false;
}
