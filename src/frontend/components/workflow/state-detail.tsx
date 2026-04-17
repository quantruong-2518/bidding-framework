import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  STATE_PALETTE,
  type NodeKind,
  nodeKindToState,
} from '@/lib/utils/state-palette';
import type { WorkflowStatus } from '@/lib/api/types';

interface StateDetailProps {
  selected: NodeKind | null;
  status?: WorkflowStatus;
}

/** Right-pane info box shown next to the workflow graph. */
export function StateDetail({ selected, status }: StateDetailProps): React.ReactElement {
  if (!selected) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Select a state</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Click any node on the left to read what that state does and see the
          data produced so far.
        </CardContent>
      </Card>
    );
  }

  const meta = STATE_PALETTE[nodeKindToState(selected)];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>
            <span className="font-mono">{selected}</span> — {meta.label}
          </CardTitle>
          <Badge variant="outline">{status?.current_state ?? status?.state ?? 'unknown'}</Badge>
        </div>
        <p className="text-sm text-muted-foreground">{meta.description}</p>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {selected === 'S0' && status?.bid_card && (
          <div>
            <h4 className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
              Bid Card
            </h4>
            <dl className="grid grid-cols-2 gap-2 text-xs">
              <dt className="text-muted-foreground">Client</dt>
              <dd>{status.bid_card.client_name ?? '—'}</dd>
              <dt className="text-muted-foreground">Industry</dt>
              <dd>{status.bid_card.industry ?? '—'}</dd>
              <dt className="text-muted-foreground">Profile</dt>
              <dd>{status.bid_card.estimated_profile ?? '—'}</dd>
              <dt className="text-muted-foreground">Deadline</dt>
              <dd>{status.bid_card.deadline ?? '—'}</dd>
            </dl>
          </div>
        )}

        {selected === 'S1' && status?.triage && (
          <div className="space-y-2">
            <p>
              Recommendation:{' '}
              <strong>{status.triage.recommend ?? 'pending'}</strong>
              {typeof status.triage.confidence === 'number' && (
                <span className="ml-2 text-muted-foreground">
                  ({Math.round(status.triage.confidence * 100)}% confidence)
                </span>
              )}
            </p>
            {status.triage.rationale && (
              <p className="text-muted-foreground">{status.triage.rationale}</p>
            )}
          </div>
        )}

        {selected === 'S2' && status?.scoping && (
          <div>
            <h4 className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
              Workstreams
            </h4>
            {status.scoping.workstreams && status.scoping.workstreams.length > 0 ? (
              <ul className="list-disc space-y-1 pl-4">
                {status.scoping.workstreams.map((ws) => (
                  <li key={ws.id}>
                    <strong>{ws.name}</strong>
                    {typeof ws.estimated_effort_md === 'number' && (
                      <span className="ml-2 text-muted-foreground">
                        ~{ws.estimated_effort_md} MD
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground">No workstreams yet.</p>
            )}
            {status.scoping.summary && (
              <p className="mt-2 text-muted-foreground">{status.scoping.summary}</p>
            )}
          </div>
        )}

        {selected !== 'S0' && selected !== 'S1' && selected !== 'S2' && (
          <p className="text-muted-foreground">
            Details for <span className="font-mono">{selected}</span> appear
            once the workflow reaches this state.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
