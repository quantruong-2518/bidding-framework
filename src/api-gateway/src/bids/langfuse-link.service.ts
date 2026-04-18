import { Injectable, NotFoundException } from '@nestjs/common';

/**
 * Returns the browser-facing Langfuse URL for a bid's trace.
 *
 * Phase 3.5: trace_id = bid_id convention (see ai-service LangfuseTracer).
 * When `LANGFUSE_WEB_URL` is unset, the observability stack isn't available
 * in this environment — surface 404 so the frontend hides the link.
 */
@Injectable()
export class LangfuseLinkService {
  getTraceUrl(bidId: string): { url: string } {
    const base = process.env.LANGFUSE_WEB_URL;
    if (!base) {
      throw new NotFoundException(
        'Langfuse observability is not configured (LANGFUSE_WEB_URL unset).',
      );
    }
    const trimmed = base.replace(/\/+$/, '');
    return { url: `${trimmed}/trace/${bidId}` };
  }
}
