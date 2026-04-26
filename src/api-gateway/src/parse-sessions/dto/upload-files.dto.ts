import {
  IsIn,
  IsOptional,
  IsString,
  Matches,
  MaxLength,
  MinLength,
} from 'class-validator';

/**
 * S0.5 Wave 2B — multipart upload form fields for ``POST /bids/parse``.
 *
 * The actual file blobs ride alongside this DTO via ``FilesInterceptor``;
 * the controller validates per-file size + mime separately so we can return
 * a precise 400 ("file 3: rfp.bin mime not supported") instead of a vague
 * pipe error. The DTO covers the *form fields* only.
 *
 * Per design doc §4 Wave 2B + §3.6 PreviewResponse contract.
 */
export class UploadFilesDto {
  /**
   * Tenant scope for the parse + downstream RAG ingestion. Required —
   * cross-tenant leakage is the worst regression we could ship from this
   * waves so the field is mandatory at the gate.
   */
  @IsString()
  @MinLength(1)
  @MaxLength(64)
  @Matches(/^[a-z0-9][a-z0-9_-]{0,63}$/, {
    message:
      'tenant_id must be lowercase alphanumeric, dashes, or underscores',
  })
  tenant_id!: string;

  /**
   * Optional language override. When unset the parser runs ``langdetect`` on
   * the first 500 chars of file 1 (per Decision 6).
   */
  @IsOptional()
  @IsIn(['en', 'vi'])
  language?: 'en' | 'vi';
}

/**
 * Allowed MIME types per Decision 5 (PDF / DOCX / XLSX / MD / TXT).
 * Some browsers send ``text/x-markdown`` for *.md, hence the alias entry.
 */
export const ALLOWED_UPLOAD_MIMES = new Set<string>([
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'text/markdown',
  'text/x-markdown',
  'text/plain',
]);

/** Per-file size cap. */
export const MAX_UPLOAD_FILE_BYTES = 50 * 1024 * 1024;

/** Max files in a single ``POST /bids/parse`` call. */
export const MAX_UPLOAD_FILES = 10;
