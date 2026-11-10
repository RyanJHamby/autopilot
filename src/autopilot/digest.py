"""Morning markdown digest of the last 24 hours. Pure functions over already-fetched data; no network, no model."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

from autopilot import picker

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "kit" / "runtime"))
from guard import _matches  # noqa: E402
from tier import PROTECTED_TIER2  # noqa: E402

LARGE = 400  # changed lines

NOT_FAILURES = ("success", "skipped", "cancelled", "", None)


def _ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def summarize(repo: str, prs: list[dict], runs: list[dict], now: dt.datetime) -> dict:
    """prs: gh pr list rows; runs: agent-exec run rows. Only agent/* PRs and the last 24h count."""
    since = now - dt.timedelta(hours=24)
    agent = [p for p in prs if p["headRefName"].startswith("agent/")]
    return {
        "repo": repo,
        "merged": [p for p in agent if p.get("mergedAt") and _ts(p["mergedAt"]) >= since],
        "waiting": [p for p in agent if p["state"] == "OPEN" and not p.get("isDraft")],
        "failed": [r for r in runs if r.get("conclusion") not in NOT_FAILURES and _ts(r["createdAt"]) >= since],
    }


def risk(p: dict) -> tuple[int, str]:
    """(rank, why): lower rank = look first. Missing fields (an older gh payload) just mean no signal, never a lower risk."""
    hit = next((f["path"] for f in p.get("files") or [] if _matches(f["path"], PROTECTED_TIER2)), None)
    if hit:
        return 0, f"protected path {hit}"
    if any(
        (c.get("conclusion") or c.get("state")) in ("FAILURE", "ERROR", "TIMED_OUT") for c in p.get("statusCheckRollup") or []
    ):
        return 1, "a check is failing"
    size = (p.get("additions") or 0) + (p.get("deletions") or 0)
    if size > LARGE:
        return 2, f"large ({size} lines)"
    if any(c.get("status") in ("IN_PROGRESS", "QUEUED", "PENDING") for c in p.get("statusCheckRollup") or []):
        return 3, "checks still running"
    return 4, f"{size} lines, checks ok" if p.get("statusCheckRollup") else "no checks yet"


def repo_status(entry: dict, paused: bool, now: dt.datetime) -> str:
    if entry.get("mode") == "dormant":
        return "dormant"
    if picker.held(entry, now):
        return f"held until {entry['hold_until']}"
    return "paused" if paused else "ok"


def _section(title: str, lines: list[str]) -> list[str]:
    return [f"## {title} ({len(lines)})" if lines else f"## {title}", *(lines or ["- none"]), ""]


def read_history(path, n: int = 2) -> list[dict]:
    """The last `n` valid runs from converge's history file, oldest first. A missing file, a blank line or a corrupt line is skipped."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    runs = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and isinstance(row.get("repos"), dict):
            runs.append(row)
    return runs[-n:]


def standard_section(rows: list[dict]) -> list[str]:
    """The standard's burn-down: each repo with gaps, now against the previous converge run, worst first. Pure; reads no network."""
    if not rows:
        return ["- converge has not recorded a run yet (it records one on `ap standard converge --apply`)"]
    cur = rows[-1]["repos"]
    prev = rows[-2]["repos"] if len(rows) > 1 else None
    gaps = {n: c for n, c in cur.items() if c["fail_level"] or c["warn"] or c["grandfathered"]}
    out = []
    for name, c in sorted(gaps.items(), key=lambda kv: (-kv[1]["fail_level"], -kv[1]["warn"], kv[0])):
        f, w, g = c["fail_level"], c["warn"], c["grandfathered"]
        if prev is None:
            out.append(f"- {name}: {f} fail-level, {w} warn, {g} grandfathered")
        elif name not in prev:
            out.append(f"- {name}: {f} fail-level (new since last run), {w} warn, {g} grandfathered")
        else:
            p = prev[name]
            out.append(
                f"- {name}: {f} fail-level (was {p['fail_level']}), {w} warn (was {p['warn']}), {g} grandfathered (was {p['grandfathered']})"
            )
    clean = len(cur) - len(gaps)
    if clean:
        out.append(f"- {clean} repo(s) conform (no gaps)")
    if prev is None:
        out.append("- no earlier run to compare yet")
    return out


def render(summaries: list[dict], statuses: dict[str, str], now: dt.datetime, standard: list[str] | None = None) -> str:
    def prs(key: str) -> list[str]:
        return [f"- {s['repo']} #{p['number']} {p['title']} ({p['url']})" for s in summaries for p in s[key]]

    def waiting() -> list[str]:
        rows = sorted(
            ((risk(p), s["repo"], p) for s in summaries for p in s["waiting"]), key=lambda r: (r[0][0], r[1], r[2]["number"])
        )
        return [f"- {repo} #{p['number']} {p['title']}: {why} ({p['url']})" for (_, why), repo, p in rows]

    failed = [f"- {s['repo']} run {r['databaseId']} ({r['conclusion']})" for s in summaries for r in s["failed"]]
    stopped = [f"- {n}: {st}" for n, st in statuses.items() if st != "ok"]
    out = [f"# Autopilot digest {now.strftime('%Y-%m-%d')}", "", "Last 24 hours.", ""]
    out += _section("Merged", prs("merged")) + _section("Waiting on you", waiting())
    out += _section("Failed runs", failed) + _section("Paused or held", stopped)
    if standard is not None:
        out += _section("Standard burn-down", standard)
    return "\n".join(out).rstrip("\n") + "\n"
