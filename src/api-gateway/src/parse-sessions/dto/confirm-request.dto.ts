import { Type } from 'class-transformer';
import {
  ArrayMaxSize,
  IsArray,
  IsEnum,
  IsISO8601,
  IsObject,
  IsOptional,
  IsString,
  MaxLength,
  MinLength,
  ValidateNested,
} from 'class-validator';
import { BidProfile } from '../../bids/bid.entity';

/**
 * S0.5 Wave 2B — exact §3.7 ConfirmRequest contract for
 * ``POST /bids/parse/:sid/confirm``.
 *
 * Every field is optional — the user MAY have nothing to override and just
 * accept the suggested bid_card / atoms verbatim. Atom edits arrive as
 * targeted patches against atom ids that the preview endpoint already
 * surfaced; rejected ids are dropped before vault materialisation.
 */

export class AtomEditDto {
  @IsString()
  @MinLength(1)
  @MaxLength(64)
  id!: string;

  /**
   * Partial frontmatter patch. We intentionally accept any shape here —
   * the ai-service materialise activity validates against the canonical
   * ``AtomFrontmatter`` Pydantic model and rejects unknown fields.
   */
  @IsObject()
  patch!: Record<string, unknown>;
}

export class ConfirmRequestDto {
  @IsOptional()
  @IsString()
  @MinLength(1)
  @MaxLength(200)
  client_name?: string;

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
  @IsEnum(BidProfile)
  profile_override?: BidProfile;

  @IsOptional()
  @IsString()
  @MinLength(1)
  @MaxLength(200)
  name?: string;

  @IsOptional()
  @IsArray()
  @ArrayMaxSize(2_000)
  @ValidateNested({ each: true })
  @Type(() => AtomEditDto)
  atom_edits?: AtomEditDto[];

  @IsOptional()
  @IsArray()
  @ArrayMaxSize(2_000)
  @IsString({ each: true })
  atom_rejects?: string[];
}

/**
 * S0.5 Wave 2B — exact §3.7 ConfirmResponse contract.
 *
 * Plain interface (response shape only).
 */
export interface ConfirmResponseDto {
  bid_id: string;
  workflow_id: string;
  vault_path: string;
  /** Populated when Langfuse observability profile is up. */
  trace_id?: string;
}
