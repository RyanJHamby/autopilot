# apx compromise runbook (backlog S6)

For the apx off-Actions executor on the Mac: three accounts (`apx`, `apx-ci`, `apx-agent`), one GitHub App (`autopilot-apx`), three repos
(`RyanJHamby/autopilot`, `RyanJHamby/drillpad-workspace`, `RyanJHamby/stencil`). Background: `docs/apx-app.md`, `docs/apx-runbook.md`,
`docs/apx-backlog.md`, `policy/CONSTITUTION.md`.

How to read this:
- **[RYAN-SUDO]** = run in Terminal.app by Ryan. Agents never run `sudo`.
- **[RYAN-ADMIN]** = needs Ryan's GitHub admin login, GitHub web UI, Claude account or Vercel. An agent cannot do it.
- No tag = read-only, any session with a `gh` login can run it.
- **unverified** = derived by reasoning from the repo, not confirmed on the real host or from GitHub/Anthropic documentation.
- Written 2026-10-29 from the repo only. None of these commands were run on the live host. `tests/test_apx_compromise_doc.py` checks that
  every env var, repo path, host path and module named here still exists in the repo; it cannot check that the commands work.

Rule of thumb: if you are unsure which account is affected, assume `apx` and do sections 1, 3 and 4. Rotation is cheap; a leaked App key is not.

## 1. Stop apx (under a minute)

Do 1.1 to 1.4 in order. Together they: unload the timer, stop it coming back at boot, make every repo's planner return no actions, and
make sure no half-finished pass is still running.

1.1 [RYAN-SUDO] Unload the daemon (label from `deploy/launchd/com.autopilot.apx.daemon.plist`):
```
sudo launchctl bootout system/com.autopilot.apx
```
1.2 [RYAN-SUDO] Stop it reloading at the next boot:
```
sudo launchctl disable system/com.autopilot.apx
```
1.3 [RYAN-ADMIN] Set `AUTOPILOT_PAUSED` on all three repos. This is a repo Actions variable, not a host env var: the planner reads it through
the App and returns zero actions for a paused repo (`src/autopilot/apx/planner.py`, `enabled`).
```
gh variable set AUTOPILOT_PAUSED --body true --repo RyanJHamby/autopilot
gh variable set AUTOPILOT_PAUSED --body true --repo RyanJHamby/drillpad-workspace
gh variable set AUTOPILOT_PAUSED --body true --repo RyanJHamby/stencil
```
1.4 [RYAN-SUDO] Make sure `APX_LIVE` is not set anywhere it could be picked up. The daemon only acts live when `--live` AND `APX_LIVE=1`
(`src/autopilot/apx/daemon.py`). The plist exports it inside its command string, so unloading (1.1) is what removes it; the settings file
should not contain it:
```
sudo grep -n '^APX_LIVE' /Users/apx/.apx/apx.env
```
No output is the expected result. If a line prints, delete it:
```
sudo -u apx -H sed -i '' '/^APX_LIVE/d' /Users/apx/.apx/apx.env
```
1.5 [RYAN-SUDO] Kill anything still running as the three accounts (a pass can hold a long agent run):
```
sudo pkill -u apx
sudo pkill -u apx-ci
sudo pkill -u apx-agent
```
If you also want the hard stop that does not depend on the host: [RYAN-ADMIN] GitHub > Settings > Developer settings > GitHub Apps >
`autopilot-apx` > Install App > the cog next to your account > Suspend (the stop `docs/apx-app.md` section 5 names). Suspension blocks new
tokens; whether it also kills installation tokens already minted (they last up to an hour) is **unverified**.

Verify it stopped:
```
sudo launchctl print system/com.autopilot.apx
```
Expect an error ("Could not find service"). Then:
```
pgrep -lf autopilot.apx
```
Expect no output. Then confirm the pause landed:
```
gh variable get AUTOPILOT_PAUSED --repo RyanJHamby/autopilot
```
Expect `true` (repeat for the other two repos). The local status file goes `stale` only after 15 minutes
(`STALE_AFTER` in `src/autopilot/apx/status.py`), so it is not an instant check:
```
PYTHONPATH=/Users/Shared/apx/autopilot/src /usr/bin/python3 -m autopilot.apx.status --print
```
`stale: apx last finished a pass ...` after 15 minutes is the expected final confirmation. Your `com.autopilot.apx.watch` notifier will
also fire; that is expected, leave it running.

