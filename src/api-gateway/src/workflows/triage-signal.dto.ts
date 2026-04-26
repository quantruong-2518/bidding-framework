import {
  IsBoolean,
  IsEnum,
  IsOptional,
  IsString,
  MaxLength,
  MinLength,
} from 'class-validator';
import { BidProfile } from '../bids/bid.entity';

export class TriageSignalDto {
  @IsBoolean()
  approved!: boolean;

  @IsString()
  @MinLength(1)
  @MaxLength(200)
  reviewer!: string;

  @IsOptional()
  @IsString()
  @MaxLength(5000)
  notes?: string;

  @IsOptional()
  @IsEnum(BidProfile)
  bidProfileOverride?: BidProfile;
}
