import { Test, type TestingModule } from '@nestjs/testing';
import { TypeOrmModule, getRepositoryToken } from '@nestjs/typeorm';
import { NotFoundException } from '@nestjs/common';
import { Repository } from 'typeorm';
import { BidsService } from '../src/bids/bids.service';
import { Bid, BidProfile, BidStatus } from '../src/bids/bid.entity';
import { RedisService } from '../src/redis/redis.service';

describe('BidsService (persistence via in-memory sqlite)', () => {
  let service: BidsService;
  let repo: Repository<Bid>;
  let redis: { publishStream: jest.Mock; deadLetter: jest.Mock };
  let moduleRef: TestingModule;

  beforeEach(async () => {
    redis = {
      publishStream: jest.fn().mockResolvedValue('1-0'),
      deadLetter: jest.fn().mockResolvedValue(undefined),
    };

    moduleRef = await Test.createTestingModule({
      imports: [
        TypeOrmModule.forRoot({
          type: 'better-sqlite3',
          database: ':memory:',
          entities: [Bid],
          synchronize: true,
          dropSchema: true,
        }),
        TypeOrmModule.forFeature([Bid]),
      ],
      providers: [
        BidsService,
        { provide: RedisService, useValue: redis },
      ],
    }).compile();

    service = moduleRef.get(BidsService);
    repo = moduleRef.get(getRepositoryToken(Bid));
  });

  afterEach(async () => {
    await moduleRef.close();
  });

  const dto = {
    clientName: 'ACME',
    industry: 'banking',
    region: 'APAC',
    deadline: '2026-06-01',
    scopeSummary: 'core banking modernization',
    technologyKeywords: ['microservices', 'kafka'],
    estimatedProfile: BidProfile.L,
  };

  it('create() persists a row with defaults + publishes to Redis stream', async () => {
    const bid = await service.create(dto, 'alice');
    expect(bid.id).toMatch(/^[0-9a-f-]{36}$/);
    expect(bid.status).toBe(BidStatus.DRAFT);
    expect(bid.workflowId).toBeNull();
    expect(bid.technologyKeywords).toEqual(['microservices', 'kafka']);

    const fromDb = await repo.findOneByOrFail({ id: bid.id });
    expect(fromDb.clientName).toBe('ACME');
    expect(fromDb.estimatedProfile).toBe(BidProfile.L);

    expect(redis.publishStream).toHaveBeenCalledWith(
      'bid.events',
      expect.objectContaining({
        event: 'bid.created',
        bidId: bid.id,
        createdBy: 'alice',
      }),
    );
  });

  it('create() defaults estimatedProfile to M when DTO omits it', async () => {
    const { estimatedProfile, ...dtoNoProfile } = dto;
    void estimatedProfile;
    const bid = await service.create(dtoNoProfile as typeof dto, undefined);
    expect(bid.estimatedProfile).toBe(BidProfile.M);
  });

  it('findOne() throws NotFoundException for a missing id', async () => {
    await expect(
      service.findOne('00000000-0000-0000-0000-000000000999'),
    ).rejects.toBeInstanceOf(NotFoundException);
  });

  it('findAll() orders by createdAt DESC', async () => {
    const a = await service.create({ ...dto, clientName: 'A' }, 'u');
    // Ensure the timestamps differ by >=1 ms so ordering is deterministic.
    await new Promise((r) => setTimeout(r, 5));
    const b = await service.create({ ...dto, clientName: 'B' }, 'u');
    const list = await service.findAll();
    expect(list.map((x) => x.id)).toEqual([b.id, a.id]);
  });

  it('attachWorkflow() persists workflowId + flips status to IN_PROGRESS', async () => {
    const bid = await service.create(dto, 'alice');
    const updated = await service.attachWorkflow(bid.id, 'wf-abc');
    expect(updated.workflowId).toBe('wf-abc');
    expect(updated.status).toBe(BidStatus.IN_PROGRESS);

    const fromDb = await repo.findOneByOrFail({ id: bid.id });
    expect(fromDb.workflowId).toBe('wf-abc');
  });

  it('findByWorkflowId() returns the matching bid or null', async () => {
    const bid = await service.create(dto, 'alice');
    await service.attachWorkflow(bid.id, 'wf-xyz');
    await expect(service.findByWorkflowId('wf-xyz')).resolves.toMatchObject({
      id: bid.id,
    });
    await expect(service.findByWorkflowId('wf-nope')).resolves.toBeNull();
  });

  it('update() mutates allowed fields + bumps updatedAt', async () => {
    const bid = await service.create(dto, 'alice');
    const original = bid.updatedAt;
    await new Promise((r) => setTimeout(r, 5));
    const updated = await service.update(bid.id, { status: BidStatus.TRIAGED });
    expect(updated.status).toBe(BidStatus.TRIAGED);
    expect(updated.updatedAt).not.toBe(original);
  });

  it('remove() deletes the row', async () => {
    const bid = await service.create(dto, 'alice');
    await service.remove(bid.id);
    await expect(service.findOne(bid.id)).rejects.toBeInstanceOf(
      NotFoundException,
    );
  });

  it('remove() throws NotFoundException for a missing id', async () => {
    await expect(
      service.remove('00000000-0000-0000-0000-000000000999'),
    ).rejects.toBeInstanceOf(NotFoundException);
  });

  it('redis publish failures do not abort create()', async () => {
    redis.publishStream.mockRejectedValueOnce(new Error('network'));
    const bid = await service.create(dto, 'alice');
    expect(bid.id).toBeDefined();
    const fromDb = await repo.findOneByOrFail({ id: bid.id });
    expect(fromDb).toBeTruthy();
  });

  it('routes failed stream publishes to the DLQ with full payload + error', async () => {
    const cause = new Error('xadd MAXLEN reject');
    redis.publishStream.mockRejectedValueOnce(cause);
    const bid = await service.create(dto, 'alice');
    expect(redis.deadLetter).toHaveBeenCalledTimes(1);
    expect(redis.deadLetter).toHaveBeenCalledWith(
      'bid.events',
      expect.objectContaining({
        event: 'bid.created',
        bidId: bid.id,
        createdBy: 'alice',
      }),
      cause,
    );
  });

  it('still returns the saved bid when both stream + DLQ fail', async () => {
    redis.publishStream.mockRejectedValueOnce(new Error('stream down'));
    redis.deadLetter.mockRejectedValueOnce(new Error('dlq down'));
    const bid = await service.create(dto, 'alice');
    expect(bid.id).toBeDefined();
    const fromDb = await repo.findOneByOrFail({ id: bid.id });
    expect(fromDb).toBeTruthy();
  });
});