Write down the time you stopped (`date`). Installation tokens minted before it stay valid up to 1 hour (`src/autopilot/apx/app_auth.py`).

## 2. Triage: which account, what it can reach

What each account holds, derived from `deploy/apx-ci-account.sh`, `deploy/apx-agent-account.sh`, `deploy/apx-install-mac.sh` and `src/autopilot/apx/`:

| Account | Holds | Can reach |
|---|---|---|
| `apx` (orchestrator) | App private key `/Users/apx/.apx/app.pem`, App id, settings `/Users/apx/.apx/apx.env`, ledger DB, webhook secret file if configured (`APX_WEBHOOK_SECRET_FILE`, location **unverified**). Not the Claude token once `deploy/apx-agent-account.sh` has run (it deletes that copy). | GitHub as the App on the three repos: Contents, Pull requests, Issues, Checks write; Variables read (`docs/apx-app.md`). Can mint write tokens at will. Can post a check with any required name (rulesets accept any app until `autopilot.apx.pin --apply`, backlog S3). Can sudo to `apx-ci` and `apx-agent` without a password (`/etc/sudoers.d/apx-ci`, `/etc/sudoers.d/apx-agent`). Once a repo is in `APX_CUTOVER`, the merge lane can merge tier-0 PRs. It is a standard (non-admin) user. |
| `apx-ci` (runs PR code) | Nothing by design. Home `/Users/apx-ci`, work dir `/Users/apx-ci/work`. | Cannot read `/Users/apx/.apx/app.pem` (the install script probes this). Reads the world-readable `/Users/Shared/apx` (kit cache, code copy, status file: no secrets). Network egress is not restricted (backlog S4 open). While a job runs it holds a 1-hour installation token with the App's full write permissions in `APX_GIT_TOKEN` for the checkout (`src/autopilot/apx/sandbox.py` passes `token_for`, not the read-only token). The CI commands themselves run with a scrubbed environment (`ci_env` in `src/autopilot/apx/cilane.py`); whether PR code could still read the job's parent environment is **unverified**. No sudoers rule lets it become another user (**unverified** beyond the script's comments). |
| `apx-agent` (runs the model) | The Claude OAuth token `/Users/apx-agent/.apx/claude-oauth`, the `claude` CLI. | Anthropic API. Per task, one read-only (contents + metadata) token for one repository, 1 hour (`read_token_for`), so it cannot write to GitHub. Cannot read the App key or the apx home (probed by the install script). Network egress not restricted (S4 open). Its output comes back as data; `apx` makes the commit, after the kit patch check. |

Evidence to read before deciding (all [RYAN-SUDO], read-only):
```
sudo tail -n 200 /Users/apx/Library/Logs/apx.err.log
sudo tail -n 200 /Users/apx/Library/Logs/apx.log
sudo ls -lat /Users/apx-ci/work
sudo ls -lat /Users/apx-agent/work
sudo ls -la /Users/apx-agent/.apx /Users/apx/.apx
sudo last -20
```
Persistence checks (a compromised `apx` can edit the code that `apx-ci` and `apx-agent` execute, and the sudoers rules):
```
sudo ls -la /etc/sudoers.d
sudo cat /etc/sudoers.d/apx-ci /etc/sudoers.d/apx-agent
sudo -u apx -H git -C /Users/apx/autopilot status --short
sudo -u apx -H git -C /Users/Shared/apx/autopilot status --short
sudo ls -la /Library/LaunchDaemons
```
Expected: each sudoers file is the single line `apx ALL=(apx-ci) NOPASSWD:SETENV: ALL` or `apx ALL=(apx-agent) NOPASSWD:SETENV: ALL`; both clones show no
local changes (and `HEAD` is a commit you recognise: `git log -1`); the LaunchDaemons plist matches `deploy/launchd/com.autopilot.apx.daemon.plist`.
Note the header of that plist says to copy it to `/Library/LaunchDaemons/` but then names `com.autopilot.apx.plist` in the `chown`, `chmod` and
`bootstrap` lines; which file name is actually on the host is **unverified**, so list the directory first.

Decision guide:

| Signal | Treat as | Do |
|---|---|---|
| Unknown commits, branches, PRs or checks by the App; ruleset or variable changed; App key seen outside `/Users/apx/.apx` | `apx` | Sections 1, 3A, 3C, 3D, 4, integrity checks above, then 5 |
| Odd files or processes in `/Users/apx-ci/work`; a PR that printed or probed secrets; suspicious dependency or install script | `apx-ci` | Sections 1, 3A (its token was a write token), 3C, 4; then 5 |
| Unexpected Claude usage; a prompt-injected issue or PR comment; odd files in `/Users/apx-agent/work` | `apx-agent` | Sections 1, 3B, 4; then 5. The GitHub App key is not reachable from this account (probed) |
| Cannot tell | `apx` | Everything |

## 3. Rotation

Do these with apx stopped (section 1). Order: 3A, 3B, 3D, then run the doctor (3E).

### 3A. GitHub App private key [RYAN-ADMIN + RYAN-SUDO]

3A.1 [RYAN-ADMIN] GitHub > Settings > Developer settings > GitHub Apps > `autopilot-apx` > Private keys > **Generate a private key**. It downloads once.
The App id and installation ids do not change.

3A.2 [RYAN-ADMIN] On the same page, **Delete** the old key (match it by its fingerprint/created date). Do this now if the key may be leaked; the
cost is only that apx cannot authenticate until 3A.3 is done.

3A.3 [RYAN-SUDO] Install the new key where `APX_KEY_PATH` points (default `/Users/apx/.apx/app.pem`; confirm with
`sudo grep '^APX_KEY_PATH' /Users/apx/.apx/apx.env`), owner `apx`, mode 600:
```
sudo install -m 600 -o apx -g staff ~/Downloads/NEW-KEY-FILE.pem /Users/apx/.apx/app.pem
```
(Replace `NEW-KEY-FILE.pem` with the downloaded file name.) Then delete your downloaded copy and any other copy you made (look first:
`ls -la ~/Downloads/*.pem ~/.apx`; the runbook says your own `~/.apx/app.pem` should already be gone).

3A.4 Check it: run the doctor (3E). "app authentication" and "app id matches" must pass.

3A.5 [RYAN-ADMIN] Installation tokens already minted live up to 1 hour. If you need them dead sooner, suspend the installation (Install page) and
unsuspend after the hour. Whether deleting the key alone revokes them is **unverified**.

### 3B. Claude OAuth token [RYAN-ADMIN + RYAN-SUDO]

With the agent account in place the token lives only at `/Users/apx-agent/.apx/claude-oauth` (`deploy/apx-agent-account.sh`). If
`/Users/apx/.apx/claude-oauth` still exists, the split is not complete: delete it as part of this rotation.

3B.1 [RYAN-ADMIN] Revoke the old token. How to revoke a `claude setup-token` token in your Claude account is **unverified**: this repo does not document
it. Check your Claude account settings for a way to revoke it. If there is none, rotating the file below at least removes it from the host.

3B.2 [RYAN-ADMIN] Mint a new one with `claude setup-token` (as in `docs/apx-runbook.md` step 2) in your own login.

3B.3 [RYAN-SUDO] Write it with a hidden prompt (never in shell history, argv or a repo):
```
read -rs T < /dev/tty; printf '%s' "$T" | sudo -u apx-agent tee /Users/apx-agent/.apx/claude-oauth >/dev/null; unset T
sudo chmod 600 /Users/apx-agent/.apx/claude-oauth
sudo chown apx-agent:staff /Users/apx-agent/.apx/claude-oauth
```
3B.4 Check it with the doctor (3E): "agent account can read its own Claude token" must pass.

### 3C. Per-checkout read-only tokens (no action on disk)

There is no file to rotate. `read_token_for` in `src/autopilot/apx/app_auth.py` mints a contents+metadata, single-repo token per checkout, caches it in
memory only, and it expires in 1 hour; the CI lane's checkout token (`token_for`) is the same, but with write permissions. Rotating the key (3A)
stops new ones being minted; the ones already out expire on their own. Note the time you stopped (section 1) and treat 60 minutes after that as
the point at which none are valid (assuming the key was deleted, **unverified** as above). The git token is passed to git through its
environment, not written to the checkout (`src/autopilot/apx/gitops.py`), so a leftover checkout does not contain it.

### 3D. Webhook secret [RYAN-ADMIN + RYAN-SUDO]

This is the secret apx uses to sign ledger reports to the control plane (`src/autopilot/apx/report.py`). It lives in two places and they must match:
a file named by `APX_WEBHOOK_SECRET_FILE` in `/Users/apx/.apx/apx.env`, and the Vercel project env `APX_WEBHOOK_SECRET`
(`apps/control-plane/app/api/github/webhook/route.ts`). It is not GitHub's webhook secret (the App has webhooks off; the control plane's
`GITHUB_WEBHOOK_SECRET` is a different variable). If `APX_WEBHOOK_SECRET_FILE` is not set in your `apx.env`, backlog O3 is not done and there is
nothing to rotate; skip this section.
```
sudo grep '^APX_WEBHOOK_SECRET_FILE' /Users/apx/.apx/apx.env
```
3D.1 [RYAN-SUDO] Write a fresh value into that file (replace `PATH-FROM-ABOVE`):
```
openssl rand -hex 32 | sudo -u apx tee PATH-FROM-ABOVE >/dev/null
sudo chmod 600 PATH-FROM-ABOVE
```
3D.2 [RYAN-ADMIN] Put the same value in Vercel without showing it. The `rm`-then-`add` form is the usual Vercel CLI behaviour (**unverified** here;
the dashboard works too):
```
vercel env rm APX_WEBHOOK_SECRET production
sudo cat PATH-FROM-ABOVE | vercel env add APX_WEBHOOK_SECRET production
```
3D.3 [RYAN-ADMIN] Redeploy the control plane so it picks up the new value. Until both sides match, apx's reports are rejected; the reporter is
best effort and never blocks a run (`src/autopilot/apx/report.py`).

