import { Column, Entity, Index, PrimaryGeneratedColumn } from 'typeorm';

export enum BidStatus {
  DRAFT = 'DRAFT',
  TRIAGED = 'TRIAGED',
  IN_PROGRESS = 'IN_PROGRESS',
  WON = 'WON',
  LOST = 'LOST',
}

export enum BidProfile {
  S = 'S',
  M = 'M',
  L = 'L',
  XL = 'XL',
}

@Entity({ name: 'bids' })
@Index('ix_bids_workflow_id', ['workflowId'])
export class Bid {
  @PrimaryGeneratedColumn('uuid')
  id!: string;

  @Column({ name: 'client_name', type: 'varchar' })
  clientName!: string;

  @Column({ type: 'varchar' })
  industry!: string;

  @Column({ type: 'varchar' })
  region!: string;

  @Column({ type: 'varchar' })
  deadline!: string; // ISO-8601 date string

  @Column({ name: 'scope_summary', type: 'text' })
  scopeSummary!: string;

  @Column({
    name: 'technology_keywords',
    type: 'simple-json',
    default: () => "'[]'",
  })
  technologyKeywords!: string[];

  @Column({
    name: 'estimated_profile',
    type: 'varchar',
    length: 8,
    default: BidProfile.M,
  })
  estimatedProfile!: BidProfile;

  @Column({ type: 'varchar', length: 16, default: BidStatus.DRAFT })
  status!: BidStatus;

  @Column({ name: 'workflow_id', type: 'varchar', nullable: true })
  workflowId!: string | null;

  @Column({
    name: 'created_at',
    type: 'varchar',
  })
  createdAt!: string;

  @Column({
    name: 'updated_at',
    type: 'varchar',
  })
  updatedAt!: string;
}
