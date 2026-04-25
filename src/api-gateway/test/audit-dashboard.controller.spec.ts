import { Test, type TestingModule } from '@nestjs/testing';
import { BadRequestException } from '@nestjs/common';
import { AuditDashboardController } from '../src/audit-dashboard/audit-dashboard.controller';
import { AuditDashboardService } from '../src/audit-dashboard/audit-dashboard.service';
import type {
  BidAuditDetail,
  CostsResponse,
  DashboardSummary,
} from '../src/audit-dashboard/types';

const SAMPLE_DETAIL: BidAuditDetail = {
  bidId: 'bid-1',
  workflowId: 'wf-1',
  summary: {
    status: 'IN_PROGRESS',
    createdAt: '2026-04-01T00:00:00.000Z',
    completedAt: null,
    totalDurationMs: null,
  },
  decisionTrail: [],
  workflowHistory: [],
  costs: {
    totalUsd: 0,
    byAgent: {},
    byModel: {},
    generationCount: 0,
    latencyP95Ms: 0,
  },
  warnings: [],
};

const SAMPLE_SUMMARY: DashboardSummary = {
  dateRange: { from: '2026-04-01', to: '2026-04-30' },
  totals: { bids: 2, completed: 1, rejected: 1, blocked: 0 },
  costUsd: { total: 1.23, avgPerBid: 0.615, p95PerBid: 0 },
  agentCost: { ba: 0.5, sa: 0.73, domain: 0 },
  byDay: [{ date: '2026-04-10', bidCount: 2, costUsd: 1.23 }],
  topBids: [],
  recentDecisions: [],
  warnings: [],
};

describe('AuditDashboardController', () => {
  let controller: AuditDashboardController;
  let service: jest.Mocked<AuditDashboardService>;

  beforeEach(async () => {
    service = {
      getBidDetail: jest.fn().mockResolvedValue(SAMPLE_DETAIL),
      getSummary: jest.fn().mockResolvedValue(SAMPLE_SUMMARY),
      getCosts: jest.fn().mockResolvedValue({
        dateRange: { from: '2026-04-01', to: '2026-04-30' },
        groupBy: 'agent',
        buckets: [],
        warnings: [],
      } satisfies CostsResponse),
      summaryToCsv: jest
        .fn()
        .mockReturnValue('date,bid_count,cost_usd\n2026-04-10,2,1.2300\n'),
    } as unknown as jest.Mocked<AuditDashboardService>;

    const moduleRef: TestingModule = await Test.createTestingModule({
      controllers: [AuditDashboardController],
      providers: [{ provide: AuditDashboardService, useValue: service }],
    }).compile();

    controller = moduleRef.get(AuditDashboardController);
  });

  it('GET /bids/:id/audit returns the detail DTO', async () => {
    const detail = await controller.getBidAudit(
      '11111111-1111-1111-1111-111111111111',
    );
    expect(detail).toEqual(SAMPLE_DETAIL);
  });

  it('GET /dashboard/audit passes through query params', async () => {
    await controller.getSummary(
      '2026-04-01',
      '2026-04-30',
      'bid_manager',
      'WON',
      'M',
      'Acme',
      '0',
      '25',
    );
    expect(service.getSummary).toHaveBeenCalledWith(
      expect.objectContaining({
        from: '2026-04-01',
        to: '2026-04-30',
        role: 'bid_manager',
        status: 'WON',
        profile: 'M',
        client: 'Acme',
        page: 0,
        limit: 25,
      }),
    );
  });

  it('GET /dashboard/audit defaults to the last 30 days when from/to omitted', async () => {
    await controller.getSummary();
    expect(service.getSummary).toHaveBeenCalledWith(
      expect.objectContaining({
        from: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
        to: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      }),
    );
  });

  it('rejects malformed dates with 400', async () => {
    await expect(controller.getSummary('yesterday', '2026-04-30')).rejects.toBeInstanceOf(
      BadRequestException,
    );
  });

  it('GET /dashboard/audit.csv returns the serialised string', async () => {
    const csv = await controller.exportCsv('2026-04-01', '2026-04-30');
    expect(typeof csv).toBe('string');
    expect(csv.startsWith('date,bid_count,cost_usd')).toBe(true);
    expect(service.getSummary).toHaveBeenCalled();
    expect(service.summaryToCsv).toHaveBeenCalledWith(SAMPLE_SUMMARY);
  });

  it('GET /dashboard/costs normalises groupBy to agent when invalid', async () => {
    await controller.getCosts('2026-04-01', '2026-04-30', 'gibberish');
    expect(service.getCosts).toHaveBeenCalledWith(
      expect.objectContaining({ groupBy: 'agent' }),
    );
  });

  it('GET /dashboard/costs keeps a valid groupBy through', async () => {
    await controller.getCosts('2026-04-01', '2026-04-30', 'bid');
    expect(service.getCosts).toHaveBeenCalledWith(
      expect.objectContaining({ groupBy: 'bid' }),
    );
  });
});
