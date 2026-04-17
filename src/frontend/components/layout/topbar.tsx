'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { LogOut, Wifi, WifiOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuthStore } from '@/lib/auth/store';
import { closeSocket } from '@/lib/ws/socket';
import { cn } from '@/lib/utils/cn';

interface TopbarProps {
  connected?: boolean;
}

export function Topbar({ connected }: TopbarProps): React.ReactElement {
  const user = useAuthStore((s) => s.user);
  const clearAuth = useAuthStore((s) => s.clearAuth);
  const router = useRouter();

  const onLogout = (): void => {
    closeSocket();
    clearAuth();
    router.push('/login');
  };

  return (
    <header className="sticky top-0 z-10 flex h-14 items-center justify-between border-b border-border bg-card px-4">
      <div className="flex items-center gap-2">
        <span
          title={connected ? 'Realtime connected' : 'Realtime disconnected'}
          className={cn(
            'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs',
            connected
              ? 'bg-success/10 text-success'
              : 'bg-muted text-muted-foreground',
          )}
        >
          {connected ? (
            <Wifi className="h-3 w-3" />
          ) : (
            <WifiOff className="h-3 w-3" />
          )}
          {connected ? 'Live' : 'Offline'}
        </span>
      </div>
      <div className="flex items-center gap-3">
        {user && (
          <div className="text-right text-xs">
            <div className="font-medium text-foreground">{user.username}</div>
            <div className="text-muted-foreground">{user.roles.join(', ') || '—'}</div>
          </div>
        )}
        <Button variant="outline" size="sm" onClick={onLogout}>
          <LogOut className="h-4 w-4" />
          Logout
        </Button>
      </div>
    </header>
  );
}
