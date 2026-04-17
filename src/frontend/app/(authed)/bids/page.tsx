'use client';

import * as React from 'react';
import Link from 'next/link';
import { PlusCircle } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';
import { BidTable } from '@/components/bids/bid-table';
import { useBids } from '@/lib/hooks/use-bids';

export default function BidsPage(): React.ReactElement {
  const { data, isLoading, isError, error } = useBids();

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Bids</h1>
          <p className="text-sm text-muted-foreground">All opportunities tracked in the framework.</p>
        </div>
        <Link
          href="/bids/new"
          className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          <PlusCircle className="h-4 w-4" />
          New bid
        </Link>
      </div>

      {isError && (
        <div className="rounded-md border border-destructive/60 bg-destructive/10 p-4 text-sm text-destructive">
          Failed to load bids: {(error as Error).message}
        </div>
      )}

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : (
        <BidTable bids={data ?? []} />
      )}
    </main>
  );
}
