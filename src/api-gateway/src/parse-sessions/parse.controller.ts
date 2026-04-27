import {
  BadRequestException,
  Body,
  Controller,
  Delete,
  Get,
  HttpCode,
  HttpStatus,
  Param,
  ParseUUIDPipe,
  Post,
  UploadedFiles,
  UseGuards,
  UseInterceptors,
  UsePipes,
  ValidationPipe,
} from '@nestjs/common';
import { FilesInterceptor } from '@nestjs/platform-express';
import { v4 as uuidv4 } from 'uuid';
import {
  CurrentUser,
  type AuthenticatedUser,
} from '../auth/current-user.decorator';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import { Roles } from '../auth/roles.decorator';
import { RolesGuard } from '../auth/roles.guard';
import {
  AiServiceClient,
  type StartParseFile,
} from '../gateway/ai-service.client';
import { ObjectStoreService } from '../object-store/object-store.service';
import {
  ALLOWED_UPLOAD_MIMES,
  MAX_UPLOAD_FILES,
  MAX_UPLOAD_FILE_BYTES,
  UploadFilesDto,
} from './dto/upload-files.dto';
import type {
  ConfirmRequestDto,
  ConfirmResponseDto,
} from './dto/confirm-request.dto';
import { ConfirmRequestDto as ConfirmRequestDtoClass } from './dto/confirm-request.dto';
import type {
  AtomPreviewItem,
  ConflictItem,
  PreviewResponseDto,
  SourcePreviewItem,
  SuggestedBidCardPreview,
  SuggestedWorkflow,
} from './dto/preview-response.dto';
import { MaterializeService } from './materialize.service';
import type { ParseSession } from './parse-session.entity';
import { ParseSessionsService } from './parse-sessions.service';

const FILE_SAMPLE_LIMIT = 10;

/**
 * S0.5 Wave 2B — REST surface for parse sessions.
 *
 * Endpoints:
 *   - `POST   /bids/parse`                  — multipart upload, returns sid
 *   - `GET    /bids/parse/:sid/preview`     — §3.6 PreviewResponse shape
 *   - `POST   /bids/parse/:sid/confirm`     — §3.7 ConfirmRequest → bid + workflow
 *   - `DELETE /bids/parse/:sid`             — abandon (idempotent)
 *
 * RBAC: upload + confirm gated on admin / bid_manager (matches the legacy
 * `POST /bids` policy). Preview is any authenticated user — reviewers may
 * sit on different roles, and there's no PII in the preview shape beyond
 * what `GET /bids/:id` already exposes.
 *
 * AuditInterceptor (`@Roles(...)` is the trigger metadata) records every
 * call automatically — no manual `audit.record(...)` calls required.
 */
@UseGuards(JwtAuthGuard, RolesGuard)
@Controller('bids/parse')
export class ParseController {
  constructor(
    private readonly sessions: ParseSessionsService,
    private readonly aiClient: AiServiceClient,
    private readonly objectStore: ObjectStoreService,
    private readonly materialize: MaterializeService,
  ) {}

