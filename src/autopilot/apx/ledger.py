"""Local run ledger for the off-Actions executor (apx).

gate.decide() was written against Actions run history. This keeps the same facts in sqlite and hands
decide() the same shape: [{created_at, conclusion, status, hard}], newest first. No network here.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

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
  kind text not null default 'run',
  ref text not null default ''
)
"""
MIGRATIONS = (
    "alter table runs add column kind text not null default 'run'",
    "alter table runs add column ref text not null default ''",
)
IN_FLIGHT = ("queued", "in_progress")


def _iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).isoformat()


class Ledger:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute(SCHEMA)
        have = {r["name"] for r in self.db.execute("pragma table_info(runs)")}
        for stmt in MIGRATIONS:  # a ledger file from before these columns existed is upgraded in place
            if stmt.split()[5] not in have:
                self.db.execute(stmt)
        self.db.commit()

    def start(
        self, repo: str, issue: int, *, hard: bool = False, now: dt.datetime | None = None, kind: str = "run", ref: str = ""
    ) -> int:
        """kind 'fix' marks a red-CI retry of an existing PR; ref is then the PR head sha the retry was for."""
        now = now or dt.datetime.now(dt.timezone.utc)
        cur = self.db.execute(
            "insert into runs (repo, issue, hard, created_at, kind, ref) values (?, ?, ?, ?, ?, ?)",
            (repo, issue, int(hard), _iso(now), kind, ref),
        )
        self.db.commit()
        return int(cur.lastrowid)

    def finish(
        self, run_id: int, conclusion: str, *, model: str | None = None, turns: int | None = None, now: dt.datetime | None = None
    ) -> None:
        now = now or dt.datetime.now(dt.timezone.utc)
        self.db.execute(
            "update runs set status='completed', conclusion=?, model=?, turns=?, finished_at=? where id=?",
            (conclusion, model, turns, _iso(now), run_id),
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
