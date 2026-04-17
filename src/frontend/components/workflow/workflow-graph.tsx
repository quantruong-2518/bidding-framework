'use client';

import * as React from 'react';
import ReactFlow, {
  Background,
  Controls,
  type Edge,
  type Node,
  type NodeProps,
  MarkerType,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { cn } from '@/lib/utils/cn';
import {
  MAIN_FLOW,
  PARALLEL_STREAMS,
  STATE_PALETTE,
  type NodeKind,
  type WorkflowState,
  nodeKindToState,
} from '@/lib/utils/state-palette';

export type NodeStatus = 'done' | 'active' | 'pending' | 'skipped';

interface WorkflowNodeData {
  kind: NodeKind;
  label: string;
  sub: string;
  status: NodeStatus;
}

interface WorkflowGraphProps {
  currentState: WorkflowState | null | undefined;
  onSelect?: (kind: NodeKind) => void;
  selected?: NodeKind | null;
}

const STATUS_STYLE: Record<NodeStatus, string> = {
  done: 'border-success bg-success/10 text-success',
  active:
    'border-primary bg-primary/10 text-primary animate-pulse-ring shadow-lg',
  pending: 'border-border bg-muted text-muted-foreground',
  skipped: 'border-dashed border-border bg-transparent text-muted-foreground',
};

function StateNode({ data, selected }: NodeProps<WorkflowNodeData>): React.ReactElement {
  return (
    <div
      className={cn(
        'rounded-md border-2 px-3 py-2 text-center shadow-sm transition-colors',
        STATUS_STYLE[data.status],
        selected && 'ring-2 ring-ring ring-offset-2 ring-offset-background',
      )}
      style={{ width: 150 }}
      data-testid={`wf-node-${data.kind}`}
    >
      <div className="text-xs font-semibold tracking-wide">{data.kind}</div>
      <div className="text-[11px] leading-tight text-foreground/80">{data.label}</div>
    </div>
  );
}

const nodeTypes = { state: StateNode };

/**
 * Compute node status given the workflow's current state.
 * - Everything before current → done
 * - Current node → active
 * - S3 siblings are all "active" when current_state is S3; "done" if past S3
 * - Everything after current → pending
 */
function computeStatuses(
  current: WorkflowState | null | undefined,
): Record<NodeKind, NodeStatus> {
  const order: NodeKind[] = [
    'S0',
    'S1',
    'S2',
    'S3a',
    'S3b',
    'S3c',
    'S4',
    'S5',
    'S6',
    'S7',
    'S8',
    'S9',
    'S10',
    'S11',
  ];
  const statuses: Record<NodeKind, NodeStatus> = {} as Record<NodeKind, NodeStatus>;

  if (!current) {
    order.forEach((k) => {
      statuses[k] = 'pending';
    });
    return statuses;
  }

  if (current === 'S1_NO_BID') {
    order.forEach((k) => {
      statuses[k] = k === 'S0' || k === 'S1' ? 'done' : 'skipped';
    });
    statuses['S1'] = 'active';
    return statuses;
  }

  const mainOrderForCompare: WorkflowState[] = [
    'S0',
    'S1',
    'S2',
    'S2_DONE',
    'S3',
    'S4',
    'S5',
    'S6',
    'S7',
    'S8',
    'S9',
    'S10',
    'S11',
    'S11_DONE',
  ];

  const currentIdx = mainOrderForCompare.indexOf(current);
  const isS2Complete = currentIdx >= mainOrderForCompare.indexOf('S2_DONE');
  const isPipelineComplete = current === 'S11_DONE';

  // Pipeline terminal: every node is done — short-circuit before the index
  // comparison (which would otherwise mis-classify everything as "pending"
  // because S11_DONE sits past the last node in `order`).
  if (isPipelineComplete) {
    order.forEach((k) => {
      statuses[k] = 'done';
    });
    return statuses;
  }

  order.forEach((kind) => {
    const mapped = nodeKindToState(kind);
    const nodeIdx = mainOrderForCompare.indexOf(mapped);

    if (mapped === 'S2' && isS2Complete) {
      statuses[kind] = 'done';
      return;
    }

    if (nodeIdx < currentIdx) {
      statuses[kind] = 'done';
    } else if (nodeIdx === currentIdx) {
      statuses[kind] = 'active';
    } else {
      statuses[kind] = 'pending';
    }
  });

  return statuses;
}

function buildLayout(
  statuses: Record<NodeKind, NodeStatus>,
): { nodes: Node<WorkflowNodeData>[]; edges: Edge[] } {
  const x = 260;
  const dy = 90;
  const nodes: Node<WorkflowNodeData>[] = [];
  const edges: Edge[] = [];

  const rowOf = (kind: NodeKind): number => {
    const idx = MAIN_FLOW.indexOf(kind);
    if (idx >= 0) return idx < 3 ? idx : idx + 1; // insert a S3 row after S2
    return 3;
  };

  // Main flow nodes
  MAIN_FLOW.forEach((kind) => {
    nodes.push({
      id: kind,
      type: 'state',
      position: { x, y: rowOf(kind) * dy },
      data: {
        kind,
        label: STATE_PALETTE[nodeKindToState(kind)].label,
        sub: STATE_PALETTE[nodeKindToState(kind)].description,
        status: statuses[kind],
      },
    });
  });

  // Parallel S3 nodes at row 3, horizontally offset from the main column
  PARALLEL_STREAMS.forEach((kind, i) => {
    nodes.push({
      id: kind,
      type: 'state',
      position: { x: x + (i - 1) * 200, y: rowOf(kind) * dy },
      data: {
        kind,
        label: STATE_PALETTE['S3'].label.replace('Parallel Streams', subLabel(kind)),
        sub: STATE_PALETTE['S3'].description,
        status: statuses[kind],
      },
    });
  });

  // Edges: S0 → S1 → S2 → (S3a, S3b, S3c) → S4 → … → S11
  const sequential: NodeKind[] = ['S0', 'S1', 'S2'];
  for (let i = 0; i < sequential.length - 1; i += 1) {
    edges.push({
      id: `${sequential[i]}-${sequential[i + 1]}`,
      source: sequential[i],
      target: sequential[i + 1],
      markerEnd: { type: MarkerType.ArrowClosed },
    });
  }
  PARALLEL_STREAMS.forEach((kind) => {
    edges.push({
      id: `S2-${kind}`,
      source: 'S2',
      target: kind,
      markerEnd: { type: MarkerType.ArrowClosed },
    });
    edges.push({
      id: `${kind}-S4`,
      source: kind,
      target: 'S4',
      markerEnd: { type: MarkerType.ArrowClosed },
    });
  });
  const tail: NodeKind[] = ['S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'S11'];
  for (let i = 0; i < tail.length - 1; i += 1) {
    edges.push({
      id: `${tail[i]}-${tail[i + 1]}`,
      source: tail[i],
      target: tail[i + 1],
      markerEnd: { type: MarkerType.ArrowClosed },
    });
  }

  return { nodes, edges };
}

function subLabel(kind: NodeKind): string {
  if (kind === 'S3a') return 'Business Analysis';
  if (kind === 'S3b') return 'Technical Analysis';
  if (kind === 'S3c') return 'Domain Mining';
  return STATE_PALETTE[nodeKindToState(kind)].label;
}

export function WorkflowGraph({
  currentState,
  onSelect,
  selected,
}: WorkflowGraphProps): React.ReactElement {
  const statuses = React.useMemo(() => computeStatuses(currentState), [currentState]);
  const { nodes, edges } = React.useMemo(() => buildLayout(statuses), [statuses]);

  const selectedNodes = React.useMemo(
    () =>
      nodes.map((n) => ({
        ...n,
        selected: selected === (n.data.kind as NodeKind),
      })),
    [nodes, selected],
  );

  return (
    <div
      className="h-[560px] w-full rounded-md border border-border bg-background"
      data-testid="workflow-graph"
    >
      <ReactFlow
        nodes={selectedNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        onNodeClick={(_, node) => onSelect?.(node.data.kind as NodeKind)}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={20} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