  /**
   * Multipart upload — accepts up to `MAX_UPLOAD_FILES` files plus a
   * `tenant_id` form field (and optional `language`). Saves originals to
   * MinIO under `parse_sessions/<sid>/<file_id>.<ext>` then asks ai-service
   * to start the parse pipeline. Returns immediately with `status: 'PARSING'`
   * — the frontend polls `GET /preview` for progress.
   */
  @Post()
  @Roles('admin', 'bid_manager')
  @UseInterceptors(
    FilesInterceptor('files', MAX_UPLOAD_FILES, {
      limits: { fileSize: MAX_UPLOAD_FILE_BYTES },
    }),
  )
  async upload(
    @UploadedFiles() files: Express.Multer.File[] | undefined,
    @Body(new ValidationPipe({ whitelist: true, transform: true }))
    body: UploadFilesDto,
    @CurrentUser() user: AuthenticatedUser | undefined,
  ): Promise<{ session_id: string; status: 'PARSING' }> {
    if (!files || files.length === 0) {
      throw new BadRequestException(
        'At least one file must be provided in the "files" multipart field',
      );
    }
    if (files.length > MAX_UPLOAD_FILES) {
      throw new BadRequestException(
        `At most ${MAX_UPLOAD_FILES} files per upload (received ${files.length})`,
      );
    }
    for (const file of files) {
      if (!ALLOWED_UPLOAD_MIMES.has(file.mimetype)) {
        throw new BadRequestException(
          `File "${file.originalname}" mime ${file.mimetype} not supported`,
        );
      }
      if (file.size > MAX_UPLOAD_FILE_BYTES) {
        throw new BadRequestException(
          `File "${file.originalname}" exceeds ${MAX_UPLOAD_FILE_BYTES} bytes`,
        );
      }
    }

    const userId = user?.username ?? 'anonymous';
    const session = await this.sessions.createSession(body.tenant_id, userId);
    const bucket = this.sessions.getBucket();
    const startFiles: StartParseFile[] = [];

    for (const file of files) {
      const fileId = uuidv4();
      const ext = pickExtension(file.originalname, file.mimetype);
      const key = `${this.sessions.parseSessionPrefix(session.id)}${fileId}${ext}`;
      await this.objectStore.putObject(
        bucket,
        key,
        file.buffer,
        file.mimetype,
      );
      startFiles.push({
        file_id: fileId,
        original_name: file.originalname,
        mime: file.mimetype,
        object_store_uri: `s3://${bucket}/${key}`,
        size_bytes: file.size,
      });
    }

    try {
      await this.aiClient.startParse({
        parse_session_id: session.id,
        tenant_id: body.tenant_id,
        user_id: userId,
        files: startFiles,
        lang: body.language,
      });
    } catch (err) {
      // ai-service refused — mark FAILED so the user sees the parser error
      // in the preview poll instead of a phantom PARSING row.
      await this.sessions.setStatus(
        session.id,
        'FAILED',
        (err as Error).message,
      );
      throw err;
    }

    return { session_id: session.id, status: 'PARSING' };
  }

  /**
   * Preview poll endpoint — frontend hits this every ~2s while PARSING.
   * Returns the §3.6 PreviewResponse shape.
   */
  @Get(':sid/preview')
  @Roles('admin', 'bid_manager', 'ba', 'sa', 'qc')
  async preview(
    @Param('sid', new ParseUUIDPipe()) sid: string,
  ): Promise<PreviewResponseDto> {
    let session = await this.sessions.getById(sid);
    let tracker: Awaited<ReturnType<AiServiceClient['getParseStatus']>> | null =
      null;
    if (session.status === 'PARSING') {
      // Merge ai-service in-memory tracker so the frontend's 2 s preview
      // poll sees atoms accumulate while the background parse runs file by
      // file. Tracker miss / network error is non-fatal — we just fall back
      // to the empty Postgres shape; the next poll round will retry.
      try {
        tracker = await this.aiClient.getParseStatus(sid);
      } catch (err) {
        // No-op: keep PARSING + empty preview. Logging at debug to avoid
        // spamming on the 2 s polling cadence.
      }
      // Sync ai-service terminal states into Postgres so the row stops
      // being PARSING the moment the background parse finishes — without
      // this, polling never converges (tracker is in-memory only).
      if (tracker?.status === 'READY' && tracker.result) {
        session = await this.sessions.setResult(sid, {
          atoms: (tracker.result.atoms as unknown[]) ?? [],
          anchorMd: (tracker.result.anchor_md as string) ?? '',
          summaryMd: (tracker.result.summary_md as string) ?? '',
          openQuestions: (tracker.result.open_questions as unknown[]) ?? [],
          conflicts: (tracker.result.conflicts as unknown[]) ?? [],
          manifest:
            (tracker.result.manifest as Record<string, unknown>) ?? null,
          flipToReady: true,
        });
      } else if (tracker?.status === 'FAILED') {
        session = await this.sessions.setStatus(
          sid,
          'FAILED',
          tracker.error ?? 'parse failed in ai-service',
        );
      }
    }
    return this.toPreviewResponse(session, tracker);
  }

  /**
   * Confirm — the heavy operation. Delegates to {@link MaterializeService};
   * see that file for the seven-step transactional contract.
   */
  @Post(':sid/confirm')
  @Roles('admin', 'bid_manager')
  @UsePipes(new ValidationPipe({ whitelist: true, transform: true }))
  async confirm(
    @Param('sid', new ParseUUIDPipe()) sid: string,
    @Body() body: ConfirmRequestDtoClass,
    @CurrentUser() user: AuthenticatedUser | undefined,
  ): Promise<ConfirmResponseDto> {
    const userId = user?.username ?? 'anonymous';
    return this.materialize.confirmAndStart(
      sid,
      body as ConfirmRequestDto,
      userId,
    );
  }

