import { Injectable, Logger, NotFoundException } from '@nestjs/common';
import { v4 as uuidv4 } from 'uuid';
import { RedisService } from '../redis/redis.service';
import { Bid, BidProfile, BidStatus } from './bid.entity';
import { CreateBidDto } from './create-bid.dto';
import { UpdateBidDto } from './update-bid.dto';

export const BID_STREAM = 'bid.events';

@Injectable()
export class BidsService {
  private readonly logger = new Logger(BidsService.name);

  // in-memory store — replaced in Phase 1.x (Postgres via TypeORM/Prisma)
  private readonly bids = new Map<string, Bid>();

  constructor(private readonly redis: RedisService) {}

  async create(dto: CreateBidDto, createdBy: string | undefined): Promise<Bid> {
    const now = new Date().toISOString();
    const bid: Bid = {
      id: uuidv4(),
      clientName: dto.clientName,
      industry: dto.industry,
      region: dto.region,
      deadline: dto.deadline,
      scopeSummary: dto.scopeSummary,
      technologyKeywords: dto.technologyKeywords,
      estimatedProfile: dto.estimatedProfile ?? BidProfile.M,
      status: BidStatus.DRAFT,
      workflowId: null,
      createdAt: now,
      updatedAt: now,
    };
    this.bids.set(bid.id, bid);

    try {
      await this.redis.publishStream(BID_STREAM, {
        event: 'bid.created',
        bidId: bid.id,
        createdBy: createdBy ?? 'system',
        payload: bid,
      });
    } catch (err) {
      this.logger.warn(
        `Failed to publish bid.created to stream: ${(err as Error).message}`,
      );
    }
    return bid;
  }

  findAll(): Bid[] {
    return Array.from(this.bids.values());
  }

  findOne(id: string): Bid {
    const bid = this.bids.get(id);
    if (!bid) {
      throw new NotFoundException(`Bid ${id} not found`);
    }
    return bid;
  }

  findByWorkflowId(workflowId: string): Bid | undefined {
    for (const bid of this.bids.values()) {
      if (bid.workflowId === workflowId) return bid;
    }
    return undefined;
  }

  update(id: string, dto: UpdateBidDto): Bid {
    const bid = this.findOne(id);
    Object.assign(bid, dto, { updatedAt: new Date().toISOString() });
    this.bids.set(id, bid);
    return bid;
  }

  /**
   * Attach a Temporal workflow id to a bid (set by WorkflowsService after trigger).
   */
  attachWorkflow(id: string, workflowId: string): Bid {
    const bid = this.findOne(id);
    bid.workflowId = workflowId;
    bid.status = BidStatus.IN_PROGRESS;
    bid.updatedAt = new Date().toISOString();
    this.bids.set(id, bid);
    return bid;
  }

  remove(id: string): void {
    if (!this.bids.delete(id)) {
      throw new NotFoundException(`Bid ${id} not found`);
    }
  }
}
