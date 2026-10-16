import { createHmac, timingSafeEqual } from "node:crypto";

/** Allowlist of GitHub numeric user ids that may sign in (ids, never logins: logins can be renamed and reclaimed). */
export function allowedUser(id: number | string, allow: string | undefined): boolean {
  const ids = (allow ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  return ids.length > 0 && ids.includes(String(id));
}

export interface Session {
  uid: string;
  exp: number; // epoch seconds
}

const b64 = (s: string) => Buffer.from(s).toString("base64url");

export function signSession(secret: string, s: Session): string {
  if (secret.length < 32) throw new Error("session secret must be at least 32 chars");
  const body = b64(JSON.stringify(s));
  return `${body}.${createHmac("sha256", secret).update(body).digest("base64url")}`;
}

export function readSession(secret: string, token: string | undefined, now = Date.now() / 1000): Session | null {
  if (!token || secret.length < 32) return null;
  const [body, mac] = token.split(".");
  if (!body || !mac) return null;
  const want = createHmac("sha256", secret).update(body).digest();
  let got: Buffer;
  try {
    got = Buffer.from(mac, "base64url");
  } catch {
    return null;
  }
  if (got.length !== want.length || !timingSafeEqual(got, want)) return null;
  try {
    const s = JSON.parse(Buffer.from(body, "base64url").toString()) as Session;
    return typeof s.uid === "string" && typeof s.exp === "number" && s.exp > now ? s : null;
  } catch {
    return null;
  }
}
