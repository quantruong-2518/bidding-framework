import { HttpModule } from '@nestjs/axios';
import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { AuditLog } from '../audit/audit-log.entity';
import { BidsModule } from '../bids/bids.module';
import { AuditDashboardController } from './audit-dashboard.controller';
import { AuditDashboardService } from './audit-dashboard.service';
import { AuditLogAggregator } from './aggregators/audit-log.aggregator';
import { LangfuseAggregator } from './aggregators/langfuse.aggregator';
import { TemporalAggregator } from './aggregators/temporal.aggregator';

@Module({
  imports: [
    HttpModule.register({ timeout: 10_000, maxRedirects: 2 }),
    TypeOrmModule.forFeature([AuditLog]),
    BidsModule,
  ],
  controllers: [AuditDashboardController],
  providers: [
    AuditDashboardService,
    AuditLogAggregator,
    LangfuseAggregator,
    TemporalAggregator,
  ],
  exports: [AuditDashboardService],
})
export class AuditDashboardModule {}
