import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  STATE_PALETTE,
  type NodeKind,
  nodeKindToState,
} from '@/lib/utils/state-palette';
import type { WorkflowStatus } from '@/lib/api/types';
import type {
  AgentName,
  AgentStreamState,
} from '@/lib/ws/use-bid-events';
import { AgentStreamPanel } from '@/components/workflow/agent-stream-panel';

interface StateDetailProps {
  selected: NodeKind | null;
  status?: WorkflowStatus;
  agentStreams?: Record<AgentName, AgentStreamState | null>;
}

const NODE_KIND_TO_AGENT: Partial<Record<NodeKind, AgentName>> = {
  S3a: 'ba',
  S3b: 'sa',
  S3c: 'domain',
};

/** Right-pane info box shown next to the workflow graph. */
export function StateDetail({
  selected,
  status,
  agentStreams,
}: StateDetailProps): React.ReactElement {
  if (!selected) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Select a state</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Click any node on the left to read what that state does and see the
          data produced so far.
        </CardContent>
      </Card>
    );
  }

  const meta = STATE_PALETTE[nodeKindToState(selected)];
  const streamAgent = NODE_KIND_TO_AGENT[selected];
  const currentState = status?.current_state ?? status?.state;
  const showStream =
    streamAgent !== undefined && currentState === 'S3' && agentStreams;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>
            <span className="font-mono">{selected}</span> — {meta.label}
          </CardTitle>
          <Badge variant="outline">{status?.current_state ?? status?.state ?? 'unknown'}</Badge>
        </div>
        <p className="text-sm text-muted-foreground">{meta.description}</p>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {showStream && streamAgent && (
          <AgentStreamPanel
            agent={streamAgent}
            stream={agentStreams[streamAgent]}
          />
        )}
        <ArtifactPanel selected={selected} status={status} />
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Per-node artifact panels. Each one prefers compact summaries over full
// dumps — Phase 3 can expand individual views when needed.
// ---------------------------------------------------------------------------

function ArtifactPanel({
  selected,
  status,
}: {
  selected: NodeKind;
  status?: WorkflowStatus;
}): React.ReactElement {
  if (selected === 'S0') return <BidCardPanel status={status} />;
  if (selected === 'S1') return <TriagePanel status={status} />;
  if (selected === 'S2') return <ScopingPanel status={status} />;
  if (selected === 'S3a') return <BADraftPanel status={status} />;
  if (selected === 'S3b') return <SADraftPanel status={status} />;
  if (selected === 'S3c') return <DomainNotesPanel status={status} />;
  if (selected === 'S4') return <ConvergencePanel status={status} />;
  if (selected === 'S5') return <HLDPanel status={status} />;
  if (selected === 'S6') return <WBSPanel status={status} />;
  if (selected === 'S7') return <PricingPanel status={status} />;
  if (selected === 'S8') return <ProposalPanel status={status} />;
  if (selected === 'S9') return <ReviewsPanel status={status} />;
  if (selected === 'S10') return <SubmissionPanel status={status} />;
  if (selected === 'S11') return <RetrospectivePanel status={status} />;
  return <Empty label={selected} />;
}

function Empty({ label }: { label: string }): React.ReactElement {
  return (
    <p className="text-muted-foreground">
      Details for <span className="font-mono">{label}</span> appear once the
      workflow reaches this state.
    </p>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }): React.ReactElement {
  return (
    <h4 className="mb-1 text-xs font-semibold uppercase text-muted-foreground">
      {children}
    </h4>
  );
}

function ConfidenceBar({ value }: { value: number }): React.ReactElement {
  const pct = Math.max(0, Math.min(1, value));
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <span>Confidence</span>
      <div className="h-1.5 w-24 overflow-hidden rounded bg-muted">
        <div className="h-full bg-primary" style={{ width: `${pct * 100}%` }} />
      </div>
      <span>{Math.round(pct * 100)}%</span>
    </div>
  );
}

