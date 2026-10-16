import { createHmac } from "node:crypto";
import { describe, expect, it } from "vitest";
import { toRunRow, verifySignature } from "./ledger";

const sign = (s: string, b: string) => "sha256=" + createHmac("sha256", s).update(b).digest("hex");
const ev = (over: object = {}, name = "agent-exec") => ({
  action: "completed",
  repository: { full_name: "me/stencil" },
  workflow_run: { name, display_title: "agent #38 ", conclusion: "success", run_started_at: "2026-10-16T22:00:00Z", ...over },
});

describe("verifySignature", () => {
  it("accepts a correct signature and rejects everything else", () => {
    expect(verifySignature("s3cret", "{}", sign("s3cret", "{}"))).toBe(true);
    expect(verifySignature("s3cret", "{}", sign("other", "{}"))).toBe(false);
    expect(verifySignature("s3cret", "{ }", sign("s3cret", "{}"))).toBe(false);
    expect(verifySignature("s3cret", "{}", null)).toBe(false);
    expect(verifySignature("s3cret", "{}", "sha256=zz")).toBe(false);
    expect(verifySignature("", "{}", sign("", "{}"))).toBe(false); // an unset secret never validates
  });
});

describe("toRunRow", () => {
  it("maps a completed agent-exec run", () => {
    expect(toRunRow("workflow_run", ev())).toMatchObject({ repo: "me/stencil", issue: 38, model: "sonnet", run_points: 75, outcome: "success" });
  });
  it("hard runs are opus and cost more points", () => {
    expect(toRunRow("workflow_run", ev({ display_title: "agent #5 [hard]" }))).toMatchObject({ model: "opus", run_points: 450 });
  });
  it("skipped and cancelled cost nothing", () => {
    expect(toRunRow("workflow_run", ev({ conclusion: "skipped" }))?.run_points).toBe(0);
    expect(toRunRow("workflow_run", ev({ conclusion: "cancelled" }))?.run_points).toBe(0);
  });
  it("ignores other workflows, events and in-progress runs", () => {
    expect(toRunRow("workflow_run", ev({}, "ci"))).toBeNull();
    expect(toRunRow("push", ev())).toBeNull();
    expect(toRunRow("workflow_run", { ...ev(), action: "requested" })).toBeNull();
  });
  it("failures are recorded as failure", () => {
    expect(toRunRow("workflow_run", ev({ conclusion: "timed_out" }))?.outcome).toBe("failure");
  });
});
