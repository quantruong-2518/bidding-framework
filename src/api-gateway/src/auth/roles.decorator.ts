import { SetMetadata } from '@nestjs/common';

export const ROLES_KEY = 'roles';

export type AppRole = 'admin' | 'bid_manager' | 'ba' | 'sa' | 'qc';

/**
 * Declares the roles allowed to invoke a controller route.
 * Enforced by RolesGuard (applied globally in AppModule).
 */
export const Roles = (...roles: AppRole[]): MethodDecorator & ClassDecorator =>
  SetMetadata(ROLES_KEY, roles);
