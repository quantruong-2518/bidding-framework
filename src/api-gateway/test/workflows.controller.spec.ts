import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { Test, type TestingModule } from '@nestjs/testing';
import { of } from 'rxjs';
import type { AxiosResponse } from 'axios';
import { AclService } from '../src/acl/acl.service';
import { BidsService } from '../src/bids/bids.service';
import { BidProfile, BidStatus, type Bid } from '../src/bids/bid.entity';
import { WorkflowsController } from '../src/workflows/workflows.controller';
import { WorkflowsService } from '../src/workflows/workflows.service';
import type { TriageSignalDto } from '../src/workflows/triage-signal.dto';
import {
  ReviewCommentSeverity,
  ReviewSignalDto,
  ReviewTargetState,
  ReviewVerdict,
  ReviewerRole,
} from '../src/workflows/review-signal.dto';
import type { AuthenticatedUser } from '../src/auth/current-user.decorator';

const adminUser: AuthenticatedUser = {
  sub: 'kc-admin',
  username: 'admin',
  email: 'a@b.c',
  roles: ['admin'],
};

describe('WorkflowsController', () => {
  let controller: WorkflowsController;
  let http: { post: jest.Mock; get: jest.Mock };
  let bidsService: { findOne: jest.Mock; attachWorkflow: jest.Mock };
  let aclService: { assertVisible: jest.Mock };

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
      findOne: jest.fn().mockResolvedValue(baseBid),
      attachWorkflow: jest.fn().mockResolvedValue({ ...baseBid, workflowId: 'wf-1' }),
    };
    aclService = {
      // Admin is the default user in these specs → always visible.
      assertVisible: jest.fn(),
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
        { provide: AclService, useValue: aclService },
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
    bidsService.findOne.mockResolvedValue({ ...baseBid, workflowId: 'wf-42' });
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
    bidsService.findOne.mockResolvedValue({ ...baseBid, workflowId: 'wf-42' });
    http.get.mockReturnValue(of(okResponse({ workflow_id: 'wf-42', status: 'RUNNING', state: 'S1' })));
    const status = (await controller.status(baseBid.id, adminUser)) as { state: string };
    expect(http.get).toHaveBeenCalledWith(
      'http://ai:8001/workflows/bid/wf-42',
      expect.any(Object),
    );
    expect(status.state).toBe('S1');
  });

  it('GET status forwards caller roles via x-user-roles header', async () => {
    bidsService.findOne.mockResolvedValue({ ...baseBid, workflowId: 'wf-42' });
    http.get.mockReturnValue(of(okResponse({ workflow_id: 'wf-42', state: 'S2' })));
    const baUser: AuthenticatedUser = {
      sub: 'kc-ba',
      username: 'bob',
      email: 'b@a.c',
      roles: ['ba', 'qc'],
    };
    await controller.status(baseBid.id, baUser);
    expect(http.get).toHaveBeenCalledWith(
      'http://ai:8001/workflows/bid/wf-42',
      expect.objectContaining({
        headers: expect.objectContaining({ 'x-user-roles': 'ba,qc' }),
      }),
    );
  });

  it('GET artifacts/:type rejects with 403 when role is not in ACL', async () => {
    const baUser: AuthenticatedUser = {
      sub: 'kc-ba',
      username: 'bob',
      email: 'b@a.c',
      roles: ['ba'],
    };
    aclService.assertVisible.mockImplementation(() => {
      throw new (require('@nestjs/common').ForbiddenException)(
        "Role(s) [ba] cannot access artifact 'pricing'.",
      );
    });
    await expect(
      controller.artifact(baseBid.id, 'pricing', baUser),
    ).rejects.toThrow(/cannot access artifact 'pricing'/);
    expect(http.get).not.toHaveBeenCalled();
  });

  it('GET artifacts/:type returns the named artifact', async () => {
    bidsService.findOne.mockResolvedValue({ ...baseBid, workflowId: 'wf-42' });
    const statusPayload = {
      workflow_id: 'wf-42',
      status: 'COMPLETED',
      current_state: 'S11_DONE',
      wbs: { bid_id: baseBid.id, items: [], total_effort_md: 205, timeline_weeks: 10, critical_path: [] },
    };
    http.get.mockReturnValue(of(okResponse(statusPayload)));
    const artifact = (await controller.artifact(baseBid.id, 'wbs', adminUser)) as {
      total_effort_md: number;
    };
    expect(artifact.total_effort_md).toBe(205);
  });

  it('GET artifacts/:type rejects unknown keys with 400', async () => {
    await expect(controller.artifact(baseBid.id, 'nope', adminUser)).rejects.toThrow(
      /Unknown artifact type 'nope'/,
    );
  });

  it('GET artifacts/:type returns 404 when artifact is null (not yet produced)', async () => {
    bidsService.findOne.mockResolvedValue({ ...baseBid, workflowId: 'wf-42' });
    const statusPayload = {
      workflow_id: 'wf-42',
      status: 'RUNNING',
      current_state: 'S2_DONE',
      wbs: null,
    };
    http.get.mockReturnValue(of(okResponse(statusPayload)));
    await expect(controller.artifact(baseBid.id, 'wbs', adminUser)).rejects.toThrow(
      /has not been produced yet/,
    );
  });

  // --- Phase 2.4 S9 review-signal routing ---------------------------------

  const reviewDto: ReviewSignalDto = {
    verdict: ReviewVerdict.CHANGES_REQUESTED,
    reviewer: 'qc-anna',
    reviewerRole: ReviewerRole.QC,
    comments: [
      {
        section: 'Solution',
        severity: ReviewCommentSeverity.MAJOR,
        message: 'Rework the HLD',
        targetState: ReviewTargetState.S5,
      },
    ],
    notes: 'needs more depth',
  };

  it('POST review-signal forwards snake_case body when workflow is at S9', async () => {
    bidsService.findOne.mockResolvedValue({ ...baseBid, workflowId: 'wf-42' });
    // Status check (guard) + actual review-signal POST.
    http.get.mockReturnValueOnce(
      of(okResponse({ workflow_id: 'wf-42', current_state: 'S9' })),
    );
    http.post.mockReturnValue(of(okResponse({ status: 'accepted' })));

    await controller.review(baseBid.id, reviewDto, adminUser);

    expect(http.post).toHaveBeenCalledWith(
      'http://ai:8001/workflows/bid/wf-42/review-signal',
      {
        verdict: 'CHANGES_REQUESTED',
        reviewer: 'qc-anna',
        reviewer_role: 'qc',
        comments: [
          {
            section: 'Solution',
            severity: 'MAJOR',
            message: 'Rework the HLD',
            target_state: 'S5',
          },
        ],
        notes: 'needs more depth',
      },
      expect.any(Object),
    );
  });

  it('POST review-signal returns 409 when workflow has advanced past S9', async () => {
    bidsService.findOne.mockResolvedValue({ ...baseBid, workflowId: 'wf-42' });
    http.get.mockReturnValueOnce(
      of(okResponse({ workflow_id: 'wf-42', current_state: 'S11_DONE' })),
    );
    await expect(controller.review(baseBid.id, reviewDto, adminUser)).rejects.toThrow(
      /S9 review gate already resolved/,
    );
    expect(http.post).not.toHaveBeenCalled();
  });

  it('POST review-signal bubbles ai-service 404 as NotFoundException', async () => {
    bidsService.findOne.mockResolvedValue({ ...baseBid, workflowId: 'wf-42' });
    http.get.mockReturnValueOnce(
      of(okResponse({ workflow_id: 'wf-42', current_state: 'S9' })),
    );
    const upstreamErr = Object.assign(new Error('not found'), {
      response: { status: 404, data: { detail: 'workflow gone' } },
    });
    http.post.mockReturnValue(
      // rxjs throwError factory via synchronous throw inside firstValueFrom.
      new (require('rxjs').Observable)((sub: { error: (e: unknown) => void }) =>
        sub.error(upstreamErr),
      ),
    );
    await expect(controller.review(baseBid.id, reviewDto, adminUser)).rejects.toThrow(
      /workflow gone/,
    );
  });
});
