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
