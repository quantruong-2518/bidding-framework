import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StateDetail } from '@/components/workflow/state-detail';
import type { ProposalPackage, WorkflowStatus } from '@/lib/api/types';

function buildPackage(overrides: Partial<ProposalPackage> = {}): ProposalPackage {
  return {
    bid_id: 'bid-1',
    title: 'Proposal for Acme Bank',
    sections: [
      {
        heading: 'Cover Page',
        body_markdown: '# Cover Page\n\n- **Client**: Acme Bank',
        sourced_from: ['bid_card'],
      },
      {
        heading: 'Executive Summary',
        body_markdown: '# Executive Summary\n\nModernize the core.',
        sourced_from: ['ba_draft'],
      },
      {
        heading: 'Terms + Appendix',
        body_markdown: '# Terms + Appendix\n\n_Valid 30 days._',
        sourced_from: ['domain_notes'],
      },
    ],
    appendices: [],
    consistency_checks: {
      ba_coverage: true,
      rendered_all_sections: true,
    },
    ...overrides,
  };
}

function buildStatus(overrides: Partial<WorkflowStatus> = {}): WorkflowStatus {
  return {
    current_state: 'S8',
    proposal_package: buildPackage(),
    ...overrides,
  } as WorkflowStatus;
}

describe('ProposalPanel (rendered via StateDetail)', () => {
  it('shows the empty placeholder when no proposal is available', () => {
    render(<StateDetail selected="S8" status={{} as WorkflowStatus} />);
    expect(
      screen.getByText(/appear once the workflow reaches this state/i),
    ).toBeInTheDocument();
  });

  it('renders every section with a collapsible summary + markdown body', () => {
    const { container } = render(
      <StateDetail selected="S8" status={buildStatus()} />,
    );
    expect(screen.getByText('Proposal for Acme Bank')).toBeInTheDocument();

    const sections = screen.getAllByTestId('proposal-section');
    expect(sections).toHaveLength(3);

    // Query <summary> elements specifically — the markdown body also renders
    // the heading as an <h1>, so a plain getByText(heading) is ambiguous.
    const summaries = Array.from(container.querySelectorAll('summary')).map((el) =>
      el.textContent?.trim(),
    );
    expect(summaries).toEqual([
      'Cover Page',
      'Executive Summary',
      'Terms + Appendix',
    ]);
  });

  it('expands the first section by default and collapses the rest', () => {
    render(<StateDetail selected="S8" status={buildStatus()} />);
    const sections = screen.getAllByTestId('proposal-section') as HTMLDetailsElement[];
    expect(sections[0].open).toBe(true);
    expect(sections[1].open).toBe(false);
    expect(sections[2].open).toBe(false);
  });

  it('surfaces consistency_checks as a bulleted list', () => {
    render(<StateDetail selected="S8" status={buildStatus()} />);
    expect(screen.getByText(/ba_coverage/)).toBeInTheDocument();
    expect(screen.getByText(/rendered_all_sections/)).toBeInTheDocument();
  });
});
