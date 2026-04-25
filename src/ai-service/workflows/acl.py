"""Artifact-level access control list — single source of truth for RBAC.

The NestJS api-gateway proxies `GET /workflows/bid/acl/artifacts` to reuse this
map, so Python owns the contract. Keep `ARTIFACT_ACL` + `AppRole` aligned with
`src/api-gateway/src/acl/acl.service.ts` (the proxy adds no local overrides).

Semantics:
- ``admin`` is a wildcard — always returns True via :func:`has_access`.
- Any other role must appear in the artifact's frozenset to gain access.
- ``visible_artifacts`` is a convenience for bulk filtering (e.g. BidState).
"""

from __future__ import annotations

from typing import Iterable, Literal, get_args

AppRole = Literal[
    "admin",
    "bid_manager",
    "ba",
    "sa",
    "qc",
    "domain_expert",
    "solution_lead",
]

ArtifactKey = Literal[
    "bid_card",
    "triage",
    "scoping",
    "ba_draft",
    "sa_draft",
    "domain_notes",
    "convergence",
    "hld",
    "wbs",
    "pricing",
    "proposal_package",
    "reviews",
    "submission",
    "retrospective",
]

ALL_ROLES: frozenset[AppRole] = frozenset(get_args(AppRole))
ALL_ARTIFACT_KEYS: tuple[ArtifactKey, ...] = get_args(ArtifactKey)

ARTIFACT_ACL: dict[ArtifactKey, frozenset[AppRole]] = {
    "bid_card": ALL_ROLES,
    "triage": frozenset({"admin", "bid_manager", "qc"}),
    "scoping": frozenset({"admin", "bid_manager", "ba", "sa", "qc"}),
    "ba_draft": frozenset({"admin", "bid_manager", "ba", "qc"}),
    "sa_draft": frozenset({"admin", "bid_manager", "sa", "qc", "solution_lead"}),
    "domain_notes": frozenset({"admin", "bid_manager", "domain_expert", "qc"}),
    "convergence": frozenset({"admin", "bid_manager", "qc", "solution_lead"}),
    "hld": frozenset({"admin", "bid_manager", "sa", "qc", "solution_lead"}),
    "wbs": frozenset({"admin", "bid_manager", "ba", "sa", "qc"}),
    # pricing is commercial-confidential: only bid_manager + qc beyond admin.
    "pricing": frozenset({"admin", "bid_manager", "qc"}),
    "proposal_package": frozenset({"admin", "bid_manager", "qc"}),
    "reviews": frozenset(
        {"admin", "bid_manager", "qc", "sa", "domain_expert", "solution_lead"}
    ),
    "submission": frozenset({"admin", "bid_manager", "qc"}),
    "retrospective": frozenset(
        {
            "admin",
            "bid_manager",
            "qc",
            "ba",
            "sa",
            "domain_expert",
            "solution_lead",
        }
    ),
}


def has_access(role_set: Iterable[str], key: str) -> bool:
    """Return True when any of the caller's roles grants access to ``key``.

    ``admin`` is a wildcard — unknown keys still return True for admin. Any
    other unknown key raises ``KeyError`` so the caller is forced to update
    :data:`ARTIFACT_ACL` when extending ``BidState``.
    """

    roles = {r for r in role_set if r}
    if "admin" in roles:
        return True
    if key not in ARTIFACT_ACL:
        raise KeyError(f"unknown artifact key: {key!r}")
    return bool(ARTIFACT_ACL[key] & roles)


def visible_artifacts(role_set: Iterable[str]) -> set[ArtifactKey]:
    """Return the set of artifact keys visible to ``role_set``."""

    roles = {r for r in role_set if r}
    if "admin" in roles:
        return set(ALL_ARTIFACT_KEYS)
    return {k for k, allowed in ARTIFACT_ACL.items() if allowed & roles}


def acl_as_json() -> dict[str, list[str]]:
    """Serialise :data:`ARTIFACT_ACL` for the HTTP endpoint / frontend fetch."""

    return {k: sorted(v) for k, v in ARTIFACT_ACL.items()}


__all__ = [
    "AppRole",
    "ArtifactKey",
    "ALL_ROLES",
    "ALL_ARTIFACT_KEYS",
    "ARTIFACT_ACL",
    "has_access",
    "visible_artifacts",
    "acl_as_json",
]
