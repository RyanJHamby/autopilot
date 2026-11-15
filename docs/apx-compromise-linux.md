# apx compromise runbook: the Linux host

The Linux version of [apx-compromise.md](apx-compromise.md), for the host built by `deploy/linux/bootstrap.sh` ([apx-linux-host.md](apx-linux-host.md)). Same three
accounts (`apx`, `apx-ci`, `apx-agent`), plus `apx-dns` (the allowlist resolver), the same GitHub App (`autopilot-apx`) and the same three repos. The GitHub-side
sections of the macOS runbook (its section 4, "What to check on GitHub afterwards") apply unchanged; this page links to them rather than copying them.

How to read this:
- Every command runs in bash on the host, logged in over SSH as your admin account (`ryan` on the current host), with `sudo` where shown. Agents never run these.
- **[RYAN-ADMIN]** = needs your GitHub admin login, the GitHub web UI or your Claude account. An agent cannot do it.
- **unverified** = derived from the repo by reading the code, not run on the real host.
- **not supported on Linux yet** = the macOS runbook has the step, and nothing in this repo does it on Linux. Nothing is invented to fill the gap.
- Run scripts from **your own clone** (`~/autopilot`, made in step 2 of apx-linux-host.md), never from `/srv/apx`. The `apx` account owns everything under
  `/srv/apx`, so after a compromise that code is suspect; your clone is owned by you and `apx` cannot write to it.
- Written 2026-11-15 from the repo only. None of it has been run on the host yet; the "Rehearsal" section at the end is how to change that.
  `tests/test_apx_compromise_linux_doc.py` checks that the env vars, repo paths, units and host paths named here exist in the repo. It cannot check that the
  commands work.

Rule of thumb: if you are unsure which account is affected, assume `apx` and do everything. Rotation is cheap; a leaked App key is not.

## 1. Stop everything now (about two minutes)

1.1 Stop new passes. The timers start `apx.service` and `apx-updater.service` every two minutes; disabling them with `--now` stops them firing and keeps them
off after a reboot (bootstrap installs them disabled, so a reboot alone never turns them back on):
```
sudo systemctl disable --now apx.timer apx-updater.timer
```
Do not use `systemctl mask` here: the unit files live in `/etc/systemd/system`, where a mask link would have to go, so it fails, and bootstrap rewrites those
files anyway.

1.2 Make the evidence directory and take a ten-second snapshot of what is running, before you kill it. Everything in sections 1, 2 and 4 that collects evidence
writes here; it is root-only. Keep this shell open: later steps use `$E` and `$STAMP`.
```
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
E=/root/apx-evidence-$STAMP
sudo install -d -m 700 -o root -g root "$E"
date -u | sudo tee "$E/stopped-at.txt"
sudo ps -eo pid,ppid,user,lstart,etime,args --forest | sudo tee "$E/ps.txt" >/dev/null
sudo ss -tunap | sudo tee "$E/sockets.txt" >/dev/null
sudo nft list table inet apx | sudo tee "$E/nft-table.txt" >/dev/null
```
The last line matters most: the allowlist sets hold the addresses each lane's resolver answered, and entries expire after an hour (`SET_TIMEOUT` in
`src/autopilot/apx/nftrules.py`). After that you have no record of which addresses a lane could reach.

