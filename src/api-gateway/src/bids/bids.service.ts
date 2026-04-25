import { Injectable, Logger, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { RedisService } from '../redis/redis.service';
import { Bid, BidProfile, BidStatus } from './bid.entity';
import { CreateBidDto } from './create-bid.dto';
import { UpdateBidDto } from './update-bid.dto';

export const BID_STREAM = 'bid.events';

@Injectable()
export class BidsService {
  private readonly logger = new Logger(BidsService.name);

  constructor(
    @InjectRepository(Bid) private readonly bids: Repository<Bid>,
    private readonly redis: RedisService,
  ) {}

  async create(dto: CreateBidDto, createdBy: string | undefined): Promise<Bid> {
    const now = new Date().toISOString();
    const entity = this.bids.create({
      clientName: dto.clientName,
      industry: dto.industry,
      region: dto.region,
      deadline: dto.deadline,
      scopeSummary: dto.scopeSummary,
      technologyKeywords: dto.technologyKeywords ?? [],
      estimatedProfile: dto.estimatedProfile ?? BidProfile.M,
      status: BidStatus.DRAFT,
      workflowId: null,
      createdAt: now,
      updatedAt: now,
    });
    const saved = await this.bids.save(entity);

    try {
      await this.redis.publishStream(BID_STREAM, {
        event: 'bid.created',
        bidId: saved.id,
        createdBy: createdBy ?? 'system',
        payload: saved,
      });
    } catch (err) {
      this.logger.warn(
        `Failed to publish bid.created to stream: ${(err as Error).message}`,
      );
    }
    return saved;
  }

  async findAll(): Promise<Bid[]> {
    return this.bids.find({ order: { createdAt: 'DESC' } });
  }

  async findOne(id: string): Promise<Bid> {
    const bid = await this.bids.findOne({ where: { id } });
    if (!bid) {
      throw new NotFoundException(`Bid ${id} not found`);
    }
    return bid;
  }

  async findByWorkflowId(workflowId: string): Promise<Bid | null> {
    return this.bids.findOne({ where: { workflowId } });
  }

  async update(id: string, dto: UpdateBidDto): Promise<Bid> {
    const bid = await this.findOne(id);
    Object.assign(bid, dto, { updatedAt: new Date().toISOString() });
    return this.bids.save(bid);
  }

  /**
   * Attach a Temporal workflow id to a bid (set by WorkflowsService after trigger).
   */
  async attachWorkflow(id: string, workflowId: string): Promise<Bid> {
    const bid = await this.findOne(id);
    bid.workflowId = workflowId;
    bid.status = BidStatus.IN_PROGRESS;
    bid.updatedAt = new Date().toISOString();
    return this.bids.save(bid);
  }

  async remove(id: string): Promise<void> {
    const result = await this.bids.delete(id);
    if (!result.affected) {
      throw new NotFoundException(`Bid ${id} not found`);
    }
  }
}
