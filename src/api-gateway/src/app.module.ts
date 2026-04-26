import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { APP_GUARD } from '@nestjs/core';
import { AclModule } from './acl/acl.module';
import { AppController } from './app.controller';
import { AuditDashboardModule } from './audit-dashboard/audit-dashboard.module';
import { AuditModule } from './audit/audit.module';
import { AuthModule } from './auth/auth.module';
import { JwtAuthGuard } from './auth/jwt-auth.guard';
import { RolesGuard } from './auth/roles.guard';
import { BidStateProjectionModule } from './bid-state-projection/bid-state-projection.module';
import { BidsModule } from './bids/bids.module';
import { DatabaseModule } from './database/database.module';
import { EventsModule } from './gateway/events.module';
import { ParsersModule } from './parsers/parsers.module';
import { RedisModule } from './redis/redis.module';
import { WorkflowsModule } from './workflows/workflows.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      envFilePath: ['.env.local', '.env'],
    }),
    DatabaseModule,
    AuditModule,
    AuthModule,
    AclModule,
    RedisModule,
    BidsModule,
    BidStateProjectionModule,
    WorkflowsModule,
    ParsersModule,
    EventsModule,
    AuditDashboardModule,
  ],
  controllers: [AppController],
  providers: [
    { provide: APP_GUARD, useClass: JwtAuthGuard },
    { provide: APP_GUARD, useClass: RolesGuard },
  ],
})
export class AppModule {}
