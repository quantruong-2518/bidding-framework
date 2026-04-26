import { MigrationInterface, QueryRunner } from 'typeorm';

/**
 * S0.5 Wave 1 — transient parse-session table.
 *
 * `parse_sessions` holds the LLM parse output (atoms + anchor + summary +
 * manifest) between multi-file upload (`POST /bids/parse`) and human
 * confirmation (`POST /bids/parse/:sid/confirm`). Pre-confirm, no row in
 * `bids` exists and nothing is written to the kb-vault. Post-confirm, the
 * row's `confirmed_bid_id` is populated and the materialise activity copies
 * atoms into the vault tree.
 *
 * Lifecycle (Decision 10): PARSING → READY → CONFIRMED | ABANDONED | FAILED.
 * Default TTL is 7 days from `created_at`; the hourly cleanup cron drops
 * rows + their MinIO `parse_sessions/<sid>/` prefix once `expires_at` lapses
 * AND status ∈ (PARSING, READY).
 */
export class CreateParseSessions1714000000003 implements MigrationInterface {
  name = 'CreateParseSessions1714000000003';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "parse_sessions" (
        "id" uuid PRIMARY KEY,
        "tenant_id" varchar(64) NOT NULL,
        "user_id" varchar(128) NOT NULL,
        "status" varchar(16) NOT NULL,
        "suggested_bid_card" jsonb NULL,
        "atoms" jsonb NULL,
        "anchor_md" text NULL,
        "summary_md" text NULL,
        "manifest" jsonb NULL,
        "conflicts" jsonb NULL,
        "open_questions" jsonb NULL,
        "parse_error" text NULL,
        "expires_at" timestamptz NOT NULL,
        "created_at" timestamptz NOT NULL DEFAULT now(),
        "updated_at" timestamptz NOT NULL DEFAULT now(),
        "confirmed_bid_id" uuid NULL,
        "confirmed_at" timestamptz NULL,
        "confirmed_by" varchar(128) NULL,
        CONSTRAINT "ck_parse_sessions_status" CHECK (
          "status" IN ('PARSING','READY','CONFIRMED','ABANDONED','FAILED')
        )
      )
    `);
    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS "ix_parse_sessions_tenant_status"
        ON "parse_sessions" ("tenant_id", "status")
    `);
    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS "ix_parse_sessions_expires"
        ON "parse_sessions" ("expires_at")
        WHERE "status" IN ('PARSING','READY')
    `);
    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS "ix_parse_sessions_user"
        ON "parse_sessions" ("user_id", "created_at" DESC)
    `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`DROP INDEX IF EXISTS "ix_parse_sessions_user"`);
    await queryRunner.query(`DROP INDEX IF EXISTS "ix_parse_sessions_expires"`);
    await queryRunner.query(
      `DROP INDEX IF EXISTS "ix_parse_sessions_tenant_status"`,
    );
    await queryRunner.query(`DROP TABLE IF EXISTS "parse_sessions"`);
  }
}
