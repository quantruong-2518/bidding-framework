import { HttpModule } from '@nestjs/axios';
import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { ParsersController } from './parsers.controller';
import { ParsersService } from './parsers.service';

@Module({
  imports: [HttpModule, ConfigModule],
  controllers: [ParsersController],
  providers: [ParsersService],
})
export class ParsersModule {}
