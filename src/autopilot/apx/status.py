"""apx status file and the owner-only watcher.

After every pass apx writes a small JSON file that anyone on the Mac can read (no secrets: repo names, counts, the pass log). The
watcher runs as the OWNER, reads it, and shows a LOCAL macOS notification when apx has stopped or its last pass had problems. Nothing
here touches the network, email, chat or any other person: the only recipient is the owner's own screen.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .redact import redact

PROBLEM_WORDS = ("planner error", "crashed", "failed", "config error", "rolled back")
DEFAULT_STATUS = "/Users/Shared/apx/status.json"
DEFAULT_UPDATE_STATUS = "/Users/Shared/apx/update.json"
STALE_AFTER = dt.timedelta(minutes=15)  # the timer fires every 2 minutes; a long agent run can hold a pass for a while


def problems_in(lines: list[str]) -> list[str]:
    return [ln for ln in lines if any(w in ln for w in PROBLEM_WORDS)]


def write_status(path: str | Path, lines: list[str], *, live: bool, version: str = "", now: dt.datetime | None = None) -> bool:
    """Atomic, world-readable, never raises (a status file must not be able to break a pass). True if written."""
    now = now or dt.datetime.now(dt.timezone.utc)
    clean = [redact(ln)[:300] for ln in lines][:60]
    body = {
        "ts": now.astimezone(dt.timezone.utc).isoformat(),
        "live": live,
        "version": version,
        "ok": not problems_in(clean),
        "problems": problems_in(clean)[:10],
        "lines": clean,
    }
    try:
        path = Path(path)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".status-")
        with os.fdopen(fd, "w") as fh:
            json.dump(body, fh)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def check_status(path: str | Path, *, now: dt.datetime | None = None, stale_after: dt.timedelta = STALE_AFTER) -> tuple[str, str]:
    """('ok'|'stale'|'problem'|'missing', one-line message)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        s = json.loads(Path(path).read_text())
        ts = dt.datetime.fromisoformat(s["ts"])
    except (OSError, ValueError, KeyError, TypeError):
        return "missing", "apx has not written a status file (is the daemon running?)"
    age = now - ts
    if age > stale_after:
        return "stale", f"apx last finished a pass {int(age.total_seconds() // 60)} minutes ago"
    if not s.get("ok", False):
        first = (s.get("problems") or ["unknown problem"])[0]
        return "problem", f"apx's last pass had a problem: {first}"[:200]
    return "ok", f"apx ok, last pass {int(age.total_seconds() // 60)} min ago"


def code_version(code_dir: str) -> str:
    try:
        p = subprocess.run(["git", "-C", code_dir, "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10)
        return p.stdout.strip() if p.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def notify(title: str, message: str) -> None:
    """A local macOS notification on the owner's own screen. Arguments are passed as argv, never interpolated into the script."""
    script = "on run argv\ndisplay notification (item 2 of argv) with title (item 1 of argv)\nend run"
    subprocess.run(["/usr/bin/osascript", "-e", script, title, message], capture_output=True, timeout=15)


def check_update(path: str | Path) -> tuple[str, str]:
    """The updater's last line. A missing or unreadable file is fine (the updater may not be installed); only a problem counts, and
    it is never 'stale': a rollback stays raised until the owner deals with it."""
    try:
        s = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return "ok", ""
    if s.get("ok", True):
        return "ok", ""
    return "problem", f"apx updater: {(s.get('problems') or ['unknown problem'])[0]}"[:200]


def watch_once(
    path: str | Path,
    state_file: str | Path,
    *,
    now: dt.datetime | None = None,
    notifier=notify,
    update_path: str | Path | None = None,
) -> str:
    """Notify once per distinct problem (and once when it clears); returns the level. State lives in the owner's own file."""
    level, msg = check_status(path, now=now)
    if level == "ok" and update_path:
        level, msg = check_update(update_path)
        if level == "ok":
            msg = ""
    state = Path(state_file)
    try:
        last = state.read_text().strip()
    except OSError:
        last = "ok"
    key = f"{level}:{msg}" if level == "problem" else level  # a stale message counts minutes: it must not re-notify every check
    if key != last:
        if level == "ok":
            notifier("apx", "apx is running again")
        else:
            notifier("apx needs a look", msg)
        try:
            state.write_text(key)
        except OSError:
            pass
    return level


def main(argv: list[str] | None = None) -> int:
    path = os.environ.get("APX_STATUS", DEFAULT_STATUS)
    state = os.environ.get("APX_WATCH_STATE", str(Path.home() / ".apx-watch-state"))
    if argv and argv[0] == "--print":
        level, msg = check_status(path)
        print(f"{level}: {msg}")
        return 0 if level == "ok" else 1
    return 0 if watch_once(path, state, update_path=os.environ.get("APX_UPDATE_STATUS", DEFAULT_UPDATE_STATUS)) == "ok" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
