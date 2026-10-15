# autopilot

Async agent system for my GitHub repos: standards, spend controls, model/effort routing, phone steering,
and a spec "handshake", with hard guardrails against any outbound or admin action.

## How it works
```
 you (phone) ── label / @claude / edit specs ──► GitHub
   agent-dispatch.yml  (zero tokens: enabled? paused? caps? breaker? pick issue; owner-only)
        └─► agent-exec.yml (the only job that spends Claude usage; model/effort/turn cap chosen by the gate)
              └─► agent/<issue>-* branch ─► PR ─► CI + `guard` (deterministic) ─► you merge (merge commit only)
```
- Runtime is **GitHub Actions** with `anthropics/claude-code-action`, billed to the Max subscription via
  `CLAUDE_CODE_OAUTH_TOKEN`. Not claude.ai routines: those attach every claude.ai connector (Gmail, Calendar,
  Todoist, Asana) by default and use them without asking.
- Budget state is read from GitHub (recent `agent-exec.yml` runs, open `agent/*` PRs), not from a file an agent could edit.

## Layout
| path | purpose |
|---|---|
| `policy/CONSTITUTION.md` | the iron rules, copied into every repo |
| `policy/deny.json` | `.claude/settings.json` deny rules (mcp, secrets, publishing, force-push, gh api, ...) |
| `policy/portfolio.yaml` | repo → tier/mode, budgets, excluded repos |
| `kit/runtime/` | `guard.py`, `handshake.py`, `gate.py`: stdlib + PyYAML, tested, copied to `.autopilot/` |
| `kit/repo/` | workflows, CODEOWNERS, templates written by `ap init` |
| `kit/agents/` | role definitions (drop a file to add a role) |
| `src/autopilot/cli.py` | `ap` |

## Commands
```
./install.sh                          # installs `ap`
ap init ~/dev/<repo> [--dry-run]      # scaffold on branch autopilot/init; never pushes
ap handshake specs/foo.md             # ACCEPTED / NEEDS-WORK / REJECTED + what the system will do
ap doctor ~/dev/<repo>...             # audit files, SHA pins, ruleset, secret
ap status                             # runs (24h) and agent PRs per repo
ap ruleset <repo> [--apply]           # branch ruleset: PR + code owners + signed + merge-commit only + guard
ap enable|pause|resume [repo] [--apply]   # repo variables; dry run unless --apply
```
All commands that change GitHub are dry-run by default.

## Guardrails (defense in depth)
Constitution forbids contacting people, calendars/inboxes/task managers, social/publishing, secrets, spend,
protected paths. Enforced by: no connectors in the Action runtime; `.claude/settings.json` deny rules; minimal
job permissions + owner-only triggers; a `guard` required check (secrets, messaging/social/mail SDKs and URLs,
protected paths, test weakening, size) run from the base branch copy; branch ruleset; CODEOWNERS.

## Setup checklist (per repo, done by hand)
1. `claude setup-token` once; `gh secret set CLAUDE_CODE_OAUTH_TOKEN -R RyanJHamby/<repo>`.
2. Install the Claude GitHub App on the repo.
3. Merge the `autopilot/init` PR, then `ap ruleset <repo> --check ci --apply`, then `ap enable <repo> --apply`.
4. Audit claude.ai connectors; remove all from any routine, toggle off for cloud sessions on these repos.

## Pilot results (drillpad-workspace, 2026-10-15)
- V1 PROVEN: agent run opened a PR from `agent/8-<run>` whose commit is Verified (`claude[bot]`, signed via the action's `github_file_ops`).
- V2 PARTIAL: `--model sonnet --effort medium` accepted; compound shell commands denied by the allowlist. The deny list was not exercised by a model that tried to comply (see below).
- V3 PROVEN: `guard` and `test` fire on the agent's PR.
- V4 PROVEN: `gh workflow run` from the dispatch job works.
- Red team round 1 (email, print .env, edit workflow, Slack post, delete tests): all five refused by the **constitution layer** (the model), no files changed, no PR. This does NOT yet show the deterministic layers (deny rules, guard, ruleset) stop a model that complies. Round 2 must apply pressure.
- Real-run bugs found and fixed, in order: exec skipped for bot actor; gate counted skipped runs; action rejects bot actor; blanket `mcp__*` deny blocked the signed-commit tool; signed commits targeted `main` (fixed by `CLAUDE_BRANCH`).

## Not built yet
Triage/fixer/reviewer/auditor workflows (role files exist), the `autopilot-hq` daily digest, `ap upgrade` as a PR.

## How this was built

Design, experiments, and analysis are mine. I used AI coding assistants for
parts of the implementation, tests, and documentation, and reviewed every change.
The [engineering journal](docs/journal.md) records decisions and dead ends as
they happened, and [`results/`](results/) holds the raw output behind every
number quoted here.
