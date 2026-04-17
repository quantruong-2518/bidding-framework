import * as React from 'react';
import Link from 'next/link';
import { format, parseISO } from 'date-fns';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { StatusBadge } from './status-badge';
import type { Bid } from '@/lib/api/types';

interface BidCardProps {
  bid: Bid;
}

function safeDate(value: string, fmt: string): string {
  try {
    return format(parseISO(value), fmt);
  } catch {
    return value;
  }
}

export function BidCard({ bid }: BidCardProps): React.ReactElement {
  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle data-testid="bid-card-client">{bid.clientName}</CardTitle>
            <p className="text-sm text-muted-foreground">{bid.industry} · {bid.region}</p>
          </div>
          <StatusBadge status={bid.status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="line-clamp-3 text-muted-foreground">
          {bid.scopeSummary || 'No scope summary yet.'}
        </p>
        <div className="flex flex-wrap gap-1.5">
          {bid.technologyKeywords.slice(0, 6).map((kw) => (
            <Badge key={kw} variant="outline">
              {kw}
            </Badge>
          ))}
        </div>
        <div className="flex items-center justify-between pt-2 text-xs text-muted-foreground">
          <span>Profile: <strong className="text-foreground">{bid.estimatedProfile}</strong></span>
          <span>Due {safeDate(bid.deadline, 'yyyy-MM-dd')}</span>
        </div>
        <div className="flex justify-end">
          <Link
            href={`/bids/${bid.id}`}
            className="text-sm font-medium text-primary hover:underline"
          >
            Open workflow →
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
