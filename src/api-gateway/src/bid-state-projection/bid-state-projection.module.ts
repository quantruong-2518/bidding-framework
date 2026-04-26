import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { BidStateProjectionConsumer } from './bid-state-projection.consumer';
import { BidStateProjection } from './bid-state-projection.entity';
import { BidStateTransition } from './bid-state-transition.entity';
import { BidStateController } from './bid-state.controller';
import { BidStateService } from './bid-state.service';

/**
 * CQRS read-side: durable Redis-stream consumer + Postgres projection table.
 *
 * The consumer starts on `onModuleInit` and stops on `onModuleDestroy`. The
 * controller exposes `GET /bids/:id/state` for any authenticated user.
 */
@Module({
  imports: [TypeOrmModule.forFeature([BidStateTransition, BidStateProjection])],
  providers: [BidStateService, BidStateProjectionConsumer],
  controllers: [BidStateController],
  exports: [BidStateService],
})
export class BidStateProjectionModule {}