### 3E. Doctor (read-only) [RYAN-SUDO]

Same invocation as `deploy/apx-install-mac.sh` uses:
```
sudo -u apx -H env PATH=/Users/apx/.local/bin:/opt/homebrew/bin:/usr/bin:/bin sh -c 'set -a; . /Users/apx/.apx/apx.env; set +a; cd /Users/apx/autopilot && uv run python -m autopilot.apx.daemon --doctor'
```
Every line must be PASS. It checks key and token file modes, that the App has only the documented permissions, that it is installed on exactly the three
repos, that `apx-ci` and `apx-agent` cannot read the App key, and the kit sha (`src/autopilot/apx/doctor.py`).

## 4. What to check on GitHub afterwards (read-only `gh`)

Needs your `gh` login (admin on the repos). Set the repo, run the block, repeat for the other two repos. Look at everything since the earliest time
you think the compromise could have started.
```
R=RyanJHamby/autopilot
```
4.1 Branches: apx may only create `agent/*` (`policy/CONSTITUTION.md` section 5). Anything printed here is unexpected:
```
gh api "repos/$R/branches" --paginate --jq '.[].name | select(startswith("agent/") | not)'
gh api "repos/$R/git/matching-refs/heads/agent" --paginate --jq '.[].ref'
```
The second lists the `agent/*` branches; each should map to a PR or issue you recognise.

