"""`ap queue`: read-only status of batch manifests, and a local-file-only scaffold for a new one.

Nothing here labels an issue, files an issue, pushes, or merges. `add` writes `.autopilot/batches/<id>.yaml` locally; the owner
opens and merges the PR, which is the batch approval.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from autopilot.apx import batch as batch_mod

_AGENT = re.compile(r"agent/(\d+)-")


def item_states(b: batch_mod.Batch, prs: list[dict], labels: dict[int, set[str]]) -> list[tuple[int, str]]:
    """prs: gh pr list rows (headRefName, state, mergedAt). labels: open issue number -> label names.
    State is one of merged | pr-open | closed-unmerged | waiting #N | needs-label | held | ready."""
    merged, open_, closed = set(), set(), set()
    for p in prs:
        m = _AGENT.match(p.get("headRefName") or "")
        if not m:
            continue
        n = int(m.group(1))
        if p.get("mergedAt"):
            merged.add(n)
        elif p.get("state") == "OPEN":
            open_.add(n)
        else:
            closed.add(n)
    out = []
    for it in b.items:
        n = it.issue
        names = labels.get(n)
        if n in merged:
            s = "merged"
        elif n in open_:
            s = "pr-open"
        elif names is None:
            s = "issue-closed-or-missing"
        elif names & {"hold", "needs-human", "blocked"}:
            s = "held (" + ", ".join(sorted(names & {"hold", "needs-human", "blocked"})) + ")"
        elif any(d not in merged for d in it.depends_on):
            s = "waiting " + ", ".join(f"#{d}" for d in it.depends_on if d not in merged)
        elif "agent-ready" not in names:
            s = "needs-label"
        elif n in closed:
            s = "closed-unmerged (retry?)"
        else:
            s = "ready"
        out.append((n, s))
    return out


def render(b: batch_mod.Batch, states: list[tuple[int, str]]) -> str:
    done = sum(1 for _, s in states if s == "merged")
    lines = [f"batch {b.id}: {done}/{len(states)} merged"]
    for (n, s), it in zip(states, b.items):
        dep = f"  after {', '.join('#' + str(d) for d in it.depends_on)}" if it.depends_on else ""
        lines.append(f"  #{n:<5} {s}{dep}")
    return "\n".join(lines) + "\n"


def preflight(specs: list[str], prs: list[dict], labels: dict[int, set[str]], retry: bool = False) -> tuple[list[str], list[str]]:
    """(errors, warnings) for a batch about to be written. An issue that already has a merged agent PR is an error unless `retry`
    (the planner would skip it anyway, so listing it only misleads), as is an issue that is not open. A missing agent-ready label is a
    warning: applying it is the owner's act."""
    merged = {int(m.group(1)) for p in prs if p.get("mergedAt") and (m := _AGENT.match(p.get("headRefName") or ""))}
    errors, warns = [], []
    for s in specs:
        n = int(s.partition(":")[0])
        if n in merged and not retry:
            errors.append(f"#{n} already has a merged agent PR (pass --retry if you really want it run again)")
        elif n not in labels:
            errors.append(f"#{n} is closed or does not exist")
        elif "agent-ready" not in labels[n]:
            warns.append(f"#{n} is not labelled agent-ready yet (yours to apply)")
    return errors, warns


def scaffold(batch_id: str, specs: list[str], directory: Path) -> Path:
    """specs like ["101", "102:101", "103:101,102"] = issue[:deps]. Written locally, validated by the same parser the planner uses."""
    items = []
    for s in specs:
        num, _, deps = s.partition(":")
        row: dict = {"issue": int(num)}
        if deps:
            row["depends_on"] = [int(d) for d in deps.split(",")]
        items.append(row)
    text = yaml.safe_dump({"id": batch_id, "items": items}, sort_keys=False)
    batch_mod.parse(text)  # raises BatchError rather than writing a file the planner would ignore
    path = directory / f"{batch_id}.yaml"
    if path.exists():
        raise FileExistsError(str(path))
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path
