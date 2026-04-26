import { Module } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { TypeOrmModule, TypeOrmModuleOptions } from '@nestjs/typeorm';
import { AuditLog } from '../audit/audit-log.entity';
import { BidStateProjection } from '../bid-state-projection/bid-state-projection.entity';
import { BidStateTransition } from '../bid-state-projection/bid-state-transition.entity';
import { Bid } from '../bids/bid.entity';
import { ParseSession } from '../parse-sessions/parse-session.entity';
import { CreateBidStateProjection1714000000002 } from './migrations/1714000000002-create-bid-state-projection';
import { CreateParseSessions1714000000003 } from './migrations/1714000000003-create-parse-sessions';
import { InitBidsAndAuditLog1714000000001 } from './migrations/1714000000001-init-bids-and-audit-log';

export const DATABASE_ENTITIES = [
  Bid,
  AuditLog,
  BidStateTransition,
  BidStateProjection,
  ParseSession,
];
export const DATABASE_MIGRATIONS = [
  InitBidsAndAuditLog1714000000001,
  CreateBidStateProjection1714000000002,
  CreateParseSessions1714000000003,
];

/**
 * Build the TypeORM connection options from the `POSTGRES_URL` env var.
 *
 * Dev/prod → Postgres (via `pg`). Tests provision their own TypeOrmModule
 * with `type: 'better-sqlite3'` + `synchronize: true`, so this helper is
 * deliberately thin.
 */
export function buildTypeOrmOptions(
  config: ConfigService,
): TypeOrmModuleOptions {
  const url =
    config.get<string>('POSTGRES_URL') ??
    config.get<string>('DATABASE_URL') ??
    'postgresql://bidding:bidding@postgres:5432/bidding_db';

  return {
    type: 'postgres',
    url,
    entities: DATABASE_ENTITIES,
    migrations: DATABASE_MIGRATIONS,
    migrationsRun: true,
    synchronize: false,
    logging: ['error', 'warn'],
  };
}

@Module({
  imports: [
    TypeOrmModule.forRootAsync({
      imports: [ConfigModule],
      inject: [ConfigService],
      useFactory: buildTypeOrmOptions,
    }),
  ],
})
export class DatabaseModule {}
