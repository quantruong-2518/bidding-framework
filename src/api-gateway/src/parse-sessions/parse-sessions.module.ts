import { HttpModule } from '@nestjs/axios';
import { Module } from '@nestjs/common';
import { ScheduleModule } from '@nestjs/schedule';
import { TypeOrmModule } from '@nestjs/typeorm';
import { BidsModule } from '../bids/bids.module';
import { AiServiceClient } from '../gateway/ai-service.client';
import { ObjectStoreModule } from '../object-store/object-store.module';
import { WorkflowsModule } from '../workflows/workflows.module';
import { MaterializeService } from './materialize.service';
import { ParseController } from './parse.controller';
import { ParseSession } from './parse-session.entity';
import { ParseSessionsService } from './parse-sessions.service';
import { ParseSessionTtlCleanupCron } from './ttl-cleanup.cron';

/**
 * S0.5 Wave 2B — top-level NestJS module wiring the parse-session surface.
 *
 * Dependency surface:
 *   - `TypeOrmModule.forFeature([ParseSession])` — Wave 1 entity, repository.
 *   - `ObjectStoreModule` — Wave 1 MinIO/S3 wrapper.
 *   - `BidsModule` — extended with `createFromParseSession()` for the
 *     confirm-tx atomic insert.
 *   - `WorkflowsModule` — re-uses the existing `WorkflowsService.trigger()`
 *     so post-confirm Temporal start re-uses the proven path.
 *   - `HttpModule` — needed by `AiServiceClient` for the parse + materialise
 *     RPC calls.
 *   - `ScheduleModule.forRoot()` — registers `@Cron` decorators for the
 *     hourly TTL cleanup. Idempotent if another module already registered
 *     it (NestJS dedupes globals).
 *
 * The module is imported into `AppModule` (additive — existing modules
 * untouched, see `app.module.ts`).
 */
@Module({
  imports: [
    TypeOrmModule.forFeature([ParseSession]),
    ObjectStoreModule,
    BidsModule,
    WorkflowsModule,
    HttpModule.register({ timeout: 30_000, maxRedirects: 2 }),
    ScheduleModule.forRoot(),
  ],
  controllers: [ParseController],
  providers: [
    ParseSessionsService,
    MaterializeService,
    AiServiceClient,
    ParseSessionTtlCleanupCron,
  ],
  exports: [ParseSessionsService, MaterializeService],
})
export class ParseSessionsModule {}
