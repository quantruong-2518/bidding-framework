'use client';

import * as React from 'react';
import Link from 'next/link';
import { format, parseISO } from 'date-fns';
import { StatusBadge } from './status-badge';
import type { Bid } from '@/lib/api/types';

interface BidTableProps {
  bids: Bid[];
}

export function BidTable({ bids }: BidTableProps): React.ReactElement {
  if (bids.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
        No bids yet. Click <strong>New bid</strong> to create one.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="min-w-full divide-y divide-border text-sm">
        <thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th className="px-4 py-3 font-medium">Client</th>
            <th className="px-4 py-3 font-medium">Industry</th>
            <th className="px-4 py-3 font-medium">Profile</th>
            <th className="px-4 py-3 font-medium">Status</th>
            <th className="px-4 py-3 font-medium">Created</th>
            <th className="px-4 py-3 font-medium" aria-label="Actions" />
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {bids.map((bid) => (
            <tr key={bid.id} className="hover:bg-muted/30">
              <td className="px-4 py-3 font-medium text-foreground">
                {bid.clientName}
                <div className="text-xs text-muted-foreground">{bid.region}</div>
              </td>
              <td className="px-4 py-3 text-muted-foreground">{bid.industry}</td>
              <td className="px-4 py-3">
                <span className="inline-block rounded bg-muted px-2 py-0.5 text-xs font-semibold">
                  {bid.estimatedProfile}
                </span>
              </td>
              <td className="px-4 py-3">
                <StatusBadge status={bid.status} />
              </td>
              <td className="px-4 py-3 text-muted-foreground">
                {safeDate(bid.createdAt)}
              </td>
              <td className="px-4 py-3 text-right">
                <Link
                  href={`/bids/${bid.id}`}
                  className="inline-flex h-8 items-center rounded-md border border-border px-3 text-xs font-medium hover:bg-accent"
                >
                  View
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function safeDate(value: string): string {
  try {
    return format(parseISO(value), 'yyyy-MM-dd HH:mm');
  } catch {
    return value;
  }
}
