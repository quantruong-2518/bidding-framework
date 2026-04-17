'use client';

import * as React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { CreateBidForm } from './create-bid-form';
import { RfpUpload } from './rfp-upload';
import type { BidCardSuggestion } from '@/lib/api/parsers';

type Profile = 'S' | 'M' | 'L' | 'XL';

interface FormSeed {
  clientName: string;
  industry: string;
  region: string;
  scopeSummary: string;
  technologyKeywords: string;
  estimatedProfile: Profile | '';
}

function asProfile(hint: BidCardSuggestion['estimated_profile_hint']): Profile | '' {
  return hint ?? '';
}

function mapSuggestion(s: BidCardSuggestion): FormSeed {
  const scope = s.scope_summary.trim();
  const bulletRequirements = s.requirement_candidates
    .map((r) => `- ${r.trim()}`)
    .join('\n');
  // Surface both the scope paragraph and the detected requirement list inside
  // the scope textarea so the bid manager has everything in one place. The
  // downstream workflow re-parses requirements from `scope_summary`, so this
  // inline list is honoured end-to-end.
  const scopeSummary = bulletRequirements
    ? `${scope}\n\nRequirement candidates:\n${bulletRequirements}`
    : scope;
  return {
    clientName: s.client_name,
    industry: s.industry,
    region: s.region,
    scopeSummary,
    technologyKeywords: s.technology_keywords.join(', '),
    estimatedProfile: asProfile(s.estimated_profile_hint),
  };
}

export function NewBidShell(): React.ReactElement {
  const [seed, setSeed] = React.useState<FormSeed | undefined>(undefined);
  const [resetToken, setResetToken] = React.useState(0);

  const onSuggestion = React.useCallback((suggestion: BidCardSuggestion) => {
    setSeed(mapSuggestion(suggestion));
    setResetToken((n) => n + 1);
  }, []);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Upload RFP (optional)</CardTitle>
          <CardDescription>
            Drop a PDF/DOCX and we&apos;ll pre-fill the form below with a
            heuristic pass over the document. Review before starting the
            workflow.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <RfpUpload onSuggestion={onSuggestion} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Bid details</CardTitle>
          <CardDescription>
            Required fields match the NestJS POST /bids contract.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <CreateBidForm initialValues={seed} resetToken={resetToken} />
        </CardContent>
      </Card>
    </div>
  );
}
