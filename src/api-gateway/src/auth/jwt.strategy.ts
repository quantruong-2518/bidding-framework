import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { PassportStrategy } from '@nestjs/passport';
import { ExtractJwt, Strategy, StrategyOptions } from 'passport-jwt';
import { passportJwtSecret } from 'jwks-rsa';
import type { AuthenticatedUser } from './current-user.decorator';

interface KeycloakJwtPayload {
  sub: string;
  preferred_username?: string;
  email?: string;
  realm_access?: { roles?: string[] };
  resource_access?: Record<string, { roles?: string[] }>;
}

@Injectable()
export class JwtStrategy extends PassportStrategy(Strategy, 'jwt') {
  private static readonly logger = new Logger(JwtStrategy.name);

  constructor(configService: ConfigService) {
    const issuer = configService.get<string>('KEYCLOAK_ISSUER');
    const audience = configService.get<string>('KEYCLOAK_CLIENT_ID');

    if (!issuer || !audience) {
      JwtStrategy.logger.warn(
        'KEYCLOAK_ISSUER or KEYCLOAK_CLIENT_ID missing — JWT verification will fail until set.',
      );
    }

    const options: StrategyOptions = {
      jwtFromRequest: ExtractJwt.fromAuthHeaderAsBearerToken(),
      ignoreExpiration: false,
      audience: audience ?? 'bidding-api',
      issuer: issuer ?? 'http://keycloak:8080/realms/bidding',
      algorithms: ['RS256'],
      secretOrKeyProvider: passportJwtSecret({
        cache: true,
        rateLimit: true,
        jwksRequestsPerMinute: 10,
        jwksUri: `${issuer ?? 'http://keycloak:8080/realms/bidding'}/protocol/openid-connect/certs`,
      }),
    };
    super(options);
  }

  validate(payload: KeycloakJwtPayload): AuthenticatedUser {
    return {
      sub: payload.sub,
      username: payload.preferred_username ?? payload.sub,
      email: payload.email ?? '',
      roles: payload.realm_access?.roles ?? [],
    };
  }
}
