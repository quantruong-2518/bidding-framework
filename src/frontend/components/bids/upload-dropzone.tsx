'use client';

import * as React from 'react';
import { File as FileIcon, Loader2, Trash2, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import type { Language } from '@/lib/api/types';

/**
 * S0.5 Wave 3 — multi-file dropzone for `POST /bids/parse`.
 *
 * Mirrors the gateway's mime allow-list + 50 MB per-file cap so a user
 * sees a precise validation error before the upload starts. The submit
 * button is disabled until at least one file is queued and `tenant_id`
 * is non-empty.
 */

export const ALLOWED_MIMES = new Set<string>([
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'text/markdown',
  'text/x-markdown',
  'text/plain',
]);

const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.xlsx', '.md', '.txt'] as const;
export const MAX_FILE_BYTES = 50 * 1024 * 1024;
export const MAX_FILES = 10;

interface UploadDropzoneProps {
  onSubmit: (
    files: File[],
    tenantId: string,
    language: Language,
  ) => Promise<void> | void;
  defaultTenantId?: string;
  defaultLanguage?: Language;
  /** When true, the form disables itself + shows a spinner on the submit. */
  pending?: boolean;
}

export function UploadDropzone({
  onSubmit,
  defaultTenantId = '',
  defaultLanguage = 'en',
  pending = false,
}: UploadDropzoneProps): React.ReactElement {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [files, setFiles] = React.useState<File[]>([]);
  const [tenantId, setTenantId] = React.useState<string>(defaultTenantId);
  const [language, setLanguage] = React.useState<Language>(defaultLanguage);
  const [error, setError] = React.useState<string | null>(null);
  const [dragActive, setDragActive] = React.useState(false);

  const acceptFiles = React.useCallback(
    (incoming: FileList | File[] | null) => {
      if (!incoming) return;
      setError(null);
      const queue = Array.from(incoming);
      const accepted: File[] = [];
      for (const file of queue) {
        if (!isAllowedFile(file)) {
          setError(
            `"${file.name}": only PDF/DOCX/XLSX/MD/TXT are accepted.`,
          );
          continue;
        }
        if (file.size > MAX_FILE_BYTES) {
          setError(
            `"${file.name}" is ${formatBytes(file.size)} — files must be ≤ ${formatBytes(MAX_FILE_BYTES)}.`,
          );
          continue;
        }
        accepted.push(file);
      }
      if (accepted.length === 0) return;
      setFiles((prev) => {
        const merged = [...prev, ...accepted].slice(0, MAX_FILES);
        if (merged.length === MAX_FILES && prev.length + accepted.length > MAX_FILES) {
          setError(`At most ${MAX_FILES} files per upload.`);
        }
        return merged;
      });
    },
    [],
  );

  const onPick = (e: React.ChangeEvent<HTMLInputElement>): void => {
    acceptFiles(e.target.files);
    e.target.value = '';
  };

  const onDrop = (e: React.DragEvent<HTMLDivElement>): void => {
    e.preventDefault();
    setDragActive(false);
    acceptFiles(e.dataTransfer.files);
  };

  const removeFile = (idx: number): void => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  const submitDisabled =
    pending || files.length === 0 || tenantId.trim().length === 0;

  const handleSubmit = async (
    e: React.FormEvent<HTMLFormElement>,
  ): Promise<void> => {
    e.preventDefault();
    if (submitDisabled) return;
    await onSubmit(files, tenantId.trim(), language);
  };

  return (
    <form className="space-y-4" onSubmit={(e) => void handleSubmit(e)}>
      <div
        onDrop={onDrop}
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        className={`flex flex-col items-center gap-3 rounded-md border-2 border-dashed p-6 text-center transition-colors ${
          dragActive
            ? 'border-primary bg-primary/5'
            : 'border-muted-foreground/30 bg-muted/30'
        }`}
        data-testid="upload-dropzone"
      >
        <Upload className="h-6 w-6 text-muted-foreground" aria-hidden />
        <div className="text-sm">
          Drop up to <strong>{MAX_FILES}</strong> files
          <strong> (PDF / DOCX / XLSX / MD / TXT, ≤ {formatBytes(MAX_FILE_BYTES)} each)</strong> here, or
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={() => inputRef.current?.click()}
          disabled={pending}
        >
          Choose files
        </Button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ALLOWED_EXTENSIONS.join(',')}
          className="hidden"
          onChange={onPick}
          data-testid="upload-input"
        />
        <p className="text-xs text-muted-foreground">
          Multiple RFP / appendix / Q&A files supported. They&apos;ll be
          parsed into atoms you can review before confirming.
        </p>
      </div>

      {files.length > 0 && (
        <ul className="divide-y divide-border rounded-md border border-border">
          {files.map((file, idx) => (
            <li
              key={`${file.name}-${idx}`}
              className="flex items-center gap-3 px-3 py-2 text-sm"
              data-testid="upload-file-row"
            >
              <FileIcon className="h-4 w-4 text-muted-foreground" />
              <span className="flex-1 truncate">{file.name}</span>
              <span className="text-xs font-mono text-muted-foreground">
                {formatBytes(file.size)}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => removeFile(idx)}
                disabled={pending}
                aria-label={`Remove ${file.name}`}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="upload-tenant">Tenant ID</Label>
          <Input
            id="upload-tenant"
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            placeholder="customer-a"
            required
            disabled={pending}
            data-testid="upload-tenant"
          />
        </div>
        <div>
          <Label htmlFor="upload-language">Language hint</Label>
          <Select
            id="upload-language"
            value={language}
            onChange={(e) => setLanguage(e.target.value as Language)}
            disabled={pending}
            data-testid="upload-language"
          >
            <option value="en">English</option>
            <option value="vi">Tiếng Việt</option>
          </Select>
        </div>
      </div>

      {error && (
        <div
          className="rounded-md border border-destructive/60 bg-destructive/10 p-3 text-sm text-destructive"
          data-testid="upload-error"
        >
          {error}
        </div>
      )}

      <div className="flex items-center gap-2">
        <Button type="submit" disabled={submitDisabled} data-testid="upload-submit">
          {pending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Uploading…
            </>
          ) : (
            <>
              <Upload className="h-4 w-4" />
              Start parse ({files.length} {files.length === 1 ? 'file' : 'files'})
            </>
          )}
        </Button>
        <span className="text-xs text-muted-foreground">
          The parse runs async — you&apos;ll be redirected to the preview
          page to monitor progress.
        </span>
      </div>
    </form>
  );
}

function isAllowedFile(file: File): boolean {
  if (file.type && ALLOWED_MIMES.has(file.type)) return true;
  // Some browsers (Firefox on .md) leave file.type empty — fall back to
  // extension check to avoid rejecting valid files.
  const lower = file.name.toLowerCase();
  return ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  if (bytes >= 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${bytes} B`;
}
