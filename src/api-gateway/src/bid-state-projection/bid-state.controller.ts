import { Controller, Get, Param, ParseUUIDPipe } from '@nestjs/common';
import { BidStateService } from './bid-state.service';
import { BidStateView } from './bid-state.types';

/**
 * Read-side endpoint for the bid state CQRS projection.
 *
 * Any authenticated user can read — the projection holds no PII beyond what
 * `GET /bids/:id` already returns. No `@Roles(...)` guard so polling clients
 * (frontend bid viewer, oncall dashboards) can hit it cheaply.
 */
@Controller('bids')
export class BidStateController {
  constructor(private readonly stateService: BidStateService) {}

  @Get(':id/state')
  getState(
    @Param('id', new ParseUUIDPipe()) id: string,
  ): Promise<BidStateView> {
    return this.stateService.getStateByBidId(id);
  }
}
