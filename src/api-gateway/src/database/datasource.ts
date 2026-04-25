import 'reflect-metadata';
import { DataSource } from 'typeorm';
import { DATABASE_ENTITIES, DATABASE_MIGRATIONS } from './database.module';

/**
 * Standalone DataSource for the TypeORM CLI:
 *   npx typeorm migration:run -d dist/database/datasource.js
 *
 * The NestJS app uses `TypeOrmModule.forRootAsync` in `DatabaseModule`, which
 * is the runtime path (`migrationsRun: true` on boot). This file exists so
 * operators can manually inspect / revert migrations.
 */
export const AppDataSource = new DataSource({
  type: 'postgres',
  url:
    process.env.POSTGRES_URL ??
    process.env.DATABASE_URL ??
    'postgresql://bidding:bidding@localhost:5432/bidding_db',
  entities: DATABASE_ENTITIES,
  migrations: DATABASE_MIGRATIONS,
  migrationsRun: false,
  synchronize: false,
});
