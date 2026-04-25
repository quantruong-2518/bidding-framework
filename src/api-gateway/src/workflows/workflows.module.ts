import { HttpModule } from '@nestjs/axios';
import { Module } from '@nestjs/common';
import { AclModule } from '../acl/acl.module';
import { BidsModule } from '../bids/bids.module';
import { WorkflowsController } from './workflows.controller';
import { WorkflowsService } from './workflows.service';

@Module({
  imports: [
    HttpModule.register({
      timeout: 10_000,
      maxRedirects: 2,
    }),
    AclModule,
    BidsModule,
  ],
  controllers: [WorkflowsController],
  providers: [WorkflowsService],
  exports: [WorkflowsService],
})
export class WorkflowsModule {}
