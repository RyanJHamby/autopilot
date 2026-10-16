"""Outcome scorecard from GitHub PR history. Pure functions over already-fetched data; no network here."""

from __future__ import annotations

import datetime as dt
import statistics
from collections import defaultdict


def _ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def is_agent(pr: dict) -> bool:
    return pr["headRefName"].startswith("agent/")


def revert_targets(prs: list[dict]) -> set[int]:
    """PR numbers that a later `Revert ...` PR names (GitHub's revert button writes 'Reverts #N')."""
    import re

    out: set[int] = set()
    for p in prs:
        if (p.get("title") or "").startswith("Revert"):
            out |= {int(n) for n in re.findall(r"#(\d+)", (p.get("title") or "") + " " + (p.get("body") or ""))}
    return out


def scorecard(prs: list[dict], *, since: dt.datetime) -> dict:
    """prs: [{number,title,body,headRefName,state,createdAt,mergedAt,closedAt,labels:[{name}]}]."""
    reverted = revert_targets(prs)
    mine = [p for p in prs if is_agent(p) and _ts(p["createdAt"]) >= since]
    merged = [p for p in mine if p.get("mergedAt")]
    closed = [p for p in mine if p["state"] == "CLOSED" and not p.get("mergedAt")]
    open_ = [p for p in mine if p["state"] == "OPEN"]
    hours = [(_ts(p["mergedAt"]) - _ts(p["createdAt"])).total_seconds() / 3600 for p in merged]
    by_class: dict[str, dict] = defaultdict(lambda: {"merged": 0, "reverted": 0})
    for p in merged:
        cls = next(
            (x["name"].split(":", 1)[1] for x in p.get("labels", []) if x["name"].startswith("automerged:")), "human-merged"
        )
        by_class[cls]["merged"] += 1
        by_class[cls]["reverted"] += p["number"] in reverted
    decided = len(merged) + len(closed)
    return {
        "opened": len(mine),
        "merged": len(merged),
        "closed_unmerged": len(closed),
        "open": len(open_),
        "reverted": sum(p["number"] in reverted for p in merged),
        "merge_rate": round(len(merged) / decided, 2) if decided else None,
        "median_hours_to_merge": round(statistics.median(hours), 1) if hours else None,
        "by_class": dict(by_class),
    }


# Same weights and turn caps as apps/control-plane/lib/ledger.ts. Upper-bound estimates: the Max pool exposes no tokens.
_WEIGHT = {"sonnet": 3, "opus": 15}
_TURNS = {"sonnet": 40, "opus": 45}


def run_points(runs: list[dict]) -> int:
    """Estimated run-points for `agent-exec` runs [{displayTitle,conclusion}]; skipped/cancelled runs cost nothing."""
    total = 0
    for r in runs:
        if r.get("conclusion") in ("skipped", "cancelled"):
            continue
        model = "opus" if "[hard]" in (r.get("displayTitle") or "") else "sonnet"
        total += _TURNS[model] * _WEIGHT[model]
    return total


def points_per_merged(runs: list[dict], prs: list[dict], *, since: dt.datetime) -> float | None:
    """Estimated run-points per merged agent PR in the window; None when nothing merged."""
    merged = sum(1 for p in prs if is_agent(p) and p.get("mergedAt") and _ts(p["createdAt"]) >= since)
    return round(run_points(runs) / merged, 1) if merged else None


def promotion_candidates(card: dict, enabled: list[str], *, min_clean: int = 10) -> list[str]:
    """Classes with enough clean merges to be worth proposing to the owner (a loosening: the owner decides)."""
    return [
        c
        for c, v in card["by_class"].items()
        if c not in enabled and c != "human-merged" and v["merged"] >= min_clean and v["reverted"] == 0
    ]
