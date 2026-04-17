'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { useForm, Controller } from 'react-hook-form';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select } from '@/components/ui/select';
import { CreateBidSchema, type CreateBidInput } from '@/lib/api/types';
import { useCreateBid } from '@/lib/hooks/use-bids';

interface FormValues {
  clientName: string;
  industry: string;
  region: string;
  deadline: string;
  scopeSummary: string;
  technologyKeywords: string;
  estimatedProfile: 'S' | 'M' | 'L' | 'XL' | '';
}

const DEFAULTS: FormValues = {
  clientName: '',
  industry: '',
  region: '',
  deadline: '',
  scopeSummary: '',
  technologyKeywords: '',
  estimatedProfile: '',
};

function parseKeywords(raw: string): string[] {
  return raw
    .split(/[,\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function CreateBidForm(): React.ReactElement {
  const router = useRouter();
  const mutation = useCreateBid();
  const {
    control,
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<FormValues>({
    defaultValues: DEFAULTS,
  });

  const onSubmit = handleSubmit(async (values) => {
    const keywords = parseKeywords(values.technologyKeywords);
    const payload: CreateBidInput = {
      clientName: values.clientName.trim(),
      industry: values.industry.trim(),
      region: values.region.trim(),
      deadline: values.deadline,
      scopeSummary: values.scopeSummary.trim(),
      technologyKeywords: keywords,
      estimatedProfile:
        values.estimatedProfile === '' ? undefined : values.estimatedProfile,
    };

    const parsed = CreateBidSchema.safeParse(payload);
    if (!parsed.success) {
      for (const issue of parsed.error.issues) {
        const field = issue.path[0] as keyof FormValues;
        setError(field, { message: issue.message });
      }
      return;
    }

    try {
      const created = await mutation.mutateAsync(parsed.data);
      router.push(`/bids/${created.id}`);
    } catch (err) {
      setError('root', {
        message: err instanceof Error ? err.message : 'Failed to create bid',
      });
    }
  });

  return (
    <form onSubmit={onSubmit} className="grid grid-cols-1 gap-5 md:grid-cols-2">
      <div className="md:col-span-2">
        <Label htmlFor="clientName">Client name</Label>
        <Input id="clientName" {...register('clientName')} autoComplete="off" />
        {errors.clientName && (
          <p className="mt-1 text-xs text-destructive">{errors.clientName.message}</p>
        )}
      </div>

      <div>
        <Label htmlFor="industry">Industry</Label>
        <Input id="industry" {...register('industry')} />
        {errors.industry && (
          <p className="mt-1 text-xs text-destructive">{errors.industry.message}</p>
        )}
      </div>

      <div>
        <Label htmlFor="region">Region</Label>
        <Input id="region" {...register('region')} placeholder="APAC / EMEA / NA" />
        {errors.region && (
          <p className="mt-1 text-xs text-destructive">{errors.region.message}</p>
        )}
      </div>

      <div>
        <Label htmlFor="deadline">Deadline</Label>
        <Input id="deadline" type="datetime-local" {...register('deadline')} />
        {errors.deadline && (
          <p className="mt-1 text-xs text-destructive">{errors.deadline.message}</p>
        )}
      </div>

      <div>
        <Label htmlFor="estimatedProfile">Estimated profile</Label>
        <Controller
          control={control}
          name="estimatedProfile"
          render={({ field }) => (
            <Select id="estimatedProfile" {...field}>
              <option value="">Let AI suggest</option>
              <option value="S">S — &lt; 100 MD</option>
              <option value="M">M — 100-500 MD</option>
              <option value="L">L — 500-2000 MD</option>
              <option value="XL">XL — &gt; 2000 MD</option>
            </Select>
          )}
        />
      </div>

      <div className="md:col-span-2">
        <Label htmlFor="scopeSummary">Scope summary</Label>
        <Textarea
          id="scopeSummary"
          rows={4}
          placeholder="One or two paragraphs describing the opportunity."
          {...register('scopeSummary')}
        />
        {errors.scopeSummary && (
          <p className="mt-1 text-xs text-destructive">{errors.scopeSummary.message}</p>
        )}
      </div>

      <div className="md:col-span-2">
        <Label htmlFor="technologyKeywords">Technology keywords</Label>
        <Input
          id="technologyKeywords"
          placeholder="React, Node.js, PostgreSQL, Kafka"
          {...register('technologyKeywords')}
        />
        <p className="mt-1 text-xs text-muted-foreground">
          Comma- or newline-separated.
        </p>
        {errors.technologyKeywords && (
          <p className="mt-1 text-xs text-destructive">
            {errors.technologyKeywords.message as string}
          </p>
        )}
      </div>

      {errors.root?.message && (
        <div className="md:col-span-2 rounded-md border border-destructive/60 bg-destructive/10 p-3 text-sm text-destructive">
          {errors.root.message}
        </div>
      )}

      <div className="md:col-span-2 flex items-center justify-end gap-2">
        <Button type="button" variant="outline" onClick={() => router.back()}>
          Cancel
        </Button>
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Creating…
            </>
          ) : (
            'Create bid'
          )}
        </Button>
      </div>
    </form>
  );
}
