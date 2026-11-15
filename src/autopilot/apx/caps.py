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


def _defaults() -> dict:
    try:
        d = yaml.safe_load(Path(PORTFOLIO_FILE).read_text())["defaults"]
    except (OSError, yaml.YAMLError, KeyError, TypeError) as e:
        raise CapError(f"cannot read defaults from {PORTFOLIO_FILE.name} ({type(e).__name__})") from None
    if not isinstance(d, dict):
        raise CapError(f"{PORTFOLIO_FILE.name}: defaults is not a mapping")
    return d


def global_usd_per_day() -> float | None:
    """`defaults.global_usd_per_day`: the dollar ceiling for all agent runs in all repos over a rolling 24h. Absent means no global
    ceiling (None). Present but not a finite number >= 0, or a policy file that cannot be read, raises CapError: no agent runs."""
    d = _defaults()
    if "global_usd_per_day" not in d:
        return None
    v = d["global_usd_per_day"]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
        raise CapError(f"{PORTFOLIO_FILE.name}: global_usd_per_day must be a number of dollars >= 0, got {v!r}")
    return float(v)


def largest_budget() -> float:
    """The highest per-role cap in policy, for a ledger row that recorded none; MAX_BUDGET_USD if policy gives no usable number."""
    try:
        return max(valid_budget(v) for v in _defaults()["max_budget_usd"].values())
    except (CapError, KeyError, TypeError, AttributeError, ValueError):
        return MAX_BUDGET_USD


def detail_budget(detail: str) -> float | None:
    """The run's dollar cap from an action detail: the lowest valid `budget=` token (as daemon.parse_detail), None if there is none."""
    given = []
    for p in detail.split():
        if p.startswith("budget="):
            try:
                given.append(valid_budget(float(p.split("=", 1)[1])))
            except ValueError:
                continue
    return min(given) if given else None
