import { appJwt, installationToken, repoInstallationId } from "../../../lib/githubApp";
import { sameOriginJson } from "../../../lib/origin";
import { currentSession } from "../../../lib/session";
import { issueBody, issueTitle, screen, type TaskInput } from "../../../lib/task";

export const runtime = "nodejs";

const OWNER_UUID = "00000000-0000-0000-0000-000068158512";
const MAX_PER_DAY = 10;

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
 * POST { repo, goal, acceptance: string[], scope?: string[] }
 * Creates a GitHub issue labelled `agent-ready` ONLY if the task screens clean. The label event comes from the app, not
 * you, so dispatch (owner-only) does not fire; the next scheduled run picks it up. Capped per repo per day.
 */
export async function POST(req: Request) {
  if (!(await currentSession())) return new Response("unauthorized", { status: 401 });
  if (!sameOriginJson(req)) return new Response("bad origin", { status: 403 });
  const b = (await req.json().catch(() => null)) as (TaskInput & { repo?: string }) | null;
  if (!b || typeof b.goal !== "string" || !Array.isArray(b.acceptance) || !b.acceptance.every((x) => typeof x === "string"))
    return new Response("bad request", { status: 400 });
  const repo = b.repo ?? "";
  if (!/^[\w.-]+\/[\w.-]+$/.test(repo)) return new Response("bad repo", { status: 400 });

  const task: TaskInput = { goal: b.goal, acceptance: b.acceptance, scope: Array.isArray(b.scope) ? b.scope.filter((s) => typeof s === "string") : [] };
  const s = screen(task);
  if (!s.ok) return Response.json({ created: false, problems: s.problems }, { status: 422 });

  const rows = (await (await sb(`projects?repo=eq.${encodeURIComponent(repo)}&select=org_id,enabled,mode,paused`)).json()) as any[];
  if (rows.length !== 1) return new Response("unknown project", { status: 404 });
  if (!rows[0].enabled || rows[0].mode === "dormant") return Response.json({ created: false, problems: ["project is not enabled"] }, { status: 409 });

  const since = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
  const recent = (await (await sb(`audit?action=eq.task.create&detail->>repo=eq.${encodeURIComponent(repo)}&at=gte.${since}&select=id`)).json()) as any[];
  if (Array.isArray(recent) && recent.length >= MAX_PER_DAY) return Response.json({ created: false, problems: [`daily limit of ${MAX_PER_DAY} app tasks reached`] }, { status: 429 });

  try {
    const jwt = appJwt(process.env.GITHUB_APP_ID!, process.env.GITHUB_APP_PRIVATE_KEY!);
    const tok = await installationToken(jwt, await repoInstallationId(jwt, repo), repo, { issues: "write" });
    const res = await fetch(`https://api.github.com/repos/${repo}/issues`, {
      method: "POST",
      headers: { Authorization: `Bearer ${tok}`, Accept: "application/vnd.github+json", "User-Agent": "autopilot-control" },
      body: JSON.stringify({ title: issueTitle(task.goal), body: issueBody(task), labels: ["agent-ready", "from-app"] }),
    });
    if (!res.ok) return Response.json({ created: false, problems: [`GitHub refused (${res.status})`] }, { status: 502 });
    const issue = (await res.json()) as { number: number; html_url: string };
    await sb("audit", { method: "POST", body: JSON.stringify({ org_id: rows[0].org_id, actor: OWNER_UUID, action: "task.create", detail: { repo, issue: issue.number } }) });
    return Response.json({ created: true, number: issue.number, url: issue.html_url, paused: !!rows[0].paused });
  } catch (e) {
    return Response.json({ created: false, problems: [String((e as Error).message)] }, { status: 502 });
  }
}
