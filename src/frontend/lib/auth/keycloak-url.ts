/**
 * Keycloak OIDC PKCE helpers. Phase 3.2a upgrades this from a Phase 1 stub to
 * a real authorization-code + PKCE flow against the `bidding` realm.
 *
 * - `keycloakConfig()` — reads `NEXT_PUBLIC_KEYCLOAK_*` envs.
 * - `buildAuthUrl(redirectUri)` — generates a code verifier, persists it in
 *   `sessionStorage`, and returns the `/auth` redirect URL.
 * - `consumePkceState(state)` — callback-side helper: verifies the `state`
 *   returned by Keycloak matches what we stored, then pulls the verifier
 *   back out (+ clears storage).
 *
 * `decodeJwt` is kept for backwards-compat with the `?devToken=` CI path.
 */

import {
  computeCodeChallenge,
  generateCodeVerifier,
  generateState,
} from './pkce';

export interface KeycloakConfig {
  url: string;
  realm: string;
  clientId: string;
}

export const PKCE_VERIFIER_STORAGE_KEY = 'pkce.code_verifier';
export const PKCE_STATE_STORAGE_KEY = 'pkce.state';
export const PKCE_RETURN_TO_STORAGE_KEY = 'pkce.return_to';

export function keycloakConfig(): KeycloakConfig {
  return {
    url: process.env.NEXT_PUBLIC_KEYCLOAK_URL ?? 'http://localhost:8080',
    realm: process.env.NEXT_PUBLIC_KEYCLOAK_REALM ?? 'bidding',
    clientId:
      process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID ?? 'bidding-frontend',
  };
}

/**
 * Build the /auth URL + persist the PKCE verifier / state. Call from the
 * login page click handler, then `window.location.assign(url)`.
 */
export async function buildAuthUrl(
  redirectUri: string,
  options?: { returnTo?: string },
): Promise<string> {
  if (typeof window === 'undefined') {
    throw new Error('buildAuthUrl must run in the browser (needs sessionStorage).');
  }
  const { url, realm, clientId } = keycloakConfig();
  const verifier = generateCodeVerifier();
  const challenge = await computeCodeChallenge(verifier);
  const state = generateState();

  window.sessionStorage.setItem(PKCE_VERIFIER_STORAGE_KEY, verifier);
  window.sessionStorage.setItem(PKCE_STATE_STORAGE_KEY, state);
  if (options?.returnTo) {
    window.sessionStorage.setItem(PKCE_RETURN_TO_STORAGE_KEY, options.returnTo);
  } else {
    window.sessionStorage.removeItem(PKCE_RETURN_TO_STORAGE_KEY);
  }

  const params = new URLSearchParams({
    client_id: clientId,
    response_type: 'code',
    scope: 'openid profile email',
    redirect_uri: redirectUri,
    state,
    code_challenge: challenge,
    code_challenge_method: 'S256',
  });
  return `${url}/realms/${realm}/protocol/openid-connect/auth?${params.toString()}`;
}

export interface ConsumedPkceState {
  verifier: string;
  returnTo: string | null;
}

/**
 * Callback-side — returns the stored verifier after validating the `state`
 * query param matches what we stored before the redirect. Throws if the
 * state is missing or does not match (CSRF guard).
 */
export function consumePkceState(stateFromUrl: string | null): ConsumedPkceState {
  if (typeof window === 'undefined') {
    throw new Error('consumePkceState must run in the browser.');
  }
  const expectedState = window.sessionStorage.getItem(PKCE_STATE_STORAGE_KEY);
  const verifier = window.sessionStorage.getItem(PKCE_VERIFIER_STORAGE_KEY);
  const returnTo = window.sessionStorage.getItem(PKCE_RETURN_TO_STORAGE_KEY);

  // Clear regardless of outcome — one-shot use.
  window.sessionStorage.removeItem(PKCE_STATE_STORAGE_KEY);
  window.sessionStorage.removeItem(PKCE_VERIFIER_STORAGE_KEY);
  window.sessionStorage.removeItem(PKCE_RETURN_TO_STORAGE_KEY);

  if (!expectedState || !verifier) {
    throw new Error('PKCE session not initialised — re-start sign-in.');
  }
  if (!stateFromUrl || stateFromUrl !== expectedState) {
    throw new Error('PKCE state mismatch — possible CSRF, aborting.');
  }
  return { verifier, returnTo };
}

/**
 * Build the Keycloak end-session URL. Frontend redirects here on logout to
 * clear the SSO session before returning to /login.
 */
export function buildLogoutUrl(postLogoutRedirectUri: string): string {
  const { url, realm, clientId } = keycloakConfig();
  const params = new URLSearchParams({
    client_id: clientId,
    post_logout_redirect_uri: postLogoutRedirectUri,
  });
  return `${url}/realms/${realm}/protocol/openid-connect/logout?${params.toString()}`;
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
