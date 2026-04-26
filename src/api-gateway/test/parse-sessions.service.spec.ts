import { ConflictException, NotFoundException } from '@nestjs/common';
import { Test, type TestingModule } from '@nestjs/testing';
import { TypeOrmModule, getRepositoryToken } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { ObjectStoreService } from '../src/object-store/object-store.service';
import { ParseSession } from '../src/parse-sessions/parse-session.entity';
import { ParseSessionsService } from '../src/parse-sessions/parse-sessions.service';

describe('ParseSessionsService', () => {
  let service: ParseSessionsService;
  let repo: Repository<ParseSession>;
  let objectStore: jest.Mocked<ObjectStoreService>;
  let moduleRef: TestingModule;

  beforeEach(async () => {
    objectStore = {
      deletePrefix: jest.fn().mockResolvedValue(0),
      renamePrefix: jest.fn().mockResolvedValue(0),
      putObject: jest.fn().mockResolvedValue(undefined),
      getObject: jest.fn().mockResolvedValue(null),
      ensureBucket: jest.fn().mockResolvedValue(undefined),
      presignedGetUrl: jest.fn().mockResolvedValue('stub://x'),
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
        { provide: ObjectStoreService, useValue: objectStore },
      ],
    }).compile();

    service = moduleRef.get(ParseSessionsService);
    repo = moduleRef.get(getRepositoryToken(ParseSession));
  });

  afterEach(async () => {
    await moduleRef.close();
  });

  it('createSession() persists a row in PARSING status with 7d expiry', async () => {
    const before = Date.now();
    const session = await service.createSession('acme', 'alice');
    expect(session.id).toMatch(/^[0-9a-f-]{36}$/);
    expect(session.status).toBe('PARSING');
    expect(session.tenantId).toBe('acme');
    expect(session.userId).toBe('alice');
    const expiresMs = new Date(session.expiresAt).getTime();
    expect(expiresMs).toBeGreaterThan(before + 6 * 24 * 60 * 60 * 1_000);
    expect(expiresMs).toBeLessThan(before + 8 * 24 * 60 * 60 * 1_000);
    const fromDb = await repo.findOneByOrFail({ id: session.id });
    expect(fromDb.status).toBe('PARSING');
  });

  it('setStatus() PARSING → READY succeeds and persists', async () => {
    const session = await service.createSession('acme', 'alice');
    await service.setStatus(session.id, 'READY');
    const fresh = await repo.findOneByOrFail({ id: session.id });
    expect(fresh.status).toBe('READY');
  });

  it('setStatus() PARSING → CONFIRMED is rejected by transition guard', async () => {
    const session = await service.createSession('acme', 'alice');
    await expect(
      service.setStatus(session.id, 'CONFIRMED'),
    ).rejects.toBeInstanceOf(ConflictException);
  });

  it('setStatus() FAILED is terminal — cannot move to READY', async () => {
    const session = await service.createSession('acme', 'alice');
    await service.setStatus(session.id, 'FAILED', 'parser blew up');
    const fresh = await repo.findOneByOrFail({ id: session.id });
    expect(fresh.status).toBe('FAILED');
    expect(fresh.parseError).toBe('parser blew up');
    await expect(
      service.setStatus(session.id, 'READY'),
    ).rejects.toBeInstanceOf(ConflictException);
  });

  it('setResult() with flipToReady=true moves PARSING → READY', async () => {
    const session = await service.createSession('acme', 'alice');
    await service.setResult(session.id, {
      atoms: [{ frontmatter: { id: 'REQ-F-001' }, body_md: '...' }],
      suggestedBidCard: { client_name: 'ACME' },
      flipToReady: true,
    });
    const fresh = await repo.findOneByOrFail({ id: session.id });
    expect(fresh.status).toBe('READY');
    expect(fresh.atoms).toHaveLength(1);
    expect(fresh.suggestedBidCard).toEqual({ client_name: 'ACME' });
  });

  it('getById() throws 404 when session is expired AND status is PARSING', async () => {
    const session = await service.createSession('acme', 'alice');
    // Forcibly move expires_at into the past.
    session.expiresAt = '2020-01-01T00:00:00.000Z';
    await repo.save(session);
    await expect(service.getById(session.id)).rejects.toBeInstanceOf(
      NotFoundException,
    );
    // allowExpired=true bypasses the guard.
    await expect(
      service.getById(session.id, { allowExpired: true }),
    ).resolves.toMatchObject({ id: session.id });
  });

  it('findExpired() returns only PARSING/READY rows past expires_at', async () => {
    const a = await service.createSession('acme', 'alice');
    const b = await service.createSession('acme', 'alice');
    const c = await service.createSession('acme', 'alice');
    a.expiresAt = '2020-01-01T00:00:00.000Z';
    b.expiresAt = '2020-01-01T00:00:00.000Z';
    b.status = 'CONFIRMED';
    c.expiresAt = '2099-12-31T23:59:59.000Z'; // future
    await repo.save([a, b, c]);
    const expired = await service.findExpired();
    const ids = expired.map((s) => s.id);
    expect(ids).toContain(a.id);
    // CONFIRMED rows are excluded even if expired (no MinIO prefix to clean).
    expect(ids).not.toContain(b.id);
    // Future expiry not yet expired.
    expect(ids).not.toContain(c.id);
  });

  it('markAbandoned() drops the MinIO prefix and flips status', async () => {
    const session = await service.createSession('acme', 'alice');
    objectStore.deletePrefix.mockResolvedValueOnce(3);
    const result = await service.markAbandoned(session.id);
    expect(result.deleted).toBe(3);
    expect(result.status).toBe('ABANDONED');
    expect(objectStore.deletePrefix).toHaveBeenCalledWith(
      service.getBucket(),
      `parse_sessions/${session.id}/`,
    );
    const fresh = await repo.findOneByOrFail({ id: session.id });
    expect(fresh.status).toBe('ABANDONED');
  });

  it('markAbandoned() refuses CONFIRMED sessions (their MinIO is renamed)', async () => {
    const session = await service.createSession('acme', 'alice');
    session.status = 'CONFIRMED';
    session.confirmedBidId = '11111111-1111-1111-1111-111111111111';
    await repo.save(session);
    await expect(service.markAbandoned(session.id)).rejects.toBeInstanceOf(
      ConflictException,
    );
  });

  it('markAbandoned() is idempotent (already-abandoned is a no-op)', async () => {
    const session = await service.createSession('acme', 'alice');
    session.status = 'ABANDONED';
    await repo.save(session);
    objectStore.deletePrefix.mockResolvedValueOnce(0);
    const result = await service.markAbandoned(session.id);
    expect(result.status).toBe('ABANDONED');
    expect(result.deleted).toBe(0);
  });

  it('assertTransition() exhaustively encodes the lifecycle table', () => {
    expect(() => service.assertTransition('PARSING', 'READY')).not.toThrow();
    expect(() => service.assertTransition('PARSING', 'FAILED')).not.toThrow();
    expect(() =>
      service.assertTransition('READY', 'CONFIRMED'),
    ).not.toThrow();
    expect(() =>
      service.assertTransition('READY', 'ABANDONED'),
    ).not.toThrow();
    expect(() => service.assertTransition('PARSING', 'CONFIRMED')).toThrow();
    expect(() => service.assertTransition('CONFIRMED', 'READY')).toThrow();
    expect(() => service.assertTransition('FAILED', 'READY')).toThrow();
    expect(() => service.assertTransition('ABANDONED', 'READY')).toThrow();
  });
});