4.2 Recent commits (author, signature status, message). Unsigned or unknown ones are suspect:
```
gh api "repos/$R/commits?per_page=50" --jq '.[] | [.sha[0:8], .commit.author.date, (.author.login // "?"), .commit.verification.verified, (.commit.message | split("\n")[0])] | @tsv'
```
4.3 PRs, with who opened them and whether they merged:
```
gh pr list --repo "$R" --state all --limit 50 --json number,title,author,headRefName,createdAt,mergedAt
```
4.4 Workflows and `.github` must not change through apx (the App has no Workflows permission, `docs/apx-app.md`), so any change is a finding:
```
gh api "repos/$R/commits?path=.github&per_page=10" --jq '.[] | [.sha[0:8], .commit.author.date, (.author.login // "?"), (.commit.message | split("\n")[0])] | @tsv'
```
4.5 Ruleset unchanged. List them, then compare the `required_status_checks` and `bypass_actors` with what you expect (for `integration_id` pins see
`src/autopilot/apx/pin.py`; its default run is a dry run that only reads):
```
gh api "repos/$R/rulesets" --jq '.[] | [.id, .name, .enforcement] | @tsv'
gh api "repos/$R/rulesets/RULESET-ID" --jq '{bypass_actors, rules: [.rules[] | {type, parameters}]}'
python3 -m autopilot.apx.pin --repo "$R"
```
(Replace `RULESET-ID` with the id of `autopilot-main`.)

