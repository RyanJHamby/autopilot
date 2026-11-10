"""Where apx's service accounts live and how to ask the operating system about them, on macOS and on Linux.

apx runs on a Mac today and will run on a Linux host. Nothing here changes what the Mac does: every Mac value is the one that used to be
hard-coded. What changes is that the paths and the admin check are no longer macOS-only, and the notifier no longer crashes without
`osascript`. `is_darwin()` is the one switch every platform decision goes through, so a test can simulate either OS by patching it
(never by patching the global `sys.platform`, which breaks the standard library's own lazy imports).
"""

from __future__ import annotations

import pwd
import sys

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
