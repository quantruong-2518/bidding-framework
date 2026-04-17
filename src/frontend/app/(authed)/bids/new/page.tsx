import * as React from 'react';
import { NewBidShell } from '@/components/bids/new-bid-shell';

export default function NewBidPage(): React.ReactElement {
  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">New bid</h1>
        <p className="text-sm text-muted-foreground">
          Optionally upload an RFP to pre-fill the Bid Card. Triggering the
          workflow moves it through S0 → S1 → S2 and waits for triage approval.
        </p>
      </div>
      <NewBidShell />
    </main>
  );
}
