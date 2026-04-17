'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { KeyRound, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useAuthStore } from '@/lib/auth/store';
import { decodeJwt } from '@/lib/auth/keycloak-url';
import type { AuthUser } from '@/lib/api/types';

export const dynamic = 'force-dynamic';

// temporary — replaced when Keycloak realm lands.
const DEMO_USER: AuthUser = {
  sub: 'demo',
  username: 'demo',
  roles: ['bid_manager'],
};

export default function LoginPage(): React.ReactElement {
  const router = useRouter();
  const setAuth = useAuthStore((s) => s.setAuth);
  const hydrated = useAuthStore((s) => s.hydrated);
  const token = useAuthStore((s) => s.accessToken);
  const [pasted, setPasted] = React.useState('');
  const [reviewer, setReviewer] = React.useState('demo');
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (hydrated && token) {
      router.replace('/dashboard');
    }
  }, [hydrated, token, router]);

  const signInWithToken = (): void => {
    setError(null);
    const trimmed = pasted.trim();
    if (!trimmed) {
      setError('Paste a JWT first.');
      return;
    }
    const payload = decodeJwt<{
      sub?: string;
      preferred_username?: string;
      email?: string;
      realm_access?: { roles?: string[] };
    }>(trimmed);
    if (!payload?.sub) {
      setError('Could not decode JWT — check the value.');
      return;
    }
    const user: AuthUser = {
      sub: payload.sub,
      username: payload.preferred_username ?? reviewer,
      email: payload.email,
      roles: payload.realm_access?.roles ?? ['bid_manager'],
    };
    setAuth(trimmed, user);
    router.push('/dashboard');
  };

  const signInDemo = (): void => {
    // temporary — replaced when Keycloak realm lands.
    setAuth('demo-token', { ...DEMO_USER, username: reviewer || 'demo' });
    router.push('/dashboard');
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/20 p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Sign in</CardTitle>
          <CardDescription>
            Phase 1 PoC: paste a Keycloak JWT or use demo mode. Full OIDC lands
            in a later wave.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label htmlFor="reviewer">Display name</Label>
            <Input
              id="reviewer"
              value={reviewer}
              onChange={(e) => setReviewer(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="token">Bearer token</Label>
            <Textarea
              id="token"
              rows={4}
              placeholder="eyJhbGciOi…"
              value={pasted}
              onChange={(e) => setPasted(e.target.value)}
              className="font-mono text-xs"
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex flex-col gap-2">
            <Button onClick={signInWithToken}>
              <KeyRound className="h-4 w-4" />
              Sign in with token
            </Button>
            <Button variant="secondary" onClick={signInDemo}>
              <Sparkles className="h-4 w-4" />
              Demo mode
            </Button>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
