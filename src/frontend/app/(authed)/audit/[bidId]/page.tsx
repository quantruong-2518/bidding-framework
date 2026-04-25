'use client';

import * as React from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AuditTimeline } from '@/components/audit/audit-timeline';
import { DecisionTrail } from '@/components/audit/decision-trail';
import { WorkflowHistoryView } from '@/components/audit/workflow-history-view';
import { fetchBidAudit } from '@/lib/api/audit';

/**
 * Per-bid drill-down. Three panels:
 * 1. Summary card (status, duration, total cost)
 * 2. Timeline (decisions + events interleaved)
 * 3. Separate decision-trail table + Temporal event list
 */
export default function BidAuditDetailPage(): React.ReactElement {
  const params = useParams<{ bidId: string }>();
  const bidId = params?.bidId ?? '';

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['bid-audit', bidId],
    queryFn: () => fetchBidAudit(bidId),
    enabled: Boolean(bidId),
    staleTime: 60_000,
  });

  if (!bidId) {
    return <p className="p-6 text-sm text-muted-foreground">Missing bid id.</p>;
  }

  return (
    <div className="space-y-6 p-6" data-testid="bid-audit-page">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Bid audit</h1>
          <p className="font-mono text-xs text-muted-foreground">{bidId}</p>
        </div>
        <Link href="/audit" className="text-sm underline">
          ← Back to dashboard
        </Link>
      </header>

      {isError && (
        <p className="text-sm text-red-600" role="alert">
          {(error as Error).message}
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
                <div className="text-lg font-semibold">
                  {data.summary.status}
                </div>
                <p className="text-xs text-muted-foreground">Status</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-lg font-semibold">
                  {data.summary.totalDurationMs !== null
                    ? `${(data.summary.totalDurationMs / 1000 / 60).toFixed(1)} min`
                    : '—'}
                </div>
                <p className="text-xs text-muted-foreground">Duration</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-lg font-semibold">
                  ${data.costs.totalUsd.toFixed(4)}
                </div>
                <p className="text-xs text-muted-foreground">
                  Total LLM cost ({data.costs.generationCount} gens)
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-lg font-semibold">
                  {Math.round(data.costs.latencyP95Ms)} ms
                </div>
                <p className="text-xs text-muted-foreground">p95 latency</p>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <AuditTimeline
                decisions={data.decisionTrail}
                events={data.workflowHistory}
              />
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Decision trail</CardTitle>
              </CardHeader>
              <CardContent>
                <DecisionTrail entries={data.decisionTrail} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Workflow history</CardTitle>
              </CardHeader>
              <CardContent>
                <WorkflowHistoryView
                  events={data.workflowHistory}
                  warningIfEmpty={
                    data.warnings.find((w) =>
                      w.toLowerCase().includes('temporal'),
                    ) ?? undefined
                  }
                />
              </CardContent>
            </Card>
          </div>
        </>
      )}

      {isLoading && !data && (
        <p className="text-sm text-muted-foreground">Loading detail…</p>
      )}
    </div>
  );
}
