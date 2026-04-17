import { HttpService } from '@nestjs/axios';
import {
  BadGatewayException,
  HttpException,
  HttpStatus,
  Injectable,
  Logger,
  PayloadTooLargeException,
  RequestTimeoutException,
  UnsupportedMediaTypeException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { AxiosError, AxiosResponse } from 'axios';
import { firstValueFrom } from 'rxjs';

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
const ALLOWED_EXTENSIONS = ['.pdf', '.docx'] as const;

export interface ParseResponse {
  parsed_rfp: Record<string, unknown>;
  suggested_bid_card: Record<string, unknown>;
}

@Injectable()
export class ParsersService {
  private readonly logger = new Logger(ParsersService.name);

  constructor(
    private readonly http: HttpService,
    private readonly config: ConfigService,
  ) {}

  private baseUrl(): string {
    return (
      this.config.get<string>('AI_SERVICE_URL') ?? 'http://ai-service:8001'
    );
  }

  /** Pipe the uploaded RFP buffer to ai-service `/workflows/bid/parse-rfp`. */
  async parseRfp(
    originalname: string,
    mimetype: string,
    buffer: Buffer,
  ): Promise<ParseResponse> {
    this.ensureSupported(originalname, buffer);

    const form = new FormData();
    // Node 20 global Blob — FormData wants a Blob-like payload. The Buffer view
    // is coerced via a fresh Uint8Array to satisfy the strict BlobPart type.
    const blob = new Blob([new Uint8Array(buffer)], {
      type: mimetype || 'application/octet-stream',
    });
    form.append('file', blob, originalname);

    const url = `${this.baseUrl()}/workflows/bid/parse-rfp`;
    try {
      const response: AxiosResponse<ParseResponse> = await firstValueFrom(
        this.http.post<ParseResponse>(url, form, {
          timeout: 30_000,
          maxContentLength: MAX_UPLOAD_BYTES * 2,
          maxBodyLength: MAX_UPLOAD_BYTES * 2,
        }),
      );
      return response.data;
    } catch (err) {
      throw this.mapError(err, url);
    }
  }

  private ensureSupported(originalname: string, buffer: Buffer): void {
    if (!buffer || buffer.byteLength === 0) {
      throw new HttpException('Uploaded file is empty.', HttpStatus.BAD_REQUEST);
    }
    if (buffer.byteLength > MAX_UPLOAD_BYTES) {
      throw new PayloadTooLargeException(
        `File exceeds ${MAX_UPLOAD_BYTES / (1024 * 1024)}MB upload limit.`,
      );
    }
    const lower = (originalname || '').toLowerCase();
    if (!ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
      throw new UnsupportedMediaTypeException(
        `Unsupported file type for ${originalname}; upload .pdf or .docx`,
      );
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
    if (status && status >= 400 && status < 500) {
      return new HttpException(upstream, status);
    }
    this.logger.error(`ai-service upstream failure on ${url}: ${upstream}`);
    return new BadGatewayException(upstream);
  }
}
