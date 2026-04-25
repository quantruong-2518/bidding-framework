import {
  BadRequestException,
  Controller,
  Get,
  Header,
  Param,
  ParseUUIDPipe,
  Query,
  UseGuards,
} from '@nestjs/common';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import { RolesGuard } from '../auth/roles.guard';
import { Roles } from '../auth/roles.decorator';
import { SkipAudit } from '../audit/skip-audit.decorator';
import { AuditDashboardService } from './audit-dashboard.service';
import type {
  BidAuditDetail,
  CostsResponse,
  DashboardSummary,
  SummaryQuery,
} from './types';

const DATE_REGEX = /^\d{4}-\d{2}-\d{2}$/;

function parseDateRange(from?: string, to?: string): { from: string; to: string } {
  const today = new Date();
  const defaultTo = today.toISOString().slice(0, 10);
  const defaultFromDate = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);
  const defaultFrom = defaultFromDate.toISOString().slice(0, 10);
  const f = from ?? defaultFrom;
  const t = to ?? defaultTo;
  if (!DATE_REGEX.test(f) || !DATE_REGEX.test(t)) {
    throw new BadRequestException('Expected from/to as YYYY-MM-DD.');
  }
  return { from: f, to: t };
}

@UseGuards(JwtAuthGuard, RolesGuard)
@SkipAudit() // Dashboard reads are observability, not decisions — muted class-wide to keep audit_log focused on writes.
@Controller()
export class AuditDashboardController {
  constructor(private readonly service: AuditDashboardService) {}

  @Get('bids/:id/audit')
  @Roles('admin', 'bid_manager', 'qc')
  async getBidAudit(
    @Param('id', new ParseUUIDPipe()) id: string,
  ): Promise<BidAuditDetail> {
    return this.service.getBidDetail(id);
  }

  @Get('dashboard/audit')
  @Roles('admin')
  async getSummary(
    @Query('from') from?: string,
    @Query('to') to?: string,
    @Query('role') role?: string,
    @Query('status') status?: string,
    @Query('profile') profile?: string,
    @Query('client') client?: string,
    @Query('page') page?: string,
    @Query('limit') limit?: string,
  ): Promise<DashboardSummary> {
    const range = parseDateRange(from, to);
    const query: SummaryQuery = {
      ...range,
      role,
      status,
      profile,
      client,
      page: page ? Number(page) : undefined,
      limit: limit ? Number(limit) : undefined,
    };
    return this.service.getSummary(query);
  }

  @Get('dashboard/audit.csv')
  @Roles('admin')
  @Header('Content-Type', 'text/csv; charset=utf-8')
  @Header('Content-Disposition', 'attachment; filename="audit-summary.csv"')
  async exportCsv(
    @Query('from') from?: string,
    @Query('to') to?: string,
    @Query('role') role?: string,
    @Query('status') status?: string,
    @Query('profile') profile?: string,
    @Query('client') client?: string,
  ): Promise<string> {
    const range = parseDateRange(from, to);
    const summary = await this.service.getSummary({
      ...range,
      role,
      status,
      profile,
      client,
    });
    return this.service.summaryToCsv(summary);
  }

  @Get('dashboard/costs')
  @Roles('admin')
  async getCosts(
    @Query('from') from?: string,
    @Query('to') to?: string,
    @Query('groupBy') groupBy?: string,
  ): Promise<CostsResponse> {
    const range = parseDateRange(from, to);
    const gb =
      groupBy === 'bid' || groupBy === 'state' || groupBy === 'agent'
        ? groupBy
        : 'agent';
    return this.service.getCosts({ ...range, groupBy: gb });
  }
}
