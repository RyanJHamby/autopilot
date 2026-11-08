"""Intake lint: an `agent-ready` issue must carry a runnable acceptance command before the planner dispatches it.

Deterministic and free: no model, no network. Reuses the kit handshake's own definition of "a runnable command", so
the two cannot drift. An issue that fails is held (never labelled, commented or closed) and the planner's note says why."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "kit" / "runtime"))
from handshake import _looks_like_command  # noqa: E402

_HEADING = re.compile(r"^#{1,6}\s*acceptance\b.*$", re.I | re.M)
_NEXT_HEADING = re.compile(r"^#{1,6}\s", re.M)
_TICKS = re.compile(r"`([^`\n]+)`")


def acceptance_commands(body: str) -> list[str]:
    """Backticked items under the first `## Acceptance` heading, up to the next heading."""
    m = _HEADING.search(body or "")
    if not m:
        return []
    rest = body[m.end() :]
    nxt = _NEXT_HEADING.search(rest)
    section = rest[: nxt.start()] if nxt else rest
    return [c.strip() for c in _TICKS.findall(section) if c.strip()]


def problem(body: str) -> str | None:
    """None when the issue is dispatchable, else one short reason."""
    cmds = acceptance_commands(body)
    if not cmds:
        return "no `## Acceptance` section with a backticked command"
    bad = [c for c in cmds if not _looks_like_command(c)]
    if bad:
        return f"acceptance item is not a runnable command: {bad[0][:40]}"
    return None
