import {
  Column,
  CreateDateColumn,
  Entity,
  Index,
  PrimaryColumn,
  UpdateDateColumn,
} from 'typeorm';

/**
 * S0.5 Wave 1 — transient parse-session row.
 *
 * Holds the LLM parse output (suggested BidCard + atoms + anchor/summary +
 * manifest + conflicts + open_questions) between multi-file upload and human
 * confirmation. Lifecycle: PARSING → READY → CONFIRMED | ABANDONED | FAILED.
 *
 * `simple-json` columns map to Postgres `jsonb` (per project convention from
 * `bid-state-projection.entity.ts`). Test runs against sqlite store these as
 * TEXT — TypeORM's `simple-json` transformer round-trips both transparently.
 */
export type ParseSessionStatus =
  | 'PARSING'
  | 'READY'
  | 'CONFIRMED'
  | 'ABANDONED'
  | 'FAILED';

@Entity({ name: 'parse_sessions' })
@Index('ix_parse_sessions_tenant_status', ['tenantId', 'status'])
@Index('ix_parse_sessions_user', ['userId', 'createdAt'])
export class ParseSession {
  @PrimaryColumn({ type: 'varchar' })
  id!: string;

  @Column({ name: 'tenant_id', type: 'varchar', length: 64 })
  tenantId!: string;

  @Column({ name: 'user_id', type: 'varchar', length: 128 })
  userId!: string;

  @Column({ type: 'varchar', length: 16 })
  status!: ParseSessionStatus;

  @Column({
    name: 'suggested_bid_card',
    type: 'simple-json',
    nullable: true,
  })
  suggestedBidCard!: Record<string, unknown> | null;

  /** List of {frontmatter, body_md} entries — see ai-service AtomFrontmatter. */
  @Column({ type: 'simple-json', nullable: true })
  atoms!: unknown[] | null;

  @Column({ name: 'anchor_md', type: 'text', nullable: true })
  anchorMd!: string | null;

  @Column({ name: 'summary_md', type: 'text', nullable: true })
  summaryMd!: string | null;

  @Column({ type: 'simple-json', nullable: true })
  manifest!: Record<string, unknown> | null;

  @Column({ type: 'simple-json', nullable: true })
  conflicts!: unknown[] | null;

  @Column({ name: 'open_questions', type: 'simple-json', nullable: true })
  openQuestions!: unknown[] | null;

  @Column({ name: 'parse_error', type: 'text', nullable: true })
  parseError!: string | null;

  @Column({ name: 'expires_at', type: 'varchar' })
  expiresAt!: string;

  @CreateDateColumn({ name: 'created_at', type: 'varchar' })
  createdAt!: Date;

  @UpdateDateColumn({ name: 'updated_at', type: 'varchar' })
  updatedAt!: Date;

  @Column({ name: 'confirmed_bid_id', type: 'varchar', nullable: true })
  confirmedBidId!: string | null;

  @Column({ name: 'confirmed_at', type: 'varchar', nullable: true })
  confirmedAt!: string | null;

  @Column({
    name: 'confirmed_by',
    type: 'varchar',
    length: 128,
    nullable: true,
  })
  confirmedBy!: string | null;
}
