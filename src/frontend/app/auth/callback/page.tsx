'use client';

import * as React from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Loader2 } from 'lucide-react';
import { consumePkceState } from '@/lib/auth/keycloak-url';
import { exchangeCodeForToken } from '@/lib/auth/token-exchange';
import { useAuthStore } from '@/lib/auth/store';

export const dynamic = 'force-dynamic';

type CallbackStatus = 'pending' | 'error';

/**
 * Phase 3.2a — OIDC authorization-code callback.
 *
 * Reads `?code` + `?state` from the URL, pulls the stashed PKCE verifier
 * back out of sessionStorage, and swaps the code for an access token. On
 * success stores the token pair in {@link useAuthStore} and redirects to
 * the `returnTo` path (or `/dashboard` by default).
 */
export default function AuthCallbackPage(): React.ReactElement {
  const router = useRouter();
  const searchParams = useSearchParams();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [status, setStatus] = React.useState<CallbackStatus>('pending');
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    const code = searchParams?.get('code') ?? null;
    const state = searchParams?.get('state') ?? null;
    const oauthError = searchParams?.get('error');

    if (oauthError) {
      setStatus('error');
      setError(`${oauthError}: ${searchParams?.get('error_description') ?? ''}`);
      return;
    }
    if (!code) {
      setStatus('error');
      setError('Missing `code` query param — start sign-in from /login.');
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const { verifier, returnTo } = consumePkceState(state);
        const redirectUri = `${window.location.origin}/auth/callback`;
        const result = await exchangeCodeForToken({
          code,
          verifier,
          redirectUri,
        });
        if (cancelled) return;
        setAuth(result.accessToken, result.user, {
          refreshToken: result.refreshToken,
          expiresAt: result.expiresAt,
        });
        router.replace(returnTo && returnTo.startsWith('/') ? returnTo : '/dashboard');
      } catch (exc) {
        if (cancelled) return;
        setStatus('error');
        setError(exc instanceof Error ? exc.message : String(exc));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router, searchParams, setAuth]);

  if (status === 'pending') {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Finishing sign-in…
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <div className="max-w-md space-y-3">
        <h1 className="text-lg font-semibold">Sign-in failed</h1>
        <p className="text-sm text-destructive">{error}</p>
        <Link className="text-sm text-primary hover:underline" href="/login">
          ← Back to /login
        </Link>
      </div>
    </main>
  );
}
