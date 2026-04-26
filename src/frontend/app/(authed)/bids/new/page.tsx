'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { useMutation } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { UploadDropzone } from '@/components/bids/upload-dropzone';
import { uploadFiles } from '@/lib/api/parse-sessions';
import type { Language } from '@/lib/api/types';

/**
 * S0.5 — unified bid creation entry. User uploads one or more bid documents,
 * presses Submit, and the gateway runs the parse-confirm pipeline:
 *
 *   POST /bids/parse → preview (with live atom counts) → confirm → workflow.
 *
 * The legacy manual form has been retired in favour of this upload-first flow
 * so every bid passes through the parser, atom extraction, and the human
 * review gate before a bid record exists.
 */
export default function NewBidPage(): React.ReactElement {
  const router = useRouter();
  const [error, setError] = React.useState<string | null>(null);

  const uploadMut = useMutation({
    mutationFn: (args: { files: File[]; tenantId: string; language: Language }) =>
      uploadFiles(args.files, args.tenantId, args.language),
    onSuccess: (res) => {
      router.push(`/bids/new/preview/${res.session_id}`);
    },
    onError: (err: unknown) =>
      setError(err instanceof Error ? err.message : 'Upload failed'),
  });

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">New bid</h1>
        <p className="text-sm text-muted-foreground">
          Upload the RFP plus any appendices, Q&amp;A, or reference documents.
          The parser extracts requirement atoms incrementally as each file
          finishes — you review the preview, edit anything wrong, then confirm
          to register the bid and start the workflow.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Upload documents</CardTitle>
        </CardHeader>
        <CardContent>
          <UploadDropzone
            pending={uploadMut.isPending}
            onSubmit={async (files, tenantId, language) => {
              setError(null);
              uploadMut.mutate({ files, tenantId, language });
            }}
          />
          {error && (
            <div
              className="mt-3 rounded-md border border-destructive/60 bg-destructive/10 p-3 text-sm text-destructive"
              data-testid="upload-page-error"
            >
              {error}
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
