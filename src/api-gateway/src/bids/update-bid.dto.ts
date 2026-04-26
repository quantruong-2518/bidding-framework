import {
  IsArray,
  IsEnum,
  IsISO8601,
  IsOptional,
  IsString,
  MaxLength,
  MinLength,
} from 'class-validator';
import { BidProfile, BidStatus } from './bid.entity';

export class UpdateBidDto {
  @IsOptional()
  @IsString()
  @MinLength(1)
  @MaxLength(200)
  clientName?: string;

  @IsOptional()
  @IsString()
  @MinLength(1)
  @MaxLength(100)
  industry?: string;

  @IsOptional()
  @IsString()
  @MinLength(1)
  @MaxLength(100)
  region?: string;

  @IsOptional()
  @IsISO8601()
  deadline?: string;

  @IsOptional()
  @IsString()
  @MaxLength(5000)
  scopeSummary?: string;

  @IsOptional()
  @IsArray()
  @IsString({ each: true })
  technologyKeywords?: string[];

  @IsOptional()
  @IsEnum(BidProfile)
  estimatedProfile?: BidProfile;

  @IsOptional()
  @IsEnum(BidStatus)
  status?: BidStatus;
}
