'use client';

import * as React from 'react';
import { useForm, useFieldArray, Controller } from 'react-hook-form';
import { Check, Loader2, MessageSquareWarning, Plus, Trash2, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select } from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { useSendReviewSignal } from '@/lib/hooks/use-bids';
import { useAuthStore } from '@/lib/auth/store';
import type { ReviewRecord, ReviewSignalInput } from '@/lib/api/types';

interface ReviewGatePanelProps {
  bidId: string;
  round: number;
  reviews?: ReviewRecord[];
}

const ROLES = [
  'bid_manager',
  'ba',
  'sa',
  'qc',
  'domain_expert',
  'solution_lead',
] as const;

const SEVERITIES = ['NIT', 'MINOR', 'MAJOR', 'BLOCKER'] as const;
const TARGETS = ['', 'S2', 'S5', 'S6', 'S8'] as const;

type FormValues = {
  verdict: 'APPROVED' | 'REJECTED' | 'CHANGES_REQUESTED';
  reviewerRole: (typeof ROLES)[number];
  notes: string;
  comments: Array<{
    section: string;
    severity: (typeof SEVERITIES)[number];
    message: string;
    targetState: '' | 'S2' | 'S5' | 'S6' | 'S8';
  }>;
};

export function ReviewGatePanel({
  bidId,
  round,
  reviews,
}: ReviewGatePanelProps): React.ReactElement {
  const reviewer = useAuthStore((s) => s.user?.username ?? 'anonymous');
  const mutation = useSendReviewSignal(bidId);

  const { register, handleSubmit, control, watch, formState: { errors }, reset } =
    useForm<FormValues>({
      defaultValues: {
        verdict: 'APPROVED',
        reviewerRole: 'bid_manager',
        notes: '',
        comments: [],
      },
    });
  const { fields, append, remove } = useFieldArray({ control, name: 'comments' });
  const verdict = watch('verdict');

  const submit = handleSubmit(async (values) => {
    const payload: ReviewSignalInput = {
      verdict: values.verdict,
      reviewer,
      reviewerRole: values.reviewerRole,
      notes: values.notes || undefined,
      comments: values.comments.map((c) => ({
        section: c.section,
        severity: c.severity,
        message: c.message,
        targetState: c.targetState === '' ? undefined : c.targetState,
      })),
    };
    await mutation.mutateAsync(payload);
    reset({ ...values, comments: [], notes: '' });
  });

  const lastPreHuman = reviews?.find((r) => r.reviewer === 'phase-2.4-pre-human');

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle>Review gate — Round {round + 1}</CardTitle>
          <Badge variant="warning">
            <MessageSquareWarning className="mr-1 h-3.5 w-3.5" />
            S9
          </Badge>
        </div>
        {lastPreHuman && (
          <p className="text-xs text-muted-foreground">
            Pre-human verdict: <strong>{lastPreHuman.verdict}</strong>
          </p>
        )}
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={(e) => void submit(e)}>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="review-verdict">Verdict</Label>
              <Select id="review-verdict" {...register('verdict')}>
                <option value="APPROVED">Approve</option>
                <option value="CHANGES_REQUESTED">Request changes</option>
                <option value="REJECTED">Reject (terminal)</option>
              </Select>
            </div>
            <div>
              <Label htmlFor="review-role">Reviewer role</Label>
              <Select id="review-role" {...register('reviewerRole')}>
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          <div>
            <Label htmlFor="review-notes">Notes</Label>
            <Textarea
              id="review-notes"
              rows={2}
              placeholder="Optional narrative for the audit trail."
              {...register('notes', { maxLength: 2000 })}
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Comments {verdict === 'CHANGES_REQUESTED' && <span className="text-destructive">*</span>}</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() =>
                  append({
                    section: '',
                    severity: 'MINOR',
                    message: '',
                    targetState: '',
                  })
                }
              >
                <Plus className="h-3.5 w-3.5" />
                Add
              </Button>
            </div>
            {fields.length === 0 && verdict === 'CHANGES_REQUESTED' && (
              <p className="text-xs text-destructive">
                Request changes requires at least one comment with a loop-back target.
              </p>
            )}
            <ul className="space-y-3">
              {fields.map((field, index) => (
                <li
                  key={field.id}
                  className="rounded-md border border-border p-3 space-y-2"
                >
                  <div className="grid grid-cols-3 gap-2">
                    <Input
                      placeholder="Section (e.g. Solution)"
                      {...register(`comments.${index}.section` as const, {
                        required: true,
                      })}
                    />
                    <Controller
                      control={control}
                      name={`comments.${index}.severity` as const}
                      render={({ field: f }) => (
                        <Select {...f}>
                          {SEVERITIES.map((s) => (
                            <option key={s} value={s}>
                              {s}
                            </option>
                          ))}
                        </Select>
                      )}
                    />
                    <Controller
                      control={control}
                      name={`comments.${index}.targetState` as const}
                      render={({ field: f }) => (
                        <Select {...f}>
                          {TARGETS.map((t) => (
                            <option key={t || 'none'} value={t}>
                              {t === '' ? 'no target' : `Loop → ${t}`}
                            </option>
                          ))}
                        </Select>
                      )}
                    />
                  </div>
                  <Textarea
                    rows={2}
                    placeholder="Finding / required change"
                    {...register(`comments.${index}.message` as const, {
                      required: true,
                    })}
                  />
                  <div className="flex justify-end">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => remove(index)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <div className="flex items-center gap-2">
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : verdict === 'APPROVED' ? (
                <Check className="h-4 w-4" />
              ) : (
                <XCircle className="h-4 w-4" />
              )}
              Submit review
            </Button>
            {mutation.isSuccess && (
              <span className="text-xs text-success">Submitted. Awaiting workflow.</span>
            )}
            {mutation.isError && (
              <span className="text-xs text-destructive">
                {(mutation.error as Error).message}
              </span>
            )}
            {errors.comments && (
              <span className="text-xs text-destructive">
                Some comments are incomplete.
              </span>
            )}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
