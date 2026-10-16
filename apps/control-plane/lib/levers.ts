/**
 * Turns a requested lever change into a plan. Safe changes become repo variables (agents cannot write those);
 * anything that loosens a guardrail becomes a PR the owner must merge; unknown or forbidden keys are rejected.
 * The database can therefore never be the path that weakens safety.
 */
export interface Levers {
  enabled: boolean;
  paused: boolean;
  priority: number; // 0-10
  greediness: number; // 0-3
  max_open_prs: number; // 0-10
  hold_until: string | null;
}

export type Role = "owner" | "maintainer" | "contributor" | "viewer";

export interface Plan {
  variables: Record<string, string>; // GitHub repo variables to set
  pr: { key: string; from: unknown; to: unknown; why: string }[]; // guardrail changes: open a PR for the owner
  rejected: { key: string; why: string }[];
}

export const FLOOR_MAX_OPEN_PRS = 3;
const KNOWN = new Set<keyof Levers>(["enabled", "paused", "priority", "greediness", "max_open_prs", "hold_until"]);
const FORBIDDEN = ["auto_merge_classes", "protected_paths", "protected_extra", "comms", "guard"];

export function planChange(cur: Levers, req: Record<string, unknown>, role: Role, canChangeLevers: boolean): Plan {
  const plan: Plan = { variables: {}, pr: [], rejected: [] };
  const reject = (key: string, why: string) => plan.rejected.push({ key, why });
  if (role === "viewer" || !canChangeLevers) {
    for (const k of Object.keys(req)) reject(k, "no permission to change levers");
    return plan;
  }
  for (const [key, to] of Object.entries(req)) {
    if (FORBIDDEN.includes(key)) {
      if (role === "owner") plan.pr.push({ key, from: undefined, to, why: "guardrail: changes only via a PR you merge" });
      else reject(key, "guardrail: owner only, via PR");
      continue;
    }
    if (!KNOWN.has(key as keyof Levers)) {
      reject(key, "unknown lever");
      continue;
    }
    const k = key as keyof Levers;
    switch (k) {
      case "enabled":
        if (typeof to !== "boolean") reject(k, "must be boolean");
        else if (to && !cur.enabled && role !== "owner") reject(k, "only the owner can start a project spending");
        else plan.variables.AUTOPILOT_ENABLED = String(to);
        break;
      case "paused":
        if (typeof to !== "boolean") reject(k, "must be boolean");
        else plan.variables.AUTOPILOT_PAUSED = String(to); // pausing is always allowed; unpausing needs change_levers (checked above)
        break;
      case "priority":
      case "greediness":
      case "max_open_prs": {
        const max = k === "priority" ? 10 : k === "greediness" ? 3 : 10;
        if (!Number.isInteger(to) || (to as number) < 0 || (to as number) > max) reject(k, `integer 0-${max}`);
        else if (k === "max_open_prs" && (to as number) > FLOOR_MAX_OPEN_PRS)
          plan.pr.push({ key: k, from: cur[k], to, why: `above the floor of ${FLOOR_MAX_OPEN_PRS} open agent PRs` });
        else plan.variables[`AUTOPILOT_${k.toUpperCase()}`] = String(to);
        break;
      }
      case "hold_until":
        if (to !== null && (typeof to !== "string" || Number.isNaN(Date.parse(to)))) reject(k, "ISO date or null");
        else plan.variables.AUTOPILOT_HOLD_UNTIL = to === null ? "" : String(to);
        break;
    }
  }
  return plan;
}
