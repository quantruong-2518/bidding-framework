import { HttpService } from '@nestjs/axios';
import {
  BadGatewayException,
  HttpException,
  HttpStatus,
  Injectable,
  Logger,
  NotFoundException,
  RequestTimeoutException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { AxiosError, AxiosResponse } from 'axios';
import { firstValueFrom } from 'rxjs';

/**
 * S0.5 Wave 2B — typed HTTP client for the ai-service parse + materialise
 * endpoints. Lives alongside `WorkflowsService` (the older client wrapping
 * `/workflows/bid/*`) so the surface stays narrow per route family.
 *
 * Endpoints covered:
 *   - `POST /workflows/bid/parse/start`            — kick off LLM parse pipeline
 *   - `GET  /workflows/bid/parse/:sid/status`      — poll progress
 *   - `POST /workflows/bid/parse/:sid/materialize` — write vault tree post-confirm
 *
 * Decision 9 (parse runs OUTSIDE Temporal) means these calls are plain
 * REST round-trips; the materialise endpoint is idempotent on a per-bid
 * basis (file hash) so a confirm-tx retry cannot duplicate work.
 */

export interface StartParseFile {
  /** Stable id we generated when uploading; ai-service uses this in manifest. */
  file_id: string;
  /** Original filename for manifest + display. */
  original_name: string;
  /** Mime type as detected by multer. */
  mime: string;
  /** MinIO key under the parse_sessions prefix. */
  object_store_uri: string;
  /** Size in bytes (parser uses this for chunking heuristics). */
  size_bytes: number;
}

export interface StartParseRequest {
  parse_session_id: string;
  tenant_id: string;
  user_id: string;
  files: StartParseFile[];
  lang?: 'en' | 'vi';
}

export interface StartParseResponse {
  session_id: string;
  status: 'PARSING' | 'READY' | 'FAILED';
}

export interface ParseStatusResponse {
  session_id: string;
  status: 'PARSING' | 'READY' | 'FAILED';
  progress?: {
    stage: string;
    percent?: number;
    files_total?: number;
    files_processed?: number;
    atoms_so_far?: number;
  };
  error?: string;
  /**
   * Live tracker payload while ``status === 'PARSING'``. Carries the running
   * ``atoms_preview`` + ``sources_preview`` shape so api-gateway can merge it
   * into the §3.6 PreviewResponse without round-tripping through Postgres.
   * Populated to the full ``ContextSynthesisOutput`` once status flips to
   * READY.
   */
  result?: Record<string, unknown>;
}

export interface MaterializeRequest {
  bid_id: string;
  tenant_id: string;
  vault_root: string;
  parse_session_payload: Record<string, unknown>;
}

export interface MaterializeResponse {
  bid_id: string;
  vault_path: string;
  atoms_written: number;
  trace_id?: string;
}

@Injectable()
export class AiServiceClient {
  private readonly logger = new Logger(AiServiceClient.name);

  constructor(
    private readonly http: HttpService,
    private readonly config: ConfigService,
  ) {}

  private baseUrl(): string {
    return (
      this.config.get<string>('AI_SERVICE_URL') ?? 'http://ai-service:8001'
    );
  }

  /**
   * POST /workflows/bid/parse/start — kicks off the async parse pipeline. The
   * session id is allocated by api-gateway (Postgres write happens *first*,
   * then this RPC), so a partial network failure leaves a stale PARSING row
   * the TTL cleanup will eventually drop.
   */
  async startParse(req: StartParseRequest): Promise<StartParseResponse> {
    const url = `${this.baseUrl()}/workflows/bid/parse/start`;
    return this.request<StartParseResponse>(
      'POST',
      url,
      req as unknown as Record<string, unknown>,
    );
  }

  /** GET /workflows/bid/parse/:sid/status. Used by progress polling + tests. */
  async getParseStatus(sid: string): Promise<ParseStatusResponse> {
    const url = `${this.baseUrl()}/workflows/bid/parse/${encodeURIComponent(sid)}/status`;
    return this.request<ParseStatusResponse>('GET', url);
  }

  /**
   * POST /workflows/bid/parse/:sid/materialize — invoked by the confirm tx
   * (after bids row insert + MinIO rename succeed). The ai-service writes
   * the vault tree atomically (temp dir + rename per Decision 11) and
   * returns the path so the response can include it.
   */
  async materialize(
    sid: string,
    req: MaterializeRequest,
  ): Promise<MaterializeResponse> {
    const url = `${this.baseUrl()}/workflows/bid/parse/${encodeURIComponent(sid)}/materialize`;
    return this.request<MaterializeResponse>(
      'POST',
      url,
      req as unknown as Record<string, unknown>,
    );
  }

  private async request<T>(
    method: 'GET' | 'POST',
    url: string,
    body?: Record<string, unknown>,
  ): Promise<T> {
    try {
      const response: AxiosResponse<T> = await firstValueFrom(
        method === 'GET'
          ? this.http.get<T>(url, { timeout: 30_000 })
          : this.http.post<T>(url, body, { timeout: 30_000 }),
      );
      return response.data;
    } catch (err) {
      throw this.mapError(err, url);
    }
  }

  private mapError(err: unknown, url: string): HttpException {
    const axiosErr = err as AxiosError<{ message?: string; detail?: string }>;
    if (axiosErr?.code === 'ECONNABORTED' || axiosErr?.code === 'ETIMEDOUT') {
      this.logger.warn(`ai-service timeout on ${url}`);
      return new RequestTimeoutException('ai-service did not respond in time.');
    }
    const status = axiosErr?.response?.status;
    const upstream =
      axiosErr?.response?.data?.message ??
      axiosErr?.response?.data?.detail ??
      axiosErr?.message ??
      'ai-service error';
    if (status === HttpStatus.NOT_FOUND) {
      return new NotFoundException(upstream);
    }
    if (status && status >= 400 && status < 500) {
      return new HttpException(upstream, status);
    }
    this.logger.error(`ai-service upstream failure on ${url}: ${upstream}`);
    return new BadGatewayException(upstream);
  }
}
