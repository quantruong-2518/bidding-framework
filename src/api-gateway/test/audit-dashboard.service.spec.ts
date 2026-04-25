import { NotFoundException } from '@nestjs/common';
import { AuditDashboardService } from '../src/audit-dashboard/audit-dashboard.service';
import type { AuditLogAggregator } from '../src/audit-dashboard/aggregators/audit-log.aggregator';
import type { LangfuseAggregator } from '../src/audit-dashboard/aggregators/langfuse.aggregator';
import type { TemporalAggregator } from '../src/audit-dashboard/aggregators/temporal.aggregator';
import type { BidsService } from '../src/bids/bids.service';
import { summariseObservations } from '../src/audit-dashboard/aggregators/langfuse.aggregator';
import type { DecisionTrailEntry } from '../src/audit-dashboard/types';

function buildService(overrides?: {
  bids?: Partial<BidsService>;
  auditLogs?: Partial<AuditLogAggregator>;
  langfuse?: Partial<LangfuseAggregator>;
  temporal?: Partial<TemporalAggregator>;
}): {
  service: AuditDashboardService;
  bids: jest.Mocked<BidsService>;
  auditLogs: jest.Mocked<AuditLogAggregator>;
  langfuse: jest.Mocked<LangfuseAggregator>;
  temporal: jest.Mocked<TemporalAggregator>;
} {
  const bids = {
    findOne: jest.fn().mockResolvedValue({
      id: 'bid-1',
      clientName: 'ACME',
      industry: 'retail',
      region: 'NA',
      deadline: '2026-07-01',
      scopeSummary: 'ecom',
      technologyKeywords: [],
      estimatedProfile: 'M',
      status: 'IN_PROGRESS',
      workflowId: 'wf-1',
      createdAt: '2026-04-01T00:00:00.000Z',
      updatedAt: '2026-04-02T00:00:00.000Z',
    }),
    findAll: jest.fn().mockResolvedValue([]),
    ...overrides?.bids,
  } as unknown as jest.Mocked<BidsService>;

  const auditLogs = {
    forBid: jest.fn().mockResolvedValue([] as DecisionTrailEntry[]),
    recent: jest.fn().mockResolvedValue([] as DecisionTrailEntry[]),
    distinctBidCount: jest.fn().mockResolvedValue(0),
    ...overrides?.auditLogs,
  } as unknown as jest.Mocked<AuditLogAggregator>;

  const langfuse = {
    forBid: jest.fn().mockResolvedValue({
      costs: {
        totalUsd: 0,
        byAgent: {},
        byModel: {},
        generationCount: 0,
        latencyP95Ms: 0,
      },
    }),
    aggregateRange: jest.fn().mockResolvedValue({ total: 0, byAgent: {}, byDay: {} }),
    isConfigured: jest.fn().mockReturnValue(false),
    ...overrides?.langfuse,
  } as unknown as jest.Mocked<LangfuseAggregator>;

  const temporal = {
    forWorkflow: jest.fn().mockResolvedValue({ events: [] }),
    ...overrides?.temporal,
  } as unknown as jest.Mocked<TemporalAggregator>;

  return {
    service: new AuditDashboardService(bids, auditLogs, langfuse, temporal),
    bids,
    auditLogs,
    langfuse,
    temporal,
  };
}

