import {
  Inject,
  Injectable,
  Logger,
  OnModuleDestroy,
  OnModuleInit,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import Redis, { type RedisOptions } from 'ioredis';

export const REDIS_CLIENT = Symbol('REDIS_CLIENT');
export const REDIS_SUBSCRIBER = Symbol('REDIS_SUBSCRIBER');

/** Cap on the dead-letter list — bounds memory if Redis stays degraded. */
const DLQ_CAP = 1_000;

export type RedisMessageHandler = (channel: string, message: string) => void;

/**
 * Thin wrapper over ioredis exposing:
 *   - XADD publishing for Redis Streams (worker inbox).
 *   - PUBLISH for pub/sub (WebSocket fanout).
 *   - SUBSCRIBE with a dedicated connection.
 */
@Injectable()
export class RedisService implements OnModuleInit, OnModuleDestroy {
  private readonly logger = new Logger(RedisService.name);
  private readonly handlers = new Map<string, Set<RedisMessageHandler>>();

  constructor(
    @Inject(REDIS_CLIENT) private readonly client: Redis,
    @Inject(REDIS_SUBSCRIBER) private readonly subscriber: Redis,
  ) {}

  onModuleInit(): void {
    this.subscriber.on('message', (channel: string, message: string) => {
      const channelHandlers = this.handlers.get(channel);
      if (!channelHandlers) return;
      for (const handler of channelHandlers) {
        try {
          handler(channel, message);
        } catch (err) {
          this.logger.error(
            `Subscriber handler for channel ${channel} threw: ${(err as Error).message}`,
          );
        }
      }
    });
  }

  async onModuleDestroy(): Promise<void> {
    await Promise.allSettled([this.client.quit(), this.subscriber.quit()]);
  }

  getClient(): Redis {
    return this.client;
  }

  /**
   * Append an entry to a Redis stream. Values are JSON-stringified.
   */
  async publishStream(
    stream: string,
    data: Record<string, unknown>,
  ): Promise<string> {
    const entries: string[] = [];
    for (const [key, value] of Object.entries(data)) {
      entries.push(
        key,
        typeof value === 'string' ? value : JSON.stringify(value),
      );
    }
    const id = await this.client.xadd(stream, '*', ...entries);
    return id ?? '';
  }

  /**
   * Park a payload that failed to reach its primary stream. Writes a
   * JSON envelope to a Redis list `${stream}.dlq` (LPUSH) and trims to a
   * cap so the list can't grow unbounded. An oncall script can drain the
   * list with LRANGE/RPOPLPUSH once the underlying outage clears.
   *
   * Caveat: a Redis-list DLQ does NOT help when the entire Redis cluster
   * is down — both calls would fail. Catches the realistic cases (XADD
   * type mismatch, MAXLEN reject, transient stream-only failure).
   */
  async deadLetter(
    stream: string,
    payload: Record<string, unknown>,
    error: Error,
  ): Promise<void> {
    const dlqKey = `${stream}.dlq`;
    const envelope = JSON.stringify({
      stream,
      payload,
      error: error.message,
      failedAt: new Date().toISOString(),
    });
    await this.client
      .multi()
      .lpush(dlqKey, envelope)
      .ltrim(dlqKey, 0, DLQ_CAP - 1)
      .exec();
  }

  /**
   * Publish a pub/sub event (JSON-stringified payload).
   */
  async publishEvent(
    channel: string,
    payload: Record<string, unknown>,
  ): Promise<number> {
    return this.client.publish(channel, JSON.stringify(payload));
  }

  /**
   * Subscribe a handler to a pub/sub channel. Idempotent per channel.
   */
  async subscribe(channel: string, handler: RedisMessageHandler): Promise<void> {
    let set = this.handlers.get(channel);
    if (!set) {
      set = new Set();
      this.handlers.set(channel, set);
      await this.subscriber.subscribe(channel);
      this.logger.log(`Subscribed to channel ${channel}`);
    }
    set.add(handler);
  }

  async unsubscribe(channel: string, handler?: RedisMessageHandler): Promise<void> {
    const set = this.handlers.get(channel);
    if (!set) return;
    if (handler) {
      set.delete(handler);
    }
    if (!handler || set.size === 0) {
      this.handlers.delete(channel);
      await this.subscriber.unsubscribe(channel);
    }
  }
}

export function createRedisClientProvider(
  token: symbol,
): {
  provide: symbol;
  inject: [typeof ConfigService];
  useFactory: (cfg: ConfigService) => Redis;
} {
  return {
    provide: token,
    inject: [ConfigService],
    useFactory: (cfg: ConfigService): Redis => {
      const url = cfg.get<string>('REDIS_URL') ?? 'redis://localhost:6379';
      const options: RedisOptions = {
        lazyConnect: false,
        maxRetriesPerRequest: 3,
      };
      return new Redis(url, options);
    },
  };
}
