'use client';

import * as React from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { CostChart } from '@/components/audit/cost-chart';
import { DecisionTrail } from '@/components/audit/decision-trail';
import {
  downloadCsv,
  fetchSummary,
  type SummaryFilters,
} from '@/lib/api/audit';

function defaultRange(): { from: string; to: string } {
  const now = new Date();
  const from = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
  return {
    from: from.toISOString().slice(0, 10),
    to: now.toISOString().slice(0, 10),
  };
}

/**
 * Cross-bid audit summary (admin only).
 *
 * Reads `/dashboard/audit` and renders:
 * - KPI cards (totals + cost summary)
 * - cost chart (daily bar + agent pie)
 * - recent decisions table
 * - CSV export button
 *
 * Server already caches the response for 5 minutes; the page uses
 * TanStack Query with `staleTime: 60_000` so a tab switch doesn't re-fetch.
 */
export default function AuditPage(): React.ReactElement {
  const initial = defaultRange();
  const [filters, setFilters] = React.useState<SummaryFilters>(initial);
  const [pending, setPending] = React.useState<SummaryFilters>(initial);
  const [csvError, setCsvError] = React.useState<string | null>(null);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['audit-summary', filters],
    queryFn: () => fetchSummary(filters),
    staleTime: 60_000,
  });

  function applyFilters(e: React.FormEvent): void {
    e.preventDefault();
    setFilters(pending);
  }

  async function onDownloadCsv(): Promise<void> {
    setCsvError(null);
    try {
      await downloadCsv(filters);
    } catch (err) {
      setCsvError((err as Error).message);
    }
  }

  return (
    <div className="space-y-6 p-6" data-testid="audit-page">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Audit & cost dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Cross-bid view {filters.from} → {filters.to}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={onDownloadCsv}
            data-testid="export-csv"
          >
            Export CSV
          </Button>
          <Button variant="default" onClick={() => refetch()}>
            Refresh
          </Button>
        </div>
      </header>

      {csvError && (
        <p className="text-sm text-red-600" role="alert">
          CSV export failed: {csvError}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={applyFilters}
            className="grid gap-3 md:grid-cols-6"
            data-testid="filters-form"
          >
            <div>
              <Label htmlFor="f-from">From</Label>
              <Input
                id="f-from"
                type="date"
                value={pending.from ?? ''}
                onChange={(e) =>
                  setPending((p) => ({ ...p, from: e.target.value }))
                }
              />
            </div>
            <div>
              <Label htmlFor="f-to">To</Label>
              <Input
                id="f-to"
                type="date"
                value={pending.to ?? ''}
                onChange={(e) =>
                  setPending((p) => ({ ...p, to: e.target.value }))
                }
              />
            </div>
            <div>
              <Label htmlFor="f-status">Status</Label>
              <Input
                id="f-status"
                placeholder="WON / LOST / …"
                value={pending.status ?? ''}
                onChange={(e) =>
                  setPending((p) => ({ ...p, status: e.target.value }))
                }
              />
            </div>
            <div>
              <Label htmlFor="f-profile">Profile</Label>
              <Input
                id="f-profile"
                placeholder="S / M / L / XL"
                value={pending.profile ?? ''}
                onChange={(e) =>
                  setPending((p) => ({ ...p, profile: e.target.value }))
                }
              />
            </div>
            <div>
              <Label htmlFor="f-client">Client</Label>
              <Input
                id="f-client"
                placeholder="substring"
                value={pending.client ?? ''}
                onChange={(e) =>
                  setPending((p) => ({ ...p, client: e.target.value }))
                }
              />
            </div>
            <div className="flex items-end">
              <Button type="submit" className="w-full">
                Apply
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {isError && (
        <p className="text-sm text-red-600" role="alert">
          Failed to load: {(error as Error).message}
        </p>
      )}

      {data && (
        <>
          {data.warnings.length > 0 && (
            <div
              className="rounded border border-amber-400 bg-amber-50 p-3 text-sm text-amber-900"
              data-testid="warnings-banner"
            >
              <strong>Partial data:</strong>
              <ul className="mt-1 list-disc pl-5">
                {data.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-4">
            <Card>
              <CardContent className="pt-6">
                <div className="text-3xl font-semibold">{data.totals.bids}</div>
                <p className="text-xs text-muted-foreground">Bids in range</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-3xl font-semibold">
                  {data.totals.completed}
                </div>
                <p className="text-xs text-muted-foreground">Completed (WON)</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-3xl font-semibold">
                  ${data.costUsd.total.toFixed(2)}
                </div>
                <p className="text-xs text-muted-foreground">Total LLM cost</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-3xl font-semibold">
                  ${data.costUsd.avgPerBid.toFixed(2)}
                </div>
                <p className="text-xs text-muted-foreground">Avg / bid</p>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Cost charts</CardTitle>
            </CardHeader>
            <CardContent>
              <CostChart byDay={data.byDay} agentCost={data.agentCost} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Recent decisions</CardTitle>
            </CardHeader>
            <CardContent>
              <DecisionTrail
                entries={data.recentDecisions}
                showBid
              />
              {data.recentDecisions.length > 0 && (
                <p className="mt-3 text-xs text-muted-foreground">
                  Click a bid id in the per-bid detail view to drill in:{' '}
                  <Link href="/bids" className="underline">
                    open bids list
                  </Link>
                </p>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {isLoading && !data && (
        <p className="text-sm text-muted-foreground">Loading summary…</p>
      )}
    </div>
  );
}
