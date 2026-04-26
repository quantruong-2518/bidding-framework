'use client';

import * as React from 'react';
import { Clock, DollarSign, Users, Workflow } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import type { SuggestedWorkflow } from '@/lib/api/types';

interface WorkflowProposalCardProps {
  workflow: SuggestedWorkflow | null;
}

/**
 * S0.5 Wave 3 — proposed workflow card.
 *
 * Renders the §3.6 `suggested_workflow` block: profile + state pipeline +
 * estimated cost + estimated duration + review-gate parameters. The fields
 * are read-only here; the bid manager picks an override (if any) on the
 * SuggestedBidCard form above this card.
 */
export function WorkflowProposalCard({
  workflow,
}: WorkflowProposalCardProps): React.ReactElement {
  if (!workflow) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Suggested workflow</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Workflow proposal not available yet — waiting for the parser
            to settle the suggested profile.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card data-testid="workflow-proposal-card">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle>Suggested workflow</CardTitle>
          <Badge variant="primary">Profile {workflow.profile}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <Workflow className="h-3.5 w-3.5" />
            Pipeline
          </div>
          <div
            className="flex flex-wrap gap-1.5"
            data-testid="workflow-pipeline"
          >
            {workflow.pipeline.map((state) => (
              <Badge key={state} variant="outline" className="font-mono">
                {state}
              </Badge>
            ))}
          </div>
        </div>

        <Separator />

        <div className="grid grid-cols-2 gap-4 text-sm">
          <Stat
            icon={<DollarSign className="h-3.5 w-3.5" />}
            label="Est. token cost"
            value={`$${workflow.estimated_total_token_cost_usd.toFixed(2)}`}
            testId="workflow-cost"
          />
          <Stat
            icon={<Clock className="h-3.5 w-3.5" />}
            label="Est. duration"
            value={`${workflow.estimated_duration_hours.toFixed(1)} h`}
            testId="workflow-duration"
          />
        </div>

        <Separator />

        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <Users className="h-3.5 w-3.5" />
            Review gate (S9)
          </div>
          <ul
            className="grid grid-cols-3 gap-2 text-sm"
            data-testid="workflow-review-gate"
          >
            <Stat
              label="Reviewers"
              value={String(workflow.review_gate.reviewer_count)}
              compact
            />
            <Stat
              label="Timeout"
              value={`${workflow.review_gate.timeout_hours} h`}
              compact
            />
            <Stat
              label="Max rounds"
              value={String(workflow.review_gate.max_rounds)}
              compact
            />
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}

interface StatProps {
  icon?: React.ReactNode;
  label: string;
  value: string;
  testId?: string;
  compact?: boolean;
}

function Stat({
  icon,
  label,
  value,
  testId,
  compact,
}: StatProps): React.ReactElement {
  return (
    <div className="flex flex-col gap-0.5" data-testid={testId}>
      <span className="flex items-center gap-1 text-xs uppercase tracking-wide text-muted-foreground">
        {icon}
        {label}
      </span>
      <span className={compact ? 'text-sm font-semibold' : 'text-base font-semibold'}>
        {value}
      </span>
    </div>
  );
}
