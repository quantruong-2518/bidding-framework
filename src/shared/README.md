# shared/

Tiny pile of cross-language contract files. Anything in here is read by
both Python (ai-service) and TypeScript (api-gateway, frontend) — keep
the format simple (JSON / strict YAML).

## `acl-map.json`

Canonical artifact-key → allowed-role mapping (Phase 3.2b).
Single source of truth: `ai-service/workflows/acl.py::ARTIFACT_ACL`.

The drift guards check both sides match this file:
- Python: `ai-service/tests/test_acl.py::test_canonical_json_matches_source`.
- TypeScript: `api-gateway/test/acl-canonical.spec.ts`.

When the policy changes:
1. Update `ai-service/workflows/acl.py::ARTIFACT_ACL`.
2. Re-export the JSON: `python3 -c "from workflows.acl import acl_as_json; import json; print(json.dumps(acl_as_json(), indent=2, sort_keys=True))" > src/shared/acl-map.json`.
3. Update `api-gateway/src/acl/acl.service.ts::FALLBACK_ARTIFACT_ACL` to match.
4. Both drift specs pass green again.

If only one side is updated, both sides' drift tests fail — the canonical
JSON acts as the choke-point that forces a reviewer to look at all three.
