import { NotFoundException } from '@nestjs/common';
import { LangfuseLinkService } from '../src/bids/langfuse-link.service';

describe('LangfuseLinkService', () => {
  const BID_ID = '00000000-0000-0000-0000-000000000042';
  const originalEnv = process.env.LANGFUSE_WEB_URL;

  afterEach(() => {
    if (originalEnv === undefined) {
      delete process.env.LANGFUSE_WEB_URL;
    } else {
      process.env.LANGFUSE_WEB_URL = originalEnv;
    }
  });

  it('returns a trace URL when LANGFUSE_WEB_URL is set', () => {
    process.env.LANGFUSE_WEB_URL = 'http://localhost:3002';
    const service = new LangfuseLinkService();
    expect(service.getTraceUrl(BID_ID)).toEqual({
      url: `http://localhost:3002/trace/${BID_ID}`,
    });
  });

  it('strips trailing slashes before appending the trace path', () => {
    process.env.LANGFUSE_WEB_URL = 'http://localhost:3002/';
    const service = new LangfuseLinkService();
    expect(service.getTraceUrl(BID_ID).url).toBe(
      `http://localhost:3002/trace/${BID_ID}`,
    );
  });

  it('throws NotFoundException when LANGFUSE_WEB_URL is unset', () => {
    delete process.env.LANGFUSE_WEB_URL;
    const service = new LangfuseLinkService();
    expect(() => service.getTraceUrl(BID_ID)).toThrow(NotFoundException);
  });
});
