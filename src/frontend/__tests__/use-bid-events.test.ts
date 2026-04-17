import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import * as React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useBidEvents } from '@/lib/ws/use-bid-events';
import { useAuthStore } from '@/lib/auth/store';

interface MockSocket {
  connected: boolean;
  emit: ReturnType<typeof vi.fn>;
  on: ReturnType<typeof vi.fn>;
  off: ReturnType<typeof vi.fn>;
}

const mockSocket: MockSocket = {
  connected: true,
  emit: vi.fn(),
  on: vi.fn(),
  off: vi.fn(),
};

vi.mock('@/lib/ws/socket', () => ({
  getSocket: vi.fn(() => mockSocket),
  closeSocket: vi.fn(),
  wsBaseUrl: vi.fn(() => 'http://localhost:3001'),
}));

function wrapper({ children }: { children: React.ReactNode }): React.ReactElement {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

describe('useBidEvents', () => {
  beforeEach(() => {
    mockSocket.emit.mockClear();
    mockSocket.on.mockClear();
    mockSocket.off.mockClear();
    useAuthStore.setState({
      accessToken: 'test-token',
      user: { sub: 'demo', username: 'demo', roles: ['bid_manager'] },
      hydrated: true,
    });
  });

  it('subscribes on mount and unsubscribes on unmount', () => {
    const { unmount } = renderHook(() => useBidEvents('bid-123'), { wrapper });

    expect(mockSocket.emit).toHaveBeenCalledWith('subscribe', 'bid-123');
    expect(mockSocket.on).toHaveBeenCalledWith('bid.event', expect.any(Function));

    unmount();

    expect(mockSocket.emit).toHaveBeenCalledWith('unsubscribe', 'bid-123');
    expect(mockSocket.off).toHaveBeenCalledWith('bid.event', expect.any(Function));
  });

  it('does nothing when no token present', () => {
    useAuthStore.setState({ accessToken: null, user: null, hydrated: true });
    renderHook(() => useBidEvents('bid-123'), { wrapper });
    expect(mockSocket.emit).not.toHaveBeenCalled();
  });
});
