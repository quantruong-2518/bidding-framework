import {
  ArrayNotEmpty,
  IsArray,
  IsEnum,
  IsISO8601,
  IsOptional,
  IsString,
  MaxLength,
  MinLength,
} from 'class-validator';
import { BidProfile } from './bid.entity';

export class CreateBidDto {
  @IsString()
  @MinLength(1)
  @MaxLength(200)
  clientName!: string;

  @IsString()
  @MinLength(1)
  @MaxLength(100)
  industry!: string;

  @IsString()
  @MinLength(1)
  @MaxLength(100)
  region!: string;

  @IsISO8601()
  deadline!: string;

  @IsString()
  @MaxLength(2000)
  scopeSummary!: string;

  @IsArray()
  @ArrayNotEmpty()
  @IsString({ each: true })
  technologyKeywords!: string[];

  @IsOptional()
  @IsEnum(BidProfile)
  estimatedProfile?: BidProfile;
}
