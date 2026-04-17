import * as React from 'react';
import { Badge } from '@/components/ui/badge';
import {
  STATE_PALETTE,
  type WorkflowState,
} from '@/lib/utils/state-palette';
import { cn } from '@/lib/utils/cn';
import type { BidStatus } from '@/lib/api/types';

type BadgeVariant = 'default' | 'primary' | 'success' | 'warning' | 'destructive' | 'outline';

const BID_STATUS_VARIANT: Record<BidStatus, BadgeVariant> = {
  DRAFT: 'outline',
  TRIAGED: 'primary',
  IN_PROGRESS: 'primary',
  WON: 'success',
  LOST: 'destructive',
};

const WORKFLOW_VARIANT = {
  neutral: 'default',
  active: 'primary',
  done: 'success',
  warning: 'warning',
  danger: 'destructive',
  pending: 'outline',
} as const satisfies Record<string, BadgeVariant>;

interface StatusBadgeProps {
  status?: BidStatus;
  state?: WorkflowState | null;
  className?: string;
}

/**
 * Shows either the persisted Bid.status (from the API) or the live workflow
 * state. If both are passed, workflow state wins since it's the more recent
 * signal.
 */
export function StatusBadge({ status, state, className }: StatusBadgeProps): React.ReactElement {
  if (state) {
    const meta = STATE_PALETTE[state];
    return (
      <Badge
        variant={WORKFLOW_VARIANT[meta.tone]}
        className={cn('font-semibold uppercase', className)}
        title={meta.description}
      >
        {meta.state} · {meta.label}
      </Badge>
    );
  }

  const resolved: BidStatus = status ?? 'DRAFT';
  return (
    <Badge variant={BID_STATUS_VARIANT[resolved]} className={cn('uppercase', className)}>
      {resolved}
    </Badge>
  );
}
