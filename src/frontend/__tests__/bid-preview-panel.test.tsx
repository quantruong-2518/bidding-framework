import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BidPreviewPanel } from '@/components/bids/bid-preview-panel';
import type { PreviewResponse } from '@/lib/api/types';

const confirmMock = vi.fn();
const abandonMock = vi.fn();
const pushMock = vi.fn();

vi.mock('@/lib/api/parse-sessions', () => ({
  confirm: (...args: unknown[]) => confirmMock(...args),
  abandon: (...args: unknown[]) => abandonMock(...args),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock, replace: pushMock }),
}));

function buildPreview(overrides: Partial<PreviewResponse> = {}): PreviewResponse {
  return {
    session_id: 'sid-1',
    status: 'READY',
    suggested_bid_card: {
      name: 'Acme Bank — Core Mod',
      client_name: 'Acme Bank',
      industry: 'banking',
      region: 'VN',
      deadline: '2026-08-30',
      scope_summary: 'Modernise core banking',
      estimated_profile: 'L',
      language: 'en',
      technology_keywords: ['microservices', 'kafka'],
    },
    context_preview: {
      anchor_md: 'Anchor frame.',
      summary_md: 'Exec summary.',
      open_questions: ['Which AD forest?'],
    },
    atoms_preview: {
      total: 5,
      by_type: { functional: 3, nfr: 2 },
      by_priority: { MUST: 4, SHOULD: 1 },
      low_confidence_count: 1,
      sample: [
        {
          id: 'REQ-F-001',
          type: 'functional',
          priority: 'MUST',
          category: 'auth',
          source_file: 'sources/01-rfp.md',
          body_md: 'SSO',
          confidence: 0.9,
        },
      ],
    },
    sources_preview: [],
    conflicts_detected: [
      {
        id: 'C1',
        description: 'AWS only vs multi-cloud',
        atom_ids: ['REQ-TECH-005', 'REQ-TECH-012'],
        severity: 'high',
      },
    ],
    suggested_workflow: {
      profile: 'L',
      pipeline: ['S0', 'S0_5', 'S1', 'S2', 'S3', 'S4', 'S11'],
      estimated_total_token_cost_usd: 2.4,
      estimated_duration_hours: 48,
      review_gate: { reviewer_count: 3, timeout_hours: 72, max_rounds: 3 },
    },
    current_state: 'AWAITING_CONFIRM',
    expires_at: '2026-05-03T00:00:00Z',
    ...overrides,
  };
}

function wrapper({ children }: { children: React.ReactNode }): React.ReactElement {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

describe('BidPreviewPanel', () => {
  beforeEach(() => {
    confirmMock.mockReset();
    abandonMock.mockReset();
    pushMock.mockReset();
  });

  it('renders bid card + workflow + conflict shape from PreviewResponse', () => {
    render(<BidPreviewPanel preview={buildPreview()} />, { wrapper });
    expect(screen.getByTestId('bid-name')).toHaveValue('Acme Bank — Core Mod');
    expect(screen.getByTestId('bid-client')).toHaveValue('Acme Bank');
    expect(screen.getByTestId('workflow-proposal-card')).toBeInTheDocument();
    expect(screen.getByTestId('conflict-row-C1')).toHaveTextContent(/AWS only/);
    expect(screen.getByTestId('atoms-total')).toHaveTextContent('Total: 5');
  });

  it('confirm posts only the changed overrides and navigates on success', async () => {
    confirmMock.mockResolvedValue({
      bid_id: 'bid-42',
      workflow_id: 'wf-42',
      vault_path: 'kb-vault/bids/bid-42',
    });
    render(<BidPreviewPanel preview={buildPreview()} />, { wrapper });
    fireEvent.change(screen.getByTestId('bid-name'), {
      target: { value: 'New name' },
    });
    fireEvent.change(screen.getByTestId('bid-profile'), {
      target: { value: 'XL' },
    });
    fireEvent.click(screen.getByTestId('confirm-button'));
    await waitFor(() => expect(confirmMock).toHaveBeenCalled());
    expect(confirmMock).toHaveBeenCalledWith('sid-1', {
      name: 'New name',
      profile_override: 'XL',
    });
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/bids/bid-42'));
  });

  it('abandon button calls abandon API and navigates back to /bids', async () => {
    abandonMock.mockResolvedValue(undefined);
    render(<BidPreviewPanel preview={buildPreview()} />, { wrapper });
    fireEvent.click(screen.getByTestId('abandon-button'));
    await waitFor(() => expect(abandonMock).toHaveBeenCalledWith('sid-1'));
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/bids'));
  });

  it('surfaces confirm error in the panel error banner', async () => {
    confirmMock.mockRejectedValue(new Error('boom'));
    render(<BidPreviewPanel preview={buildPreview()} />, { wrapper });
    fireEvent.click(screen.getByTestId('confirm-button'));
    await waitFor(() =>
      expect(screen.getByTestId('bid-preview-error')).toHaveTextContent('boom'),
    );
    expect(pushMock).not.toHaveBeenCalled();
  });
});