Optional, only while a pass is still running: `apx.service` has `PrivateTmp=yes`, and the work dir defaults to `apx-work` under the temp dir (`APX_WORK`
in `src/autopilot/apx/daemon.py`, unset in the documented `apx.env`), so stopping the service deletes it. To keep it, copy it first (path pattern is
systemd's, **unverified** on the host):
```
sudo sh -c 'cp -a /tmp/systemd-private-*-apx.service-*/tmp/apx-work "$1/apx-work"' _ "$E"
```

1.3 Kill a pass that is still running. A pass can hold a long agent run; disabling the timer does not stop it. Stopping the service kills its whole control
group, which includes the sandboxed children (the unit comment says sudo keeps them in it):
```
sudo systemctl stop apx.service apx-updater.service
```
`retire.sh` does 1.1 and 1.3 in one go, from your clone (it previews without `DO=1`, and deletes nothing):
```
cd ~/autopilot
sudo DO=1 bash deploy/linux/retire.sh
```

1.4 Kill anything left running as the three accounts (something that escaped the unit, or was started another way). Leave `apx-dns` alone: section 2 decides
about it.
```
sudo pkill -KILL -u apx
sudo pkill -KILL -u apx-ci
sudo pkill -KILL -u apx-agent
```

1.5 [RYAN-ADMIN] Pause the planner on all three repos, as on the Mac (repo variable, read through the App, `enabled` in `src/autopilot/apx/planner.py`). Run
this from any machine with your `gh` login; it is what keeps a second host, or a restarted one, from acting:
```
gh variable set AUTOPILOT_PAUSED --body true --repo RyanJHamby/autopilot
gh variable set AUTOPILOT_PAUSED --body true --repo RyanJHamby/drillpad-workspace
gh variable set AUTOPILOT_PAUSED --body true --repo RyanJHamby/stencil
```
If you also want the stop that does not depend on this host: [RYAN-ADMIN] GitHub > Settings > Developer settings > GitHub Apps > `autopilot-apx` > Install
App > the cog next to your account > Suspend. Whether that also kills installation tokens already minted is **unverified**.

1.6 `APX_LIVE`: on Linux it is set inside `ExecStart=` of `apx.service`, not in `apx.env`, so stopping the unit is what removes it. Check the settings file has
no copy (no output is expected):
```
sudo grep -nE '^(APX_LIVE|APX_UPDATE_LIVE)' /home/apx/.apx/apx.env
```
And check whether the updater was made live by a drop-in (apx-linux-host.md, step 6). A `--live` there is worth knowing for section 5:
```
sudo systemctl cat apx-updater.service
```

Verify it stopped:
```
systemctl is-enabled apx.timer apx-updater.timer
systemctl is-active apx.service apx-updater.service
pgrep -l -u apx,apx-ci,apx-agent
```
Expect `disabled` twice, then `inactive` twice, then no output. Then `gh variable get AUTOPILOT_PAUSED --repo RyanJHamby/autopilot` should print `true` (repeat
for the other two). The status file only goes `stale` after 15 minutes (`STALE_AFTER` in `src/autopilot/apx/status.py`):
```
PYTHONPATH="$HOME/autopilot/src" python3 -m autopilot.apx.status --print
```
It reads `/srv/apx/status.json`. It is run from your clone, not from `/srv/apx/current`, for the reason above.

Installation tokens minted before the stop stay valid up to an hour (`src/autopilot/apx/app_auth.py`); the time is in `$E/stopped-at.txt`.

## 2. Contain egress

What the rules already block, without you doing anything (`src/autopilot/apx/nftrules.py`, `deploy/linux/systemd/apx-nft.service`): traffic from the three
accounts is matched by uid. Each lane may open TCP 443 only to addresses its own resolver answered for its own names, and never to a private, link-local or
metadata range. `apx-ci` and `apx-agent` may also reach TCP ports 1024 and up on `127.0.0.1`. Everything else from them is refused, including all IPv6, SSH to
GitHub and other resolvers; their DNS is redirected to the allowlist resolver. Which names each lane gets is `lanes()` in that module: the orchestrator gets
GitHub (plus the control-plane host if bootstrap was given `CONTROL_HOST`), `apx-ci` gets GitHub and the package registries, `apx-agent` gets GitHub and the
model API. Your admin account, root, apt and the resolver itself are not restricted.

**Never stop `apx-nft.service` during an incident.** Its `ExecStop=` deletes `table inet apx`, and the output chain's policy is accept, so stopping it removes
every restriction on the three accounts.

**A deny-all mode is not supported on Linux yet.** Nothing in the code renders a rule set that refuses the allowed names too, and this page does not invent
one. What you can do with what exists:

2.1 Stop the resolver (derived from the unit files, **unverified** on the host). With `apx-dns.service` stopped, the three accounts' DNS is still redirected to
its port and nothing answers, so no new name resolves and no new address enters a lane's set. Addresses already in a set stay reachable on 443 until their
entry expires (up to an hour, the same `SET_TIMEOUT`). `apx.service` and `apx-updater.service` both `Require=` the resolver, so neither can start while it is
stopped. Take the snapshot in 1.2 first, then:
```
sudo systemctl stop apx-dns.service
```
It is still enabled, so it comes back at boot; that is fine while the timers stay disabled.

2.2 Everything the processes could do is already stopped by section 1: with no process running as the three accounts, the lanes carry no traffic.

2.3 The rules restrict only the three apx accounts. If you think something escaped them (root, your admin account, or another uid), the allowlist does not
help: treat the whole host as lost, disconnect it with your provider's console or firewall, and rebuild (section 6, option A). That step is outside this repo.

Check the rules are still loaded and the probe still passes (from your clone; it needs the resolver for its "allowed path" checks, so with 2.1 done expect
the GitHub-on-443 and allowlisted-name checks to report BROKEN, and every must-fail case to stay ok):
```
sudo nft list table inet apx | head -5
cd ~/autopilot
sudo bash deploy/linux/egress-probe.sh
```

## 3. Revoke credentials

Do these with apx stopped (section 1). The settings file holds paths and ids only, no secret (apx-linux-host.md, step 4), so reading it is safe.

### 3.1 GitHub App private key [RYAN-ADMIN]

Where it is on the host. The setting is `APX_KEY_PATH` (default in the documented `apx.env`: `/home/apx/.apx/app.pem`):
```
sudo grep '^APX_KEY_PATH' /home/apx/.apx/apx.env
```
In GitHub: Settings > Developer settings > GitHub Apps > `autopilot-apx` > **Private keys**.
1. **Delete** the key in use now (match it by fingerprint and creation date). Until a new key is installed apx cannot authenticate, which is what you want.
2. Generate a new key only when you are ready to rebuild (section 6). It downloads once. The App id and installation ids do not change.

Then remove the old copy from the host (it is dead once deleted on GitHub; it is not evidence, so it never goes in the tarball):
```
sudo shred -u /home/apx/.apx/app.pem
```
If `APX_KEY_PATH` printed a different path, use that one. Look for stray copies too:
```
sudo find /home /srv/apx /tmp /root -name '*.pem' -ls 2>/dev/null
```

### 3.2 Model token for `apx-agent` [RYAN-ADMIN]

With `APX_AGENT_USER` set, the token lives only in that account's home, `/home/apx-agent/.apx/claude-oauth` (`Settings.from_env` in
`src/autopilot/apx/daemon.py`; `APX_OAUTH_FILE` overrides it, so check):
```
sudo grep -nE '^(APX_OAUTH_FILE|APX_AGENT_USER)' /home/apx/.apx/apx.env
sudo ls -la /home/apx-agent/.apx /home/apx/.apx
```
If `/home/apx/.apx/claude-oauth` exists, the orchestrator could read the token: treat it as leaked whichever account you suspected.

