'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import type { AtomEdit, AtomPreviewItem } from '@/lib/api/types';

interface AtomEditModalProps {
  /** When non-null, the dialog is open and edits target this atom. */
  atom: AtomPreviewItem | null;
  onClose: () => void;
  onSave: (edit: AtomEdit) => void;
}

/**
 * S0.5 Wave 3 — inline atom editor.
 *
 * Edits map onto the §3.7 `ConfirmRequest.atom_edits[]` patch payload. We
 * surface the four fields a reviewer realistically tweaks before confirm
 * (priority / category / tags / body_md). Type stays read-only here — it
 * almost always implies pipeline routing changes a reviewer should not flip
 * casually; if needed, that becomes a separate ticket.
 */
export function AtomEditModal({
  atom,
  onClose,
  onSave,
}: AtomEditModalProps): React.ReactElement | null {
  const [priority, setPriority] = React.useState<AtomPreviewItem['priority']>(
    atom?.priority ?? 'MUST',
  );
  const [category, setCategory] = React.useState<string>(atom?.category ?? '');
  const [tagsInput, setTagsInput] = React.useState<string>('');
  const [bodyMd, setBodyMd] = React.useState<string>(atom?.body_md ?? '');

  React.useEffect(() => {
    if (!atom) return;
    setPriority(atom.priority);
    setCategory(atom.category);
    setTagsInput('');
    setBodyMd(atom.body_md);
  }, [atom]);

  if (!atom) return null;

  const handleSave = (): void => {
    const patch: Record<string, unknown> = {};
    if (priority !== atom.priority) patch.priority = priority;
    if (category !== atom.category) patch.category = category.trim();
    const trimmed = tagsInput.trim();
    if (trimmed.length > 0) {
      patch.tags = trimmed
        .split(',')
        .map((t) => t.trim())
        .filter((t) => t.length > 0);
    }
    if (bodyMd !== atom.body_md) patch.body_md = bodyMd;
    if (Object.keys(patch).length === 0) {
      onClose();
      return;
    }
    onSave({ id: atom.id, patch });
    onClose();
  };

  return (
    <Dialog open onOpenChange={(open) => (open ? null : onClose())}>
      <div className="space-y-4" data-testid="atom-edit-modal">
        <div>
          <h2 className="text-lg font-semibold">
            Edit <span className="font-mono">{atom.id}</span>
          </h2>
          <p className="text-xs text-muted-foreground">
            Source: {atom.source_file}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label htmlFor="atom-priority">Priority</Label>
            <Select
              id="atom-priority"
              value={priority}
              onChange={(e) =>
                setPriority(e.target.value as AtomPreviewItem['priority'])
              }
              data-testid="atom-priority"
            >
              <option value="MUST">MUST</option>
              <option value="SHOULD">SHOULD</option>
              <option value="COULD">COULD</option>
              <option value="WONT">WONT</option>
            </Select>
          </div>
          <div>
            <Label htmlFor="atom-category">Category</Label>
            <Input
              id="atom-category"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              data-testid="atom-category"
            />
          </div>
        </div>

        <div>
          <Label htmlFor="atom-tags">
            Add tags (comma-separated; appended to existing)
          </Label>
          <Input
            id="atom-tags"
            value={tagsInput}
            onChange={(e) => setTagsInput(e.target.value)}
            placeholder="auth, sso, mandatory"
            data-testid="atom-tags"
          />
        </div>

        <div>
          <Label htmlFor="atom-body">Body (markdown)</Label>
          <Textarea
            id="atom-body"
            rows={6}
            value={bodyMd}
            onChange={(e) => setBodyMd(e.target.value)}
            data-testid="atom-body"
          />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose} data-testid="atom-cancel">
            Cancel
          </Button>
          <Button onClick={handleSave} data-testid="atom-save">
            Save edit
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
