import { Injectable, Logger } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { AuditLog } from './audit-log.entity';

export interface AuditRecord {
  userSub: string;
  username: string;
  roles: string[];
  action: string;
  resourceType: string;
  resourceId: string | null;
  statusCode: number;
  metadata?: Record<string, unknown> | null;
}

/**
 * Persists role-gated HTTP activity to the `audit_log` table.
 *
 * Fire-and-forget by design: `record()` never throws. A DB failure is logged
 * but the originating request is NOT impacted — availability > audit fidelity.
 * Phase 3.3 audit dashboard queries this table.
 */
@Injectable()
export class AuditService {
  private readonly logger = new Logger(AuditService.name);

  constructor(
    @InjectRepository(AuditLog)
    private readonly repo: Repository<AuditLog>,
  ) {}

  async record(entry: AuditRecord): Promise<void> {
    try {
      const row = this.repo.create({
        userSub: entry.userSub,
        username: entry.username,
        roles: entry.roles,
        action: entry.action,
        resourceType: entry.resourceType,
        resourceId: entry.resourceId,
        statusCode: entry.statusCode,
        metadata: entry.metadata ?? null,
      });
      await this.repo.save(row);
    } catch (err) {
      this.logger.warn(
        `audit.record failed (swallowed): ${(err as Error).message}`,
      );
    }
  }
}
