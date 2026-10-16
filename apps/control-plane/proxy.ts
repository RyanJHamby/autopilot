import { NextResponse, type NextRequest } from "next/server";
import { readSession } from "./lib/auth";

// Default deny. The webhook authenticates itself with an HMAC; login/callback must be reachable to sign in.
const PUBLIC = [/^\/login$/, /^\/api\/auth\/(login|callback)$/, /^\/api\/github\/webhook$/, /^\/manifest\.webmanifest$/];

export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (PUBLIC.some((re) => re.test(pathname))) return NextResponse.next();
  const ok = readSession(process.env.SESSION_SECRET ?? "", req.cookies.get("ap_session")?.value);
  if (ok) return NextResponse.next();
  if (pathname.startsWith("/api/")) return new NextResponse("unauthorized", { status: 401 });
  return NextResponse.redirect(new URL("/login", req.url));
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