Revoke it in your Claude account settings. The exact menu for a `claude setup-token` token is **unverified**: neither runbook documents it. Then remove the file:
```
sudo shred -u /home/apx-agent/.apx/claude-oauth
```
Mint the new one only in section 6.

### 3.3 Installation tokens (nothing on disk)

`token_for` and `read_token_for` in `src/autopilot/apx/app_auth.py` mint installation tokens that expire one hour after they were minted, and keep them in
memory only. The CI lane's checkout token is a write token (`token_for`, passed by `src/autopilot/apx/sandbox.py`); the agent lane's is read-only for one
repo. Git gets them through its environment, not a file (`src/autopilot/apx/gitops.py`), so a leftover checkout does not contain one. Deleting the key (3.1)
stops new ones; treat one hour after the time in `$E/stopped-at.txt` as the point when none minted on this host is valid. Whether deleting the key also kills
the ones already minted is **unverified**; suspending the installation (1.5) is the faster stop if that hour matters.

### 3.4 Webhook secret

Only if `APX_WEBHOOK_SECRET_FILE` is set:
```
sudo grep '^APX_WEBHOOK_SECRET_FILE' /home/apx/.apx/apx.env
```
If it prints a path, follow 3D in [apx-compromise.md](apx-compromise.md) with that path; the control-plane side is the same for both hosts. If it prints
nothing there is nothing to rotate.

