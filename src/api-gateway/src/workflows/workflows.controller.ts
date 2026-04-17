import {
  BadRequestException,
  Body,
  Controller,
  Get,
  Param,
  ParseUUIDPipe,
  Post,
  UseGuards,
} from '@nestjs/common';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import { RolesGuard } from '../auth/roles.guard';
import { Roles } from '../auth/roles.decorator';
import { WorkflowsService } from './workflows.service';
import { TriageSignalDto } from './triage-signal.dto';
import { ReviewSignalDto } from './review-signal.dto';

/**
 * Artifact keys exposed by Python `BidState`. Keep in sync with
 * `src/ai-service/workflows/models.py::BidState` and
 * `src/ai-service/workflows/artifacts.py`.
 */
export const ARTIFACT_KEYS = [
  'bid_card',
  'triage',
  'scoping',
  'ba_draft',
  'sa_draft',
  'domain_notes',
  'convergence',
  'hld',
  'wbs',
  'pricing',
  'proposal_package',
  'reviews',
  'submission',
  'retrospective',
] as const;

export type ArtifactKey = (typeof ARTIFACT_KEYS)[number];

function assertArtifactKey(value: string): asserts value is ArtifactKey {
  if (!(ARTIFACT_KEYS as readonly string[]).includes(value)) {
    throw new BadRequestException(
      `Unknown artifact type '${value}'. Allowed: ${ARTIFACT_KEYS.join(', ')}.`,
    );
  }
}

@UseGuards(JwtAuthGuard, RolesGuard)
@Controller('bids/:id/workflow')
export class WorkflowsController {
  constructor(private readonly workflowsService: WorkflowsService) {}

  @Post()
  @Roles('admin', 'bid_manager')
  trigger(@Param('id', new ParseUUIDPipe()) id: string): Promise<unknown> {
    return this.workflowsService.trigger(id);
  }

  @Post('triage-signal')
  @Roles('admin', 'bid_manager', 'ba', 'sa', 'qc')
  signal(
    @Param('id', new ParseUUIDPipe()) id: string,
    @Body() dto: TriageSignalDto,
  ): Promise<unknown> {
    return this.workflowsService.sendTriageSignal(id, dto);
  }

  @Post('review-signal')
  @Roles('admin', 'bid_manager', 'qc', 'sa', 'domain_expert', 'solution_lead')
  review(
    @Param('id', new ParseUUIDPipe()) id: string,
    @Body() dto: ReviewSignalDto,
  ): Promise<unknown> {
    return this.workflowsService.sendReviewSignal(id, dto);
  }

  @Get('status')
  status(@Param('id', new ParseUUIDPipe()) id: string): Promise<unknown> {
    return this.workflowsService.getStatus(id);
  }

  @Get('artifacts/:type')
  async artifact(
    @Param('id', new ParseUUIDPipe()) id: string,
    @Param('type') type: string,
  ): Promise<unknown> {
    assertArtifactKey(type);
    return this.workflowsService.getArtifact(id, type);
  }
}
