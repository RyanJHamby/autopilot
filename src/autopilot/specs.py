"""Read-only index of a repo's specs: which are active, what state, what changed. No model, no network.

A spec is specs/<id>.md with YAML frontmatter (the handshake contract) plus two optional lifecycle fields:
  status: draft | ready | active | done | abandoned     (default draft)
  issue:  the GitHub issue number once filed
and an optional `## Log` section of dated one-line entries. Git history is the authoritative changelog.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "kit" / "runtime"))
import handshake  # noqa: E402

STATUSES = ("draft", "ready", "active", "done", "abandoned")
LIVE = ("ready", "active")


@dataclass
class SpecRow:
    path: str
    id: str
    status: str
    issue: int | None
    tier: int | None
    verdict: str
    log: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    changed: str = ""


def log_entries(body: str) -> list[str]:
    m = re.search(r"(?ims)^##\s+Log\s*$(.*?)(?=^##\s|\Z)", body)
    if not m:
        return []
    return [ln.strip()[2:].strip() for ln in m.group(1).splitlines() if ln.strip().startswith("- ")]


def read_spec(path: Path, repo_cfg: dict | None = None) -> SpecRow:
    text = path.read_text()
    try:
        meta, body = handshake.parse_spec(text)
    except ValueError as e:
        return SpecRow(path.name, path.stem, "draft", None, None, "NEEDS-WORK", problems=[str(e)])
    status = str(meta.get("status") or "draft").lower()
    issue = meta.get("issue")
    issue = issue if isinstance(issue, int) and not isinstance(issue, bool) else None
    row = SpecRow(
        path=path.name,
        id=str(meta.get("id") or path.stem),
        status=status,
        issue=issue,
        tier=meta.get("risk_tier") if isinstance(meta.get("risk_tier"), int) else None,
        verdict=handshake.evaluate(text, repo_cfg).status,
        log=log_entries(body),
    )
    if status not in STATUSES:
        row.problems.append(f"status {status!r} is not one of {', '.join(STATUSES)}")
    if status in LIVE and row.verdict != "ACCEPTED":
        row.problems.append(f"{status} but the handshake says {row.verdict}")
    if status == "active" and issue is None:
        row.problems.append("active but no `issue:` number")
    if status in ("done", "abandoned") and not row.log:
        row.problems.append(f"{status} but the `## Log` has no entry saying why")
    if row.id != path.stem:
        row.problems.append(f"id {row.id!r} does not match the file name {path.stem!r}")
    return row


def last_changed(path: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(path.parent), "log", "-1", "--format=%as %h %s", "--", path.name],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out


def history(path: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(path.parent), "log", "--format=%as %h %s", "--follow", "--", path.name],
        capture_output=True,
        text=True,
        timeout=20,
    ).stdout
    return [ln for ln in out.splitlines() if ln]


def load(specs_dir: Path, repo_cfg: dict | None = None) -> list[SpecRow]:
    rows = []
    for p in sorted(specs_dir.glob("*.md")):
        if p.name.startswith("_") or p.name.upper() == "README.MD":
            continue
        r = read_spec(p, repo_cfg)
        r.changed = last_changed(p)
        rows.append(r)
    order = {s: i for i, s in enumerate(("active", "ready", "draft", "done", "abandoned"))}
    rows.sort(key=lambda r: (order.get(r.status, 9), r.id))
    return rows


def render(rows: list[SpecRow]) -> str:
    if not rows:
        return "No specs yet. Copy specs/_TEMPLATE.md to specs/<id>.md.\n"
    lines = ["| status | id | issue | tier | handshake | last change |", "|---|---|---|---|---|---|"]
    for r in rows:
        iss = f"#{r.issue}" if r.issue else "-"
        lines.append(f"| {r.status} | {r.id} | {iss} | {r.tier or '-'} | {r.verdict} | {r.changed or '-'} |")
    bad = [(r, p) for r in rows for p in r.problems]
    if bad:
        lines += ["", "Problems:"] + [f"- {r.id}: {p}" for r, p in bad]
    return "\n".join(lines) + "\n"
