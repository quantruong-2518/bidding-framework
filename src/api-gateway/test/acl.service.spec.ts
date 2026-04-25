import { HttpService } from '@nestjs/axios';
import { ConfigService } from '@nestjs/config';
import { of, throwError } from 'rxjs';
import type { AxiosResponse } from 'axios';
import { AclService, FALLBACK_ARTIFACT_ACL } from '../src/acl/acl.service';
import { ARTIFACT_KEYS } from '../src/workflows/artifact-keys';

const okAxios = <T>(data: T): AxiosResponse<T> => ({
  data,
  status: 200,
  statusText: 'OK',
  headers: {},
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  config: {} as any,
});

describe('AclService', () => {
  it('starts with the fallback map', () => {
    const service = new AclService(null, null);
    expect(service.getMap()).toEqual(FALLBACK_ARTIFACT_ACL);
    expect(service.wasLoaded()).toBe(false);
  });

  it('refresh() replaces the map with the ai-service payload', async () => {
    const http = {
      get: jest.fn().mockReturnValue(
        of(
          okAxios({
            ...FALLBACK_ARTIFACT_ACL,
            pricing: ['admin'], // simulate a tightened policy
          }),
        ),
      ),
    } as unknown as HttpService;
    const config = {
      get: (k: string) => (k === 'AI_SERVICE_URL' ? 'http://ai:8001' : undefined),
    } as unknown as ConfigService;

    const service = new AclService(http, config);
    await service.refresh();

    expect(http.get).toHaveBeenCalledWith(
      'http://ai:8001/workflows/bid/acl/artifacts',
      expect.objectContaining({ timeout: 5000 }),
    );
    expect(service.wasLoaded()).toBe(true);
    expect(service.getMap().pricing).toEqual(['admin']);
    expect(service.hasAccess(['bid_manager'], 'pricing')).toBe(false);
  });

  it('refresh() swallows upstream errors and keeps the fallback', async () => {
    const http = {
      get: jest
        .fn()
        .mockReturnValue(throwError(() => new Error('econnrefused'))),
    } as unknown as HttpService;
    const config = {
      get: () => 'http://ai:8001',
    } as unknown as ConfigService;

    const service = new AclService(http, config);
    await expect(service.refresh()).resolves.toBeUndefined();
    expect(service.wasLoaded()).toBe(false);
    expect(service.getMap()).toEqual(FALLBACK_ARTIFACT_ACL);
  });

  it('onModuleInit never throws even if refresh fails', async () => {
    const http = {
      get: () => {
        throw new Error('boom');
      },
    } as unknown as HttpService;
    const config = { get: () => 'http://ai:8001' } as unknown as ConfigService;
    const service = new AclService(http, config);
    await expect(service.onModuleInit()).resolves.toBeUndefined();
  });

  it('assertVisible passes for admin across every artifact', () => {
    const service = new AclService(null, null);
    for (const key of ARTIFACT_KEYS) {
      expect(() => service.assertVisible(['admin'], key)).not.toThrow();
    }
  });

  it('assertVisible rejects unknown artifact keys', () => {
    const service = new AclService(null, null);
    expect(() => service.assertVisible(['admin'], 'gibberish')).toThrow(
      /unknown artifact key/,
    );
  });

  it('hasAccess ignores blank roles', () => {
    const service = new AclService(null, null);
    expect(service.hasAccess(['', '  '], 'bid_card')).toBe(false);
    expect(service.hasAccess(['admin', ''], 'pricing')).toBe(true);
  });
});
