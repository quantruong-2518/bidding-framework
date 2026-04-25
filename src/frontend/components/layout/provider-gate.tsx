'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/lib/auth/store';
import { useSilentTokenRefresh } from '@/lib/auth/use-silent-refresh';
import { fetchAcl } from '@/lib/api/acl';
import { Skeleton } from '@/components/ui/skeleton';

interface ProviderGateProps {
  children: React.ReactNode;
}

/**
 * Redirects unauthenticated users to /login. Waits for the zustand persist
 * hydration to finish before making the decision — otherwise a brief
 * server/client mismatch would bounce authed users away.
 *
 * Also fetches the ACL map once per authed session. A fetch failure is
 * logged + swallowed; the store falls back to the admin-only conservative
 * map, which quietly hides panels for non-admin users until the next retry.
 */
export function ProviderGate({ children }: ProviderGateProps): React.ReactElement {
  const router = useRouter();
  const hydrated = useAuthStore((s) => s.hydrated);
  const token = useAuthStore((s) => s.accessToken);
  const acl = useAuthStore((s) => s.acl);
  const setAcl = useAuthStore((s) => s.setAcl);

  // Schedules a silent refresh 60 s before access-token expiry. No-ops
  // when refreshToken/expiresAt are unset (e.g. before login).
  useSilentTokenRefresh();

  React.useEffect(() => {
    if (hydrated && !token) {
      router.replace('/login');
    }
  }, [hydrated, token, router]);

  React.useEffect(() => {
    if (!token || acl) return;
    let cancelled = false;
    fetchAcl()
      .then((map) => {
        if (!cancelled) setAcl(map);
      })
      .catch((err: unknown) => {
        // eslint-disable-next-line no-console
        console.warn('ACL fetch failed — using fallback', err);
      });
    return () => {
      cancelled = true;
    };
  }, [token, acl, setAcl]);

  if (!hydrated) {
    return (
      <div className="p-8">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="mt-4 h-32 w-full" />
      </div>
    );
  }
  if (!token) return <div className="p-8 text-sm text-muted-foreground">Redirecting…</div>;
  return <>{children}</>;
}
