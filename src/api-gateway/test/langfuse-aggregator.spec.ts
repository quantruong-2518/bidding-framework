import { chunkedMap } from '../src/audit-dashboard/aggregators/langfuse.aggregator';

describe('chunkedMap', () => {
  it('returns empty array for empty input', async () => {
    expect(await chunkedMap([], 4, async () => 'x')).toEqual([]);
  });

  it('preserves input order in the output', async () => {
    const out = await chunkedMap([1, 2, 3, 4, 5], 2, async (x) => x * 10);
    expect(out).toEqual([10, 20, 30, 40, 50]);
  });

  it('respects the concurrency cap', async () => {
    let inflight = 0;
    let peak = 0;
    const timings = await chunkedMap([1, 2, 3, 4, 5, 6, 7, 8], 3, async (x) => {
      inflight += 1;
      peak = Math.max(peak, inflight);
      await new Promise((r) => setTimeout(r, 5));
      inflight -= 1;
      return x;
    });
    expect(timings).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    expect(peak).toBeLessThanOrEqual(3);
    expect(peak).toBeGreaterThanOrEqual(2);
  });

  it('rethrows the first rejection', async () => {
    await expect(
      chunkedMap([1, 2, 3], 2, async (x) => {
        if (x === 2) throw new Error('nope');
        return x;
      }),
    ).rejects.toThrow(/nope/);
  });
});
