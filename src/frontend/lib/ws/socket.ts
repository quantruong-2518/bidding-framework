'use client';

import { io, type Socket } from 'socket.io-client';

let socketInstance: Socket | null = null;
let socketToken: string | null = null;

export function wsBaseUrl(): string {
  return process.env.NEXT_PUBLIC_WS_URL ?? 'http://localhost:3001';
}

/**
 * Returns a singleton socket.io client bound to the supplied JWT. If the
 * token changes, the previous socket is torn down and replaced.
 */
export function getSocket(token: string | null): Socket | null {
  if (!token) {
    if (socketInstance) {
      socketInstance.disconnect();
      socketInstance = null;
      socketToken = null;
    }
    return null;
  }

  if (socketInstance && socketToken === token && socketInstance.connected) {
    return socketInstance;
  }
  if (socketInstance && socketToken !== token) {
    socketInstance.disconnect();
    socketInstance = null;
  }

  socketToken = token;
  socketInstance = io(`${wsBaseUrl()}/ws`, {
    auth: { token },
    transports: ['websocket'],
    autoConnect: true,
    reconnection: true,
    reconnectionAttempts: 5,
  });

  return socketInstance;
}

export function closeSocket(): void {
  if (socketInstance) {
    socketInstance.disconnect();
    socketInstance = null;
    socketToken = null;
  }
}
