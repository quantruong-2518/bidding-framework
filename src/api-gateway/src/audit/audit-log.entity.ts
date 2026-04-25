import {
  Column,
  CreateDateColumn,
  Entity,
  Index,
  PrimaryGeneratedColumn,
} from 'typeorm';

/**
 * Per-request audit row for RBAC-gated HTTP endpoints.
 *
 * Written by `AuditInterceptor` for any route that declares `@Roles(...)`.
 * Public routes (e.g. `/health`) are skipped. One row per request; status
 * code + `metadata` capture whether the request succeeded or was rejected
 * (401 / 403 / 404 / 5xx).
 */
@Entity({ name: 'audit_log' })
@Index('ix_audit_user_time', ['userSub', 'timestamp'])
@Index('ix_audit_resource', ['resourceType', 'resourceId'])
export class AuditLog {
  @PrimaryGeneratedColumn('uuid')
  id!: string;

  @CreateDateColumn({ name: 'timestamp', type: 'varchar' })
  timestamp!: Date;

  @Column({ name: 'user_sub', type: 'varchar' })
  userSub!: string;

  @Column({ type: 'varchar' })
  username!: string;

  /** Roles as a JSON-encoded string array — portable across Postgres + SQLite. */
  @Column({ type: 'simple-json' })
  roles!: string[];

  /** e.g. `"POST /bids/:id/workflow/artifacts/:type"` (route template, not concrete path). */
  @Column({ type: 'varchar' })
  action!: string;

  @Column({ name: 'resource_type', type: 'varchar' })
  resourceType!: string;

  @Column({ name: 'resource_id', type: 'varchar', nullable: true })
  resourceId!: string | null;

  @Column({ name: 'status_code', type: 'integer' })
  statusCode!: number;

  @Column({ type: 'simple-json', nullable: true })
  metadata!: Record<string, unknown> | null;
}
