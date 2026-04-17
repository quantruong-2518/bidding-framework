'use client';

import * as React from 'react';
import { useForm } from 'react-hook-form';
import { Check, X, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { Select } from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { useSendTriageSignal } from '@/lib/hooks/use-bids';
import { useAuthStore } from '@/lib/auth/store';
import type { Triage } from '@/lib/api/types';

interface TriageReviewPanelProps {
  bidId: string;
  triage?: Triage;
}

interface FormValues {
  notes: string;
  bidProfileOverride: '' | 'S' | 'M' | 'L' | 'XL';
}

export function TriageReviewPanel({ bidId, triage }: TriageReviewPanelProps): React.ReactElement {
  const reviewer = useAuthStore((s) => s.user?.username ?? 'anonymous');
  const mutation = useSendTriageSignal(bidId);
  const { register, handleSubmit, formState: { errors } } = useForm<FormValues>({
    defaultValues: { notes: '', bidProfileOverride: '' },
  });
  const [decision, setDecision] = React.useState<boolean | null>(null);

  const submit = async (approved: boolean, values: FormValues): Promise<void> => {
    setDecision(approved);
    try {
      await mutation.mutateAsync({
        approved,
        reviewer,
        notes: values.notes || undefined,
        bidProfileOverride: values.bidProfileOverride || undefined,
      });
    } finally {
      setDecision(null);
    }
  };

  const onApprove = handleSubmit((v) => submit(true, v));
  const onReject = handleSubmit((v) => submit(false, v));

  const recommendation = triage?.recommend ?? 'bid';
  const confidencePct =
    typeof triage?.confidence === 'number' ? Math.round(triage.confidence * 100) : null;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle>Triage review</CardTitle>
          <Badge variant={recommendation === 'bid' ? 'success' : 'destructive'}>
            Recommend: {recommendation}
          </Badge>
        </div>
        {confidencePct != null && (
          <p className="text-xs text-muted-foreground">
            Model confidence: <strong>{confidencePct}%</strong>
          </p>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {triage?.scores && triage.scores.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase text-muted-foreground">Scores</p>
            <ul className="divide-y divide-border rounded-md border border-border">
              {triage.scores.map((score, i) => (
                <li key={`${score.label}-${i}`} className="flex items-center justify-between px-3 py-2 text-sm">
                  <span>{score.label ?? `Criterion ${i + 1}`}</span>
                  <span className="font-mono">{score.score ?? '—'}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {triage?.rationale && (
          <p className="rounded-md bg-muted/40 p-3 text-sm text-muted-foreground">
            {triage.rationale}
          </p>
        )}

        <form className="space-y-3">
          <div>
            <Label htmlFor="triage-notes">Reviewer notes</Label>
            <Textarea
              id="triage-notes"
              rows={3}
              placeholder="Optional notes for the workflow history."
              {...register('notes', { maxLength: 2000 })}
            />
            {errors.notes && (
              <p className="mt-1 text-xs text-destructive">Notes are too long.</p>
            )}
          </div>
          <div>
            <Label htmlFor="triage-profile">Override profile (optional)</Label>
            <Select id="triage-profile" {...register('bidProfileOverride')}>
              <option value="">Keep AI suggestion</option>
              <option value="S">S</option>
              <option value="M">M</option>
              <option value="L">L</option>
              <option value="XL">XL</option>
            </Select>
          </div>
          <div className="flex items-center gap-2 pt-2">
            <Button
              type="button"
              variant="success"
              onClick={() => void onApprove()}
              disabled={mutation.isPending}
            >
              {mutation.isPending && decision === true ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Check className="h-4 w-4" />
              )}
              Approve &amp; continue
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={() => void onReject()}
              disabled={mutation.isPending}
            >
              {mutation.isPending && decision === false ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <X className="h-4 w-4" />
              )}
              Mark no-bid
            </Button>
          </div>
          {mutation.isError && (
            <p className="text-xs text-destructive">
              {(mutation.error as Error).message}
            </p>
          )}
          {mutation.isSuccess && (
            <p className="text-xs text-success">Signal sent to workflow.</p>
          )}
        </form>
      </CardContent>
    </Card>
  );
}