## 4. Preserve evidence (before any cleanup)

Into `$E` from section 1, then one root-only tarball. Do this before section 6 moves or rebuilds anything. Secrets are left out on purpose (the key and token
are already shredded; nothing below copies a `.pem` or `claude-oauth`).

4.1 Journals, one file per unit, plus a full export of the last week (the binary export format keeps every field):
```
for u in apx.service apx.timer apx-updater.service apx-updater.timer apx-nft.service apx-dns.service; do sudo journalctl -u "$u" --no-pager -o short-iso-precise | sudo tee "$E/journal-$u.txt" >/dev/null; done
sudo journalctl --since "-7 days" -o export | sudo tee "$E/journal-7d.export" >/dev/null
```
The resolver does not log queries (the rendered `dnsmasq.conf` has no query logging), so its journal shows starts and stops only; the nft snapshot from 1.2 is
the record of what was resolved.

4.2 Status files, the last swap and the HOLD switch (`src/autopilot/apx/status.py`, `src/autopilot/apx/release.py`); missing files print an error and are
skipped:
```
sudo cp -a /srv/apx/status.json /srv/apx/update.json /srv/apx/swap.json /srv/apx/HOLD "$E/" 2>&1
```

4.3 The run ledger. Its path is `APX_DB`; the documented Linux `apx.env` does not set it, and then it is the relative name `apx.sqlite` in the working
directory of `apx.service`, which is `/srv/apx/current`. That means each release directory has its own ledger, and a release switch starts an empty one. So
collect all of them:
```
sudo grep '^APX_DB' /home/apx/.apx/apx.env
sudo find /srv/apx/releases -maxdepth 2 -name 'apx.sqlite*' -ls
sudo sh -c 'for f in /srv/apx/releases/*/apx.sqlite*; do [ -e "$f" ] && cp -a "$f" "$1/ledger-$(basename "$(dirname "$f")")-$(basename "$f")"; done' _ "$E"
```
If `APX_DB` printed a path, copy that file instead.

4.4 Releases and what `current` and `previous` point at, with each release's HEAD and any local changes:
```
sudo ls -la --time-style=full-iso /srv/apx /srv/apx/releases | sudo tee "$E/srv-apx-ls.txt" >/dev/null
sudo readlink /srv/apx/current /srv/apx/previous | sudo tee "$E/links.txt"
sudo sh -c 'for d in /srv/apx/releases/*/ /srv/apx/autopilot /srv/apx/updater; do echo "== $d"; git -c safe.directory="*" -C "$d" log -1 --format="%H %cI %s"; git -c safe.directory="*" -C "$d" status --porcelain --ignored; done' | sudo tee "$E/releases-git.txt" >/dev/null
```
`safe.directory` lets root read a repo another account owns; root runs only `log` and `status` here. A compromised `apx` could have planted git hooks or
config in those clones, so do not run anything else in them as root.

4.5 Settings, the installed system files, and the sandbox work dirs:
```
sudo cp -a /home/apx/.apx/apx.env /etc/apx /etc/sudoers.d/apx-ci /etc/sudoers.d/apx-agent "$E/"
sudo sh -c 'mkdir -p "$1/systemd" && cp -a /etc/systemd/system/apx* "$1/systemd/"' _ "$E"
sudo sh -c 'ls -laR --time-style=full-iso /home/apx /home/apx-ci /home/apx-agent' | sudo tee "$E/homes-ls.txt" >/dev/null
sudo tar -C / -czf "$E/sandbox-work.tar.gz" home/apx-ci/work home/apx-agent/work
```
The work dirs hold repo checkouts and whatever PR code or the model left behind; they can be large.

