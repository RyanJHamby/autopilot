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
