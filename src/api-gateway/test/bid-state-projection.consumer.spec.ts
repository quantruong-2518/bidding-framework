import { Test, type TestingModule } from '@nestjs/testing';
import { TypeOrmModule, getDataSourceToken } from '@nestjs/typeorm';
import { DataSource } from 'typeorm';
import {
  BidStateProjectionConsumer,
  CONSUMER_GROUP,
  STREAM_KEY,
} from '../src/bid-state-projection/bid-state-projection.consumer';
import { BidStateProjection } from '../src/bid-state-projection/bid-state-projection.entity';
import { BidStateTransition } from '../src/bid-state-projection/bid-state-transition.entity';
import { RedisService } from '../src/redis/redis.service';

const BID_A = '11111111-1111-1111-1111-111111111111';

function entry(
  fields: Partial<{
    bid_id: string;
    workflow_id: string;
    transition_seq: string;
    tenant_id: string;
    from_state: string;
    to_state: string;
    profile: string;
    artifact_keys: string;
    occurred_at: string;
    llm_cost_delta: string;
  }>,
  id = '0-0',
): [string, string[]] {
  const merged = {
    bid_id: BID_A,
    workflow_id: 'wf-A',
    transition_seq: '1',
    tenant_id: 'acme',
    from_state: '',
    to_state: 'S0_DONE',
    profile: 'M',
    artifact_keys: '["bid_card"]',
    occurred_at: '2026-04-26T12:00:00+00:00',
    llm_cost_delta: '',
    ...fields,
  };
  const flat: string[] = [];
  for (const [k, v] of Object.entries(merged)) flat.push(k, v);
  return [id, flat];
}

