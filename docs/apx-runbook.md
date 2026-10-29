# apx runbook: first run on the Mac (owner steps)

Everything below is safe by default: apx does nothing live unless you pass `--live` AND set `APX_LIVE=1`, and in shadow
mode its checks use non-required names, so it cannot approve or block a merge. Stop it any time with `launchctl bootout`
or by suspending the App. See `docs/apx-app.md` for the App itself.

## 0. Isolation first (5 min)

apx runs model output and PR code. Do not run it as your normal login.
1. System Settings > Users & Groups > add a **standard** (non-admin) user `apx`. No iCloud, no Apple ID, no keychain items,
   no SSH keys, no `gh` login.
2. Log in as `apx` only to do the steps below. Home directory permissions stay `700`.
3. macOS has no network egress firewall per user. Until the Oracle host exists this is a **spike machine**: keep it to
   throwaway PRs on `autopilot` (see step 5), not your other repos.

## Move into the apx account (after setup, before any timer)

```
DRY_RUN=1 bash deploy/apx-install-mac.sh     # preview, changes nothing
sudo bash deploy/apx-install-mac.sh          # do it
```
Copies the App key, App id and Claude token into `/Users/apx/.apx` (mode 600/700, owned by `apx`), rewrites the settings
so only `REPOS` (default: autopilot) is enabled, copies `uv` and `claude` into `/Users/apx/.local/bin`, clones the public
repo, and runs the doctor as `apx`. Then remove your own copies of `app.pem` and `claude-oauth` from `~/.apx`. The timer is
`deploy/launchd/com.autopilot.apx.daemon.plist` (runs as `apx`, no login needed; install steps are in its header).

## Fast path: the setup helper (replaces steps 2 and 3 below)

```
python -m autopilot.apx.setup
```
It opens GitHub with a least-privilege manifest (click **Create GitHub App** once), writes the private key straight into
`~/.apx/app.pem` (mode 600, never printed), waits while you install the App on the three repos (second click), writes
`~/.apx/apx.env` (paths and ids only), and asks for the Claude token with a hidden prompt. Then run the doctor.

## 1. Tools (as `apx`)

`git`, `python3` (3.11+), `openssl`, `claude` (Claude Code CLI), `pip install pyyaml`. Clone the autopilot repo read-only
(a deploy key or HTTPS with the App token; never your personal SSH key).

## 2. App and secrets (you, in the GitHub UI, about 5 min)

Follow `docs/apx-app.md`. Then, as `apx`:
```
mkdir -p ~/secrets && chmod 700 ~/secrets
# paste the downloaded .pem here, then:
chmod 600 ~/secrets/apx-app.pem
read -rs T < /dev/tty; printf '%s' "$T" > ~/secrets/claude-oauth; unset T; chmod 600 ~/secrets/claude-oauth
```
(`claude setup-token` prints the token; paste it at the hidden prompt. It never goes in a repo, chat or shell history.)

## 3. Settings file

`~/apx.env` (mode 600), no secrets inside, only paths and ids:
```
APX_APP_ID=<app id>
APX_KEY_PATH=/Users/apx/secrets/apx-app.pem
APX_INSTALLATIONS=RyanJHamby/autopilot=<installation id>
APX_OAUTH_FILE=/Users/apx/secrets/claude-oauth
APX_KIT_REPO=RyanJHamby/autopilot-kit
APX_KIT_REF=<an APPROVED kit sha, 40 hex>
```
Start with `autopilot` only. Add `drillpad-workspace` and `stencil` after the spike passes.

## 4a. Doctor (read-only, run this first)

```
set -a; . ~/apx.env; set +a
python -m autopilot.apx.daemon --doctor
```
Checks tools, key and token file permissions, that the App id matches, that the App has **only** the permissions in
`docs/apx-app.md` (it FAILS on administration, workflows, secrets, environments or any extra permission), that it is
installed on exactly your three repos and nothing else, and that the kit sha is on the APPROVED list. Fix every FAIL
before going on; paste me the output if one is unclear.

## 4b. Dry run (changes nothing)

```
set -a; . ~/apx.env; set +a
python -m autopilot.apx.daemon --once
```
It prints what it WOULD do (`DRY-RUN check-pr ...`, `DRY-RUN run-agent ...`). Check the list makes sense.

## 5. The spike (one throwaway PR, live)

1. In `autopilot`, open a tiny docs-only PR from a branch named `agent/0-spike`.
2. `APX_LIVE=1 python -m autopilot.apx.daemon --once --live`
3. Look for three things on the PR:
   - checks named `apx / guard` and `apx / build` appeared (App can post check runs)
   - they are green for a clean change and red if you add a fake secret-shaped string
   - for an agent-made PR (label an `agent-ready` issue you wrote): the commit shows **Verified** in the PR
4. Tell Claude the result. The live behaviour of the real `claude` flags is confirmed here for the first time.

## 6. Run it on a timer (only after the spike)

