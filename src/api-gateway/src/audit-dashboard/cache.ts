import { LRUCache } from 'lru-cache';

/**
 * Thin LRU cache wrapper used by `AuditDashboardService` to dedupe expensive
 * aggregations. TTL is fixed at construction; keys are the full query signature.
 *
 * Kept in-process: a multi-replica deploy (Phase 3.6) will need a Redis
 * backend. That's a module swap — callers use `TtlCache` and don't care.
 */
export class TtlCache<V extends object> {
  private readonly lru: LRUCache<string, V>;

  constructor(options: { ttlMs: number; maxEntries?: number } = { ttlMs: 300_000 }) {
    this.lru = new LRUCache<string, V>({
      max: options.maxEntries ?? 200,
      ttl: options.ttlMs,
      // Re-compute on miss; eager TTL eviction.
      updateAgeOnGet: false,
    });
  }

  async getOrLoad(key: string, loader: () => Promise<V>): Promise<V> {
    const hit = this.lru.get(key);
    if (hit !== undefined) return hit;
    const value = await loader();
    this.lru.set(key, value);
    return value;
  }

  invalidate(key: string): void {
    this.lru.delete(key);
  }

  clear(): void {
    this.lru.clear();
  }

  size(): number {
    return this.lru.size;
  }
}
