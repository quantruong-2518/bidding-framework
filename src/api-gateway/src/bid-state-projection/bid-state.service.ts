import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { BidStateProjection } from './bid-state-projection.entity';
import { BidStateView } from './bid-state.types';

/**
 * Read-side service for the bid state CQRS projection.
 *
 * Reads only — writes happen in `BidStateProjectionConsumer`. Keeps the
 * controller free of TypeORM concerns and provides a stable view shape.
 */
@Injectable()
export class BidStateService {
  constructor(
    @InjectRepository(BidStateProjection)
    private readonly projections: Repository<BidStateProjection>,
  ) {}

  async getStateByBidId(bidId: string): Promise<BidStateView> {
    const row = await this.projections.findOne({ where: { bidId } });
    if (!row) {
      throw new NotFoundException(
        `No state projection for bid ${bidId} — workflow may not have started`,
      );
    }
    return this.toView(row);
  }

  private toView(row: BidStateProjection): BidStateView {
    return {
      bidId: row.bidId,
      workflowId: row.workflowId,
      tenantId: row.tenantId,
      currentState: row.currentState,
      profile: row.profile,
      clientName: row.clientName,
      industry: row.industry,
      lastTransitionSeq: row.lastTransitionSeq,
      lastTransitionAt: row.lastTransitionAt,
      artifactsDone: row.artifactsDone ?? {},
      isTerminal: row.isTerminal,
      outcome: row.outcome,
      totalLlmCostUsd: Number(row.totalLlmCostUsd ?? 0),
      updatedAt:
        row.updatedAt instanceof Date
          ? row.updatedAt.toISOString()
          : String(row.updatedAt ?? ''),
    };
  }
}
