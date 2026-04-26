import { Injectable, Logger, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { EntityManager, Repository } from 'typeorm';
import type { ParseSession } from '../parse-sessions/parse-session.entity';
import type { ConfirmRequestDto } from '../parse-sessions/dto/confirm-request.dto';
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

    const event = {
      event: 'bid.created',
      bidId: saved.id,
      createdBy: createdBy ?? 'system',
      payload: saved,
    };
    try {
      await this.redis.publishStream(BID_STREAM, event);
    } catch (err) {
      this.logger.warn(
        `Failed to publish bid.created to stream: ${(err as Error).message} — routing to DLQ`,
      );
      try {
        await this.redis.deadLetter(BID_STREAM, event, err as Error);
      } catch (dlqErr) {
        // Both Redis paths failed — the cluster is likely fully down.
        // Last-resort: dump the payload to logs so an oncall can replay
        // by hand. The bid row is already persisted in Postgres so the
        // user request still succeeds.
        this.logger.error(
          `Stream + DLQ both failed for bid=${saved.id}: ${(dlqErr as Error).message}. Payload: ${JSON.stringify(event)}`,
        );
      }
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

  /**
   * S0.5 Wave 2B — atomic bid creation from a confirmed parse session.
   *
   * Builds the entity from `session.suggestedBidCard` then layers on user
   * overrides supplied at confirm time (client_name / industry / region /
   * deadline / profile_override / name). Optional `em` parameter lets the
   * caller chain inserts inside an existing TypeORM transaction — required
   * by `MaterializeService` so a downstream failure (vault write,
   * Temporal start) rolls back the bids row too.
   *
   * The post-confirm bid carries no `workflow_id` yet (Decision 9: workflow
   * starts AFTER materialise succeeds). Callers must invoke
   * `attachWorkflow()` once Temporal returns.
   *
   * Existing `create()` is untouched — manual `POST /bids` keeps working.
   */
  async createFromParseSession(
    session: ParseSession,
    overrides: ConfirmRequestDto,
    em?: EntityManager,
  ): Promise<Bid> {
    const repo = em ? em.getRepository(Bid) : this.bids;
    const card = (session.suggestedBidCard ?? {}) as Record<string, unknown>;
    const now = new Date().toISOString();

    const clientName =
      overrides.client_name ?? (card.client_name as string | undefined) ?? '';
    const industry =
      overrides.industry ?? (card.industry as string | undefined) ?? '';
    const region =
      overrides.region ?? (card.region as string | undefined) ?? '';
    const deadline =
      overrides.deadline ?? (card.deadline as string | undefined) ?? now;
    const scopeSummary =
      (card.scope_summary as string | undefined) ?? '';
    const technologyKeywords =
      (card.technology_keywords as string[] | undefined) ?? [];
    const estimatedProfile =
      (overrides.profile_override as BidProfile | undefined) ??
      ((card.estimated_profile as BidProfile | undefined) ?? BidProfile.M);

    const entity = repo.create({
      clientName,
      industry,
      region,
      deadline,
      scopeSummary,
      technologyKeywords,
      estimatedProfile,
      status: BidStatus.DRAFT,
      workflowId: null,
      createdAt: now,
      updatedAt: now,
    });
    return repo.save(entity);
  }
}
