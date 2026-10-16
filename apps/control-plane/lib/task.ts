/**
 * Turns a phone-entered task into an issue body and decides whether it may be labelled `agent-ready`.
 * This is a first, conservative screen. The authoritative checks still run later: the agent's constitution, the gate,
 * and the guard. A task that fails the screen is rejected with reasons, never created half-ready.
 */
export interface TaskInput {
  goal: string;
  acceptance: string[]; // optional: empty means the agent proposes the tests (the owner reviews them first)
  scope?: string[];
}

export interface Screen {
  ok: boolean;
  problems: string[];
}

// Same families the kit handshake accepts as machine-checkable runners.
const RUNNERS = /^(pytest|uv|uvx|python3?|pip|ruff|mypy|pyright|npm|npx|pnpm|yarn|node|cargo|go|make|tsc|vitest|jest|bash \.\/scripts\/[\w./-]+)\b/;
const SAFE_CMD = /^[A-Za-z0-9._:/@=+ \-\[\]*"',]+$/;
const FORBIDDEN: [RegExp, string][] = [
  [/\b(send|post|publish|tweet|email|e-mail|dm|message|notify|ping|alert)\b.{0,40}\b(slack|email|linkedin|twitter|substack|discord|sms|customers?|users?|people|team)\b/i, "asks the agent to contact people or publish"],
  [/\b(calendar|inbox|gmail|linkedin|substack)\b/i, "touches calendars, inboxes or social accounts"],
  [/\b(print|cat|echo|dump|read|commit|upload|exfiltrate)\b.{0,40}(\.env|secrets?|api keys?|credentials|private keys?|tokens?)/i, "touches secrets"],
  [/\b(deploy|release|publish)\b.{0,20}\b(prod|production|npm|pypi)\b/i, "asks for a deploy or release"],
  [/\.github\/|\.autopilot\/|\.claude\/|AGENTS\.md|CLAUDE\.md/, "targets protected paths"],
];

export function screen(t: TaskInput): Screen {
  const problems: string[] = [];
  const goal = t.goal.trim();
  if (goal.length < 15) problems.push("goal is too short to be checkable");
  if (goal.length > 1500) problems.push("goal is too long; split it into smaller tasks");
  if (t.acceptance.length > 6) problems.push("at most 6 acceptance commands");
  for (const c of t.acceptance) {
    const cmd = c.trim();
    if (!SAFE_CMD.test(cmd) || cmd.length > 200) problems.push(`acceptance command has unsafe characters or is too long: ${cmd.slice(0, 40)}`);
    else if (!RUNNERS.test(cmd)) problems.push(`acceptance must start with a known runner (pytest, npm, uv, ...): ${cmd.slice(0, 40)}`);
  }
  const blob = [goal, ...t.acceptance, ...(t.scope ?? [])].join("\n");
  for (const [re, why] of FORBIDDEN) if (re.test(blob)) problems.push(why);
  for (const s of t.scope ?? []) if (!/^[\w./*-]+$/.test(s) || s.includes("..")) problems.push(`bad scope glob: ${s.slice(0, 40)}`);
  return { ok: problems.length === 0, problems };
}

export function issueTitle(goal: string): string {
  const first = goal.trim().split("\n")[0].replace(/\s+/g, " ");
  return first.length > 80 ? first.slice(0, 77) + "..." : first;
}

export const INFERRED_LABEL = "acceptance-inferred";

export function issueBody(t: TaskInput): string {
  const scope = t.scope?.length ? `\n## Scope\n${t.scope.map((s) => `- \`${s}\``).join("\n")}\n` : "";
  return [
    "## Goal",
    t.goal.trim(),
    "",
    ...(t.acceptance.length
      ? ["## Acceptance (commands that must exit 0)", ...t.acceptance.map((c) => `- [ ] \`${c.trim()}\``)]
      : ["## Acceptance", "_Not given. The agent infers tests that capture this goal, states its assumptions in the PR, and the owner reviews the tests first._"]),
    scope,
    "_Created from the autopilot app._",
  ].join("\n");
}
