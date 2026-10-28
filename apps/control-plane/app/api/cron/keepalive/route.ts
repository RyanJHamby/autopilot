export const runtime = "nodejs";

/** Daily ping so the free-tier Supabase project is never paused for inactivity (a paused DB silently drops ledger events).
 * Needs no secret: it reads one id server-side and returns only "ok" or an error, never data. */
export async function GET() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) return new Response("ledger store not configured", { status: 501 });
  const res = await fetch(`${url}/rest/v1/projects?select=id&limit=1`, { headers: { apikey: key, Authorization: `Bearer ${key}` } });
  return new Response(res.ok ? "ok" : "ledger unreachable", { status: res.ok ? 200 : 502 });
}