4.6 Deploy keys, hooks, Actions secrets and variables. The App cannot read or write secrets or keys, so any surprise here did not come from apx:
```
gh api "repos/$R/keys" --jq '.[] | [.id, .title, .read_only, .created_at] | @tsv'
gh api "repos/$R/hooks" --jq '.[] | [.id, .config.url, .active] | @tsv'
gh api "repos/$R/actions/secrets" --jq '.secrets[] | [.name, .updated_at] | @tsv'
gh api "repos/$R/actions/variables" --jq '.variables[] | [.name, .value, .updated_at] | @tsv'
```
Check `AUTOPILOT_ENABLED`, `AUTOPILOT_PAUSED`, `AUTOPILOT_HOLD_UNTIL` values and times.

4.7 For any merged PR you do not recognise, see which app posted its checks (a fake pass from another app is possible until S3 is applied):
```
gh api "repos/$R/commits/SHA/check-runs" --jq '.check_runs[] | [.name, .app.slug, .conclusion] | @tsv'
```
4.8 The App itself: GitHub > Settings > Developer settings > GitHub Apps > `autopilot-apx` [RYAN-ADMIN] should show only the permissions in `docs/apx-app.md`
and be installed on exactly the three repos. The doctor (3E) checks this too.

If anything is found: leave apx stopped, do not delete evidence (do not delete branches yet), revert on a normal PR, and tell Ryan.

## 5. Resume safely: shadow first, then cutover

5.1 Preconditions: section 3 done, doctor all PASS, section 4 clean, and the integrity checks in section 2 clean. If either code clone differs from
`origin/main` and you did not do it, re-clone (look at the target before deleting anything).
```
sudo -u apx -H git -C /Users/apx/autopilot fetch -q origin
sudo -u apx -H git -C /Users/apx/autopilot diff --stat origin/main
sudo -u apx -H git -C /Users/Shared/apx/autopilot fetch -q origin
sudo -u apx -H git -C /Users/Shared/apx/autopilot diff --stat origin/main
```
5.2 [RYAN-SUDO] Go back to shadow: no `APX_CUTOVER`, no `APX_AUTHORITATIVE`, `APX_SHADOW` unset (shadow is the default,
`src/autopilot/apx/daemon.py`). Note what was there first so you can restore it later:
```
sudo grep -nE '^(APX_CUTOVER|APX_AUTHORITATIVE|APX_SHADOW|APX_LIVE)' /Users/apx/.apx/apx.env
```
Delete any lines it prints (the file has paths and ids only, no secrets, per `docs/apx-runbook.md`). Edit with `sudo -u apx` and an editor you trust.

