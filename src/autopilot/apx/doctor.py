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


def sandbox_checks(s, launcher) -> list[Check]:
    """Prove the split holds on THIS machine, from the sandbox account's point of view. The decisive checks are the negative
    ones: the account that runs a PR's code must NOT be able to read the App key, the Claude token or the orchestrator's home."""

    def run(argv):
        try:
            return launcher.run(argv, cwd="/", env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=60)
        except Exception as e:  # noqa: BLE001
            return type("R", (), {"returncode": 255, "stdout": "", "stderr": type(e).__name__})()

    out: list[Check] = []
    who = run(["/usr/bin/id", "-un"])
    out.append(
        Check(
            "sandbox account is usable via sudo",
            who.returncode == 0 and who.stdout.strip() == s.ci_user,
            who.stderr.strip()[:80] or s.ci_user,
        )
    )
    admin = run(["/usr/sbin/dseditgroup", "-o", "checkmember", "-m", s.ci_user, "admin"])
    out.append(
        Check(
            "sandbox account is not an admin",
            "is a member" not in (admin.stdout + admin.stderr) or "NOT" in admin.stdout,
            "standard user",
        )
    )
    for label, path in (
        ("App key", str(s.key_path)),
        ("Claude token", s.oauth_file),
        ("orchestrator home", str(Path(s.key_path).parent)),
    ):
        r = run(["/bin/ls", path] if label == "orchestrator home" else ["/bin/cat", path])
        leaked = r.returncode == 0
        out.append(
            Check(
                f"sandbox account CANNOT read the {label}",
                not leaked,
                "readable: the split is not in place" if leaked else "denied",
            )
        )
    work = run(["/bin/sh", "-c", f'test -d "{s.ci_work}" && test -w "{s.ci_work}"'])
    out.append(Check("sandbox work directory exists and is writable", work.returncode == 0, s.ci_work))
    py = run([f"{s.shared_dir}/venv/bin/python", "-c", "import yaml"])
    # without PyYAML the kit guard silently loses its config, which would weaken it: treat as a failure
    out.append(
        Check(
            "sandbox python has PyYAML (guard config would silently vanish without it)",
            py.returncode == 0,
            f"{s.shared_dir}/venv",
        )
    )
    return out


def agent_checks(s, launcher) -> list[Check]:
    """The model's account: it may hold the Claude token and nothing that can write to GitHub. Proven from ITS side, plus the one
    check only the orchestrator can make: that this account no longer keeps a copy of the Claude token."""
    home = f"/Users/{s.agent_user}"
    token = s.oauth_file
    code_dir = s.code_dir()
    python = f"{s.shared_dir}/venv/bin/python"
    binary = s.agent_binary or f"{home}/.local/bin/claude"

    def run(argv, env=None):
        try:
            return launcher.run(argv, cwd="/", env=env or {"PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=60)
        except Exception as e:  # noqa: BLE001
            return type("R", (), {"returncode": 255, "stdout": "", "stderr": type(e).__name__})()

    out: list[Check] = []
    who = run(["/usr/bin/id", "-un"])
    out.append(
        Check("agent account is usable via sudo", who.returncode == 0 and who.stdout.strip() == s.agent_user, s.agent_user)
    )
    admin = run(["/usr/sbin/dseditgroup", "-o", "checkmember", "-m", s.agent_user, "admin"])
    out.append(
        Check(
            "agent account is not an admin",
            "is a member" not in (admin.stdout + admin.stderr) or "NOT" in admin.stdout,
            "standard user",
        )
    )
    for label, argv in (
        ("the App key", ["/bin/cat", str(s.key_path)]),
        ("the orchestrator home", ["/bin/ls", str(Path(s.key_path).parent)]),
    ):
        r = run(argv)
        out.append(
            Check(
                f"agent account CANNOT read {label}",
                r.returncode != 0,
                "readable: no write-key separation" if r.returncode == 0 else "denied",
            )
        )
    shape = run(
        [
            python,
            "-c",
            f"from autopilot.apx.doctor import token_shape as t; c=t({token!r}); print('OK' if c.ok else 'BAD '+c.detail)",
        ],
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": f"{code_dir}/src"},
    )
    out.append(
        Check(
            "agent account can read its own Claude token (shape checked, value not shown)",
            shape.stdout.strip() == "OK",
            shape.stdout.strip()[:80] or "unreadable",
        )
    )
    kept = Path(s.key_path).parent / "claude-oauth"
    out.append(
        Check(
            "orchestrator no longer holds a copy of the Claude token",
            not kept.exists(),
            f"remove {kept}" if kept.exists() else "gone",
        )
    )
    ver = run([binary, "--version"])
    out.append(Check("agent account can run the claude CLI", ver.returncode == 0, ver.stdout.strip()[:40] or binary))
    work = run(["/bin/sh", "-c", f'test -d "{s.agent_work or home + "/work"}" && test -w "{s.agent_work or home + "/work"}"'])
    out.append(Check("agent work directory exists and is writable", work.returncode == 0, s.agent_work or home + "/work"))
    return out


def run_doctor(
    s,
    *,
    api_factory: Callable = make_api,
    which: Callable = shutil.which,
    approved: Callable[[str], list[str]] = kit_automerge.fetch_approved,
    launcher=None,
    agent_launcher=None,
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
    # with an agent account the Claude token lives in ITS home and this account must not (and cannot) read it
    for label, path in (("app key", str(s.key_path)),) + (() if s.agent_user else (("claude oauth file", s.oauth_file),)):
        ok, why = _mode_ok(path)
        out.append(Check(f"{label} file", ok, why))
    if not s.agent_user:
        out.append(token_shape(s.oauth_file))
        out.append(Check("agent account configured (APX_AGENT_USER)", True, "none: agent runs stay blocked (backlog S1b)"))
    if s.ci_user:
        from .runas import Launcher

        out.extend(sandbox_checks(s, launcher or Launcher(s.ci_user)))
    else:
        out.append(
            Check("sandbox account configured (APX_CI_USER)", False, "PR code still runs as the account that holds the secrets")
        )
    if s.agent_user:
        from .runas import Launcher as _L

        out.extend(agent_checks(s, agent_launcher or _L(s.agent_user)))
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
