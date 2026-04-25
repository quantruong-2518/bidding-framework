'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/lib/auth/store';
import { Skeleton } from '@/components/ui/skeleton';

interface AdminGateProps {
  children: React.ReactNode;
  /** Where to send a non-admin user. Defaults to /dashboard. */
  redirectTo?: string;
}

/**
 * Defence-in-depth admin gate for routes whose data is admin-only on the
 * server (e.g. `/dashboard/audit`). The server already 403s; this gate
 * just spares the user from staring at a red error banner before the
 * router bounces them.
 *
 * Waits for the zustand persist hydration before checking the role —
 * otherwise a fresh-tab render flickers the "denied" state for one frame
 * before the persisted token shows up.
 */
export function AdminGate({
  children,
  redirectTo = '/dashboard',
}: AdminGateProps): React.ReactElement {
  const router = useRouter();
  const hydrated = useAuthStore((s) => s.hydrated);
  const roles = useAuthStore((s) => s.user?.roles ?? []);
  const isAdmin = roles.includes('admin');

  React.useEffect(() => {
    if (hydrated && !isAdmin) {
      router.replace(redirectTo);
    }
  }, [hydrated, isAdmin, router, redirectTo]);

  if (!hydrated) {
    return (
      <div className="p-8" data-testid="admin-gate-loading">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="mt-4 h-32 w-full" />
      </div>
    );
  }
  if (!isAdmin) {
    return (
      <p
        className="p-8 text-sm text-muted-foreground"
        data-testid="admin-gate-denied"
      >
        Admin access required. Redirecting…
      </p>
    );
  }
  return <>{children}</>;
}
