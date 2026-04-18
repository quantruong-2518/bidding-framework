'use client';

import * as React from 'react';
import { Badge } from '@/components/ui/badge';
import type { AgentName, AgentStreamState } from '@/lib/ws/use-bid-events';

interface AgentStreamPanelProps {
  agent: AgentName;
  stream: AgentStreamState | null;
}

const AGENT_LABEL: Record<AgentName, string> = {
  ba: 'Business Analysis',
  sa: 'Solution Architecture',
  domain: 'Domain Mining',
};

const NODE_LABEL: Record<string, string> = {
  retrieve_similar: 'Retrieve',
  extract_requirements: 'Extraction (Haiku)',
  classify_signals: 'Classification (Haiku)',
  tag_atoms: 'Tagging (Haiku)',
  synthesize_draft: 'Synthesis (Sonnet)',
  synthesize: 'Synthesis (Sonnet)',
  self_critique: 'Self-critique (Sonnet)',
  critique: 'Self-critique (Sonnet)',
};

/**
 * Live typewriter panel for streaming LLM output from a single S3 agent.
 *
 * Renders nothing when the stream is null (stub path — deterministic fallback
 * produces artifacts in <100 ms and never publishes tokens). Artifact panels
 * above remain the source of truth; this panel is UX candy during live LLM
 * calls only.
 */
export function AgentStreamPanel({
  agent,
  stream,
}: AgentStreamPanelProps): React.ReactElement {
  if (!stream) {
    return (
      <div className="rounded border border-dashed border-border p-3 text-xs text-muted-foreground">
        <strong>{AGENT_LABEL[agent]}</strong> —{' '}
        <span>Agent idle or running in deterministic mode (no token stream).</span>
      </div>
    );
  }
  const nodeLabel = NODE_LABEL[stream.node] ?? stream.node;
  return (
    <div className="rounded border border-border bg-muted/30 p-3 text-xs">
      <div className="mb-2 flex items-center justify-between">
        <div>
          <strong>{AGENT_LABEL[agent]}</strong>{' '}
          <span className="text-muted-foreground">/ {nodeLabel}</span>
        </div>
        <Badge variant={stream.done ? 'success' : 'outline'}>
          {stream.done ? 'done' : 'streaming'}
        </Badge>
      </div>
      <pre
        className="whitespace-pre-wrap break-words font-mono text-[11px] leading-snug text-foreground/90"
        data-testid={`agent-stream-${agent}-text`}
      >
        {stream.text || '…'}
      </pre>
    </div>
  );
}
