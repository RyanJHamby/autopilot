import { randomBytes } from "node:crypto";

export async function GET(req: Request) {
  const id = process.env.GITHUB_CLIENT_ID;
  if (!id || !process.env.SESSION_SECRET) return new Response("sign-in not configured", { status: 503 });
  const state = randomBytes(16).toString("hex");
  const u = new URL("https://github.com/login/oauth/authorize");
  u.searchParams.set("client_id", id);
  u.searchParams.set("state", state);
  u.searchParams.set("scope", ""); // identity only: no repo access through the user token
  u.searchParams.set("redirect_uri", new URL("/api/auth/callback", req.url).toString());
  return new Response(null, {
    status: 302,
    headers: { Location: u.toString(), "Set-Cookie": `ap_state=${state}; HttpOnly; Secure; SameSite=Lax; Path=/api/auth; Max-Age=600` },
  });
}