  /**
   * Idempotent abandon — flips status to ABANDONED + drops the MinIO prefix.
   * Returns 204 either way (already-abandoned is not an error).
   */
  @Delete(':sid')
  @Roles('admin', 'bid_manager')
  @HttpCode(HttpStatus.NO_CONTENT)
  async abandon(@Param('sid', new ParseUUIDPipe()) sid: string): Promise<void> {
    await this.sessions.markAbandoned(sid);
  }

  /**
   * Build the §3.6 PreviewResponse from an entity. Defensive against
   * mid-parse polls (status=PARSING with empty atoms) — when ``tracker``
   * is supplied we merge its live atoms_preview / sources_preview /
   * progress so the frontend sees atoms grow while the background parse
   * walks file by file.
   */
  private toPreviewResponse(
    session: ParseSession,
    tracker: {
      progress?: {
        stage?: string;
        percent?: number;
        files_total?: number;
        files_processed?: number;
        atoms_so_far?: number;
      };
      result?: Record<string, unknown>;
    } | null,
  ): PreviewResponseDto {
    const card = (session.suggestedBidCard ?? null) as
      | (SuggestedBidCardPreview & Record<string, unknown>)
      | null;

    const atomsRaw = (session.atoms ?? []) as Array<Record<string, unknown>>;
    const byType: Record<string, number> = {};
    const byPriority: Record<string, number> = {};
    let lowConf = 0;
    const sample: AtomPreviewItem[] = [];
    for (const atom of atomsRaw) {
      const fm = (atom?.frontmatter as Record<string, unknown>) ?? {};
      const type = String(fm.type ?? 'unclear');
      const priority = String(fm.priority ?? 'COULD');
      byType[type] = (byType[type] ?? 0) + 1;
      byPriority[priority] = (byPriority[priority] ?? 0) + 1;
      const ext = (fm.extraction as Record<string, unknown>) ?? {};
      const conf = Number(ext.confidence ?? 1);
      if (conf < 0.6) lowConf += 1;
      if (sample.length < FILE_SAMPLE_LIMIT) {
        const src = (fm.source as Record<string, unknown>) ?? {};
        sample.push({
          id: String(fm.id ?? ''),
          type: type as AtomPreviewItem['type'],
          priority: priority as AtomPreviewItem['priority'],
          category: String(fm.category ?? ''),
          source_file: String(src.file ?? ''),
          body_md: String(atom?.body_md ?? ''),
          confidence: Number.isFinite(conf) ? conf : 1,
          split_recommended: Boolean(fm.split_recommended ?? false),
        });
      }
    }

    const manifest = (session.manifest ?? {}) as Record<string, unknown>;
    const sources_preview = this.buildSourcesPreview(manifest);

    const conflicts_detected = ((session.conflicts ?? []) as ConflictItem[]) ?? [];
    const open_questions = ((session.openQuestions ?? []) as Array<
      string | { question?: string }
    >).map((q) => (typeof q === 'string' ? q : (q.question ?? '')));

    const suggested_workflow = this.buildSuggestedWorkflow(card);

    const current_state =
      session.status === 'CONFIRMED'
        ? 'CONFIRMED'
        : session.status === 'ABANDONED'
          ? 'ABANDONED'
          : 'AWAITING_CONFIRM';

    let atoms_preview = {
      total: atomsRaw.length,
      by_type: byType,
      by_priority: byPriority,
      low_confidence_count: lowConf,
      sample,
    };
    let sources_preview_final = sources_preview;
    let progress: { stage: string; percent: number } | undefined;

    if (session.status === 'PARSING') {
      const trackerProgress = tracker?.progress;
      const trackerResult = (tracker?.result ?? {}) as Record<string, unknown>;
      const trackerAtomsPreview =
        (trackerResult.atoms_preview as typeof atoms_preview | undefined) ??
        null;
      const trackerSources =
        (trackerResult.sources_preview as SourcePreviewItem[] | undefined) ??
        null;

      // Prefer the live tracker payload — it carries atoms accumulated so
      // far. Fall back to the Postgres atoms only if the tracker is
      // unavailable (network blip during the 2 s poll).
      if (trackerAtomsPreview && trackerAtomsPreview.total > 0) {
        atoms_preview = trackerAtomsPreview;
      }
      if (trackerSources && trackerSources.length > 0) {
        sources_preview_final = trackerSources;
      }

      const stage = String(trackerProgress?.stage ?? 'parsing');
      const trackerPct = trackerProgress?.percent;
      const computedPct =
        typeof trackerPct === 'number'
          ? trackerPct
          : atoms_preview.total === 0
            ? 10
            : 60;
      progress = { stage, percent: computedPct };
    }

    return {
      session_id: session.id,
      status: session.status,
      progress,
      parse_error: session.parseError ?? undefined,
      suggested_bid_card: card
        ? {
            name: String(card.name ?? card.client_name ?? ''),
            client_name: String(card.client_name ?? ''),
            industry: String(card.industry ?? ''),
            region: String(card.region ?? ''),
            deadline: String(card.deadline ?? ''),
            scope_summary: String(card.scope_summary ?? ''),
            estimated_profile:
              (card.estimated_profile as SuggestedBidCardPreview['estimated_profile']) ??
              'M',
            language:
              (card.language as SuggestedBidCardPreview['language']) ?? 'en',
            technology_keywords:
              (card.technology_keywords as string[] | undefined) ?? [],
          }
        : null,
      context_preview: {
        anchor_md: session.anchorMd ?? '',
        summary_md: session.summaryMd ?? '',
        open_questions,
      },
      atoms_preview,
      sources_preview: sources_preview_final,
      conflicts_detected,
      suggested_workflow,
      current_state,
      expires_at: session.expiresAt,
    };
  }

