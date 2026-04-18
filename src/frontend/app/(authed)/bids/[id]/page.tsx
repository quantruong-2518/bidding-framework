'use client';

import * as React from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { format, parseISO } from 'date-fns';
import { Play, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import { StatusBadge } from '@/components/bids/status-badge';
import { TriageReviewPanel } from '@/components/bids/triage-review-panel';
import { ReviewGatePanel } from '@/components/bids/review-gate-panel';
import { LangfuseLinkButton } from '@/components/bids/langfuse-link-button';
import { WorkflowGraph } from '@/components/workflow/workflow-graph';
import { StateDetail } from '@/components/workflow/state-detail';
import {
  useBid,
  useTriggerWorkflow,
  useWorkflowStatus,
} from '@/lib/hooks/use-bids';
import { useBidEvents } from '@/lib/ws/use-bid-events';
import type { NodeKind, WorkflowState } from '@/lib/utils/state-palette';

export default function BidDetailPage(): React.ReactElement {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? '';
  const bid = useBid(id);
  const workflow = useWorkflowStatus(id);
  const trigger = useTriggerWorkflow();
  const { connected, agentStreams } = useBidEvents(id);
  const [selected, setSelected] = React.useState<NodeKind | null>(null);

  const currentState: WorkflowState | null =
    (workflow.data?.current_state as WorkflowState | undefined) ??
    (workflow.data?.state as WorkflowState | undefined) ??
    null;

  const onTrigger = async (): Promise<void> => {
    await trigger.mutateAsync(id);
  };

  if (bid.isLoading) {
    return (
      <main className="mx-auto max-w-6xl p-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="mt-4 h-[500px] w-full" />
      </main>
    );
  }

  if (bid.isError || !bid.data) {
    return (
      <main className="mx-auto max-w-6xl p-6">
        <div className="rounded-md border border-destructive/60 bg-destructive/10 p-4 text-sm text-destructive">
          Failed to load bid: {(bid.error as Error | undefined)?.message ?? 'unknown error'}
        </div>
        <div className="mt-4">
          <Link href="/bids" className="text-sm text-primary hover:underline">
            ← Back to bids
          </Link>
        </div>
      </main>
    );
  }

  const b = bid.data;

  return (
    <main className="mx-auto max-w-7xl space-y-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link href="/bids" className="text-xs text-muted-foreground hover:underline">
            ← Bids
          </Link>
          <h1 className="text-2xl font-semibold tracking-tight">{b.clientName}</h1>
          <p className="text-sm text-muted-foreground">
            {b.industry} · {b.region} · Deadline {safeDate(b.deadline)}
          </p>
          <div className="mt-2 flex gap-2">
            <StatusBadge status={b.status} />
            {currentState && <StatusBadge state={currentState} />}
            <span className="inline-flex items-center text-xs text-muted-foreground">
              {connected ? 'realtime live' : 'realtime offline'}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {!b.workflowId && (
            <Button onClick={() => void onTrigger()} disabled={trigger.isPending}>
              {trigger.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              Trigger workflow
            </Button>
          )}
          {b.workflowId && (
            <span className="rounded-md border border-border bg-muted px-3 py-1.5 text-xs font-mono">
              wf: {b.workflowId}
            </span>
          )}
          {b.workflowId && <LangfuseLinkButton bidId={id} />}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <Card>
          <CardHeader>
            <CardTitle>Workflow</CardTitle>
          </CardHeader>
          <CardContent>
            {workflow.isLoading && !workflow.data ? (
              <Skeleton className="h-[500px] w-full" />
            ) : (
              <WorkflowGraph
                currentState={currentState}
                selected={selected}
                onSelect={setSelected}
              />
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          {currentState === 'S1' && (
            <TriageReviewPanel bidId={id} triage={workflow.data?.triage} />
          )}

          {currentState === 'S9' && (
            <ReviewGatePanel
              bidId={id}
              round={workflow.data?.loop_back_history?.length ?? 0}
              reviews={workflow.data?.reviews}
            />
          )}

          {currentState === 'S9_BLOCKED' && (
            <div className="rounded-md border border-destructive/60 bg-destructive/10 p-4 text-sm text-destructive">
              <strong>Review gate blocked.</strong> The S9 gate exhausted all
              review rounds or received a REJECT. Resolve out-of-band and
              restart the workflow.
            </div>
          )}

          <StateDetail
            selected={selected ?? inferSelected(currentState)}
            status={workflow.data}
            agentStreams={agentStreams}
          />

          <Card>
            <CardHeader>
              <CardTitle>Bid Card</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div>
                <span className="text-muted-foreground">Profile: </span>
                <strong>{b.estimatedProfile}</strong>
              </div>
              <Separator />
              <p className="text-muted-foreground">{b.scopeSummary || 'No scope summary'}</p>
              <Separator />
              <div className="flex flex-wrap gap-1.5">
                {b.technologyKeywords.map((kw) => (
                  <span
                    key={kw}
                    className="rounded bg-muted px-2 py-0.5 text-xs"
                  >
                    {kw}
                  </span>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </main>
  );
}

function inferSelected(state: WorkflowState | null): NodeKind | null {
  if (!state) return null;
  if (state === 'S1_NO_BID') return 'S1';
  if (state === 'S2_DONE') return 'S2';
  if (state === 'S3') return 'S3a';
  if (state === 'S9_BLOCKED') return 'S9';
  if (state === 'S11_DONE') return 'S11';
  return state as NodeKind;
}

function safeDate(value: string): string {
  try {
    return format(parseISO(value), 'yyyy-MM-dd HH:mm');
  } catch {
    return value;
  }
}