4.6 Pack it, root-only, and record the checksum:
```
sudo tar -C /root -czf "/root/apx-evidence-$STAMP.tar.gz" "apx-evidence-$STAMP"
sudo chmod 600 "/root/apx-evidence-$STAMP.tar.gz"
sudo sha256sum "/root/apx-evidence-$STAMP.tar.gz" | sudo tee "/root/apx-evidence-$STAMP.sha256"
```
Copy the tarball off the host if you will re-image it (section 6, option A), with your own `scp` from your laptop; it never goes into a repo.

## 5. Find out what happened

Read-only. Start from the earliest time the compromise could have begun.

5.1 GitHub side: run section 4 of [apx-compromise.md](apx-compromise.md) ("What to check on GitHub afterwards") on all three repos. It is the same for both
hosts: branches outside `agent/*`, unsigned or unknown commits, PRs, `.github` changes, rulesets, deploy keys, hooks, secrets, variables, check-run apps.

5.2 What apx did: `$E/journal-apx.service.txt` (every pass prints its plan and actions), `$E/journal-apx-updater.service.txt` (any swap, rollback or refusal),
the ledgers from 4.3 (`runs` table: repo, issue, kind, status, times), `status.json` and `swap.json`. A swap you did not expect is a finding.

5.3 Integrity of the code apx runs. Compare with `main` from your own clone (fetch there, not in `/srv/apx`):
```
git -C ~/autopilot fetch -q origin
cat "$E/links.txt"
git -C ~/autopilot branch -r --contains SHA-FROM-LINKS
```
(Replace `SHA-FROM-LINKS` with the sha in each link.) Every release HEAD must be on `origin/main`, and `$E/releases-git.txt` should show no modified files.
Untracked files under `src/` are a finding even though `release.sh` would accept them: its cleanliness check ignores untracked files.

5.4 Integrity of what root installed. Compare the units with the repo, and the rules with a fresh render (as in bootstrap):
```
cd ~/autopilot
for u in apx.service apx.timer apx-updater.service apx-updater.timer apx-nft.service apx-dns.service; do diff "deploy/linux/systemd/$u" "/etc/systemd/system/$u" && echo "same: $u"; done
ls /etc/systemd/system/apx.service.d /etc/systemd/system/apx-updater.service.d 2>&1
sudo cat /etc/sudoers.d/apx-ci /etc/sudoers.d/apx-agent
PYTHONPATH=src python3 -m autopilot.apx.nftrules nft --uid "apx=$(id -u apx)" --uid "apx-ci=$(id -u apx-ci)" --uid "apx-agent=$(id -u apx-agent)" | diff - /etc/apx/apx.nft && echo "same: apx.nft"
```
Expected: every unit `same` (the units may differ only if your clone is newer than the release that installed them); the drop-ins are only bootstrap's
`10-memory.conf` and any live drop-in you added; each sudoers file is the single line `apx ALL=(apx-ci) NOPASSWD:SETENV: ALL` or
`apx ALL=(apx-agent) NOPASSWD:SETENV: ALL`. These files are root-owned, so a change here means more than one apx account was involved.

5.5 Persistence the code does not set up, so any entry is a finding (general Linux checks; the paths are the distribution's, not this repo's):
```
for u in apx apx-ci apx-agent; do echo "== $u"; sudo crontab -l -u "$u" 2>&1; done
ls /var/lib/systemd/linger 2>&1
sudo ls -la /home/apx/.local/bin /home/apx-ci/.local/bin /home/apx-agent/.local/bin
sudo find /srv/apx/toolchains ! -user root -ls
sudo find /srv/apx/toolchains -perm /022 ! -type l -ls
sudo last -20
```
Each account owns its own `.local/bin` (`uv` for `apx-ci`, `claude` for `apx-agent`), so PR code can replace `uv` for the next job and the model's account can
replace its own `claude`. Treat both as suspect after an incident and reinstall them (section 6). `/srv/apx/toolchains` must be all root-owned and not
group- or world-writable; anything printed by the two `find` lines is a finding. Note that `apx` owns `/srv/apx` itself, so it could rename the toolchains
directory and put its own in place; the `! -user root` line catches that, since `apx` cannot create root-owned files.

