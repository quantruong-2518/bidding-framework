import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { ObjectStoreService } from './object-store.service';

/**
 * S0.5 Wave 1 — S3-compatible object-store wrapper module.
 *
 * Exposes :class:`ObjectStoreService` to any other module that needs to
 * upload, fetch, presign, or rename binary blobs (parse-session originals,
 * audit-dashboard exports, etc.). Backend selection is env-driven:
 *
 *   * ``OBJECT_STORE_BACKEND=minio`` → talks to the local MinIO container
 *   * ``OBJECT_STORE_BACKEND=s3``    → talks to AWS S3 via @aws-sdk/client-s3
 *   * ``OBJECT_STORE_BACKEND``       unset → stub mode (warning + no-ops),
 *                                     so the api-gateway boots cleanly
 *                                     without object-store infra.
 */
@Module({
  imports: [ConfigModule],
  providers: [ObjectStoreService],
  exports: [ObjectStoreService],
})
export class ObjectStoreModule {}
