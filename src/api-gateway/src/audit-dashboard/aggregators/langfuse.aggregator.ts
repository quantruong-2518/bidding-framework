import { HttpService } from '@nestjs/axios';
import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { firstValueFrom } from 'rxjs';
import type { BidCostBreakdown } from '../types';

/**
 * Pulls cost + latency telemetry from self-hosted Langfuse's public REST API.
 *
 * Wire contract (Langfuse ≥3.x):
 *   GET /api/public/traces?tags[]={bid_id}
 *   GET /api/public/observations?traceId={trace_id}&type=GENERATION
 *   basic-auth = base64(publicKey:secretKey)
 *
 * When `LANGFUSE_SECRET_KEY` or `LANGFUSE_HOST` is unset the aggregator
 * returns zeros + a single warning — the dashboard renders but the cost
 * panels show placeholders. Same semantics as the ai-service
 * `LangfuseTracer` no-op path (Phase 3.5).
 */
@Injectable()
export class LangfuseAggregator {
  private readonly logger = new Logger(LangfuseAggregator.name);

  constructor(
    private readonly http: HttpService,
    private readonly config: ConfigService,
  ) {}

  /** Returns `null` when Langfuse isn't configured — caller adds a warning. */
  private credentials(): {
    host: string;
    authHeader: string;
  } | null {
    const host = this.config.get<string>('LANGFUSE_HOST');
    const publicKey = this.config.get<string>('LANGFUSE_PUBLIC_KEY');
    const secretKey = this.config.get<string>('LANGFUSE_SECRET_KEY');
    if (!host || !publicKey || !secretKey) return null;
    const auth = Buffer.from(`${publicKey}:${secretKey}`).toString('base64');
    return {
      host: host.replace(/\/+$/, ''),
      authHeader: `Basic ${auth}`,
    };
  }

  isConfigured(): boolean {
    return this.credentials() !== null;
  }

  async forBid(bidId: string): Promise<{
    costs: BidCostBreakdown;
    warning?: string;
  }> {
    const empty: BidCostBreakdown = {
      totalUsd: 0,
      byAgent: {},
      byModel: {},
      generationCount: 0,
      latencyP95Ms: 0,
    };
    const creds = this.credentials();
    if (!creds) {
      return {
        costs: empty,
        warning: 'Langfuse is not configured (LANGFUSE_HOST/PUBLIC_KEY/SECRET_KEY).',
      };
    }

    try {
      const tracesUrl = `${creds.host}/api/public/traces?tags%5B%5D=${encodeURIComponent(bidId)}&limit=50`;
      const traces = await firstValueFrom(
        this.http.get<{ data: Array<{ id: string }> }>(tracesUrl, {
          headers: { Authorization: creds.authHeader },
          timeout: 5_000,
        }),
      );
      const ids = (traces.data?.data ?? []).map((t) => t.id);
      if (ids.length === 0) return { costs: empty };

      const observations = await Promise.all(
        ids.map((id) =>
          firstValueFrom(
            this.http.get<{
              data: Array<{
                type: string;
                name?: string | null;
                model?: string | null;
                usageDetails?: { totalCost?: number };
                latency?: number;
                parentObservationId?: string | null;
              }>;
            }>(
              `${creds.host}/api/public/observations?traceId=${encodeURIComponent(id)}&type=GENERATION&limit=100`,
              {
                headers: { Authorization: creds.authHeader },
                timeout: 5_000,
              },
            ),
          ),
        ),
      );

      const costs = summariseObservations(
        observations.flatMap((r) => r.data?.data ?? []),
      );
      return { costs };
    } catch (err) {
      this.logger.warn(
        `Langfuse fetch failed for bid=${bidId}: ${(err as Error).message}`,
      );
      return {
        costs: empty,
        warning: `Langfuse aggregation failed: ${(err as Error).message}`,
      };
    }
  }

