import { describe, expect, it } from "vitest";
import { classify, dedupeKey, issueBody, issueTitle, repeatedCauses, sanitizeLog, type FailedRun } from "./triage";

const NOW = new Date("2026-10-17T12:00:00Z");
const run = (o: Partial<FailedRun> = {}): FailedRun => ({
  id: 1, conclusion: "failure", failedStep: "Install deps", title: "agent #5", url: "https://github.com/o/r/actions/runs/1", createdAt: "2026-10-16T10:00:00Z", ...o,
});

describe("classify", () => {
  it("maps failures to runner/kit causes", () => {
    expect(classify(run())).toBe("infra:install-deps");
    expect(classify(run({ conclusion: "timed_out" }))).toBe("timeout");
    expect(classify(run({ failedStep: "Run anthropics/claude-code-action@x" }))).toBe("agent-error");
    expect(classify(run({ failedStep: "" }))).toBe("failed-unknown");
    expect(classify(run({ conclusion: "success" }))).toBeNull();
    expect(classify(run({ conclusion: "cancelled" }))).toBeNull();
  });
});

describe("repeatedCauses", () => {
  it("needs the same cause at least twice inside the window", () => {
    expect(repeatedCauses([run()], NOW)).toEqual([]);
    const two = repeatedCauses([run({ id: 1 }), run({ id: 2 })], NOW);
    expect(two).toHaveLength(1);
    expect(two[0].cause).toBe("infra:install-deps");
    expect(repeatedCauses([run({ id: 1, createdAt: "2026-09-01T00:00:00Z" }), run({ id: 2 })], NOW)).toEqual([]);
  });
  it("keeps different causes apart", () => {
    const rs = [run({ id: 1 }), run({ id: 2, failedStep: "Other" }), run({ id: 3 }), run({ id: 4, failedStep: "Other" })];
    expect(repeatedCauses(rs, NOW).map((c) => c.cause).sort()).toEqual(["infra:install-deps", "infra:other"]);
  });
});

describe("issue text", () => {
  it("has a stable dedupe key in the title", () => {
    expect(issueTitle("o/r", "timeout", 3)).toContain(dedupeKey("o/r", "timeout"));
  });
  it("sanitizes logs: control characters, secrets, fences, size", () => {
    const gh = "gh" + "p_" + "abcdefghijklmnop1234";
    const dirty = `\x1b[31mred\x1b[0m line\u0000\nAuthorization: Bearer abcdef123456\nkey ${gh}\n\`\`\`injected\`\`\`\n` + "x".repeat(9000);
    const out = sanitizeLog(dirty);
    expect(out).not.toMatch(/\x1b|\u0000/);
    expect(out).not.toContain(gh);
    expect(out).not.toContain("abcdef123456");
    expect(out).not.toContain("```");
    expect(out.length).toBeLessThanOrEqual(6000);
  });
  it("keeps only the last lines", () => {
    const text = Array.from({ length: 200 }, (_, i) => `line ${i}`).join("\n");
    const out = sanitizeLog(text, 60);
    expect(out).toContain("line 199");
    expect(out).not.toContain("line 10\n");
  });
  it("marks the log as untrusted and lists runs", () => {
    const b = issueBody("o/r", "timeout", [run({ id: 7 })], "tail");
    expect(b).toContain("UNTRUSTED");
    expect(b).toContain("[7](");
    expect(b).toContain("for the owner");
  });
});
