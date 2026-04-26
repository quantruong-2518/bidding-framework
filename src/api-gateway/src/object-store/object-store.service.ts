import {
  CopyObjectCommand,
  CreateBucketCommand,
  DeleteObjectCommand,
  DeleteObjectsCommand,
  GetObjectCommand,
  HeadBucketCommand,
  ListObjectsV2Command,
  PutObjectCommand,
  S3Client,
  type S3ClientConfig,
} from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';
import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';

/**
 * S0.5 Wave 1 — S3-compatible object-store wrapper.
 *
 * Methods mirror the Python sibling at ``ai-service/tools/object_store.py``
 * so server-side parse + materialise share an identical contract:
 *   - ``putObject(bucket, key, body, mime?)``
 *   - ``getObject(bucket, key)``
 *   - ``presignedGetUrl(bucket, key, ttlSec)``
 *   - ``renamePrefix(bucket, oldPrefix, newPrefix)``
 *   - ``deletePrefix(bucket, prefix)``
 *   - ``ensureBucket(bucket)``
 *
 * Backend selection (env-driven, evaluated once at construction):
 *   * ``OBJECT_STORE_BACKEND=minio`` → forces ``forcePathStyle=true`` so the
 *     classic MinIO single-bucket-as-directory layout works.
 *   * ``OBJECT_STORE_BACKEND=s3``    → vanilla AWS S3 client (subdomain
 *     style hosts, region picked from ``OBJECT_STORE_REGION``).
 *   * ``OBJECT_STORE_BACKEND``       unset → **stub mode** (warning logged,
 *     every method becomes a no-op or trivial pass-through). Lets local dev
 *     boot without provisioning MinIO and lets unit tests cover the
 *     "no infra" code path.
 *
 * If the SDK throws synchronously while we construct the underlying
 * :class:`S3Client` (e.g. malformed endpoint), we fall back to stub mode and
 * log a warning rather than crash the api-gateway boot.
 */
@Injectable()
export class ObjectStoreService {
  private readonly logger = new Logger(ObjectStoreService.name);
  private readonly client: S3Client | null;
  private readonly stub: boolean;
  private readonly endpoint: string | null;
  private readonly region: string;

  constructor(private readonly config: ConfigService) {
    const backend = (
      this.config.get<string>('OBJECT_STORE_BACKEND') ?? ''
    ).toLowerCase();
    this.endpoint = this.config.get<string>('OBJECT_STORE_ENDPOINT') ?? null;
    this.region =
      this.config.get<string>('OBJECT_STORE_REGION') ?? 'us-east-1';

    if (backend !== 'minio' && backend !== 's3') {
      this.logger.warn(
        'OBJECT_STORE_BACKEND unset (or unknown) — running in STUB mode; ' +
          'every put/get/rename/delete is a no-op. Set OBJECT_STORE_BACKEND=minio|s3 to enable.',
      );
      this.client = null;
      this.stub = true;
      return;
    }

    try {
      const accessKeyId =
        this.config.get<string>('OBJECT_STORE_ACCESS_KEY') ?? '';
      const secretAccessKey =
        this.config.get<string>('OBJECT_STORE_SECRET_KEY') ?? '';

      const opts: S3ClientConfig = {
        region: this.region,
        forcePathStyle: backend === 'minio',
      };
      if (this.endpoint) {
        opts.endpoint = this.endpoint;
      }
      if (accessKeyId && secretAccessKey) {
        opts.credentials = { accessKeyId, secretAccessKey };
      }

      this.client = new S3Client(opts);
      this.stub = false;
      this.logger.log(
        `ObjectStoreService ready backend=${backend} endpoint=${this.endpoint ?? '<sdk-default>'} region=${this.region}`,
      );
    } catch (err) {
      this.logger.warn(
        `S3Client construction failed — falling back to stub: ${(err as Error).message}`,
      );
      this.client = null;
      this.stub = true;
    }
  }

  /** True when no real backend was wired up; useful for tests + health endpoints. */
  get isStub(): boolean {
    return this.stub;
  }

  /** Upload a single object. ``body`` may be a Buffer or string. */
  async putObject(
    bucket: string,
    key: string,
    body: Buffer | Uint8Array | string,
    mime?: string,
  ): Promise<void> {
    if (this.stub || !this.client) {
      this.logger.debug(
        `[stub] putObject bucket=${bucket} key=${key} bytes=${body.length} mime=${mime ?? 'unset'}`,
      );
      return;
    }
    await this.client.send(
      new PutObjectCommand({
        Bucket: bucket,
        Key: key,
        Body: body,
        ContentType: mime,
      }),
    );
  }

