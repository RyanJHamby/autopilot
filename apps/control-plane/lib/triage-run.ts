import { appJwt, installationToken, repoInstallationId } from "./githubApp";
import { dedupeKey, issueBody, issueTitle, repeatedCauses, type FailedRun } from "./triage";

export interface TriageDeps {
  fetch: typeof fetch;
  env: Record<string, string | undefined>;
  now: Date;
}

export interface TriageResult {
  filed: string[];
  skipped: string;
}

const REPO_RE = /^[\w.-]+\/[\w.-]+$/;
const gh = (token: string) => ({ Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "User-Agent": "autopilot-control" });

/**
 * Called when an agent-exec run FAILS. If the same infrastructure-class cause has now repeated, opens ONE `kit-fix` issue on
 * the kit-source repo (labels kit-fix + from-triage) unless one is already open for that cause or any triage issue was
 * opened in the last 24h. Off unless AUTO_TRIAGE=true. Every failure path returns quietly: triage must never break the
 * ledger webhook.
 */
export async function maybeTriage(repo: string, d: TriageDeps): Promise<TriageResult> {
  const kitRepo = d.env.TRIAGE_KIT_REPO ?? "";
  if (d.env.AUTO_TRIAGE !== "true") return { filed: [], skipped: "AUTO_TRIAGE is off" };
  if (!REPO_RE.test(repo) || !REPO_RE.test(kitRepo)) return { filed: [], skipped: "bad repo configuration" };
  const appId = d.env.GITHUB_APP_ID;
  const pem = d.env.GITHUB_APP_PRIVATE_KEY;
  if (!appId || !pem) return { filed: [], skipped: "GitHub App is not configured" };
  const f = d.fetch;
  const jwt = appJwt(appId, pem, Math.floor(d.now.getTime() / 1000));

  const src = await installationToken(jwt, await repoInstallationId(jwt, repo, f), repo, { actions: "read" }, f);
  const runsRes = await f(`https://api.github.com/repos/${repo}/actions/workflows/agent-exec.yml/runs?per_page=30`, { headers: gh(src) });
  if (!runsRes.ok) return { filed: [], skipped: `could not list runs (${runsRes.status})` };
  const failed: FailedRun[] = [];
  let newestJob: number | null = null;
  for (const r of ((await runsRes.json()) as any).workflow_runs ?? []) {
    if (!["failure", "timed_out"].includes(r.conclusion) || failed.length >= 10) continue;
    const jobs = (await (await f(`https://api.github.com/repos/${repo}/actions/runs/${r.id}/jobs`, { headers: gh(src) })).json()) as any;
    let step = "";
    for (const j of jobs.jobs ?? []) {
      const s = (j.steps ?? []).find((x: any) => x.conclusion === "failure");
      if (s) {
        step = s.name;
        if (failed.length === 0) newestJob = j.id;
      }
    }
    failed.push({ id: r.id, conclusion: r.conclusion, failedStep: step, title: r.display_title ?? "", url: r.html_url, createdAt: r.created_at });
  }
  const causes = repeatedCauses(failed, d.now);
  if (!causes.length) return { filed: [], skipped: "no repeated cause yet" };

  const kit = await installationToken(jwt, await repoInstallationId(jwt, kitRepo, f), kitRepo, { issues: "write" }, f);
  const open = (await (await f(`https://api.github.com/repos/${kitRepo}/issues?labels=kit-fix&state=open&per_page=50`, { headers: gh(kit) })).json()) as any[];
  const since = new Date(d.now.getTime() - 86400_000).toISOString();
  const recent = (await (await f(`https://api.github.com/repos/${kitRepo}/issues?labels=from-triage&state=all&since=${since}&per_page=10`, { headers: gh(kit) })).json()) as any[];
  if (Array.isArray(recent) && recent.length >= 1) return { filed: [], skipped: "a triage issue was already opened in the last 24h" };

  const filed: string[] = [];
  for (const c of causes) {
    if (Array.isArray(open) && open.some((i) => String(i.title).includes(dedupeKey(repo, c.cause)))) continue;
    let tail = "";
    if (newestJob) {
      const lr = await f(`https://api.github.com/repos/${repo}/actions/jobs/${newestJob}/logs`, { headers: gh(src) });
      if (lr.ok) tail = await lr.text();
    }
    const res = await f(`https://api.github.com/repos/${kitRepo}/issues`, {
      method: "POST",
      headers: gh(kit),
      body: JSON.stringify({ title: issueTitle(repo, c.cause, c.runs.length), body: issueBody(repo, c.cause, c.runs, tail), labels: ["kit-fix", "from-triage"] }),
    });
    if (res.ok) filed.push(String(((await res.json()) as any).html_url));
    break; // at most one issue per failure event
  }
  return { filed, skipped: filed.length ? "" : "an open kit-fix issue already covers it" };
}
