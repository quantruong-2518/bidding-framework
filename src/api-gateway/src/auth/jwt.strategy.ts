import { Injectable, Logger, UnauthorizedException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { PassportStrategy } from '@nestjs/passport';
import { ExtractJwt, Strategy, StrategyOptions } from 'passport-jwt';
import { passportJwtSecret } from 'jwks-rsa';
import type { AuthenticatedUser } from './current-user.decorator';

/**
 * Phase 3.2a — hard-coded audience per D12 on the plan.
 * Passport-jwt uses the `audience` StrategyOption to reject tokens whose
 * `aud` claim does not include this value. We ALSO assert it a second time
 * inside `validate()` as a belt-and-braces defense against any future
 * config drift (e.g. if someone sets KEYCLOAK_CLIENT_ID to something else
 * by mistake — strategy construction would loosen the check silently).
 */
export const EXPECTED_AUDIENCE = 'bidding-api';

interface KeycloakJwtPayload {
  sub: string;
  aud?: string | string[];
  preferred_username?: string;
  email?: string;
  realm_access?: { roles?: string[] };
  resource_access?: Record<string, { roles?: string[] }>;
}

@Injectable()
export class JwtStrategy extends PassportStrategy(Strategy, 'jwt') {
  private static readonly logger = new Logger(JwtStrategy.name);

  constructor(configService: ConfigService) {
    const issuer =
      configService.get<string>('KEYCLOAK_ISSUER') ??
      'http://keycloak:8080/realms/bidding';
    // Public-facing issuer URL embedded in token `iss` claim. Defaults to the
    // realm's `frontendUrl` (http://localhost:8080) so browser-issued tokens
    // verify. Falls back to `issuer` when unset (single-host dev).
    const publicIssuer =
      configService.get<string>('KEYCLOAK_PUBLIC_ISSUER') ?? issuer;
    // JWKS endpoint — must be reachable from THIS process (api-gateway). Uses
    // the internal `keycloak:8080` hostname inside Docker; `publicIssuer` is
    // unreachable from inside the container.
    const jwksUri =
      configService.get<string>('KEYCLOAK_JWKS_URI') ??
      `${issuer}/protocol/openid-connect/certs`;

    if (!configService.get<string>('KEYCLOAK_ISSUER')) {
      JwtStrategy.logger.warn(
        'KEYCLOAK_ISSUER missing — JWT verification will fail until set.',
      );
    }

    const options: StrategyOptions = {
      jwtFromRequest: ExtractJwt.fromAuthHeaderAsBearerToken(),
      ignoreExpiration: false,
      audience: EXPECTED_AUDIENCE,
      issuer: publicIssuer,
      algorithms: ['RS256'],
      secretOrKeyProvider: passportJwtSecret({
        cache: true,
        rateLimit: true,
        jwksRequestsPerMinute: 10,
        jwksUri,
      }),
    };
    super(options);
  }

  validate(payload: KeycloakJwtPayload): AuthenticatedUser {
    // Belt-and-braces audience guard in addition to passport-jwt's own check.
    if (!matchesAudience(payload.aud, EXPECTED_AUDIENCE)) {
      throw new UnauthorizedException(
        `JWT audience must include '${EXPECTED_AUDIENCE}'.`,
      );
    }
    return {
      sub: payload.sub,
      username: payload.preferred_username ?? payload.sub,
      email: payload.email ?? '',
      roles: payload.realm_access?.roles ?? [],
    };
  }
}

function matchesAudience(
  claim: string | string[] | undefined,
  expected: string,
): boolean {
  if (!claim) return false;
  if (Array.isArray(claim)) return claim.includes(expected);
  return claim === expected;
}