  /** Fetch an object as a Buffer. Returns ``null`` in stub mode. */
  async getObject(bucket: string, key: string): Promise<Buffer | null> {
    if (this.stub || !this.client) {
      this.logger.debug(`[stub] getObject bucket=${bucket} key=${key}`);
      return null;
    }
    const out = await this.client.send(
      new GetObjectCommand({ Bucket: bucket, Key: key }),
    );
    const body = out.Body as
      | NodeJS.ReadableStream
      | { transformToByteArray?: () => Promise<Uint8Array> }
      | undefined;
    if (!body) return Buffer.alloc(0);
    if (
      typeof (body as { transformToByteArray?: unknown })
        .transformToByteArray === 'function'
    ) {
      const bytes = await (
        body as { transformToByteArray: () => Promise<Uint8Array> }
      ).transformToByteArray();
      return Buffer.from(bytes);
    }
    // Fallback: stream → Buffer
    const stream = body as NodeJS.ReadableStream;
    const chunks: Buffer[] = [];
    for await (const chunk of stream) {
      chunks.push(
        typeof chunk === 'string' ? Buffer.from(chunk) : Buffer.from(chunk),
      );
    }
    return Buffer.concat(chunks);
  }

  /**
   * Generate a time-limited presigned GET URL.
   *
   * Returns a stable placeholder string in stub mode so callers (e.g. a
   * preview endpoint) can still emit a payload that the frontend can render
   * without crashing. Real production setups never see the placeholder.
   */
  async presignedGetUrl(
    bucket: string,
    key: string,
    ttlSec: number,
  ): Promise<string> {
    if (this.stub || !this.client) {
      this.logger.debug(
        `[stub] presignedGetUrl bucket=${bucket} key=${key} ttl=${ttlSec}`,
      );
      return `stub://object-store/${bucket}/${key}?ttl=${ttlSec}`;
    }
    const cmd = new GetObjectCommand({ Bucket: bucket, Key: key });
    return getSignedUrl(this.client, cmd, { expiresIn: ttlSec });
  }

  /**
   * Rename a key prefix by listing → copy-each → delete-old. Idempotent on
   * partial failure: callers can retry; copies that already exist no-op.
   * Used by the Wave 2B confirm tx to flip ``parse_sessions/<sid>/`` →
   * ``bids/<bid_id>/``.
   */
  async renamePrefix(
    bucket: string,
    oldPrefix: string,
    newPrefix: string,
  ): Promise<number> {
    if (this.stub || !this.client) {
      this.logger.debug(
        `[stub] renamePrefix bucket=${bucket} ${oldPrefix} -> ${newPrefix}`,
      );
      return 0;
    }
    const keys = await this._listKeys(bucket, oldPrefix);
    let moved = 0;
    for (const key of keys) {
      const newKey = newPrefix + key.slice(oldPrefix.length);
      await this.client.send(
        new CopyObjectCommand({
          Bucket: bucket,
          CopySource: encodeURIComponent(`${bucket}/${key}`),
          Key: newKey,
        }),
      );
      await this.client.send(
        new DeleteObjectCommand({ Bucket: bucket, Key: key }),
      );
      moved += 1;
    }
    return moved;
  }

  /**
   * Delete every key under ``prefix``. Returns the count deleted.
   * Used by the TTL cron to clean abandoned parse sessions.
   */
  async deletePrefix(bucket: string, prefix: string): Promise<number> {
    if (this.stub || !this.client) {
      this.logger.debug(`[stub] deletePrefix bucket=${bucket} prefix=${prefix}`);
      return 0;
    }
    const keys = await this._listKeys(bucket, prefix);
    if (keys.length === 0) return 0;
    // S3 caps DeleteObjects at 1000 per call
    let deleted = 0;
    for (let i = 0; i < keys.length; i += 1000) {
      const batch = keys.slice(i, i + 1000);
      await this.client.send(
        new DeleteObjectsCommand({
          Bucket: bucket,
          Delete: { Objects: batch.map((k) => ({ Key: k })) },
        }),
      );
      deleted += batch.length;
    }
    return deleted;
  }

  /**
   * Idempotent bucket bootstrap. ``HeadBucket`` first; on 404 (or NotFound)
   * fall through to ``CreateBucket``. No-op when the bucket already exists.
   */
  async ensureBucket(bucket: string): Promise<void> {
    if (this.stub || !this.client) {
      this.logger.debug(`[stub] ensureBucket bucket=${bucket}`);
      return;
    }
    try {
      await this.client.send(new HeadBucketCommand({ Bucket: bucket }));
      return;
    } catch (err) {
      const status =
        (err as { $metadata?: { httpStatusCode?: number } })?.$metadata
          ?.httpStatusCode ?? 0;
      const code = (err as { name?: string }).name ?? '';
      if (status !== 404 && code !== 'NotFound' && code !== 'NoSuchBucket') {
        // Permission errors etc. — surface upstream
        throw err;
      }
    }
    await this.client.send(new CreateBucketCommand({ Bucket: bucket }));
  }

  /**
   * Internal: enumerate every key under ``prefix`` (handles pagination).
   */
  private async _listKeys(bucket: string, prefix: string): Promise<string[]> {
    if (!this.client) return [];
    const keys: string[] = [];
    let continuationToken: string | undefined;
    do {
      const out = await this.client.send(
        new ListObjectsV2Command({
          Bucket: bucket,
          Prefix: prefix,
          ContinuationToken: continuationToken,
        }),
      );
      for (const item of out.Contents ?? []) {
        if (item.Key) keys.push(item.Key);
      }
      continuationToken = out.IsTruncated
        ? out.NextContinuationToken
        : undefined;
    } while (continuationToken);
    return keys;
  }
}
