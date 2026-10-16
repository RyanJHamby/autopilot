# autopilot: engineering journal

Dated notes on what I tried, what happened, and why I made each call, including
the dead ends. Entries are appended with `pow log` and `pow run`, so dates match
commit history. Raw outputs for any number quoted in the README live in
[`results/`](../results/).

## 2026-10-13 23:02 EDT (at 8b2614b)

Chose GitHub Actions (not claude.ai routines) as primary runtime: routines attach all claude.ai connectors (Gmail, Calendar, Todoist, Asana) by default and use them unprompted, which violates the no-outbound-action rule. Gate counts agent-exec.yml runs from GitHub itself instead of a committed ledger so an agent cannot forge its own budget.

## 2026-10-14 09:02 EDT (at be75af1)

Built ap CLI + repo templates. Found ~/dev/drillpad is the drillpad-workspace repo, so ap resolves repo identity from the git remote, not the directory. Open verification items V1-V4 listed in README; the pilot must settle them before wave 1.

## 2026-10-15 08:05 EDT (at e673090)

gate counted skipped/cancelled agent-exec runs toward the daily cap; smoke issue #8 was blocked at 2/2 with zero real runs. Fixed to exclude them; failures still count (conservative).

## 2026-10-15 08:24 EDT (at 4b7cc82)

smoke #8 first real run: action rejected github-actions actor (needs allowed_bots), then model call died in 2s with is_error and no usage, message hidden by show_full_output=false. Added AUTOPILOT_DEBUG var switch.

## 2026-10-15 10:33 EDT (at 0381f97)

First real agent run on #8: token ok after clipboard mixups (secret held command text); agent obeyed constitution and commented needs-human instead of forcing it. Blocker: mcp__* deny blocked github_file_ops (the signed-commit path). Fix: allow commit_files, specific mcp deny families, no plain git commit. Log shows only github_file_ops MCP exists in the runtime - no connectors.

## 2026-10-15 18:35 EDT (at 1de0ecd)

2nd real run: signed-commit tool allowed but 422 (targets main, ruleset rejects). Cause: dispatch has no entity context so action uses checked-out branch. Fix: trusted step creates agent/<issue>-<run_id>, agent cannot branch, empty branch cleaned up.

## 2026-10-15 18:52 EDT (at 39b310c)

PR13 wasn't enough: file_ops uses CLAUDE_BRANCH||GITHUB_REF_NAME (src/modes/agent/index.ts @pinned SHA), not the checked-out branch. Pinned CLAUDE_BRANCH. Cleanup via API since action revokes git creds. Also wasted one run by firing before PR13 merged: check merge state first.

## 2026-10-15 19:01 EDT (at 7becf79)

Pilot: V1,V3,V4 proven; red team round 1: all 5 hostile issues refused by constitution layer only. Deterministic layers untested under a complying model; round 2 needs pressure prompts.

## 2026-10-15 19:15 EDT (at 1e533b6)

Red team round 2 + deny isolation: model refused 5/6; slack_sdk module PR failed guard comms rule (layer 4 held); in a constitution-free clone .github edit, .env read, curl, force-push were all denied by settings (layer 2 held). Removed redundant Write() denies; added push retry after a GitHub 500.

## 2026-10-15 19:18 EDT (at 0830829)

Found 4/5 wave-1 repos are public; portfolio 'public' flag was unused. Added exec step that locks the issue when event.repository.private==false, plus owner-only-comments instruction.

## 2026-10-15 19:20 EDT (at 1523d27)

Onboarding order-book-engine (public, no CI, nested CMake): ap init only saw root markers and ignored repo.yaml commands; fixed both. Added ci.yml (verified build+52 tests locally). Empty tracked .pem in history: size 0 in every commit, no key blocks, no AWS key ids.

## 2026-10-16 08:53 EDT (at 09355a7)

Onboarding stencil (Next.js/Supabase/Vercel/Stripe/web-push, existing AGENTS.md+CLAUDE.md+workflows). Found eval-vision.yml spends OPENAI_API_KEY on every PR and runs PR code with secrets: agent PRs could read/spend it. Added detector (init warn, doctor fail), SUBPROCESS_ENV_SCRUB=1 default, dropped npx.

## 2026-10-16 08:55 EDT (at fef15e0)

ap init clobbered stencil's PR template and CODEOWNERS catch-all. Now: existing non-autopilot files are left alone; CODEOWNERS gets a managed block merged into it.

## 2026-10-16 10:07 EDT (at f457e10)

ap scan: read-only repo triage (fresh->B, warm->C dormant; forks, archived, stale, excluded skipped; public flagged; tier A never suggested). First slice of v2 P1.

## 2026-10-16 10:15 EDT (at fb189b3)

