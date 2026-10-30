"""Usage meter: how much of the agent budget the ledger says was used. Read-only over the ledger, no network.

Counting rules (kept in one place, `_summarise`):
- "started" is every ledger row created in the window, fixes included, because fixes share the daily cap with runs.
- "ok" is conclusion 'success'; "failed" is any other finished conclusion except skipped/cancelled (those never reached the model).
- "fixes" is the subset of started rows with kind='fix'.
- "turns" sums the turns recorded at finish(); finished rows that recorded none are counted in `turns_unrecorded`, not guessed.
- "day" is the rolling 24h the gate caps on (the status line uses it); "today" is the current UTC calendar day; "week" is the 7 rolling days ending now.
- `remaining` mirrors gate.decide(): a rolling 24h window, skipped/cancelled excluded, against the repo's daily cap.
To add cost later, add fields to `Window` and one line in `_summarise`; callers read the dict from `to_dict()`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
from typing import Optional

from .ledger import Ledger

NOT_SPENT = ("skipped", "cancelled")  # same exclusion as gate.decide()


@dataclass
class Window:
    started: int = 0
    ok: int = 0
    failed: int = 0
    fixes: int = 0
    turns: int = 0
    turns_unrecorded: int = 0  # finished rows with no turns value


@dataclass
class RepoUsage:
    repo: str
    today: Window
    day: Window  # rolling 24h, the window the gate caps on
    week: Window
    cap: Optional[int]  # None when the daily cap is not known
    used_24h: int  # what gate.decide() counts against the cap
    remaining: Optional[int]

    def to_dict(self) -> dict:
        return asdict(self)


def _parse(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _summarise(rows: list, since: dt.datetime) -> Window:
    w = Window()
    for r in rows:
        if r["at"] < since:
            continue
        w.started += 1
        if r["kind"] == "fix":
            w.fixes += 1
        if r["status"] == "completed":
            if r["conclusion"] == "success":
                w.ok += 1
            elif r["conclusion"] not in NOT_SPENT:
                w.failed += 1
            if r["turns"] is None:
                w.turns_unrecorded += 1
            else:
                w.turns += int(r["turns"])
    return w


def repo_usage(ledger: Ledger, repo: str, *, cap: Optional[int] = None, now: Optional[dt.datetime] = None) -> RepoUsage:
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - dt.timedelta(days=7)
    day_start = now - dt.timedelta(hours=24)
    raw = ledger.db.execute("select created_at, status, conclusion, turns, kind from runs where repo=?", (repo,)).fetchall()
    rows = [
        {
            "at": _parse(r["created_at"]),
            "status": r["status"],
            "conclusion": r["conclusion"],
            "turns": r["turns"],
            "kind": r["kind"],
        }
        for r in raw
    ]
    rows = [r for r in rows if r["at"] <= now]
    used = sum(1 for r in rows if r["at"] >= day_start and r["conclusion"] not in NOT_SPENT)
    return RepoUsage(
        repo=repo,
        today=_summarise(rows, midnight),
        day=_summarise(rows, day_start),
        week=_summarise(rows, week_start),
        cap=cap,
        used_24h=used,
        remaining=None if cap is None else max(cap - used, 0),
    )


def usage_line(u: RepoUsage) -> str:
    """Every number on the line is the gate's rolling 24h window, so 'used' and 'left' can never disagree."""
    left = "" if u.remaining is None else f" ({u.remaining} of {u.cap} left)"
    return f"{u.repo}: usage last 24h {u.day.started} runs{left}, {u.day.fixes} fixes, 7d: {u.week.started} runs"
