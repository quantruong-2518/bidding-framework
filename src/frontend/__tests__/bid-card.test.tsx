import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BidCard } from '@/components/bids/bid-card';
import type { Bid } from '@/lib/api/types';

const SAMPLE: Bid = {
  id: 'bid-1',
  clientName: 'Acme Corp',
  industry: 'Finance',
  region: 'APAC',
  deadline: '2026-06-30T00:00:00.000Z',
  scopeSummary: 'Modernize core banking platform with event-driven services.',
  technologyKeywords: ['Kafka', 'Kubernetes', 'NestJS', 'React'],
  estimatedProfile: 'L',
  status: 'IN_PROGRESS',
  workflowId: 'wf-1',
  createdAt: '2026-04-01T08:00:00.000Z',
  updatedAt: '2026-04-02T08:00:00.000Z',
};

describe('BidCard', () => {
  it('renders client, industry, profile, deadline and tech keywords', () => {
    render(<BidCard bid={SAMPLE} />);
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    expect(screen.getByText(/Finance/)).toBeInTheDocument();
    expect(screen.getByText(/APAC/)).toBeInTheDocument();
    expect(screen.getByText('L')).toBeInTheDocument();
    expect(screen.getByText(/2026-06-30/)).toBeInTheDocument();
    expect(screen.getByText('Kafka')).toBeInTheDocument();
    expect(screen.getByText('NestJS')).toBeInTheDocument();
    expect(screen.getByText(/Open workflow/)).toBeInTheDocument();
  });

  it('shows the status badge derived from bid.status', () => {
    render(<BidCard bid={SAMPLE} />);
    expect(screen.getByText('IN_PROGRESS')).toBeInTheDocument();
  });
});
