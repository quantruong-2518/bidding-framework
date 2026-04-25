import { SetMetadata } from '@nestjs/common';

export const SKIP_AUDIT_KEY = 'audit:skip';

/**
 * Opts a role-gated route out of the `audit_log` interceptor.
 *
 * Use sparingly — audit log is the compliance source of truth for
 * who-did-what. Apply only to:
 *   - High-frequency read polls (`/workflow/status` polled every 15s from
 *     the UI) whose signal-to-noise ratio would drown the table.
 *   - The audit dashboard endpoints themselves (otherwise every admin
 *     dashboard render logs itself, producing self-referential noise).
 *
 * Writes (POST/PATCH/DELETE) should stay audited. If you're tempted to
 * silence a write, the answer is probably "fix the caller, not the log".
 */
export const SkipAudit = (): MethodDecorator & ClassDecorator =>
  SetMetadata(SKIP_AUDIT_KEY, true);