describe('BidStateProjectionConsumer (better-sqlite3)', () => {
  let consumer: BidStateProjectionConsumer;
  let dataSource: DataSource;
  let moduleRef: TestingModule;
  let redisClient: { xack: jest.Mock; xgroup: jest.Mock; xreadgroup: jest.Mock };

  beforeEach(async () => {
    redisClient = {
      xack: jest.fn().mockResolvedValue(1),
      xgroup: jest.fn().mockResolvedValue('OK'),
      xreadgroup: jest.fn().mockResolvedValue(null),
    };

    moduleRef = await Test.createTestingModule({
      imports: [
        TypeOrmModule.forRoot({
          type: 'better-sqlite3',
          database: ':memory:',
          entities: [BidStateTransition, BidStateProjection],
          synchronize: true,
          dropSchema: true,
        }),
        TypeOrmModule.forFeature([BidStateTransition, BidStateProjection]),
      ],
      providers: [
        BidStateProjectionConsumer,
        {
          provide: RedisService,
          useValue: {
            getClient: () => redisClient,
          },
        },
      ],
    }).compile();

    consumer = moduleRef.get(BidStateProjectionConsumer);
    dataSource = moduleRef.get(getDataSourceToken());
  });

  afterEach(async () => {
    await moduleRef.close();
  });

  it('inserts log row + creates projection row on first transition', async () => {
    await consumer.processBatch(redisClient as never, [
      entry({ transition_seq: '1', to_state: 'S0_DONE' }, '1-0'),
    ]);

    const logs = await dataSource
      .getRepository(BidStateTransition)
      .find({ order: { transitionSeq: 'ASC' } });
    expect(logs).toHaveLength(1);
    expect(logs[0].transitionSeq).toBe(1);
    expect(logs[0].toState).toBe('S0_DONE');

    const projections = await dataSource.getRepository(BidStateProjection).find();
    expect(projections).toHaveLength(1);
    expect(projections[0].currentState).toBe('S0_DONE');
    expect(projections[0].lastTransitionSeq).toBe(1);
    expect(projections[0].isTerminal).toBe(false);
    expect(projections[0].artifactsDone).toEqual({
      bid_card: '2026-04-26T12:00:00+00:00',
    });
    expect(redisClient.xack).toHaveBeenCalledWith(STREAM_KEY, CONSUMER_GROUP, '1-0');
  });

  it('is idempotent under XREADGROUP at-least-once redelivery', async () => {
    await consumer.processBatch(redisClient as never, [
      entry({ transition_seq: '1', llm_cost_delta: '0.5' }, '1-0'),
    ]);
    await consumer.processBatch(redisClient as never, [
      entry({ transition_seq: '1', llm_cost_delta: '0.5' }, '1-1'),
    ]);

    const logs = await dataSource.getRepository(BidStateTransition).find();
    expect(logs).toHaveLength(1);
    const proj = await dataSource
      .getRepository(BidStateProjection)
      .findOneByOrFail({ bidId: BID_A });
    expect(Number(proj.totalLlmCostUsd)).toBeCloseTo(0.5, 6);
    expect(redisClient.xack).toHaveBeenCalledTimes(2);
  });

  it('flips is_terminal + sets outcome on a terminal state', async () => {
    await consumer.processBatch(redisClient as never, [
      entry({ transition_seq: '1', to_state: 'S0_DONE' }, '1-0'),
      entry(
        {
          transition_seq: '16',
          from_state: 'S10_DONE',
          to_state: 'S11_DONE',
          artifact_keys: '["retrospective"]',
        },
        '2-0',
      ),
    ]);

    const proj = await dataSource
      .getRepository(BidStateProjection)
      .findOneByOrFail({ bidId: BID_A });
    expect(proj.currentState).toBe('S11_DONE');
    expect(proj.isTerminal).toBe(true);
    expect(proj.outcome).toBe('COMPLETED');
    expect(proj.artifactsDone).toMatchObject({
      bid_card: expect.any(String),
      retrospective: expect.any(String),
    });
  });

  it('rolls up llm_cost_delta across transitions', async () => {
    await consumer.processBatch(redisClient as never, [
      entry({ transition_seq: '1', llm_cost_delta: '0.012345' }, '1-0'),
      entry(
        { transition_seq: '2', to_state: 'S5_DONE', llm_cost_delta: '0.025' },
        '2-0',
      ),
      entry(
        { transition_seq: '3', to_state: 'S6_DONE', llm_cost_delta: '' },
        '3-0',
      ),
    ]);

    const proj = await dataSource
      .getRepository(BidStateProjection)
      .findOneByOrFail({ bidId: BID_A });
    expect(Number(proj.totalLlmCostUsd)).toBeCloseTo(0.037345, 6);
  });

  it('does not roll the projection backward on out-of-order delivery', async () => {
    await consumer.processBatch(redisClient as never, [
      entry(
        { transition_seq: '5', to_state: 'S5_DONE', llm_cost_delta: '0.02' },
        '5-0',
      ),
      // Out-of-order: seq 3 arrives after seq 5. Log row is appended (audit
      // fidelity) but projection.current_state stays S5_DONE.
      entry(
        { transition_seq: '3', to_state: 'S3_DONE', llm_cost_delta: '0.005' },
        '3-late',
      ),
    ]);

    const logs = await dataSource.getRepository(BidStateTransition).find();
    expect(logs).toHaveLength(2);
    const proj = await dataSource
      .getRepository(BidStateProjection)
      .findOneByOrFail({ bidId: BID_A });
    expect(proj.currentState).toBe('S5_DONE');
    expect(proj.lastTransitionSeq).toBe(5);
    // Cost is still summed from BOTH log rows, since each was novel.
    expect(Number(proj.totalLlmCostUsd)).toBeCloseTo(0.025, 6);
  });

  it('skips malformed entries with a warning + still XACKs', async () => {
    const warn = jest.spyOn(consumer['logger'], 'warn').mockImplementation();
    await consumer.processBatch(redisClient as never, [
      // Missing required fields entirely.
      ['bad-1', ['bid_id', '', 'to_state', '']],
    ]);

    expect(warn).toHaveBeenCalled();
    expect(redisClient.xack).toHaveBeenCalledWith(STREAM_KEY, CONSUMER_GROUP, 'bad-1');
    const logs = await dataSource.getRepository(BidStateTransition).find();
    expect(logs).toHaveLength(0);
  });

  it('parseEntry rejects non-numeric transition_seq', () => {
    const parsed = consumer.parseEntry('1-0', [
      'bid_id',
      BID_A,
      'transition_seq',
      'NOT_A_NUMBER',
      'to_state',
      'S0_DONE',
      'profile',
      'M',
    ]);
    expect(parsed).toBeNull();
  });

  it('ensureGroup is a no-op when group already exists (BUSYGROUP)', async () => {
    redisClient.xgroup.mockRejectedValueOnce(
      new Error('BUSYGROUP Consumer Group name already exists'),
    );
    await expect(consumer.ensureGroup()).resolves.toBeUndefined();
  });
});
