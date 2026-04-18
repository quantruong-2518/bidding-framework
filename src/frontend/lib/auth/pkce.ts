/**
 * Phase 3.2a — PKCE (RFC 7636) helpers.
 *
 * - `generateCodeVerifier` — cryptographically random URL-safe string
 *   between 43 and 128 chars, per RFC 7636 §4.1.
 * - `computeCodeChallenge` — `base64url(SHA256(code_verifier))`, the S256
 *   method required by Keycloak client attribute `pkce.code.challenge.method`.
 *
 * Browser-only — relies on `crypto.subtle`. `sessionStorage` persistence lives
 * in `keycloak-url.ts` so these helpers stay pure + testable.
 */

const VERIFIER_BYTES = 48; // 48 random bytes → 64-char base64url string.

/**
 * Encode raw bytes as base64url without padding — used for both the code
 * verifier (random bytes) and the code challenge (SHA-256 digest).
 */
export function base64urlEncode(bytes: ArrayBuffer | Uint8Array): string {
  const buf =
    bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let binary = '';
  for (const byte of buf) {
    binary += String.fromCharCode(byte);
  }
  const b64 =
    typeof btoa === 'function'
      ? btoa(binary)
      : Buffer.from(binary, 'binary').toString('base64');
  return b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/**
 * Generate a 43–128 char URL-safe verifier (RFC 7636 §4.1). The default size
 * yields 64 chars — middle of the allowed range, plenty of entropy.
 */
export function generateCodeVerifier(size = VERIFIER_BYTES): string {
  const cryptoObj = resolveCrypto();
  const bytes = new Uint8Array(size);
  cryptoObj.getRandomValues(bytes);
  return base64urlEncode(bytes);
}

/** SHA-256 the verifier and return its base64url-encoded digest. */
export async function computeCodeChallenge(verifier: string): Promise<string> {
  const cryptoObj = resolveCrypto();
  const data = new TextEncoder().encode(verifier);
  const digest = await cryptoObj.subtle.digest('SHA-256', data);
  return base64urlEncode(digest);
}

/** 32 bytes of opaque state — guards against CSRF on the callback. */
export function generateState(size = 16): string {
  const cryptoObj = resolveCrypto();
  const bytes = new Uint8Array(size);
  cryptoObj.getRandomValues(bytes);
  return base64urlEncode(bytes);
}

function resolveCrypto(): Crypto {
  const g = globalThis as typeof globalThis & { crypto?: Crypto };
  if (!g.crypto || !g.crypto.subtle) {
    throw new Error(
      'PKCE requires the WebCrypto API (crypto.subtle). Run in a modern browser.',
    );
  }
  return g.crypto;
}
