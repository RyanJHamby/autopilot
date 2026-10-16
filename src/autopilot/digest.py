"""Morning markdown digest of the last 24 hours. Pure functions over already-fetched data; no network, no model."""

from __future__ import annotations

import datetime as dt

from autopilot import picker

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


def repo_status(entry: dict, paused: bool, now: dt.datetime) -> str:
    if entry.get("mode") == "dormant":
        return "dormant"
    if picker.held(entry, now):
        return f"held until {entry['hold_until']}"
    return "paused" if paused else "ok"


def _section(title: str, lines: list[str]) -> list[str]:
    return [f"## {title} ({len(lines)})" if lines else f"## {title}", *(lines or ["- none"]), ""]


def render(summaries: list[dict], statuses: dict[str, str], now: dt.datetime) -> str:
    def prs(key: str) -> list[str]:
        return [f"- {s['repo']} #{p['number']} {p['title']} ({p['url']})" for s in summaries for p in s[key]]

    failed = [f"- {s['repo']} run {r['databaseId']} ({r['conclusion']})" for s in summaries for r in s["failed"]]
    stopped = [f"- {n}: {st}" for n, st in statuses.items() if st != "ok"]
    out = [f"# Autopilot digest {now.strftime('%Y-%m-%d')}", "", "Last 24 hours.", ""]
    out += _section("Merged", prs("merged")) + _section("Waiting on you", prs("waiting"))
    out += _section("Failed runs", failed) + _section("Paused or held", stopped)
    return "\n".join(out).rstrip("\n") + "\n"
