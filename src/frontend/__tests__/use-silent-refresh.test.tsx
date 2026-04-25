import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAuthStore } from '@/lib/auth/store';
import { useSilentTokenRefresh } from '@/lib/auth/use-silent-refresh';

const replace = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
}));

const refreshMock = vi.fn();
vi.mock('@/lib/auth/token-exchange', () => ({
  refreshAccessToken: (...args: unknown[]) => refreshMock(...args),
}));

function freshUser() {
  return { sub: 'kc-1', username: 'alice', email: 'a@b', roles: ['bid_manager'] };
}

describe('useSilentTokenRefresh', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    replace.mockReset();
    refreshMock.mockReset();
    useAuthStore.getState().clearAuth();
    useAuthStore.setState({ hydrated: true });
  });

  afterEach(() => {
    vi.useRealTimers();
    useAuthStore.getState().clearAuth();
    useAuthStore.setState({ hydrated: false });
  });

  it('no-ops when refreshToken or expiresAt are unset', () => {
    renderHook(() => useSilentTokenRefresh());
    // Advance well beyond any plausible refresh window.
    act(() => {
      vi.advanceTimersByTime(20 * 60 * 1000);
    });
    expect(refreshMock).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
  });

  it('schedules a refresh ~60 s before expiry and updates the store on success', async () => {
    const now = Date.now();
    useAuthStore.setState({
      accessToken: 'old-at',
      refreshToken: 'rt-1',
      expiresAt: now + 5 * 60 * 1000, // 5 min from now
      user: freshUser(),
    });
    refreshMock.mockResolvedValueOnce({
      accessToken: 'new-at',
      refreshToken: 'new-rt',
      expiresAt: now + 20 * 60 * 1000,
      user: { ...freshUser(), username: 'alice2' },
    });

    renderHook(() => useSilentTokenRefresh());
    expect(refreshMock).not.toHaveBeenCalled();

    // Advance to T-60s (i.e. 4 min in) and flush microtasks so the
    // resolved refresh promise propagates into the store before assert.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4 * 60 * 1000);
    });

    expect(refreshMock).toHaveBeenCalledTimes(1);
    expect(refreshMock).toHaveBeenCalledWith({ refreshToken: 'rt-1' });
    const store = useAuthStore.getState();
    expect(store.accessToken).toBe('new-at');
    expect(store.refreshToken).toBe('new-rt');
    expect(store.user?.username).toBe('alice2');
  });

  it('refreshes immediately when expiresAt is already past the lead window', async () => {
    const now = Date.now();
    useAuthStore.setState({
      accessToken: 'old-at',
      refreshToken: 'rt-1',
      expiresAt: now + 30_000, // 30 s away — already past 60 s lead
      user: freshUser(),
    });
    refreshMock.mockResolvedValueOnce({
      accessToken: 'new-at',
      refreshToken: 'new-rt',
      expiresAt: now + 20 * 60 * 1000,
      user: freshUser(),
    });

    renderHook(() => useSilentTokenRefresh());
    // Flush the microtask queue so the immediate refresh resolves.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(refreshMock).toHaveBeenCalledTimes(1);
  });

  it('clears the session and redirects to /login when refresh fails', async () => {
    const now = Date.now();
    useAuthStore.setState({
      accessToken: 'old-at',
      refreshToken: 'rt-bad',
      expiresAt: now + 30_000,
      user: freshUser(),
    });
    refreshMock.mockRejectedValueOnce(new Error('refresh expired'));

    renderHook(() => useSilentTokenRefresh());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(replace).toHaveBeenCalledWith('/login');
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().refreshToken).toBeNull();
  });

  it('clears the timer on unmount so a logout does not race a stale refresh', () => {
    const now = Date.now();
    useAuthStore.setState({
      accessToken: 'old-at',
      refreshToken: 'rt-1',
      expiresAt: now + 5 * 60 * 1000,
      user: freshUser(),
    });
    const { unmount } = renderHook(() => useSilentTokenRefresh());
    unmount();
    act(() => {
      vi.advanceTimersByTime(10 * 60 * 1000);
    });
    expect(refreshMock).not.toHaveBeenCalled();
  });
});