Use the template `deploy/launchd/com.autopilot.apx.plist` (replace `REPO_DIR`; install steps and the stop command are in its
header comment). It ticks every 120 seconds; a tick that finds a previous pass still running skips itself (single-instance
lock), so a long agent run never starts the same issue twice. It does not start at load.
Keep `APX_SHADOW` unset (shadow on) for a week and compare apx's checks with the Actions ones before any cutover.

## 7. Cutover (later, per repo, your decision)

Cutover changes the required checks and disables the Actions callers: protected-path PRs that you merge. Not part of the
spike.

## What apx never does

- It never merges while in shadow mode (`APX_SHADOW` on, the default): the merge lane only exists after a repo is cut over.
- It only ever pushes `agent/*` branches; the committer refuses any other branch name.
- It never holds Administration, Workflows, Secrets or Environments permissions; the doctor FAILS if the App has them.
- It does nothing live unless you pass `--live` AND set `APX_LIVE=1`; otherwise every pass is a dry run.
- It only works on the three configured repos (`autopilot`, `drillpad-workspace`, `stencil`); the doctor checks the App is installed on exactly those.
- It never gives the model GitHub credentials: only the trusted committer and check reporter use the App's token.

## Shadow week: what to look at

The timer ticks every 2 minutes as the `apx` account, autopilot only, in shadow mode (non-required `apx / ...` check names).
- **Is it alive?** Open any autopilot PR: `apx / guard` and `apx / build` should appear within a couple of minutes of a push,
  posted by the `autopilot-apx` App. No checks from the App on a fresh PR after ~5 minutes means the timer is not running.
- **Does it agree with Actions?** For every PR compare `apx / guard` with `guard / guard`, and `apx / build` with `test`.
  They run the same guard and the same CI steps, so any disagreement is a bug to investigate, not noise.
- **Logs** (need sudo, they belong to `apx`): `sudo tail -n 50 /Users/apx/Library/Logs/apx.log` and `apx.err.log` next to it.
- **Stop it:** `sudo launchctl bootout system/com.autopilot.apx`. **Start it again:** the `bootstrap` line from the plist header.
- **Code freshness:** `apx` runs the clone it made at install time; it does not update itself. Refresh it with
  `sudo -u apx -H git -C /Users/apx/autopilot pull --ff-only` after a change you want it to pick up.

## Private repos without Actions minutes: authoritative mode (per repo)

Stencil and drillpad-workspace can't run Actions while the private-minute limit is hit, so a shadow comparison there is
impossible and their PRs wait on required checks only Actions posts. For a repo you list in `APX_AUTHORITATIVE`, apx posts
the names its ruleset requires (`guard / guard` plus `test`, or `build` for stencil) instead of `apx / ...`. The ruleset
accepts any app for those names, so apx's results satisfy the merge rules. Agent runs and the merge lane stay off until a
full cutover (`APX_SHADOW=0`).

Per repo, in order:
1. The repo's `.autopilot/repo.yaml` on main must have a `ci:` list (drillpad-workspace #74, stencil #98). Without it the lane
   fails closed ("no `ci:` steps configured"). Those two PRs are blocked by the same missing Actions checks, so merging them
   needs the repo admin's bypass on the merge button; they only add a list of commands.
2. In `/Users/apx/.apx/apx.env` (as `apx`): add the repo to `APX_INSTALLATIONS` (same installation id) and to
   `APX_AUTHORITATIVE`.
3. Refresh the clone so apx has this code: `sudo -u apx -H git -C /Users/apx/autopilot pull --ff-only`.

Risk to know: apx runs the PR's code as the `apx` Mac account, which isolates files and credentials but cannot firewall the
network. Stencil's CI runs `npm ci` with dependency install scripts; do stencil only after the Oracle host, or accept that.

## Full cutover of one repo (apx replaces Actions for it)

