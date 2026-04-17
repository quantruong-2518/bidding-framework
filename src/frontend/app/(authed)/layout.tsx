'use client';

import * as React from 'react';
import { Sidebar } from '@/components/layout/sidebar';
import { Topbar } from '@/components/layout/topbar';
import { ProviderGate } from '@/components/layout/provider-gate';

export default function AuthedLayout({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <ProviderGate>
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar />
          <div className="flex-1 bg-muted/10">{children}</div>
        </div>
      </div>
    </ProviderGate>
  );
}
