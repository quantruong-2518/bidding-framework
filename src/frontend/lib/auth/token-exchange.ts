/**
 * Phase 3.2a — exchange an authorization code for tokens + decode the
 * access token into the {@link AuthUser} shape the rest of the app expects.
 *
 * The exchange targets Keycloak's token endpoint directly (public client,
 * no secret). Decoded user info comes from the ID token / access-token
 * claims — we intentionally skip the userinfo endpoint since the access
 * token already carries `preferred_username` + realm roles.
 */

import type { AuthUser } from '@/lib/api/types';
import { decodeJwt, keycloakConfig } from './keycloak-url';

export interface TokenExchangeResult {
  accessToken: string;
  refreshToken: string;
  expiresAt: number; // epoch ms
  user: AuthUser;
}

interface KeycloakTokenResponse {
  access_token: string;
  expires_in: number;
  refresh_token?: string;
  refresh_expires_in?: number;
  token_type: string;
  id_token?: string;
  'not-before-policy'?: number;
  session_state?: string;
  scope?: string;
}

interface KeycloakAccessTokenClaims {
  sub: string;
  preferred_username?: string;
  email?: string;
  realm_access?: { roles?: string[] };
}

/**
 * POST the code + verifier to `${issuer}/protocol/openid-connect/token`
 * and parse the response into {@link TokenExchangeResult}.
 */
export async function exchangeCodeForToken(args: {
  code: string;
  verifier: string;
  redirectUri: string;
  fetchImpl?: typeof fetch;
}): Promise<TokenExchangeResult> {
  const { url, realm, clientId } = keycloakConfig();
  const fetchFn = args.fetchImpl ?? fetch;
  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: clientId,
    code: args.code,
    code_verifier: args.verifier,
    redirect_uri: args.redirectUri,
  });

  const res = await fetchFn(`${url}/realms/${realm}/protocol/openid-connect/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(
      `Keycloak token exchange failed (${res.status}): ${detail || res.statusText}`,
    );
  }

  const payload = (await res.json()) as KeycloakTokenResponse;
  return normaliseTokenResponse(payload);
}

/**
 * Refresh an expired access token using the stored refresh token. Returns
 * a new {@link TokenExchangeResult} or throws if the refresh fails (in
 * which case callers should wipe the session and redirect to /login).
 */
export async function refreshAccessToken(args: {
  refreshToken: string;
  fetchImpl?: typeof fetch;
}): Promise<TokenExchangeResult> {
  const { url, realm, clientId } = keycloakConfig();
  const fetchFn = args.fetchImpl ?? fetch;
  const body = new URLSearchParams({
    grant_type: 'refresh_token',
    client_id: clientId,
    refresh_token: args.refreshToken,
  });
  const res = await fetchFn(`${url}/realms/${realm}/protocol/openid-connect/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(
      `Keycloak refresh failed (${res.status}): ${detail || res.statusText}`,
    );
  }
  const payload = (await res.json()) as KeycloakTokenResponse;
  return normaliseTokenResponse(payload);
}

function normaliseTokenResponse(payload: KeycloakTokenResponse): TokenExchangeResult {
  const claims = decodeJwt<KeycloakAccessTokenClaims>(payload.access_token);
  if (!claims?.sub) {
    throw new Error('Access token missing `sub` claim — not a Keycloak token.');
  }
  const user: AuthUser = {
    sub: claims.sub,
    username: claims.preferred_username ?? claims.sub,
    email: claims.email,
    roles: claims.realm_access?.roles ?? [],
  };
  return {
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token ?? '',
    expiresAt: Date.now() + payload.expires_in * 1000,
    user,
  };
}
