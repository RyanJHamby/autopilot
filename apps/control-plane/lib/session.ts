import { cookies } from "next/headers";
import { readSession, type Session } from "./auth";

export const COOKIE = "ap_session";

/** Server-side check used by pages and routes in addition to proxy.ts (proxy is only an optimistic gate). */
export async function currentSession(): Promise<Session | null> {
  const jar = await cookies();
  return readSession(process.env.SESSION_SECRET ?? "", jar.get(COOKIE)?.value);
}
