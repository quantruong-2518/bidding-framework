import { Test, type TestingModule } from '@nestjs/testing';
import { TypeOrmModule, getRepositoryToken } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { AuditLog } from '../src/audit/audit-log.entity';
import { AuditService } from '../src/audit/audit.service';

describe('AuditService (sqlite in-memory)', () => {
  let service: AuditService;
  let repo: Repository<AuditLog>;
  let moduleRef: TestingModule;

  beforeEach(async () => {
    moduleRef = await Test.createTestingModule({
      imports: [
        TypeOrmModule.forRoot({
          type: 'better-sqlite3',
          database: ':memory:',
          entities: [AuditLog],
          synchronize: true,
          dropSchema: true,
        }),
        TypeOrmModule.forFeature([AuditLog]),
      ],
      providers: [AuditService],
    }).compile();

    service = moduleRef.get(AuditService);
    repo = moduleRef.get(getRepositoryToken(AuditLog));
  });

  afterEach(async () => {
    await moduleRef.close();
  });

  it('persists a full audit row', async () => {
    await service.record({
      userSub: 'kc-user-1',
      username: 'alice',
      roles: ['bid_manager'],
      action: 'POST /bids',
      resourceType: 'bids',
      resourceId: null,
      statusCode: 201,
      metadata: { path: '/bids' },
    });

    const rows = await repo.find();
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      userSub: 'kc-user-1',
      username: 'alice',
      roles: ['bid_manager'],
      action: 'POST /bids',
      resourceType: 'bids',
      resourceId: null,
      statusCode: 201,
    });
    expect(rows[0].metadata).toEqual({ path: '/bids' });
  });

  it('writes sequential rows — one per request', async () => {
    for (let i = 0; i < 3; i += 1) {
      await service.record({
        userSub: 'u',
        username: 'u',
        roles: ['ba'],
        action: `GET /bids/${i}`,
        resourceType: 'bids',
        resourceId: String(i),
        statusCode: 200,
      });
    }
    expect(await repo.count()).toBe(3);
  });

  it('swallows DB errors (audit never breaks the request)', async () => {
    // Close the repository's underlying connection to force a write failure;
    // the service should log + resolve without throwing.
    await moduleRef.close();
    await expect(
      service.record({
        userSub: 'u',
        username: 'u',
        roles: [],
        action: 'POST /bids',
        resourceType: 'bids',
        resourceId: null,
        statusCode: 500,
      }),
    ).resolves.toBeUndefined();
  });

  it('dedupes identical GET 2xx rows from the same actor on the same resource', async () => {
    const sameRow = {
      userSub: 'kc-u',
      username: 'alice',
      roles: ['bid_manager'],
      action: 'GET /bids/:id/workflow/status',
      resourceType: 'bids',
      resourceId: 'bid-9',
      statusCode: 200,
    };
    await service.record(sameRow);
    await service.record(sameRow);
    await service.record(sameRow);
    expect(await repo.count()).toBe(1);
  });

  it('does NOT dedupe state-changing methods even on identical (actor, resource)', async () => {
    const samePost = {
      userSub: 'kc-u',
      username: 'alice',
      roles: ['admin'],
      action: 'POST /bids/:id/workflow',
      resourceType: 'bids',
      resourceId: 'bid-1',
      statusCode: 200,
    };
    await service.record(samePost);
    await service.record(samePost);
    expect(await repo.count()).toBe(2);
  });

  it('does NOT dedupe error responses (≥400) — security-relevant signals', async () => {
    const forbidden = {
      userSub: 'kc-u',
      username: 'mallory',
      roles: ['ba'],
      action: 'GET /bids/:id',
      resourceType: 'bids',
      resourceId: 'bid-secret',
      statusCode: 403,
    };
    await service.record(forbidden);
    await service.record(forbidden);
    expect(await repo.count()).toBe(2);
  });

  it('treats a different actor as a different dedupe key', async () => {
    const base = {
      action: 'GET /bids/:id',
      resourceType: 'bids',
      resourceId: 'bid-1',
      statusCode: 200,
    } as const;
    await service.record({ ...base, userSub: 'u-1', username: 'alice', roles: ['ba'] });
    await service.record({ ...base, userSub: 'u-2', username: 'bob', roles: ['sa'] });
    expect(await repo.count()).toBe(2);
  });

  it('clearDedupeCacheForTest re-opens the window for the same key', async () => {
    const row = {
      userSub: 'u',
      username: 'u',
      roles: ['admin'],
      action: 'GET /dashboard/audit',
      resourceType: 'dashboard',
      resourceId: null,
      statusCode: 200,
    };
    await service.record(row);
    await service.record(row); // suppressed
    expect(await repo.count()).toBe(1);
    service.clearDedupeCacheForTest();
    await service.record(row); // window reset → new row
    expect(await repo.count()).toBe(2);
  });
});
