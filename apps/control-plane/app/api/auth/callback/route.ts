import { allowedUser, signSession } from "../../../../lib/auth";

const fail = (m: string, s = 403) => new Response(m, { status: s });

export async function GET(req: Request) {
  const { GITHUB_CLIENT_ID: id, GITHUB_CLIENT_SECRET: secret, SESSION_SECRET: sess, ALLOWED_GITHUB_IDS: allow } = process.env;
  if (!id || !secret || !sess) return fail("sign-in not configured", 503);
  const url = new URL(req.url);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const cookieState = /(?:^|; )ap_state=([a-f0-9]+)/.exec(req.headers.get("cookie") ?? "")?.[1];
  if (!code || !state || state !== cookieState) return fail("bad state");

  const tok = await fetch("https://github.com/login/oauth/access_token", {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ client_id: id, client_secret: secret, code }),
  }).then((r) => r.json());
  if (!tok.access_token) return fail("token exchange failed");
  const me = await fetch("https://api.github.com/user", {
    headers: { Authorization: `Bearer ${tok.access_token}`, "User-Agent": "autopilot-control" },
  }).then((r) => r.json());
  if (!me?.id || !allowedUser(me.id, allow)) return fail("not allowed");

  const session = signSession(sess, { uid: String(me.id), exp: Math.floor(Date.now() / 1000) + 12 * 3600 });
  const h = new Headers({ Location: new URL("/", req.url).toString() });
  h.append("Set-Cookie", `ap_session=${session}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=43200`);
  h.append("Set-Cookie", "ap_state=; HttpOnly; Secure; Path=/api/auth; Max-Age=0");
  return new Response(null, { status: 302, headers: h });
}
