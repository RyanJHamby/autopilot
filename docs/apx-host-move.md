# Moving apx to a different Mac (backlog H3, for a spare always-on Mac at home)

Why: apx stops when the Mac you carry sleeps or leaves the house. A spare Mac that stays plugged in at home (the 2019 Intel MacBook Pro) can be the host instead. The Oracle VM
(H1/H2) or a small VPS would be the same move to a Linux box; this page is only the Mac-to-Mac case, and it uses the scripts that already exist.

**The one rule: never two live hosts.** Two daemons polling the same repos post duplicate check runs and can start the same agent run twice. The new host is installed
and tested in DRY-RUN while the old one stays live; the old one is stopped first, then the new one is switched to live. Everything before the switch is reversible.

Nothing here is copied from the old Mac: the new host gets its **own new App key** and its **own new model token**, so the old ones can be killed afterwards.

## 1. Is the Mac fit? (new Mac, no sudo, read-only)

```
git clone https://github.com/RyanJHamby/autopilot.git ~/autopilot-src && cd ~/autopilot-src
bash deploy/apx-host-preflight.sh
```
Fix every FAIL (usually: an old macOS, too little disk). WARN lines worth acting on: sleeping on AC power (`sudo pmset -c sleep 0 disablesleep 1`), missing `node`/`uv`, no battery
charge limit. FileVault is your call: On protects the keys if the laptop is stolen, but after a reboot nothing runs until someone types the disk password.

Also: Ethernet if you can, a guest network or separate Wi-Fi for it if your router has one (PR code runs on this machine, so keep it away from your other devices), and
turn on the battery's optimized/limited charging.

## 2. New secrets (your admin actions, in the GitHub UI and the terminal)

1. GitHub > Settings > Developer settings > GitHub Apps > `autopilot-apx` > **Generate a private key**. Save the `.pem` on the new Mac only. **Do not delete the old key yet.**
2. On the new Mac, make the owner's `~/.apx` that `apx-install-mac.sh` reads: the new `app.pem`, `app.id` (the App id, not secret), `apx.env`
   (paths and ids only; it can be copied from the old Mac, nothing in it is a secret), and a fresh model token:
   ```
   mkdir -p ~/.apx && chmod 700 ~/.apx
   claude setup-token        # prints a token; paste it at the next prompt, it is not shown
   read -rs T < /dev/tty; printf '%s' "$T" > ~/.apx/claude-oauth; unset T; chmod 600 ~/.apx/claude-oauth ~/.apx/app.pem
   ```

## 3. Install in dry-run on the new Mac (old Mac stays live)

Follow `docs/apx-runbook.md` in this order, each with its `DRY_RUN=1` preview first:
`apx` account (section 0) -> `deploy/apx-install-mac.sh` (with `REPOS` listing all three repos) -> `deploy/apx-ci-account.sh` ->
`deploy/apx-agent-account.sh` -> the doctor (`--doctor`, must be green) -> `deploy/apx-updater-setup.sh` (phase 1; the updater is dry-run by default).
Do **not** run `deploy/apx-switch-to-current.sh` (phase 2, the step that makes it live) yet.

Quiet hours, once PR "active-hours window" is merged: add `APX_ACTIVE_WINDOW=18:00-08:30` to `/Users/apx/.apx/apx.env` (see the runbook's "Active hours").

## 4. Cut over (a few minutes with no CI; that is fine)

1. On the OLD Mac, preview then stop its jobs: `sudo bash deploy/apx-retire-host.sh`, then `DO=1 sudo bash deploy/apx-retire-host.sh`. It only stops the launchd jobs.
2. On the NEW Mac: `sudo bash deploy/apx-switch-to-current.sh` (phase 2), then check `PYTHONPATH=/Users/Shared/apx/current/src /usr/bin/python3 -m autopilot.apx.status --print`
   shows `ok` after one pass, and the next PR gets its `apx / guard` and `apx / build` checks.

Roll back if the new host misbehaves: stop its two jobs (`sudo launchctl bootout system/com.autopilot.apx` and `.updater`), then on the old Mac
`sudo launchctl bootstrap system /Library/LaunchDaemons/com.autopilot.apx.plist` (and `.updater.plist`). Its plists and secrets are still there.

## 5. Retire the old secrets (after the new host has run cleanly for a day)

1. GitHub > the App > private keys > **delete the OLD key** (your admin action). From then the old Mac's copy is dead even if the file survives.
2. On the old Mac remove the files `apx-retire-host.sh` listed (`/Users/apx/.apx/app.pem`, `claude-oauth`, and your own `~/.apx`). Look at each before deleting.
3. Revoke the old model token from your Claude account settings if you want it dead (I have not verified the exact menu; deleting the file is the minimum).
4. Tick H3 on issue #126.
