import { Reflector } from '@nestjs/core';
import {
  CallHandler,
  ExecutionContext,
  ForbiddenException,
} from '@nestjs/common';
import { lastValueFrom, of, throwError } from 'rxjs';
import { AuditInterceptor } from '../src/audit/audit.interceptor';
import type { AuditService } from '../src/audit/audit.service';
import { ROLES_KEY } from '../src/auth/roles.decorator';

describe('AuditInterceptor', () => {
  const audit: jest.Mocked<Pick<AuditService, 'record'>> = {
    record: jest.fn().mockResolvedValue(undefined),
  };
  const reflector = new Reflector();

  const interceptor = new AuditInterceptor(
    audit as unknown as AuditService,
    reflector,
  );

  function buildContext(opts: {
    roles?: string[];
    method?: string;
    routePath?: string;
    params?: Record<string, string>;
    user?: { sub: string; username: string; roles: string[] };
  }): ExecutionContext {
    const handler = () => undefined;
    if (opts.roles) Reflect.defineMetadata(ROLES_KEY, opts.roles, handler);

    const req = {
      method: opts.method ?? 'GET',
      route: { path: opts.routePath ?? '/bids/:id' },
      params: opts.params ?? { id: 'bid-123' },
      user: opts.user,
    };
    return {
      getType: () => 'http',
      getHandler: () => handler,
      getClass: () => class Dummy {},
      switchToHttp: () => ({
        getRequest: () => req,
      }),
    } as unknown as ExecutionContext;
  }

  beforeEach(() => {
    audit.record.mockClear();
  });

  it('skips routes without @Roles() metadata', async () => {
    const ctx = buildContext({ roles: undefined });
    const next: CallHandler = { handle: () => of('ok') };
    await lastValueFrom(interceptor.intercept(ctx, next));
    expect(audit.record).not.toHaveBeenCalled();
  });

  it('records a 200 row on success for role-gated routes', async () => {
    const ctx = buildContext({
      roles: ['admin', 'bid_manager'],
      method: 'POST',
      routePath: '/bids/:id/workflow',
      params: { id: 'bid-42' },
      user: {
        sub: 'kc-1',
        username: 'alice',
        roles: ['bid_manager'],
      },
    });
    const next: CallHandler = { handle: () => of({ ok: true }) };
    await lastValueFrom(interceptor.intercept(ctx, next));

    expect(audit.record).toHaveBeenCalledTimes(1);
    expect(audit.record).toHaveBeenCalledWith(
      expect.objectContaining({
        userSub: 'kc-1',
        username: 'alice',
        roles: ['bid_manager'],
        action: 'POST /bids/:id/workflow',
        resourceType: 'bids',
        resourceId: 'bid-42',
        statusCode: 200,
      }),
    );
  });

  it('records the real HTTP status on error', async () => {
    const ctx = buildContext({
      roles: ['admin'],
      method: 'DELETE',
      routePath: '/bids/:id',
      params: { id: 'bid-xyz' },
      user: {
        sub: 'kc-2',
        username: 'bob',
        roles: ['ba'], // intentionally no admin — will trigger forbidden
      },
    });
    const next: CallHandler = {
      handle: () => throwError(() => new ForbiddenException('not allowed')),
    };
    await expect(
      lastValueFrom(interceptor.intercept(ctx, next)),
    ).rejects.toBeInstanceOf(ForbiddenException);
    expect(audit.record).toHaveBeenCalledWith(
      expect.objectContaining({
        statusCode: 403,
        resourceType: 'bids',
        action: 'DELETE /bids/:id',
      }),
    );
  });

  it('records statusCode=500 for plain Error', async () => {
    const ctx = buildContext({
      roles: ['admin'],
      method: 'POST',
      routePath: '/bids/:id/workflow',
      params: { id: 'bid-z' },
      user: { sub: 'kc-3', username: 'carol', roles: ['admin'] },
    });
    const next: CallHandler = {
      handle: () => throwError(() => new Error('boom')),
    };
    await expect(
      lastValueFrom(interceptor.intercept(ctx, next)),
    ).rejects.toThrow('boom');
    expect(audit.record).toHaveBeenCalledWith(
      expect.objectContaining({ statusCode: 500 }),
    );
  });

  it('falls back to `anonymous` when request has no user', async () => {
    const ctx = buildContext({
      roles: ['admin'],
      user: undefined,
    });
    const next: CallHandler = { handle: () => of('ok') };
    await lastValueFrom(interceptor.intercept(ctx, next));
    expect(audit.record).toHaveBeenCalledWith(
      expect.objectContaining({
        userSub: 'anonymous',
        username: 'anonymous',
        roles: [],
      }),
    );
  });
});
