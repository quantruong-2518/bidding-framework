import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as React from 'react';
import AuditPage from '@/app/(authed)/audit/page';
import { DecisionTrail } from '@/components/audit/decision-trail';
import { WorkflowHistoryView } from '@/components/audit/workflow-history-view';
import * as auditApi from '@/lib/api/audit';
import type { DashboardSummary } from '@/lib/api/audit';

vi.mock('recharts', async () => {
  const React = await import('react');
  const Passthrough = ({
    children,
  }: {
    children?: React.ReactNode;
  }): React.ReactElement => <div>{children}</div>;
  const Empty = (): null => null;
  return {
    ResponsiveContainer: Passthrough,
    BarChart: Passthrough,
    Bar: Empty,
    PieChart: Passthrough,
    Pie: Empty,
    Cell: Empty,
    XAxis: Empty,
    YAxis: Empty,
    Tooltip: Empty,
    Legend: Empty,
    CartesianGrid: Empty,
  };
});

const SUMMARY: DashboardSummary = {
  dateRange: { from: '2026-04-01', to: '2026-04-30' },
  totals: { bids: 5, completed: 3, rejected: 1, inProgress: 1 },
  costUsd: { total: 12.34, avgPerBid: 2.47 },
  agentCost: { ba: 4.2, sa: 5.1, domain: 3.04 },
  byDay: [
    { date: '2026-04-10', bidCount: 2, costUsd: 5.0 },
    { date: '2026-04-11', bidCount: 3, costUsd: 7.34 },
  ],
  recentBids: [],
  recentDecisions: [
    {
      timestamp: '2026-04-10T12:00:00.000Z',
      action: 'POST /bids/:id/workflow',
      actor: { userSub: 'u1', username: 'alice', roles: ['admin'] },
      resourceType: 'bids',
      resourceId: 'bid-1',
      statusCode: 200,
      metadata: null,
      bidId: 'bid-1',
    },
  ],
  warnings: [],
};

function Wrapper({ children }: { children: React.ReactNode }): React.ReactElement {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('AuditPage', () => {
  beforeEach(() => {
    vi.spyOn(auditApi, 'fetchSummary').mockResolvedValue(SUMMARY);
    vi.spyOn(auditApi, 'downloadCsv').mockResolvedValue();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders totals + cost cards once the summary loads', async () => {
    render(<AuditPage />, { wrapper: Wrapper });
    expect(screen.getByTestId('audit-page')).toBeInTheDocument();
    // Wait for async summary to populate.
    expect(await screen.findByText('5')).toBeInTheDocument();
    expect(screen.getByText('$12.34')).toBeInTheDocument();
    expect(screen.getByText('$2.47')).toBeInTheDocument();
  });

  it('surfaces a warnings banner when the server reports partial data', async () => {
    vi.spyOn(auditApi, 'fetchSummary').mockResolvedValue({
      ...SUMMARY,
      warnings: ['Langfuse unreachable'],
    });
    render(<AuditPage />, { wrapper: Wrapper });
    expect(await screen.findByTestId('warnings-banner')).toBeInTheDocument();
    expect(screen.getByText(/Langfuse unreachable/)).toBeInTheDocument();
  });

  it('passes filter values through to fetchSummary', async () => {
    render(<AuditPage />, { wrapper: Wrapper });
    await screen.findByText('5'); // initial load done

    const statusInput = screen.getByLabelText('Status');
    fireEvent.change(statusInput, { target: { value: 'WON' } });
    const form = screen.getByTestId('filters-form');
    fireEvent.submit(form);

    await waitFor(() => {
      expect(auditApi.fetchSummary).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: 'WON' }),
      );
    });
  });

  it('triggers CSV download when the export button is clicked', async () => {
    render(<AuditPage />, { wrapper: Wrapper });
    const btn = await screen.findByTestId('export-csv');
    fireEvent.click(btn);
    await waitFor(() => {
      expect(auditApi.downloadCsv).toHaveBeenCalled();
    });
  });
});

describe('DecisionTrail', () => {
  it('renders rows with status-coloured codes', () => {
    render(
      <DecisionTrail
        entries={[
          {
            timestamp: '2026-04-10T12:00:00.000Z',
            action: 'POST /bids',
            actor: { userSub: 'u', username: 'alice', roles: ['admin'] },
            resourceType: 'bids',
            resourceId: 'bid-1',
            statusCode: 403,
            metadata: null,
          },
        ]}
      />,
    );
    expect(screen.getByText('403')).toBeInTheDocument();
    expect(screen.getByText('POST /bids')).toBeInTheDocument();
  });

  it('shows an empty-state message when there are no entries', () => {
    render(<DecisionTrail entries={[]} />);
    expect(screen.getByText(/No decisions recorded/)).toBeInTheDocument();
  });
});

describe('WorkflowHistoryView', () => {
  it('renders the warning placeholder when events are empty', () => {
    render(
      <WorkflowHistoryView
        events={[]}
        warningIfEmpty="Temporal Visibility stubbed (Phase 3.6)"
      />,
    );
    expect(screen.getByTestId('workflow-history-empty')).toBeInTheDocument();
    expect(screen.getByText(/Temporal Visibility stubbed/)).toBeInTheDocument();
  });

  it('renders one collapsible per event', () => {
    render(
      <WorkflowHistoryView
        events={[
          {
            eventId: 1,
            eventType: 'WorkflowStarted',
            timestamp: '2026-04-10T12:00:00.000Z',
            attributes: { foo: 'bar' },
          },
        ]}
      />,
    );
    expect(screen.getByText(/WorkflowStarted/)).toBeInTheDocument();
  });
});
