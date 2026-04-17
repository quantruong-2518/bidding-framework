import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorkflowGraph } from '@/components/workflow/workflow-graph';

// Mock reactflow primitives so the component renders without a real DOM canvas.
vi.mock('reactflow', () => {
  const Dummy = ({ children }: { children?: React.ReactNode }) => <>{children}</>;
  const ReactFlow = ({
    nodes,
    nodeTypes,
  }: {
    nodes: Array<{ id: string; data: { kind: string }; type: string }>;
    nodeTypes: Record<string, React.ComponentType<{ data: unknown; selected: boolean }>>;
  }) => (
    <div data-testid="mock-reactflow">
      {nodes.map((n) => {
        const Cmp = nodeTypes[n.type];
        return (
          <div key={n.id} data-testid={`mock-node-${n.id}`}>
            <Cmp data={n.data} selected={false} />
          </div>
        );
      })}
    </div>
  );
  return {
    __esModule: true,
    default: ReactFlow,
    Background: Dummy,
    Controls: Dummy,
    MarkerType: { ArrowClosed: 'ArrowClosed' },
  };
});

describe('WorkflowGraph', () => {
  it('renders all main flow + parallel stream nodes', () => {
    render(<WorkflowGraph currentState="S2" />);
    ['S0', 'S1', 'S2', 'S3a', 'S3b', 'S3c', 'S4', 'S11'].forEach((id) => {
      expect(screen.getByTestId(`mock-node-${id}`)).toBeInTheDocument();
    });
  });

  it('marks the current state node as active', () => {
    render(<WorkflowGraph currentState="S2" />);
    const node = screen.getByTestId('wf-node-S2');
    expect(node.className).toMatch(/animate-pulse-ring|border-primary/);
  });
});
