'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from './store';
import { refreshAccessToken } from './token-exchange';

/**
 * How long before access-token expiry to fire the refresh. 60 s leaves
 * comfortable headroom against clock skew without burning extra exchanges
 * on a normal 15 min token.
 */
const REFRESH_LEAD_MS = 60_000;

/**
 * Schedules a silent token refresh ahead of `expiresAt`. On success the
 * fresh token pair lands in the auth store and the next scheduled
 * timeout fires before the new expiry. On failure the session is cleared
 * and the user is bounced to `/login` — better than letting TanStack
 * Query show an opaque 401 banner.
 *
 * Idempotent / cleanup-safe: the effect re-schedules whenever
 * `expiresAt` or `refreshToken` change. The cleanup clears the pending
 * timer so a logout (which clears both fields) doesn't leave a ghost
 * refresh attempt running with stale state.
 */
export function useSilentTokenRefresh(): void {
  const router = useRouter();
  const refreshToken = useAuthStore((s) => s.refreshToken);
  const expiresAt = useAuthStore((s) => s.expiresAt);
  const setAuth = useAuthStore((s) => s.setAuth);
  const clearAuth = useAuthStore((s) => s.clearAuth);

  React.useEffect(() => {
    if (!refreshToken || !expiresAt) return undefined;

    const doRefresh = async (): Promise<void> => {
      try {
        const next = await refreshAccessToken({ refreshToken });
        setAuth(next.accessToken, next.user, {
          refreshToken: next.refreshToken,
          expiresAt: next.expiresAt,
        });
      } catch {
        clearAuth();
        router.replace('/login');
      }
    };

    const delay = expiresAt - Date.now() - REFRESH_LEAD_MS;
    if (delay <= 0) {
      void doRefresh();
      return undefined;
    }
    const handle = setTimeout(() => {
      void doRefresh();
    }, delay);
    return () => clearTimeout(handle);
  }, [refreshToken, expiresAt, setAuth, clearAuth, router]);
}
