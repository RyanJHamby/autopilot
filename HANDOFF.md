# Handoff: autopilot

- Branch: `main` (continue from `wip/main`; base commit `a5951fe`)
- Instructions: read this file, continue the work, commit in small steps, push a new branch and open a PR. Never push to `main`.
- Generated from the local session transcript without a model call; it may be incomplete.

## Goal (first prompt of the session)



<pasted_content id="4dba">
We're mothballing Zonevex (pausing, not killing). Goal: full revivability.
Deadline: everything committed before Nov 16 (I start at Hume).
Follow my proof-of-work conventions: small signed commits, a `pow log`
entry for the decision, accurate README AI disclosure. NOTHING destructive:
don't delete services, buckets, data or DNS, and don't cancel anything.
I'll do that separately after the backups are verified.

1. Decision record
   - Write docs/DECISION-2026-11-sunset.md covering: what Zonevex did, what I
     found (well-funded competitors/incumbents; HyperQ covering both the
     developer and RTO sides), the pivots I considered and why I passed
     (unclear distribution, unclear ROI), and revisit triggers (a buyer need
     incumbents won't serve, inbound with a budget or pilot, an interconnection
     rule change that opens a wedge, a distribution channel I can reach).
     Ask me for anything you can't infer from the repo.
   - Add a matching `pow log` entry.

2. Backups (store OUTSIDE the repo at ~/Archive/zonevex/<date>/; never commit
   dumps or secrets)
   - Railway: use the railway CLI to `pg_dump -Fc` every Postgres DB. Also
     back up any other datastores you find (Redis, volumes).
   - Verify each dump: restore it into a throwaway local Postgres (docker) and
     compare table row counts against prod. Report the results.
   - R2: rclone sync every bucket; verify object counts and total bytes match.
   - Env vars: list the variable NAMES per service/environment in
     docs/REVIVAL.md. Don't print or write the values; I'll copy them into my
     password manager myself.
   - Encrypt the archive folder (age or gpg; ask me which key) and checksum it.

3. Revival memo: docs/REVIVAL.md
   - Architecture overview; every external service (Railway, R2, Loops,
     domain/DNS, Google Workspace, G2/Capterra, anything else in the code or
     config) and what each one is used for
   - Exact steps to redeploy from scratch, plus where the backups live
   - A dated snapshot of the competitor landscape (link the decision doc)

4. Static "paused" site

## Diff summary (`git diff --stat`, base to wip, HANDOFF.md excluded)

```
 .githooks/_chain-global                            |  35 ++
 .githooks/commit-msg                               |   6 +
 .githooks/pre-commit                               |   6 +
 .githooks/pre-merge-commit                         |   6 +
 .githooks/pre-push                                 |   3 +
 .github/workflows/ci.yml                           |   8 +-
 .github/workflows/kit-proposer.yml                 |   4 +-
 .github/workflows/release.yml                      |   6 +-
 .../launchd/com.autopilot.standard.converge.plist  |   6 +-
 docs/apx-freeze.md                                 |  30 ++
 docs/journal.md                                    |  28 ++
 docs/standard-converge.md                          |   8 +-
 kit/repo/AGENTS.block.md                           |   2 +-
 policy/claude.yaml                                 |   5 +
 policy/portfolio.yaml                              |  14 +
 policy/time.yaml                                   |  13 +
 pyproject.toml                                     |   2 +-
 scratch-check                                      |   1 +
 src/autopilot/apx/agent_job.py                     |   6 +
 src/autopilot/apx/caps.py                          |  51 +++
 src/autopilot/apx/claude_runner.py                 |  76 +++-
 src/autopilot/apx/daemon.py                        |  70 ++-
 src/autopilot/apx/doctor.py                        |   6 +
 src/autopilot/apx/executor.py                      |  27 +-
 src/autopilot/apx/freeze_gate.py                   |  76 ++++
 src/autopilot/apx/ledger.py                        |  19 +-
 src/autopilot/apx/planner.py                       |  10 +-
 src/autopilot/apx/update_main.py                   |   7 +-
 src/autopilot/apx/window.py                        |   5 +-
 src/autopilot/claude_floor.py                      |  98 ++++
 src/autopilot/cli.py                               |   6 +
 src/autopilot/converge/command.py                  |  30 +-
 src/autopilot/freeze.py                            | 179 ++++++++
 src/autopilot/launch.py                            |   6 +-
 tests/conftest.py                                  |  11 +
 tests/test_apx_agent.py                            |   1 +
 tests/test_apx_claude_runner.py                    |   2 +-
 tests/test_apx_daemon.py                           |   5 +-
 tests/test_apx_doctor.py                           |  50 ++-
 tests/test_apx_freeze_gate.py                      | 496 +++++++++++++++++++++
 tests/test_apx_run_caps.py                         | 426 ++++++++++++++++++
 tests/test_claude_floor.py                         | 202 +++++++++
 tests/test_converge.py                             |   7 +-
 tests/test_converge_freeze.py                      | 277 ++++++++++++
 tests/test_doctor.py                               |  56 ++-
 tests/test_freeze.py                               | 292 ++++++++++++
 tests/test_githooks_chain.py                       | 220 +++++++++
 tests/test_launch.py                               |  22 +
 uv.lock                                            |  50 +--
 49 files changed, 2888 insertions(+), 84 deletions(-)
```

## Last 20 exchanges

### Claude

I'll look at the live homepage to see what's actually there.

### Claude

The diff is what I intended. I'm rebuilding the site to check how the homepage renders.

### Claude

