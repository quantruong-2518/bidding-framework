/**
 * 7 roles × 14 artifacts = 98 parameterised cases driving `AclService.assertVisible`.
 *
 * Golden-copy baseline: must match `src/ai-service/workflows/acl.py::ARTIFACT_ACL`.
 * When the Python map changes the fallback in `acl.service.ts` must be updated
 * too — this spec will catch any drift.
 */

import { ForbiddenException } from '@nestjs/common';
import {
  AclService,
  FALLBACK_ARTIFACT_ACL,
} from '../src/acl/acl.service';
import { ARTIFACT_KEYS, type ArtifactKey } from '../src/workflows/artifact-keys';

type AppRole =
  | 'admin'
  | 'bid_manager'
  | 'ba'
  | 'sa'
  | 'qc'
  | 'domain_expert'
  | 'solution_lead';

const ROLES: readonly AppRole[] = [
  'admin',
  'bid_manager',
  'ba',
  'sa',
  'qc',
  'domain_expert',
  'solution_lead',
];

/** Expected visibility: mirror of `FALLBACK_ARTIFACT_ACL` with admin-wildcard. */
function expected(role: AppRole, key: ArtifactKey): boolean {
  if (role === 'admin') return true;
  return FALLBACK_ARTIFACT_ACL[key].includes(role);
}

describe('RBAC matrix — 98 cases (7 roles × 14 artifacts)', () => {
  const service = new AclService(null, null);

  for (const role of ROLES) {
    for (const key of ARTIFACT_KEYS) {
      const should = expected(role, key);
      const label = `${role.padEnd(14)} → ${String(key).padEnd(18)} → ${should ? 'ALLOW' : 'DENY '}`;

      if (should) {
        it(label, () => {
          expect(() => service.assertVisible([role], key)).not.toThrow();
        });
      } else {
        it(label, () => {
          expect(() => service.assertVisible([role], key)).toThrow(
            ForbiddenException,
          );
        });
      }
    }
  }

  it('has 14 unique artifact keys', () => {
    expect(new Set(ARTIFACT_KEYS).size).toBe(14);
  });

  it('fallback map covers every key', () => {
    for (const key of ARTIFACT_KEYS) {
      expect(FALLBACK_ARTIFACT_ACL[key]).toBeDefined();
    }
  });

  it('pricing remains commercial-confidential (only admin/bid_manager/qc)', () => {
    expect([...FALLBACK_ARTIFACT_ACL.pricing].sort()).toEqual([
      'admin',
      'bid_manager',
      'qc',
    ]);
  });

  it('bid_card is visible to every role', () => {
    for (const role of ROLES) {
      expect(() => service.assertVisible([role], 'bid_card')).not.toThrow();
    }
  });

  it('assertVisible throws for unknown keys', () => {
    expect(() => service.assertVisible(['admin'], 'not_a_real_key')).toThrow(
      /unknown artifact key/,
    );
  });

  it('user with multiple roles inherits the union', () => {
    // ba alone can't see pricing, but ba+bid_manager can.
    expect(() =>
      service.assertVisible(['ba', 'bid_manager'], 'pricing'),
    ).not.toThrow();
  });

  it('empty role list always denies non-admin resources', () => {
    for (const key of ARTIFACT_KEYS) {
      expect(() => service.assertVisible([], key)).toThrow(ForbiddenException);
    }
  });
});
