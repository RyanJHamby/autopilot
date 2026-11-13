# Handoff: autopilot

- Branch: `docs/fix-upgrade-wording` (continue from `wip/docs/fix-upgrade-wording`; base commit `f690c46`)
- Instructions: read this file, continue the work, commit in small steps, push a new branch and open a PR. Never push to `main`.
- Generated from the local session transcript without a model call; it may be incomplete.

## Goal (first prompt of the session)

/Users/ryanhamby/Downloads/Lean\ Ship\ Stack\ 100+\ Workflow\ \&\ Small-Company\ Setup\ Tips.md  implement these, and first check my repos to see what is done so far and what is actually worth it. i want a lot to be set up out of the box for any new repos (it should never get missed), and systems that ensure at certain gates (like starting to charge customers) other things trigger. i can retrofit to past repos later, but for now at least think about how to prioritize the new ones and have at least a decent plan to retrofit
i dont think you thought deeply enough about where the gaps are and what exactly are the best ways to phase thorugh it. do that and go deep on this
go into plan mode first. i dont think you thought this through
next
next
next
go
go
recommended
This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion of the conversation.

<system-reminder>
<tools-used-before-summary>Agent, AskUserQuestion, Bash, Edit, EnterPlanMode, ExitPlanMode, Read, ToolSearch, WebFetch, Write</tools-used-before-summary>
</system-reminder>
Summary:
1. Primary Request and Intent:
   - Original: "implement these [Lean Ship Stack 100+ tips, file ~/Downloads/Lean Ship Stack 100+ Workflow & Small-Company Setup Tips.md], and first check my repos to see what is done so far and what is actually worth it. i want a lot to be set up out of the box for any new repos (it should never get missed), and systems that ensure at certain gates (like starting to charge customers) other things trigger. i can retrofit to past repos later, but for now at least think about how to prioritize the new ones and have at least a decent plan to retrofit."
   - User pushed back twice for depth ("go deep", "go into plan mode first. i dont think you thought this through"); subsequent short approvals: "next", "go", "recommended".
   - Side question mid-turn: "and should we migrate to vps? my 2019 mac has sensistive info and pics on it. maybe we want a sandboxed vps altogether ?" → led to the approved host-move plan (move apx executor off the shared 2019 Mac to an isolated Linux VPS).
   - Current approved plan (file /Users/ryanhamby/.claude/plans/enchanted-stargazing-glade.md, "Move the apx executor off the shared Mac to an isolated Linux host"): P0 facts/Mac interim (owner-run), P1 portable Python (DONE), P2 Linux kit (IN PROGRESS), P3 provision+shadow (owner buys VPS), P4 cutover/retire Mac role, P5 later (per-job sandbox, capped API key, alert, hosted runners). Decisions: small paid x86 VPS; accounts + per-user nftables allowlist with DNS control; key-only SSH locked to owner IP; Mac interim = run four checks, pause if any fail. Docker/throwaway containers approved for local real-Linux verification.

2. Key Technical Concepts:
   - Autopilot repo (~/dev/autopilot, public, Python/uv, ruff line 130): `ap` CLI, project standard (`src/autopilot/standard/`: checks.yaml, engine.py, packs.yaml, capabilities.py), `since: YYYY-MM-DD` rule floor (grandfather older repos to warn; no-commit/non-repo = new; shallow clone = old unless `born_on`; `force_new` for revive), day-0 scaffold (`ap new`: .githooks/pre-commit linked into .git/hooks, Makefile setup/quick/check/audit/standard/standard-report, dependabot cooldown 7 days), capability packs (payments/llm/deploy; code/record/codeowners items; records self-attested, Verified date stale after 180 days), converge (audits GitHub default branch via shallow clone), burn-down history, `ap enable` revive gate, gates (`ap gate show/seed`, src/autopilot/gates/{__init__,core,command}.py + gates.yaml), pawl control repo (steps/artifacts JSON, `--root`, `--no-push`, explicit ids), apx executor (daemon, cilane, claude_runner, three accounts apx/apx-ci/apx-agent, sudo launcher, GitHub App key + Claude token, updater, fabric firewall package).
   - apx hostenv portability: `hostenv.is_darwin()` single switch (tests patch only this, never global sys.platform), `home_of` via pw