describe('AuditDashboardService.getBidDetail', () => {
  it('merges trail + history + costs for a known bid', async () => {
    const { service, auditLogs, langfuse } = buildService();
    auditLogs.forBid.mockResolvedValue([
      {
        timestamp: '2026-04-01T00:00:00.000Z',
        action: 'POST /bids/:id/workflow',
        actor: { userSub: 'u1', username: 'alice', roles: ['bid_manager'] },
        resourceType: 'bids',
        resourceId: 'bid-1',
        statusCode: 200,
        metadata: null,
      },
    ]);
    langfuse.forBid.mockResolvedValue({
      costs: {
        totalUsd: 1.23,
        byAgent: { ba: 0.5, sa: 0.73 },
        byModel: { 'claude-sonnet-4-6': 1.23 },
        generationCount: 2,
        latencyP95Ms: 1500,
      },
    });

    const detail = await service.getBidDetail('bid-1');
    expect(detail.bidId).toBe('bid-1');
    expect(detail.decisionTrail).toHaveLength(1);
    expect(detail.costs.totalUsd).toBeCloseTo(1.23);
    expect(detail.warnings).toEqual([]);
  });

  it('surfaces warnings from partial upstream failures', async () => {
    const { service, langfuse, temporal } = buildService();
    langfuse.forBid.mockResolvedValue({
      costs: {
        totalUsd: 0,
        byAgent: {},
        byModel: {},
        generationCount: 0,
        latencyP95Ms: 0,
      },
      warning: 'Langfuse unreachable',
    });
    temporal.forWorkflow.mockResolvedValue({
      events: [],
      warning: 'Temporal Visibility not wired',
    });

    const detail = await service.getBidDetail('bid-1');
    expect(detail.warnings).toEqual(
      expect.arrayContaining([
        'Langfuse unreachable',
        'Temporal Visibility not wired',
      ]),
    );
    expect(detail.costs.totalUsd).toBe(0);
  });

  it('re-throws NotFoundException when the bid is missing', async () => {
    const { service, bids } = buildService();
    bids.findOne.mockRejectedValueOnce(new NotFoundException('gone'));
    await expect(service.getBidDetail('nope')).rejects.toBeInstanceOf(
      NotFoundException,
    );
  });

  it('reports completedAt + duration only for WON/LOST bids', async () => {
    const { service, bids } = buildService();
    bids.findOne.mockResolvedValueOnce({
      id: 'bid-1',
      clientName: 'ACME',
      industry: '',
      region: '',
      deadline: '',
      scopeSummary: '',
      technologyKeywords: [],
      estimatedProfile: 'M',
      status: 'WON',
      workflowId: 'wf-1',
      createdAt: '2026-04-01T00:00:00.000Z',
      updatedAt: '2026-04-01T01:30:00.000Z',
    } as never);
    const won = await service.getBidDetail('bid-1');
    expect(won.summary.completedAt).toBe('2026-04-01T01:30:00.000Z');
    expect(won.summary.totalDurationMs).toBe(90 * 60 * 1000);

    bids.findOne.mockResolvedValueOnce({
      id: 'bid-2',
      clientName: 'ACME',
      industry: '',
      region: '',
      deadline: '',
      scopeSummary: '',
      technologyKeywords: [],
      estimatedProfile: 'M',
      status: 'IN_PROGRESS',
      workflowId: 'wf-2',
      createdAt: '2026-04-01T00:00:00.000Z',
      updatedAt: '2026-04-01T01:30:00.000Z',
    } as never);
    const inProgress = await service.getBidDetail('bid-2');
    expect(inProgress.summary.completedAt).toBeNull();
    expect(inProgress.summary.totalDurationMs).toBeNull();
  });

  it('caches the response within the TTL', async () => {
    const { service, auditLogs } = buildService();
    auditLogs.forBid.mockResolvedValue([]);
    await service.getBidDetail('bid-1');
    await service.getBidDetail('bid-1');
    expect(auditLogs.forBid).toHaveBeenCalledTimes(1);
  });
});

