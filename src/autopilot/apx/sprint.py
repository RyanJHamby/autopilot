"""Sprints: a time-boxed run allowance for ONE repo in `mode: yolo`, so a scrappy hour of agent work is possible at all.

Who starts one: only the owner, by applying the `sprint` label to an open issue or PR in that repo. The latest `labeled` event for it
must have the owner as actor (the same check as planner._owner_vouches for `agent-ready`); a label applied by anyone else, or events
that cannot be read in one page, mean no sprint. The sprint starts at that event's time. Removing the label ends it.

Limits: policy/portfolio.yaml `defaults.sprint` ({window_h, runs, usd, per_run_usd}) if present, else BUILTIN. The repo's
default-branch `.autopilot/repo.yaml` may carry `sprint: {...}` with the same keys, and each value may only LOWER policy's (a higher
one is ignored and the note says so). Invalid values anywhere refuse the sprint: the normal caps apply.

While active, the repo's runs_per_day is replaced by the sprint's remaining runs (and what its dollars still cover at per_run_usd),
and each run's dollar cap is min(policy's cap for the mode, per_run_usd). Spent dollars are the ledger's cost_usd for this repo since
the start, an unknown cost charged at the run's cap (spend.cost_of). Nothing else is lifted: the freeze, shadow mode, the owner hold,
the breaker, max_open_agent_prs and global_usd_per_day all still apply, because the sprint only changes the repo's cfg before
gate.decide() and the per-run cap before spend.enforce().

Ends: window over, runs used up, or not enough dollars left for one more run. Then no new runs for the repo until the window closes
(after it, the normal rolling-24h cap, which counts the sprint's runs). The planner note carries the summary (runs, merged agent PRs,
cost) and record() writes it to the ledger once; an ended sprint never reopens.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, replace

from . import caps, spend
from .github import GitHubError
from .ledger import Ledger, _iso

LABEL = "sprint"
BUILTIN = {"window_h": 4.0, "runs": 4, "usd": 8.0, "per_run_usd": 2.0}
EPS = 1e-9


class SprintError(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    window_h: float
    runs: int
    usd: float
    per_run_usd: float


def _value(key: str, v):
    if key == "runs":
        if isinstance(v, bool) or not isinstance(v, int) or v < 1:
            raise SprintError(f"sprint.runs must be a whole number >= 1, got {v!r}")
        return v
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
        raise SprintError(f"sprint.{key} must be a number above 0, got {v!r}")
    if key == "per_run_usd" and v > caps.MAX_BUDGET_USD:
        raise SprintError(f"sprint.per_run_usd must be at most {caps.MAX_BUDGET_USD:g}, got {v!r}")
    return float(v)


def _parse(raw, where: str) -> dict:
    if not isinstance(raw, dict):
        raise SprintError(f"{where}: sprint must be a mapping, got {type(raw).__name__}")
    unknown = sorted(set(raw) - set(BUILTIN))
    if unknown:
        raise SprintError(f"{where}: unknown sprint keys {unknown}")
    return {k: _value(k, v) for k, v in raw.items()}


def policy_limits() -> Limits:
    """The ceilings. CapError (unreadable policy) is turned into SprintError: no sprint."""
    try:
        raw = caps._defaults().get("sprint")
    except caps.CapError as e:
        raise SprintError(str(e)) from None
    vals = dict(BUILTIN)
    if raw is not None:
        vals.update(_parse(raw, caps.PORTFOLIO_FILE.name))
    return Limits(**vals)


def limits_for(cfg: dict) -> tuple[Limits, str]:
    """Policy's limits, lowered by repo.yaml's `sprint:` block. Returns (limits, note naming any value that was above policy)."""
    ceiling = policy_limits()
    if cfg.get("sprint") is None:
        return ceiling, ""
    asked = _parse(cfg["sprint"], "repo.yaml")
    above = sorted(k for k, v in asked.items() if v > getattr(ceiling, k))
    lim = replace(ceiling, **{k: min(v, getattr(ceiling, k)) for k, v in asked.items()})
    lim = replace(lim, per_run_usd=min(lim.per_run_usd, lim.usd))
    return lim, (f"repo.yaml sprint values above policy ignored: {', '.join(above)}" if above else "")


def _left(td: dt.timedelta) -> str:
    secs = max(int(td.total_seconds()), 0)
    return f"{secs // 3600}h{secs // 60 % 60:02d}m"


def _time(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def started_at(api, repo: str, owner: str) -> tuple[dt.datetime | None, list[int]]:
    """(start of the newest owner-applied sprint label, numbers labelled by someone else). Any read error means no sprint."""
    try:
        items = api("GET", f"/repos/{repo}/issues?labels={LABEL}&state=open&per_page=20") or []
    except (GitHubError, OSError):
        return None, []
    best, ignored = None, []
    for it in items:
        if LABEL not in {(ln or {}).get("name") for ln in it.get("labels", [])}:
            continue
        try:
            events = api("GET", f"/repos/{repo}/issues/{it['number']}/events?per_page=100")
            if len(events) >= 100:  # the latest event may be on a later page: fail closed
                raise ValueError("too many events")
            ours = [e for e in events if e.get("event") == "labeled" and (e.get("label") or {}).get("name") == LABEL]
            if not ours or (ours[-1].get("actor") or {}).get("login") != owner:
                ignored.append(it["number"])
                continue
            t = _time(ours[-1]["created_at"])
        except (GitHubError, OSError, KeyError, TypeError, ValueError, AttributeError):
            ignored.append(it.get("number"))
            continue
        best = t if best is None or t > best else best
    return best, ignored


@dataclass
class State:
    repo: str
    started: dt.datetime
    limits: Limits
    runs: int
    usd: float
    now: dt.datetime
    ended: str | None = None
    newly_ended: bool = False
    merged: int | None = None

    @property
    def ends(self) -> dt.datetime:
        return self.started + dt.timedelta(hours=self.limits.window_h)

    def end_reason(self) -> str | None:
        if self.now >= self.ends:
            return "window ended"
        if self.runs >= self.limits.runs:
            return "run limit"
        if self.usd + self.limits.per_run_usd > self.limits.usd + EPS:
            return "dollar limit"
        return None

    def allowed(self) -> int:
        """New runs this sprint still covers: its run count and what its dollars pay for at per_run_usd, whichever is smaller."""
        if self.ended:
            return 0
        by_usd = math.floor((self.limits.usd - self.usd) / self.limits.per_run_usd + EPS)
        return max(0, min(self.limits.runs - self.runs, by_usd))

    def summary(self) -> str:
        merged = "?" if self.merged is None else self.merged
        return f"{self.runs} run(s), {merged} merged PR(s), ${self.usd:.2f} of ${self.limits.usd:.2f}"

    def note(self) -> str:
        if self.ended:
            return f"sprint ended ({self.ended}): {self.summary()}"
        return f"sprint active: {self.summary()}, {_left(self.ends - self.now)} left"


def _merged_since(api, repo: str, since: dt.datetime) -> int | None:
    try:
        closed = api("GET", f"/repos/{repo}/pulls?state=closed&per_page=100")
        return sum(
            1
            for p in closed
            if ((p.get("head") or {}).get("ref") or "").startswith("agent/") and p.get("merged_at") and _time(p["merged_at"]) >= since
        )
    except (GitHubError, OSError, KeyError, TypeError, ValueError, AttributeError):
        return None


def evaluate(api, repo: str, owner: str, cfg: dict, ledger: Ledger, now: dt.datetime) -> tuple[State | None, str]:
    """The repo's sprint this pass, or None, and a note for the planner. Read-only (GitHub and the ledger)."""
    start, ignored = started_at(api, repo, owner)
    notes = [f"sprint label on #{', #'.join(map(str, ignored))} not applied by the owner: ignored"] if ignored else []
    if start is None:
        return None, "; ".join(notes)
    if cfg.get("mode") != "yolo":
        return None, "; ".join(notes + ["sprint needs mode: yolo"])
    try:
        lim, clamped = limits_for(cfg)
    except SprintError as e:
        return None, "; ".join(notes + [f"sprint refused: {e}"])
    notes += [clamped] if clamped else []
    n, usd = spend.used_since(ledger, repo, start)
    st = State(repo, start, lim, n, usd, now)
    prior = ledger.sprint(repo, _iso(start))
    if prior is not None and prior["ended_at"]:
        st.ended, st.merged = prior["reason"], prior["merged"]
        st.runs, st.usd = prior["runs"], prior["cost_usd"]
    else:
        st.ended = st.end_reason()
        if st.ended:
            st.newly_ended, st.merged = True, _merged_since(api, repo, start)
    return st, "; ".join(notes)


