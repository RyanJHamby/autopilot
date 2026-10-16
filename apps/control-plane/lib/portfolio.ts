export type Tier = "A" | "B" | "C";

export interface Repo {
  name: string;
  tier: Tier;
  mode: "standard" | "yolo" | "dormant";
  enabled: boolean;
  priority: number;
  hold_until: string | null;
  public: boolean;
}

export interface State {
  generated_at: string;
  owner: string;
  global_runs_per_day: number;
  repos: Repo[];
}

export type Status = "active" | "held" | "paused-off" | "dormant";

/** What the owner should read at a glance. A hold beats everything: it is an explicit owner pause. */
export function status(r: Repo, now: Date): Status {
  if (r.hold_until && now < new Date(r.hold_until)) return "held";
  if (r.mode === "dormant") return "dormant";
  return r.enabled ? "active" : "paused-off";
}

/** Active repos first, then by priority desc, then name. */
export function ranked(repos: Repo[], now: Date): Repo[] {
  const rank: Record<Status, number> = { active: 0, held: 1, "paused-off": 2, dormant: 3 };
  return [...repos].sort(
    (a, b) =>
      rank[status(a, now)] - rank[status(b, now)] || b.priority - a.priority || a.name.localeCompare(b.name),
  );
}

/** Priority-weighted share of the daily pool among active repos (percent, 0 for inactive). */
export function share(r: Repo, repos: Repo[], now: Date): number {
  const act = repos.filter((x) => status(x, now) === "active");
  const total = act.reduce((s, x) => s + x.priority, 0);
  return status(r, now) === "active" && total > 0 ? Math.round((r.priority / total) * 100) : 0;
}
