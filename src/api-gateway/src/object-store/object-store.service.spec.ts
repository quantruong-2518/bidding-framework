import { ConfigService } from '@nestjs/config';
import { ObjectStoreService } from './object-store.service';

/**
 * S0.5 Wave 1 — ObjectStoreService unit specs.
 *
 * Strategy: hand-rolled jest.mock of ``@aws-sdk/client-s3`` so we capture the
 * commands sent to the (fake) S3Client without touching the network. Each
 * Command class is a plain identity function recording its constructor args
 * on the instance, so ``client.send(new PutObjectCommand({...}))`` lets us
 * assert against ``mockSend.mock.calls[0][0].input``.
 */

type CapturedCmd = { __cmd: string; input: Record<string, unknown> };

const mockSend = jest.fn<Promise<unknown>, [CapturedCmd]>();

jest.mock('@aws-sdk/client-s3', () => {
  function makeCmd(name: string) {
    return class {
      __cmd = name;
      input: Record<string, unknown>;
      constructor(input: Record<string, unknown>) {
        this.input = input;
      }
    };
  }
  return {
    S3Client: jest.fn().mockImplementation(() => ({ send: mockSend })),
    PutObjectCommand: makeCmd('PutObjectCommand'),
    GetObjectCommand: makeCmd('GetObjectCommand'),
    CopyObjectCommand: makeCmd('CopyObjectCommand'),
    DeleteObjectCommand: makeCmd('DeleteObjectCommand'),
    DeleteObjectsCommand: makeCmd('DeleteObjectsCommand'),
    ListObjectsV2Command: makeCmd('ListObjectsV2Command'),
    HeadBucketCommand: makeCmd('HeadBucketCommand'),
    CreateBucketCommand: makeCmd('CreateBucketCommand'),
  };
});

jest.mock('@aws-sdk/s3-request-presigner', () => ({
  getSignedUrl: jest.fn(
    async (
      _client: unknown,
      cmd: CapturedCmd,
      opts: { expiresIn: number },
    ) =>
      `https://mock-presign/${(cmd.input.Bucket as string) ?? 'b'}/${(cmd.input.Key as string) ?? 'k'}?ttl=${opts.expiresIn}`,
  ),
}));

function makeConfig(env: Record<string, string | undefined>): ConfigService {
  return {
    get: jest.fn(<T>(key: string): T | undefined => env[key] as T | undefined),
  } as unknown as ConfigService;
}

