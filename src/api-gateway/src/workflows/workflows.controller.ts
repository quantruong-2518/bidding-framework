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
import { CurrentUser, type AuthenticatedUser } from '../auth/current-user.decorator';
import { AclService } from '../acl/acl.service';
import { ARTIFACT_KEYS, type ArtifactKey } from './artifact-keys';
import { WorkflowsService } from './workflows.service';
import { TriageSignalDto } from './triage-signal.dto';
import { ReviewSignalDto } from './review-signal.dto';

// Re-exported for existing imports (`../src/workflows/workflows.controller`).
export { ARTIFACT_KEYS, type ArtifactKey };

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
  constructor(
    private readonly workflowsService: WorkflowsService,
    private readonly acl: AclService,
  ) {}

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
    @CurrentUser() user: AuthenticatedUser | undefined,
  ): Promise<unknown> {
    return this.workflowsService.sendReviewSignal(id, dto, user?.roles ?? []);
  }

  @Get('status')
  @Roles('admin', 'bid_manager', 'ba', 'sa', 'qc', 'domain_expert', 'solution_lead')
  status(
    @Param('id', new ParseUUIDPipe()) id: string,
    @CurrentUser() user: AuthenticatedUser | undefined,
  ): Promise<unknown> {
    return this.workflowsService.getStatus(id, user?.roles ?? []);
  }

  @Get('artifacts/:type')
  @Roles('admin', 'bid_manager', 'ba', 'sa', 'qc', 'domain_expert', 'solution_lead')
  async artifact(
    @Param('id', new ParseUUIDPipe()) id: string,
    @Param('type') type: string,
    @CurrentUser() user: AuthenticatedUser | undefined,
  ): Promise<unknown> {
    assertArtifactKey(type);
    // Defence in depth: ai-service also filters BidState on x-user-roles,
    // but rejecting here avoids a pointless round-trip and produces 403
    // with a stable message regardless of workflow state.
    this.acl.assertVisible(user?.roles ?? [], type);
    return this.workflowsService.getArtifact(id, type, user?.roles ?? []);
  }
}
