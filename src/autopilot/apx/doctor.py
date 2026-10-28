"""apx doctor: one command that checks the whole setup before anything runs live. Read-only against GitHub.

It also enforces least privilege on the GitHub App itself: if the App was created with more permission than apx needs
(administration, workflows, secrets...) or is installed on more repos than the three in scope, the doctor FAILS, so a
mis-click in the GitHub UI cannot silently widen what a leaked key could do.
"""

from __future__ import annotations

import re
import shutil
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "kit" / "runtime"))
import automerge as kit_automerge  # noqa: E402

from .app_auth import TokenCache, make_jwt  # noqa: E402
from .github import make_api  # noqa: E402
from .planner import ALLOWED_REPOS  # noqa: E402

RANK = {"read": 1, "write": 2, "admin": 3}
REQUIRED = {
    "metadata": "read",
    "contents": "write",
    "pull_requests": "write",
    "issues": "write",
    "checks": "write",
    "actions_variables": "read",
}
# Anything outside REQUIRED is refused unless it is in this harmless set (read-only, no code or secret reach).
TOLERATED_EXTRA = {"metadata"}


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


def check_permissions(granted: dict) -> list[Check]:
    out = []
    for perm, need in REQUIRED.items():
        have = granted.get(perm)
        ok = have is not None and RANK.get(have, 0) >= RANK[need]
        out.append(Check(f"app permission {perm}>={need}", ok, f"granted: {have}"))
    extra = {k: v for k, v in granted.items() if k not in REQUIRED and k not in TOLERATED_EXTRA}
    out.append(Check("app has no extra permissions", not extra, f"unexpected: {sorted(extra)}" if extra else "none"))
    over = {k: v for k, v in granted.items() if k in REQUIRED and RANK.get(v, 0) > RANK[REQUIRED[k]]}
    out.append(Check("app permissions not above need", not over, f"too high: {over}" if over else "none"))
    return out


def token_shape(path: str) -> Check:
    """Looks only at the SHAPE of the token file, never its value: one line of token-safe characters, long enough. Catches
    the common mistake of saving the wrong clipboard contents (a sentence, a command, an error message)."""
    try:
        raw = Path(path).read_text()
    except OSError as e:
        return Check("claude token shape", False, f"cannot read ({type(e).__name__})")
    body = raw.strip()
    problems = []
    if len(body) < 40:
        problems.append(f"too short ({len(body)} chars)")
    if any(ch.isspace() for ch in body):
        problems.append("contains whitespace (not a token)")
    elif not re.fullmatch(r"[A-Za-z0-9._~+/=-]+", body or "-"):
        problems.append("contains characters a token never has")
    detail = "; ".join(problems) if problems else f"{len(body)} chars, one line"
    if not problems and not body.startswith("sk-ant-"):
        detail += " (note: does not start with sk-ant-; unusual)"
    return Check("claude token shape", not problems, detail)


def _mode_ok(path: str) -> tuple[bool, str]:
    try:
        st = Path(path).stat()
    except OSError as e:
        return False, f"cannot stat ({type(e).__name__})"
    open_bits = st.st_mode & (stat.S_IRWXG | stat.S_IRWXO)
    return open_bits == 0, "mode 600/700 ok" if open_bits == 0 else "permissions too open; chmod 600"


def run_doctor(
    s,
    *,
    api_factory: Callable = make_api,
    which: Callable = shutil.which,
    approved: Callable[[str], list[str]] = kit_automerge.fetch_approved,
) -> list[Check]:
    out: list[Check] = []
    for tool, required in (("git", True), ("openssl", True), ("claude", True), ("gh", False)):
        found = which(tool) is not None
        out.append(
            Check(
                f"tool {tool}",
                found or not required,
                "found" if found else "missing" + ("" if required else " (needed only for the merge lane)"),
            )
        )
    for label, path in (("app key", str(s.key_path)), ("claude oauth file", s.oauth_file)):
        ok, why = _mode_ok(path)
        out.append(Check(f"{label} file", ok, why))
    out.append(token_shape(s.oauth_file))
    out.append(Check("installations within scope", set(s.installations) <= ALLOWED_REPOS, ", ".join(sorted(s.installations))))
    try:
        jwt_api = api_factory(make_jwt(s.app_id, s.key_path))
        app = jwt_api("GET", "/app")
        out.append(Check("app id matches", str(app.get("id")) == str(s.app_id), f"api says {app.get('id')}"))  # type: ignore[union-attr]
        out.extend(check_permissions(app.get("permissions", {})))  # type: ignore[union-attr]
    except Exception as e:  # noqa: BLE001 - report, never crash the doctor
        out.append(Check("app authentication", False, f"{type(e).__name__}: key, app id or network"))
        return out
    cache = TokenCache(s.app_id, s.key_path, s.installations, api_factory=api_factory)
    for repo in sorted(s.installations):
        try:
            repos = cache.api_for(repo)("GET", "/installation/repositories?per_page=100")["repositories"]  # type: ignore[index]
            names = {r["full_name"] for r in repos}
            extra = names - ALLOWED_REPOS
            out.append(
                Check(
                    f"installation for {repo}",
                    repo in names and not extra,
                    f"covers {sorted(names)}" + (f"; OUT OF SCOPE: {sorted(extra)}" if extra else ""),
                )
            )
        except Exception as e:  # noqa: BLE001
            out.append(Check(f"installation for {repo}", False, f"{type(e).__name__}"))
    try:
        ok = s.kit_ref in approved(s.kit_repo)
        out.append(Check("kit sha is approved", ok, s.kit_ref[:7] if ok else f"{s.kit_ref[:7]} is not on the APPROVED list"))
    except Exception as e:  # noqa: BLE001
        out.append(Check("kit sha is approved", False, f"could not read APPROVED ({type(e).__name__})"))
    return out


def render(checks: list[Check]) -> tuple[str, bool]:
    lines = [f"{'PASS' if c.ok else 'FAIL'}  {c.name}: {c.detail}" for c in checks]
    ok = all(c.ok for c in checks)
    lines.append("")
    lines.append(
        "doctor: all checks passed"
        if ok
        else f"doctor: {sum(not c.ok for c in checks)} check(s) failed; fix before any --live run"
    )
    return "\n".join(lines), ok
