import * as React from 'react';
import {
  STATE_PALETTE,
  TONE_CLASSES,
  type WorkflowState,
} from '@/lib/utils/state-palette';
import { cn } from '@/lib/utils/cn';

interface StateTimelineProps {
  currentState?: WorkflowState | null;
}

const ORDER: WorkflowState[] = [
  'S0',
  'S1',
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
];

/**
 * Server-renderable vertical timeline — used as a fallback on pages that
 * don't want to ship ReactFlow (e.g. overview summaries).
 */
export function StateTimeline({ currentState }: StateTimelineProps): React.ReactElement {
  return (
    <ol className="space-y-2">
      {ORDER.map((state) => {
        const meta = STATE_PALETTE[state];
        const active = currentState === state;
        return (
          <li
            key={state}
            className={cn(
              'flex items-start gap-3 rounded-md border px-3 py-2 text-sm',
              TONE_CLASSES[meta.tone],
              active && 'ring-2 ring-ring',
            )}
          >
            <span className="font-mono text-xs font-semibold">{meta.state}</span>
            <div>
              <p className="font-medium">{meta.label}</p>
              <p className="text-xs opacity-80">{meta.description}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
