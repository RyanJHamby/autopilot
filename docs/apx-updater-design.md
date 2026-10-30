# apx safe updater (O2): design for review, no code yet

**Status:** proposal for Ryan. Nothing here is built. Ryan decides whether to build it.

## Problem

After every merge to autopilot `main`, the host keeps running the old code until someone runs `sudo git pull` in Terminal.app. That is a manual step per merge, and the host drifts when it is forgotten (the status `version` label is how we notice).

## The security fact that shapes everything

The host code is the executor. Whoever can change what the host runs controls the App key holder, the Claude token holder and the merge lane. So "auto-update from main" means **"anyone who can land code on main controls apx"**. The updater must therefore be stricter than "git pull", not looser, and it must never be a path for the agent, a PR author, or apx's own merge lane to change apx.

## Proposal

apx updates itself only to a commit that Ryan merged himself, after the checks he requires, and it can undo the update by itself.

### Layout (replaces the in-place checkout)

```
/Users/Shared/apx/releases/<sha>/     one read-only checkout per release
/Users/Shared/apx/current  ->  releases/<sha>     symlink; launchd runs python from here
/Users/Shared/apx/previous ->  releases/<old sha>
```

The updater is a separate tiny script (stdlib only, ~100 lines) that lives **outside** the releases and is itself updated only by the manual `sudo` path. Changing the updater is the one thing that still needs Ryan at a terminal. Deliberate: nothing can update the thing that decides what to trust.

### An update happens only if ALL of these hold (checked via the GitHub API with the apx token, not by trusting the git objects)

1. The candidate is `origin/main`'s head and is a **fast-forward** of `current` (no force-push or rewrite is ever adopted).
2. The commit is the merge of a PR whose `merged_by` is the owner (`RyanJHamby`). Merges by apx's own lane, by a bot, or by anyone else are ignored.
3. GitHub marks the commit **Verified** (web-flow signature).
4. The required checks on that sha are green: `guard / guard` and `build` posted by the apx App (the same `integration_id` pin the rulesets use).
5. The PR is not labelled `hold`, and the file `/Users/Shared/apx/HOLD` does not exist (Ryan's local stop switch).
6. A **settling delay** (default 15 min) has passed since the merge, so a merge Ryan regrets can be stopped with `touch HOLD` before the host runs it.
7. The release checkout builds: `python -m compileall`, `pytest -q` as `apx-ci` (no secrets) on the new tree. A red suite means no swap.

If any condition fails, apx keeps running the current release and writes one line to status ("update to abc1234 skipped: <reason>"). A skip is not a problem state; a failed swap is.

### Swap and rollback

- Swap = write `previous`, then atomically replace `current` (`rename` over the symlink), then let launchd restart the daemon on its next 120 s tick.
- **Canary:** after a swap the updater watches the next 3 passes. If status shows `crashed`, `planner error` or `config error`, or no pass finishes within 15 min, it flips `current` back to `previous`, writes `HOLD`, and the status watcher raises a local notification. It does not retry the same sha.
- Keep the last 3 releases, delete older ones.

### What it deliberately does not do

- No update when a run is in flight (it takes the same pass lock, then swaps between passes).
- No update of `apx.env`, plists, accounts, or the updater. Those stay manual (`sudo`, Terminal.app).
- No network beyond GitHub, no notifications beyond the local macOS one. Same no-outbound rule as the rest of apx.
- Never applies to a repo's PRs; it only reads `RyanJHamby/autopilot` main.

## Failure modes and the answer to each

| Failure | Result |
|---|---|
| Ryan's account or a merge-bypass is abused to land bad code | Same exposure as today (manual pull would also run it); the 15 min delay and `HOLD` add a window. Not solved, only narrowed. |
| apx's own merge lane merges to autopilot main | Rule 2 ignores it. (apx is shadow-only on autopilot today; this keeps it safe if that changes.) |
| Force-push or history rewrite on main | Rule 1 refuses. |
| New release crashes at import | Canary rolls back within about 3 passes. |
| New release runs but is subtly wrong (bad planner decision) | Not caught. Mitigation is the existing main-health check and the shadow cross-check, plus `HOLD`. |
| GitHub API down | No update, no harm. |
| Updater bug | Worst case it does nothing or swaps to a verified sha; the updater is small, stdlib-only and mutation-tested, and replaced only manually. |

## Build plan if approved (3 small PRs, each mutation-tested)

1. `verify` module: pure function from API payloads to `(ok, reason)` for rules 1 to 6, with a table of cases (merged_by someone else, unsigned, red check, non-FF, hold, too soon).
2. Release layout + swap + canary rollback, tested against a temp dir and fake launchd.
3. One-time host setup doc (manual `sudo`, Terminal.app, one short line each) and a drill: merge a trivial PR, watch the swap; merge a deliberately crashing one on a scratch branch, watch the rollback.

## Decisions for Ryan

1. Is "merged by Ryan + Verified + green checks + 15 min delay" the right trust bar, or do you want a longer delay or an explicit `ship` label per release?
2. OK that changes to the updater itself stay manual?
3. Build now, or wait until the Oracle host exists (the same layout would carry over; nothing here is Mac-specific)?

## Not verified

Everything above is design. I have not checked that a symlink swap plus launchd restart behaves as described on this Mac, or that the Verified flag is exposed on the commits API for a web-flow merge in every case.
