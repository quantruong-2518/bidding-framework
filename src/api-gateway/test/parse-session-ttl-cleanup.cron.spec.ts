import { Test, type TestingModule } from '@nestjs/testing';
import { TypeOrmModule, getRepositoryToken } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { ObjectStoreService } from '../src/object-store/object-store.service';
import { ParseSession } from '../src/parse-sessions/parse-session.entity';
import { ParseSessionsService } from '../src/parse-sessions/parse-sessions.service';
import { ParseSessionTtlCleanupCron } from '../src/parse-sessions/ttl-cleanup.cron';

describe('ParseSessionTtlCleanupCron.sweepOnce', () => {
  let cron: ParseSessionTtlCleanupCron;
  let service: ParseSessionsService;
  let repo: Repository<ParseSession>;
  let objectStore: jest.Mocked<ObjectStoreService>;
  let moduleRef: TestingModule;

  beforeEach(async () => {
    objectStore = {
      deletePrefix: jest.fn().mockResolvedValue(0),
      renamePrefix: jest.fn().mockResolvedValue(0),
      putObject: jest.fn(),
      getObject: jest.fn(),
      ensureBucket: jest.fn(),
      presignedGetUrl: jest.fn(),
      isStub: true,
    } as unknown as jest.Mocked<ObjectStoreService>;

    moduleRef = await Test.createTestingModule({
      imports: [
        TypeOrmModule.forRoot({
          type: 'better-sqlite3',
          database: ':memory:',
          entities: [ParseSession],
          synchronize: true,
          dropSchema: true,
        }),
        TypeOrmModule.forFeature([ParseSession]),
      ],
      providers: [
        ParseSessionsService,
        ParseSessionTtlCleanupCron,
        { provide: ObjectStoreService, useValue: objectStore },
      ],
    }).compile();

    cron = moduleRef.get(ParseSessionTtlCleanupCron);
    service = moduleRef.get(ParseSessionsService);
    repo = moduleRef.get(getRepositoryToken(ParseSession));
  });

  afterEach(async () => {
    await moduleRef.close();
  });

  it('returns zero counters when nothing has expired', async () => {
    await service.createSession('acme', 'alice');
    const result = await cron.sweepOnce();
    expect(result).toEqual({ scanned: 0, abandoned: 0, errors: 0 });
    expect(objectStore.deletePrefix).not.toHaveBeenCalled();
  });

  it('flips expired PARSING/READY sessions to ABANDONED + drops MinIO prefix', async () => {
    const a = await service.createSession('acme', 'alice');
    const b = await service.createSession('acme', 'alice');
    a.expiresAt = '2020-01-01T00:00:00.000Z';
    b.expiresAt = '2020-01-01T00:00:00.000Z';
    b.status = 'READY';
    await repo.save([a, b]);

    objectStore.deletePrefix
      .mockResolvedValueOnce(1)
      .mockResolvedValueOnce(2);

    const result = await cron.sweepOnce();
    expect(result.scanned).toBe(2);
    expect(result.abandoned).toBe(2);
    expect(result.errors).toBe(0);

    const fresh = await repo.find();
    for (const session of fresh) {
      expect(session.status).toBe('ABANDONED');
    }
  });

  it('failure isolation — single bad MinIO prefix does not abort the batch', async () => {
    const a = await service.createSession('acme', 'alice');
    const b = await service.createSession('acme', 'alice');
    a.expiresAt = '2020-01-01T00:00:00.000Z';
    b.expiresAt = '2020-01-01T00:00:00.000Z';
    await repo.save([a, b]);

    // a fails MinIO delete; b succeeds.
    objectStore.deletePrefix
      .mockRejectedValueOnce(new Error('s3 timeout'))
      .mockResolvedValueOnce(0);

    const result = await cron.sweepOnce();
    // Even with the MinIO failure, the row gets marked ABANDONED to stop
    // the cron retrying forever — both sessions count as abandoned.
    expect(result.scanned).toBe(2);
    expect(result.abandoned).toBe(2);
    expect(result.errors).toBe(0);

    const fresh = await repo.find();
    expect(fresh.every((s) => s.status === 'ABANDONED')).toBe(true);
  });

  it('skips terminal statuses even when expires_at is in the past', async () => {
    const a = await service.createSession('acme', 'alice');
    a.expiresAt = '2020-01-01T00:00:00.000Z';
    a.status = 'CONFIRMED';
    a.confirmedBidId = '11111111-1111-1111-1111-111111111111';
    await repo.save(a);

    const result = await cron.sweepOnce();
    expect(result.scanned).toBe(0);
    expect(result.abandoned).toBe(0);
    expect(objectStore.deletePrefix).not.toHaveBeenCalled();
  });
});
