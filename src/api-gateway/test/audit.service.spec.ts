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
});
