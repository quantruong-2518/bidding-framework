import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StateDetail } from '@/components/workflow/state-detail';
import { useAuthStore } from '@/lib/auth/store';
import {
  FALLBACK_ACL,
  hasArtifactAccess,
  type AclMap,
} from '@/lib/api/acl';
import type { WorkflowStatus } from '@/lib/api/types';

const SAMPLE_STATUS: Partial<WorkflowStatus> = {
  workflow_id: 'wf-1',
  status: 'COMPLETED',
  current_state: 'S11_DONE',
  state: 'S11_DONE',
  bid_card: {
    bid_id: 'bid-1',
    client_name: 'Acme Corp',
    industry: 'Finance',
    region: 'APAC',
    deadline: '2026-06-30T00:00:00.000Z',
    scope_summary: 'Modernize platform',
    estimated_profile: 'L',
    technology_keywords: ['Kafka'],
    requirements_raw: [],
    created_at: '2026-04-01T08:00:00.000Z',
  },
  pricing: {
    bid_id: 'bid-1',
    model: 'fixed_price',
    subtotal: 200_000,
    total: 240_000,
    margin_pct: 20,
    currency: 'USD',
    scenarios: {},
    line_items: [],
    notes: [],
  },
} as unknown as Partial<WorkflowStatus>;

const AI_ACL: AclMap = {
  ...FALLBACK_ACL,
  bid_card: [
    'admin',
    'bid_manager',
    'ba',
    'sa',
    'qc',
    'domain_expert',
    'solution_lead',
  ],
  pricing: ['admin', 'bid_manager', 'qc'],
};

function setAuth(roles: string[], acl: AclMap | null = AI_ACL): void {
  useAuthStore.setState({
    accessToken: 'stub-token',
    user: {
      sub: 'kc-1',
      username: 'tester',
      email: 't@b.c',
      roles,
    },
    acl,
    hydrated: true,
    refreshToken: null,
    expiresAt: null,
  });
}

describe('StateDetail RBAC filtering', () => {
  beforeEach(() => {
    useAuthStore.setState({
      accessToken: null,
      refreshToken: null,
      expiresAt: null,
      user: null,
      acl: null,
      hydrated: false,
    });
    vi.restoreAllMocks();
  });

  it('renders the pricing panel for admin', () => {
    setAuth(['admin']);
    render(
      <StateDetail selected="S7" status={SAMPLE_STATUS as WorkflowStatus} />,
    );
    // The pricing panel renders "Pricing" section header.
    expect(screen.getByText(/Pricing/i)).toBeInTheDocument();
    expect(screen.queryByRole('alert', { name: /access-denied/i })).toBeNull();
  });

  it('hides pricing behind an access-restricted placeholder for BA', () => {
    setAuth(['ba']);
    render(
      <StateDetail selected="S7" status={SAMPLE_STATUS as WorkflowStatus} />,
    );
    expect(
      screen.getByRole('alert', { name: /access-denied/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/access restricted/i)).toBeInTheDocument();
  });

  it('shows the bid card to every role (ACL union)', () => {
    setAuth(['domain_expert']);
    render(
      <StateDetail selected="S0" status={SAMPLE_STATUS as WorkflowStatus} />,
    );
    expect(screen.getByText(/Acme Corp/)).toBeInTheDocument();
    expect(screen.queryByRole('alert', { name: /access-denied/i })).toBeNull();
  });

  it('falls back to admin-only map when ACL fetch has not completed', () => {
    // No user set — fallback path must still deny non-admins.
    setAuth(['ba'], null);
    render(
      <StateDetail selected="S7" status={SAMPLE_STATUS as WorkflowStatus} />,
    );
    expect(
      screen.getByRole('alert', { name: /access-denied/i }),
    ).toBeInTheDocument();
  });
});

describe('hasArtifactAccess helper', () => {
  it('admin bypasses the ACL map entirely', () => {
    expect(hasArtifactAccess(null, ['admin'], 'pricing')).toBe(true);
  });

  it('returns false when no roles are supplied', () => {
    expect(hasArtifactAccess(AI_ACL, [], 'bid_card')).toBe(false);
  });

  it('matches role against the map', () => {
    expect(hasArtifactAccess(AI_ACL, ['qc'], 'pricing')).toBe(true);
    expect(hasArtifactAccess(AI_ACL, ['ba'], 'pricing')).toBe(false);
  });

  it('skips blank-string entries', () => {
    expect(hasArtifactAccess(AI_ACL, ['', 'qc', '  '], 'pricing')).toBe(true);
    expect(hasArtifactAccess(AI_ACL, ['', '  '], 'bid_card')).toBe(false);
  });
});
