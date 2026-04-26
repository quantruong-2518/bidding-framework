import { BadRequestException, ConflictException, NotFoundException } from '@nestjs/common';
import { Test, type TestingModule } from '@nestjs/testing';
import { TypeOrmModule, getRepositoryToken } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Bid } from '../src/bids/bid.entity';
import { AiServiceClient } from '../src/gateway/ai-service.client';
import { ObjectStoreService } from '../src/object-store/object-store.service';
import type { AuthenticatedUser } from '../src/auth/current-user.decorator';
import type { ConfirmRequestDto } from '../src/parse-sessions/dto/confirm-request.dto';
import type { UploadFilesDto } from '../src/parse-sessions/dto/upload-files.dto';
import { MaterializeService } from '../src/parse-sessions/materialize.service';
import { ParseController } from '../src/parse-sessions/parse.controller';
import { ParseSession } from '../src/parse-sessions/parse-session.entity';
import { ParseSessionsService } from '../src/parse-sessions/parse-sessions.service';

const TENANT = 'acme';
const USER: AuthenticatedUser = {
  sub: 'kc-1',
  username: 'alice',
  email: 'a@b.c',
  roles: ['admin'],
};

function makeUploadedFile(
  overrides: Partial<Express.Multer.File> = {},
): Express.Multer.File {
  return {
    fieldname: 'files',
    originalname: 'rfp.pdf',
    encoding: '7bit',
    mimetype: 'application/pdf',
    size: 100,
    stream: null as never,
    destination: '',
    filename: 'rfp.pdf',
    path: '',
    buffer: Buffer.from('hello'),
    ...overrides,
  };
}

