'use client';

import * as React from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { DashboardSummary } from '@/lib/api/audit';

interface CostChartProps {
  byDay: DashboardSummary['byDay'];
  agentCost: DashboardSummary['agentCost'];
}

const AGENT_COLOURS: Record<string, string> = {
  ba: '#2563eb',
  sa: '#16a34a',
  domain: '#f97316',
  other: '#a855f7',
};

/**
 * Dual chart: daily cost bar + agent split pie. Both driven by the
 * server's pre-aggregated `DashboardSummary.byDay` + `agentCost`.
 */
export function CostChart({
  byDay,
  agentCost,
}: CostChartProps): React.ReactElement {
  const agentData = Object.entries(agentCost)
    .filter(([, v]) => v > 0)
    .map(([key, value]) => ({ name: key, value }));

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div
        data-testid="cost-by-day"
        className="h-64 rounded-md border border-border p-4"
      >
        <h4 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
          Cost per day (USD)
        </h4>
        {byDay.length === 0 ? (
          <p className="text-sm text-muted-foreground">No cost data.</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={byDay}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                formatter={(v: number) => [`$${v.toFixed(4)}`, 'Cost']}
              />
              <Bar dataKey="costUsd" fill="#2563eb" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      <div
        data-testid="cost-by-agent"
        className="h-64 rounded-md border border-border p-4"
      >
        <h4 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
          Cost by agent
        </h4>
        {agentData.length === 0 ? (
          <p className="text-sm text-muted-foreground">No agent breakdown.</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={agentData}
                dataKey="value"
                nameKey="name"
                innerRadius={40}
                outerRadius={80}
                paddingAngle={2}
              >
                {agentData.map((entry) => (
                  <Cell
                    key={entry.name}
                    fill={AGENT_COLOURS[entry.name] ?? '#94a3b8'}
                  />
                ))}
              </Pie>
              <Tooltip
                formatter={(v: number) => [`$${v.toFixed(4)}`, 'Cost']}
              />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
