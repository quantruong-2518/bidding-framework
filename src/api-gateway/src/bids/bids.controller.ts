import {
  Body,
  Controller,
  Delete,
  Get,
  HttpCode,
  HttpStatus,
  Param,
  ParseUUIDPipe,
  Patch,
  Post,
  UseGuards,
} from '@nestjs/common';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import { RolesGuard } from '../auth/roles.guard';
import { Roles } from '../auth/roles.decorator';
import { CurrentUser, type AuthenticatedUser } from '../auth/current-user.decorator';
import { BidsService } from './bids.service';
import { CreateBidDto } from './create-bid.dto';
import { UpdateBidDto } from './update-bid.dto';
import type { Bid } from './bid.entity';
import { LangfuseLinkService } from './langfuse-link.service';

@UseGuards(JwtAuthGuard, RolesGuard)
@Controller('bids')
export class BidsController {
  constructor(
    private readonly bidsService: BidsService,
    private readonly langfuseLinkService: LangfuseLinkService,
  ) {}

  @Get(':id/trace-url')
  @Roles('admin', 'bid_manager')
  getTraceUrl(@Param('id', new ParseUUIDPipe()) id: string): { url: string } {
    return this.langfuseLinkService.getTraceUrl(id);
  }

  @Post()
  @Roles('admin', 'bid_manager')
  create(
    @Body() dto: CreateBidDto,
    @CurrentUser() user: AuthenticatedUser | undefined,
  ): Promise<Bid> {
    return this.bidsService.create(dto, user?.username);
  }

  @Get()
  list(): Promise<Bid[]> {
    return this.bidsService.findAll();
  }

  @Get(':id')
  findOne(@Param('id', new ParseUUIDPipe()) id: string): Promise<Bid> {
    return this.bidsService.findOne(id);
  }

  @Patch(':id')
  @Roles('admin', 'bid_manager')
  update(
    @Param('id', new ParseUUIDPipe()) id: string,
    @Body() dto: UpdateBidDto,
  ): Promise<Bid> {
    return this.bidsService.update(id, dto);
  }

  @Delete(':id')
  @Roles('admin')
  @HttpCode(HttpStatus.NO_CONTENT)
  remove(@Param('id', new ParseUUIDPipe()) id: string): Promise<void> {
    return this.bidsService.remove(id);
  }
}
