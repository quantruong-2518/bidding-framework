'use client';

import * as React from 'react';
import { cn } from '@/lib/utils/cn';

export interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
  className?: string;
}

/**
 * Minimal modal dialog. Not a full shadcn/Radix implementation — enough for
 * confirm boxes in the PoC. Click-outside and Escape close.
 */
export function Dialog({ open, onOpenChange, children, className }: DialogProps): React.ReactElement | null {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onOpenChange(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onOpenChange]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4"
      onClick={() => onOpenChange(false)}
    >
      <div
        className={cn(
          'w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-xl',
          className,
        )}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}
