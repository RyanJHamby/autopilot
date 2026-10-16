"""Failure retro evidence: classify why agent work did not land. Pure functions; no network, no model.

The evidence packet is what a cheap model (or the owner) reads to write a lesson. Counting causes first means lessons
target what actually keeps failing instead of whatever the last failure was.
"""

from __future__ import annotations

import re
from collections import Counter

GUARD_RE = re.compile(
    r"\[(secret|comms|protected-path|mcp-config|test-deletion|test-weakening|size|path|symlink|mode|binary|rename)\]"
)


def classify_run(run: dict) -> str | None:
    """run: {conclusion, failed_step?, guard_output?, pr_opened?}. None = a success worth ignoring."""
    c = run.get("conclusion")
    if c in ("success", "skipped", "cancelled", None, ""):
        return None
    if c == "timed_out":
        return "timeout"
    m = GUARD_RE.search(run.get("guard_output") or "")
    if m:
        return f"guard:{m.group(1)}"
    step = (run.get("failed_step") or "").lower()
    if "claude" in step or "anthropic" in step:
        return "agent-error"
    if step:
        return f"infra:{re.sub(r'[^a-z0-9]+', '-', step).strip('-')[:40]}"
    return "failed-unknown"


def classify_pr(pr: dict) -> str | None:
    """pr: {state, mergedAt, ci?: green|red, guard_output?, comments?: int}. Closed-unmerged agent PRs only."""
    if pr.get("mergedAt") or pr.get("state") != "CLOSED":
        return None
    m = GUARD_RE.search(pr.get("guard_output") or "")
    if m:
        return f"guard:{m.group(1)}"
    if pr.get("ci") == "red":
        return "ci-red"
    return "rejected-by-owner" if (pr.get("comments") or 0) > 0 else "closed-no-reason"


def causes(runs: list[dict], prs: list[dict]) -> Counter:
    out: Counter = Counter()
    for r in runs:
        k = classify_run(r)
        if k:
            out[k] += 1
    for p in prs:
        k = classify_pr(p)
        if k:
            out[k] += 1
    return out


def packet(counter: Counter, examples: dict[str, list[str]], *, min_count: int = 2) -> str:
    """Markdown the lesson-writer reads. Only causes seen at least min_count times become lesson candidates."""
    lines = ["# Failure retro evidence", ""]
    if not counter:
        return "\n".join(lines + ["No failures in the window.", ""])
    lines += ["| cause | count | lesson candidate |", "|---|---|---|"]
    for cause, n in counter.most_common():
        lines.append(f"| {cause} | {n} | {'yes' if n >= min_count else 'no (seen once)'} |")
    lines.append("")
    for cause, n in counter.most_common():
        if n >= min_count and examples.get(cause):
            lines += [f"## {cause}", *[f"- {e}" for e in examples[cause][:5]], ""]
    lines.append("Lessons go in `.autopilot/lessons.md` through a PR the owner reviews. Never loosen a guardrail in a lesson.")
    return "\n".join(lines) + "\n"