describe('ParseController', () => {
  let controller: ParseController;
  let sessionRepo: Repository<ParseSession>;
  let sessions: ParseSessionsService;
  let aiClient: { startParse: jest.Mock; getParseStatus: jest.Mock };
  let objectStore: { putObject: jest.Mock; deletePrefix: jest.Mock };
  let materialize: { confirmAndStart: jest.Mock };
  let moduleRef: TestingModule;

  beforeEach(async () => {
    aiClient = {
      startParse: jest.fn().mockResolvedValue({
        session_id: 'will-be-overwritten',
        status: 'PARSING',
      }),
      // Default tracker: PARSING with no result. Per-test overrides below
      // exercise the live atoms-merge path. Tracker errors are swallowed by
      // the controller, so a missing override falls back to the empty Postgres
      // shape — that's the existing PARSING test's contract.
      getParseStatus: jest.fn().mockRejectedValue(new Error('tracker miss')),
    };
    objectStore = {
      putObject: jest.fn().mockResolvedValue(undefined),
      deletePrefix: jest.fn().mockResolvedValue(0),
    };
    materialize = {
      confirmAndStart: jest.fn().mockResolvedValue({
        bid_id: 'bid-1',
        workflow_id: 'wf-1',
        vault_path: '/v/bids/bid-1/',
        trace_id: 'trace-1',
      }),
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
        TypeOrmModule.forFeature([ParseSession]),
      ],
      controllers: [ParseController],
      providers: [
        ParseSessionsService,
        { provide: ObjectStoreService, useValue: objectStore },
        { provide: AiServiceClient, useValue: aiClient },
        { provide: MaterializeService, useValue: materialize },
      ],
    }).compile();

    controller = moduleRef.get(ParseController);
    sessions = moduleRef.get(ParseSessionsService);
    sessionRepo = moduleRef.get(getRepositoryToken(ParseSession));
  });

  afterEach(async () => {
    await moduleRef.close();
  });

  describe('POST /bids/parse', () => {
    const body: UploadFilesDto = { tenant_id: TENANT };

    it('uploads files, persists session in PARSING, returns sid', async () => {
      const files = [
        makeUploadedFile({ originalname: 'rfp.pdf', mimetype: 'application/pdf' }),
        makeUploadedFile({
          originalname: 'apx.docx',
          mimetype:
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        }),
      ];
      const result = await controller.upload(files, body, USER);
      expect(result.status).toBe('PARSING');
      expect(result.session_id).toMatch(/^[0-9a-f-]{36}$/);
      const fromDb = await sessionRepo.findOneByOrFail({ id: result.session_id });
      expect(fromDb.tenantId).toBe(TENANT);
      expect(fromDb.userId).toBe('alice');
      // 2 files → 2 putObject calls.
      expect(objectStore.putObject).toHaveBeenCalledTimes(2);
      // ai-service kicked off with the right shape.
      expect(aiClient.startParse).toHaveBeenCalledWith(
        expect.objectContaining({
          session_id: result.session_id,
          tenant_id: TENANT,
          user_id: 'alice',
          files: expect.arrayContaining([
            expect.objectContaining({
              original_name: 'rfp.pdf',
              mime: 'application/pdf',
            }),
          ]),
        }),
      );
    });

    it('rejects empty files[] with 400', async () => {
      await expect(controller.upload([], body, USER)).rejects.toBeInstanceOf(
        BadRequestException,
      );
      await expect(
        controller.upload(undefined, body, USER),
      ).rejects.toBeInstanceOf(BadRequestException);
    });

    it('rejects unsupported mime types', async () => {
      const files = [
        makeUploadedFile({ originalname: 'evil.exe', mimetype: 'application/x-msdownload' }),
      ];
      await expect(controller.upload(files, body, USER)).rejects.toBeInstanceOf(
        BadRequestException,
      );
      expect(aiClient.startParse).not.toHaveBeenCalled();
    });

    it('flips session to FAILED when ai-service refuses', async () => {
      aiClient.startParse.mockRejectedValueOnce(new Error('parser blew up'));
      const files = [makeUploadedFile()];
      await expect(
        controller.upload(files, body, USER),
      ).rejects.toThrow(/parser blew up/);
      const rows = await sessionRepo.find();
      expect(rows).toHaveLength(1);
      expect(rows[0].status).toBe('FAILED');
      expect(rows[0].parseError).toMatch(/parser blew up/);
    });
  });

  describe('GET /bids/parse/:sid/preview', () => {
    it('returns READY shape with atom counts + suggested workflow', async () => {
      const session = await sessions.createSession(TENANT, 'alice');
      await sessions.setResult(session.id, {
        suggestedBidCard: {
          name: 'ACME Bid',
          client_name: 'ACME',
          industry: 'banking',
          region: 'APAC',
          deadline: '2026-06-01',
          scope_summary: 'core banking',
          estimated_profile: 'M',
          language: 'en',
          technology_keywords: ['kafka'],
        },
        atoms: [
          {
            frontmatter: {
              id: 'REQ-F-001',
              type: 'functional',
              priority: 'MUST',
              category: 'login',
              extraction: { confidence: 0.9 },
              source: { file: 'sources/01-rfp.md' },
            },
            body_md: 'first',
          },
          {
            frontmatter: {
              id: 'REQ-NFR-001',
              type: 'nfr',
              priority: 'SHOULD',
              category: 'perf',
              extraction: { confidence: 0.4 },
              source: { file: 'sources/01-rfp.md' },
            },
            body_md: 'slow',
          },
        ],
        anchorMd: '# anchor',
        summaryMd: '# summary',
        manifest: { files: [{ file_id: 'f1', original_name: 'rfp.pdf', mime: 'application/pdf', role: 'rfp' }] },
        openQuestions: [{ atom_id: 'REQ-NFR-001', question: 'How fast?' }],
        flipToReady: true,
      });

      const preview = await controller.preview(session.id);
      expect(preview.status).toBe('READY');
      expect(preview.suggested_bid_card?.client_name).toBe('ACME');
      expect(preview.atoms_preview.total).toBe(2);
      expect(preview.atoms_preview.by_type).toEqual({ functional: 1, nfr: 1 });
      expect(preview.atoms_preview.by_priority).toEqual({ MUST: 1, SHOULD: 1 });
      expect(preview.atoms_preview.low_confidence_count).toBe(1);
      expect(preview.atoms_preview.sample).toHaveLength(2);
      expect(preview.context_preview.open_questions).toEqual(['How fast?']);
      expect(preview.suggested_workflow?.profile).toBe('M');
      expect(preview.current_state).toBe('AWAITING_CONFIRM');
      expect(preview.sources_preview).toHaveLength(1);
    });

    it('returns PARSING shape with progress + zero atoms', async () => {
      const session = await sessions.createSession(TENANT, 'alice');
      const preview = await controller.preview(session.id);
      expect(preview.status).toBe('PARSING');
      expect(preview.progress).toBeDefined();
      expect(preview.atoms_preview.total).toBe(0);
      expect(preview.suggested_bid_card).toBeNull();
      expect(preview.suggested_workflow).toBeNull();
    });

    it('merges live ai-service tracker atoms into the PARSING preview', async () => {
      const session = await sessions.createSession(TENANT, 'alice');
      // Simulate ai-service mid-parse: 2 of 3 files done, 4 atoms accumulated.
      aiClient.getParseStatus.mockResolvedValueOnce({
        session_id: session.id,
        status: 'PARSING',
        progress: {
          stage: 'extracted 4 atoms (2/3 files)',
          files_total: 3,
          files_processed: 2,
          atoms_so_far: 4,
          percent: 60,
        },
        result: {
          atoms_preview: {
            total: 4,
            by_type: { functional: 3, nfr: 1 },
            by_priority: { MUST: 3, SHOULD: 1 },
            low_confidence_count: 1,
            sample: [
              {
                id: 'REQ-F-001',
                type: 'functional',
                priority: 'MUST',
                category: 'auth',
                source_file: 'rfp.pdf',
                body_md: 'SSO required',
                confidence: 0.92,
                split_recommended: false,
              },
            ],
          },
          sources_preview: [
            {
              file_id: 'rfp',
              name: 'rfp.pdf',
              role: 'rfp',
              language: 'en',
              page_count: 12,
              atoms_extracted: 3,
              original_name: 'rfp.pdf',
              mime: 'application/pdf',
              parsed_to: 'sources/01-rfp.md',
            },
            {
              file_id: 'qa',
              name: 'qa.pdf',
              role: 'qa',
              language: 'en',
              page_count: 2,
              atoms_extracted: 1,
              original_name: 'qa.pdf',
              mime: 'application/pdf',
              parsed_to: 'sources/02-qa.md',
            },
          ],
        },
      });

      const preview = await controller.preview(session.id);
      expect(preview.status).toBe('PARSING');
      expect(preview.atoms_preview.total).toBe(4);
      expect(preview.atoms_preview.by_type).toEqual({ functional: 3, nfr: 1 });
      expect(preview.atoms_preview.sample).toHaveLength(1);
      expect(preview.sources_preview).toHaveLength(2);
      expect(preview.progress?.stage).toMatch(/extracted 4 atoms/);
      expect(preview.progress?.percent).toBe(60);
      expect(aiClient.getParseStatus).toHaveBeenCalledWith(session.id);
    });

    it('falls back to empty atoms when tracker fetch throws', async () => {
      const session = await sessions.createSession(TENANT, 'alice');
      // Default mock rejects → controller swallows → empty Postgres shape.
      const preview = await controller.preview(session.id);
      expect(preview.status).toBe('PARSING');
      expect(preview.atoms_preview.total).toBe(0);
      expect(preview.progress?.stage).toBe('parsing');
    });

    it('does not call ai-service tracker for non-PARSING sessions', async () => {
      const session = await sessions.createSession(TENANT, 'alice');
      session.status = 'READY';
      session.atoms = [];
      await sessionRepo.save(session);
      const preview = await controller.preview(session.id);
      expect(preview.status).toBe('READY');
      expect(aiClient.getParseStatus).not.toHaveBeenCalled();
    });

    it('throws 404 for an unknown sid', async () => {
      await expect(
        controller.preview('00000000-0000-0000-0000-000000000999'),
      ).rejects.toBeInstanceOf(NotFoundException);
    });

    it('throws 404 when session has expired', async () => {
      const session = await sessions.createSession(TENANT, 'alice');
      session.expiresAt = '2020-01-01T00:00:00.000Z';
      await sessionRepo.save(session);
      await expect(controller.preview(session.id)).rejects.toBeInstanceOf(
        NotFoundException,
      );
    });
  });

  describe('POST /bids/parse/:sid/confirm', () => {
    const dto: ConfirmRequestDto = { atom_rejects: ['REQ-F-X'] };

    it('delegates to MaterializeService and returns confirm shape', async () => {
      const sid = '11111111-1111-1111-1111-111111111111';
      const result = await controller.confirm(sid, dto as never, USER);
      expect(result).toEqual({
        bid_id: 'bid-1',
        workflow_id: 'wf-1',
        vault_path: '/v/bids/bid-1/',
        trace_id: 'trace-1',
      });
      expect(materialize.confirmAndStart).toHaveBeenCalledWith(
        sid,
        dto,
        'alice',
      );
    });

    it('propagates ConflictException from re-confirm', async () => {
      materialize.confirmAndStart.mockRejectedValueOnce(
        new ConflictException('already confirmed'),
      );
      await expect(
        controller.confirm(
          '11111111-1111-1111-1111-111111111111',
          {} as never,
          USER,
        ),
      ).rejects.toBeInstanceOf(ConflictException);
    });
  });

  describe('DELETE /bids/parse/:sid', () => {
    it('flips status to ABANDONED + drops MinIO prefix', async () => {
      const session = await sessions.createSession(TENANT, 'alice');
      objectStore.deletePrefix.mockResolvedValueOnce(2);
      await controller.abandon(session.id);
      const fresh = await sessionRepo.findOneByOrFail({ id: session.id });
      expect(fresh.status).toBe('ABANDONED');
      expect(objectStore.deletePrefix).toHaveBeenCalledWith(
        sessions.getBucket(),
        `parse_sessions/${session.id}/`,
      );
    });

    it('is idempotent for already-ABANDONED sessions', async () => {
      const session = await sessions.createSession(TENANT, 'alice');
      session.status = 'ABANDONED';
      await sessionRepo.save(session);
      await expect(controller.abandon(session.id)).resolves.toBeUndefined();
    });
  });
});
