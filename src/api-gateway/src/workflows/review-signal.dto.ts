import { Type } from 'class-transformer';
import {
  ArrayMaxSize,
  IsArray,
  IsEnum,
  IsOptional,
  IsString,
  MaxLength,
  MinLength,
  ValidateNested,
} from 'class-validator';

export enum ReviewVerdict {
  APPROVED = 'APPROVED',
  REJECTED = 'REJECTED',
  CHANGES_REQUESTED = 'CHANGES_REQUESTED',
}

export enum ReviewerRole {
  BID_MANAGER = 'bid_manager',
  BA = 'ba',
  SA = 'sa',
  QC = 'qc',
  DOMAIN_EXPERT = 'domain_expert',
  SOLUTION_LEAD = 'solution_lead',
}

export enum ReviewCommentSeverity {
  NIT = 'NIT',
  MINOR = 'MINOR',
  MAJOR = 'MAJOR',
  BLOCKER = 'BLOCKER',
}

export enum ReviewTargetState {
  S2 = 'S2',
  S5 = 'S5',
  S6 = 'S6',
  S8 = 'S8',
}

export class ReviewCommentDto {
  @IsString()
  @MinLength(1)
  @MaxLength(200)
  section!: string;

  @IsEnum(ReviewCommentSeverity)
  severity!: ReviewCommentSeverity;

  @IsString()
  @MinLength(1)
  @MaxLength(2000)
  message!: string;

  @IsOptional()
  @IsEnum(ReviewTargetState)
  targetState?: ReviewTargetState;
}

export class ReviewSignalDto {
  @IsEnum(ReviewVerdict)
  verdict!: ReviewVerdict;

  @IsString()
  @MinLength(1)
  @MaxLength(200)
  reviewer!: string;

  @IsEnum(ReviewerRole)
  reviewerRole!: ReviewerRole;

  @IsArray()
  @ArrayMaxSize(50)
  @ValidateNested({ each: true })
  @Type(() => ReviewCommentDto)
  comments: ReviewCommentDto[] = [];

  @IsOptional()
  @IsString()
  @MaxLength(2000)
  notes?: string;
}