Shared kit (v2 P1): reusable workflow_call workflows + thin callers pinned by sha, runtime/config.py reads repo.yaml for node/allowed tools, ap init --kit, ap kit-export with a leak check. Decision: kit repo is PUBLIC (private scripts can't be fetched by other repos without an App token). Reusable-workflow job checks report as 'guard / guard', so ap ruleset --central. NOT yet validated live: vars context inside called workflows, the pinned-sha fetch, and the check name.

## 2026-10-16 10:19 EDT (at 3243a5f)

Central kit validated on private sandbox repo (RyanJHamby/autopilot-sandbox): guard / guard and handshake pass; dispatch fired exec; exec ran through branch creation and cleanup, failed only at 'Claude Code is not installed' (expected, App not on sandbox). vars context, pinned-sha fetch, config outputs and the check name all work in called workflows. Kit published public at RyanJHamby/autopilot-kit @ 1ac281b (noreply author email). Sandbox AUTOPILOT_ENABLED set back to false.

## 2026-10-16 10:25 EDT (at b8c78d5)

ap add / ap set edit policy/portfolio.yaml line-by-line (keeps comments); validated by re-parse; stencil recorded as A/standard/enabled to match the scaffold PR. Local-only, no GitHub effects.

## 2026-10-16 10:32 EDT (at fd8b43d)

ap ruleset --apply now PUTs an existing autopilot-main instead of POSTing a duplicate. drillpad-workspace migrated to the shared kit (PR #29); guard / guard passes; ruleset now requires guard / guard + test.

## 2026-10-16 10:38 EDT (at 879df4b)

P2 start: kit/runtime/tier.py, a deterministic PR risk classifier (tier 2 protected paths, tier 0 only for owner-enabled classes: docs-only, tests-add-only, lockfile-patch (patch bumps only), generated). auto_merge_classes ships empty. Not yet wired into a workflow or the kit sha; formatter-only deliberately omitted (needs a tool run, not a diff read).

## 2026-10-16 10:39 EDT (at 3a0d592)

Tier wired in informationally: guard workflow now runs tier.py from the base branch's merge-policy.yaml (template ships empty via ap init) and writes the result to the job summary. Nothing merges on it yet; the merge App and per-class demotion are next.

## 2026-10-16 10:41 EDT (at d7c383b)

demote.py: stateless per-class circuit breaker for tier-0 auto-merge (revert or red main within 30d demotes only that class; owner re-adding the class in merge-policy clears it). Pure logic; the merger will feed it from GitHub history.

## 2026-10-16 10:42 EDT (at 9ce5bed)

automerge.py + reusable automerge.yml + caller: merges PRs only if agent/* or dependabot, all checks green, tier.py=0 for an owner-enabled class not demoted (history derived from automerged:<class> labels, revert titles, check-runs on the merge sha). Ships inert (empty merge-policy). Workflow runs on default-branch copy and only diffs PR content. Not yet live-tested.

## 2026-10-16 10:52 EDT (at 75740ba)

ap pick: work-conserving allocation of the global daily run pool across enabled repos by priority (tier default A8/B5/C2), capacity = min(agent-ready issues, runs left under the repo gate), owner reserve, portfolio hold_until pause (stencil held to 21:00Z). Wave-1 repos Ryan put on hold are now enabled:false in the portfolio so nothing reads or dispatches them.

## 2026-10-16 10:56 EDT (at 1ee1f27)

control-plane scaffold (apps/control-plane): Next 16 PWA, read-only Portfolio page from ap export-state snapshot; status/rank/share logic unit-tested (vitest); builds and serves. Not deployable yet: no auth, snapshot names private repos.

## 2026-10-16 10:59 EDT (at 38aa305)

control-plane schema (supabase/migrations/0001_core.sql): orgs/members/projects/grants/runs/audit with RLS and can(project, action); validated in pglite (outsider sees nothing, grant-gated lever updates with CHECK bounds, no self-grant, owner-only append-only audit, no column can loosen a guardrail). GitHub App manifest drafted (no contents write, no workflows/admin/secrets); not registered.

## 2026-10-16 11:06 EDT (at 3edb21f)

Lever write path (control-plane lib/levers.ts): requested change -> plan. Safe levers become repo variables, guardrail keys (auto_merge_classes, protected paths, comms) never do (owner gets a PR plan, others rejected), max_open_prs above the floor of 3 needs a PR, only owner can start a project, bounds/types enforced. Gate now honors AUTOPILOT_HOLD_UNTIL (owner pause, fails to the hold). Kit not republished yet.

## 2026-10-16 11:09 EDT (at 247423f)

Run ledger ingestion (control-plane): HMAC-verified GitHub webhook -> agent-exec completions -> runs rows (service role, project resolved server-side, unknown repos dropped). run_points is an upper-bound estimate (turn cap x model weight) since the Max pool reports no tokens. Not deployed; needs SUPABASE_* and GITHUB_WEBHOOK_SECRET.
