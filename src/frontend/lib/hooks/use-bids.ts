'use client';

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import {
  createBid,
  getBid,
  getWorkflowStatus,
  listBids,
  sendTriageSignal,
  triggerWorkflow,
} from '@/lib/api/bids';
import type {
  Bid,
  CreateBidInput,
  TriageSignalInput,
  WorkflowStatus,
  WorkflowTrigger,
} from '@/lib/api/types';
import { useAuthStore } from '@/lib/auth/store';
import { bidKeys } from './query-keys';

export function useBids(): UseQueryResult<Bid[]> {
  const authenticated = useAuthStore((s) => Boolean(s.accessToken));
  return useQuery({
    queryKey: bidKeys.list(),
    queryFn: listBids,
    enabled: authenticated,
    staleTime: 10_000,
  });
}

export function useBid(id: string | null | undefined): UseQueryResult<Bid> {
  const authenticated = useAuthStore((s) => Boolean(s.accessToken));
  return useQuery({
    queryKey: id ? bidKeys.detail(id) : ['bids', 'detail', 'none'],
    queryFn: () => getBid(id as string),
    enabled: Boolean(id) && authenticated,
    staleTime: 5_000,
  });
}

export function useWorkflowStatus(
  id: string | null | undefined,
): UseQueryResult<WorkflowStatus> {
  const authenticated = useAuthStore((s) => Boolean(s.accessToken));
  return useQuery({
    queryKey: id ? bidKeys.workflow(id) : ['bids', 'workflow', 'none'],
    queryFn: () => getWorkflowStatus(id as string),
    enabled: Boolean(id) && authenticated,
    refetchInterval: 15_000,
  });
}

export function useCreateBid(): UseMutationResult<Bid, Error, CreateBidInput> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createBid,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: bidKeys.list() });
    },
  });
}

export function useTriggerWorkflow(): UseMutationResult<
  WorkflowTrigger,
  Error,
  string
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: triggerWorkflow,
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: bidKeys.list() });
      void qc.invalidateQueries({ queryKey: bidKeys.detail(data.bid.id) });
      void qc.invalidateQueries({ queryKey: bidKeys.workflow(data.bid.id) });
    },
  });
}

export function useSendTriageSignal(bidId: string): UseMutationResult<
  { status: string },
  Error,
  TriageSignalInput
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input) => sendTriageSignal(bidId, input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: bidKeys.workflow(bidId) });
      void qc.invalidateQueries({ queryKey: bidKeys.detail(bidId) });
    },
  });
}
