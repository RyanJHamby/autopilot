"""Work-conserving allocation of a global daily run pool across repos. Pure; no network."""

from __future__ import annotations

import datetime as dt

TIER_PRIORITY = {"A": 8, "B": 5, "C": 2}


def priority(entry: dict) -> int:
    return int(entry.get("priority", TIER_PRIORITY.get(entry.get("tier", "C"), 2)))


def held(entry: dict, now: dt.datetime) -> bool:
    """`hold_until` (ISO 8601 UTC) is an owner pause: no dispatch until that time."""
    h = entry.get("hold_until")
    return bool(h) and now < dt.datetime.fromisoformat(str(h).replace("Z", "+00:00"))


def allocate(repos: list[dict], pool: int, reserve: int = 0) -> dict[str, int]:
    """repos: [{name, priority, capacity}] where capacity = min(eligible issues, runs left under the repo's own gate).

    Pass 1 gives each repo a priority-weighted slice (floor, at most its capacity). Pass 2 hands any unspent runs,
    one at a time, to the highest-priority repo that still has capacity, so budget is never stranded on an idle repo.
    The repo gate remains the hard floor: this only decides where discretionary runs go.
    """
    budget = max(pool - reserve, 0)
    live = [r for r in repos if r["capacity"] > 0 and r["priority"] > 0]
    out = {r["name"]: 0 for r in live}
    total = sum(r["priority"] for r in live)
    if not live or budget == 0:
        return {}
    for r in live:
        out[r["name"]] = min(r["capacity"], budget * r["priority"] // total)
    left = budget - sum(out.values())
    order = sorted(live, key=lambda r: (-r["priority"], r["name"]))
    while left > 0:
        progressed = False
        for r in order:
            if left > 0 and out[r["name"]] < r["capacity"]:
                out[r["name"]] += 1
                left -= 1
                progressed = True
        if not progressed:
            break
    return {k: v for k, v in out.items() if v}
