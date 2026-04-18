import '@testing-library/jest-dom/vitest';
import { webcrypto } from 'node:crypto';

// jsdom does not ship a full WebCrypto implementation. Node 20+ provides
// `globalThis.crypto` + `crypto.subtle`, but if jsdom overrides or hides it
// we bolt Node's webcrypto on before any test touches PKCE helpers.
if (!globalThis.crypto || !globalThis.crypto.subtle) {
  Object.defineProperty(globalThis, 'crypto', {
    value: webcrypto,
    writable: true,
    configurable: true,
  });
}
