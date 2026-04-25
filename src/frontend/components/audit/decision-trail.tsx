'use client';

import * as React from 'react';
import type { DecisionTrailEntry } from '@/lib/api/audit';

interface DecisionTrailProps {
  entries: Array<DecisionTrailEntry & { bidId?: string | null }>;
  showBid?: boolean;
}

/**
 * Flat table of audit_log rows. Each row = one role-gated HTTP call.
 *
 * Phase 3.3 does not try to semantically rename actions (e.g.,
 * `POST /bids/:id/workflow/triage-signal` → `triage.submitted`) — that's a
 * product decision the dashboard iterates on once users request it.
 */
export function DecisionTrail({
  entries,
  showBid = false,
}: DecisionTrailProps): React.ReactElement {
  if (entries.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No decisions recorded in this range.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table
        data-testid="decision-trail"
        className="w-full text-left text-xs"
      >
        <thead className="text-muted-foreground">
          <tr className="border-b border-border">
            <th className="py-2 pr-3">Time</th>
            <th className="py-2 pr-3">User</th>
            <th className="py-2 pr-3">Roles</th>
            <th className="py-2 pr-3">Action</th>
            {showBid && <th className="py-2 pr-3">Bid</th>}
            <th className="py-2 pr-3">Status</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e, idx) => (
            <tr
              key={`${e.timestamp}-${idx}`}
              className="border-b border-border/50"
            >
              <td className="py-1 pr-3 font-mono text-[11px]">
                {formatTimestamp(e.timestamp)}
              </td>
              <td className="py-1 pr-3">{e.actor.username}</td>
              <td className="py-1 pr-3 text-muted-foreground">
                {e.actor.roles.join(', ') || '—'}
              </td>
              <td className="py-1 pr-3 font-mono">{e.action}</td>
              {showBid && (
                <td className="py-1 pr-3 font-mono">
                  {e.bidId ?? '—'}
                </td>
              )}
              <td className={`py-1 pr-3 ${statusClass(e.statusCode)}`}>
                {e.statusCode}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatTimestamp(ts: string): string {
  if (!ts) return '—';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toISOString().replace('T', ' ').slice(0, 19);
}

function statusClass(code: number): string {
  if (code >= 500) return 'text-red-600 font-semibold';
  if (code >= 400) return 'text-amber-600';
  return 'text-emerald-600';
}
