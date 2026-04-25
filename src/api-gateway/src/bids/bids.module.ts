import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Bid } from './bid.entity';
import { BidsController } from './bids.controller';
import { BidsService } from './bids.service';
import { LangfuseLinkService } from './langfuse-link.service';

@Module({
  imports: [TypeOrmModule.forFeature([Bid])],
  controllers: [BidsController],
  providers: [BidsService, LangfuseLinkService],
  exports: [BidsService],
})
export class BidsModule {}
