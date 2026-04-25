import { MigrationInterface, QueryRunner } from 'typeorm';

/**
 * Phase 3.2b — create `bids` + `audit_log` tables.
 *
 * `bids` replaces the in-memory Map in `BidsService`; `audit_log` backs the
 * `AuditInterceptor` emitted by `@Roles(...)`-decorated routes.
 */
export class InitBidsAndAuditLog1714000000001 implements MigrationInterface {
  name = 'InitBidsAndAuditLog1714000000001';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "bids" (
        "id" uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        "client_name" varchar NOT NULL,
        "industry" varchar NOT NULL,
        "region" varchar NOT NULL,
        "deadline" varchar NOT NULL,
        "scope_summary" text NOT NULL,
        "technology_keywords" text NOT NULL DEFAULT '[]',
        "estimated_profile" varchar(8) NOT NULL DEFAULT 'M',
        "status" varchar(16) NOT NULL DEFAULT 'DRAFT',
        "workflow_id" varchar NULL,
        "created_at" varchar NOT NULL,
        "updated_at" varchar NOT NULL
      )
    `);
    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS "ix_bids_workflow_id" ON "bids" ("workflow_id")
    `);

    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "audit_log" (
        "id" uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        "timestamp" varchar NOT NULL DEFAULT (now()::text),
        "user_sub" varchar NOT NULL,
        "username" varchar NOT NULL,
        "roles" text NOT NULL,
        "action" varchar NOT NULL,
        "resource_type" varchar NOT NULL,
        "resource_id" varchar NULL,
        "status_code" integer NOT NULL,
        "metadata" text NULL
      )
    `);
    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS "ix_audit_user_time" ON "audit_log" ("user_sub", "timestamp")
    `);
    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS "ix_audit_resource" ON "audit_log" ("resource_type", "resource_id")
    `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`DROP INDEX IF EXISTS "ix_audit_resource"`);
    await queryRunner.query(`DROP INDEX IF EXISTS "ix_audit_user_time"`);
    await queryRunner.query(`DROP TABLE IF EXISTS "audit_log"`);
    await queryRunner.query(`DROP INDEX IF EXISTS "ix_bids_workflow_id"`);
    await queryRunner.query(`DROP TABLE IF EXISTS "bids"`);
  }
}
