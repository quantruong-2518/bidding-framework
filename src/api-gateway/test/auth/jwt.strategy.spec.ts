import { ConfigService } from '@nestjs/config';
import { UnauthorizedException } from '@nestjs/common';
import { EXPECTED_AUDIENCE, JwtStrategy } from '../../src/auth/jwt.strategy';

type Payload = Parameters<JwtStrategy['validate']>[0];

function makeStrategy(): JwtStrategy {
  const config = new ConfigService({
    KEYCLOAK_ISSUER: 'http://keycloak:8080/realms/bidding',
  });
  return new JwtStrategy(config);
}

describe('JwtStrategy.validate', () => {
  const baseline: Payload = {
    sub: 'user-123',
    aud: EXPECTED_AUDIENCE,
    preferred_username: 'alice',
    email: 'alice@example.com',
    realm_access: { roles: ['bid_manager', 'ba'] },
  };

  it('maps a valid payload to AuthenticatedUser preserving realm roles', () => {
    const strategy = makeStrategy();
    expect(strategy.validate(baseline)).toEqual({
      sub: 'user-123',
      username: 'alice',
      email: 'alice@example.com',
      roles: ['bid_manager', 'ba'],
    });
  });

  it('falls back to sub when preferred_username missing', () => {
    const strategy = makeStrategy();
    const payload: Payload = { ...baseline, preferred_username: undefined };
    expect(strategy.validate(payload).username).toBe('user-123');
  });

  it('defaults roles to an empty array when realm_access is absent', () => {
    const strategy = makeStrategy();
    const payload: Payload = { ...baseline, realm_access: undefined };
    expect(strategy.validate(payload).roles).toEqual([]);
  });

  it('accepts an array aud that includes bidding-api', () => {
    const strategy = makeStrategy();
    const payload: Payload = { ...baseline, aud: ['account', EXPECTED_AUDIENCE] };
    expect(() => strategy.validate(payload)).not.toThrow();
  });

  it('rejects tokens whose aud is a string other than bidding-api', () => {
    const strategy = makeStrategy();
    const payload: Payload = { ...baseline, aud: 'some-other-client' };
    expect(() => strategy.validate(payload)).toThrow(UnauthorizedException);
  });

  it('rejects tokens whose aud array omits bidding-api', () => {
    const strategy = makeStrategy();
    const payload: Payload = { ...baseline, aud: ['account', 'some-other-client'] };
    expect(() => strategy.validate(payload)).toThrow(UnauthorizedException);
  });

  it('rejects tokens without an aud claim', () => {
    const strategy = makeStrategy();
    const payload: Payload = { ...baseline, aud: undefined };
    expect(() => strategy.validate(payload)).toThrow(UnauthorizedException);
  });
});