5.6 Decide which account it was, with the decision table in section 2 of [apx-compromise.md](apx-compromise.md) (the signals are the same; read
`/home/apx...` for `/Users/apx...`). Root-owned files changed, or a process not owned by the three accounts doing something odd: treat it as root and take
option A below.

## 6. Rebuild and recover

Preconditions: sections 1 to 5 done, the evidence tarball made, and you know which account it was.

**Option A: re-image (when `apx` or root is suspected, or you cannot tell).** Rebuild the server from your provider's console and follow
[apx-linux-host.md](apx-linux-host.md) from step 1, with new secrets. This repo does not automate re-imaging; it is the only option that does not trust anything
the compromised accounts could write. Then continue at 6.5.

**Option B: in place (`apx-ci` or `apx-agent` only, with clean 5.3 to 5.5).**

6.1 Pick a known-good commit of `main` from your own clone: one you reviewed, signed, and older than the earliest suspect time:
```
cd ~/autopilot
git fetch -q origin
git log --show-signature -5 origin/main
SHA=$(git rev-parse COMMIT-YOU-CHOSE)
git checkout -q --detach "$SHA"
```

6.2 Move apx's tree and the sandbox state aside, into the evidence directory, so nothing the compromised accounts wrote is reused. `release.sh` reuses an existing
`releases/<sha>` that passes its check, and that check ignores untracked files, so a fresh tree is the safe start. Bootstrap recreates the directories and
clones fresh when `/srv/apx/autopilot` is missing:
```
sudo mv /srv/apx "$E/srv-apx"
sudo mv /home/apx-ci/work "$E/apx-ci-work"
sudo mv /home/apx-agent/work "$E/apx-agent-work"
sudo mv /home/apx-ci/.local/bin "$E/apx-ci-bin"
sudo mv /home/apx-agent/.local/bin "$E/apx-agent-bin"
```
The toolchains moved with `/srv/apx`. Reinstall them (apx-linux-host.md, step 5), or move them back only if both `find` lines in 5.5 printed nothing:
`sudo install -d -m 755 -o apx -g apx /srv/apx` then `sudo mv "$E/srv-apx/toolchains" /srv/apx/toolchains`.

6.3 Preview, then bootstrap at that sha. With `APX_SHA` set, bootstrap hands the release to `deploy/linux/release.sh`, which refuses a sha that is not on
`origin/main`, builds and verifies `releases/<sha>`, and only then switches `current`:
```
DRY_RUN=1 APX_SHA="$SHA" ADMIN_USER=ryan bash deploy/linux/bootstrap.sh
sudo APX_SHA="$SHA" ADMIN_USER=ryan bash deploy/linux/bootstrap.sh
```
Read its output: `wrote:` for `/etc/apx/apx.nft`, `/etc/apx/dnsmasq.conf`, a unit or a sudoers file that you did not expect to change means the installed copy
differed from this commit's. Bootstrap must end with `Done.` and no FAIL. Add `CONTROL_HOST=...` after `sudo` if the host had one. If 2.1 stopped the resolver,
bootstrap restarts it.

6.4 Reinstall `uv` for `apx-ci` and the `claude` CLI for `apx-agent` (apx-linux-host.md, step 5), then the preflight:
```
sudo sh -c 'set -a; . /home/apx/.apx/apx.env; set +a; bash deploy/linux/preflight.sh'
```

6.5 New secrets, never copied from the old host (apx-linux-host.md, step 4): [RYAN-ADMIN] generate a new App private key (3.1), copy it over with `scp`,
then install it and shred the copy:
```
sudo install -m 600 -o apx -g apx /tmp/app.pem /home/apx/.apx/app.pem
sudo shred -u /tmp/app.pem
```
[RYAN-ADMIN] mint a new model token with `claude setup-token` on your laptop, then write it with a hidden prompt (never in shell history or argv):
```
read -rs T < /dev/tty; printf '%s' "$T" | sudo install -m 600 -o apx-agent -g apx-agent /dev/stdin /home/apx-agent/.apx/claude-oauth; unset T
```

