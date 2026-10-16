import { createHmac, timingSafeEqual } from "node:crypto";

export interface RunRow {
  repo: string; // owner/name
  issue: number | null;
  runner: string;
  model: string;
  run_points: number;
  outcome: "success" | "failure" | "skipped" | "cancelled";
  started_at: string;
}

/** GitHub signs webhooks with HMAC-SHA256 over the raw body: `X-Hub-Signature-256: sha256=<hex>`. */
export function verifySignature(secret: string, rawBody: string, header: string | null): boolean {
  if (!secret || !header?.startsWith("sha256=")) return false;
  const want = createHmac("sha256", secret).update(rawBody).digest();
  let got: Buffer;
  try {
    got = Buffer.from(header.slice(7), "hex");
  } catch {
    return false;
  }
  return got.length === want.length && timingSafeEqual(got, want);
}

const WEIGHT: Record<string, number> = { haiku: 1, sonnet: 3, opus: 15 };

/**
 * Only completed `agent-exec` runs count. Run-points are an UPPER-BOUND estimate (turn cap x model weight) because the
 * Max pool exposes no token counts; the run title only tells us whether it was the opus "hard" run.
 */
export function toRunRow(event: string, payload: any): RunRow | null {
  if (event !== "workflow_run" || payload?.action !== "completed") return null;
  const r = payload.workflow_run;
  if (!r || !/^agent-exec/.test(r.name ?? "")) return null;
  const title: string = r.display_title ?? "";
  const hard = title.includes("[hard]");
  const model = hard ? "opus" : "sonnet";
  const turns = hard ? 45 : 40;
  const c = r.conclusion;
  const outcome = c === "success" ? "success" : c === "skipped" ? "skipped" : c === "cancelled" ? "cancelled" : "failure";
  const m = /#(\d+)/.exec(title);
  return {
    repo: payload.repository.full_name,
    issue: m ? Number(m[1]) : null,
    runner: "claude-code-action",
    model,
    run_points: outcome === "skipped" || outcome === "cancelled" ? 0 : turns * WEIGHT[model],
    outcome,
    started_at: r.run_started_at ?? r.created_at,
  };
}