`APX_CUTOVER=<repo>[,<repo>]` in `/Users/apx/.apx/apx.env` turns on the whole loop for those repos only: required-name checks
(like authoritative mode), plus agent runs for `agent-ready` issues, rebases (`update-branch` for behind PRs, a once-a-day
re-run for conflicted ones), and the merge lane (the kit's `automerge.py`, same tier-0 rules). Other repos stay in shadow.

Do it in this order so two systems never act on the same repo:
1. `APX_CUTOVER` set for the repo, clone refreshed (`sudo -u apx -H git -C /Users/apx/autopilot pull --ff-only`), doctor green.
2. Watch one agent run and one merge go through apx.
3. Only then disable Actions for that repo (Settings > Actions > General > Disable actions, or leave the callers failing:
   they can only fail on the spending limit). Until step 3, the kit's Actions dispatcher can still race apx on `agent-ready`
   issues if the spending limit is ever lifted, so step 3 should follow step 2 closely.
Rollback: remove the repo from `APX_CUTOVER`, re-enable Actions.

## Sandbox account: keep PR code away from the secrets (backlog S1)

The App key and the Claude token are files owned by `apx`. Anything that runs as `apx` can read them, including a PR's tests. With a
second account, `apx-ci`, the guard and the repo's CI commands run there instead, and `apx-ci` cannot read those files.

Order matters (the sandbox runs a shared copy of this repo's code, which must already contain it):
1. Merge the PR that adds this section, so `main` contains the sandbox job.
2. Preview, then run, in **Terminal.app** (the real run prompts for a password for the new account):
   ```
   DRY_RUN=1 bash deploy/apx-ci-account.sh
   sudo bash deploy/apx-ci-account.sh
   ```
   It creates `apx-ci` (private home, `uv`, links to `rustc`/`cargo`), a world-readable shared area `/Users/Shared/apx` (kit cache, a
   copy of this repo, a Python with PyYAML), and the one sudoers rule `apx ALL=(apx-ci) NOPASSWD:SETENV: ALL` (syntax-checked first).
   It then proves the split: `apx` can run commands as `apx-ci`, and `apx-ci` **cannot** read the App key.
3. As `apx`, add `APX_CI_USER=apx-ci`, `APX_CI_WORK=/Users/apx-ci/work`, `APX_SHARED=/Users/Shared/apx` to `/Users/apx/.apx/apx.env`.
4. Refresh both clones whenever code changes: `/Users/apx/autopilot` and `/Users/Shared/apx/autopilot`.
5. Run the doctor. It now fails if the sandbox can read the key, the token or the orchestrator's home, if it is an admin, or if its
   Python lacks PyYAML (without which the kit guard would silently lose its config).

Agent runs stay **off** after a cutover until a separate agent account (`APX_AGENT_USER`, backlog S1b) exists, even if `APX_CUTOVER` is
set: the planner says "agent runs blocked: no dedicated agent account". Rebases and merges are not affected.

## Pin required checks to the apx App (backlog S3, admin action, run by the owner)

Until this is done the rulesets accept `guard / guard` and `test`/`build` from ANY app, so anything holding a `checks:write` token could post a
passing check. Pinning makes only the apx App's results count.

```
cd ~/dev/autopilot
python3 -m autopilot.apx.pin --repo RyanJHamby/drillpad-workspace            # dry run: shows what would change
python3 -m autopilot.apx.pin --repo RyanJHamby/drillpad-workspace --apply     # writes the ruleset
python3 -m autopilot.apx.pin --repo RyanJHamby/drillpad-workspace --undo --apply   # puts it back
```
It uses your own `gh` login (the edit needs admin). It changes only `integration_id` on the check names apx posts for that repo; other rules,
bypass actors and conditions are sent back unchanged. It **refuses** unless apx has posted those checks successfully on the repo's recent PRs,
because pinning a repo whose checks still come from Actions would stop every merge. Do drillpad-workspace first; autopilot and stencil only
after apx is authoritative there. If apx stops, pinned PRs cannot merge until you undo the pin or use your admin bypass: that is the point.

## The model's own account: agent runs (backlog S1b)

The model runs as a third account, `apx-agent`, that holds **only the Claude token**. It gets a short-lived, read-only, single-repository token for each
checkout and never sees the App key, so even a fully prompt-injected agent cannot write to GitHub; its edits come back as data and `apx` makes the
commit. The account that runs a PR's code (`apx-ci`) cannot read the model's token, and `apx` itself stops holding the Claude token.

Do this only after the sandbox account (above) is done. Order:
1. Merge the PR that adds this section (so the shared code copy contains the agent job).
2. Preview, then run, in **Terminal.app** (the real run prompts for a password for the new account):
   ```
   DRY_RUN=1 bash deploy/apx-agent-account.sh
   sudo bash deploy/apx-agent-account.sh
   ```
   It creates `apx-agent`, installs the `claude` CLI into its home, **moves** your Claude token into its home (mode 0600), installs one
   syntax-checked sudoers rule, and proves the separation from every side: `apx-agent` cannot read the App key or the apx home, `apx-ci` cannot read the
   model's token, `apx-agent` can read its own token and run `claude`. Only after those pass does it delete `apx`'s old copy of the token
   (set `KEEP_OLD_TOKEN=1` to skip that).
3. As `apx`, add `APX_AGENT_USER=apx-agent` to `/Users/apx/.apx/apx.env` and delete any `APX_OAUTH_FILE` line.
4. Refresh both clones (`/Users/apx/autopilot` and `/Users/Shared/apx/autopilot`), then run the doctor. It now also checks the agent account from its own side.

Agent runs still only start for a repo that is cut over (`APX_CUTOVER` or `APX_SHADOW=0`). Nothing starts until you choose that.

## Knowing when apx has stopped (owner-only, local)

apx writes `/Users/Shared/apx/status.json` after every pass (world-readable, no secrets). Check it any time, no sudo:

    PYTHONPATH=/Users/Shared/apx/autopilot/src /usr/bin/python3 -m autopilot.apx.status --print

To get a local macOS notification when apx stops (no pass for 15 minutes) or a pass reports a problem, install the owner's watcher once
(it runs as you, every 5 minutes, and only shows a notification on your own screen; nothing leaves the Mac):

    cp deploy/launchd/com.autopilot.apx.watch.plist ~/Library/LaunchAgents/
    launchctl load ~/Library/LaunchAgents/com.autopilot.apx.watch.plist

You are told once per distinct problem and once when it clears. Phone push needs the control-plane webhook secret (backlog O3).
