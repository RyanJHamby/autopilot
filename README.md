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

## Verify in the pilot (not yet proven)
- V1 agent-mode run pushes `agent/*` branches with Verified commits (`use_commit_signing`, `branch_prefix`).
- V2 `--effort` is accepted by the action's CLI; `--allowedTools`/deny rules hold under a red-team issue.
- V3 `push` to `agent/**` fires `ci` and `guard` so required checks are satisfied for PRs opened with the workflow token.
- V4 `gh workflow run` from the dispatch job works with `actions: write` on `GITHUB_TOKEN`.

## Not built yet
Triage/fixer/reviewer/auditor workflows (role files exist), the `autopilot-hq` daily digest, `ap upgrade` as a PR.

## How this was built

Design, experiments, and analysis are mine. I used AI coding assistants for
parts of the implementation, tests, and documentation, and reviewed every change.
The [engineering journal](docs/journal.md) records decisions and dead ends as
they happened, and [`results/`](results/) holds the raw output behind every
number quoted here.
