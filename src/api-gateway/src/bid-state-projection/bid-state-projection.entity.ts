import { Column, Entity, Index, PrimaryColumn, UpdateDateColumn } from 'typeorm';

/**
 * 1-row-per-bid CQRS read model.
 *
 * Upserted by `BidStateProjectionConsumer` after each transition is appended
 * to `bid_state_transitions`. Stale entries (older `last_transition_seq`)
 * are skipped at upsert time so out-of-order delivery / replay can't roll
 * the projection backward.
 */
@Entity({ name: 'bid_state_projection' })
@Index('ix_bsp_state', ['currentState'])
@Index('ix_bsp_tenant_state', ['tenantId', 'currentState'])
export class BidStateProjection {
  @PrimaryColumn({ name: 'bid_id', type: 'varchar' })
  bidId!: string;

  @Column({ name: 'workflow_id', type: 'varchar', length: 255 })
  workflowId!: string;

  @Column({ name: 'tenant_id', type: 'varchar', length: 128 })
  tenantId!: string;

  @Column({ name: 'current_state', type: 'varchar', length: 32 })
  currentState!: string;

  @Column({ type: 'varchar', length: 8 })
  profile!: string;

  @Column({ name: 'client_name', type: 'varchar', length: 255, default: '' })
  clientName!: string;

  @Column({ type: 'varchar', length: 64, default: '' })
  industry!: string;

  @Column({ name: 'last_transition_seq', type: 'integer' })
  lastTransitionSeq!: number;

  @Column({ name: 'last_transition_at', type: 'varchar' })
  lastTransitionAt!: string;

  /**
   * `{ <artifact_key>: <occurred_at_iso> }` — append-only set of which artifact
   * fields have been written across the whole bid history.
   */
  @Column({
    name: 'artifacts_done',
    type: 'simple-json',
    default: () => "'{}'",
  })
  artifactsDone!: Record<string, string>;

  @Column({ name: 'is_terminal', type: 'boolean', default: false })
  isTerminal!: boolean;

  @Column({ type: 'varchar', length: 16, nullable: true })
  outcome!: string | null;

  @Column({
    name: 'total_llm_cost_usd',
    type: 'numeric',
    precision: 12,
    scale: 6,
    default: 0,
    transformer: {
      to: (v: number | null | undefined) => v ?? 0,
      from: (v: string | number | null) =>
        v == null ? 0 : typeof v === 'number' ? v : Number(v),
    },
  })
  totalLlmCostUsd!: number;

  @UpdateDateColumn({ name: 'updated_at', type: 'varchar' })
  updatedAt!: Date;
}
