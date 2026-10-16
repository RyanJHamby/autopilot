---
id: ap-digest
goal: "`ap digest [--out FILE]` prints (or writes) a markdown digest of the last 24h: agent PRs merged, PRs waiting on the owner, failed runs, paused/held repos. Read-only, zero model usage."
acceptance:
  - uv run pytest tests/test_digest.py
  - uv run ruff check .
scope:
  - src/autopilot/digest.py
  - src/autopilot/cli.py
  - tests/test_digest.py
  - README.md
non_goals:
  - no network calls inside digest.py (pure functions over fetched data, like report.py)
  - no sending anything anywhere; output goes to stdout or a local file only
  - no new dependencies
risk_tier: 2
max_runs: 3
autonomy: inherit
---
Mirror `src/autopilot/report.py`: pure formatter in `digest.py`, thin `cmd_digest` in cli.py that fetches via `gh`.
The owner copies the output into their own local notes by hand or cron; this command only writes the file it is given.
