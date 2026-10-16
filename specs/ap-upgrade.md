---
id: ap-upgrade
goal: "`ap upgrade REPO_CLONE --kit OWNER/REPO@SHA` bumps only the pinned kit sha in an already-central repo's caller workflows and refuses if any other line differs from what `ap init` would write."
acceptance:
  - uv run pytest tests/test_cli.py -k upgrade
  - uv run ruff check .
scope:
  - src/autopilot/cli.py
  - tests/test_cli.py
non_goals:
  - never edits .autopilot/repo.yaml or merge-policy.yaml (owner-owned)
  - never pushes; leaves a branch like `ap init` does
risk_tier: 2
max_runs: 3
autonomy: inherit
---
Reuse `init_repo(..., central=...)`. The refusal rule is the point: a hand-edited caller must not be silently overwritten.
