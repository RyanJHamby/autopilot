"""Global dollar ceiling for agent runs across ALL repos: policy/portfolio.yaml `defaults.global_usd_per_day`, rolling 24h.

Read-only over the ledger, no network. What counts as spent (fail closed: an unknown cost is charged at the run's full cap):
- a run started in the last 24h that reported cost_usd: that cost;
- a run still in flight (whatever its age) or finished without a reported cost: its recorded budget_usd, or, for a row from before
  the ledger recorded caps, the largest per-role cap in policy;
- a run that finished skipped/cancelled without a cost never reached the model (the same exclusion as gate.decide()): nothing.
The planner holds every new agent run and CI fix when spent + planned + this run's cap would pass the ceiling. Absent key: no ceiling.
"""

from __future__ import annotations

import datetime as dt

from . import caps
from .ledger import IN_FLIGHT, Ledger, _iso

NOT_SPENT = ("skipped", "cancelled")
AGENT_KINDS = ("run-agent", "fix-ci")  # actions that start a model; checks, rebases (update-branch) and merges are never held


def used_24h(ledger: Ledger, *, now: dt.datetime | None = None, fallback: float | None = None) -> float:
    now = now or dt.datetime.now(dt.timezone.utc)
    fallback = caps.largest_budget() if fallback is None else fallback
    q = ",".join("?" for _ in IN_FLIGHT)
    rows = ledger.db.execute(
        f"select status, conclusion, cost_usd, budget_usd from runs where (created_at >= ? and created_at <= ?) or status in ({q})",
        (_iso(now - dt.timedelta(hours=24)), _iso(now), *IN_FLIGHT),
    ).fetchall()
    total = 0.0
    for r in rows:
        if r["status"] not in IN_FLIGHT and r["cost_usd"] is not None:
            total += float(r["cost_usd"])
        elif r["status"] not in IN_FLIGHT and r["conclusion"] in NOT_SPENT:
            continue
        else:
            total += float(r["budget_usd"]) if r["budget_usd"] is not None else fallback
    return total


def hold_reason(ledger: Ledger, now: dt.datetime | None = None):
    """(ceiling or None, used, error or None) for one planning pass."""
    try:
        ceiling = caps.global_usd_per_day()
    except caps.CapError as e:
        return None, 0.0, f"global spend ceiling unreadable (fail closed): {e}"
    return ceiling, used_24h(ledger, now=now), None


def enforce(result: dict[str, dict], ledger: Ledger, now: dt.datetime | None = None) -> dict[str, dict]:
    """Drop agent actions from the planner's result once the ceiling would be passed, in plan order: the first run that does not fit
    stops new runs everywhere for this pass. Each repo that lost an action says why in its note."""
    ceiling, used, error = hold_reason(ledger, now)
    if ceiling is None and error is None:
        return result
    planned, full = 0.0, error is not None
    for v in result.values():
        kept, dropped = [], False
        for a in v["actions"]:
            if a.kind not in AGENT_KINDS:
                kept.append(a)
                continue
            if not full:
                b = caps.detail_budget(a.detail)
                cost = b if b is not None else caps.largest_budget()
                if used + planned + cost <= ceiling:  # type: ignore[operator]
                    planned += cost
                    kept.append(a)
                    continue
                full = True
            dropped = True
        if dropped:
            why = error or f"global spend ceiling: ${used:.2f} of ${ceiling:.2f} used in 24h"
            v["actions"], v["note"] = kept, f"{v['note']}; {why}"
    return result


def spend_line(ledger: Ledger, now: dt.datetime | None = None) -> str:
    """One status line per pass: the 24h spend across all repos and the ceiling, or that none is set."""
    ceiling, used, error = hold_reason(ledger, now)
    if error:
        return f"all repos: spend last 24h ${used_24h(ledger, now=now):.2f}; {error}"
    if ceiling is None:
        return f"all repos: spend last 24h ${used:.2f} (global_usd_per_day not set)"
    return f"all repos: spend last 24h ${used:.2f} of ${ceiling:.2f} ceiling"
