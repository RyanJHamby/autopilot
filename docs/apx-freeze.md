# apx and the work-hours freeze

Finding (from the code, before this change): apx did NOT read `policy/time.yaml`. Its only time control was the optional
`APX_ACTIVE_WINDOW` environment setting (`apx/window.py`); unset meant "always on", so on the VPS agent runs, checks and merges would
have started inside Mon-Fri 08:30-18:30 ET.

Now: `src/autopilot/apx/freeze_gate.py` asks the one resolver (`autopilot.freeze.check_file`, which reads `policy/time.yaml`) and holds work.

| Where | What it does |
|---|---|
| `daemon.main` | idle heartbeat, no pass, when frozen |
| `daemon.run_once` / `_run_once_locked` | returns the idle line before any API call, so also covers callers other than `main` |
| `executor.execute(gate=...)` | asks the gate before EACH live action (agent run, CI fix, merge, branch update, check run). A pass that begins at 08:29 stops at 08:30. Held actions open no ledger row and are planned again next pass. |
| `update_main.main` | the updater does not fetch, run tests or swap inside the freeze |

Rules: any resolver, policy-file or clock error means frozen (a bad file falls back to the default window and ignores `lift`);
no flag or environment variable lifts it (only a date in `time.yaml` `lift.dates`); `APX_ACTIVE_WINDOW` is ANDed with it, so it can
only narrow the window. The picker (`picker.py`, pure allocation) and `ap queue` (read-only, local files) start nothing and are unchanged.

## Check runs: question for Ryan

apx posts `guard` / `build` / `test` check runs on PRs. That is not a commit, but it is activity on personal repos and it runs PR
code on the VPS. Is it a "change to personal repos during work hours"? Not decided here. Default: gated too. One setting,
`defaults.apx_freeze_gates_check_runs` in `policy/portfolio.yaml` (true now). Only the literal `false` lets check runs proceed in the
window (agent runs, merges and branch updates stay held either way); anything missing or malformed keeps them held.
Cost of true: PRs opened during the day get no checks until 18:30 ET.

Tests: `tests/test_apx_freeze_gate.py` (09:00 ET Monday after 2026-11-16 with a frozen clock; DST, `lift`, broken-policy cases).
Not verified: a real VPS pass, and that the installed release tree on the VPS contains `policy/time.yaml` (without it the default
window applies, which is the same window but ignores `lift`).
