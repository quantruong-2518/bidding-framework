import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import * as React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  applyToken,
  useBidEvents,
  type AgentStreamState,
  type AgentTokenEvent,
} from '@/lib/ws/use-bid-events';
import { useAuthStore } from '@/lib/auth/store';

interface MockSocket {
  connected: boolean;
  emit: ReturnType<typeof vi.fn>;
  on: ReturnType<typeof vi.fn>;
  off: ReturnType<typeof vi.fn>;
}

const mockSocket: MockSocket = {
  connected: true,
  emit: vi.fn(),
  on: vi.fn(),
  off: vi.fn(),
};

vi.mock('@/lib/ws/socket', () => ({
  getSocket: vi.fn(() => mockSocket),
  closeSocket: vi.fn(),
  wsBaseUrl: vi.fn(() => 'http://localhost:3001'),
}));

function wrapper({ children }: { children: React.ReactNode }): React.ReactElement {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

function grabEventHandler(): (payload: unknown) => void {
  const call = mockSocket.on.mock.calls.find(
    (c: unknown[]) => c[0] === 'bid.event',
  );
  return call?.[1] as (payload: unknown) => void;
}

describe('applyToken pure function', () => {
  it('starts a fresh buffer when no prior state', () => {
    const evt: AgentTokenEvent = {
      type: 'agent_token',
      agent: 'ba',
      node: 'synthesize_draft',
      attempt: 1,
      seq: 1,
      text_delta: 'Hello',
      done: false,
    };
    expect(applyToken(null, evt)).toEqual<AgentStreamState>({
      node: 'synthesize_draft',
      attempt: 1,
      text: 'Hello',
      done: false,
      lastSeq: 1,
    });
  });

  it('drops tokens from an older attempt', () => {
    const current: AgentStreamState = {
      node: 'synthesize_draft',
      attempt: 2,
      text: 'fresh',
      done: false,
      lastSeq: 5,
    };
    const stale: AgentTokenEvent = {
      type: 'agent_token',
      agent: 'ba',
      node: 'synthesize_draft',
      attempt: 1,
      seq: 99,
      text_delta: 'stale',
      done: false,
    };
    expect(applyToken(current, stale)).toBe(current);
  });

  it('resets text on a newer attempt', () => {
    const current: AgentStreamState = {
      node: 'synthesize_draft',
      attempt: 1,
      text: 'old',
      done: true,
      lastSeq: 10,
    };
    const evt: AgentTokenEvent = {
      type: 'agent_token',
      agent: 'ba',
      node: 'synthesize_draft',
      attempt: 2,
      seq: 1,
      text_delta: 'new',
      done: false,
    };
    expect(applyToken(current, evt)).toEqual<AgentStreamState>({
      node: 'synthesize_draft',
      attempt: 2,
      text: 'new',
      done: false,
      lastSeq: 1,
    });
  });

  it('resets text when node changes within the same attempt', () => {
    const current: AgentStreamState = {
      node: 'extract_requirements',
      attempt: 1,
      text: 'extract output',
      done: true,
      lastSeq: 3,
    };
    const evt: AgentTokenEvent = {
      type: 'agent_token',
      agent: 'ba',
      node: 'synthesize_draft',
      attempt: 1,
      seq: 1,
      text_delta: 'synth',
      done: false,
    };
    const next = applyToken(current, evt)!;
    expect(next.node).toBe('synthesize_draft');
    expect(next.text).toBe('synth');
  });

  it('appends deltas in order and ignores duplicate seq', () => {
    const s0 = applyToken(null, {
      type: 'agent_token',
      agent: 'ba',
      node: 'synthesize_draft',
      attempt: 1,
      seq: 1,
      text_delta: 'A',
      done: false,
    });
    const s1 = applyToken(s0, {
      type: 'agent_token',
      agent: 'ba',
      node: 'synthesize_draft',
      attempt: 1,
      seq: 2,
      text_delta: 'B',
      done: false,
    });
    // Duplicate seq=2 must not append.
    const s2 = applyToken(s1, {
      type: 'agent_token',
      agent: 'ba',
      node: 'synthesize_draft',
      attempt: 1,
      seq: 2,
      text_delta: 'X',
      done: false,
    });
    expect(s2?.text).toBe('AB');
    const done = applyToken(s2, {
      type: 'agent_token',
      agent: 'ba',
      node: 'synthesize_draft',
      attempt: 1,
      seq: 3,
      text_delta: '',
      done: true,
    });
    expect(done?.done).toBe(true);
    expect(done?.text).toBe('AB');
  });
});

describe('useBidEvents — streaming + state_completed buffering', () => {
  beforeEach(() => {
    mockSocket.emit.mockClear();
    mockSocket.on.mockClear();
    mockSocket.off.mockClear();
    useAuthStore.setState({
      accessToken: 'test-token',
      user: { sub: 'demo', username: 'demo', roles: ['bid_manager'] },
      hydrated: true,
    });
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('accumulates agent_token events and flushes on 150ms throttle', () => {
    const { result } = renderHook(() => useBidEvents('bid-xyz'), { wrapper });
    const handler = grabEventHandler();
    expect(handler).toBeDefined();

    act(() => {
      handler({
        type: 'agent_token',
        agent: 'ba',
        node: 'synthesize_draft',
        attempt: 1,
        seq: 1,
        text_delta: 'Hello ',
        done: false,
      });
      handler({
        type: 'agent_token',
        agent: 'ba',
        node: 'synthesize_draft',
        attempt: 1,
        seq: 2,
        text_delta: 'world',
        done: false,
      });
    });
    // Before the throttle elapses nothing is flushed.
    expect(result.current.agentStreams.ba).toBeNull();

    act(() => {
      vi.advanceTimersByTime(160);
    });
    expect(result.current.agentStreams.ba).not.toBeNull();
    expect(result.current.agentStreams.ba?.text).toBe('Hello world');
    expect(result.current.agentStreams.ba?.done).toBe(false);
  });

  it('collects state_completed events into the rolling transitions list', () => {
    const { result } = renderHook(() => useBidEvents('bid-abc'), { wrapper });
    const handler = grabEventHandler();

    act(() => {
      handler({
        type: 'state_completed',
        state: 'S4_DONE',
        profile: 'M',
        artifact_keys: ['convergence'],
        occurred_at: '2026-04-18T12:00:00Z',
      });
      handler({
        type: 'state_completed',
        state: 'S5_DONE',
        profile: 'M',
        artifact_keys: ['hld'],
        occurred_at: '2026-04-18T12:01:00Z',
      });
      vi.advanceTimersByTime(200);
    });
    expect(result.current.stateTransitions).toHaveLength(2);
    expect(result.current.stateTransitions.map((e) => e.state)).toEqual([
      'S4_DONE',
      'S5_DONE',
    ]);
  });

  it('resets agentStreams when bidId changes', () => {
    const { result, rerender } = renderHook(
      (props: { id: string }) => useBidEvents(props.id),
      { wrapper, initialProps: { id: 'bid-a' } },
    );
    const handlerA = grabEventHandler();

    act(() => {
      handlerA({
        type: 'agent_token',
        agent: 'ba',
        node: 'synthesize_draft',
        attempt: 1,
        seq: 1,
        text_delta: 'first bid',
        done: false,
      });
      vi.advanceTimersByTime(200);
    });
    expect(result.current.agentStreams.ba?.text).toBe('first bid');

    rerender({ id: 'bid-b' });
    expect(result.current.agentStreams.ba).toBeNull();
    expect(result.current.stateTransitions).toEqual([]);
  });

  it('still handles approval_needed like Phase 2.4 (backwards compatible)', () => {
    const { result } = renderHook(() => useBidEvents('bid-1'), { wrapper });
    const handler = grabEventHandler();
    act(() => {
      handler({
        type: 'approval_needed',
        state: 'S9',
        workflow_id: 'wf-1',
        round: 1,
        reviewer_index: 0,
        reviewer_count: 1,
        profile: 'M',
      });
    });
    expect(result.current.approvalNeeded?.type).toBe('approval_needed');
  });
});
