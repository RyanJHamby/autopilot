import { describe, expect, it } from "vitest";
import { planChange, type Levers } from "./levers";

const cur: Levers = { enabled: true, paused: false, priority: 5, greediness: 1, max_open_prs: 3, hold_until: null };

describe("planChange", () => {
  it("safe levers become repo variables", () => {
    const p = planChange(cur, { priority: 8, greediness: 2, paused: true, hold_until: "2026-10-16T21:00:00Z" }, "owner", true);
    expect(p.variables).toEqual({
      AUTOPILOT_PRIORITY: "8",
      AUTOPILOT_GREEDINESS: "2",
      AUTOPILOT_PAUSED: "true",
      AUTOPILOT_HOLD_UNTIL: "2026-10-16T21:00:00Z",
    });
    expect(p.pr).toEqual([]);
  });

  it("guardrail keys never become variables: owner gets a PR, others are rejected", () => {
    const o = planChange(cur, { auto_merge_classes: ["docs-only"] }, "owner", true);
    expect(o.variables).toEqual({});
    expect(o.pr).toHaveLength(1);
    const m = planChange(cur, { protected_paths: [] }, "maintainer", true);
    expect(m.pr).toEqual([]);
    expect(m.rejected[0].key).toBe("protected_paths");
  });

  it("raising max_open_prs above the floor needs a PR", () => {
    expect(planChange(cur, { max_open_prs: 5 }, "owner", true).pr).toHaveLength(1);
    expect(planChange(cur, { max_open_prs: 2 }, "owner", true).variables.AUTOPILOT_MAX_OPEN_PRS).toBe("2");
  });

  it("bounds and types are enforced", () => {
    const p = planChange(cur, { priority: 11, greediness: 1.5, enabled: "yes", hold_until: "soon", mystery: 1 }, "owner", true);
    expect(p.variables).toEqual({});
    expect(p.rejected.map((r) => r.key).sort()).toEqual(["enabled", "greediness", "hold_until", "mystery", "priority"]);
  });

  it("only the owner can start a disabled project", () => {
    const off = { ...cur, enabled: false };
    expect(planChange(off, { enabled: true }, "maintainer", true).rejected).toHaveLength(1);
    expect(planChange(off, { enabled: true }, "owner", true).variables.AUTOPILOT_ENABLED).toBe("true");
  });

  it("no permission means nothing applies", () => {
    expect(planChange(cur, { priority: 1 }, "contributor", false).variables).toEqual({});
    expect(planChange(cur, { priority: 1 }, "viewer", true).rejected).toHaveLength(1);
  });
});
