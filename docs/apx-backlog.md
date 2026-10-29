# apx backlog: path to "autopilot done"

Scoped 2026-10-29. Status key: `[x]` done, `[ ]` open. Owner: **me** (the agent session), **Ryan** (needs your account, password, GUI or admin
action). Size: S under half a day, M about a day, L several days or calendar-bound.

## Definition of done

All three repos run their full loop (PR checks, agent runs, rebases, merges) through apx on an **always-on, isolated host**, with
**zero Actions minutes**, **no path for PR code or a model to reach the App key or the Claude token**, **an alert to Ryan if apx stops**, and
**a clean week** of real traffic with no unexplained disagreement or incident. Ryan reviews only tier-1/2 PRs and decisions.

## Where we are (2026-10-29)

Proven live: checks on drillpad-workspace with zero Actions minutes (a PR went CLEAN on apx's checks alone); one real agent run end to end;
Verified App commits; the unprivileged `apx` Mac account; a healthy timer. **Not safe yet for unattended agents** (see Gate S).

## Gate S: security, blocks enabling agent runs (C1)

The finding: the App key and the Claude token are files owned by the same account that runs a PR's tests. Code in a PR (or a prompt-injected
agent's test) can read them. Fix by separating roles, not by hoping.

| ID | Item | Done when | Owner | Size | Needs |
|---|---|---|---|---|---|
| S1 | **Split accounts** (DONE 2026-10-29: the `apx-ci` account exists, `apx` can run commands as it, and it cannot read the App key, the Claude token or the apx home; doctor green on the live host). `apx` keeps the App key and posts checks. A second no-secrets account `apx-ci` runs the PR's code and CI commands via a fixed, root-owned wrapper allowed by one narrow sudoers rule. | A test and a live probe run as `apx-ci` and **fail** to read `/Users/apx/.apx/app.pem` and the token; the CI lane runs through the wrapper; the doctor checks the split | me (code) + Ryan (create user, install sudoers rule) | M | |
| S1b | **Agent account.** The model runs as `apx-agent`, which holds only the Claude token (never the App key); the trusted committer stays in `apx`. | As `apx-agent` the key is unreadable; an agent run still produces its PR | me + Ryan | M | S1 |
| S2 | **Redact secrets from published check output.** Strip key blocks, token shapes, and the exact secret values apx holds before anything is posted. Public repos get step names and durations only unless the guard is clean. | Unit tests with planted secrets; a live check on a PR that prints a fake token shows it redacted | me | S | |
| S3 | **Pin required checks to the apx App** (`integration_id` on `guard / guard`, `test`, `build`) so another app cannot fake a pass. | A check of the same name from another app no longer satisfies the ruleset | me (script) + Ryan (admin applies the ruleset edit) | S | S1 |
| S4 | **Egress control.** Default-deny outbound for the CI and agent accounts; allow GitHub, the package registries, and (agent only) Anthropic. macOS: test `pf` rules keyed by user; otherwise ship on the Oracle host (H2). | `redteam_probe.sh` passes **on the host**: arbitrary host, DNS tunnel, IPv6 and LAN all fail | me | L | S1, H2 |
| S5 | **Install-time code.** Stencil's `npm ci` and `uv sync` build steps execute dependency code. Run only inside S1/S4, and use `--ignore-scripts` where the build allows it. | Stencil CI passes with scripts off, or with an explicit reviewed allowlist | me | M | S1 |
| S6 | **Compromise runbook + drill.** Suspend the App, rotate the key, revoke the token, audit recent PRs and branches; practise once. | Written steps in the repo; the drill completes in under 15 minutes | me (doc) + Ryan (drill) | S | |
| S7 | **Red-team in the doctor.** Weekly job tries the exfiltration paths (read the key from a test, print a secret, reach LAN) and must see them fail. | Red result blocks cutover; recorded in the ledger | me | M | S1 |

## Rollout C

| ID | Item | Done when | Owner | Size | Needs |
|---|---|---|---|---|---|
| C1 | **drillpad-workspace full loop** (`APX_CUTOVER`): agent runs, rebases, merges through apx. | An `agent-ready` issue becomes a Verified PR and, if tier-0, merges, all via apx; Actions stays off | me + Ryan (one setting line) | S | **S1, S1b, S2, S3** |
| C2 | **Stencil enrolment.** Merge #98 (the `ci:` list; admin bypass), disable Actions, add to apx's settings as authoritative, then cutover. | A stencil PR is CLEAN on apx's checks; the 21 `agent-ready` issues start flowing | me + Ryan (admin steps) | M | S5, H2 |
| C3 | **autopilot repo** (public, free Actions): cut over only for consistency; low priority. | Optional | me | S | C1 |
| C4 | **Remove leftover Actions callers** per repo after the soak. Touches `.github/`, so each is a PR you merge. | No failing or orphaned workflows remain | me + Ryan (merge) | S | X1 |

## Host H: always-on and isolated

| ID | Item | Done when | Owner | Size | Needs |
|---|---|---|---|---|---|
| H1 | **Oracle Always Free ARM VM**, hardened OS, key-only SSH, no other credentials. | VM reachable only by Ryan's key; baseline probe clean | Ryan (signup, SSH key) + me | M | |
| H2 | **Linux install + service.** systemd unit instead of launchd; per-job sandbox (rootless podman or gVisor); the fabric nftables rules rendered and `nft -c` checked on the real host (never run yet). | apx runs on the VM; `redteam_probe.sh` green there | me | L | H1 |
| H3 | **Move the role off the Mac.** New App key generated on the host, old key revoked, Mac timer removed. | Mac holds no apx secrets | me + Ryan | S | H2 |
| H4 | Optional second worker (the Pi after its Wi-Fi reflash, see `docs/pi-runner-handoff.md`). | Throughput need shown by the meter (O4) first | me + Ryan | M | O4 |

## Operations O

| ID | Item | Done when | Owner | Size | Needs |
|---|---|---|---|---|---|
| O1 | **Silent-failure alert, to Ryan only.** apx writes a heartbeat; the control plane notices a stale one and sends a web push to Ryan (never anyone else). The timer has died silently twice. | Stopping the timer produces a push within 10 minutes | me + Ryan (Vercel secret) | M | |
| O2 | **Safe update path.** The host only pulls commits whose sha is on the approved list; no blind `git pull`. | A non-approved commit on main is not deployed | me | M | |
| O3 | **Dashboard secret.** Set `APX_WEBHOOK_SECRET` in Vercel so apx runs appear in the ledger and `ap report`. | A run shows up in the dashboard | Ryan | S | |
| O4 | **Usage meter.** Turns per task and per day, minutes saved, trend in `ap report`, so Max headroom is measured, not guessed. | A week of numbers; a throttle if headroom is low | me | S | O3 |
| O5 | **Scheduling.** Passes are sequential, so a 4-minute suite blocks every other PR and the lock skips ticks. Check PRs before agent runs, bounded parallelism per lane. | Median time-to-first-check under 2 minutes with 3 PRs open | me | M | |
| O6 | **Status file I can read.** apx writes counts and the last error to a world-readable file; I have been blind without sudo. | I can see the last pass result without asking you | me | S | |
| O7 | Merge #124 (version footer in every check summary). | Merged | Ryan | S | |

## Exit X

| ID | Item | Done when |
|---|---|---|
| X1 | **Clean week.** 7 days of real PRs on the isolated host, no unexplained apx-vs-expected disagreement, no incident. | Ledger and checks reviewed together |
| X2 | **Final security review** against this backlog's Gate S. | Signed off in the PR |
| X3 | Memory, README and AI-disclosure updated; numbers quoted only from captured runs. | Merged |

## Parallel tracks (other sessions, not blocking)

- Stencil eval platform (`/lab`, results ratchet, golden set), in its own terminal.
- Review-load digest (one page of waiting PRs ordered by risk).

## Critical path

`S1 -> S1b -> S2 -> S3 -> C1`  (a few focused days)  ·  `H1 -> H2 -> H3`  (calendar-bound by the VM)  ·  `C2 needs S5 + H2`  ·  `X1 needs C1, C2 and a week`.

First two things to build now, no sudo needed: **S2** (redaction) and the code half of **S1** (the `apx-ci` wrapper, behind a setting that defaults to off).
