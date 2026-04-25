'use client';

import * as React from 'react';
import type {
  DecisionTrailEntry,
  WorkflowHistoryEvent,
} from '@/lib/api/audit';

interface AuditTimelineProps {
  decisions: DecisionTrailEntry[];
  events: WorkflowHistoryEvent[];
}

type TimelineItem =
  | {
      kind: 'decision';
      timestamp: string;
      label: string;
      detail: string;
    }
  | {
      kind: 'event';
      timestamp: string;
      label: string;
      detail: string;
    };

/** Interleaves audit decisions + Temporal events on a single vertical track. */
export function AuditTimeline({
  decisions,
  events,
}: AuditTimelineProps): React.ReactElement {
  const items: TimelineItem[] = [
    ...decisions.map((d) => ({
      kind: 'decision' as const,
      timestamp: d.timestamp,
      label: d.action,
      detail: `${d.actor.username} (${d.actor.roles.join(', ') || 'no role'})`,
    })),
    ...events.map((e) => ({
      kind: 'event' as const,
      timestamp: e.timestamp,
      label: e.eventType,
      detail: `event #${e.eventId}`,
    })),
  ].sort((a, b) => a.timestamp.localeCompare(b.timestamp));

  if (items.length === 0) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="timeline-empty">
        Timeline will populate once the bid produces activity.
      </p>
    );
  }

  return (
    <ol
      data-testid="audit-timeline"
      className="relative space-y-3 border-l border-border pl-4"
    >
      {items.map((item, idx) => (
        <li key={`${item.timestamp}-${idx}`} className="relative">
          <span
            className={`absolute -left-[9px] top-1.5 h-3 w-3 rounded-full border ${
              item.kind === 'decision'
                ? 'bg-primary border-primary'
                : 'bg-background border-muted-foreground'
            }`}
          />
          <div className="text-xs">
            <span className="font-mono text-[11px] text-muted-foreground">
              {item.timestamp.slice(0, 19).replace('T', ' ')}
            </span>
            <span className="ml-2 font-mono">{item.label}</span>
            <span className="ml-2 text-muted-foreground">{item.detail}</span>
          </div>
        </li>
      ))}
    </ol>
  );
}
