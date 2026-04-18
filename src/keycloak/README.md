# Keycloak realm provisioning

Phase 3.2a — replaces the Phase 1 demo-mode login with a real OIDC realm.
`bidding-realm.json` is imported by Keycloak on container start via
`--import-realm`, so `docker compose up -d` is all a dev needs.

## What ships in the realm

- **Realm name:** `bidding`
- **Access token TTL:** 15 min (900 s)
- **SSO idle timeout:** 30 min (1800 s)
- **Roles:** `admin`, `bid_manager`, `ba`, `sa`, `qc`, `domain_expert`, `solution_lead`
- **Clients:**
  - `bidding-api` — bearer-only, verified by the NestJS `JwtStrategy`.
  - `bidding-frontend` — public client with PKCE (S256), redirect back to
    `http://localhost:3001/auth/callback`. Audience mapper adds `bidding-api`
    to access tokens so api-gateway accepts them.
- **Seed user:** `bidadmin / ChangeMe!` with roles `admin` + `bid_manager`.
  Password is `temporary: true` — Keycloak forces a change on first login.

## Bring it up

Default compose command is now `start-dev --import-realm`, so a fresh
volume imports on first boot:

```bash
cd src
docker compose up -d keycloak
# First boot takes ~90 s. Wait for the healthcheck to pass:
docker compose ps keycloak
# Then verify the realm exists:
curl -s http://localhost:8080/realms/bidding/.well-known/openid-configuration | jq .issuer
# → "http://localhost:8080/realms/bidding"
```

If the realm is already imported, Keycloak skips the import silently
(idempotent). If you want to re-import from scratch, drop the
`keycloak_data` volume:

```bash
docker compose down keycloak
docker volume rm bid-framework_keycloak_data
docker compose up -d keycloak
```

## First-time admin login

1. Open http://localhost:8080/admin and select realm `bidding` in the
   top-left dropdown.
2. Log in as `bidadmin / ChangeMe!` — Keycloak will immediately prompt
   for a new password (the `temporary: true` flag on the credential).
3. **Rotate the password before any shared deployment.** The default is
   fine for local dev but the realm JSON is in-repo.

## Adding more users

Admin UI → `bidding` realm → Users → Add user. Assign realm roles from
the Role mapping tab (`ba`, `sa`, `qc`, `domain_expert`, `solution_lead`,
`bid_manager`, `admin`). New users get a temporary password set on
the Credentials tab.

## Editing + re-exporting the realm

When you want to save a UI change back to `bidding-realm.json`:

```bash
# Export inside the running container
docker exec bid-keycloak /opt/keycloak/bin/kc.sh export \
  --realm bidding \
  --file /tmp/bidding-realm.json

# Copy out and normalize (pretty-print)
docker cp bid-keycloak:/tmp/bidding-realm.json ./bidding-realm.json
jq . ./bidding-realm.json > ./bidding-realm.tmp && mv ./bidding-realm.tmp ./bidding-realm.json
```

Review the diff carefully — Keycloak emits UUIDs and timestamps that
are fine to keep but clutter the review. Commit only intentional
changes (new roles, new clients, new seed users).

## Gotchas

- **`temporary: true` credentials** — first login is a forced password
  change. Automated smoke tests must bypass this (use the Admin API to
  clear the flag in a setup step, or pre-seed a second test user with
  `temporary: false`).
- **Audience mapper** — the `bidding-frontend` client includes an
  audience mapper that adds `bidding-api` to access tokens. Without this
  mapper the NestJS api-gateway returns 401 because `aud` mismatches.
  If you see `Invalid audience` in api-gateway logs, check the mapper.
- **Post-logout redirect** — `post.logout.redirect.uris` in realm JSON
  uses `##` as the separator (Keycloak 24 quirk). Edit both entries if
  you rename the frontend URL.
- **`HOSTNAME_STRICT=false`** — Keycloak 24 is flexible enough that we
  leave this unset in compose; container listens on both `localhost`
  (browser) and `keycloak` (internal Docker network). Real prod should
  use a single canonical hostname.

## See also

- `../docker-compose.yml` — Keycloak service + `--import-realm` flag + the
  `./keycloak:/opt/keycloak/data/import:ro` volume mount.
- `../api-gateway/src/auth/jwt.strategy.ts` — JWKS-backed verification
  pointing at `${KEYCLOAK_ISSUER}/protocol/openid-connect/certs`.
- `../frontend/lib/auth/` — PKCE URL builder + token exchange + silent
  refresh used by the Next.js login page.
