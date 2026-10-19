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

## 2026-10-16 11:23 EDT (at 74b2447)

LIVE FINDING: first automerge attempt on drillpad-workspace PR #33 crashed: 'gh pr view --json statusCheckRollup' fails with the workflow token (GraphQL status scopes). Ryan then merged it by hand, so the merge path is not yet proven. Fix: automerge.py is REST-only (pulls, commits/<sha>/check-runs, issues labels, PUT pulls/N/merge with sha pin), labels before merge, gh stderr surfaced.

## 2026-10-16 11:25 EDT (at 243fb72)

control-plane auth: GitHub OAuth (identity scope only) with numeric-id allowlist, HMAC session cookie, proxy.ts default-deny + page re-check; smoke-tested live locally (no cookie 307, forged cookie 307, valid 200, API 401, unsigned webhook 401, unconfigured login 503). Inbox triage lib (protected-path PRs first, oldest first). 30 vitest tests.

## 2026-10-16 11:33 EDT (at 73747be)

Supabase project autopilot-control created (ref tubzfpzqcyhwkkenygpu, us-east-1, separate from stencil's). DB password is random, stored only in macOS keychain item autopilot-control-db, never printed. Migrations 0001-0003 applied; security advisors clean after moving can()/is_owner() to a private schema and revoking anon grants; anon REST reads/inserts/RPC all denied (probed live). Service-role and other keys not yet placed anywhere.

## 2026-10-16 11:45 EDT (at 68a2d94)

Deployed control plane to Vercel (project autopilot-control, https://autopilot-control.vercel.app). Env (encrypted, never printed): SESSION_SECRET, ALLOWED_GITHUB_IDS=68158512, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY. Private portfolio snapshot no longer bundled (.vercelignore + runtime fallback). Probed live: / 307 to login, API 401, unsigned webhook 401, login 503 until the OAuth app exists, state.json not served. Needs GitHub OAuth client id/secret + webhook secret next.

## 2026-10-16 12:04 EDT (at 9dfb9de)

Portfolio now served from Supabase: migration 0004 (mode, is_public), 'ap export-state --sql' idempotent seed (12 projects, owner org), lib/store.ts reads projects with the service role server-side, falls back to local snapshot in dev. Owner sign-in verified by Ryan. Seed ran via supabase db query (stand-in owner uuid 00000000-...-68158512 until Supabase Auth).

## 2026-10-16 12:06 EDT (at 89a1068)

GitHub App helpers (control-plane lib/githubApp.ts): RS256 app JWT (9 min), repo-scoped installation tokens with minimal permissions, repo-variable upsert restricted to AUTOPILOT_* names. Unit-tested with a generated key; not yet used against a real App (not registered).

## 2026-10-16 12:10 EDT (at 7e7449a)

GitHub App 'autopilot-control' registered by Ryan (id 5347578). Private key stored in Vercel (sensitive) and the downloaded .pem deleted. Verified via app JWT: permissions exactly actions:read, actions_variables:write, checks:read, contents:read, issues:write, pull_requests:write (no workflows/admin/secrets); events issues/pull_request/workflow_run. No installation yet.

## 2026-10-16 12:21 EDT (at 1985610)

Webhook verified live: GitHub deliveries 401 until the secret was reset on both sides, then 202. Lever write path live: POST /api/levers (owner session + same-origin JSON) -> planChange -> app JWT -> repo-scoped installation token (actions_variables:write only) -> AUTOPILOT_* variable + DB + audit row; Pause/Resume/priority controls on the portfolio. Not yet exercised against drillpad-workspace by a signed-in click.

## 2026-10-16 12:33 EDT (at e3bd8b3)

Pause/Resume now give feedback: pressed state, in-flight label, saved/err flash; paused persisted (migration 0005) and shown as a 'paused' status. Found drillpad-workspace AUTOPILOT_PAUSED=true from Ryan's test click; DB synced to match, he must press Resume.

## 2026-10-16 12:35 EDT (at 52a0b71)

ap report: read-only outcome scorecard from GitHub PR history (opened/merged/closed/reverted, merge rate, median hours to merge, per auto-merge class) plus a deterministic promotion suggester (>=10 clean merges, 0 reverts, class not yet enabled -> propose to owner as a PR). First step of the self-improvement loop: measurement before any tuning. Skips dormant and held repos.

## 2026-10-16 12:39 EDT (at af7e820)

Safety zones: ap init now refuses clones that hold personal or secret material (.obsidian, journal/diary/medical/tax names, key files, .env; names only, contents never read) or live under never_paths (~/notes, Obsidian Vault, claude-docs vault, ~/.claude), and any repo marked data_class: restricted (also refused by enable/pick). Override only with --allow-sensitive.

## 2026-10-16 12:45 EDT (at d41ca3c)

Backlog: 5 agent-safe specs (report-cost, ap-digest, ap-upgrade, inbox-page, scorecard-ui) with runnable acceptance commands, all passing the handshake (ap-digest first rejected because it said 'vault'; reworded). BACKLOG.md splits agent-safe periphery from human-only guard-path work. The autopilot repo has no remote, no CI and no issues yet.

## 2026-10-16 12:48 EDT (at f5328e7)

Dogfooding prep: autopilot has a private remote (RyanJHamby/autopilot), CI (ruff, pytest, control-plane typecheck+tests; green), BACKLOG.md and five agent-safe specs. Scaffolded onto itself in central mode (PR #1, not enabled). New: guard.extra_protected now flows into CODEOWNERS and Edit-deny rules, so agents may improve reports/digests/UI/tests but never kit runtime, workflows, policy, auth/webhook/lever code, API routes or migrations. docs/journal.md tripped the sensitive-name check (false positive, overridden on purpose).
## 2026-10-16 patchcheck
patchcheck.py: the gate for the vendor-neutral commit path (P5). A runner only edits a worktree; a trusted job makes a patch that must pass this (no symlinks/submodules/mode or binary changes/renames, no path tricks or .git internals) plus all guard rules before a signed commit is created. Pure and tested; not wired to a workflow or runner yet.

## 2026-10-16 runner interface
runner.py: Runner protocol (untrusted; edits a worktree only) + trusted pipeline: git builds the patch against the BASE commit recorded before the run (so a runner that commits its own changes cannot hide them), patchcheck gates it, usage passes through when a runner reports tokens. Caught in my own test: diffing against HEAD would have missed a runner-made commit touching a protected path followed by an innocuous edit; fixed before merge. Stub-runner tests only; no real second runner yet.

## 2026-10-16 first run on the autopilot repo: two kit bugs
1. Claude Code 2.1.299 refuses to start with CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1 unless bubblewrap exists ("Failed to install Claude Code after 3 attempts"). The kit now installs bubblewrap (verified on the runner) rather than disabling the scrub. This would also have failed drillpad-workspace's nightly smoke run.
2. When the action's workflow validation fails (workflow differs from the default branch) it skips itself and the run still reports success, silently spending a daily budget slot. exec now fails if the step produced no execution file. Consequence: kit/caller changes can only be exercised after they merge to the default branch. Evidence the Claude GitHub App is installed on this repo: the OIDC token exchange succeeded.
## 2026-10-16 sensitive-name precision
First real use of the sensitive-material check on drillpad-workspace flagged interview lessons ('health-checker-circuit.py', '07-secrets-and-key-management.md') because it matched substrings. Now whole file stems only (journal, diary, secrets, credentials, key extensions, .env), so ordinary content passes and dated journals still match. A journal.md still trips it on purpose (dev journals must be a conscious --allow-sensitive).

## 2026-10-16 New task form
Phone-entered tasks: /new -> POST /api/tasks. A conservative screen (lib/task.ts: known runner commands only, safe characters, no comms/secrets/deploy/protected-path asks, size limits) decides whether the issue gets `agent-ready`; failures are rejected with reasons, never created half-ready. Issue is created through the GitHub App (issues:write only), so the label event comes from the app and owner-only dispatch does not fire; the next scheduled dispatch picks it up. 10 app-created tasks per repo per day (audit-counted). lib/task.ts is on the guard path. Deployed; first live use pending Ryan.

## 2026-10-16 second kit bug on the first real run: sandbox needs socat
After #6 the agent started but every Bash call failed: "Sandbox is required but failed to initialize: socat not installed". The agent refused to use dangerouslyDisableSandbox and reported the blocker (6 turns, ~$0.07 notional): the constitution layer behaved. Exec now installs bubblewrap, socat and ripgrep and self-checks. The run still reported success with no PR: a gap to close (a run that ends without a PR, a branch with commits, or an issue comment should be flagged). Kit f3402ce.

## 2026-10-16 third finding: the agent did the work but could not verify it
Run on main after the socat fix: 23 turns, ~$0.18 notional, the agent wrote the report-cost code and two tests, then stopped because `uv` was not on the runner (python3 -m pytest fallback not allowed). It committed nothing, commented the blocker on the issue and labeled needs-human: correct, conservative behavior. Gap was ours: a sandboxed agent cannot install tooling, so exec must prepare the stack before the model starts (node was already handled; uv now too, pinned 0.12.16, `uv sync --frozen`). Stacked PR #10 merged into the #9 branch instead of main (retargeting trap): superseded by #12, which includes #11. Lesson: stacked PRs need retargeting after the base merges, or just don't stack.

## 2026-10-16 goal-only task works; turn cap too tight
First spoken-style task (no acceptance): the agent wrote tests first, recorded them failing (ImportError) then passing, listed its assumptions, and opened a signed PR (#15, ap digest, 203 lines). The run was marked failed only because it used 27 turns against a cap of 25 (the action enforces the cap strictly even after success). Inferring tests costs turns, so the standard cap goes 25 -> 40 (hard 30 -> 45), mirrored in the ledger weights and ap report so the estimates stay consistent. Also fixed a fragile test (a runner-provided GITHUB_OUTPUT leaked into tier's e2e test; found by the agent in its sandbox run).

## 2026-10-16 release approval: one merge per kit release, not N+1
Problem: every kit fix needed a PR in the autopilot repo plus a pin-bump PR in every repo. Design: the owner approves a kit sha once, by merging a PR on `<owner>/autopilot-approved` (public, tiny, ruleset: PR + owner review; kept separate from the kit repo because the kit repo is pushed to constantly). `ap approve --kit OWNER/REPO@SHA` opens that PR; `ap rollout` opens signed pin-bump PRs in every enabled repo. A new auto-merge class `kit-bump` (opt-in per repo in merge-policy) lets a pin bump merge itself ONLY if: branch autopilot/kit-* by the repo owner, every changed line is a caller workflow line differing from its old line solely by a 40-hex sha (same repo, no new step or permission), the manifest only re-hashes workflow files, and every new sha is on APPROVED. It overrides the normal protected-path rule for that exact shape. Fails closed (unreachable list = no auto-merge). Limit worth stating: anything I do through Ryan's gh login is "Ryan" to GitHub, so I will not merge approval PRs; that is a behavioral rule, not a technical one.

## 2026-10-16 approval PR was unsigned
The first approval PR (autopilot-approved #1) could not merge: "Commits must have verified signatures". `ap approve` created it through the contents API, whose commit carried the user's email as committer and was unsigned. Fixed the PR by re-committing locally (signed) and force-pushing its branch; `ap approve` now clones, commits with -S and pushes. Also reworded the rollout refusal (it checks the approvals repo, not the kit repo).

## 2026-10-16 automerge's first real attempt failed: a GraphQL call survived my "REST-only" rewrite
drillpad-workspace #41 (agent PR, docs-only, all checks green) did not merge: every automerge run died on `gh pr view --json statusCheckRollup` ("Resource not accessible by integration"). My earlier fix replaced the call with a string substitution that silently did not match after ruff reformatted the code, and I never re-read the file. The tests covered decide() but not main(), so nothing caught it. Now: the call is REST check-runs, a test asserts the module contains no `gh pr view`/statusCheckRollup, and two end-to-end tests drive main() with a fake gh (green docs PR merges via PUT /merge with the head sha pinned and labels added first; a red check skips). Also history() bound its gh function at definition time (monkeypatch-blind); now bound at call time. Lesson: a silent no-op string replace is a bug; assert on the result.
## 2026-10-16 drillpad-workspace smoke: the agent ended its turn waiting on a background test run
Run 1 committed docs/AUTOPILOT.md (Verified) but opened no PR; the new "neither a PR nor a blocker" check correctly flagged it. Debug run 2: 17 turns, ~$0.13; the agent started `pytest -q` in the background (this repo's full suite takes ~6 min, longer than a foreground command may run), said "I'll open the PR once it finishes" and ended the session, which ends everything. Fix is instructional and structural: never end a turn with a command running; for slow suites run targeted tests, open the PR and leave the rest to CI. Also narrowed smoke issue #30's acceptance (no full pytest). Lesson: acceptance commands must be cheap, and the role must say what to do when they are not.

## 2026-10-16 ap preflight
`ap preflight REPO...`: read-only readiness check before leaving a repo unattended (secret, enabled/paused, ruleset incl. guard check + signatures + code-owner review, CODEOWNERS catch-all, kit pinned and owner-approved and current, last agent run result, billing-block heuristic (recent jobs failing in seconds), open agent PR cap, agent-ready queue, merge classes, restricted/public+debug). Pure evaluator + gatherer; exit 1 on any FAIL. Born from today's pattern of discovering missing prerequisites in the middle of a run (app not installed, spending limit, signatures). On first run: stencil, drillpad-workspace, autopilot all 0 FAIL.

## 2026-10-16 "runs when ready": chain the dispatch
Ryan's point: the system should run when there is work and capacity, not wait for a timer GitHub delays by hours (observed: the 05:37Z cron fired ~10:05Z). dispatch now also triggers when this repo's own agent-exec finishes (workflow_run) and on pushes to main (a merge changed open-PR capacity); the cron stays as a safety net. The gate is unchanged and is the only thing that decides: daily caps, open-PR cap, circuit breaker, holds, pause. gate.py now skips issues whose exec run is queued/in progress (their branch exists but no PR yet, so the open-PR check could not see them), which a chain of dispatches would otherwise double-start. Honest limit: this makes it continuous within its caps; with no human review the open-PR cap is what stops it, which is the intended brake. Self-improvement is still measure-only; the retro -> lessons PR loop is next, and lessons must land on a protected path reviewed by the owner (they are instructions to future agents, so an auto-merged lesson would be a prompt-injection channel).

## 2026-10-16 the lessons loop (first self-improvement step that acts)
Weekly `improve` workflow (kit): zero-token evidence from REST (failed agent-exec runs by failing step; agent PRs closed unmerged) -> causes seen >= 2 times -> a haiku run with Read and Write ONLY (no Bash, no commit tool, no network) writes <= 5 imperative bullets to a temp file -> a trusted step validates them (<= 1200 chars, <= 5 bullets of <= 220 chars; rejects URLs, code fences, "ignore the rules", anything that weakens a check/test/review/sandbox/guard, secrets, contacting people, unsafe flags) -> commits to a branch via the API and opens a PR to `.autopilot/lessons.md`, a protected path the owner must review. It never merges. exec/implementer now read lessons.md when present. Caught by tests before release: two step names with a colon made the workflow invalid YAML. Not yet run live; first live run will be a manual dispatch on the autopilot repo after the release. Risk accepted: lessons are model-written instructions derived partly from untrusted text (issue titles in the evidence); mitigation is narrow validation + owner review of every line.

## 2026-10-16 first chained runs: two findings, plus the lessons loop verified in parts
- First live improve run on autopilot: all steps green; evidence had only 2 `agent-error` causes (both the early install bugs, since fixed); the haiku run wrote nothing (2 turns, ~$0.003): no honest lesson, no PR. Correct. The commit path was verified separately on the sandbox: API commits made with the workflow GITHUB_TOKEN are Verified (author github-actions[bot], reason valid), so a lessons PR will satisfy the signed-commit ruleset.
- Stencil's chain fired by itself after the rollout merge (github-actions[bot], push to main) and re-ran #48 because the agent's first PR used `Refs #48` (the visual check remains) and left the issue agent-ready. The second run behaved well (read main, changed nothing, commented, added needs-human) but spent a run. Fix: the implementer role must use `Refs #N` and add needs-human when a PR does not fully resolve the issue.
- That run could not run vitest: EROFS writing the runner's step-summary file inside the sandbox (vitest's github-actions reporter). Fix: GITHUB_STEP_SUMMARY=/dev/null on the agent step.

## 2026-10-17 the proposer: the missing half of the self-improvement loop
Why the loop was not looping: every fix this week was made by hand because the problems were in the kit's workflows, prompts and scripts, which is the guard path, so repo agents are forbidden to edit it, and the weekly retro only writes advice. Added a kit-proposer: when the OWNER labels an issue `kit-fix`, a model with narrow edit rights (kit/, src/autopilot/, tests/, the journal; deny rules for .github, .claude, .autopilot, policy, apps auth/webhook/levers/ledger/task/api/migrations, CODEOWNERS) reproduces the failure, writes the smallest fix plus a failing-then-passing test, runs ruff and pytest in the foreground, and opens an autopilot/kit-fix-* PR with root cause and exact commands. It cannot merge or push (disallowed and denied), the repo's own settings are swapped for the narrow ones in the working tree only, and a trusted step re-lists the PR's files afterwards and closes it if anything outside the allowed paths changed. `ap kit-fix TITLE --run REPO:RUN_ID` files the issue with the redacted failed-step log tail, so failure -> fix PR is one command plus your review. Redaction bug caught by its own test: the word "Bearer" was treated as the secret and the real token survived; fixed (Bearer rule first). Not yet run live: the workflow must be on the default branch first (the action refuses workflows that differ), so the first real kit-fix issue comes after this merges. Still manual: nothing files kit-fix issues by itself yet; next step is for the weekly improve run to do it for infra-class causes.

## 2026-10-17 the proposer's own PR tripped the guard (two false positives)
guard failed on PR #34: (1) the proposer's settings file lists commands it denies (npm publish, twine...) and the guard's package-publishing pattern read them as a new publishing surface (the existing .claude/settings.json already has an exemption for the same reason; added one for this protected file only, with a test that other files are still flagged); (2) the redaction test contained a literal key-shaped string, which the secret scan flagged (the test now builds it at runtime). The guard doing its job on the loop's own code is the point of dogfooding it; the exemption is a kit change, so it takes effect in repos after the next release.

## 2026-10-17 second guard false positive: the repo discussing its own guard
PR #35 (the fix for the first false positives) failed guard again, for the same class of reason: its journal entry and its guard test named the very commands the guard forbids (publish commands). This repo writes and tests the guard, so the designed mechanism applies: `guard.comms_allow` in .autopilot/repo.yaml lists the three files that may name them (journal, test_guard, test_proposer). Narrow on purpose: it is path-scoped, owner-edited and protected, and the comms check still applies to everything else. Lesson recorded for the proposer loop: its own PRs are a good test of the guard, and merged-with-red-guard twice means the ruleset's required-check was bypassed by an admin merge; worth deciding whether that should stay possible.

## 2026-10-17 auto-triage: failures file their own kit-fix issues (off until switched on)
The proposer fixed #36 end to end, but a human still had to file the issue. Closing that: when the control plane's webhook sees an agent-exec run FAIL, `maybeTriage` (lib/triage-run.ts) lists the repo's recent failed runs, classifies each by failing step (same families as `ap retro`), and if the same infrastructure-class cause repeated (>= 2 in 7 days) opens ONE `kit-fix` + `from-triage` issue on the kit-source repo with run metadata and a sanitized, redacted, bounded log tail marked as untrusted. Brakes: off unless AUTO_TRIAGE=true; dedupe by a key in the title against open kit-fix issues; at most one triage issue per 24h; at most one issue per failure event; every failure path returns quietly so the ledger webhook is never affected. The kit-proposer now also accepts the control plane's bot (`autopilot-control[bot]`) but only on an issue labelled from-triage, and has its own cap of 2 proposer PRs per 24h. Net effect once switched on: failure -> issue -> fix PR with tests -> owner review/release, with no human step before the review. Switching on needs the GitHub App installed on the kit repo (issues:write there) and on the repos being watched (actions:read), then AUTO_TRIAGE=true and TRIAGE_KIT_REPO in Vercel. Typecheck caught a sloppy `expect(...) && expect(...)` in my own test.

## 2026-10-18 10:11 EDT (at 5190ddd)

charter + weekly audit: bounds (goals, non-goals, no new deps, weekly line budget, proposal/backlog caps) enforced by guard/gate/charter.py; model only writes JSON, trusted step files issues. stencil automerge fetch bug: private repo checkout has no credentials.

## 2026-10-18 22:35 EDT (at a7e9173)

ap release: planner (state->action) + thin executors reusing cmd_approve/cmd_rollout; tamper guard compares local kit/ to autopilot main via REST trees and the merged kit sha to the export tree; never calls merge. Decided resumability comes from re-deriving state from PRs each run (no local state file). Not run live with --apply.

## 2026-10-19 07:02 EDT (at a7e9173)

ap release: removed the agent's force-push of the release branch (constitution: never force-push); a re-run on an existing branch now fails closed. Found while reviewing: ap approve (cli.py ~1032) and the rollout/onboard pushes still use -f / --force-with-lease; left untouched, flagged in the PR.
