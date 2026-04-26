'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { BidPreviewPanel } from '@/components/bids/bid-preview-panel';
import { useParseSession } from '@/lib/hooks/use-parse-session';

interface PageProps {
  params: { sessionId: string };
}

/**
 * S0.5 Wave 3 — preview & confirm page.
 *
 * The hook polls every 2 s while the session is `PARSING`. Terminal states
 * stop the poll automatically. CONFIRMED never normally lands here (the
 * confirm action navigates straight to `/bids/[id]`); we still handle it
 * defensively in case the user reloads after confirm.
 */
export default function PreviewParsePage({ params }: PageProps): React.ReactElement {
  const router = useRouter();
  const { data, isLoading, error } = useParseSession(params.sessionId);

  React.useEffect(() => {
    if (data?.status === 'CONFIRMED') {
      router.replace('/bids');
    }
  }, [data?.status, router]);

  if (isLoading || !data) {
    return <PendingShell heading="Loading parse session…" />;
  }

  if (error) {
    return (
      <ErrorShell
        title="Failed to load preview"
        message={error instanceof Error ? error.message : String(error)}
      />
    );
  }

  if (data.status === 'PARSING') {
    return (
      <PendingShell
        heading="Parsing in progress"
        progress={data.progress}
      />
    );
  }

  if (data.status === 'FAILED') {
    return (
      <ErrorShell
        title="Parse failed"
        message={data.parse_error ?? 'The parser raised an error. Try again.'}
        showRestart
      />
    );
  }

  if (data.status === 'ABANDONED') {
    return (
      <ErrorShell
        title="Session abandoned"
        message="This parse session was abandoned. Start a new upload to retry."
        showRestart
      />
    );
  }

  // READY — render the preview panel.
  return (
    <main className="mx-auto max-w-5xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Preview &amp; confirm
          </h1>
          <p className="text-sm text-muted-foreground">
            Review the suggested bid card, atoms, conflicts, and workflow.
            Edits apply on confirm; the bid record is created atomically.
          </p>
        </div>
        <Badge variant="primary">{data.status}</Badge>
      </div>
      <BidPreviewPanel preview={data} />
    </main>
  );
}

function PendingShell({
  heading,
  progress,
}: {
  heading: string;
  progress?: { stage: string; percent: number };
}): React.ReactElement {
  return (
    <main className="mx-auto max-w-3xl space-y-4 p-6" data-testid="preview-pending">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            {heading}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {progress && (
            <p className="text-sm text-muted-foreground">
              {progress.stage} — {Math.round(progress.percent)}%
            </p>
          )}
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
    </main>
  );
}

function ErrorShell({
  title,
  message,
  showRestart,
}: {
  title: string;
  message: string;
  showRestart?: boolean;
}): React.ReactElement {
  return (
    <main className="mx-auto max-w-3xl space-y-4 p-6" data-testid="preview-error">
      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-destructive">{message}</p>
          <div className="flex gap-2">
            {showRestart && (
              <Link href="/bids/new/upload" className={buttonVariants()}>
                Start a new upload
              </Link>
            )}
            <Link
              href="/bids"
              className={buttonVariants({ variant: 'outline' })}
            >
              Back to bids
            </Link>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