describe('ObjectStoreService', () => {
  beforeEach(() => {
    mockSend.mockReset();
  });

  describe('stub mode', () => {
    it('constructs successfully when OBJECT_STORE_BACKEND is unset', () => {
      const svc = new ObjectStoreService(makeConfig({}));
      expect(svc.isStub).toBe(true);
    });

    it('constructs in stub mode for unknown backend value', () => {
      const svc = new ObjectStoreService(
        makeConfig({ OBJECT_STORE_BACKEND: 'rados' }),
      );
      expect(svc.isStub).toBe(true);
    });

    it('returns null/0 from get/rename/delete and a placeholder URL', async () => {
      const svc = new ObjectStoreService(makeConfig({}));
      await expect(svc.putObject('b', 'k', Buffer.from('x'))).resolves.toBeUndefined();
      await expect(svc.getObject('b', 'k')).resolves.toBeNull();
      await expect(svc.renamePrefix('b', 'old/', 'new/')).resolves.toBe(0);
      await expect(svc.deletePrefix('b', 'old/')).resolves.toBe(0);
      await expect(svc.ensureBucket('b')).resolves.toBeUndefined();
      const url = await svc.presignedGetUrl('b', 'k', 300);
      expect(url).toContain('stub://');
      expect(mockSend).not.toHaveBeenCalled();
    });
  });

  describe('minio backend', () => {
    const makeMinioSvc = () =>
      new ObjectStoreService(
        makeConfig({
          OBJECT_STORE_BACKEND: 'minio',
          OBJECT_STORE_ENDPOINT: 'http://minio:9000',
          OBJECT_STORE_ACCESS_KEY: 'k',
          OBJECT_STORE_SECRET_KEY: 's',
        }),
      );

    it('constructs in non-stub mode when backend=minio', () => {
      const svc = makeMinioSvc();
      expect(svc.isStub).toBe(false);
    });

    it('putObject sends PutObjectCommand with bucket/key/body/mime', async () => {
      mockSend.mockResolvedValue({});
      const svc = makeMinioSvc();
      await svc.putObject('bid-originals', 'sess/01.pdf', Buffer.from('hi'), 'application/pdf');
      expect(mockSend).toHaveBeenCalledTimes(1);
      const cmd = mockSend.mock.calls[0][0];
      expect(cmd.__cmd).toBe('PutObjectCommand');
      expect(cmd.input.Bucket).toBe('bid-originals');
      expect(cmd.input.Key).toBe('sess/01.pdf');
      expect(cmd.input.ContentType).toBe('application/pdf');
    });

    it('getObject collects bytes via transformToByteArray', async () => {
      mockSend.mockResolvedValue({
        Body: {
          transformToByteArray: async () => new Uint8Array([1, 2, 3]),
        },
      });
      const svc = makeMinioSvc();
      const buf = await svc.getObject('b', 'k');
      expect(buf).not.toBeNull();
      expect(buf!.equals(Buffer.from([1, 2, 3]))).toBe(true);
    });

    it('renamePrefix lists, copies each, deletes each', async () => {
      mockSend
        .mockResolvedValueOnce({
          Contents: [
            { Key: 'old/a.txt' },
            { Key: 'old/sub/b.txt' },
          ],
          IsTruncated: false,
        })
        // Copy + delete for each of the 2 keys = 4 calls
        .mockResolvedValue({});
      const svc = makeMinioSvc();
      const moved = await svc.renamePrefix('bid-originals', 'old/', 'new/');
      expect(moved).toBe(2);
      // 1 list + 2 (copy + delete) = 5 calls
      expect(mockSend).toHaveBeenCalledTimes(5);
      const copyCmds = mockSend.mock.calls
        .map((c) => c[0])
        .filter((c) => c.__cmd === 'CopyObjectCommand');
      expect(copyCmds).toHaveLength(2);
      expect(copyCmds[0].input.Key).toBe('new/a.txt');
      expect(copyCmds[1].input.Key).toBe('new/sub/b.txt');
    });

    it('deletePrefix lists then sends DeleteObjects in batches', async () => {
      mockSend
        .mockResolvedValueOnce({
          Contents: [{ Key: 'sess/a' }, { Key: 'sess/b' }, { Key: 'sess/c' }],
          IsTruncated: false,
        })
        .mockResolvedValueOnce({});
      const svc = makeMinioSvc();
      const n = await svc.deletePrefix('bid-originals', 'sess/');
      expect(n).toBe(3);
      const delCmd = mockSend.mock.calls[1][0];
      expect(delCmd.__cmd).toBe('DeleteObjectsCommand');
      expect((delCmd.input.Delete as { Objects: { Key: string }[] }).Objects).toHaveLength(3);
    });

    it('ensureBucket is idempotent when HeadBucket succeeds', async () => {
      mockSend.mockResolvedValueOnce({}); // HeadBucket OK
      const svc = makeMinioSvc();
      await svc.ensureBucket('bid-originals');
      expect(mockSend).toHaveBeenCalledTimes(1);
      expect(mockSend.mock.calls[0][0].__cmd).toBe('HeadBucketCommand');
    });

    it('ensureBucket creates the bucket when HeadBucket 404s', async () => {
      const notFound = Object.assign(new Error('not found'), {
        $metadata: { httpStatusCode: 404 },
        name: 'NotFound',
      });
      mockSend
        .mockRejectedValueOnce(notFound)
        .mockResolvedValueOnce({});
      const svc = makeMinioSvc();
      await svc.ensureBucket('bid-originals');
      expect(mockSend).toHaveBeenCalledTimes(2);
      expect(mockSend.mock.calls[1][0].__cmd).toBe('CreateBucketCommand');
    });

    it('presignedGetUrl returns a real signed URL string with the requested TTL', async () => {
      const svc = makeMinioSvc();
      const url = await svc.presignedGetUrl('bid-originals', 'sess/x.pdf', 600);
      expect(url).toContain('mock-presign');
      expect(url).toContain('bid-originals');
      expect(url).toContain('sess/x.pdf');
      expect(url).toContain('ttl=600');
    });

    it('list pagination follows continuation tokens', async () => {
      mockSend
        .mockResolvedValueOnce({
          Contents: [{ Key: 'p/1' }],
          IsTruncated: true,
          NextContinuationToken: 'TOK',
        })
        .mockResolvedValueOnce({
          Contents: [{ Key: 'p/2' }],
          IsTruncated: false,
        })
        .mockResolvedValueOnce({}); // DeleteObjects
      const svc = makeMinioSvc();
      const n = await svc.deletePrefix('b', 'p/');
      expect(n).toBe(2);
      // 2 list calls + 1 delete = 3 sends
      expect(mockSend).toHaveBeenCalledTimes(3);
    });
  });
});
