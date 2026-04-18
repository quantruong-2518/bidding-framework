import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { LangfuseLinkButton } from '@/components/bids/langfuse-link-button';
import { useAuthStore } from '@/lib/auth/store';

const getBidTraceUrlMock = vi.fn();

vi.mock('@/lib/api/bids', async (orig) => {
  const real = await orig<typeof import('@/lib/api/bids')>();
  return {
    ...real,
    getBidTraceUrl: (...args: unknown[]) => getBidTraceUrlMock(...args),
  };
});

describe('LangfuseLinkButton', () => {
  beforeEach(() => {
    getBidTraceUrlMock.mockReset();
  });

  it('shows the trace link for an admin user', async () => {
    useAuthStore.setState({
      accessToken: 'tok',
      user: { sub: 'u1', username: 'admin', roles: ['admin'] },
      hydrated: true,
    });
    getBidTraceUrlMock.mockResolvedValueOnce({
      url: 'http://localhost:3002/trace/bid-42',
    });

    render(<LangfuseLinkButton bidId="bid-42" />);

    const link = await screen.findByRole('link', { name: /Langfuse trace/i });
    expect(link).toHaveAttribute('href', 'http://localhost:3002/trace/bid-42');
    expect(link).toHaveAttribute('target', '_blank');
    expect(getBidTraceUrlMock).toHaveBeenCalledWith('bid-42');
  });

  it('renders nothing for a viewer without allowed roles', async () => {
    useAuthStore.setState({
      accessToken: 'tok',
      user: { sub: 'u2', username: 'viewer', roles: ['ba'] },
      hydrated: true,
    });

    const { container } = render(<LangfuseLinkButton bidId="bid-42" />);

    await waitFor(() => {
      expect(container.textContent ?? '').toBe('');
    });
    expect(getBidTraceUrlMock).not.toHaveBeenCalled();
  });

  it('renders nothing when the gateway returns 404 (Langfuse not configured)', async () => {
    useAuthStore.setState({
      accessToken: 'tok',
      user: { sub: 'u3', username: 'mgr', roles: ['bid_manager'] },
      hydrated: true,
    });
    getBidTraceUrlMock.mockRejectedValueOnce(new Error('not found'));

    const { container } = render(<LangfuseLinkButton bidId="bid-42" />);

    await waitFor(() => {
      expect(getBidTraceUrlMock).toHaveBeenCalledWith('bid-42');
    });
    expect(container.querySelector('a')).toBeNull();
  });
});
