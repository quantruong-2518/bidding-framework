import { ConfigService } from '@nestjs/config';
import {
  ConflictException,
  InternalServerErrorException,
  NotFoundException,
} from '@nestjs/common';
import { Test, type TestingModule } from '@nestjs/testing';
import {
  TypeOrmModule,
  getDataSourceToken,
  getRepositoryToken,
} from '@nestjs/typeorm';
import { DataSource, Repository } from 'typeorm';
import { Bid, BidProfile } from '../src/bids/bid.entity';
import { BidsService } from '../src/bids/bids.service';
import { AiServiceClient } from '../src/gateway/ai-service.client';
import { ObjectStoreService } from '../src/object-store/object-store.service';
import { MaterializeService } from '../src/parse-sessions/materialize.service';
import { ParseSession } from '../src/parse-sessions/parse-session.entity';
import { ParseSessionsService } from '../src/parse-sessions/parse-sessions.service';
import { RedisService } from '../src/redis/redis.service';
import { WorkflowsService } from '../src/workflows/workflows.service';

const SID = '11111111-1111-1111-1111-111111111111';
const TENANT = 'acme';
const USER = 'alice';

describe('MaterializeService.confirmAndStart', () => {
  let service: MaterializeService;
  let sessionRepo: Repository<ParseSession>;
  let bidRepo: Repository<Bid>;
  let dataSource: DataSource;
  let moduleRef: TestingModule;

  let aiClient: { materialize: jest.Mock };
  let objectStore: { renamePrefix: jest.Mock; deletePrefix: jest.Mock };
  let workflows: { trigger: jest.Mock };
  let redis: { publishStream: jest.Mock; deadLetter: jest.Mock };

  beforeEach(async () => {
    aiClient = {
      materialize: jest.fn().mockResolvedValue({
        bid_id: 'bid-x',
        vault_path: '/vault/kb-vault/bids/bid-x/',
        atoms_written: 5,
        trace_id: 'trace-1',
      }),
    };
    objectStore = {
      renamePrefix: jest.fn().mockResolvedValue(2),
      deletePrefix: jest.fn().mockResolvedValue(0),
    };
    workflows = {
      trigger: jest.fn().mockResolvedValue({
        bid: { id: 'placeholder' },
        workflow: { workflow_id: 'wf-99' },
      }),
    };
    redis = {
      publishStream: jest.fn().mockResolvedValue('1-0'),
      deadLetter: jest.fn().mockResolvedValue(undefined),
    };

    moduleRef = await Test.createTestingModule({
      imports: [
        TypeOrmModule.forRoot({
          type: 'better-sqlite3',
          database: ':memory:',
          entities: [ParseSession, Bid],
          synchronize: true,
          dropSchema: true,
        }),
        TypeOrmModule.forFeature([ParseSession, Bid]),
      ],
      providers: [
        ParseSessionsService,
        BidsService,
        MaterializeService,
        { provide: ObjectStoreService, useValue: objectStore },
        { provide: AiServiceClient, useValue: aiClient },
        { provide: WorkflowsService, useValue: workflows },
        { provide: RedisService, useValue: redis },
        {
          provide: ConfigService,
          useValue: { get: () => '/vault/kb-vault' },
        },
      ],
    }).compile();

    service = moduleRef.get(MaterializeService);
    sessionRepo = moduleRef.get(getRepositoryToken(ParseSession));
    bidRepo = moduleRef.get(getRepositoryToken(Bid));
    dataSource = moduleRef.get(getDataSourceToken());
  });

  afterEach(async () => {
    await moduleRef.close();
  });

  async function seedReadySession(
    overrides: Partial<ParseSession> = {},
  ): Promise<ParseSession> {
    const entity = sessionRepo.create({
      id: SID,
      tenantId: TENANT,
      userId: USER,
      status: 'READY',
      suggestedBidCard: {
        client_name: 'ACME',
        industry: 'banking',
        region: 'APAC',
        deadline: '2026-06-01',
        scope_summary: 'core banking',
        technology_keywords: ['kafka'],
        estimated_profile: 'M',
        language: 'en',
      },
      atoms: [
        { frontmatter: { id: 'REQ-F-001' }, body_md: 'first' },
        { frontmatter: { id: 'REQ-F-002' }, body_md: 'second' },
      ],
      anchorMd: '# anchor',
      summaryMd: '# summary',
      manifest: { files: [] },
      conflicts: [],
      openQuestions: [],
      parseError: null,
      expiresAt: '2099-12-31T00:00:00.000Z',
      confirmedBidId: null,
      confirmedAt: null,
      confirmedBy: null,
      ...overrides,
    });
    return sessionRepo.save(entity);
  }

  it('happy path commits bid + flips session to CONFIRMED + starts workflow', async () => {
    await seedReadySession();
    const result = await service.confirmAndStart(SID, {}, USER);

    expect(result.bid_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(result.workflow_id).toBe('wf-99');
    expect(result.vault_path).toBe('/vault/kb-vault/bids/bid-x/');
    expect(result.trace_id).toBe('trace-1');

    const fresh = await sessionRepo.findOneByOrFail({ id: SID });
    expect(fresh.status).toBe('CONFIRMED');
    expect(fresh.confirmedBidId).toBe(result.bid_id);
    expect(fresh.confirmedBy).toBe(USER);
    const persistedBid = await bidRepo.findOneByOrFail({ id: result.bid_id });
    expect(persistedBid.clientName).toBe('ACME');

    expect(objectStore.renamePrefix).toHaveBeenCalledWith(
      expect.any(String),
      `parse_sessions/${SID}/`,
      `bids/${result.bid_id}/`,
    );
    expect(aiClient.materialize).toHaveBeenCalled();
    expect(workflows.trigger).toHaveBeenCalledWith(result.bid_id);
  });

  it('applies user overrides + atom_rejects to ai-service payload', async () => {
    await seedReadySession();
    await service.confirmAndStart(
      SID,
      {
        client_name: 'NewClient',
        profile_override: BidProfile.L,
        atom_rejects: ['REQ-F-002'],
        atom_edits: [{ id: 'REQ-F-001', patch: { priority: 'MUST' } }],
      },
      USER,
    );
    expect(aiClient.materialize).toHaveBeenCalledWith(
      SID,
      expect.objectContaining({
        parse_session_payload: expect.objectContaining({
          atoms: expect.arrayContaining([
            expect.objectContaining({
              frontmatter: expect.objectContaining({
                id: 'REQ-F-001',
                priority: 'MUST',
              }),
            }),
          ]),
          suggested_bid_card: expect.objectContaining({
            client_name: 'NewClient',
            estimated_profile: 'L',
          }),
        }),
      }),
    );
    const sentAtoms = aiClient.materialize.mock.calls[0][1].parse_session_payload
      .atoms;
    expect(sentAtoms).toHaveLength(1);
    expect(sentAtoms[0].frontmatter.id).toBe('REQ-F-001');
  });

  it('rolls back when MinIO renamePrefix fails — no bid persisted', async () => {
    await seedReadySession();
    objectStore.renamePrefix.mockRejectedValueOnce(new Error('s3 timeout'));
    await expect(service.confirmAndStart(SID, {}, USER)).rejects.toBeInstanceOf(
      InternalServerErrorException,
    );
    const bidsAfter = await bidRepo.count();
    expect(bidsAfter).toBe(0);
    const fresh = await sessionRepo.findOneByOrFail({ id: SID });
    expect(fresh.status).toBe('READY');
    expect(workflows.trigger).not.toHaveBeenCalled();
  });

  it('rolls back when ai-service materialize fails — no bid persisted', async () => {
    await seedReadySession();
    aiClient.materialize.mockRejectedValueOnce(new Error('vault disk full'));
    await expect(service.confirmAndStart(SID, {}, USER)).rejects.toBeInstanceOf(
      InternalServerErrorException,
    );
    const bidsAfter = await bidRepo.count();
    expect(bidsAfter).toBe(0);
    const fresh = await sessionRepo.findOneByOrFail({ id: SID });
    expect(fresh.status).toBe('READY');
    expect(workflows.trigger).not.toHaveBeenCalled();
  });

  it('rejects re-confirm of an already-CONFIRMED session', async () => {
    await seedReadySession({
      status: 'CONFIRMED',
      confirmedBidId: 'bid-already',
    });
    await expect(service.confirmAndStart(SID, {}, USER)).rejects.toBeInstanceOf(
      ConflictException,
    );
    expect(objectStore.renamePrefix).not.toHaveBeenCalled();
  });

  it('rejects confirm when session is still PARSING', async () => {
    await seedReadySession({ status: 'PARSING' });
    await expect(service.confirmAndStart(SID, {}, USER)).rejects.toBeInstanceOf(
      ConflictException,
    );
  });

  it('returns 404 when the session id does not exist', async () => {
    await expect(service.confirmAndStart(SID, {}, USER)).rejects.toBeInstanceOf(
      NotFoundException,
    );
  });

  it('post-commit Temporal failure surfaces 5xx but bid + session stay committed', async () => {
    await seedReadySession();
    workflows.trigger.mockRejectedValueOnce(new Error('temporal unreachable'));
    await expect(service.confirmAndStart(SID, {}, USER)).rejects.toBeInstanceOf(
      InternalServerErrorException,
    );
    // Bid was committed before workflow start — the row stays.
    const bidsAfter = await bidRepo.count();
    expect(bidsAfter).toBe(1);
    const fresh = await sessionRepo.findOneByOrFail({ id: SID });
    expect(fresh.status).toBe('CONFIRMED');
  });

  // Touch the unused datasource binding so jest doesn't flag the import.
  it('exposes the test DataSource', () => {
    expect(dataSource.isInitialized).toBe(true);
  });
});
