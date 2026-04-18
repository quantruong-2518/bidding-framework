'use client';

import * as React from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { KeyRound, Loader2, TerminalSquare } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { useAuthStore } from '@/lib/auth/store';
import { buildAuthUrl, decodeJwt } from '@/lib/auth/keycloak-url';
import type { AuthUser } from '@/lib/api/types';

export const dynamic = 'force-dynamic';

/**
 * Next 14 requires `useSearchParams()` callers to be wrapped in Suspense;
 * the outer export keeps `next build` happy, the inner component does the
 * actual work.
 */
export default function LoginPage(): React.ReactElement {
  return (
    <React.Suspense fallback={<LoginFallback />}>
      <LoginInner />
    </React.Suspense>
  );
}

function LoginFallback(): React.ReactElement {
  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/20 p-6">
      <Loader2 className="h-4 w-4 animate-spin" />
    </main>
  );
}

/**
 * Phase 3.2a — Keycloak-first login.
 *
 * Primary path: "Sign in with Keycloak" → PKCE flow to `/auth/callback`.
 * Kept for automation: `?devToken=<JWT>` query (decoded + stored verbatim,
 * no signature validation). The UI never exposes the dev path to a real
 * user — it only fires when the query param is present.
 */
function LoginInner(): React.ReactElement {
  const router = useRouter();
  const searchParams = useSearchParams();
  const setAuth = useAuthStore((s) => s.setAuth);
  const hydrated = useAuthStore((s) => s.hydrated);
  const token = useAuthStore((s) => s.accessToken);
  const [redirecting, setRedirecting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Already signed in → straight to dashboard.
  React.useEffect(() => {
    if (hydrated && token) {
      router.replace('/dashboard');
    }
  }, [hydrated, token, router]);

  // CI bypass: /login?devToken=<JWT> stores the token without a real flow.
  React.useEffect(() => {
    if (!hydrated) return;
    const devToken = searchParams?.get('devToken');
    if (!devToken) return;
    const payload = decodeJwt<{
      sub?: string;
      preferred_username?: string;
      email?: string;
      realm_access?: { roles?: string[] };
    }>(devToken);
    if (!payload?.sub) {
      setError('Invalid ?devToken payload — must be a decodable JWT.');
      return;
    }
    const user: AuthUser = {
      sub: payload.sub,
      username: payload.preferred_username ?? payload.sub,
      email: payload.email,
      roles: payload.realm_access?.roles ?? [],
    };
    setAuth(devToken, user);
    router.replace('/dashboard');
  }, [hydrated, searchParams, setAuth, router]);

  const onSignIn = async (): Promise<void> => {
    setError(null);
    setRedirecting(true);
    try {
      const redirectUri = `${window.location.origin}/auth/callback`;
      const returnTo = searchParams?.get('returnTo') ?? undefined;
      const url = await buildAuthUrl(redirectUri, { returnTo });
      window.location.assign(url);
    } catch (exc) {
      setRedirecting(false);
      setError(exc instanceof Error ? exc.message : String(exc));
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/20 p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Sign in</CardTitle>
          <CardDescription>
            Authenticate with your organisation Keycloak account to access the
            bidding dashboard.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button
            onClick={() => void onSignIn()}
            disabled={redirecting}
            className="w-full"
          >
            {redirecting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <KeyRound className="h-4 w-4" />
            )}
            Sign in with Keycloak
          </Button>
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <TerminalSquare className="h-3 w-3" />
            CI bypass: append <span className="font-mono">?devToken=&lt;jwt&gt;</span>
            {' '}to this URL.
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
