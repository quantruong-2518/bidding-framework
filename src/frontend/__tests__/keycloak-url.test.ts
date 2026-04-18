import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  buildAuthUrl,
  buildLogoutUrl,
  consumePkceState,
  keycloakConfig,
  PKCE_RETURN_TO_STORAGE_KEY,
  PKCE_STATE_STORAGE_KEY,
  PKCE_VERIFIER_STORAGE_KEY,
} from '@/lib/auth/keycloak-url';

describe('keycloakConfig', () => {
  it('returns the expected defaults when env vars are unset', () => {
    const prev = {
      url: process.env.NEXT_PUBLIC_KEYCLOAK_URL,
      realm: process.env.NEXT_PUBLIC_KEYCLOAK_REALM,
      clientId: process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID,
    };
    delete process.env.NEXT_PUBLIC_KEYCLOAK_URL;
    delete process.env.NEXT_PUBLIC_KEYCLOAK_REALM;
    delete process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID;
    try {
      expect(keycloakConfig()).toEqual({
        url: 'http://localhost:8080',
        realm: 'bidding',
        clientId: 'bidding-frontend',
      });
    } finally {
      if (prev.url !== undefined) process.env.NEXT_PUBLIC_KEYCLOAK_URL = prev.url;
      if (prev.realm !== undefined) process.env.NEXT_PUBLIC_KEYCLOAK_REALM = prev.realm;
      if (prev.clientId !== undefined)
        process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID = prev.clientId;
    }
  });
});

describe('buildAuthUrl', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it('persists the verifier + state and emits the S256 challenge', async () => {
    const url = await buildAuthUrl('http://localhost:3001/auth/callback', {
      returnTo: '/bids/42',
    });

    const parsed = new URL(url);
    expect(parsed.pathname).toMatch(/\/realms\/bidding\/protocol\/openid-connect\/auth$/);
    expect(parsed.searchParams.get('response_type')).toBe('code');
    expect(parsed.searchParams.get('client_id')).toBe('bidding-frontend');
    expect(parsed.searchParams.get('redirect_uri')).toBe(
      'http://localhost:3001/auth/callback',
    );
    expect(parsed.searchParams.get('code_challenge_method')).toBe('S256');
    expect(parsed.searchParams.get('code_challenge')).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(parsed.searchParams.get('state')).toMatch(/^[A-Za-z0-9_-]+$/);

    const stashedState = window.sessionStorage.getItem(PKCE_STATE_STORAGE_KEY);
    expect(stashedState).toBe(parsed.searchParams.get('state'));
    expect(window.sessionStorage.getItem(PKCE_VERIFIER_STORAGE_KEY)).toMatch(
      /^[A-Za-z0-9_-]+$/,
    );
    expect(window.sessionStorage.getItem(PKCE_RETURN_TO_STORAGE_KEY)).toBe('/bids/42');
  });

  it('clears a stale returnTo when omitted', async () => {
    window.sessionStorage.setItem(PKCE_RETURN_TO_STORAGE_KEY, '/stale');
    await buildAuthUrl('http://localhost:3001/auth/callback');
    expect(window.sessionStorage.getItem(PKCE_RETURN_TO_STORAGE_KEY)).toBeNull();
  });
});

describe('consumePkceState', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it('returns the stashed verifier + returnTo when state matches', () => {
    window.sessionStorage.setItem(PKCE_STATE_STORAGE_KEY, 'abc');
    window.sessionStorage.setItem(PKCE_VERIFIER_STORAGE_KEY, 'verifier-123');
    window.sessionStorage.setItem(PKCE_RETURN_TO_STORAGE_KEY, '/bids/42');

    const result = consumePkceState('abc');

    expect(result).toEqual({ verifier: 'verifier-123', returnTo: '/bids/42' });
    // One-shot use — storage is wiped.
    expect(window.sessionStorage.getItem(PKCE_STATE_STORAGE_KEY)).toBeNull();
    expect(window.sessionStorage.getItem(PKCE_VERIFIER_STORAGE_KEY)).toBeNull();
  });

  it('throws when the state query param does not match stored state', () => {
    window.sessionStorage.setItem(PKCE_STATE_STORAGE_KEY, 'abc');
    window.sessionStorage.setItem(PKCE_VERIFIER_STORAGE_KEY, 'verifier-123');
    expect(() => consumePkceState('WRONG')).toThrow(/PKCE state mismatch/);
    // Even on mismatch we wipe storage — re-starting is the only path forward.
    expect(window.sessionStorage.getItem(PKCE_STATE_STORAGE_KEY)).toBeNull();
  });

  it('throws when sessionStorage is empty (no flow in progress)', () => {
    expect(() => consumePkceState('abc')).toThrow(/PKCE session not initialised/);
  });
});

describe('buildLogoutUrl', () => {
  it('targets the realm end-session endpoint with post_logout_redirect_uri', () => {
    const url = buildLogoutUrl('http://localhost:3001/login');
    expect(url).toMatch(/\/protocol\/openid-connect\/logout\?/);
    expect(url).toContain('post_logout_redirect_uri=http%3A%2F%2Flocalhost%3A3001%2Flogin');
    expect(url).toContain('client_id=bidding-frontend');
  });
});
