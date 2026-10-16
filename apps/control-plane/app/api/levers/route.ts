import { appJwt, installationToken, repoInstallationId, setRepoVariable } from "../../../lib/githubApp";
import { planChange, type Levers } from "../../../lib/levers";
import { sameOriginJson } from "../../../lib/origin";
import { currentSession } from "../../../lib/session";

export const runtime = "nodejs";

const sb = (path: string, init: RequestInit = {}) =>
  fetch(`${process.env.SUPABASE_URL}/rest/v1/${path}`, {
    ...init,
    headers: {
      apikey: process.env.SUPABASE_SERVICE_ROLE_KEY!,
      Authorization: `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`,
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });

/**
 * POST { repo: "owner/name", changes: { priority: 8, paused: true, ... } }
 * Safe levers are written to the database and pushed as AUTOPILOT_* repo variables; guardrail changes are returned as
 * a PR plan and nothing is applied. Owner session only (single-owner until grants are wired to Supabase Auth).
 */
export async function POST(req: Request) {
  if (!(await currentSession())) return new Response("unauthorized", { status: 401 });
  if (!sameOriginJson(req)) return new Response("bad origin", { status: 403 });
  const { repo, changes } = (await req.json()) as { repo?: string; changes?: Record<string, unknown> };
  if (!repo || !/^[\w.-]+\/[\w.-]+$/.test(repo) || !changes || typeof changes !== "object") return new Response("bad request", { status: 400 });

  const rows = (await (await sb(`projects?repo=eq.${encodeURIComponent(repo)}&select=id,org_id,enabled,priority,hold_until`)).json()) as any[];
  if (rows.length !== 1) return new Response("unknown project", { status: 404 });
  const p = rows[0];
  const cur: Levers = { enabled: p.enabled, paused: false, priority: p.priority, greediness: 0, max_open_prs: 3, hold_until: p.hold_until };
  const plan = planChange(cur, changes, "owner", true);

  const applied: string[] = [];
  if (Object.keys(plan.variables).length) {
    try {
      const jwt = appJwt(process.env.GITHUB_APP_ID!, process.env.GITHUB_APP_PRIVATE_KEY!);
      const tok = await installationToken(jwt, await repoInstallationId(jwt, repo), repo, { actions_variables: "write" });
      for (const [k, v] of Object.entries(plan.variables)) {
        await setRepoVariable(tok, repo, k, v);
        applied.push(k);
      }
    } catch (e) {
      return Response.json({ plan, applied, error: String((e as Error).message) }, { status: 502 });
    }
    const patch: Record<string, unknown> = {};
    if ("AUTOPILOT_PRIORITY" in plan.variables) patch.priority = Number(plan.variables.AUTOPILOT_PRIORITY);
    if ("AUTOPILOT_ENABLED" in plan.variables) patch.enabled = plan.variables.AUTOPILOT_ENABLED === "true";
    if ("AUTOPILOT_HOLD_UNTIL" in plan.variables) patch.hold_until = plan.variables.AUTOPILOT_HOLD_UNTIL || null;
    if (Object.keys(patch).length) await sb(`projects?id=eq.${p.id}`, { method: "PATCH", body: JSON.stringify(patch) });
  }
  await sb("audit", {
    method: "POST",
    body: JSON.stringify({ org_id: p.org_id, actor: "00000000-0000-0000-0000-000068158512", action: "levers.change", detail: { repo, plan, applied } }),
  });
  return Response.json({ plan, applied });
}
