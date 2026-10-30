---
id: cost-controls
goal: "The apx executor can pass a dollar cap (`--max-budget-usd`) to `claude`, records the `total_cost_usd` each run reports, and treats a budget stop as a named failure; model prices live in one dated file that `ap report` reads instead of the hard-coded 1/3/15 weights."
acceptance:
  - uv run pytest tests/test_apx_claude_runner.py tests/test_report.py tests/test_pricing.py
  - uv run ruff check .
scope:
  - src/autopilot/pricing.py
  - src/autopilot/report.py
  - src/autopilot/apx/claude_runner.py
  - tests/test_pricing.py
  - tests/test_report.py
  - tests/test_apx_claude_runner.py
non_goals:
  - no edits to policy/**, kit/**, apps/control-plane/** (protected; Ryan applies "Part B" below)
  - no dollar figures invented: the cap value is Ryan's to choose, so the code takes it as an argument and defaults to no cap
  - no new dependencies
  - do not change the control-plane request body (apx/report.py); that needs apps/control-plane/app/api/**, which is protected
risk_tier: 2
max_runs: 3
autonomy: inherit
---

## Why

Today the only spend controls are counts: runs per day, open PRs, a turn cap (<= 60) and a circuit breaker (`kit/runtime/gate.py`).
A turn is not a unit of money: a 40-turn Opus run and a 40-turn Haiku run differ by a large factor, and a turn that reads a large
file costs more than one that does not. `ledger.ts` and `report.py` weight runs 1/3/15 (haiku/sonnet/opus), which the dated price
note in the vault (`as_of 2026-10-29`: Haiku $0.10, Sonnet $2, Opus $4 per million input tokens) does not support. That comparison
is Ryan's inference from one source, not a checked fact, which is why the weights should come from a file with a date on it.

## What was checked on 2026-10-29 (interactive login on Ryan's machine, claude 2.1.312, not the CI token)

- `claude -p --output-format json` returns `total_cost_usd` on a Max-plan login. A trivial one-turn Haiku call reported a small
  non-zero value. This contradicts the old non-goal in `specs/report-cost.md` ("the Max pool exposes none") for this login.
- `--max-budget-usd 0.000001` stopped the run with `subtype: error_max_budget_usd`, `is_error: true`,
  `terminal_reason: budget_exhausted`. It had already spent about $0.003 when it stopped, so the cap is checked between turns and a
  run can overshoot it by one turn. Treat it as a soft cap.
- NOT checked: whether the CI path (`claude-code-action` with `CLAUDE_CODE_OAUTH_TOKEN`) reports `total_cost_usd` or honours the
  flag the same way. Part B step 1 below proves that before anything relies on it.

## Part A: what the agent builds (all inside `scope`)

1. `src/autopilot/pricing.py`: `load_prices(path)` reads `policy/pricing.yaml` (format below) and returns per-model input/output
   prices plus `as_of`, `review_by`, `source`. `is_stale(prices, today)` is true after `review_by`. `weight(model)` returns the model's
   price relative to the cheapest listed model, so the report keeps a unitless score. A missing or unparsable file raises a clear error;
   the report falls back to the old weights and says so on the line it prints (never silently).
2. `src/autopilot/report.py`: build `_WEIGHT` from `pricing.weight` when the file loads, add `haiku`, keep the old table as the
   labelled fallback. Output still says "estimate".
3. `src/autopilot/apx/claude_runner.py`:
   - `build_argv(..., max_budget_usd: float | None = None)` appends `--max-budget-usd <n>` only when given, so existing callers are
     unchanged. Reject zero, negative and non-finite values.
   - `run()` reads `total_cost_usd` from the JSON and returns it on the result (extend `Usage` with `cost_usd: float | None`).
   - A result whose `subtype` is `error_max_budget_usd` raises an error whose message names the budget stop, so a stop for money is
     distinguishable from a crash in logs and in the circuit breaker's failure text.
4. Tests first, as pure functions with the JSON fixtures from the real output shape above: flag present only when set; invalid caps
   rejected; cost parsed; missing `total_cost_usd` gives `None`, not 0; budget stop raises the named error; stale file detected;
   fallback path labelled.

`policy/pricing.yaml` format Part B creates, so Part A's tests can use a copy as a fixture:

```yaml
as_of: 2026-10-29
review_by: 2026-12-29
source: https://platform.claude.com/docs/en/about-claude/pricing   # re-fetch and re-date before changing any value
models:                 # USD per million tokens, input / output
  haiku:  {input: 0.10, output: 0.50}
  sonnet: {input: 2.00, output: 10.00}
  opus:   {input: 4.00, output: 20.00}
```

## Part B: Ryan applies (protected paths; an agent must not touch these)

1. **Probe the CI path first.** Run one cheap `agent-exec` (Haiku, low turns) and check the execution file for `total_cost_usd` and
   that a tiny `--max-budget-usd` stops it. If the CI token reports no cost, stop here: the dollar cap is not available in CI, and
   only the apx path (Part A) gets it. Record the result with `pow log`.
2. Create `policy/pricing.yaml` (above). Re-fetch the pricing page by hand first; the values above were read by a research agent and
   not re-checked.
3. `policy/portfolio.yaml`: add `max_budget_usd` per role next to `max_turns` (suggest choosing the numbers after a week of recorded
   `total_cost_usd`, not before; any number picked now would be a guess).
4. `kit/runtime/gate.py`: carry the budget in the dispatch decision and write it to `$GITHUB_OUTPUT` beside `max_turns`; validate it
   like `max_turns` (numeric, upper bound).
5. `kit/workflows/exec.yml` and the callers: add `max_budget_usd` input, validate it, pass `--max-budget-usd` in `claude_args` next
   to `--max-turns`. Same in `improve.yml` and `audit.yml` if wanted.
6. `apps/control-plane/lib/ledger.ts`: read weights from the same file or retire the table, and add a cost field to the `apx_run`
   event (`app/api/**`) so cost is logged per PR. The first version can log it only in the run summary.
7. Add a doctor/audit check that flags `policy/pricing.yaml` past `review_by`.

Run `ap handshake specs/cost-controls.md` to see whether the system accepts this spec and what it will do.
