import {
  Column,
  CreateDateColumn,
  Entity,
  Index,
  PrimaryGeneratedColumn,
  Unique,
} from 'typeorm';

/**
 * Append-only event log for bid workflow state transitions.
 *
 * One row per `bid.transitions` Redis stream entry consumed by
 * `BidStateProjectionConsumer`. The compound `UNIQUE (bid_id, transition_seq)`
 * makes XREADGROUP at-least-once delivery safe: a redelivered entry is a
 * no-op via `INSERT ... ON CONFLICT DO NOTHING`.
 */
@Entity({ name: 'bid_state_transitions' })
@Unique('uq_bst_bid_seq', ['bidId', 'transitionSeq'])
@Index('ix_bst_bid_seq', ['bidId', 'transitionSeq'])
@Index('ix_bst_recorded', ['recordedAt'])
@Index('ix_bst_tenant_state', ['tenantId', 'toState'])
export class BidStateTransition {
  @PrimaryGeneratedColumn()
  id!: number;

  @Column({ name: 'bid_id', type: 'varchar' })
  bidId!: string;

  @Column({ name: 'workflow_id', type: 'varchar', length: 255 })
  workflowId!: string;

  @Column({ name: 'transition_seq', type: 'integer' })
  transitionSeq!: number;

  @Column({ name: 'from_state', type: 'varchar', length: 32, nullable: true })
  fromState!: string | null;

  @Column({ name: 'to_state', type: 'varchar', length: 32 })
  toState!: string;

  @Column({ type: 'varchar', length: 8 })
  profile!: string;

  @Column({ name: 'tenant_id', type: 'varchar', length: 128 })
  tenantId!: string;

  @Column({ name: 'artifact_keys', type: 'simple-json', default: () => "'[]'" })
  artifactKeys!: string[];

  @Column({
    name: 'llm_cost_delta',
    type: 'decimal',
    precision: 12,
    scale: 6,
    nullable: true,
    transformer: {
      to: (v: number | null | undefined): number | null =>
        v == null ? null : Number(v),
      from: (v: string | number | null): number | null =>
        v == null ? null : typeof v === 'number' ? v : Number(v),
    },
  })
  llmCostDelta!: number | null;

  @Column({ name: 'occurred_at', type: 'varchar' })
  occurredAt!: string;

  @CreateDateColumn({ name: 'recorded_at', type: 'varchar' })
  recordedAt!: Date;
}
