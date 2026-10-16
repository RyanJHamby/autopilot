import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Repo, State, Tier } from "./portfolio";

interface Row {
  repo: string;
  tier: Tier;
  mode: Repo["mode"];
  enabled: boolean;
  priority: number;
  hold_until: string | null;
  is_public: boolean;
  paused: boolean;
}

export function fromRows(rows: Row[], owner: string, now: Date): State {
  return {
    generated_at: now.toISOString(),
    owner,
    global_runs_per_day: 12,
    repos: rows.map((r) => ({
      name: r.repo.split("/").pop() ?? r.repo,
      tier: r.tier,
      mode: r.mode,
      enabled: r.enabled,
      priority: r.priority,
      hold_until: r.hold_until,
      public: r.is_public,
      paused: r.paused,
    })),
  };
}

const EMPTY = (): State => ({ generated_at: new Date().toISOString(), owner: "(no data)", global_runs_per_day: 0, repos: [] });

/** Database first (deployed), local snapshot second (dev), empty last. Server-side only: uses the service role key. */
export async function loadState(): Promise<State> {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (url && key) {
    try {
      const res = await fetch(`${url}/rest/v1/projects?select=repo,tier,mode,enabled,priority,hold_until,is_public,paused`, {
        headers: { apikey: key, Authorization: `Bearer ${key}` },
        cache: "no-store",
      });
      if (res.ok) return fromRows((await res.json()) as Row[], "RyanJHamby", new Date());
    } catch {
      /* fall through */
    }
  }
  try {
    return JSON.parse(readFileSync(join(process.cwd(), "data", "state.json"), "utf8")) as State;
  } catch {
    return EMPTY();
  }
}
