import { Global, Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import {
  REDIS_CLIENT,
  REDIS_SUBSCRIBER,
  RedisService,
  createRedisClientProvider,
} from './redis.service';

@Global()
@Module({
  imports: [ConfigModule],
  providers: [
    createRedisClientProvider(REDIS_CLIENT),
    createRedisClientProvider(REDIS_SUBSCRIBER),
    RedisService,
  ],
  exports: [RedisService],
})
export class RedisModule {}