## Diff summary (`git diff --stat`, base to wip, HANDOFF.md excluded)

```
 apps/control-plane/app/globals.css                 |  16 +-
 docs/journal.md                                    |   4 +
 docs/permissions-log.md                            |   9 ++
 key.pub                                            |   1 +
 kit/repo/AGENTS.block.md                           |   2 +-
 policy/portfolio.yaml                              |   2 +-
 reports/Founder tech operating systems gaps.md     | 149 +++++++++++++++++++
 reports/Solo founder throughput stack 2026.md      |  80 ++++++++++
 .../agentic_workflow_portability.md                | 140 ++++++++++++++++++
 .../enforcement_and_enrollment.md                  | 164 +++++++++++++++++++++
 .../knowledge_and_decisions.md                     | 119 +++++++++++++++
 .../legal_and_ip.md                                | 126 ++++++++++++++++
 .../marketing_and_sales.md                         | 115 +++++++++++++++
 .../model_and_token_efficiency.md                  | 147 ++++++++++++++++++
 .../tool_and_stack_selection.md                    | 103 +++++++++++++
 .../agentic_dev_workflows.md                       | 133 +++++++++++++++++
 .../cadence_and_pitfalls.md                        | 124 ++++++++++++++++
 .../local_tooling.md                               | 101 +++++++++++++
 .../solo_saas_infra.md                             | 130 ++++++++++++++++
 .../validation_distribution_revenue.md             |  80 ++++++++++
 scratch-check                                      |   1 +
 spec-writer                                        |   1 +
 22 files changed, 1737 insertions(+), 10 deletions(-)
```

## Last 20 exchanges

### Claude

The signed commits, the push and the PR are running in the background. I'll report the PR link and the merge command when they finish.

### Claude

Admin PR #33 is open, and I opened it in your browser: https://github.com/RyanJHamby/admin/pull/33. The remote head `bc16a0f` matches mine. It's off current main with no conflicts, and BLOCKED is the usual `ci` check.

Merge #33:
```
! S=/private/tmp/claude-501/-Users-ryanhamby-dev-autopilot/e8b0deb5-052b-4248-a62c-0c747fff83da/scratchpad GO=1 REPO=RyanJHamby/admin PRS="33" bash /private/tmp/claude-501/-Users-ryanhamby-dev-autopilot/e8b0deb5-052b-4248-a62c-0c747fff83da/scratchpad/merge-pr.sh
```

**What it does (OQ-m-25).** Converge now asks the same freeze checker the git hooks use. Inside the window, or if the checker is unusable, it skips the fetch, pull and apply, records a skip that names the freeze, and does nothing else. The doctor, which only reads, still runs. No flag or variable 

### Claude

#33 is merged. I'll pull `~/dev/admin` with the overlap check, then confirm what the live copy now renders for the daily job, read-only.

### Claude

`~/dev/admin` is now at `ac3e388`, with your uncommitted `home_dir_gate.py` change untouched. The repo now renders the daily job at 19:07, but the job installed on your machine is still the old 09:07 one. `--check` exits 1, which confirms it.

**Reinstall it so the new time takes effect.** It's persistence on your machine, so it's yours to run:
```
! ~/dev/admin/scripts/install-doctor-job.sh --install
```
Then run `--check` on the same script and it should exit 0.

If you skip this, nothing breaks. The old 09:07 job still runs, but the converge it calls now skips inside the window, so on weekdays it would only pull at login outside the window. The reinstall is what makes the daily pull happen.

**Everything I own is merged and live.** The only things still waiting are on you:
1. **Before M

### Claude

The reinstall ran. I'll verify the installed job and see what the run it triggered at load did, read-only.

### Claude

The daily job is reinstalled and current: `--check` exits 0, the time is 19:07, and both jobs are loaded and healthy. The run it made at load shows two things you should know about.

