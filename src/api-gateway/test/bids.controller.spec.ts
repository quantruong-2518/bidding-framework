import { NotFoundException } from '@nestjs/common';
import { Test, type TestingModule } from '@nestjs/testing';
import { BidsController } from '../src/bids/bids.controller';
import { BidsService } from '../src/bids/bids.service';
import { LangfuseLinkService } from '../src/bids/langfuse-link.service';
import { BidProfile, BidStatus, type Bid } from '../src/bids/bid.entity';
import type { CreateBidDto } from '../src/bids/create-bid.dto';
import type { UpdateBidDto } from '../src/bids/update-bid.dto';
import type { AuthenticatedUser } from '../src/auth/current-user.decorator';

describe('BidsController', () => {
  let controller: BidsController;
  let service: jest.Mocked<BidsService>;
  let langfuseLink: jest.Mocked<LangfuseLinkService>;

  const fixture: Bid = {
    id: '00000000-0000-0000-0000-000000000001',
    clientName: 'ACME',
    industry: 'banking',
    region: 'APAC',
    deadline: '2026-06-01',
    scopeSummary: 'core banking modernization',
    technologyKeywords: ['microservices', 'kafka'],
    estimatedProfile: BidProfile.L,
    status: BidStatus.DRAFT,
    workflowId: null,
    createdAt: '2026-04-01T00:00:00.000Z',
    updatedAt: '2026-04-01T00:00:00.000Z',
  };

  beforeEach(async () => {
    const mock: Partial<jest.Mocked<BidsService>> = {
      create: jest.fn().mockResolvedValue(fixture),
      findAll: jest.fn().mockReturnValue([fixture]),
      findOne: jest.fn().mockReturnValue(fixture),
      update: jest.fn().mockReturnValue(fixture),
      remove: jest.fn(),
    };

    const linkMock: Partial<jest.Mocked<LangfuseLinkService>> = {
      getTraceUrl: jest.fn(),
    };

    const moduleRef: TestingModule = await Test.createTestingModule({
      controllers: [BidsController],
      providers: [
        { provide: BidsService, useValue: mock },
        { provide: LangfuseLinkService, useValue: linkMock },
      ],
    }).compile();

    controller = moduleRef.get(BidsController);
    service = moduleRef.get(BidsService) as jest.Mocked<BidsService>;
    langfuseLink = moduleRef.get(LangfuseLinkService) as jest.Mocked<LangfuseLinkService>;
  });

  it('creates a bid with current user as creator', async () => {
    const dto: CreateBidDto = {
      clientName: 'ACME',
      industry: 'banking',
      region: 'APAC',
      deadline: '2026-06-01',
      scopeSummary: 'core banking modernization',
      technologyKeywords: ['microservices', 'kafka'],
      estimatedProfile: BidProfile.L,
    };
    const user: AuthenticatedUser = {
      sub: 'u-1',
      username: 'alice',
      email: 'a@b.c',
      roles: ['bid_manager'],
    };
    await expect(controller.create(dto, user)).resolves.toEqual(fixture);
    expect(service.create).toHaveBeenCalledWith(dto, 'alice');
  });

  it('lists bids', () => {
    expect(controller.list()).toEqual([fixture]);
  });

  it('fetches a bid by id', () => {
    expect(controller.findOne(fixture.id)).toEqual(fixture);
    expect(service.findOne).toHaveBeenCalledWith(fixture.id);
  });

  it('updates a bid', () => {
    const update: UpdateBidDto = { status: BidStatus.TRIAGED };
    expect(controller.update(fixture.id, update)).toEqual(fixture);
    expect(service.update).toHaveBeenCalledWith(fixture.id, update);
  });

  it('removes a bid', () => {
    controller.remove(fixture.id);
    expect(service.remove).toHaveBeenCalledWith(fixture.id);
  });

  it('returns Langfuse trace URL for a bid', () => {
    langfuseLink.getTraceUrl.mockReturnValue({
      url: `http://localhost:3002/trace/${fixture.id}`,
    });
    expect(controller.getTraceUrl(fixture.id)).toEqual({
      url: `http://localhost:3002/trace/${fixture.id}`,
    });
    expect(langfuseLink.getTraceUrl).toHaveBeenCalledWith(fixture.id);
  });

  it('propagates 404 when Langfuse is not configured', () => {
    langfuseLink.getTraceUrl.mockImplementation(() => {
      throw new NotFoundException('unset');
    });
    expect(() => controller.getTraceUrl(fixture.id)).toThrow(NotFoundException);
  });
});