Three of the four homepage issues are fixed in PR #47: https://github.com/RyanJHamby/RyanJHamby.github.io/pull/47. Merging it updates the live homepage. I haven't merged it. Merge it with `gh pr merge 47 --merge -R RyanJHamby/RyanJHamby.github.io`.

**What the PR changes:**
- **Open PR under "Merged upstream."** I renamed the section to "Upstream contributions", because it already listed the open vLLM NIXL PR, so the old heading was inaccurate. The items now run newest merged first (Aug 3, Jul 23, Jul 16), with the open one last and labelled "Not merged yet".
- **Zonevex.** It now appears under Selected work, marked PAUSED, with a link to the postmortem. It has no numbers and no claims beyond what the post supports: what it checked, that it was paused in November 2026, and what the post co

### User

open the merge

### Claude

PR #47 should now be open in your browser. Check the diff, then click **Merge pull request** (use a merge commit, not a squash). Or, from a terminal:

```
gh pr merge 47 --merge -R RyanJHamby/RyanJHamby.github.io
```

The site redeploys in a minute or two after the merge. Tell me when it's merged, and I'll check the live homepage.

If you also want #46 (the journal entry) merged, that's still waiting too.

### User

merge conflcit here https://github.com/RyanJHamby/RyanJHamby.github.io/pull/46

### Claude

A conflict on #46 is expected, because both it and #47 append entries at the end of `docs/journal.md`. I'm checking what changed on `main`, then resolving it by keeping both entries.

### Claude

The permission settings rejected that as one compound command, so I'm running the steps separately, starting with the read-only ones.

### Claude

#47 is merged, so the homepage changes are on `main`. That's what conflicts with #46: both added entries at the end of the journal. Now I'm merging `main` into the #46 branch.

### Claude

The replacement PR is up. I'm closing the conflicted one so there aren't two.

### Claude

The conflict is resolved, and nothing was lost. #47 had added its own entry at the end of the journal, which collided with #46's. Instead of merging `main` into the old branch, I rebuilt the same entry on a fresh branch from the current `main`.

- **New PR #48:** https://github.com/RyanJHamby/RyanJHamby.github.io/pull/48. It has the same single journal entry about the Substack cross-post, and it's docs only. Merge it with `gh pr merge 48 --merge -R RyanJHamby/RyanJHamby.github.io`.
- **Old PR #46:** closed, with a comment pointing to #48. Nothing was lost, because its entry now lives in #48.

I didn't use `git merge` because your permission settings block it. The fresh-branch route needed no merge, and it avoids rewriting any history.

**Your homepage changes are live in `main`.** #47 is m

### User

i think thats all here

### Claude

I'll do one last check of the state of things before I call it done.

### Claude

Almost everything is done. Here is the closing state, including the few things that aren't.

**Verified done:**
- **Zonevex repo.** All docs, scripts and the paused page are merged to `main`, with signed commits.
- **Archive.** `~/Archive/zonevex/` holds the encrypted archive, its checksum and your key. The plaintext copy is deleted, and you restored the archive once yourself.
- **Railway.** Both services have 0 active deployments, and the repo is disconnected.
- **Zonevex post.** It's live on `ryanjhamby.dev`, cross-posted to Substack, and `zonevex.com` serves the paused page linking to it.
- **Homepage.** It's live with the "Upstream contributions" heading and Zonevex under Selected work.

**Not done:**
1. **PR #48** (the journal entry) isn't merged. It's docs only: `gh pr merge 48 --mer

### User

go

### Claude

I'm taking "go" to mean the one thing I offered that needs no input from you: finding out why FlowState is `draft = true`. This is read-only.

### Claude

That answers it. The post wasn't left in draft by accident: you withdrew it on 2026-10-30. I'm reading the exact reason, and checking that nothing else on your site still makes the withdrawn claim.

### Claude

FlowState being `draft = true` is **intentional**, not a bug. Nothing needs fixing there.

**What happened:** you withdrew the post on 2026-10-30, in commit `167b0fb`, "withdraw the FlowState post pending a fair-comparison rerun". Your journal gives the reasons:
- the benchmark harness hadn't shown equal work between the engines
- the wrapper's overhead was inside the timed region
- it ran on a laptop only

The post's changelog records the withdrawal. Its 17 claims are unverified in `claims.yaml`, and `build_post.py --publish` would refuse them, so it can't go live by accident. That matches the earlier Zonevex gate.

**Is anything else on your site making the withdrawn claim?** No. The only speed claim I found elsewhere is on the stock-screener page, which is about a different project. You

### User

This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion of the conversation.

<system-reminder>
<tools-used-before-summary>AskUserQuestion, Bash, Edit, Monitor, Read, Skill, ToolSearch, WebFetch, Write</tools-used-before-summary>
</system-reminder>
Summary:
1. Primary Request and Intent:
   - Original: mothball Zonevex (pause, not kill) with full revivability before Nov 16: decision record (`docs/DECISION-2026-11-sunset.md`) + `pow log`; backups outside the repo (`~/Archive/zonevex/<date>/`, never commit dumps/secrets) with verification; env var NAMES only in `docs/REVIVAL.md`; revival memo with architecture/services/redeploy steps/competitor snapshot; static paused site (`/paused-site`) deployed preview-only withou

### User

sudo -u apx-ci -H bash -c 'cd /home/apx-ci/work && rm -rf dbg && git clone -q --depth 1 -b agent/linux-host-swap-note https://github.com/RyanJHamby/autopilot dbg && cd dbg && export PATH=$HOME/.local/bin:/usr/bin:/bin && uv sync --quiet && uv run pytest -q -p no:cacheprovider -rf 2>&1 | grep -E "^FAILED|^ERROR|passed|failed" | tail -30'

