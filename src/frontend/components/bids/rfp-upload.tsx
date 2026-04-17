'use client';

import * as React from 'react';
import { Loader2, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { parseRfp, type BidCardSuggestion } from '@/lib/api/parsers';

interface Props {
  onSuggestion: (suggestion: BidCardSuggestion) => void;
}

const MAX_MB = 20;
const ACCEPT = '.pdf,.docx';

export function RfpUpload({ onSuggestion }: Props): React.ReactElement {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [summary, setSummary] = React.useState<string | null>(null);

  const handleFiles = React.useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return;
      const file = files[0];
      if (!file) return;
      setError(null);
      setSummary(null);

      const lower = file.name.toLowerCase();
      if (!lower.endsWith('.pdf') && !lower.endsWith('.docx')) {
        setError('Only .pdf or .docx files are supported.');
        return;
      }
      if (file.size > MAX_MB * 1024 * 1024) {
        setError(`File is larger than ${MAX_MB} MB.`);
        return;
      }

      setPending(true);
      try {
        const result = await parseRfp(file);
        onSuggestion(result.suggested_bid_card);
        const reqCount = result.suggested_bid_card.requirement_candidates.length;
        const conf = result.suggested_bid_card.confidence.toFixed(2);
        setSummary(
          `Parsed ${file.name} → ${reqCount} requirement candidate(s) (confidence ${conf}). Review and edit below.`,
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to parse file.');
      } finally {
        setPending(false);
      }
    },
    [onSuggestion],
  );

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    void handleFiles(e.dataTransfer.files);
  };

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    void handleFiles(e.target.files);
    e.target.value = '';
  };

  return (
    <div className="space-y-3">
      <div
        onDrop={onDrop}
        onDragOver={(e) => e.preventDefault()}
        className="flex flex-col items-center gap-3 rounded-md border-2 border-dashed border-muted-foreground/30 bg-muted/30 p-6 text-center"
      >
        <Upload className="h-6 w-6 text-muted-foreground" aria-hidden />
        <div className="text-sm">
          Drop an RFP (<strong>.pdf</strong> or <strong>.docx</strong>, ≤ {MAX_MB} MB) here, or
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={() => inputRef.current?.click()}
          disabled={pending}
        >
          {pending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Parsing…
            </>
          ) : (
            'Choose file'
          )}
        </Button>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={onPick}
        />
        <p className="text-xs text-muted-foreground">
          Parsing is heuristic — always review the pre-filled form before
          starting the workflow.
        </p>
      </div>
      {summary && !error && (
        <div className="rounded-md border border-emerald-500/50 bg-emerald-500/10 p-3 text-sm text-emerald-700 dark:text-emerald-400">
          {summary}
        </div>
      )}
      {error && (
        <div className="rounded-md border border-destructive/60 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}
    </div>
  );
}
