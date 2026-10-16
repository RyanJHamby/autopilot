---
id: report-cost
goal: "`ap report` also shows estimated run-points per merged PR per repo, using the same weights as apps/control-plane/lib/ledger.ts (haiku 1, sonnet 3, opus 15 x turn cap)."
acceptance:
  - uv run pytest tests/test_report.py
  - uv run ruff check .
scope:
  - src/autopilot/report.py
  - src/autopilot/cli.py
  - tests/test_report.py
non_goals:
  - no claims of dollar cost (the Max pool exposes none); label values as estimates
risk_tier: 1
max_runs: 3
autonomy: inherit
---
Count `agent-exec` runs via `gh run list` per repo and divide by merged agent PRs. Pure function + test first.