describe('AuditDashboardService.getSummary', () => {
  it('aggregates decisions + cost + totals + filters by status', async () => {
    const { service, auditLogs, langfuse, bids } = buildService();
    auditLogs.recent.mockResolvedValue([
      {
        timestamp: '2026-04-10T12:00:00.000Z',
        action: 'POST /bids',
        actor: { userSub: 'u1', username: 'alice', roles: ['admin'] },
        resourceType: 'bids',
        resourceId: 'bid-1',
        statusCode: 201,
        metadata: null,
      },
    ]);
    auditLogs.distinctBidCount.mockResolvedValue(3);
    langfuse.aggregateRange.mockResolvedValue({
      total: 4.56,
      byAgent: { ba: 2.0, sa: 1.56, domain: 1.0 },
      byDay: { '2026-04-10': 4.56 },
    });
    bids.findAll.mockResolvedValue([
      {
        id: 'bid-1',
        clientName: 'ACME',
        industry: 'retail',
        region: 'NA',
        deadline: '2026-07-01',
        scopeSummary: 'ecom',
        technologyKeywords: [],
        estimatedProfile: 'M',
        status: 'WON',
        workflowId: 'wf-1',
        createdAt: '2026-04-10T00:00:00.000Z',
        updatedAt: '2026-04-10T00:00:00.000Z',
      },
      {
        id: 'bid-2',
        clientName: 'Globex',
        industry: 'finance',
        region: 'EU',
        deadline: '2026-08-01',
        scopeSummary: 'core',
        technologyKeywords: [],
        estimatedProfile: 'L',
        status: 'LOST',
        workflowId: 'wf-2',
        createdAt: '2026-04-12T00:00:00.000Z',
        updatedAt: '2026-04-12T00:00:00.000Z',
      },
    ] as never);

    const summary = await service.getSummary({
      from: '2026-04-01',
      to: '2026-04-30',
      status: 'WON',
    });
    expect(summary.totals.completed).toBe(1);
    expect(summary.totals.rejected).toBe(0); // LOST filtered out by status=WON
    expect(summary.totals.bids).toBe(3); // from distinct audit_log count
    expect(summary.costUsd.total).toBeCloseTo(4.56);
    expect(summary.agentCost.ba).toBeCloseTo(2.0);
    expect(summary.recentDecisions[0]?.bidId).toBe('bid-1');
  });

  it('drops dashboard self-reads from the recent-decisions feed', async () => {
    const { service, auditLogs } = buildService();
    auditLogs.recent.mockResolvedValue([
      {
        timestamp: '2026-04-10T12:00:00.000Z',
        action: 'GET /dashboard/audit',
        actor: { userSub: 'admin', username: 'admin', roles: ['admin'] },
        resourceType: 'dashboard',
        resourceId: null,
        statusCode: 200,
        metadata: null,
      },
      {
        timestamp: '2026-04-10T12:01:00.000Z',
        action: 'POST /bids',
        actor: { userSub: 'u1', username: 'alice', roles: ['bid_manager'] },
        resourceType: 'bids',
        resourceId: 'bid-1',
        statusCode: 201,
        metadata: null,
      },
    ]);
    const summary = await service.getSummary({
      from: '2026-04-01',
      to: '2026-04-30',
    });
    expect(summary.recentDecisions).toHaveLength(1);
    expect(summary.recentDecisions[0]?.action).toBe('POST /bids');
  });

  it('counts in-progress as DRAFT + TRIAGED + IN_PROGRESS', async () => {
    const { service, bids } = buildService();
    bids.findAll.mockResolvedValue([
      { id: 'a', status: 'DRAFT', createdAt: '2026-04-10T00:00:00.000Z', clientName: 'A', industry: '', region: '', deadline: '', scopeSummary: '', technologyKeywords: [], estimatedProfile: 'M', workflowId: null, updatedAt: '2026-04-10T00:00:00.000Z' },
      { id: 'b', status: 'TRIAGED', createdAt: '2026-04-10T00:00:00.000Z', clientName: 'B', industry: '', region: '', deadline: '', scopeSummary: '', technologyKeywords: [], estimatedProfile: 'M', workflowId: null, updatedAt: '2026-04-10T00:00:00.000Z' },
      { id: 'c', status: 'IN_PROGRESS', createdAt: '2026-04-10T00:00:00.000Z', clientName: 'C', industry: '', region: '', deadline: '', scopeSummary: '', technologyKeywords: [], estimatedProfile: 'M', workflowId: null, updatedAt: '2026-04-10T00:00:00.000Z' },
      { id: 'd', status: 'WON', createdAt: '2026-04-10T00:00:00.000Z', clientName: 'D', industry: '', region: '', deadline: '', scopeSummary: '', technologyKeywords: [], estimatedProfile: 'M', workflowId: null, updatedAt: '2026-04-10T00:00:00.000Z' },
    ] as never);
    const summary = await service.getSummary({
      from: '2026-04-01',
      to: '2026-04-30',
    });
    expect(summary.totals.inProgress).toBe(3);
    expect(summary.totals.completed).toBe(1);
  });

  it('propagates warning when Langfuse is unconfigured', async () => {
    const { service, langfuse } = buildService();
    langfuse.aggregateRange.mockResolvedValue({
      total: 0,
      byAgent: {},
      byDay: {},
      warning: 'Langfuse is not configured',
    });
    const summary = await service.getSummary({
      from: '2026-04-01',
      to: '2026-04-30',
    });
    expect(summary.warnings).toContain('Langfuse is not configured');
  });

  it('rejects an invalid date range', async () => {
    const { service } = buildService();
    await expect(
      service.getSummary({ from: 'bad-date', to: '2026-04-30' }),
    ).rejects.toThrow(/invalid date range/);
  });
});

