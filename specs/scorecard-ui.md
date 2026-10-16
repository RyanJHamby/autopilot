---
id: scorecard-ui
goal: "The control-plane portfolio shows, per project, the last-14-day outcome numbers from ap report (opened, merged, closed, reverted, merge rate) read from a new `scorecard` JSON column fed by `ap export-state --sql`."
acceptance:
  - uv run pytest tests/test_cli.py -k scorecard
  - npm --prefix apps/control-plane test
scope:
  - src/autopilot/cli.py
  - tests/test_cli.py
  - apps/control-plane/lib/store.ts
  - apps/control-plane/lib/store.test.ts
  - apps/control-plane/app/page.tsx
non_goals:
  - do not add or edit files under apps/control-plane/supabase/ (a human writes migrations)
risk_tier: 2
max_runs: 3
autonomy: inherit
---
Needs a migration first (human). Leave this spec on `hold` until the owner adds `0006_scorecard.sql`.
