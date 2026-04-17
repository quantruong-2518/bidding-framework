import * as React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { CreateBidForm } from '@/components/bids/create-bid-form';

export default function NewBidPage(): React.ReactElement {
  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">New bid</h1>
        <p className="text-sm text-muted-foreground">
          Create a Bid Card. Triggering the workflow moves it through S0 → S1
          → S2 and waits for triage approval.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Bid details</CardTitle>
          <CardDescription>
            Required fields match the NestJS POST /bids contract.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <CreateBidForm />
        </CardContent>
      </Card>
    </main>
  );
}
