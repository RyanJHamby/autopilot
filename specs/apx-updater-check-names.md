---
id: apx-updater-check-names
goal: "The apx updater requires the check names apx actually posts for autopilot in the current mode (Settings.contexts), so a cut-over autopilot (guard / guard + test) can still be adopted, and a shadow autopilot keeps requiring apx / guard + apx / build. Tests cover both modes."
acceptance:
  - uv run pytest tests/test_apx_update_main.py tests/test_apx_update_verify.py tests/test_apx_update.py
  - uv run ruff check .
scope:
  - src/autopilot/apx/update_main.py
  - tests/test_apx_update_main.py
non_goals:
  - do not change update_verify.py or any other trust rule (Verified commit, fast-forward, owner merged it, hold label, settle delay, apx App as the poster)
  - do not trust Actions' checks; only check runs posted by the apx App count
  - no new settings or environment variables; reuse Settings.contexts
  - no new dependencies
risk_tier: 3
max_runs: 3
autonomy: inherit
---

Found on 2026-11-02 right after cutting autopilot over to apx (`APX_CUTOVER` includes `RyanJHamby/autopilot`).

`src/autopilot/apx/update_main.py` hardcodes `CHECKS = ("apx / guard", "apx / build")`, "the shadow names autopilot gets from apx",
and passes `required_checks=list(CHECKS)` to `run_update`. Once autopilot is cut over (or authoritative, or shadow is off),
`Settings.contexts("RyanJHamby/autopilot")` in `src/autopilot/apx/daemon.py` switches apx to the ruleset's required names
(`REQUIRED_CONTEXTS`: `guard / guard` and `test`), so the PR heads never carry `apx / ...` from the apx App and every update is
skipped with `required check 'apx / guard' is not green from the apx App`. Auto-deploy of autopilot is dead in that mode.

Fix: build `required_checks` from `s.contexts(REPO)` (its `guard` and `ci` values, in that order) instead of the constant, so the
updater always requires exactly the two names apx posts for autopilot right now. Keep `update_verify.verify`'s rule that only
check runs from the apx App count, unchanged.

Tests in `tests/test_apx_update_main.py` (extend the existing `Settings.from_env` monkeypatch pattern there):
- shadow settings (autopilot not in cutover/authoritative): `run_update` receives `["apx / guard", "apx / build"]`;
- cutover settings (autopilot in `cutover`): `run_update` receives `["guard / guard", "test"]`.

Risk tier 3 on purpose: this file decides what code the host trusts and runs, so the owner reviews and merges it by hand.
After it merges, the updater's own copy does not update itself; the owner refreshes it:
the updater copy was cloned from `/Users/Shared/apx/autopilot`, so pull that first, then move the copy:
`sudo -u apx -H git -C /Users/Shared/apx/autopilot pull --ff-only && sudo -u apx -H git -C /Users/Shared/apx/updater fetch -q && sudo -u apx -H git -C /Users/Shared/apx/updater checkout -q --detach <merged sha>`.

Run `ap handshake specs/apx-updater-check-names.md` to see whether the system accepts it.
