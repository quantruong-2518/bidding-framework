import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import * as React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReviewGatePanel } from '@/components/bids/review-gate-panel';
import { useAuthStore } from '@/lib/auth/store';

const sendReviewSignalMock = vi.fn().mockResolvedValue({ status: 'accepted' });

vi.mock('@/lib/api/bids', async (orig) => {
  const real = await orig<typeof import('@/lib/api/bids')>();
  return {
    ...real,
    sendReviewSignal: (...args: unknown[]) => sendReviewSignalMock(...args),
  };
});

function wrapper({ children }: { children: React.ReactNode }): React.ReactElement {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

describe('ReviewGatePanel', () => {
  beforeEach(() => {
    sendReviewSignalMock.mockClear();
    useAuthStore.setState({
      accessToken: 'test-token',
      user: { sub: 'demo', username: 'alice', roles: ['bid_manager'] },
      hydrated: true,
    });
  });

  it('renders round number and submit action', () => {
    render(<ReviewGatePanel bidId="bid-1" round={0} />, { wrapper });
    expect(screen.getByText(/Round 1/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Submit review/i })).toBeInTheDocument();
  });

  it('submits an APPROVED signal with no comments by default', async () => {
    const { container } = render(<ReviewGatePanel bidId="bid-1" round={0} />, {
      wrapper,
    });
    const form = container.querySelector('form');
    expect(form).not.toBeNull();
    fireEvent.submit(form!);
    await waitFor(() => {
      expect(sendReviewSignalMock).toHaveBeenCalled();
    });
    expect(sendReviewSignalMock).toHaveBeenCalledWith(
      'bid-1',
      expect.objectContaining({
        verdict: 'APPROVED',
        reviewer: 'alice',
        reviewerRole: 'bid_manager',
        comments: [],
      }),
    );
  });
});
