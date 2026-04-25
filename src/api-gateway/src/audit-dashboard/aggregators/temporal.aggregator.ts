import { Injectable, Logger } from '@nestjs/common';
import type { WorkflowHistoryEvent } from '../types';

/**
 * Placeholder Temporal Visibility aggregator.
 *
 * The real integration needs `@temporalio/client` + a reachable Temporal
 * server. Phase 3.3 ships the aggregator as a stub that returns empty
 * history + a warning, so `AuditDashboardService` can surface the gap to
 * the UI without throwing. Phase 3.6 (K8s) will land the gRPC client
 * against the in-cluster Temporal frontend. This file keeps the interface
 * stable so only the implementation changes.
 */
@Injectable()
export class TemporalAggregator {
  private readonly logger = new Logger(TemporalAggregator.name);

  async forWorkflow(workflowId: string | null): Promise<{
    events: WorkflowHistoryEvent[];
    warning?: string;
  }> {
    if (!workflowId) {
      return {
        events: [],
        warning: 'No workflow id attached to this bid yet.',
      };
    }
    // Intentionally not wired to a Temporal client in Phase 3.3.
    this.logger.debug(
      `temporal.history requested for ${workflowId} (stub)`,
    );
    return {
      events: [],
      warning:
        'Temporal Visibility integration is stubbed (lands with Phase 3.6 K8s).',
    };
  }
}
