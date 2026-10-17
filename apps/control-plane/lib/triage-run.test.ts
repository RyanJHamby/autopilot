import { generateKeyPairSync } from "node:crypto";
import { describe, expect, it } from "vitest";
import { maybeTriage } from "./triage-run";

const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048, privateKeyEncoding: { type: "pkcs8", format: "pem" }, publicKeyEncoding: { type: "spki", format: "pem" } });
const NOW = new Date("2026-10-17T12:00:00Z");
const ENV = { AUTO_TRIAGE: "true", TRIAGE_KIT_REPO: "me/autopilot", GITHUB_APP_ID: "1", GITHUB_APP_PRIVATE_KEY: privateKey };

function mk(over: { openIssues?: any[]; recent?: any[]; failures?: number } = {}) {
  const calls: { url: string; method: string; body?: any }[] = [];
  const failures = over.failures ?? 2;
  const f = (async (url: string, init: RequestInit = {}) => {
    const method = init.method ?? "GET";
    calls.push({ url, method, body: init.body ? JSON.parse(String(init.body)) : undefined });
    const json = (x: any, status = 200) => new Response(JSON.stringify(x), { status });
    if (url.endsWith("/installation")) return json({ id: 5 });
    if (url.includes("/access_tokens")) return json({ token: "t" }, 201);
    if (url.includes("/actions/workflows/agent-exec.yml/runs"))
      return json({ workflow_runs: Array.from({ length: failures }, (_, i) => ({ id: 100 + i, conclusion: "failure", display_title: "agent #5", html_url: `https://github.com/me/r/actions/runs/${100 + i}`, created_at: "2026-10-16T10:00:00Z" })) });
    if (/\/actions\/runs\/\d+\/jobs/.test(url)) return json({ jobs: [{ id: 900, steps: [{ name: "Install deps", conclusion: "failure" }] }] });
    if (url.endsWith("/jobs/900/logs")) return new Response("boom: command not found", { status: 200 });
    if (url.includes("labels=kit-fix&state=open")) return json(over.openIssues ?? []);
    if (url.includes("labels=from-triage")) return json(over.recent ?? []);
    if (url.endsWith("/issues") && method === "POST") return json({ html_url: "https://github.com/me/autopilot/issues/9" }, 201);
    return json({}, 404);
  }) as unknown as typeof fetch;
  return { f, calls };
}
const run = (env: any, m = mk()) => maybeTriage("me/r", { fetch: m.f, env, now: NOW }).then((r) => ({ r, calls: m.calls }));

describe("maybeTriage", () => {
  it("does nothing unless explicitly switched on", async () => {
    const { r, calls } = await run({ ...ENV, AUTO_TRIAGE: "false" });
    expect(r.skipped).toMatch(/off/);
    expect(calls).toHaveLength(0);
  });
  it("files one labelled issue when the same infra cause repeated", async () => {
    const { r, calls } = await run(ENV);
    expect(r.filed).toEqual(["https://github.com/me/autopilot/issues/9"]);
    const post = calls.find((c) => c.method === "POST" && c.url.endsWith("/me/autopilot/issues"))!;
    expect(post.body.labels).toEqual(["kit-fix", "from-triage"]);
    expect(post.body.title).toContain("[triage:me/r:infra:install-deps]");
    expect(post.body.body).toContain("UNTRUSTED");
  });
  it("waits for a repeat", async () => {
    expect((await run(ENV, mk({ failures: 1 }))).r.skipped).toMatch(/no repeated cause/);
  });
  it("does not duplicate an open issue for the same cause", async () => {
    const m = mk({ openIssues: [{ title: "[triage:me/r:infra:install-deps] 2 agent runs failed" }] });
    const { r, calls } = await run(ENV, m);
    expect(r.filed).toEqual([]);
    expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/issues"))).toBe(false);
  });
  it("opens at most one triage issue per 24 hours", async () => {
    const { r } = await run(ENV, mk({ recent: [{ number: 3 }] }));
    expect(r.skipped).toMatch(/last 24h/);
  });
  it("refuses a malformed kit repo or missing app config", async () => {
    expect((await run({ ...ENV, TRIAGE_KIT_REPO: "bad repo; x" })).r.skipped).toMatch(/bad repo/);
    expect((await run({ ...ENV, GITHUB_APP_ID: undefined })).r.skipped).toMatch(/not configured/);
  });
});
