import { Module } from '@nestjs/common';
import { BidsController } from './bids.controller';
import { BidsService } from './bids.service';
import { LangfuseLinkService } from './langfuse-link.service';

@Module({
  controllers: [BidsController],
  providers: [BidsService, LangfuseLinkService],
  exports: [BidsService],
})
export class BidsModule {}
