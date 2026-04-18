import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AgentStreamPanel } from '@/components/workflow/agent-stream-panel';

describe('AgentStreamPanel', () => {
  it('renders empty idle state when no stream bound', () => {
    render(<AgentStreamPanel agent="ba" stream={null} />);
    expect(screen.getByText(/Business Analysis/)).toBeInTheDocument();
    expect(screen.getByText(/deterministic mode/i)).toBeInTheDocument();
  });

  it('renders streaming badge + accumulated text + node label', () => {
    render(
      <AgentStreamPanel
        agent="sa"
        stream={{
          node: 'synthesize_draft',
          attempt: 1,
          text: 'Partial tech stack analysis…',
          done: false,
          lastSeq: 3,
        }}
      />,
    );
    expect(screen.getByText(/Solution Architecture/)).toBeInTheDocument();
    expect(screen.getByText(/Synthesis \(Sonnet\)/)).toBeInTheDocument();
    expect(screen.getByText(/streaming/i)).toBeInTheDocument();
    expect(screen.getByTestId('agent-stream-sa-text').textContent).toContain(
      'Partial tech stack analysis',
    );
  });

  it('renders done badge once the node finishes', () => {
    render(
      <AgentStreamPanel
        agent="domain"
        stream={{
          node: 'tag_atoms',
          attempt: 1,
          text: 'PCI DSS, HIPAA, GDPR',
          done: true,
          lastSeq: 5,
        }}
      />,
    );
    expect(screen.getByText(/Domain Mining/)).toBeInTheDocument();
    expect(screen.getByText(/Tagging/)).toBeInTheDocument();
    expect(screen.getByText(/^done$/i)).toBeInTheDocument();
    expect(screen.getByTestId('agent-stream-domain-text').textContent).toContain('PCI DSS');
  });
});
