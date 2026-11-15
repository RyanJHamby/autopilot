"""Where apx's service accounts live and how to ask the operating system about them, on macOS and on Linux.

apx runs on a Mac today and will run on a Linux host. Nothing here changes what the Mac does: every Mac value is the one that used to be
hard-coded. What changes is that the paths and the admin check are no longer macOS-only, and the notifier no longer crashes without
`osascript`. `is_darwin()` is the one switch every platform decision goes through, so a test can simulate either OS by patching it
(never by patching the global `sys.platform`, which breaks the standard library's own lazy imports).
"""

from __future__ import annotations

import os
import pwd
import shutil
import sys
import tempfile
from pathlib import Path

# An account in any of these groups can become root, so a sandbox account must not be in one.
ADMIN_GROUPS = frozenset({"sudo", "admin", "wheel"})


def is_darwin() -> bool:
    return sys.platform == "darwin"


def home_of(user: str) -> str:
    """The account's real home directory if it exists. Otherwise the platform's convention, so a settings file can be read (and a doctor
    can say the account is missing) before the account has been created."""
    try:
        return pwd.getpwnam(user).pw_dir
    except KeyError:
        return f"/Users/{user}" if is_darwin() else f"/home/{user}"


def default_shared_dir() -> str:
    """The directory the sandbox accounts can read and only apx can write (the release layout, the kit, the shared venv)."""
    return "/Users/Shared/apx" if is_darwin() else "/srv/apx"


def state_dir(env=None) -> Path:
    """apx's private state directory: apx.env, the App key, and (by default) the ledger and the work dir. APX_STATE, else ~/.apx: the
    rule `apx setup` already uses. HOME comes from the given settings (the units set HOME=/home/apx), else the account database."""
    e = os.environ if env is None else env
    if e.get("APX_STATE"):
        return Path(e["APX_STATE"])
    return Path(e.get("HOME") or pwd.getpwuid(os.getuid()).pw_dir) / ".apx"


def default_db_path(env=None) -> str:
    """The ledger outlives every release: never relative (that resolves inside releases/<sha>) and never under a tmp dir."""
    return str(state_dir(env) / "apx.sqlite")


def default_work_dir(env=None) -> Path:
    """One work dir (and so one apx.lock) for the daemon and the updater, outside /tmp because each unit has its own (PrivateTmp)."""
    return state_dir(env) / "work"


def tmp_roots() -> tuple[str, ...]:
    """Directories that are per-unit (systemd PrivateTmp) or cleaned by the OS, so nothing durable or shared may live under them."""
    roots = {"/tmp", "/var/tmp", os.path.realpath(tempfile.gettempdir())}
    if is_darwin():
        roots |= {"/private/tmp", "/private/var/tmp"}
    return tuple(sorted(roots))


def is_under(path: str, root: str) -> bool:
    p, r = os.path.realpath(path), os.path.realpath(root)
    return p == r or p.startswith(r.rstrip("/") + "/")


def adopt_old_ledger(new: Path, old: Path) -> str | None:
    """Once: if the durable ledger does not exist yet and the old relative default left one (in the release the service ran from), copy
    it (never move or delete it), so the day's runs, caps and breaker state carry over. Returns a line to log, or None."""
    new.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if new.exists() or not old.is_file() or os.path.realpath(old) == os.path.realpath(new):
        return None
    tmp = new.with_name(new.name + ".adopting")
    shutil.copyfile(old, tmp)
    os.chmod(tmp, 0o600)
    os.replace(tmp, new)
    return f"ledger: copied the per-release ledger {old} to {new} (once; the old file is left in place)"


def admin_check_argv(user: str) -> list[str]:
    """The command (run as the account itself) that tells whether it is an administrator, using a tool that exists on this OS."""
    if is_darwin():
        return ["/usr/sbin/dseditgroup", "-o", "checkmember", "-m", user, "admin"]
    return ["/usr/bin/id", "-nG", user]


def is_admin(result, user: str) -> bool:
    """Read the answer to `admin_check_argv`. macOS: the sentence dseditgroup prints. Linux: whether any group is an admin group."""
    out = (getattr(result, "stdout", "") or "") + (getattr(result, "stderr", "") or "")
    if is_darwin():
        return "is a member" in out and "NOT" not in (getattr(result, "stdout", "") or "")
    return any(group in ADMIN_GROUPS for group in (getattr(result, "stdout", "") or "").split())