function BidCardPanel({ status }: { status?: WorkflowStatus }): React.ReactElement {
  if (!status?.bid_card) return <Empty label="S0" />;
  const b = status.bid_card;
  return (
    <div>
      <SectionTitle>Bid Card</SectionTitle>
      <dl className="grid grid-cols-2 gap-2 text-xs">
        <dt className="text-muted-foreground">Client</dt>
        <dd>{b.client_name ?? '—'}</dd>
        <dt className="text-muted-foreground">Industry</dt>
        <dd>{b.industry ?? '—'}</dd>
        <dt className="text-muted-foreground">Profile</dt>
        <dd>{b.estimated_profile ?? '—'}</dd>
        <dt className="text-muted-foreground">Deadline</dt>
        <dd>{b.deadline ?? '—'}</dd>
      </dl>
    </div>
  );
}

function TriagePanel({ status }: { status?: WorkflowStatus }): React.ReactElement {
  if (!status?.triage) return <Empty label="S1" />;
  const t = status.triage;
  return (
    <div className="space-y-2">
      <p>
        Recommendation: <strong>{t.recommend ?? 'pending'}</strong>
        {typeof t.confidence === 'number' && (
          <span className="ml-2 text-muted-foreground">
            ({Math.round(t.confidence * 100)}% confidence)
          </span>
        )}
      </p>
      {t.rationale && <p className="text-muted-foreground">{t.rationale}</p>}
    </div>
  );
}

