import { verifySignature, toRunRow, toApxRunRow } from "../../../../lib/ledger";
import { maybeTriage } from "../../../../lib/triage-run";

export const runtime = "nodejs";

/** GitHub webhook receiver. Verifies the HMAC, maps agent-exec completions to ledger rows, stores via Supabase REST. */
export async function POST(req: Request) {
  const raw = await req.text();
  const event = req.headers.get("x-github-event") ?? "";
  // apx (owner-run executor) reports with its own secret; everything else is a GitHub webhook with GitHub's
  const secret = event === "apx_run" ? process.env.APX_WEBHOOK_SECRET : process.env.GITHUB_WEBHOOK_SECRET;
  if (!verifySignature(secret ?? "", raw, req.headers.get("x-hub-signature-256"))) {
    return new Response("bad signature", { status: 401 });
  }
  let body: any;
  try {
    body = JSON.parse(raw);
  } catch {
    return new Response("bad json", { status: 400 });
  }
  const row = event === "apx_run" ? toApxRunRow(body) : toRunRow(event, body);
  if (!row) return new Response("ignored", { status: 202 });

  // Failed agent run: let triage look for a repeated infrastructure cause (off unless AUTO_TRIAGE=true; never breaks the ledger)
  if (row.outcome === "failure" && row.runner !== "apx") {
    try {
      await maybeTriage(row.repo, { fetch, env: process.env, now: new Date() });
    } catch {
      /* triage is best effort */
    }
  }

  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) return new Response("ledger store not configured", { status: 501 });

  // project_id is resolved server-side from the repo; unknown repos are dropped, never auto-created
  const proj = await fetch(`${url}/rest/v1/projects?repo=eq.${encodeURIComponent(row.repo)}&select=id`, {
    headers: { apikey: key, Authorization: `Bearer ${key}` },
  }).then((r) => r.json());
  if (!Array.isArray(proj) || proj.length !== 1) return new Response("unknown project", { status: 202 });

  const { repo: _repo, ...rest } = row;
  const res = await fetch(`${url}/rest/v1/runs`, {
    method: "POST",
    headers: { apikey: key, Authorization: `Bearer ${key}`, "Content-Type": "application/json", Prefer: "return=minimal" },
    body: JSON.stringify({ ...rest, project_id: proj[0].id }),
  });
  return new Response(res.ok ? "stored" : "store failed", { status: res.ok ? 200 : 502 });
}
