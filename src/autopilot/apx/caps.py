"""Per-run caps for apx agent runs: a turn cap and a dollar cap, both mandatory.

The dollar cap is `defaults.max_budget_usd.<role>` in policy/portfolio.yaml, with the same role keys as `defaults.max_turns`. The numbers
there are placeholders the owner has not confirmed. `claude --max-budget-usd` is checked by the CLI between turns, so a run can end a
little over its cap; `--max-turns` is the hard stop. If no valid cap can be resolved the run does not start (CapError), it never runs
uncapped.
"""

from __future__ import annotations

import math
from pathlib import Path

import yaml

PORTFOLIO_FILE = Path(__file__).resolve().parents[3] / "policy" / "portfolio.yaml"
MAX_BUDGET_USD = 50.0  # a sanity ceiling on any single run's cap, not a recommendation
MAX_TURNS = 500


class CapError(ValueError):
    """No usable dollar cap. A ValueError so the planner's existing fail-closed handling applies."""


def valid_budget(value) -> float:
    """A plain number in (0, MAX_BUDGET_USD]; bools, strings, NaN, infinity, zero and negatives are refused."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= MAX_BUDGET_USD:
        raise ValueError(f"max budget must be a number above 0 and at most {MAX_BUDGET_USD:g} USD, got {value!r}")
    return float(value)


def valid_turns(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_TURNS:
        raise ValueError(f"max turns must be an integer from 1 to {MAX_TURNS}, got {value!r}")
    return value


def fmt(usd: float) -> str:
    """Cents, never an exponent, and a positive cap never rounds down to zero."""
    return f"{max(round(valid_budget(usd), 2), 0.01):.2f}"


def budget_for(role: str) -> float:
    try:
        raw = yaml.safe_load(Path(PORTFOLIO_FILE).read_text())["defaults"]["max_budget_usd"][role]
    except (OSError, yaml.YAMLError, KeyError, TypeError) as e:
        raise CapError(f"no max_budget_usd for {role!r} in {PORTFOLIO_FILE.name} ({type(e).__name__}); refusing to run uncapped") from None
    try:
        return valid_budget(raw)
    except ValueError as e:
        raise CapError(f"{PORTFOLIO_FILE.name}: {e}") from None
