import { MigrationInterface, QueryRunner } from 'typeorm';

/**
 * Conv 16a — CQRS read model for bid workflow state.
 *
 * `bid_state_transitions` is an append-only event log written by the NestJS
 * `BidStateProjectionConsumer` for every entry consumed off the
 * `bid.transitions` Redis stream. `bid_state_projection` is the 1-row-per-bid
 * read model that downstream queries hit (replaces ad-hoc `Temporal query`
 * calls). Both tables are idempotent under XREADGROUP at-least-once delivery
 * thanks to `UNIQUE (bid_id, transition_seq)` on the log.
 */
export class CreateBidStateProjection1714000000002
  implements MigrationInterface
{
  name = 'CreateBidStateProjection1714000000002';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "bid_state_transitions" (
        "id" BIGSERIAL PRIMARY KEY,
        "bid_id" uuid NOT NULL,
        "workflow_id" varchar(255) NOT NULL,
        "transition_seq" integer NOT NULL,
        "from_state" varchar(32) NULL,
        "to_state" varchar(32) NOT NULL,
        "profile" varchar(8) NOT NULL,
        "tenant_id" varchar(128) NOT NULL,
        "artifact_keys" jsonb NOT NULL DEFAULT '[]'::jsonb,
        "llm_cost_delta" numeric(12,6) NULL,
        "occurred_at" timestamptz NOT NULL,
        "recorded_at" timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT "uq_bst_bid_seq" UNIQUE ("bid_id", "transition_seq")
      )
    `);
    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS "ix_bst_bid_seq" ON "bid_state_transitions" ("bid_id", "transition_seq" DESC)
    `);
    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS "ix_bst_recorded" ON "bid_state_transitions" ("recorded_at" DESC)
    `);
    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS "ix_bst_tenant_state" ON "bid_state_transitions" ("tenant_id", "to_state")
    `);

    await queryRunner.query(`
      CREATE TABLE IF NOT EXISTS "bid_state_projection" (
        "bid_id" uuid PRIMARY KEY,
        "workflow_id" varchar(255) NOT NULL,
        "tenant_id" varchar(128) NOT NULL,
        "current_state" varchar(32) NOT NULL,
        "profile" varchar(8) NOT NULL,
        "client_name" varchar(255) NOT NULL DEFAULT '',
        "industry" varchar(64) NOT NULL DEFAULT '',
        "last_transition_seq" integer NOT NULL,
        "last_transition_at" timestamptz NOT NULL,
        "artifacts_done" jsonb NOT NULL DEFAULT '{}'::jsonb,
        "is_terminal" boolean NOT NULL DEFAULT FALSE,
        "outcome" varchar(16) NULL,
        "total_llm_cost_usd" numeric(12,6) NOT NULL DEFAULT 0,
        "updated_at" timestamptz NOT NULL DEFAULT now()
      )
    `);
    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS "ix_bsp_state" ON "bid_state_projection" ("current_state")
    `);
    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS "ix_bsp_tenant_state" ON "bid_state_projection" ("tenant_id", "current_state")
    `);
    await queryRunner.query(`
      CREATE INDEX IF NOT EXISTS "ix_bsp_active" ON "bid_state_projection" ("is_terminal", "last_transition_at" DESC) WHERE "is_terminal" = FALSE
    `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`DROP INDEX IF EXISTS "ix_bsp_active"`);
    await queryRunner.query(`DROP INDEX IF EXISTS "ix_bsp_tenant_state"`);
    await queryRunner.query(`DROP INDEX IF EXISTS "ix_bsp_state"`);
    await queryRunner.query(`DROP TABLE IF EXISTS "bid_state_projection"`);
    await queryRunner.query(`DROP INDEX IF EXISTS "ix_bst_tenant_state"`);
    await queryRunner.query(`DROP INDEX IF EXISTS "ix_bst_recorded"`);
    await queryRunner.query(`DROP INDEX IF EXISTS "ix_bst_bid_seq"`);
    await queryRunner.query(`DROP TABLE IF EXISTS "bid_state_transitions"`);
  }
}