function ScopingPanel({ status }: { status?: WorkflowStatus }): React.ReactElement {
  if (!status?.scoping) return <Empty label="S2" />;
  return (
    <div>
      <SectionTitle>Workstreams</SectionTitle>
      {status.scoping.workstreams && status.scoping.workstreams.length > 0 ? (
        <ul className="list-disc space-y-1 pl-4">
          {status.scoping.workstreams.map((ws) => (
            <li key={ws.id}>
              <strong>{ws.name}</strong>
              {typeof ws.estimated_effort_md === 'number' && (
                <span className="ml-2 text-muted-foreground">
                  ~{ws.estimated_effort_md} MD
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground">Scoping complete — requirement atoms decomposed.</p>
      )}
      {status.scoping.summary && (
        <p className="mt-2 text-muted-foreground">{status.scoping.summary}</p>
      )}
    </div>
  );
}

function BADraftPanel({ status }: { status?: WorkflowStatus }): React.ReactElement {
  const ba = status?.ba_draft;
  if (!ba) return <Empty label="S3a" />;
  return (
    <div className="space-y-3">
      <ConfidenceBar value={ba.confidence} />
      <p className="text-muted-foreground">{ba.executive_summary}</p>
      <div>
        <SectionTitle>Functional requirements ({ba.functional_requirements.length})</SectionTitle>
        <ul className="list-disc space-y-1 pl-4">
          {ba.functional_requirements.slice(0, 4).map((fr) => (
            <li key={fr.id}>
              <span className="font-mono text-xs">{fr.id}</span>{' '}
              <Badge variant="outline">{fr.priority}</Badge> {fr.title}
            </li>
          ))}
          {ba.functional_requirements.length > 4 && (
            <li className="text-muted-foreground">
              +{ba.functional_requirements.length - 4} more…
            </li>
          )}
        </ul>
      </div>
      {ba.risks.length > 0 && (
        <div>
          <SectionTitle>Risks ({ba.risks.length})</SectionTitle>
          <ul className="list-disc space-y-1 pl-4">
            {ba.risks.slice(0, 3).map((r, idx) => (
              <li key={idx}>
                <strong>{r.title}</strong>{' '}
                <span className="text-muted-foreground">
                  (likelihood {r.likelihood}, impact {r.impact})
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function SADraftPanel({ status }: { status?: WorkflowStatus }): React.ReactElement {
  const sa = status?.sa_draft;
  if (!sa) return <Empty label="S3b" />;
  return (
    <div className="space-y-3">
      <ConfidenceBar value={sa.confidence} />
      <div>
        <SectionTitle>Tech stack</SectionTitle>
        <ul className="list-disc space-y-1 pl-4">
          {sa.tech_stack.map((ts, idx) => (
            <li key={idx}>
              <span className="font-semibold">{ts.layer}:</span> {ts.choice}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <SectionTitle>NFR targets</SectionTitle>
        <dl className="grid grid-cols-2 gap-1 text-xs">
          {Object.entries(sa.nfr_targets).map(([k, v]) => (
            <React.Fragment key={k}>
              <dt className="text-muted-foreground">{k}</dt>
              <dd>{v}</dd>
            </React.Fragment>
          ))}
        </dl>
      </div>
    </div>
  );
}

function DomainNotesPanel({ status }: { status?: WorkflowStatus }): React.ReactElement {
  const dn = status?.domain_notes;
  if (!dn) return <Empty label="S3c" />;
  return (
    <div className="space-y-3">
      <ConfidenceBar value={dn.confidence} />
      <div>
        <SectionTitle>Compliance ({dn.compliance.length})</SectionTitle>
        <ul className="list-disc space-y-1 pl-4">
          {dn.compliance.slice(0, 4).map((c, idx) => (
            <li key={idx}>
              <strong>{c.framework}</strong> — {c.requirement}
            </li>
          ))}
        </ul>
      </div>
      {dn.industry_constraints.length > 0 && (
        <div>
          <SectionTitle>Constraints</SectionTitle>
          <ul className="list-disc space-y-1 pl-4">
            {dn.industry_constraints.map((c, idx) => (
              <li key={idx}>{c}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ConvergencePanel({ status }: { status?: WorkflowStatus }): React.ReactElement {
  const c = status?.convergence;
  if (!c) return <Empty label="S4" />;
  return (
    <div className="space-y-3">
      <p className="text-muted-foreground">{c.unified_summary}</p>
      <div>
        <SectionTitle>Readiness</SectionTitle>
        <dl className="grid grid-cols-2 gap-1 text-xs">
          {Object.entries(c.readiness).map(([stream, score]) => (
            <React.Fragment key={stream}>
              <dt className="text-muted-foreground">{stream}</dt>
              <dd>{Math.round(score * 100)}%</dd>
            </React.Fragment>
          ))}
        </dl>
      </div>
      {c.open_questions.length > 0 && (
        <div>
          <SectionTitle>Open questions</SectionTitle>
          <ul className="list-disc space-y-1 pl-4">
            {c.open_questions.map((q, idx) => (
              <li key={idx}>{q}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function HLDPanel({ status }: { status?: WorkflowStatus }): React.ReactElement {
  const h = status?.hld;
  if (!h) return <Empty label="S5" />;
  return (
    <div className="space-y-3">
      <p className="text-muted-foreground">{h.architecture_overview}</p>
      <div>
        <SectionTitle>Components ({h.components.length})</SectionTitle>
        <ul className="list-disc space-y-1 pl-4">
          {h.components.map((comp, idx) => (
            <li key={idx}>
              <strong>{comp.name}</strong> — {comp.responsibility}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function WBSPanel({ status }: { status?: WorkflowStatus }): React.ReactElement {
  const w = status?.wbs;
  if (!w) return <Empty label="S6" />;
  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-2 gap-1 text-xs">
        <dt className="text-muted-foreground">Total effort</dt>
        <dd>{w.total_effort_md.toFixed(1)} MD</dd>
        <dt className="text-muted-foreground">Timeline</dt>
        <dd>~{w.timeline_weeks} weeks</dd>
        <dt className="text-muted-foreground">Critical path</dt>
        <dd className="font-mono text-[11px]">{w.critical_path.join(' → ') || '—'}</dd>
      </dl>
      <div>
        <SectionTitle>Work items</SectionTitle>
        <ul className="list-disc space-y-1 pl-4">
          {w.items.slice(0, 6).map((it) => (
            <li key={it.id}>
              <span className="font-mono text-xs">{it.id}</span> — {it.name}{' '}
              <span className="text-muted-foreground">({it.effort_md} MD)</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function PricingPanel({ status }: { status?: WorkflowStatus }): React.ReactElement {
  const p = status?.pricing;
  if (!p) return <Empty label="S7" />;
  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-2 gap-1 text-xs">
        <dt className="text-muted-foreground">Model</dt>
        <dd className="font-mono">{p.model}</dd>
        <dt className="text-muted-foreground">Subtotal</dt>
        <dd>
          {p.subtotal.toLocaleString()} {p.currency}
        </dd>
        <dt className="text-muted-foreground">Margin</dt>
        <dd>{p.margin_pct.toFixed(1)}%</dd>
        <dt className="font-semibold">Total</dt>
        <dd className="font-semibold">
          {p.total.toLocaleString()} {p.currency}
        </dd>
      </dl>
      {Object.keys(p.scenarios).length > 0 && (
        <div>
          <SectionTitle>Scenarios</SectionTitle>
          <dl className="grid grid-cols-2 gap-1 text-xs">
            {Object.entries(p.scenarios).map(([name, amt]) => (
              <React.Fragment key={name}>
                <dt className="text-muted-foreground">{name}</dt>
                <dd>
                  {amt.toLocaleString()} {p.currency}
                </dd>
              </React.Fragment>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}

function ProposalPanel({ status }: { status?: WorkflowStatus }): React.ReactElement {
  const pkg = status?.proposal_package;
  if (!pkg) return <Empty label="S8" />;
  return (
    <div className="space-y-3">
      <p>
        <strong>{pkg.title}</strong>
      </p>
      <div>
        <SectionTitle>Sections ({pkg.sections.length})</SectionTitle>
        <ul className="list-disc space-y-1 pl-4">
          {pkg.sections.map((s, idx) => (
            <li key={idx}>{s.heading}</li>
          ))}
        </ul>
      </div>
      <div>
        <SectionTitle>Consistency</SectionTitle>
        <ul className="list-disc space-y-1 pl-4 text-xs">
          {Object.entries(pkg.consistency_checks).map(([name, ok]) => (
            <li key={name}>
              {name}: <span className={ok ? 'text-success' : 'text-destructive'}>{ok ? '✓' : '✗'}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function ReviewsPanel({ status }: { status?: WorkflowStatus }): React.ReactElement {
  const reviews = status?.reviews ?? [];
  if (reviews.length === 0) return <Empty label="S9" />;
  return (
    <div className="space-y-3">
      {reviews.map((r, idx) => (
        <div key={idx} className="rounded border border-border p-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              {r.reviewer} ({r.reviewer_role})
            </span>
            <Badge variant="outline">{r.verdict}</Badge>
          </div>
          {r.comments.length > 0 && (
            <ul className="mt-2 list-disc space-y-1 pl-4 text-xs">
              {r.comments.slice(0, 3).map((c, cIdx) => (
                <li key={cIdx}>
                  <Badge variant="outline">{c.severity}</Badge> {c.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

function SubmissionPanel({ status }: { status?: WorkflowStatus }): React.ReactElement {
  const s = status?.submission;
  if (!s) return <Empty label="S10" />;
  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-2 gap-1 text-xs">
        <dt className="text-muted-foreground">Channel</dt>
        <dd className="font-mono">{s.channel}</dd>
        <dt className="text-muted-foreground">Confirmation</dt>
        <dd className="font-mono">{s.confirmation_id ?? '—'}</dd>
        <dt className="text-muted-foreground">Checksum</dt>
        <dd className="font-mono">{s.package_checksum ?? '—'}</dd>
        <dt className="text-muted-foreground">Submitted</dt>
        <dd>{s.submitted_at}</dd>
      </dl>
      <div>
        <SectionTitle>Checklist</SectionTitle>
        <ul className="list-disc space-y-1 pl-4 text-xs">
          {Object.entries(s.checklist).map(([name, ok]) => (
            <li key={name}>
              {name}: <span className={ok ? 'text-success' : 'text-destructive'}>{ok ? '✓' : '✗'}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function RetrospectivePanel({ status }: { status?: WorkflowStatus }): React.ReactElement {
  const r = status?.retrospective;
  if (!r) return <Empty label="S11" />;
  return (
    <div className="space-y-3">
      <p>
        Outcome: <Badge variant="outline">{r.outcome}</Badge>
      </p>
      <div>
        <SectionTitle>Lessons ({r.lessons.length})</SectionTitle>
        <ul className="list-disc space-y-1 pl-4">
          {r.lessons.map((l, idx) => (
            <li key={idx}>
              <strong>{l.title}</strong>{' '}
              <span className="text-muted-foreground">[{l.category}]</span>
              <br />
              <span className="text-muted-foreground">{l.detail}</span>
            </li>
          ))}
        </ul>
      </div>
      {r.kb_updates.length > 0 && (
        <div>
          <SectionTitle>KB updates queued</SectionTitle>
          <ul className="list-disc space-y-1 pl-4 font-mono text-[11px]">
            {r.kb_updates.map((u, idx) => (
              <li key={idx}>{u}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
