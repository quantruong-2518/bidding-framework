'use client';

import * as React from 'react';
import { Pencil } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { AtomPreviewItem } from '@/lib/api/types';

interface AtomTablePreviewProps {
  atoms: AtomPreviewItem[];
  /** Optional click handler to open the inline editor for an atom. */
  onEdit?: (atom: AtomPreviewItem) => void;
  /** Atom IDs the user has marked rejected (rendered struck-through). */
  rejectedIds?: ReadonlySet<string>;
  onToggleReject?: (atomId: string) => void;
}

/**
 * S0.5 Wave 3 — sample-atom DataTable for the bid preview panel.
 *
 * Columns: ID | Type | Priority | Confidence (visual bar) | Source.
 * The "Edit" trailing column delegates to {@link onEdit} so the parent
 * panel can render the modal. Confidence < 0.6 receives an amber row
 * tint matching the gateway's `low_confidence_count` heuristic.
 */
export function AtomTablePreview({
  atoms,
  onEdit,
  rejectedIds,
  onToggleReject,
}: AtomTablePreviewProps): React.ReactElement {
  if (atoms.length === 0) {
    return (
      <div
        className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground"
        data-testid="atom-table-empty"
      >
        No atoms extracted yet — the parser may still be running.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border border-border">
      <table className="w-full text-sm" data-testid="atom-table">
        <thead className="bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-3 py-2 text-left">ID</th>
            <th className="px-3 py-2 text-left">Type</th>
            <th className="px-3 py-2 text-left">Priority</th>
            <th className="px-3 py-2 text-left">Confidence</th>
            <th className="px-3 py-2 text-left">Source</th>
            {(onEdit || onToggleReject) && (
              <th className="px-3 py-2 text-right">Actions</th>
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {atoms.map((atom) => {
            const lowConf = atom.confidence < 0.6;
            const rejected = rejectedIds?.has(atom.id) ?? false;
            return (
              <tr
                key={atom.id}
                className={`${
                  lowConf ? 'bg-warning/10' : ''
                } ${rejected ? 'opacity-50 line-through' : ''}`}
                data-testid={`atom-row-${atom.id}`}
                data-low-confidence={lowConf ? 'true' : 'false'}
              >
                <td className="px-3 py-2 font-mono text-xs">{atom.id}</td>
                <td className="px-3 py-2">
                  <Badge variant={typeBadge(atom.type)}>{atom.type}</Badge>
                </td>
                <td className="px-3 py-2">
                  <Badge variant={priorityBadge(atom.priority)}>
                    {atom.priority}
                  </Badge>
                </td>
                <td className="px-3 py-2">
                  <ConfidenceBar value={atom.confidence} />
                </td>
                <td className="px-3 py-2 truncate text-xs text-muted-foreground">
                  {atom.source_file}
                </td>
                {(onEdit || onToggleReject) && (
                  <td className="px-3 py-2 text-right">
                    {onEdit && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => onEdit(atom)}
                        aria-label={`Edit ${atom.id}`}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                    )}
                    {onToggleReject && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => onToggleReject(atom.id)}
                        aria-label={
                          rejected
                            ? `Restore ${atom.id}`
                            : `Reject ${atom.id}`
                        }
                      >
                        {rejected ? 'Restore' : 'Reject'}
                      </Button>
                    )}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ConfidenceBar({ value }: { value: number }): React.ReactElement {
  const pct = Math.max(0, Math.min(1, value));
  const tone =
    pct >= 0.8
      ? 'bg-success'
      : pct >= 0.6
        ? 'bg-primary'
        : 'bg-warning';
  return (
    <div className="flex items-center gap-2" data-testid="confidence-bar">
      <div className="h-2 w-16 overflow-hidden rounded bg-muted">
        <div className={`h-full ${tone}`} style={{ width: `${pct * 100}%` }} />
      </div>
      <span className="font-mono text-xs">{pct.toFixed(2)}</span>
    </div>
  );
}

function priorityBadge(
  priority: AtomPreviewItem['priority'],
): 'destructive' | 'warning' | 'primary' | 'default' {
  switch (priority) {
    case 'MUST':
      return 'destructive';
    case 'SHOULD':
      return 'warning';
    case 'COULD':
      return 'primary';
    case 'WONT':
    default:
      return 'default';
  }
}

function typeBadge(
  type: AtomPreviewItem['type'],
): 'success' | 'warning' | 'primary' | 'destructive' | 'default' {
  switch (type) {
    case 'functional':
      return 'success';
    case 'nfr':
      return 'primary';
    case 'compliance':
      return 'destructive';
    case 'timeline':
      return 'warning';
    case 'unclear':
      return 'warning';
    case 'technical':
    default:
      return 'default';
  }
}
