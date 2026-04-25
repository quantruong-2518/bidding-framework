import {
  CallHandler,
  ExecutionContext,
  HttpException,
  Injectable,
  NestInterceptor,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { Observable, tap } from 'rxjs';
import { ROLES_KEY } from '../auth/roles.decorator';
import type { AuthenticatedUser } from '../auth/current-user.decorator';
import { AuditService } from './audit.service';
import { SKIP_AUDIT_KEY } from './skip-audit.decorator';

/**
 * Global interceptor that writes one `audit_log` row per role-gated HTTP request.
 *
 * Routes without `@Roles(...)` metadata (e.g. `@Public()`) are skipped, which
 * keeps the table sized for compliance review rather than every health-check.
 *
 * The resource id is extracted from the `id` route param when present — this
 * matches every current role-gated route (`/bids/:id`, `/bids/:id/workflow`,
 * `/bids/:id/workflow/artifacts/:type`). Future routes can encode a different
 * param; `resourceType` is derived from the top-level path segment.
 */
@Injectable()
export class AuditInterceptor implements NestInterceptor {
  constructor(
    private readonly audit: AuditService,
    private readonly reflector: Reflector,
  ) {}

  intercept(
    context: ExecutionContext,
    next: CallHandler,
  ): Observable<unknown> {
    if (context.getType() !== 'http') {
      return next.handle();
    }

    const roleMeta = this.reflector.getAllAndOverride<string[] | undefined>(
      ROLES_KEY,
      [context.getHandler(), context.getClass()],
    );
    if (!roleMeta || roleMeta.length === 0) {
      return next.handle();
    }

    const skip = this.reflector.getAllAndOverride<boolean | undefined>(
      SKIP_AUDIT_KEY,
      [context.getHandler(), context.getClass()],
    );
    if (skip) {
      return next.handle();
    }

    const req = context
      .switchToHttp()
      .getRequest<{
        method: string;
        route?: { path?: string };
        originalUrl?: string;
        url?: string;
        params?: Record<string, string>;
        user?: AuthenticatedUser;
      }>();

    const routePath = req.route?.path ?? req.originalUrl ?? req.url ?? '';
    const action = `${req.method} ${routePath}`;
    const resourceId = req.params?.id ?? null;
    const resourceType = deriveResourceType(routePath);
    const user = req.user;

    return next.handle().pipe(
      tap({
        next: () =>
          this.audit.record({
            userSub: user?.sub ?? 'anonymous',
            username: user?.username ?? 'anonymous',
            roles: user?.roles ?? [],
            action,
            resourceType,
            resourceId,
            statusCode: 200,
            metadata: {
              params: req.params ?? {},
              requiredRoles: roleMeta,
            },
          }),
        error: (err: unknown) =>
          this.audit.record({
            userSub: user?.sub ?? 'anonymous',
            username: user?.username ?? 'anonymous',
            roles: user?.roles ?? [],
            action,
            resourceType,
            resourceId,
            statusCode:
              err instanceof HttpException ? err.getStatus() : 500,
            metadata: {
              params: req.params ?? {},
              requiredRoles: roleMeta,
              error: (err as Error)?.message ?? 'unknown',
            },
          }),
      }),
    );
  }
}

function deriveResourceType(routePath: string): string {
  const trimmed = routePath.replace(/^\/+/, '').split('/')[0] ?? '';
  return trimmed || 'unknown';
}
