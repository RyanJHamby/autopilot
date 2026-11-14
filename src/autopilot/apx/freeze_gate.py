"""Work-hours freeze for apx: nothing STARTS inside the window in policy/time.yaml.

The window is decided by the one resolver, `autopilot.freeze.check_file` (this module does no time arithmetic of its own). Anything
that goes wrong, a resolver exception, a clock that cannot be read, an unreadable policy file, means frozen: the resolver falls back
to the default window for a bad file, and this module treats an exception from the resolver itself as frozen. There is no argument,
flag or environment variable that lifts it; the only lift is a date listed in time.yaml.

`APX_ACTIVE_WINDOW` (apx.window) is a second, optional setting. It is ANDed with this gate, so it can only narrow what time.yaml
allows, never widen it.

What is held (all of it, checked again before every action so a pass that begins at 08:29 stops at 08:30):
  agent runs, CI-fix runs, merges, branch updates, and, by default, the check runs apx posts on PRs (`check-pr`, `check-main`).
Whether check runs are held is ONE setting, `apx_freeze_gates_check_runs` under `defaults:` in policy/portfolio.yaml. It is true.
Only the literal YAML `false` turns it off, so a missing, unreadable or odd value keeps check runs held (fail closed).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import yaml

from autopilot import freeze

from . import window as window_mod

POLICY_FILE = freeze.DEFAULT_FILE
PORTFOLIO_FILE = Path(freeze.DEFAULT_FILE).with_name("portfolio.yaml")
CHECK_KINDS = frozenset({"check-pr", "check-main"})  # posting check runs; every other kind of action changes a repo and is always held


def _clock() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def frozen_reason() -> str | None:
    """None when work may start; otherwise why not."""
    try:
        v = freeze.check_file(POLICY_FILE, clock=lambda: _clock())
    except Exception as e:  # noqa: BLE001 - a resolver that cannot answer is a freeze
        return f"freeze resolver failed ({type(e).__name__}): refusing to start work"
    return f"freeze: {v.reason}" if v.frozen else None


def checks_gated() -> bool:
    """Do check runs wait for the end of the window too? True unless policy/portfolio.yaml says `apx_freeze_gates_check_runs: false`."""
    try:
        return yaml.safe_load(Path(PORTFOLIO_FILE).read_text())["defaults"]["apx_freeze_gates_check_runs"] is not False
    except Exception:  # noqa: BLE001 - unreadable or malformed means gated
        return True


def action_gate(kind: str) -> str | None:
    """Reason this action may not start now, else None. Unknown kinds are treated as work."""
    reason = frozen_reason()
    if reason is None:
        return None
    if kind in CHECK_KINDS and not checks_gated():
        return None
    return reason


def pass_blocked(active_window: window_mod.Window | None, now: dt.datetime | None = None) -> str | None:
    """A whole pass (or update) should not begin: the freeze, or the narrower APX_ACTIVE_WINDOW, says so. Returns the idle line."""
    reason = frozen_reason()
    if reason is not None and checks_gated():
        return f"idle: {reason}; nothing ran"
    if active_window is not None:
        try:
            at = now if now is not None else _clock()
            if not active_window.is_open(at):
                return window_mod.idle_line(active_window)
        except Exception as e:  # noqa: BLE001
            return f"idle: clock unusable for the active window ({type(e).__name__}); nothing ran"
    return None
