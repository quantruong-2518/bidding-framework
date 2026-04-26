import { Test, type TestingModule } from '@nestjs/testing';
import { TypeOrmModule } from '@nestjs/typeorm';
import { NotFoundException } from '@nestjs/common';
import { Repository } from 'typeorm';
import { getRepositoryToken } from '@nestjs/typeorm';
import { BidStateController } from '../src/bid-state-projection/bid-state.controller';
import { BidStateProjection } from '../src/bid-state-projection/bid-state-projection.entity';
import { BidStateTransition } from '../src/bid-state-projection/bid-state-transition.entity';
import { BidStateService } from '../src/bid-state-projection/bid-state.service';

const BID_A = '11111111-1111-1111-1111-111111111111';
const BID_MISSING = '00000000-0000-0000-0000-000000000999';

describe('BidStateController', () => {
  let controller: BidStateController;
  let repo: Repository<BidStateProjection>;
  let moduleRef: TestingModule;

  beforeEach(async () => {
    moduleRef = await Test.createTestingModule({
      imports: [
        TypeOrmModule.forRoot({
          type: 'better-sqlite3',
          database: ':memory:',
          entities: [BidStateTransition, BidStateProjection],
          synchronize: true,
          dropSchema: true,
        }),
        TypeOrmModule.forFeature([BidStateProjection]),
      ],
      controllers: [BidStateController],
      providers: [BidStateService],
    }).compile();

    controller = moduleRef.get(BidStateController);
    repo = moduleRef.get(getRepositoryToken(BidStateProjection));
  });

  afterEach(async () => {
    await moduleRef.close();
  });

  it('returns the projection view for an existing bid', async () => {
    await repo.save(
      repo.create({
        bidId: BID_A,
        workflowId: 'wf-A',
        tenantId: 'acme',
        currentState: 'S5_DONE',
        profile: 'L',
        clientName: 'ACME',
        industry: 'banking',
        lastTransitionSeq: 7,
        lastTransitionAt: '2026-04-26T13:00:00+00:00',
        artifactsDone: {
          bid_card: '2026-04-26T12:00:00+00:00',
          hld: '2026-04-26T13:00:00+00:00',
        },
        isTerminal: false,
        outcome: null,
        totalLlmCostUsd: 0.0234,
      }),
    );

    const view = await controller.getState(BID_A);
    expect(view.bidId).toBe(BID_A);
    expect(view.currentState).toBe('S5_DONE');
    expect(view.profile).toBe('L');
    expect(view.lastTransitionSeq).toBe(7);
    expect(view.isTerminal).toBe(false);
    expect(view.totalLlmCostUsd).toBeCloseTo(0.0234, 6);
    expect(view.artifactsDone).toMatchObject({
      bid_card: expect.any(String),
      hld: expect.any(String),
    });
  });

  it('throws 404 when no projection exists for the bid id', async () => {
    await expect(controller.getState(BID_MISSING)).rejects.toBeInstanceOf(
      NotFoundException,
    );
  });

  it('view shape preserves terminal outcome + flag', async () => {
    await repo.save(
      repo.create({
        bidId: BID_A,
        workflowId: 'wf-A',
        tenantId: 'acme',
        currentState: 'S11_DONE',
        profile: 'M',
        clientName: 'ACME',
        industry: 'banking',
        lastTransitionSeq: 16,
        lastTransitionAt: '2026-04-26T18:00:00+00:00',
        artifactsDone: {},
        isTerminal: true,
        outcome: 'COMPLETED',
        totalLlmCostUsd: 0.137,
      }),
    );

    const view = await controller.getState(BID_A);
    expect(view.isTerminal).toBe(true);
    expect(view.outcome).toBe('COMPLETED');
    expect(view.currentState).toBe('S11_DONE');
  });
});
