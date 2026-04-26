'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { useMutation } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Textarea } from '@/components/ui/textarea';
import { AtomTablePreview } from '@/components/bids/atom-table-preview';
import { AtomEditModal } from '@/components/bids/atom-edit-modal';
import { ConflictList } from '@/components/bids/conflict-list';
import { WorkflowProposalCard } from '@/components/bids/workflow-proposal-card';
import { abandon, confirm } from '@/lib/api/parse-sessions';
import type {
  AtomEdit,
  AtomPreviewItem,
  BidProfileLevel,
  ConfirmRequest,
  PreviewResponse,
} from '@/lib/api/types';

interface BidPreviewPanelProps {
  preview: PreviewResponse;
}

/**
 * S0.5 Wave 3 — top-level preview composition.
 *
 * Orchestrates the §3.6 PreviewResponse render: editable BidCard form,
 * collapsible context preview (anchor + summary + open questions), atom
 * table with edit/reject affordances, conflict list, suggested workflow
 * card, and the confirm/abandon footer. On confirm the panel routes to
 * `/bids/[bid_id]`; on abandon it returns to `/bids`.
 */
export function BidPreviewPanel({
  preview,
}: BidPreviewPanelProps): React.ReactElement {
  const router = useRouter();

  const suggested = preview.suggested_bid_card;
  const [name, setName] = React.useState<string>(suggested?.name ?? '');
  const [clientName, setClientName] = React.useState<string>(
    suggested?.client_name ?? '',
  );
  const [industry, setIndustry] = React.useState<string>(
    suggested?.industry ?? '',
  );
  const [region, setRegion] = React.useState<string>(suggested?.region ?? '');
  const [deadline, setDeadline] = React.useState<string>(
    suggested?.deadline ?? '',
  );
  const [profileOverride, setProfileOverride] = React.useState<
    BidProfileLevel | ''
  >('');

  const [edits, setEdits] = React.useState<Map<string, AtomEdit>>(new Map());
  const [rejected, setRejected] = React.useState<Set<string>>(new Set());
  const [editing, setEditing] = React.useState<AtomPreviewItem | null>(null);

  const [submitError, setSubmitError] = React.useState<string | null>(null);

  const confirmMut = useMutation({
    mutationFn: (req: ConfirmRequest) => confirm(preview.session_id, req),
    onSuccess: (res) => router.push(`/bids/${res.bid_id}`),
    onError: (err: unknown) =>
      setSubmitError(err instanceof Error ? err.message : 'Confirm failed'),
  });

  const abandonMut = useMutation({
    mutationFn: () => abandon(preview.session_id),
    onSuccess: () => router.push('/bids'),
    onError: (err: unknown) =>
      setSubmitError(err instanceof Error ? err.message : 'Abandon failed'),
  });

  const handleConfirm = (): void => {
    setSubmitError(null);
    const req: ConfirmRequest = {};
    if (suggested) {
      if (name !== suggested.name) req.name = name.trim() || undefined;
      if (clientName !== suggested.client_name)
        req.client_name = clientName.trim() || undefined;
      if (industry !== suggested.industry)
        req.industry = industry.trim() || undefined;
      if (region !== suggested.region) req.region = region.trim() || undefined;
      if (deadline !== suggested.deadline)
        req.deadline = deadline.trim() || undefined;
    }
    if (profileOverride) req.profile_override = profileOverride;
    if (edits.size > 0) req.atom_edits = Array.from(edits.values());
    if (rejected.size > 0) req.atom_rejects = Array.from(rejected);
    confirmMut.mutate(req);
  };

  const onSaveEdit = (edit: AtomEdit): void => {
    setEdits((prev) => {
      const next = new Map(prev);
      next.set(edit.id, edit);
      return next;
    });
  };

  const onToggleReject = (atomId: string): void => {
    setRejected((prev) => {
      const next = new Set(prev);
      if (next.has(atomId)) next.delete(atomId);
      else next.add(atomId);
      return next;
    });
  };

  return (
    <div className="space-y-6" data-testid="bid-preview-panel">
      {suggested ? (
        <Card>
          <CardHeader>
            <CardTitle>Suggested bid card</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="bid-name">Bid name</Label>
                <Input
                  id="bid-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  data-testid="bid-name"
                />
              </div>
              <div>
                <Label htmlFor="bid-client">Client</Label>
                <Input
                  id="bid-client"
                  value={clientName}
                  onChange={(e) => setClientName(e.target.value)}
                  data-testid="bid-client"
                />
              </div>
              <div>
                <Label htmlFor="bid-industry">Industry</Label>
                <Input
                  id="bid-industry"
                  value={industry}
                  onChange={(e) => setIndustry(e.target.value)}
                  data-testid="bid-industry"
                />
              </div>
              <div>
                <Label htmlFor="bid-region">Region</Label>
                <Input
                  id="bid-region"
                  value={region}
                  onChange={(e) => setRegion(e.target.value)}
                  data-testid="bid-region"
                />
              </div>
              <div>
                <Label htmlFor="bid-deadline">Deadline</Label>
                <Input
                  id="bid-deadline"
                  value={deadline}
                  onChange={(e) => setDeadline(e.target.value)}
                  data-testid="bid-deadline"
                />
              </div>
              <div>
                <Label htmlFor="bid-profile">Profile override</Label>
                <Select
                  id="bid-profile"
                  value={profileOverride}
                  onChange={(e) =>
                    setProfileOverride(e.target.value as BidProfileLevel | '')
                  }
                  data-testid="bid-profile"
                >
                  <option value="">
                    Use suggested ({suggested.estimated_profile})
                  </option>
                  <option value="S">S</option>
                  <option value="M">M</option>
                  <option value="L">L</option>
                  <option value="XL">XL</option>
                </Select>
              </div>
            </div>
            {suggested.technology_keywords.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {suggested.technology_keywords.map((kw) => (
                  <Badge key={kw} variant="outline">
                    {kw}
                  </Badge>
                ))}
              </div>
            )}
            <Textarea
              rows={3}
              value={suggested.scope_summary}
              readOnly
              data-testid="bid-scope-summary"
            />
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            No suggested bid card available — parser may have failed.
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Project context</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <details className="rounded-md border border-border p-3" open>
            <summary className="cursor-pointer font-semibold">
              Anchor (frame for every agent)
            </summary>
            <pre
              className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap font-mono text-xs"
              data-testid="context-anchor"
            >
              {preview.context_preview.anchor_md}
            </pre>
          </details>
          <details className="rounded-md border border-border p-3">
            <summary className="cursor-pointer font-semibold">
              Executive summary
            </summary>
            <pre
              className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap font-mono text-xs"
              data-testid="context-summary"
            >
              {preview.context_preview.summary_md}
            </pre>
          </details>
          {preview.context_preview.open_questions.length > 0 && (
            <details className="rounded-md border border-border p-3" open>
              <summary className="cursor-pointer font-semibold">
                Open questions ({preview.context_preview.open_questions.length})
              </summary>
              <ul
                className="mt-2 list-disc pl-6 text-sm"
                data-testid="context-open-questions"
              >
                {preview.context_preview.open_questions.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ul>
            </details>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Atoms</CardTitle>
            <div className="flex gap-2 text-xs text-muted-foreground">
              <span data-testid="atoms-total">
                Total: {preview.atoms_preview.total}
              </span>
              <span>·</span>
              <span data-testid="atoms-low-conf">
                Low confidence: {preview.atoms_preview.low_confidence_count}
              </span>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-1.5 text-xs">
            {Object.entries(preview.atoms_preview.by_type).map(([t, n]) => (
              <Badge key={t} variant="outline">
                {t}: {n}
              </Badge>
            ))}
            <Separator orientation="vertical" className="h-4" />
            {Object.entries(preview.atoms_preview.by_priority).map(([p, n]) => (
              <Badge key={p} variant="outline">
                {p}: {n}
              </Badge>
            ))}
          </div>
          <AtomTablePreview
            atoms={preview.atoms_preview.sample}
            onEdit={(a) => setEditing(a)}
            rejectedIds={rejected}
            onToggleReject={onToggleReject}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Conflicts</CardTitle>
        </CardHeader>
        <CardContent>
          <ConflictList conflicts={preview.conflicts_detected} />
        </CardContent>
      </Card>

      <WorkflowProposalCard workflow={preview.suggested_workflow} />

      {submitError && (
        <div
          className="rounded-md border border-destructive/60 bg-destructive/10 p-3 text-sm text-destructive"
          data-testid="bid-preview-error"
        >
          {submitError}
        </div>
      )}

      <div className="flex items-center justify-end gap-2 border-t border-border pt-4">
        <Button
          variant="ghost"
          onClick={() => abandonMut.mutate()}
          disabled={confirmMut.isPending || abandonMut.isPending}
          data-testid="abandon-button"
        >
          {abandonMut.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : null}
          Abandon
        </Button>
        <Button
          onClick={handleConfirm}
          disabled={confirmMut.isPending || abandonMut.isPending}
          data-testid="confirm-button"
        >
          {confirmMut.isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Starting workflow…
            </>
          ) : (
            'Confirm & start workflow'
          )}
        </Button>
      </div>

      <AtomEditModal
        atom={editing}
        onClose={() => setEditing(null)}
        onSave={onSaveEdit}
      />
    </div>
  );
}
