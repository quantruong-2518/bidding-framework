import { Controller, Get, UseGuards } from '@nestjs/common';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import { AclService } from './acl.service';

/**
 * Exposes the artifact-key → allowed-role map for the frontend.
 *
 * Auth-gated (any authenticated user) but NOT role-gated — every user needs
 * the map to render dashboards with role-appropriate panels. This means the
 * route is also skipped by the `AuditInterceptor` (no `@Roles` metadata).
 */
@UseGuards(JwtAuthGuard)
@Controller('acl')
export class AclController {
  constructor(private readonly acl: AclService) {}

  @Get('artifacts')
  getArtifactAcl(): Record<string, readonly string[]> {
    return this.acl.getMap();
  }
}