5.3 [RYAN-ADMIN] Unpause one repo first (autopilot is the lowest-risk one):
```
gh variable delete AUTOPILOT_PAUSED --repo RyanJHamby/autopilot
```
5.4 [RYAN-SUDO] Dry run, changes nothing (`--once` without `--live` and without `APX_LIVE`):
```
sudo -u apx -H env PATH=/Users/apx/.local/bin:/opt/homebrew/bin:/usr/bin:/bin sh -c 'set -a; . /Users/apx/.apx/apx.env; set +a; cd /Users/apx/autopilot && uv run python -m autopilot.apx.daemon --once'
```
It should print `DRY-RUN ...` lines that make sense.

5.5 [RYAN-SUDO] Re-enable and reload the timer. The plist file name on the host is **unverified** (see section 2), so list it first:
```
ls /Library/LaunchDaemons | grep apx
sudo launchctl enable system/com.autopilot.apx
sudo launchctl bootstrap system /Library/LaunchDaemons/PLIST-FILE-FROM-ABOVE
```
5.6 Shadow period: follow "Shadow week: what to look at" in `docs/apx-runbook.md`. Compare `apx / guard` with `guard / guard`. How long is your call; the
runbook used a week.
```
PYTHONPATH=/Users/Shared/apx/autopilot/src /usr/bin/python3 -m autopilot.apx.status --print
```
Expect `ok`.

5.7 Unpause the other repos the same way as 5.3, one at a time.

5.8 Cutover (only after shadow looks right): follow "Full cutover of one repo" in `docs/apx-runbook.md` step by step (`APX_CUTOVER`, refresh clones, doctor,
watch one agent run and one merge, then disable Actions). Agent runs stay blocked unless `APX_AGENT_USER` is set. If S3 is not applied, do it first
(`python3 -m autopilot.apx.pin`, [RYAN-ADMIN]; dry run by default).

## 6. Drill (rehearse without breaking anything)

Goal from the backlog: complete in under 15 minutes. Time yourself. Parts 6.1 to 6.5 only read. 6.6 is optional and briefly pauses apx.

6.1 You can run sudo in Terminal.app and your `gh` login is admin:
```
gh auth status
gh api repos/RyanJHamby/autopilot --jq .permissions.admin
```
Expect `true`.

6.2 You know the live names. Compare with what this runbook assumes (sections 1 and 5):
```
ls /Library/LaunchDaemons | grep apx
sudo launchctl print system/com.autopilot.apx
sudo cat /etc/sudoers.d/apx-ci /etc/sudoers.d/apx-agent
```
Fix this document in a PR if a name differs (the test will not catch host-only differences).

6.3 You can reach the web pages (look, do not click): the App's Private keys page, the Install page with the Suspend button, the Vercel project env page (or
`vercel whoami`, `vercel env ls` for names only).

6.4 Run the section 4 commands on all three repos and save a baseline outside any repo, so a real incident has something to compare to:
```
{ for R in RyanJHamby/autopilot RyanJHamby/drillpad-workspace RyanJHamby/stencil; do echo "== $R"; gh api "repos/$R/rulesets" --jq '.[] | [.id, .name, .enforcement] | @tsv'; gh api "repos/$R/keys" --jq '.[] | [.id, .title] | @tsv'; gh api "repos/$R/actions/secrets" --jq '.secrets[] | .name'; done; } > ~/apx-baseline.txt
```
6.5 Doctor passes now (3E) and the status file says `ok`.

6.6 Optional live rehearsal of section 1 and 5.5. Only when no PRs are open on the three repos (`gh pr list --repo RyanJHamby/autopilot`; repeat)
and the repos are in shadow or unpaused-and-idle, because apx stops posting checks while it is down. Run 1.1, check with the `print` command in
section 1, then `sudo launchctl bootstrap system /Library/LaunchDaemons/PLIST-FILE` and confirm the next tick (up to 2 minutes, `StartInterval` 120) updates the
status file. Skip 1.2, 1.3 and 1.5 for the rehearsal, or undo them immediately (`enable`, `gh variable delete AUTOPILOT_PAUSED`).

6.7 Do not rehearse key or token rotation for real; instead walk the GitHub pages in 6.3 and read 3A and 3B once. Record the total time and anything that
did not match this document.
