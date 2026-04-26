'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { useMutation } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { UploadDropzone } from '@/components/bids/upload-dropzone';
import { uploadFiles } from '@/lib/api/parse-sessions';
import type { Language } from '@/lib/api/types';

/**
 * S0.5 Wave 3 — multi-file upload page.
 *
 * Posts to `POST /bids/parse`, then routes to the preview page where the
 * polling hook drives the parse status. The "manual create" flow at
 * `/bids/new` stays available as a sibling (Decision 11 — legacy preserved).
 */
export default function UploadParsePage(): React.ReactElement {
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
        <h1 className="text-2xl font-semibold tracking-tight">
          New bid (parse)
        </h1>
        <p className="text-sm text-muted-foreground">
          Upload one or more bid documents (RFP / appendix / Q&amp;A /
          reference). The parser extracts atoms, drafts an anchor context,
          and proposes a workflow. You review the preview, edit if needed,
          and confirm to register the bid.
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
