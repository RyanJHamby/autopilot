"""Local run ledger for the off-Actions executor (apx).

gate.decide() was written against Actions run history. This keeps the same facts in sqlite and hands
decide() the same shape: [{created_at, conclusion, status, hard}], newest first. No network here.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

SCHEMA = """
create table if not exists runs (
  id integer primary key autoincrement,
  repo text not null,
  issue integer not null,
  hard integer not null default 0,
  created_at text not null,
  finished_at text,
  status text not null default 'in_progress',
  conclusion text,
  model text,
  turns integer,
  model_id text,
  cost_usd real,
  budget_usd real,
  kind text not null default 'run',
  ref text not null default '',
  note text
)
"""
MIGRATIONS = (
    "alter table runs add column kind text not null default 'run'",
    "alter table runs add column ref text not null default ''",
    "alter table runs add column model_id text",
    "alter table runs add column cost_usd real",
    "alter table runs add column budget_usd real",
    "alter table runs add column note text",
)
NOTE_MAX = 2000  # a failure reason is a paragraph, not a log: longer text is cut here
# One row per sprint (sprint.py): written when a pass first sees it active, closed once with its summary. ended_at stays set, so a
# sprint that ended never reopens, even if a cost reported later comes in under the run's cap.
SPRINTS = """
create table if not exists sprints (
  repo text not null,
  started_at text not null,
  window_h real not null,
  max_runs integer not null,
  max_usd real not null,
  per_run_usd real not null,
  ended_at text,
  reason text,
  runs integer,
  merged integer,
  cost_usd real,
  primary key (repo, started_at)
)
"""
IN_FLIGHT = ("queued", "in_progress")


def _iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).isoformat()


class Ledger:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute(SCHEMA)
        self.db.execute(SPRINTS)
        have = {r["name"] for r in self.db.execute("pragma table_info(runs)")}
        for stmt in MIGRATIONS:  # a ledger file from before these columns existed is upgraded in place
            if stmt.split()[5] not in have:
                self.db.execute(stmt)
        self.db.commit()

    @classmethod
    def read_only(cls, path: str) -> "Ledger":
        """Open an existing ledger file without creating, migrating or writing it (the doctor's view). sqlite3.Error if it is absent."""
        led = cls.__new__(cls)
        led.db = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
        led.db.row_factory = sqlite3.Row
        return led

    def start(
        self,
        repo: str,
        issue: int,
        *,
        hard: bool = False,
        now: dt.datetime | None = None,
        kind: str = "run",
        ref: str = "",
        budget_usd: float | None = None,
    ) -> int:
        """kind 'fix' marks a red-CI retry of an existing PR; ref is then the PR head sha the retry was for. budget_usd is the run's
        dollar cap, which the global spend ceiling charges while the run is in flight or if it finishes without a reported cost."""
        now = now or dt.datetime.now(dt.timezone.utc)
        cur = self.db.execute(
            "insert into runs (repo, issue, hard, created_at, kind, ref, budget_usd) values (?, ?, ?, ?, ?, ?, ?)",
            (repo, issue, int(hard), _iso(now), kind, ref, budget_usd),
        )
        self.db.commit()
        return int(cur.lastrowid)

    def finish(
        self,
        run_id: int,
        conclusion: str,
        *,
        model: str | None = None,
        turns: int | None = None,
        model_id: str | None = None,
        cost_usd: float | None = None,
        note: str | None = None,
        now: dt.datetime | None = None,
    ) -> None:
        """model is the alias that was asked for; model_id is the resolved id and cost_usd the CLI's total_cost_usd (None = not reported).
        note is why a run failed, already redacted by the caller (executor.failure_reason); it is cut to NOTE_MAX characters here."""
        now = now or dt.datetime.now(dt.timezone.utc)
        self.db.execute(
            "update runs set status='completed', conclusion=?, model=?, turns=?, model_id=?, cost_usd=?, note=?, finished_at=? where id=?",
            (conclusion, model, turns, model_id, cost_usd, note[:NOTE_MAX] if note else None, _iso(now), run_id),
        )
        self.db.commit()

    def runs(self, repo: str, limit: int = 30) -> list[dict]:
        """decide()-shaped history for one repo, newest first."""
        rows = self.db.execute(
            "select created_at, conclusion, status, hard from runs where repo=? order by created_at desc, id desc limit ?",
            (repo, limit),
        ).fetchall()
        return [
            {"created_at": r["created_at"], "conclusion": r["conclusion"], "status": r["status"], "hard": bool(r["hard"])}
            for r in rows
        ]

    def recent(self, limit: int = 5) -> list[dict]:
        """The last runs across all repos, newest first, with their failure notes (the `--runs` view)."""
        rows = self.db.execute(
            "select id, repo, issue, kind, created_at, status, conclusion, turns, cost_usd, note from runs order by id desc limit ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def inflight_issues(self, repo: str) -> set[int]:
        q = ",".join("?" for _ in IN_FLIGHT)
        rows = self.db.execute(f"select issue from runs where repo=? and status in ({q})", (repo, *IN_FLIGHT)).fetchall()
        return {int(r["issue"]) for r in rows}

    def attempted_since(self, repo: str, issue: int, since: dt.datetime) -> bool:
        """True if any run (any outcome) for this issue started after `since`; used to cap re-dispatches to one a day."""
        row = self.db.execute(
            "select 1 from runs where repo=? and issue=? and created_at >= ? limit 1", (repo, issue, _iso(since))
        ).fetchone()
        return row is not None

    def fix_attempts(self, repo: str, issue: int) -> int:
        """Red-CI retries already made for this issue's PR, whatever their outcome (bounds the retry loop)."""
        row = self.db.execute("select count(*) n from runs where repo=? and issue=? and kind='fix'", (repo, issue)).fetchone()
        return int(row["n"])

    def fixed_head(self, repo: str, issue: int, sha: str) -> bool:
        """True if a retry was already made for exactly this PR head (so one red head is never retried twice)."""
        row = self.db.execute(
            "select 1 from runs where repo=? and issue=? and kind='fix' and ref=? limit 1", (repo, issue, sha)
        ).fetchone()
        return row is not None

    def abandon_stale(self, max_age: dt.timedelta, *, now: dt.datetime | None = None) -> int:
        """A crashed executor leaves in_progress rows that would block the issue forever; close them as timed_out."""
        now = now or dt.datetime.now(dt.timezone.utc)
        cutoff = _iso(now - max_age)
        cur = self.db.execute(
            "update runs set status='completed', conclusion='timed_out', finished_at=? where status='in_progress' and created_at < ?",
            (_iso(now), cutoff),
        )
        self.db.commit()
        return cur.rowcount

    def sprint_seen(self, repo: str, started_at: str, limits) -> None:
        self.db.execute(
            "insert or ignore into sprints (repo, started_at, window_h, max_runs, max_usd, per_run_usd) values (?, ?, ?, ?, ?, ?)",
            (repo, started_at, limits.window_h, limits.runs, limits.usd, limits.per_run_usd),
        )
        self.db.commit()

    def sprint_end(self, repo: str, started_at: str, *, reason: str, runs: int, merged: int | None, cost_usd: float, now: dt.datetime) -> None:
        """Closes a sprint once; a second call for the same sprint changes nothing."""
        self.db.execute(
            "update sprints set ended_at=?, reason=?, runs=?, merged=?, cost_usd=? where repo=? and started_at=? and ended_at is null",
            (_iso(now), reason, runs, merged, cost_usd, repo, started_at),
        )
        self.db.commit()

    def sprint(self, repo: str, started_at: str):
        return self.db.execute("select * from sprints where repo=? and started_at=?", (repo, started_at)).fetchone()

    def open_sprints(self, repo: str | None = None) -> list:
        q, args = "select * from sprints where ended_at is null", ()
        if repo is not None:
            q, args = q + " and repo=?", (repo,)
        return self.db.execute(q + " order by repo, started_at", args).fetchall()
