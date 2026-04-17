import {
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

  @Get('status')
  status(@Param('id', new ParseUUIDPipe()) id: string): Promise<unknown> {
    return this.workflowsService.getStatus(id);
  }
}
