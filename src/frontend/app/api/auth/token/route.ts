import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const INTERNAL_URL =
  process.env.KEYCLOAK_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_KEYCLOAK_URL ??
  'http://keycloak:8080';
const REALM = process.env.NEXT_PUBLIC_KEYCLOAK_REALM ?? 'bidding';

/**
 * Same-origin proxy for the Keycloak token endpoint. The browser posts here
 * instead of directly to Keycloak, which sidesteps every class of CORS /
 * mixed-origin failure that bit us during Conv-8b (realm `frontendUrl` makes
 * the `iss` claim authoritative, but preflight cache + extensions still
 * intermittently block cross-origin POSTs in some browsers).
 *
 * The proxy forwards the raw `application/x-www-form-urlencoded` body
 * verbatim, so both `authorization_code` and `refresh_token` grants work.
 */
export async function POST(req: NextRequest): Promise<NextResponse> {
  const body = await req.text();
  const upstream = await fetch(
    `${INTERNAL_URL}/realms/${REALM}/protocol/openid-connect/token`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    },
  );
  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: {
      'Content-Type':
        upstream.headers.get('content-type') ?? 'application/json',
    },
  });
}