6.6 Settings: start from the template in apx-linux-host.md step 4 and compare with the saved copy (`$E/apx.env`) instead of copying it back. Shadow mode: no
`APX_SHADOW` line at all (shadow is the default; only `APX_SHADOW=0` turns it off), and no `APX_CUTOVER`, `APX_AUTHORITATIVE` or `APX_LIVE`. Check:
```
sudo grep -nE '^(APX_SHADOW|APX_CUTOVER|APX_AUTHORITATIVE|APX_LIVE|APX_UPDATE_LIVE)' /home/apx/.apx/apx.env
```
No output is expected. Remove any live drop-in for the updater for now (`sudo systemctl revert apx-updater.service` should remove every drop-in for that unit; **unverified** on the host).

6.7 Doctor and egress probe. Every doctor line must be PASS (it checks key and token modes, the App's permissions and installations, that the sandbox accounts
cannot read the key, the kit sha and each repo's host tools; `src/autopilot/apx/doctor.py`). The probe must end with `sealed`.
```
cd /srv/apx/current
sudo -u apx -H sh -c 'set -a; . /home/apx/.apx/apx.env; set +a; PYTHONPATH=/srv/apx/current/src /srv/apx/venv/bin/python -m autopilot.apx.daemon --doctor'
cd ~/autopilot
sudo bash deploy/linux/egress-probe.sh
```

6.8 One dry pass, which changes nothing (`--once` without `--live` and without `APX_LIVE`); its `DRY-RUN ...` lines should make sense:
```
cd /srv/apx/current
sudo -u apx -H sh -c 'set -a; . /home/apx/.apx/apx.env; set +a; PYTHONPATH=/srv/apx/current/src /srv/apx/venv/bin/python -m autopilot.apx.daemon --once'
```

6.9 [RYAN-ADMIN] Unpause one repo (autopilot is the lowest-risk one), then start the timers and watch a pass:
```
gh variable delete AUTOPILOT_PAUSED --repo RyanJHamby/autopilot
sudo systemctl enable --now apx.timer apx-updater.timer
journalctl -u apx.service -f
```

## 7. Back to normal

- [ ] Evidence tarball made and its checksum recorded (4.6); copied off the host if it was re-imaged.
- [ ] Old App key deleted on GitHub, new one installed; old model token revoked, new one installed (3.1, 3.2, 6.5).
- [ ] Webhook secret rotated on both sides, if `APX_WEBHOOK_SECRET_FILE` is set (3.4).
- [ ] GitHub checks in section 4 of apx-compromise.md clean on all three repos, or every finding reverted on a normal PR.
- [ ] Doctor all PASS, probe `sealed`, preflight clean (6.4, 6.7).
- [ ] `apx.env` in shadow (6.6); updater dry (no live drop-in) until a week of shadow looks right.
- [ ] `AUTOPILOT_PAUSED` removed one repo at a time, each after a pass you watched; the installation unsuspended if you suspended it.
- [ ] Status `ok`: `PYTHONPATH="$HOME/autopilot/src" python3 -m autopilot.apx.status --print`.
- [ ] Shadow period as in "Shadow week: what to look at" in [apx-runbook.md](apx-runbook.md), then cutover per repo as before.
- [ ] A journal entry with what happened, what was found, and what was changed. Keep the evidence until you decide it is no longer needed.

## Rehearsal (dry run)

Goal: walk sections 1, 2, 4 and 6 in about 15 minutes without revoking anything. Nothing here touches a key, a token or a GitHub setting. Do it when no PR is
waiting on `apx / guard`, because apx posts no checks while its timers are off. Time it with `date -u` at the start and the end.

R1. The HOLD switch, as `apx`. HOLD stops the **live** updater from adopting or rolling back anything (`run_update` in `src/autopilot/apx/update.py`); a dry
updater adopts nothing anyway and does not read it, so on a dry host this only proves you can set and clear it. Look first: a HOLD that says "rolled back" is
the updater's alarm and must not be deleted unread.
```
sudo cat /srv/apx/HOLD
sudo -u apx touch /srv/apx/HOLD
ls -la /srv/apx/HOLD
sudo -u apx rm /srv/apx/HOLD
```
Skip the `rm` if the first command printed something.

R2. Stop and start the timers (1.1 and 6.9 without the GitHub steps). Run this between passes (check `systemctl is-active apx.service` says `inactive`):
```
sudo systemctl disable --now apx.timer apx-updater.timer
systemctl is-enabled apx.timer apx-updater.timer
sudo systemctl enable --now apx.timer apx-updater.timer
systemctl list-timers 'apx*'
```
Expect `disabled` twice, then both timers listed with a next run within two minutes. Then preview `retire.sh` (no `DO=1`, so it changes nothing):
```
cd ~/autopilot
sudo bash deploy/linux/retire.sh
```

R3. Evidence export to `/tmp` instead of `/root`: run 1.2 with `E=/tmp/apx-drill-$STAMP` (the `install -d -m 700 -o root` line keeps it root-only), then 4.1 to
4.6 with `/tmp` in place of `/root` in 4.6. Skip 1.3 and 1.4. Check that the tarball lists what you expect, then remove it:
```
sudo tar -tzf "/tmp/apx-drill-$STAMP.tar.gz" | head -50
sudo rm -rf "/tmp/apx-drill-$STAMP" "/tmp/apx-drill-$STAMP.tar.gz" "/tmp/apx-drill-$STAMP.sha256"
```
For 4.6 in the drill, use `sudo tar -C /tmp -czf "/tmp/apx-drill-$STAMP.tar.gz" "apx-drill-$STAMP"`.

R4. Rollback and rebuild previews. `release.sh` and `bootstrap.sh` both print their steps with `DRY_RUN=1` and change nothing. The rollback target is the release
in `previous`; if that link is missing, there is no rollback target:
```
cd ~/autopilot
PREV=$(basename "$(readlink /srv/apx/previous)")
DRY_RUN=1 APX_SHA="$PREV" bash deploy/linux/release.sh
DRY_RUN=1 APX_SHA="$PREV" ADMIN_USER=ryan bash deploy/linux/bootstrap.sh
```
A real rollback is the same bootstrap command with `sudo` in front and without `DRY_RUN=1`; do not run it in the drill. `release.py`'s own `rollback()` runs
only inside the live updater, after a failed canary; it has no command of its own.

R5. Integrity checks 5.3 to 5.5, the egress probe and the doctor (6.7). All read-only. The probe must end `sealed`, every doctor line PASS.

R6. Walk the pages you would need, without clicking: the App's Private keys page, the Install page with the Suspend button, and your Claude account settings
(find where a `setup-token` token is revoked, and write it into this page in a PR, since it is **unverified** here).

### Record it as proof of work

From your laptop, in your admin repo, wrap the read-only parts in `pow run` over SSH, the same shape your VPS cutover notes use. `pow run` records the laptop's
hardware, so name the server in the journal entry:
```
pow run apx-drill-probe -- ssh -t $ADMIN_USER@$VPS_HOST 'cd autopilot && sudo bash deploy/linux/egress-probe.sh'
pow run apx-drill-doctor -- ssh -t $ADMIN_USER@$VPS_HOST "cd /srv/apx/current && sudo -u apx -H sh -c 'set -a; . /home/apx/.apx/apx.env; set +a; PYTHONPATH=/srv/apx/current/src exec /srv/apx/venv/bin/python -m autopilot.apx.daemon --doctor'"
pow run apx-drill-retire-preview -- ssh -t $ADMIN_USER@$VPS_HOST 'cd autopilot && sudo bash deploy/linux/retire.sh'
pow run apx-drill-rollback-preview -- ssh -t $ADMIN_USER@$VPS_HOST 'cd autopilot && DRY_RUN=1 APX_SHA=$(basename $(readlink /srv/apx/previous)) bash deploy/linux/release.sh'
```
Then `pow log "apx Linux compromise drill: start and end time, which steps ran, what did not match docs/apx-compromise-linux.md"`, and fix this page in a PR
for anything that did not match. Change "None of it has been run on the host yet" at the top once a drill has run.
