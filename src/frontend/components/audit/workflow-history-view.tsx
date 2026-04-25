'use client';

import * as React from 'react';
import type { WorkflowHistoryEvent } from '@/lib/api/audit';

interface WorkflowHistoryViewProps {
  events: WorkflowHistoryEvent[];
  warningIfEmpty?: string;
}

/**
 * Collapsible list of Temporal Visibility events. Shows a friendly
 * placeholder when history is empty — most common cause in Phase 3.3 is
 * that `TemporalAggregator` returned a stubbed response (warning surfaced
 * on the parent page).
 */
export function WorkflowHistoryView({
  events,
  warningIfEmpty,
}: WorkflowHistoryViewProps): React.ReactElement {
  if (events.length === 0) {
    return (
      <div
        data-testid="workflow-history-empty"
        className="rounded border border-dashed border-muted-foreground/40 bg-muted/20 p-3 text-xs text-muted-foreground"
      >
        {warningIfEmpty ??
          'Temporal history is not available for this bid yet.'}
      </div>
    );
  }
  return (
    <ul data-testid="workflow-history" className="space-y-1">
      {events.map((event) => (
        <li key={event.eventId}>
          <details className="rounded border border-border px-2 py-1 text-xs">
            <summary className="cursor-pointer font-mono">
              #{event.eventId} · {event.eventType} ·{' '}
              <span className="text-muted-foreground">
                {event.timestamp.slice(0, 19).replace('T', ' ')}
              </span>
            </summary>
            <pre className="mt-2 overflow-auto text-[11px]">
              {JSON.stringify(event.attributes, null, 2)}
            </pre>
          </details>
        </li>
      ))}
    </ul>
  );
}
