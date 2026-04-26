/**
 * S0.5 Wave 3 — typed client for the parse-session REST surface.
 *
 * Endpoints owned (NestJS `parse.controller.ts`):
 *   - `POST   /bids/parse`              — multipart upload, returns sid
 *   - `GET    /bids/parse/:sid/preview` — §3.6 PreviewResponse
 *   - `POST   /bids/parse/:sid/confirm` — §3.7 ConfirmRequest → bid + wf
 *   - `DELETE /bids/parse/:sid`         — abandon (idempotent, 204)
 *
 * The fetch wrapper in `client.ts` always sends JSON; uploads here use
 * `FormData` directly so the multer-backed `FilesInterceptor` on the gateway
 * can read each file blob. Auth tokens are pulled from the same zustand
 * store as every other client.
 */
import { useAuthStore } from '@/lib/auth/store';
import { ApiError, apiBaseUrl, apiFetch } from './client';
import {
  ConfirmResponseSchema,
  PreviewResponseSchema,
  type ConfirmRequest,
  type ConfirmResponse,
  type Language,
  type PreviewResponse,
} from './types';

export interface UploadResponse {
  session_id: string;
  status: 'PARSING';
}

/**
 * POST /bids/parse — multipart upload. Sends each file under the `files`
 * field plus `tenant_id` and optional `language` form fields. Throws
 * ApiError on non-2xx (the controller surfaces oversize/mime errors here).
 */
export async function uploadFiles(
  files: File[],
  tenantId: string,
  language?: Language,
): Promise<UploadResponse> {
  if (files.length === 0) {
    throw new Error('uploadFiles requires at least one file');
  }
  const form = new FormData();
  for (const file of files) {
    form.append('files', file, file.name);
  }
  form.append('tenant_id', tenantId);
  if (language) form.append('language', language);

  const token = useAuthStore.getState().accessToken;
  const headers = new Headers();
  headers.set('Accept', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const res = await fetch(`${apiBaseUrl()}/bids/parse`, {
    method: 'POST',
    headers,
    body: form,
  });

  const text = await res.text();
  const parsed: unknown = text ? safeJson(text) : undefined;

  if (!res.ok) {
    throw new ApiError(res.status, extractMessage(parsed) ?? res.statusText, parsed);
  }
  // The controller returns `{session_id, status}` directly — no Zod schema
  // bump needed, but we still narrow the shape.
  const body = parsed as Partial<UploadResponse> | undefined;
  if (!body || typeof body.session_id !== 'string') {
    throw new ApiError(500, 'Malformed upload response from gateway', parsed);
  }
  return { session_id: body.session_id, status: 'PARSING' };
}

/**
 * GET /bids/parse/:sid/preview — fetches the §3.6 shape and validates it
 * with Zod. A schema mismatch raises ApiError(500, ...) so polling falls
 * into the error branch instead of trying to render half-shaped data.
 */
export async function getPreview(sid: string): Promise<PreviewResponse> {
  const raw = await apiFetch<unknown>(
    `/bids/parse/${encodeURIComponent(sid)}/preview`,
  );
  const result = PreviewResponseSchema.safeParse(raw);
  if (!result.success) {
    throw new ApiError(
      500,
      `Preview response failed schema validation: ${result.error.message}`,
      raw,
    );
  }
  return result.data;
}

/**
 * POST /bids/parse/:sid/confirm — sends ConfirmRequest body, validates the
 * §3.7 ConfirmResponse on the way out. The gateway tx returns only after
 * the bid + workflow are live, so the response is safe to consume right
 * away to navigate.
 */
export async function confirm(
  sid: string,
  request: ConfirmRequest,
): Promise<ConfirmResponse> {
  const raw = await apiFetch<unknown>(
    `/bids/parse/${encodeURIComponent(sid)}/confirm`,
    { method: 'POST', body: request },
  );
  const result = ConfirmResponseSchema.safeParse(raw);
  if (!result.success) {
    throw new ApiError(
      500,
      `Confirm response failed schema validation: ${result.error.message}`,
      raw,
    );
  }
  return result.data;
}

/**
 * DELETE /bids/parse/:sid — idempotent abandon. The gateway returns 204
 * either way (already-abandoned is not an error).
 */
export async function abandon(sid: string): Promise<void> {
  await apiFetch<void>(`/bids/parse/${encodeURIComponent(sid)}`, {
    method: 'DELETE',
  });
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function extractMessage(body: unknown): string | null {
  if (!body || typeof body !== 'object') return null;
  const record = body as Record<string, unknown>;
  const candidate = record.message ?? record.error ?? record.detail;
  if (typeof candidate === 'string') return candidate;
  if (Array.isArray(candidate) && typeof candidate[0] === 'string') {
    return candidate[0] as string;
  }
  return null;
}
