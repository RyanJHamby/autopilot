---
id: apx-deploy-docs
goal: "The apx deploy docs and script headers give commands that work as written: no VAR=value placed before sudo (sudo drops it), the daemon plist header installs the file under the name launchd and apx-switch-to-current.sh expect, and the host-move doc installs that plist before the switch. A test keeps all three true."
acceptance:
  - uv run pytest tests/test_deploy_docs.py
  - uv run ruff check .
scope:
  - docs/apx-host-move.md
  - docs/apx-runbook.md
  - deploy/apx-retire-host.sh
  - deploy/apx-updater-setup.sh
  - deploy/launchd/com.autopilot.apx.daemon.plist
  - tests/test_deploy_docs.py
non_goals:
  - no change to what any script does; only comments, docs and the new test
  - no new dependencies
  - do not touch .github/, .autopilot/, kit/, policy/ or any other deploy script
risk_tier: 1
max_runs: 3
autonomy: inherit
---

Found while moving apx to a new Mac on 2026-11-02 (docs/apx-host-move.md). Three bugs, each of which cost a retry:

1. **Variable before sudo.** `sudo` resets the environment, so `VAR=1 sudo bash x.sh` runs `x.sh` WITHOUT `VAR`. The fix is
   `sudo VAR=1 bash x.sh`. Known places:
   - `docs/apx-host-move.md` (cutover step 1): `DO=1 sudo bash deploy/apx-retire-host.sh` only previews again.
   - `deploy/apx-retire-host.sh` header, same line.
   - `deploy/apx-updater-setup.sh` header: `DRY_RUN=1 sudo bash deploy/apx-updater-setup.sh   # preview`. This one is dangerous:
     `DRY_RUN` is dropped, so the "preview" performs the real install. The preview needs no sudo at all (it only prints), so the
     header should say `DRY_RUN=1 bash deploy/apx-updater-setup.sh`, matching the other deploy scripts.
   `DRY_RUN=1 bash ...` without sudo is correct and must stay.

2. **Daemon plist installed under the wrong name.** The header of `deploy/launchd/com.autopilot.apx.daemon.plist` says
   `sudo cp deploy/launchd/com.autopilot.apx.daemon.plist /Library/LaunchDaemons/`, which creates
   `/Library/LaunchDaemons/com.autopilot.apx.daemon.plist`, but its next lines (chown, chmod, bootstrap) and
   `deploy/apx-switch-to-current.sh` all use `/Library/LaunchDaemons/com.autopilot.apx.plist`. The copy must name the target file.

3. **Host-move doc skips the daemon plist.** `deploy/apx-switch-to-current.sh` exits with `missing a plist` unless
   `/Library/LaunchDaemons/com.autopilot.apx.plist` already exists. `docs/apx-host-move.md` never installs it. Add the install
   (cp to the right name, chown root:wheel, chmod 644; no bootstrap, the switch script starts it) to the new-Mac steps before the
   switch in section 4, and say why.

`tests/test_deploy_docs.py` (pure file reads, no subprocess, no sudo) must fail on today's main and pass after the fix:
- no line in `docs/**/*.md`, `deploy/*.sh` or `deploy/launchd/*.plist` matches an assignment directly before sudo
  (regex like `\b[A-Z_][A-Z0-9_]*=\S*\s+sudo\b`);
- every `cp ... /Library/LaunchDaemons/...` line in `deploy/launchd/*.plist` headers names a target file equal to that plist's
  `Label` + `.plist`;
- `docs/apx-host-move.md` mentions `/Library/LaunchDaemons/com.autopilot.apx.plist` before it mentions `apx-switch-to-current.sh`
  in the cutover section.

Run `ap handshake specs/apx-deploy-docs.md` to see whether the system accepts it.
