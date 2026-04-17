import { describe, it, expect } from 'vitest';
import {
  STATE_PALETTE,
  MAIN_FLOW,
  PARALLEL_STREAMS,
  TONE_CLASSES,
  nodeKindToState,
  getStateMeta,
  stateLabel,
  type WorkflowState,
  type NodeKind,
} from '@/lib/utils/state-palette';

const ALL_STATES: WorkflowState[] = [
  'S0',
  'S1',
  'S1_NO_BID',
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
];

describe('state-palette', () => {
  it.each(ALL_STATES)('has metadata for %s', (state) => {
    const meta = STATE_PALETTE[state];
    expect(meta).toBeDefined();
    expect(meta.label).toBeTruthy();
    expect(meta.description).toBeTruthy();
    expect(TONE_CLASSES[meta.tone]).toBeTruthy();
  });

  it('main flow includes S0..S11 (minus S3 siblings)', () => {
    expect(MAIN_FLOW).toContain('S0');
    expect(MAIN_FLOW).toContain('S11');
    expect(MAIN_FLOW).not.toContain('S3a' as NodeKind);
  });

  it('parallel streams map onto S3', () => {
    PARALLEL_STREAMS.forEach((kind) => {
      expect(nodeKindToState(kind)).toBe('S3');
    });
  });

  it('getStateMeta returns null on missing state', () => {
    expect(getStateMeta(null)).toBeNull();
    expect(getStateMeta(undefined)).toBeNull();
  });

  it('stateLabel falls back to Unknown', () => {
    expect(stateLabel(null)).toBe('Unknown');
    expect(stateLabel('S0')).toBe('Intake');
  });
});
