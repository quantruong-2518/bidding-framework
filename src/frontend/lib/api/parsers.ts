import { apiBaseUrl, ApiError } from './client';
import { useAuthStore } from '@/lib/auth/store';

export interface BidCardSuggestion {
  client_name: string;
  industry: string;
  region: string;
  scope_summary: string;
  requirement_candidates: string[];
  technology_keywords: string[];
  estimated_profile_hint: 'S' | 'M' | 'L' | 'XL' | null;
  confidence: number;
}

export interface ParsedRFP {
  source_format: 'pdf' | 'docx' | 'txt';
  source_filename: string;
  page_count: number | null;
  sections: Array<{ heading: string; level: number; text: string; page_hint: number | null }>;
  tables: Array<{ caption: string | null; raw_text: string; page_hint: number | null }>;
  raw_text: string;
  metadata: Record<string, string>;
}

export interface ParseResponse {
  parsed_rfp: ParsedRFP;
  suggested_bid_card: BidCardSuggestion;
}

/**
 * Upload a PDF/DOCX RFP to the gateway for heuristic parsing. Returns a
 * BidCard suggestion the user can review + edit before submitting.
 */
export async function parseRfp(file: File): Promise<ParseResponse> {
  const form = new FormData();
  form.append('file', file);

  const token = useAuthStore.getState().accessToken;
  const headers = new Headers();
  headers.set('Accept', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const res = await fetch(`${apiBaseUrl()}/bids/parse-rfp`, {
    method: 'POST',
    headers,
    body: form,
  });

  const text = await res.text();
  const parsed: unknown = text ? safeJson(text) : undefined;

  if (!res.ok) {
    const message = extractMessage(parsed) ?? res.statusText;
    throw new ApiError(res.status, message, parsed);
  }
  return parsed as ParseResponse;
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
  if (Array.isArray(candidate) && typeof candidate[0] === 'string') return candidate[0] as string;
  return null;
}
