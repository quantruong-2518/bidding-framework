'use client';

import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getSocket } from './socket';
import { useAuthStore } from '@/lib/auth/store';
import { bidKeys } from '@/lib/hooks/query-keys';

export interface BidEventState {
  connected: boolean;
  lastEventAt: number | null;
}

/**
 * Subscribe to `bid.event` for a given bidId, auto-invalidating the
 * workflow-status query on any update so React Query refetches.
 */
export function useBidEvents(bidId: string | null | undefined): BidEventState {
  const queryClient = useQueryClient();
  const token = useAuthStore((s) => s.accessToken);
  const [connected, setConnected] = useState(false);
  const [lastEventAt, setLastEventAt] = useState<number | null>(null);

  useEffect(() => {
    if (!bidId || !token) {
      setConnected(false);
      return;
    }

    const socket = getSocket(token);
    if (!socket) return;

    const subscribe = (): void => {
      socket.emit('subscribe', bidId);
    };
    const onConnect = (): void => {
      setConnected(true);
      subscribe();
    };
    const onDisconnect = (): void => setConnected(false);
    const onEvent = (): void => {
      setLastEventAt(Date.now());
      void queryClient.invalidateQueries({ queryKey: bidKeys.workflow(bidId) });
      void queryClient.invalidateQueries({ queryKey: bidKeys.detail(bidId) });
    };

    socket.on('connect', onConnect);
    socket.on('disconnect', onDisconnect);
    socket.on('bid.event', onEvent);
    socket.on('bid.broadcast', onEvent);

    if (socket.connected) {
      setConnected(true);
      subscribe();
    }

    return () => {
      socket.emit('unsubscribe', bidId);
      socket.off('connect', onConnect);
      socket.off('disconnect', onDisconnect);
      socket.off('bid.event', onEvent);
      socket.off('bid.broadcast', onEvent);
    };
  }, [bidId, token, queryClient]);

  return { connected, lastEventAt };
}