  private buildSourcesPreview(
    manifest: Record<string, unknown>,
  ): SourcePreviewItem[] {
    const files = (manifest.files as Array<Record<string, unknown>>) ?? [];
    return files.map((f) => ({
      file_id: String(f.file_id ?? ''),
      original_name: String(f.original_name ?? ''),
      mime: String(f.mime ?? ''),
      page_count: (f.page_count as number | null | undefined) ?? null,
      role: String(f.role ?? 'unknown'),
      language: String(f.language ?? 'en'),
      parsed_to: String(f.parsed_to ?? ''),
      atoms_extracted: Number(f.atoms_extracted ?? 0),
    }));
  }

  private buildSuggestedWorkflow(
    card: (SuggestedBidCardPreview & Record<string, unknown>) | null,
  ): SuggestedWorkflow | null {
    if (!card) return null;
    const profile = (card.estimated_profile ??
      'M') as SuggestedWorkflow['profile'];
    const pipelineByProfile: Record<SuggestedWorkflow['profile'], string[]> = {
      S: ['S0', 'S0_5', 'S1', 'S2', 'S3', 'S4', 'S8', 'S9', 'S10', 'S11'],
      M: [
        'S0',
        'S0_5',
        'S1',
        'S2',
        'S3',
        'S4',
        'S5',
        'S6',
        'S7',
        'S8',
        'S9',
        'S10',
        'S11',
      ],
      L: [
        'S0',
        'S0_5',
        'S1',
        'S2',
        'S3',
        'S4',
        'S5',
        'S6',
        'S7',
        'S8',
        'S9',
        'S10',
        'S11',
      ],
      XL: [
        'S0',
        'S0_5',
        'S1',
        'S2',
        'S3',
        'S4',
        'S5',
        'S6',
        'S7',
        'S8',
        'S9',
        'S10',
        'S11',
      ],
    };
    const reviewerCountByProfile = { S: 1, M: 1, L: 2, XL: 3 } as const;
    const costByProfile = { S: 0.8, M: 2.5, L: 4.0, XL: 6.0 } as const;
    const durationByProfile = { S: 2, M: 4, L: 8, XL: 16 } as const;
    return {
      profile,
      pipeline: pipelineByProfile[profile],
      estimated_total_token_cost_usd: costByProfile[profile],
      estimated_duration_hours: durationByProfile[profile],
      review_gate: {
        reviewer_count: reviewerCountByProfile[profile],
        timeout_hours: 48,
        max_rounds: 3,
      },
    };
  }
}

/**
 * Pick a sane file extension from the original filename or fall back to a
 * mime-derived hint. Used for the MinIO key suffix only.
 */
function pickExtension(original: string, mime: string): string {
  const dot = original.lastIndexOf('.');
  if (dot > 0 && dot < original.length - 1) {
    return original.slice(dot).toLowerCase();
  }
  switch (mime) {
    case 'application/pdf':
      return '.pdf';
    case 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
      return '.docx';
    case 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
      return '.xlsx';
    case 'text/markdown':
    case 'text/x-markdown':
      return '.md';
    case 'text/plain':
      return '.txt';
    default:
      return '.bin';
  }
}
