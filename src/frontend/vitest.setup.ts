import '@testing-library/jest-dom/vitest';
import { webcrypto } from 'node:crypto';
import { beforeEach } from 'vitest';
import { useAuthStore } from '@/lib/auth/store';
import { FALLBACK_ACL } from '@/lib/api/acl';

// jsdom does not ship a full WebCrypto implementation. Node 20+ provides
// `globalThis.crypto` + `crypto.subtle`, but if jsdom overrides or hides it
// we bolt Node's webcrypto on before any test touches PKCE helpers.
if (!globalThis.crypto || !globalThis.crypto.subtle) {
  Object.defineProperty(globalThis, 'crypto', {
    value: webcrypto,
    writable: true,
    configurable: true,
  });
}

// Phase 3.2b — panels are now RBAC-gated. Default every test to an admin
// session with a fully-populated ACL so rendering assertions keep working.
// Tests that specifically exercise RBAC filtering override this in their
// own beforeEach.
beforeEach(() => {
  useAuthStore.setState({
    accessToken: 'stub-token',
    refreshToken: null,
    expiresAt: null,
    user: {
      sub: 'kc-admin',
      username: 'admin',
      email: 'a@b.c',
      roles: ['admin'],
    },
    acl: {
      ...FALLBACK_ACL,
      bid_card: ['admin', 'bid_manager', 'ba', 'sa', 'qc', 'domain_expert', 'solution_lead'],
      triage: ['admin', 'bid_manager', 'qc'],
      scoping: ['admin', 'bid_manager', 'ba', 'sa', 'qc'],
      ba_draft: ['admin', 'bid_manager', 'ba', 'qc'],
      sa_draft: ['admin', 'bid_manager', 'sa', 'qc', 'solution_lead'],
      domain_notes: ['admin', 'bid_manager', 'domain_expert', 'qc'],
      convergence: ['admin', 'bid_manager', 'qc', 'solution_lead'],
      hld: ['admin', 'bid_manager', 'sa', 'qc', 'solution_lead'],
      wbs: ['admin', 'bid_manager', 'ba', 'sa', 'qc'],
      pricing: ['admin', 'bid_manager', 'qc'],
      proposal_package: ['admin', 'bid_manager', 'qc'],
      reviews: ['admin', 'bid_manager', 'qc', 'sa', 'domain_expert', 'solution_lead'],
      submission: ['admin', 'bid_manager', 'qc'],
      retrospective: ['admin', 'bid_manager', 'qc', 'ba', 'sa', 'domain_expert', 'solution_lead'],
    },
    hydrated: true,
  });
});
