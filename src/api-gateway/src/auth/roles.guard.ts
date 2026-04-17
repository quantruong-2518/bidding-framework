import { CanActivate, ExecutionContext, ForbiddenException, Injectable } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { IS_PUBLIC_KEY } from './public.decorator';
import { ROLES_KEY, type AppRole } from './roles.decorator';
import type { AuthenticatedUser } from './current-user.decorator';

/**
 * Enforces @Roles(...) metadata on controller routes.
 * No metadata => pass-through (authentication-only).
 * Runs after JwtAuthGuard so request.user is populated.
 */
@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private readonly reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const isPublic = this.reflector.getAllAndOverride<boolean>(IS_PUBLIC_KEY, [
      context.getHandler(),
      context.getClass(),
    ]);
    if (isPublic) {
      return true;
    }

    const required = this.reflector.getAllAndOverride<AppRole[]>(ROLES_KEY, [
      context.getHandler(),
      context.getClass(),
    ]);
    if (!required || required.length === 0) {
      return true;
    }

    const request = context.switchToHttp().getRequest<{ user?: AuthenticatedUser }>();
    const user = request.user;
    if (!user || !Array.isArray(user.roles)) {
      throw new ForbiddenException('Missing authenticated user context.');
    }

    const hasRole = required.some((role) => user.roles.includes(role));
    if (!hasRole) {
      throw new ForbiddenException(
        `Requires one of roles: ${required.join(', ')}`,
      );
    }
    return true;
  }
}
