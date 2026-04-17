import { Logger, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import {
  OnGatewayConnection,
  OnGatewayDisconnect,
  SubscribeMessage,
  WebSocketGateway,
  WebSocketServer,
  MessageBody,
  ConnectedSocket,
} from '@nestjs/websockets';
import type { Server, Socket } from 'socket.io';
import { JwksClient } from 'jwks-rsa';
import jwt, { type JwtHeader, type SigningKeyCallback, type VerifyErrors } from 'jsonwebtoken';
import { RedisService } from '../redis/redis.service';

export const BID_EVENTS_CHANNEL_PREFIX = 'bid.events.channel';
export const BID_ROOM_PREFIX = 'bid:';

interface KeycloakTokenPayload {
  sub: string;
  preferred_username?: string;
  email?: string;
  realm_access?: { roles?: string[] };
}

/**
 * WebSocket gateway. Clients connect to /ws, pass a Keycloak JWT via
 * handshake.auth.token, then send a `subscribe` event with a bidId to join
 * the bid:{bidId} room. Server fans out Redis pub/sub events onto rooms.
 */
@WebSocketGateway({ cors: true, namespace: '/ws' })
export class EventsGateway
  implements OnGatewayConnection, OnGatewayDisconnect, OnModuleInit
{
  private readonly logger = new Logger(EventsGateway.name);
  private readonly jwks: JwksClient;
  private readonly issuer: string;
  private readonly audience: string;

  @WebSocketServer()
  server!: Server;

  constructor(
    private readonly redis: RedisService,
    config: ConfigService,
  ) {
    this.issuer =
      config.get<string>('KEYCLOAK_ISSUER') ??
      'http://keycloak:8080/realms/bidding';
    this.audience = config.get<string>('KEYCLOAK_CLIENT_ID') ?? 'bidding-api';
    this.jwks = new JwksClient({
      jwksUri: `${this.issuer}/protocol/openid-connect/certs`,
      cache: true,
      rateLimit: true,
      jwksRequestsPerMinute: 10,
    });
  }

  async onModuleInit(): Promise<void> {
    // Listen for all bid events via a single wildcard-style channel. The
    // ai-service publishes to `bid.events.channel.{bidId}`; we subscribe to
    // `bid.events.channel.broadcast` for fleet-wide events and per-bid on
    // demand when rooms are joined.
    await this.redis.subscribe(
      `${BID_EVENTS_CHANNEL_PREFIX}.broadcast`,
      (channel, message) => this.relayBroadcast(channel, message),
    );
  }

  async handleConnection(client: Socket): Promise<void> {
    const token =
      (client.handshake.auth as { token?: string } | undefined)?.token ??
      this.extractBearer(client.handshake.headers['authorization']);

    if (!token) {
      this.logger.warn(`ws connection ${client.id} rejected: missing token`);
      client.emit('error', { message: 'missing auth token' });
      client.disconnect(true);
      return;
    }

    try {
      const user = await this.verifyToken(token);
      client.data.user = user;
      this.logger.log(`ws connected: ${client.id} as ${user.username}`);
    } catch (err) {
      this.logger.warn(
        `ws connection ${client.id} rejected: ${(err as Error).message}`,
      );
      client.emit('error', { message: 'invalid auth token' });
      client.disconnect(true);
    }
  }

  handleDisconnect(client: Socket): void {
    this.logger.log(`ws disconnected: ${client.id}`);
  }

  @SubscribeMessage('subscribe')
  async handleSubscribe(
    @MessageBody() bidId: string,
    @ConnectedSocket() client: Socket,
  ): Promise<{ ok: boolean; room?: string; error?: string }> {
    if (!bidId || typeof bidId !== 'string') {
      return { ok: false, error: 'bidId required' };
    }
    const room = `${BID_ROOM_PREFIX}${bidId}`;
    await client.join(room);

    // Subscribe (idempotent) to per-bid pub/sub channel.
    const channel = `${BID_EVENTS_CHANNEL_PREFIX}.${bidId}`;
    await this.redis.subscribe(channel, (_ch, message) =>
      this.relayToRoom(room, message),
    );
    return { ok: true, room };
  }

  @SubscribeMessage('unsubscribe')
  async handleUnsubscribe(
    @MessageBody() bidId: string,
    @ConnectedSocket() client: Socket,
  ): Promise<{ ok: boolean }> {
    if (!bidId) return { ok: false };
    await client.leave(`${BID_ROOM_PREFIX}${bidId}`);
    return { ok: true };
  }

  private relayToRoom(room: string, message: string): void {
    try {
      const payload: unknown = JSON.parse(message);
      this.server.to(room).emit('bid.event', payload);
    } catch {
      this.server.to(room).emit('bid.event', { raw: message });
    }
  }

  private relayBroadcast(_channel: string, message: string): void {
    try {
      const payload: unknown = JSON.parse(message);
      this.server.emit('bid.broadcast', payload);
    } catch {
      this.server.emit('bid.broadcast', { raw: message });
    }
  }

  private extractBearer(value: string | string[] | undefined): string | null {
    if (!value) return null;
    const header = Array.isArray(value) ? value[0] : value;
    if (!header.toLowerCase().startsWith('bearer ')) return null;
    return header.slice(7).trim();
  }

  private verifyToken(token: string): Promise<KeycloakTokenPayload & { username: string }> {
    const getKey = (header: JwtHeader, cb: SigningKeyCallback): void => {
      if (!header.kid) {
        cb(new Error('missing kid in JWT header'));
        return;
      }
      this.jwks
        .getSigningKey(header.kid)
        .then((key) => cb(null, key.getPublicKey()))
        .catch((err) => cb(err as Error));
    };

    return new Promise((resolve, reject) => {
      jwt.verify(
        token,
        getKey,
        {
          audience: this.audience,
          issuer: this.issuer,
          algorithms: ['RS256'],
        },
        (err: VerifyErrors | null, decoded) => {
          if (err || !decoded || typeof decoded === 'string') {
            reject(err ?? new Error('invalid token'));
            return;
          }
          const payload = decoded as KeycloakTokenPayload;
          resolve({
            ...payload,
            username: payload.preferred_username ?? payload.sub,
          });
        },
      );
    });
  }
}