  async aggregateRange(range: {
    from: Date;
    to: Date;
  }): Promise<{
    total: number;
    byAgent: Record<string, number>;
    byDay: Record<string, number>;
    warning?: string;
  }> {
    const creds = this.credentials();
    const empty = { total: 0, byAgent: {}, byDay: {} };
    if (!creds) {
      return {
        ...empty,
        warning: 'Langfuse is not configured — cost panels show 0.',
      };
    }

    try {
      // Langfuse traces list supports `fromTimestamp`/`toTimestamp` (ISO).
      const url = `${creds.host}/api/public/traces?fromTimestamp=${encodeURIComponent(
        range.from.toISOString(),
      )}&toTimestamp=${encodeURIComponent(range.to.toISOString())}&limit=200`;
      const traces = await firstValueFrom(
        this.http.get<{
          data: Array<{ id: string; timestamp?: string }>;
        }>(url, {
          headers: { Authorization: creds.authHeader },
          timeout: 10_000,
        }),
      );
      const items = traces.data?.data ?? [];
      if (items.length === 0) return empty;

      const byDay: Record<string, number> = {};
      const byAgent: Record<string, number> = {};
      let total = 0;

      for (const trace of items) {
        const day = (trace.timestamp ?? range.from.toISOString()).slice(0, 10);
        const obs = await firstValueFrom(
          this.http.get<{
            data: Array<{
              type: string;
              name?: string | null;
              usageDetails?: { totalCost?: number };
            }>;
          }>(
            `${creds.host}/api/public/observations?traceId=${encodeURIComponent(
              trace.id,
            )}&type=GENERATION&limit=100`,
            {
              headers: { Authorization: creds.authHeader },
              timeout: 5_000,
            },
          ),
        );
        const summary = summariseObservations(obs.data?.data ?? []);
        total += summary.totalUsd;
        byDay[day] = (byDay[day] ?? 0) + summary.totalUsd;
        for (const [agent, usd] of Object.entries(summary.byAgent)) {
          byAgent[agent] = (byAgent[agent] ?? 0) + usd;
        }
      }
      return { total, byAgent, byDay };
    } catch (err) {
      this.logger.warn(
        `Langfuse range fetch failed: ${(err as Error).message}`,
      );
      return {
        ...empty,
        warning: `Langfuse aggregation failed: ${(err as Error).message}`,
      };
    }
  }
}

/**
 * Reduces raw Langfuse GENERATION observations into a per-bid cost breakdown.
 *
 * Exported for unit-test isolation — tests feed in hand-crafted observation
 * shapes without standing up an HTTP mock. Agent tag is derived from the
 * observation `name` (`ba.synthesis`, `sa.classify`, `domain.extract`, …).
 */
export function summariseObservations(
  observations: Array<{
    type?: string;
    name?: string | null;
    model?: string | null;
    usageDetails?: { totalCost?: number };
    latency?: number;
  }>,
): BidCostBreakdown {
  const breakdown: BidCostBreakdown = {
    totalUsd: 0,
    byAgent: {},
    byModel: {},
    generationCount: 0,
    latencyP95Ms: 0,
  };
  const latencies: number[] = [];

  for (const obs of observations) {
    if (obs.type && obs.type !== 'GENERATION') continue;
    const cost = obs.usageDetails?.totalCost ?? 0;
    breakdown.totalUsd += cost;
    breakdown.generationCount += 1;
    const agent = tagAgent(obs.name ?? '');
    breakdown.byAgent[agent] = (breakdown.byAgent[agent] ?? 0) + cost;
    const model = obs.model ?? 'unknown';
    breakdown.byModel[model] = (breakdown.byModel[model] ?? 0) + cost;
    if (typeof obs.latency === 'number' && Number.isFinite(obs.latency)) {
      latencies.push(obs.latency);
    }
  }

  breakdown.latencyP95Ms = percentile(latencies, 0.95);
  return breakdown;
}

function tagAgent(name: string): string {
  const n = name.toLowerCase();
  if (n.startsWith('ba')) return 'ba';
  if (n.startsWith('sa')) return 'sa';
  if (n.startsWith('domain')) return 'domain';
  return 'other';
}

function percentile(values: number[], p: number): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const idx = Math.min(
    sorted.length - 1,
    Math.max(0, Math.floor(sorted.length * p)),
  );
  return sorted[idx] ?? 0;
}
