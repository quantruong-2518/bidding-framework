import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { Test, type TestingModule } from '@nestjs/testing';
import { of } from 'rxjs';
import type { AxiosResponse } from 'axios';
import { BidsService } from '../src/bids/bids.service';
import { BidProfile, BidStatus, type Bid } from '../src/bids/bid.entity';
import { WorkflowsController } from '../src/workflows/workflows.controller';
import { WorkflowsService } from '../src/workflows/workflows.service';
import type { TriageSignalDto } from '../src/workflows/triage-signal.dto';

describe('WorkflowsController', () => {
  let controller: WorkflowsController;
  let http: { post: jest.Mock; get: jest.Mock };
  let bidsService: { findOne: jest.Mock; attachWorkflow: jest.Mock };

  const baseBid: Bid = {
    id: '11111111-1111-1111-1111-111111111111',
    clientName: 'ACME',
    industry: 'retail',
    region: 'NA',
    deadline: '2026-07-01',
    scopeSummary: 'ecommerce revamp',
    technologyKeywords: ['nextjs'],
    estimatedProfile: BidProfile.M,
    status: BidStatus.DRAFT,
    workflowId: null,
    createdAt: '2026-04-01T00:00:00.000Z',
    updatedAt: '2026-04-01T00:00:00.000Z',
  };

  const okResponse = <T>(data: T): AxiosResponse<T> => ({
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    config: {} as any,
  });

  beforeEach(async () => {
    http = { post: jest.fn(), get: jest.fn() };
    bidsService = {
      findOne: jest.fn().mockReturnValue(baseBid),
      attachWorkflow: jest.fn().mockReturnValue({ ...baseBid, workflowId: 'wf-1' }),
    };

    const moduleRef: TestingModule = await Test.createTestingModule({
      controllers: [WorkflowsController],
      providers: [
        WorkflowsService,
        { provide: HttpService, useValue: http },
        {
          provide: ConfigService,
          useValue: { get: (k: string) => (k === 'AI_SERVICE_URL' ? 'http://ai:8001' : undefined) },
        },
        { provide: BidsService, useValue: bidsService },
      ],
    }).compile();

    controller = moduleRef.get(WorkflowsController);
  });

  it('POST /bids/:id/workflow proxies to ai-service start and persists workflowId', async () => {
    http.post.mockReturnValue(of(okResponse({ workflow_id: 'wf-1', status: 'RUNNING' })));
    const result = (await controller.trigger(baseBid.id)) as {
      bid: Bid;
      workflow: { workflow_id: string };
    };
    expect(http.post).toHaveBeenCalledWith(
      'http://ai:8001/workflows/bid/start-from-card',
      expect.objectContaining({
        bid_id: baseBid.id,
        client_name: 'ACME',
        requirements_raw: [],
      }),
      expect.any(Object),
    );
    expect(bidsService.attachWorkflow).toHaveBeenCalledWith(baseBid.id, 'wf-1');
    expect(result.workflow.workflow_id).toBe('wf-1');
  });

  it('POST triage-signal proxies to the correct workflow url', async () => {
    bidsService.findOne.mockReturnValue({ ...baseBid, workflowId: 'wf-42' });
    http.post.mockReturnValue(of(okResponse({ status: 'signalled' })));
    const dto: TriageSignalDto = {
      approved: true,
      reviewer: 'alice',
      notes: 'go',
      bidProfileOverride: BidProfile.L,
    };
    await controller.signal(baseBid.id, dto);
    expect(http.post).toHaveBeenCalledWith(
      'http://ai:8001/workflows/bid/wf-42/triage-signal',
      {
        approved: true,
        reviewer: 'alice',
        notes: 'go',
        bid_profile_override: BidProfile.L,
      },
      expect.any(Object),
    );
  });

  it('GET status proxies and returns upstream payload', async () => {
    bidsService.findOne.mockReturnValue({ ...baseBid, workflowId: 'wf-42' });
    http.get.mockReturnValue(of(okResponse({ workflow_id: 'wf-42', status: 'RUNNING', state: 'S1' })));
    const status = (await controller.status(baseBid.id)) as { state: string };
    expect(http.get).toHaveBeenCalledWith(
      'http://ai:8001/workflows/bid/wf-42',
      expect.any(Object),
    );
    expect(status.state).toBe('S1');
  });
});
