import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  uploadFiles,
  getPreview,
  confirm,
  abandon,
} from '@/lib/api/parse-sessions';
import { useAuthStore } from '@/lib/auth/store';

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  useAuthStore.setState({
    accessToken: 'test-token',
    user: { sub: 'u', username: 'u', roles: ['bid_manager'] },
    hydrated: true,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('parse-sessions API client', () => {
  it('uploadFiles posts FormData with files + tenant + language', async () => {
    fetchMock.mockResolvedValue(jsonResponse(201, { session_id: 'sid-1', status: 'PARSING' }));
    const file = new File(['x'], 'a.pdf', { type: 'application/pdf' });
    const res = await uploadFiles([file], 'customer-a', 'en');
    expect(res).toEqual({ session_id: 'sid-1', status: 'PARSING' });
    const [, opts] = fetchMock.mock.calls[0];
    expect(opts.method).toBe('POST');
    expect(opts.body).toBeInstanceOf(FormData);
    const form = opts.body as FormData;
    expect(form.get('tenant_id')).toBe('customer-a');
    expect(form.get('language')).toBe('en');
    expect((opts.headers as Headers).get('Authorization')).toBe('Bearer test-token');
  });

  it('uploadFiles throws when no file is supplied', async () => {
    await expect(uploadFiles([], 'customer-a')).rejects.toThrow();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('getPreview parses a valid PreviewResponse via Zod', async () => {
    const body = {
      session_id: 'sid-1',
      status: 'READY',
      suggested_bid_card: {
        name: 'X',
        client_name: 'Y',
        industry: 'banking',
        region: 'VN',
        deadline: '2026-08-30',
        scope_summary: 's',
        estimated_profile: 'L',
        language: 'en',
        technology_keywords: [],
      },
      context_preview: { anchor_md: '', summary_md: '', open_questions: [] },
      atoms_preview: {
        total: 0,
        by_type: {},
        by_priority: {},
        low_confidence_count: 0,
        sample: [],
      },
      sources_preview: [],
      conflicts_detected: [],
      suggested_workflow: null,
      current_state: 'AWAITING_CONFIRM',
      expires_at: '2026-05-03',
    };
    fetchMock.mockResolvedValue(jsonResponse(200, body));
    const res = await getPreview('sid-1');
    expect(res.session_id).toBe('sid-1');
    expect(res.status).toBe('READY');
  });

  it('getPreview rejects malformed body via Zod', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { session_id: 'sid' }));
    await expect(getPreview('sid')).rejects.toThrow(/schema validation/);
  });

  it('confirm posts JSON and parses ConfirmResponse', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(201, { bid_id: 'b', workflow_id: 'w', vault_path: '/v' }),
    );
    const res = await confirm('sid-1', { name: 'n' });
    expect(res).toEqual({ bid_id: 'b', workflow_id: 'w', vault_path: '/v' });
    const [, opts] = fetchMock.mock.calls[0];
    expect(opts.method).toBe('POST');
    expect(opts.body).toBe(JSON.stringify({ name: 'n' }));
  });

  it('abandon issues DELETE and tolerates 204 No Content', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(abandon('sid-1')).resolves.toBeUndefined();
    const [url, opts] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/bids\/parse\/sid-1$/);
    expect(opts.method).toBe('DELETE');
  });
});
