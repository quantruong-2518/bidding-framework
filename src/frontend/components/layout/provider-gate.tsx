'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/lib/auth/store';
import { Skeleton } from '@/components/ui/skeleton';

interface ProviderGateProps {
  children: React.ReactNode;
}

/**
 * Redirects unauthenticated users to /login. Waits for the zustand persist
 * hydration to finish before making the decision — otherwise a brief
 * server/client mismatch would bounce authed users away.
 */
export function ProviderGate({ children }: ProviderGateProps): React.ReactElement {
  const router = useRouter();
  const hydrated = useAuthStore((s) => s.hydrated);
  const token = useAuthStore((s) => s.accessToken);

  React.useEffect(() => {
    if (hydrated && !token) {
      router.replace('/login');
    }
  }, [hydrated, token, router]);

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
