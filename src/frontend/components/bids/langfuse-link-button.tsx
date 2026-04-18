'use client';

import * as React from 'react';
import { ExternalLink } from 'lucide-react';
import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils/cn';
import { getBidTraceUrl } from '@/lib/api/bids';
import { useAuthStore } from '@/lib/auth/store';

interface LangfuseLinkButtonProps {
  bidId: string;
}

const ALLOWED_ROLES = new Set(['admin', 'bid_manager']);

/**
 * Opens the Langfuse trace for a bid in a new tab. Hidden unless the current
 * user has an allowed role AND the gateway reports a Langfuse URL (404 when
 * the observability stack is off — we then silently hide the button).
 */
export function LangfuseLinkButton({ bidId }: LangfuseLinkButtonProps): React.ReactElement | null {
  const roles = useAuthStore((state) => state.user?.roles ?? []);
  const hasRole = roles.some((role) => ALLOWED_ROLES.has(role));
  const [url, setUrl] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (!hasRole || !bidId) return;
    let cancelled = false;
    setLoading(true);
    getBidTraceUrl(bidId)
      .then((res) => {
        if (!cancelled) setUrl(res.url);
      })
      .catch(() => {
        if (!cancelled) setUrl(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [bidId, hasRole]);

  if (!hasRole || loading || !url) return null;

  // The project's Button wraps a native `<button>` and does not support
  // `asChild`. Apply the same class names to an anchor so keyboard +
  // screen-reader affordances stay consistent with other outline buttons.
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Open Langfuse trace"
      className={cn(
        buttonVariants({ variant: 'outline', size: 'sm' }),
        'gap-1.5 text-xs',
      )}
    >
      <ExternalLink className="h-3.5 w-3.5" />
      Langfuse trace
    </a>
  );
}
