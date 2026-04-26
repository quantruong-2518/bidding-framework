'use client';

import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { getPreview } from '@/lib/api/parse-sessions';
import type { PreviewResponse } from '@/lib/api/types';
import { useAuthStore } from '@/lib/auth/store';

/**
 * S0.5 Wave 3 — TanStack Query hook polling
 * `GET /bids/parse/:sid/preview` every 2 s while the session is still
 * PARSING. The poll stops automatically once the session resolves into
 * any terminal state (READY / FAILED / CONFIRMED / ABANDONED). 2 s is
 * the polling cadence the design doc §3.6 recommends; tighter would
 * thrash the LLM activity, looser would feel laggy.
 *
 * Disabled when no auth token is present (the underlying fetch would
 * 401 anyway; this just avoids a noisy console).
 */
export function useParseSession(
  sid: string | null | undefined,
): UseQueryResult<PreviewResponse> {
  const authenticated = useAuthStore((s) => Boolean(s.accessToken));
  return useQuery({
    queryKey: ['parse-session', sid ?? 'none'],
    queryFn: () => getPreview(sid as string),
    enabled: Boolean(sid) && authenticated,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      // Keep polling on undefined data (initial fetch in flight) AND on
      // PARSING. All terminal states stop the polling loop.
      if (status === 'PARSING' || status === undefined) return 2_000;
      return false;
    },
    refetchIntervalInBackground: false,
  });
}