def apply(cfg: dict, runs: list[dict], st: State) -> dict:
    """A copy of cfg whose runs_per_day for this tier is the runs already counted in the rolling 24h (gate.decide's rule) plus what
    the sprint still allows, so decide()'s `remaining` is exactly the sprint's."""
    since = st.now - dt.timedelta(hours=24)
    recent = sum(1 for r in runs if r.get("conclusion") not in spend.NOT_SPENT and _time(r["created_at"]) >= since)
    out = dict(cfg)
    budget = dict(out.get("budget") or {})
    budget["runs_per_day"] = {**(budget.get("runs_per_day") or {}), out.get("tier", "C"): recent + st.allowed()}
    out["budget"] = budget
    return out


def record(ledger: Ledger, planned: dict[str, dict], now: dt.datetime) -> None:
    """After planning: remember each active sprint (the doctor reads it), close ended ones with their summary, and close any open
    row whose label is gone or was replaced by a newer one. Only repos whose sprint was evaluated this pass are touched."""
    for repo, v in planned.items():
        if "sprint" not in v:
            continue
        st: State | None = v["sprint"]
        current = _iso(st.started) if st else None
        for row in ledger.open_sprints(repo):
            if row["started_at"] != current:
                n, usd = spend.used_since(ledger, repo, _time(row["started_at"]))
                ledger.sprint_end(repo, row["started_at"], reason="label removed or replaced", runs=n, merged=None, cost_usd=usd, now=now)
        if st is None:
            continue
        ledger.sprint_seen(repo, current, st.limits)  # type: ignore[arg-type]
        if st.ended:
            ledger.sprint_end(repo, current, reason=st.ended, runs=st.runs, merged=st.merged, cost_usd=st.usd, now=now)  # type: ignore[arg-type]


def doctor_lines(ledger: Ledger, now: dt.datetime) -> list[str]:
    """One line per sprint the ledger has open whose window has not closed: what it has left."""
    out = []
    for row in ledger.open_sprints():
        lim = Limits(*(row[f] for f in ("window_h", "max_runs", "max_usd", "per_run_usd")))
        start = _time(row["started_at"])
        n, usd = spend.used_since(ledger, row["repo"], start)
        st = State(row["repo"], start, lim, n, usd, now)
        if now >= st.ends:
            continue
        out.append(
            f"{row['repo']}: {max(lim.runs - n, 0)} of {lim.runs} runs, ${max(lim.usd - usd, 0):.2f} of ${lim.usd:.2f}, "
            f"{_left(st.ends - now)} left"
        )
    return out