describe('AuditDashboardService.summaryToCsv', () => {
  it('writes header + one row per byDay bucket + footer comments', async () => {
    const { service } = buildService();
    const csv = service.summaryToCsv({
      dateRange: { from: '2026-04-01', to: '2026-04-30' },
      totals: { bids: 3, completed: 1, rejected: 1, inProgress: 1 },
      costUsd: { total: 4.56, avgPerBid: 1.52 },
      agentCost: { ba: 1, sa: 2, domain: 1.56 },
      byDay: [
        { date: '2026-04-10', bidCount: 2, costUsd: 3.25 },
        { date: '2026-04-11', bidCount: 1, costUsd: 1.31 },
      ],
      recentBids: [],
      recentDecisions: [],
      warnings: [],
    });
    expect(csv.split('\n')[0]).toBe('date,bid_count,cost_usd');
    expect(csv).toContain('2026-04-10,2,3.2500');
    expect(csv).toContain('# totals.bids=3');
    expect(csv).toContain('# cost.total_usd=4.5600');
  });
});

describe('summariseObservations helper', () => {
  it('buckets costs by agent + model, counts generations, computes p95 latency', () => {
    const breakdown = summariseObservations([
      {
        type: 'GENERATION',
        name: 'ba.synth',
        model: 'claude-sonnet-4-6',
        usageDetails: { totalCost: 0.5 },
        latency: 800,
      },
      {
        type: 'GENERATION',
        name: 'sa.classify',
        model: 'claude-haiku-4-5',
        usageDetails: { totalCost: 0.1 },
        latency: 500,
      },
      {
        type: 'GENERATION',
        name: 'ba.critique',
        model: 'claude-sonnet-4-6',
        usageDetails: { totalCost: 0.4 },
        latency: 1500,
      },
      { type: 'EVENT', name: 'log.write' }, // ignored
    ]);
    expect(breakdown.totalUsd).toBeCloseTo(1.0);
    expect(breakdown.generationCount).toBe(3);
    expect(breakdown.byAgent.ba).toBeCloseTo(0.9);
    expect(breakdown.byAgent.sa).toBeCloseTo(0.1);
    expect(breakdown.byModel['claude-sonnet-4-6']).toBeCloseTo(0.9);
    expect(breakdown.latencyP95Ms).toBeGreaterThan(0);
  });

  it('returns zeros for empty input', () => {
    const empty = summariseObservations([]);
    expect(empty.totalUsd).toBe(0);
    expect(empty.generationCount).toBe(0);
    expect(empty.latencyP95Ms).toBe(0);
  });
});
