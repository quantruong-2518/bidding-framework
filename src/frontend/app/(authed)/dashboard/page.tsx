'use client';

import * as React from 'react';
import Link from 'next/link';
import { Briefcase, CheckCircle2, Clock, PlusCircle, XCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useBids } from '@/lib/hooks/use-bids';

export default function DashboardPage(): React.ReactElement {
  const { data: bids, isLoading, isError, error } = useBids();

  const stats = React.useMemo(() => {
    const all = bids ?? [];
    return {
      total: all.length,
      active: all.filter((b) => b.status === 'IN_PROGRESS' || b.status === 'TRIAGED').length,
      awaitingTriage: all.filter((b) => b.status === 'DRAFT').length,
      wins: all.filter((b) => b.status === 'WON').length,
      losses: all.filter((b) => b.status === 'LOST').length,
    };
  }, [bids]);

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Overview of active bidding pipelines.
          </p>
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

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <StatCard
          icon={Briefcase}
          label="Total bids"
          value={stats.total}
          loading={isLoading}
        />
        <StatCard
          icon={Clock}
          label="Awaiting triage"
          value={stats.awaitingTriage}
          loading={isLoading}
          tone="warning"
        />
        <StatCard
          icon={CheckCircle2}
          label="Recent wins"
          value={stats.wins}
          loading={isLoading}
          tone="success"
        />
        <StatCard
          icon={XCircle}
          label="Recent losses"
          value={stats.losses}
          loading={isLoading}
          tone="danger"
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Active pipeline</CardTitle>
          <CardDescription>
            {stats.active} bid{stats.active === 1 ? '' : 's'} running through the workflow.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading && <Skeleton className="h-24 w-full" />}
          {!isLoading && stats.active === 0 && (
            <p className="text-sm text-muted-foreground">
              No active bids. Create one to see it appear here.
            </p>
          )}
          {!isLoading && stats.active > 0 && (
            <ul className="space-y-2 text-sm">
              {bids
                ?.filter((b) => b.status === 'IN_PROGRESS' || b.status === 'TRIAGED')
                .slice(0, 5)
                .map((b) => (
                  <li key={b.id} className="flex items-center justify-between rounded-md border border-border p-3">
                    <div>
                      <div className="font-medium">{b.clientName}</div>
                      <div className="text-xs text-muted-foreground">
                        {b.industry} · {b.estimatedProfile}
                      </div>
                    </div>
                    <Link href={`/bids/${b.id}`} className="text-sm text-primary hover:underline">
                      Open
                    </Link>
                  </li>
                ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </main>
  );
}

interface StatCardProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number;
  loading?: boolean;
  tone?: 'default' | 'warning' | 'success' | 'danger';
}

function StatCard({ icon: Icon, label, value, loading, tone = 'default' }: StatCardProps): React.ReactElement {
  const accent = {
    default: 'text-primary',
    warning: 'text-warning-foreground',
    success: 'text-success',
    danger: 'text-destructive',
  }[tone];

  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <div className="rounded-md bg-muted p-2">
          <Icon className={`h-5 w-5 ${accent}`} />
        </div>
        <div>
          <div className="text-xs uppercase tracking-wide text-muted-foreground">
            {label}
          </div>
          {loading ? (
            <Skeleton className="mt-1 h-6 w-10" />
          ) : (
            <div className="text-2xl font-semibold">{value}</div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
