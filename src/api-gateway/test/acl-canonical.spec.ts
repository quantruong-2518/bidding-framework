import * as fs from 'fs';
import * as path from 'path';
import { FALLBACK_ARTIFACT_ACL } from '../src/acl/acl.service';
import { ARTIFACT_KEYS } from '../src/workflows/artifact-keys';

/**
 * Drift guard for the artifact ACL.
 *
 * `src/shared/acl-map.json` is the canonical contract written by Python
 * (`workflows/acl.py::acl_as_json`). The api-gateway carries a hardcoded
 * `FALLBACK_ARTIFACT_ACL` for the case where ai-service is unreachable
 * during boot. Any drift between the two would silently weaken or
 * tighten access — this spec fails the build until they're realigned.
 *
 * Update procedure when policy changes: see `src/shared/README.md`.
 */
describe('FALLBACK_ARTIFACT_ACL drift guard', () => {
  const canonicalPath = path.resolve(
    __dirname,
    '..',
    '..',
    'shared',
    'acl-map.json',
  );

  it('canonical JSON file exists', () => {
    expect(fs.existsSync(canonicalPath)).toBe(true);
  });

  it('matches the Python-exported canonical map', () => {
    const canonical = JSON.parse(fs.readFileSync(canonicalPath, 'utf8')) as Record<
      string,
      string[]
    >;
    // Normalise FALLBACK to plain arrays for deep-equal.
    const normalised: Record<string, string[]> = {};
    for (const [k, v] of Object.entries(FALLBACK_ARTIFACT_ACL)) {
      normalised[k] = [...v].sort();
    }
    expect(normalised).toEqual(canonical);
  });

  it('canonical JSON covers every ArtifactKey', () => {
    const canonical = JSON.parse(fs.readFileSync(canonicalPath, 'utf8'));
    for (const key of ARTIFACT_KEYS) {
      expect(canonical[key]).toBeDefined();
    }
  });
});
