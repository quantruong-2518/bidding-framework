import {
  ForbiddenException,
  Inject,
  Injectable,
  Logger,
  OnModuleInit,
  Optional,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { HttpService } from '@nestjs/axios';
import { firstValueFrom } from 'rxjs';
import { ARTIFACT_KEYS, type ArtifactKey } from '../workflows/artifact-keys';

/**
 * Fallback ACL — kept in sync with `src/ai-service/workflows/acl.py`.
 *
 * This is a defensive cache: if ai-service is unreachable during startup the
 * api-gateway can still enforce RBAC. The live map is fetched on boot (and
 * re-fetched lazily on miss). Any drift between this hardcoded map and Python
 * is surfaced by the `rbac-matrix.spec.ts` 98-case parameterised test.
 */
export const FALLBACK_ARTIFACT_ACL: Record<ArtifactKey, readonly string[]> = {
  bid_card: ['admin', 'ba', 'bid_manager', 'domain_expert', 'qc', 'sa', 'solution_lead'],
  triage: ['admin', 'bid_manager', 'qc'],
  scoping: ['admin', 'ba', 'bid_manager', 'qc', 'sa'],
  ba_draft: ['admin', 'ba', 'bid_manager', 'qc'],
  sa_draft: ['admin', 'bid_manager', 'qc', 'sa', 'solution_lead'],
  domain_notes: ['admin', 'bid_manager', 'domain_expert', 'qc'],
  convergence: ['admin', 'bid_manager', 'qc', 'solution_lead'],
  hld: ['admin', 'bid_manager', 'qc', 'sa', 'solution_lead'],
  wbs: ['admin', 'ba', 'bid_manager', 'qc', 'sa'],
  pricing: ['admin', 'bid_manager', 'qc'],
  proposal_package: ['admin', 'bid_manager', 'qc'],
  reviews: ['admin', 'bid_manager', 'domain_expert', 'qc', 'sa', 'solution_lead'],
  submission: ['admin', 'bid_manager', 'qc'],
  retrospective: [
    'admin',
    'ba',
    'bid_manager',
    'domain_expert',
    'qc',
    'sa',
    'solution_lead',
  ],
};

/**
 * Resolves artifact-key → allowed-role from the ai-service source-of-truth.
 *
 * Admin is a wildcard (always true), matching Python `acl.has_access`.
 */
@Injectable()
export class AclService implements OnModuleInit {
  private readonly logger = new Logger(AclService.name);
  private acl: Record<string, readonly string[]> = { ...FALLBACK_ARTIFACT_ACL };
  private loaded = false;

  constructor(
    @Optional() @Inject(HttpService) private readonly http: HttpService | null,
    @Optional() @Inject(ConfigService) private readonly config: ConfigService | null,
  ) {}

  async onModuleInit(): Promise<void> {
    await this.refresh().catch((err: Error) => {
      this.logger.warn(
        `ACL refresh on boot failed; using fallback map: ${err.message}`,
      );
    });
  }

  /** Fetch the live ACL map from ai-service. Swallow errors → keep fallback. */
  async refresh(): Promise<void> {
    if (!this.http || !this.config) return;
    const base =
      this.config.get<string>('AI_SERVICE_URL') ?? 'http://ai-service:8001';
    try {
      const response = await firstValueFrom(
        this.http.get<Record<string, string[]>>(
          `${base}/workflows/bid/acl/artifacts`,
          { timeout: 5_000 },
        ),
      );
      if (response?.data && typeof response.data === 'object') {
        this.acl = response.data;
        this.loaded = true;
      }
    } catch (err) {
      this.logger.warn(
        `ACL fetch from ai-service failed: ${(err as Error).message}`,
      );
    }
  }

  /** Return the canonical map (either loaded or fallback). */
  getMap(): Record<string, readonly string[]> {
    return this.acl;
  }

  wasLoaded(): boolean {
    return this.loaded;
  }

  hasAccess(roles: readonly string[], key: string): boolean {
    const set = new Set(roles.filter(Boolean));
    if (set.has('admin')) return true;
    const allowed = this.acl[key];
    if (!allowed) {
      throw new Error(`unknown artifact key: ${key}`);
    }
    for (const r of allowed) {
      if (set.has(r)) return true;
    }
    return false;
  }

  /** Throws `ForbiddenException` when the caller's roles can't see `key`. */
  assertVisible(roles: readonly string[], key: string): void {
    if (!ARTIFACT_KEYS.includes(key as ArtifactKey)) {
      throw new Error(`unknown artifact key: ${key}`);
    }
    if (!this.hasAccess(roles, key)) {
      throw new ForbiddenException(
        `Role(s) [${roles.join(',') || 'none'}] cannot access artifact '${key}'.`,
      );
    }
  }
}
