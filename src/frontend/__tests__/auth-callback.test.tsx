import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import AuthCallbackPage from '@/app/auth/callback/page';
import { useAuthStore } from '@/lib/auth/store';
import {
  PKCE_RETURN_TO_STORAGE_KEY,
  PKCE_STATE_STORAGE_KEY,
  PKCE_VERIFIER_STORAGE_KEY,
} from '@/lib/auth/keycloak-url';

const routerReplace = vi.fn();
const searchParamsStore: { get: (k: string) => string | null } = {
  get: () => null,
};

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: routerReplace, push: vi.fn() }),
  useSearchParams: () => ({ get: (k: string) => searchParamsStore.get(k) }),
}));

const exchangeMock = vi.fn();
vi.mock('@/lib/auth/token-exchange', () => ({
  exchangeCodeForToken: (...args: unknown[]) => exchangeMock(...args),
}));

function primeSession(state: string, verifier: string, returnTo?: string): void {
  window.sessionStorage.setItem(PKCE_STATE_STORAGE_KEY, state);
  window.sessionStorage.setItem(PKCE_VERIFIER_STORAGE_KEY, verifier);
  if (returnTo) {
    window.sessionStorage.setItem(PKCE_RETURN_TO_STORAGE_KEY, returnTo);
  }
}

function setSearch(params: Record<string, string | null>): void {
  searchParamsStore.get = (k) => (k in params ? params[k] : null);
}

describe('AuthCallbackPage', () => {
  beforeEach(() => {
    routerReplace.mockReset();
    exchangeMock.mockReset();
    window.sessionStorage.clear();
    useAuthStore.getState().clearAuth();
    useAuthStore.setState({ hydrated: true });
    searchParamsStore.get = () => null;
  });

  it('exchanges the code, persists the token pair, and redirects to /dashboard', async () => {
    primeSession('state-ok', 'verifier-xyz');
    setSearch({ code: 'auth-code', state: 'state-ok' });
    exchangeMock.mockResolvedValueOnce({
      accessToken: 'at-123',
      refreshToken: 'rt-456',
      expiresAt: Date.now() + 900_000,
      user: { sub: 'u-1', username: 'alice', email: 'a@b.c', roles: ['bid_manager'] },
    });

    render(<AuthCallbackPage />);

    await waitFor(() => {
      expect(routerReplace).toHaveBeenCalledWith('/dashboard');
    });
    expect(exchangeMock).toHaveBeenCalledWith({
      code: 'auth-code',
      verifier: 'verifier-xyz',
      redirectUri: expect.stringMatching(/\/auth\/callback$/),
    });
    const stored = useAuthStore.getState();
    expect(stored.accessToken).toBe('at-123');
    expect(stored.refreshToken).toBe('rt-456');
    expect(stored.user?.username).toBe('alice');
    expect(window.sessionStorage.getItem(PKCE_STATE_STORAGE_KEY)).toBeNull();
  });

  it('honours the stashed returnTo when it is a same-origin path', async () => {
    primeSession('state-ok', 'verifier-xyz', '/bids/abc');
    setSearch({ code: 'auth-code', state: 'state-ok' });
    exchangeMock.mockResolvedValueOnce({
      accessToken: 'at',
      refreshToken: 'rt',
      expiresAt: Date.now() + 900_000,
      user: { sub: 'u', username: 'u', email: 'u@u', roles: [] },
    });

    render(<AuthCallbackPage />);

    await waitFor(() => {
      expect(routerReplace).toHaveBeenCalledWith('/bids/abc');
    });
  });

  it('renders an error when state mismatches', async () => {
    primeSession('state-ok', 'verifier-xyz');
    setSearch({ code: 'auth-code', state: 'state-TAMPERED' });

    render(<AuthCallbackPage />);

    await waitFor(() => {
      expect(screen.getByText(/Sign-in failed/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/PKCE state mismatch/i)).toBeInTheDocument();
    expect(exchangeMock).not.toHaveBeenCalled();
  });

  it('renders an error when Keycloak returned an OAuth error', async () => {
    setSearch({
      error: 'access_denied',
      error_description: 'User cancelled',
    });

    render(<AuthCallbackPage />);

    await waitFor(() => {
      expect(screen.getByText(/Sign-in failed/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/access_denied/)).toBeInTheDocument();
    expect(exchangeMock).not.toHaveBeenCalled();
  });
});