**1. Converge can't pull while your live checkout has an uncommitted change.** It skipped with "tracked files have uncommitted changes". That's your edit to `guardrails/hooks/home_dir_gate.py` in `~/dev/admin`. It changes the home-directory hook from blocking a prompt to a one-time reminder. Because `~/dev/admin`'s working tree is the installed hooks, your edit is already live.
- Until that change is committed or discarded, the daily converge will skip every run and never auto-pull.
- The repo's own flow is a scratch clone and a PR, so I can deliver the exact diff that way and you merge it, which also makes th

### User

go

### Claude

I'm taking "go" as a yes to delivering your `home_dir_gate.py` change as a PR. I'll copy your exact diff into a scratch clone and leave your live copy alone. Before committing, I'll check whether any existing tests depend on the old blocking behavior.

### Claude

Now I know exactly what the hook does: it fails open on malformed input, stays silent outside `$HOME`, and reminds once per session. I'll write the tests first.

### Claude

The old-version check and the seven mutations are running in the background. Meanwhile I'll register the test and write the journal entry.

### Claude

All eight checks fail the way they should: the old blocking version and seven deliberate breaks. Now the full suite on the final tree.

### Claude

The full suite is running on the final tree. I'll commit, push and open the PR when it's green.

### Claude

The full suite passes: 735 ok, 0 FAIL, exit 0. Now the signed commits, the push and the PR.

### Claude

The signed commits, the push and the PR are running in the background. I'll report the PR link and the merge steps when they finish.

### Claude

Admin PR #34 is open, and I opened it in your browser: https://github.com/RyanJHamby/admin/pull/34. The remote head `ce1573d` matches mine. It's off current main with no conflicts, and BLOCKED is the usual `ci` check.

**What it is.** It's your own uncommitted edit to `guardrails/hooks/home_dir_gate.py`, copied byte for byte. It changes the hook from blocking a prompt in your home directory to a once-per-session reminder. I didn't decide whether that change is what you want. Say if you'd rather keep the blocking version.

**Why it matters now.** That edit was already live, because `~/dev/admin`'s working tree is the installed hooks. It was also making every daily converge run skip, so the daily pull never happened. Merging this and pulling makes that checkout clean again.

**What I added.*

### Claude

#34 is merged. As I said, your live checkout still has that same edit uncommitted, and pulling a commit that contains it can conflict. Before I touch anything, I'll check whether your working copy is byte-for-byte what just landed on `main`.

### Claude

Your `~/dev/admin` is clean and current at `1148f0f`, on `main`, tracking `origin/main`, with no stashes and no uncommitted files.

**What I did, exactly**
1. Compared your working copy of `home_dir_gate.py` to the version that just landed: byte-for-byte identical, and the only uncommitted file.
2. Stashed it (recoverable) and fast-forwarded.
3. Checked that the live hook equals the landed version and that the stash equals it too, then dropped the stash.

Nothing was lost: what I removed was a redundant copy of the change that's now on `main`.

**Live state after the pull**
- The identity gate and freeze gate both pass in a real repo.
- Both launch jobs, the daily doctor job and the freeze job, are current (`--check` exits 0).
- The daily converge can pull again, because the checkout is cl

### User

go

### Claude

I'll do a last health check on the two jobs, since that's the only thing left that I can verify.

### Claude

Both jobs are healthy. It's Friday 4:08 pm ET: the freeze job's log is empty (quiet), the resolver says "no freeze yet", and `~/dev/admin` is clean on `main`. The converge's last run, at 3:51 pm, is the skip from before the checkout was clean. Tonight's 19:07 run will be the first real pull, and I can check it tomorrow.

I have nothing more I can do on this thread without you. Everything I own is built, merged and live. What's left is yours:

1. **Before Monday 08:30 ET:** enable the agent-kit plugin with `/plugin`. It's the only freeze piece not in place.
2. **Monday ~08:35 ET:** ask me to check the freeze log. That's the first real test.
3. **Tomorrow or later:** ask me to run `ots upgrade` on both timestamps, and to check tonight's converge pull.
4. **Your own steps:**
   - Run the secr

