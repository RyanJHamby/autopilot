/** CSRF guard for cookie-authenticated writes: the request must be JSON and come from our own origin. */
export function sameOriginJson(req: Request): boolean {
  if (!(req.headers.get("content-type") ?? "").startsWith("application/json")) return false;
  const origin = req.headers.get("origin");
  return !!origin && origin === new URL(req.url).origin;
}
