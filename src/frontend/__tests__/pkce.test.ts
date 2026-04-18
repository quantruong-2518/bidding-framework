import { describe, it, expect } from 'vitest';
import {
  base64urlEncode,
  computeCodeChallenge,
  generateCodeVerifier,
  generateState,
} from '@/lib/auth/pkce';

describe('base64urlEncode', () => {
  it('matches the RFC 7636 appendix A test vector', async () => {
    // RFC 7636 appendix B test vector. The verifier bytes below SHA-256 to
    // the published expected challenge.
    const bytes = new Uint8Array([
      116, 24, 223, 180, 151, 153, 224, 37, 79, 250, 96, 125, 216, 173,
      187, 186, 22, 212, 37, 77, 105, 214, 191, 240, 91, 88, 5, 88, 83,
      132, 141, 121,
    ]);
    const verifier = base64urlEncode(bytes);
    expect(verifier).toBe('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk');
    expect(await computeCodeChallenge(verifier)).toBe(
      'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM',
    );
  });

  it('produces URL-safe output with no padding', () => {
    const raw = new Uint8Array([0xff, 0xee, 0xdd, 0xcc, 0xbb, 0xaa, 0x99, 0x88, 0x77, 0x66]);
    const encoded = base64urlEncode(raw);
    expect(encoded).not.toMatch(/[+/=]/);
  });
});

describe('generateCodeVerifier', () => {
  it('produces URL-safe strings between 43 and 128 chars', () => {
    for (let i = 0; i < 10; i += 1) {
      const v = generateCodeVerifier();
      expect(v.length).toBeGreaterThanOrEqual(43);
      expect(v.length).toBeLessThanOrEqual(128);
      expect(v).toMatch(/^[A-Za-z0-9_-]+$/);
    }
  });

  it('produces a different verifier every call', () => {
    const seen = new Set<string>();
    for (let i = 0; i < 20; i += 1) seen.add(generateCodeVerifier());
    expect(seen.size).toBe(20);
  });
});

describe('generateState', () => {
  it('produces non-empty opaque strings', () => {
    const a = generateState();
    const b = generateState();
    expect(a.length).toBeGreaterThan(10);
    expect(a).not.toBe(b);
  });
});

describe('computeCodeChallenge', () => {
  it('is idempotent for the same verifier', async () => {
    const v = generateCodeVerifier();
    const c1 = await computeCodeChallenge(v);
    const c2 = await computeCodeChallenge(v);
    expect(c1).toBe(c2);
  });
});
