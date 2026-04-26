import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AtomTablePreview } from '@/components/bids/atom-table-preview';
import type { AtomPreviewItem } from '@/lib/api/types';

const ATOMS: AtomPreviewItem[] = [
  {
    id: 'REQ-F-001',
    type: 'functional',
    priority: 'MUST',
    category: 'auth',
    source_file: 'sources/01-rfp-main.md',
    body_md: 'SSO required',
    confidence: 0.92,
  },
  {
    id: 'REQ-NFR-002',
    type: 'nfr',
    priority: 'SHOULD',
    category: 'performance',
    source_file: 'sources/02-appendix.md',
    body_md: 'Latency p99 < 200ms',
    confidence: 0.4, // low
  },
];

describe('AtomTablePreview', () => {
  it('renders an atom row per atom with id + type + priority', () => {
    render(<AtomTablePreview atoms={ATOMS} />);
    expect(screen.getByTestId('atom-row-REQ-F-001')).toBeInTheDocument();
    expect(screen.getByTestId('atom-row-REQ-NFR-002')).toBeInTheDocument();
    expect(screen.getByText('REQ-F-001')).toBeInTheDocument();
    expect(screen.getByText('functional')).toBeInTheDocument();
    expect(screen.getAllByTestId('confidence-bar')).toHaveLength(2);
  });

  it('flags low-confidence rows with data-low-confidence=true', () => {
    render(<AtomTablePreview atoms={ATOMS} />);
    const high = screen.getByTestId('atom-row-REQ-F-001');
    const low = screen.getByTestId('atom-row-REQ-NFR-002');
    expect(high.getAttribute('data-low-confidence')).toBe('false');
    expect(low.getAttribute('data-low-confidence')).toBe('true');
  });

  it('shows empty state when atoms list is empty and forwards edit/reject callbacks', () => {
    render(<AtomTablePreview atoms={[]} />);
    expect(screen.getByTestId('atom-table-empty')).toBeInTheDocument();

    const onEdit = vi.fn();
    const onReject = vi.fn();
    render(
      <AtomTablePreview
        atoms={[ATOMS[0]]}
        onEdit={onEdit}
        onToggleReject={onReject}
      />,
    );
    fireEvent.click(screen.getByLabelText('Edit REQ-F-001'));
    fireEvent.click(screen.getByLabelText('Reject REQ-F-001'));
    expect(onEdit).toHaveBeenCalledWith(ATOMS[0]);
    expect(onReject).toHaveBeenCalledWith('REQ-F-001');
  });
});
