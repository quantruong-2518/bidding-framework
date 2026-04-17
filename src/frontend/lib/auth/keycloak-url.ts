/**
 * Keycloak OIDC helpers. For the Phase 1 PoC we use a "paste a token"
 * fallback (see login page). The full PKCE dance is sketched here but wired
 * only partially — TODO: replace with keycloak-js once the realm is
 * provisioned in a later wave.
 */

export interface KeycloakConfig {
  url: string;
  realm: string;
  clientId: string;
}

export function keycloakConfig(): KeycloakConfig {
  return {
    url: process.env.NEXT_PUBLIC_KEYCLOAK_URL ?? 'http://localhost:8080',
    realm: process.env.NEXT_PUBLIC_KEYCLOAK_REALM ?? 'bidding',
    clientId: process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID ?? 'bidding-web',
  };
}

/**
 * Build the OIDC authorization URL. Kept as a helper so the login page
 * can render a "Sign in with Keycloak" link when the realm is ready.
 *
 * TODO: pair with a PKCE verifier stored in sessionStorage + callback
 * route that exchanges `code` → token. Not required for PoC.
 */
export function buildAuthorizeUrl(redirectUri: string, state: string): string {
  const { url, realm, clientId } = keycloakConfig();
  const params = new URLSearchParams({
    client_id: clientId,
    response_type: 'code',
    scope: 'openid profile email',
    redirect_uri: redirectUri,
    state,
  });
  return `${url}/realms/${realm}/protocol/openid-connect/auth?${params.toString()}`;
}

/** Decode a JWT payload without verifying the signature (client-side hint). */
export function decodeJwt<T = Record<string, unknown>>(token: string): T | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const pad = payload.length % 4 === 0 ? '' : '='.repeat(4 - (payload.length % 4));
    const json =
      typeof window === 'undefined'
        ? Buffer.from(payload + pad, 'base64').toString('utf8')
        : atob(payload + pad);
    return JSON.parse(json) as T;
  } catch {
    return null;
  }
}
