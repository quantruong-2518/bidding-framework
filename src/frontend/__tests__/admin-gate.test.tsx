import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { AdminGate } from '@/components/layout/admin-gate';
import { useAuthStore } from '@/lib/auth/store';

const replace = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
}));

describe('AdminGate', () => {
  beforeEach(() => {
    replace.mockReset();
    useAuthStore.getState().clearAuth();
    useAuthStore.setState({ hydrated: false });
  });

  afterEach(() => {
    useAuthStore.getState().clearAuth();
    useAuthStore.setState({ hydrated: false });
  });

  it('shows a loading skeleton until the auth store hydrates', () => {
    render(
      <AdminGate>
        <div data-testid="payload">payload</div>
      </AdminGate>,
    );
    expect(screen.getByTestId('admin-gate-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('payload')).not.toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it('renders children for an admin user', () => {
    useAuthStore.setState({
      hydrated: true,
      accessToken: 'stub',
      user: { sub: 'kc-1', username: 'admin', roles: ['admin'] },
    });
    render(
      <AdminGate>
        <div data-testid="payload">payload</div>
      </AdminGate>,
    );
    expect(screen.getByTestId('payload')).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it('redirects + shows a denied placeholder for a non-admin user', async () => {
    useAuthStore.setState({
      hydrated: true,
      accessToken: 'stub',
      user: { sub: 'kc-2', username: 'alice', roles: ['bid_manager'] },
    });
    render(
      <AdminGate>
        <div data-testid="payload">payload</div>
      </AdminGate>,
    );
    expect(screen.getByTestId('admin-gate-denied')).toBeInTheDocument();
    expect(screen.queryByTestId('payload')).not.toBeInTheDocument();
    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith('/dashboard');
    });
  });

  it('honours a custom redirectTo', async () => {
    useAuthStore.setState({
      hydrated: true,
      accessToken: 'stub',
      user: { sub: 'kc-3', username: 'qa', roles: ['qc'] },
    });
    render(
      <AdminGate redirectTo="/bids">
        <div>payload</div>
      </AdminGate>,
    );
    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith('/bids');
    });
  });
});
