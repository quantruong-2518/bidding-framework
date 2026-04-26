'use client';

import * as React from 'react';
import { AlertTriangle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import type { ConflictItem } from '@/lib/api/types';

interface ConflictListProps {
  conflicts: ConflictItem[];
}

/**
 * S0.5 Wave 3 — cross-source conflict viewer for the bid preview panel.
 *
 * Renders the §3.6 `conflicts_detected` block. Each row links the conflicting
 * atom IDs alongside a short rationale + severity tag so a reviewer can
 * triage which atoms to edit before confirming.
 */
export function ConflictList({ conflicts }: ConflictListProps): React.ReactElement {
  if (conflicts.length === 0) {
    return (
      <div
        className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground"
        data-testid="conflict-list-empty"
      >
        No cross-source conflicts detected.
      </div>
    );
  }

  return (
    <ul
      className="divide-y divide-border rounded-md border border-border"
      data-testid="conflict-list"
    >
      {conflicts.map((c) => (
        <li
          key={c.id}
          className="flex flex-col gap-1.5 p-3 text-sm"
          data-testid={`conflict-row-${c.id}`}
        >
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-warning" aria-hidden />
            <span className="font-medium">Conflict {c.id}</span>
            {c.severity && (
              <Badge variant={severityVariant(c.severity)}>{c.severity}</Badge>
            )}
          </div>
          <p className="text-muted-foreground">{c.description}</p>
          {c.atom_ids.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {c.atom_ids.map((aid) => (
                <Badge key={aid} variant="outline" className="font-mono">
                  {aid}
                </Badge>
              ))}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

function severityVariant(
  severity: NonNullable<ConflictItem['severity']>,
): 'destructive' | 'warning' | 'default' {
  switch (severity) {
    case 'high':
      return 'destructive';
    case 'medium':
      return 'warning';
    case 'low':
    default:
      return 'default';
  }
}
