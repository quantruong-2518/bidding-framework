'use client';

import * as React from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getSocket } from './socket';
import { useAuthStore } from '@/lib/auth/store';
import { bidKeys } from '@/lib/hooks/query-keys';

export type AgentName = 'ba' | 'sa' | 'domain';

export interface AgentTokenEvent {
  type: 'agent_token';
  agent: AgentName;
  node: string;
  attempt: number;
  seq: number;
  text_delta: string;
  done: boolean;
}

export interface StateCompletedEvent {
  type: 'state_completed';
  state: string;
  profile: string;
  artifact_keys: string[];
  occurred_at: string;
}

export interface ApprovalNeededEvent {
  type: 'approval_needed';
  state: string;
  workflow_id: string;
  round: number;
  reviewer_index: number;
  reviewer_count: number;
  profile: string;
}

export interface BidEvent {
  type?: string;
  state?: string;
  workflow_id?: string;
  round?: number;
  reviewer_index?: number;
  reviewer_count?: number;
  profile?: string;
  [key: string]: unknown;
}

export interface AgentStreamState {
  node: string;
  attempt: number;
  text: string;
  done: boolean;
  lastSeq: number;
}

export interface BidEventState {
  connected: boolean;
  lastEventAt: number | null;
  approvalNeeded: BidEvent | null;
  agentStreams: Record<AgentName, AgentStreamState | null>;
  stateTransitions: StateCompletedEvent[];
}

const EMPTY_AGENTS: Record<AgentName, AgentStreamState | null> = {
  ba: null,
  sa: null,
  domain: null,
};

const FLUSH_INTERVAL_MS = 150;
const MAX_TRANSITIONS_RETAINED = 50;

/**
 * Apply a single agent_token event to the accumulated per-agent state.
 *
 * Dedup rules (Phase 2.5 D6):
 *   - Older attempt numbers are ignored (activity retry re-emits tokens under
 *     a higher `attempt`; the frontend discards stale streams).
 *   - A newer attempt OR a new node name resets the text buffer.
 *   - Older or duplicate `seq` within the same (agent, attempt, node) is
 *     skipped so out-of-order delivery doesn't produce scrambled text.
 */
export function applyToken(
  current: AgentStreamState | null,
  evt: AgentTokenEvent,
): AgentStreamState | null {
  if (current && evt.attempt < current.attempt) {
    return current;
  }
  const startNew =
    !current || evt.attempt > current.attempt || evt.node !== current.node;
  if (startNew) {
    return {
      node: evt.node,
      attempt: evt.attempt,
      text: evt.text_delta ?? '',
      done: evt.done,
      lastSeq: evt.seq,
    };
  }
  if (evt.seq <= current.lastSeq && !evt.done) {
    return current;
  }
  return {
    node: current.node,
    attempt: current.attempt,
    text: current.text + (evt.text_delta ?? ''),
    done: evt.done || current.done,
    lastSeq: Math.max(current.lastSeq, evt.seq),
  };
}

/**
 * Subscribe to `bid.event` for a given bidId + route per-type payloads.
 *
 * - `approval_needed` → `approvalNeeded` (unchanged from Phase 2.4).
 * - `agent_token` → buffered per-agent; flushed with a 150 ms throttle to
 *    avoid re-render storms when 3 parallel agents each emit ~50 deltas/sec.
 * - `state_completed` → appended to `stateTransitions` (capped at 50).
 *
 * Also invalidates the workflow-status + detail queries on any event so
 * TanStack Query re-fetches the authoritative BidState (artifact panels are
 * poll-driven; the WS stream is UX candy on top).
 */
export function useBidEvents(bidId: string | null | undefined): BidEventState {
  const queryClient = useQueryClient();
  const token = useAuthStore((s) => s.accessToken);
  const [connected, setConnected] = React.useState(false);
  const [lastEventAt, setLastEventAt] = React.useState<number | null>(null);
  const [approvalNeeded, setApprovalNeeded] = React.useState<BidEvent | null>(null);
  const [agentStreams, setAgentStreams] =
    React.useState<Record<AgentName, AgentStreamState | null>>(EMPTY_AGENTS);
  const [stateTransitions, setStateTransitions] = React.useState<StateCompletedEvent[]>([]);

  const bufferRef = React.useRef<{
    agents: Record<AgentName, AgentStreamState | null>;
    transitions: StateCompletedEvent[];
    agentsDirty: boolean;
  }>({ agents: { ...EMPTY_AGENTS }, transitions: [], agentsDirty: false });
  const flushTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleFlush = React.useCallback(() => {
    if (flushTimer.current !== null) return;
    flushTimer.current = setTimeout(() => {
      flushTimer.current = null;
      if (bufferRef.current.agentsDirty) {
        bufferRef.current.agentsDirty = false;
        setAgentStreams({ ...bufferRef.current.agents });
      }
      if (bufferRef.current.transitions.length > 0) {
        const pending = bufferRef.current.transitions;
        bufferRef.current.transitions = [];
        setStateTransitions((prev) =>
          [...prev, ...pending].slice(-MAX_TRANSITIONS_RETAINED),
        );
      }
    }, FLUSH_INTERVAL_MS);
  }, []);

  React.useEffect(() => {
    if (!bidId || !token) {
      setConnected(false);
      return;
    }

    bufferRef.current = { agents: { ...EMPTY_AGENTS }, transitions: [], agentsDirty: false };
    setAgentStreams(EMPTY_AGENTS);
    setStateTransitions([]);
    setApprovalNeeded(null);

    const socket = getSocket(token);
    if (!socket) return;

    const subscribe = (): void => {
      socket.emit('subscribe', bidId);
    };
    const onConnect = (): void => {
      setConnected(true);
      subscribe();
    };
    const onDisconnect = (): void => setConnected(false);
    const onEvent = (payload?: BidEvent): void => {
      setLastEventAt(Date.now());
      if (!payload || typeof payload !== 'object') return;
      const t = payload.type;
      if (t === 'approval_needed') {
        setApprovalNeeded(payload);
      } else if (t === 'agent_token') {
        const evt = payload as unknown as AgentTokenEvent;
        if (evt.agent === 'ba' || evt.agent === 'sa' || evt.agent === 'domain') {
          bufferRef.current.agents[evt.agent] = applyToken(
            bufferRef.current.agents[evt.agent],
            evt,
          );
          bufferRef.current.agentsDirty = true;
          scheduleFlush();
        }
      } else if (t === 'state_completed') {
        bufferRef.current.transitions.push(payload as unknown as StateCompletedEvent);
        scheduleFlush();
      }
      void queryClient.invalidateQueries({ queryKey: bidKeys.workflow(bidId) });
      void queryClient.invalidateQueries({ queryKey: bidKeys.detail(bidId) });
    };

    socket.on('connect', onConnect);
    socket.on('disconnect', onDisconnect);
    socket.on('bid.event', onEvent);
    socket.on('bid.broadcast', onEvent);

    if (socket.connected) {
      setConnected(true);
      subscribe();
    }

    return () => {
      socket.emit('unsubscribe', bidId);
      socket.off('connect', onConnect);
      socket.off('disconnect', onDisconnect);
      socket.off('bid.event', onEvent);
      socket.off('bid.broadcast', onEvent);
      if (flushTimer.current !== null) {
        clearTimeout(flushTimer.current);
        flushTimer.current = null;
      }
    };
  }, [bidId, token, queryClient, scheduleFlush]);

  return { connected, lastEventAt, approvalNeeded, agentStreams, stateTransitions };
}
