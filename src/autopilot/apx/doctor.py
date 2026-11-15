"""apx doctor: one command that checks the whole setup before anything runs live. Read-only against GitHub.

It also enforces least privilege on the GitHub App itself: if the App was created with more permission than apx needs
(administration, workflows, secrets...) or is installed on more repos than the three in scope, the doctor FAILS, so a
mis-click in the GitHub UI cannot silently widen what a leaked key could do.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import sqlite3
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "kit" / "runtime"))
import automerge as kit_automerge  # noqa: E402

from .. import claude_floor  # noqa: E402
from . import caps, enroll, host_tools, hostenv, repo_ci, sandbox, spend, sprint, toolchains  # noqa: E402
from .app_auth import TokenCache, make_jwt  # noqa: E402
from .github import make_api  # noqa: E402
from .ledger import Ledger  # noqa: E402
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
    admin = run(hostenv.admin_check_argv(s.ci_user))
    out.append(Check("sandbox account is not an admin", not hostenv.is_admin(admin, s.ci_user), "standard user"))
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
    home = hostenv.home_of(s.agent_user)
    token = s.oauth_file
    code_dir = s.code_dir()
    python = f"{s.shared_dir}/venv/bin/python"
    binary = s.agent_bin()

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
    admin = run(hostenv.admin_check_argv(s.agent_user))
    out.append(Check("agent account is not an admin", not hostenv.is_admin(admin, s.agent_user), "standard user"))
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
    floor_ok, floor_detail = claude_floor.check_result(ver.returncode, ver.stdout)
    out.append(Check("agent account claude meets the version floor", floor_ok, floor_detail))
    work = run(["/bin/sh", "-c", f'test -d "{s.agent_work or home + "/work"}" && test -w "{s.agent_work or home + "/work"}"'])
    out.append(Check("agent work directory exists and is writable", work.returncode == 0, s.agent_work or home + "/work"))
    return out


def state_path_checks(s) -> list[Check]:
    """The ledger must outlive every release and the work dir (with its apx.lock) must be the one both the daemon and the updater see.
    Both come from Settings.from_env (hostenv.default_db_path / default_work_dir when unset), so the two services cannot disagree unless
    a path is relative (each unit has its own working directory) or under /tmp (each Linux unit has its own, PrivateTmp=yes)."""
    out = []
    db, why = str(s.db_path), ""
    if not os.path.isabs(db):
        why = f"{db} is relative: it resolves inside the release the service runs from, so every release switch starts a fresh ledger"
    elif hostenv.is_under(db, s.shared_dir):
        why = f"{os.path.realpath(db)} is under {s.shared_dir}: a release switch would start a fresh ledger (and the sandbox can read it)"
    elif any(hostenv.is_under(db, t) for t in hostenv.tmp_roots()):
        why = f"{os.path.realpath(db)} is under a tmp dir: per-unit (PrivateTmp) or cleaned, so the daily caps would reset"
    out.append(Check("ledger path (APX_DB)", not why, why or os.path.realpath(db)))
    work, why = str(s.work_dir), ""
    if not os.path.isabs(work):
        why = f"{work} is relative: the daemon and the updater run from different directories and would lock different files"
    elif not hostenv.is_darwin() and any(hostenv.is_under(work, t) for t in ("/tmp", "/var/tmp")):
        why = f"{work} is under a tmp dir and each unit has its own (PrivateTmp=yes): the updater would never see the daemon's lock"
    out.append(Check("work dir (APX_WORK, shared by the daemon and the updater)", not why, why or os.path.realpath(work)))
    return out


def _tool_check(repo: str, entry: str, run, data) -> Check:
    tool, minimum = repo_ci.parse_tool(entry)
    name, hint = f"{repo}: host tool {tool}", data.hint_for(repo, tool)
    r = run(["/bin/sh", "-c", 'command -v -- "$1"', "sh", tool])
    lines = r.stdout.strip().splitlines() if r.returncode == 0 else []
    found = lines[-1].strip() if lines and lines[-1].strip().startswith("/") else ""
    if not found:
        return Check(name, False, f"missing on the sandbox PATH; install: {hint}")
    if minimum is not None:
        v = run([found, "--version"])
        m = re.search(r"\d+(?:\.\d+)+", (v.stdout or "") + (v.stderr or "")) if v.returncode == 0 else None
        if not m or repo_ci._ver(m.group(0)) < repo_ci._ver(minimum):
            have = m.group(0) if m else "of unknown version"
            return Check(name, False, f"{found} is {have}, needs {minimum} or newer; install: {hint}")
    probe = data.probe_for(repo, tool)
    if probe is None:
        return Check(name, True, found)
    argv = [found if i == 0 and a == tool else a for i, a in enumerate(probe.argv)]
    p = run(argv, probe.stdin)
    text = (p.stdout or "") + (p.stderr or "")
    ok = p.returncode == 0 and (probe.expect is None or re.search(probe.expect, text) is not None)
    if ok:
        return Check(name, True, f"{found} ({probe.needs})")
    why = text.strip().splitlines()[-1][:100] if text.strip() else f"exit {p.returncode}"
    return Check(name, False, f"{found} lacks {probe.needs} ({why}); install: {hint}")


def repo_tool_checks(s, launcher, *, path_for: Callable[[str], str] | None = None) -> list[Check]:
    """Every host tool each enrolled repo (APX_INSTALLATIONS plus APX_PRIVATE_CI) declares must resolve, AS the sandbox account, on the
    PATH that repo's sandbox job gets, and pass its capability probe if host_tools.json has one. One check per repo and tool."""
    data, specs = host_tools.load(), repo_ci.load_specs()
    toolchain_root = toolchains.default_root(s.shared_dir)
    path_for = path_for or (lambda repo: sandbox.job_path(s.ci_home(), toolchains.bin_dirs(repo, toolchain_root)))
    out = [Check(*c) for c in toolchains.owner_checks(sorted(set(s.installations) | set(s.private_ci)), toolchain_root)]
    for repo in sorted(set(s.installations) | set(s.private_ci)):
        out.extend(tool_checks_for(s, launcher, repo, repo in s.private_ci, path_for=path_for, data=data, specs=specs))
    return out


def tool_checks_for(s, launcher, repo: str, private: bool, *, path_for=None, data=None, specs=None) -> list[Check]:
    """One repo's declared host tools, checked as the sandbox account (also used to decide a discovered repo's promotion)."""
    data, specs = data or host_tools.load(), specs if specs is not None else repo_ci.load_specs()
    path_for = path_for or (lambda r: sandbox.job_path(s.ci_home(), toolchains.bin_dirs(r, toolchains.default_root(s.shared_dir))))
    entries = host_tools.declared(repo, {repo} if private else set(), data, specs)
    if not entries:
        return [Check(f"{repo}: host tools", True, "none declared (src/autopilot/apx/host_tools.json)")]
    env = {"PATH": path_for(repo), "HOME": s.ci_home()}

    def run(argv, stdin=None, env=env):
        try:
            return launcher.run(argv, cwd="/", env=env, capture_output=True, text=True, timeout=120, input=stdin)
        except Exception as e:  # noqa: BLE001 - a broken sudo fails the check, never the doctor
            return type("R", (), {"returncode": 255, "stdout": "", "stderr": type(e).__name__})()

    return [_tool_check(repo, e, run, data) for e in entries]


def discovered_lines(found: dict) -> list[str]:
    return [f"{r}: {f.state} ({f.reason})" for r, f in sorted(found.items())]


def spend_ceiling_check(db_path: str) -> Check:
    """policy's defaults.global_usd_per_day, validated exactly as the planner does (caps.global_usd_per_day). Absent is an advisory, not
    a failure; invalid fails, because the planner then holds every agent run. The 24h spend is read-only from the ledger (spend.used_24h)."""
    name = "global spend ceiling (global_usd_per_day)"
    try:
        ceiling = caps.global_usd_per_day()
    except caps.CapError as e:
        return Check(name, False, f"{e}; the planner holds every agent run and CI fix until this is fixed")
    if ceiling is None:
        return Check(
            name,
            True,
            "not set: no daily dollar ceiling across repos (add `global_usd_per_day:` under `defaults:` in policy/portfolio.yaml)",
        )
    try:
        led = Ledger.read_only(db_path)
        try:
            used = spend.used_24h(led)
        finally:
            led.db.close()
    except sqlite3.Error as e:
        return Check(name, True, f"${ceiling:.2f} per rolling 24h; current spend not shown: ledger {db_path} unreadable ({type(e).__name__})")
    full = "; full: new agent runs are held" if used >= ceiling else ""
    return Check(name, True, f"${ceiling:.2f} per rolling 24h; ${used:.2f} used in the last 24h (ledger {db_path}){full}")


def sprint_check(db_path: str, now=None) -> Check:
    """Active sprints (sprint.py) with the runs, dollars and time each has left, read-only from the ledger. Advisory: never fails."""
    name = "sprints (yolo repos, owner `sprint` label)"
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        led = Ledger.read_only(db_path)
        try:
            lines = sprint.doctor_lines(led, now)
        finally:
            led.db.close()
    except sqlite3.Error as e:
        return Check(name, True, f"none active (ledger {db_path} unreadable or has no sprints yet: {type(e).__name__})")
    return Check(name, True, "; ".join(lines) if lines else "none active")


def run_doctor(
    s,
    *,
    api_factory: Callable = make_api,
    which: Callable = shutil.which,
    approved: Callable[[str], list[str]] = kit_automerge.fetch_approved,
    launcher=None,
    agent_launcher=None,
    claude_probe: Callable | None = None,
) -> list[Check]:
    out: list[Check] = []
    # With an agent account, claude runs as that account (checked below with its own floor); the orchestrator never runs it.
    claude_needed_here = not s.agent_user
    for tool, required in (("git", True), ("openssl", True), ("claude", claude_needed_here), ("gh", False)):
        found = which(tool) is not None
        if found:
            detail = "found"
        elif tool == "claude" and not claude_needed_here:
            detail = f"missing (not needed here: claude runs as {s.agent_user})"
        else:
            detail = "missing" + ("" if required else " (needed only for the merge lane)")
        out.append(Check(f"tool {tool}", found or not required, detail))
    if claude_needed_here:
        ok, detail = claude_floor.machine_check(probe=claude_probe)
    else:
        ok, detail = True, f"not needed here: claude runs as {s.agent_user} (its floor is checked below)"
    out.append(Check("claude meets the version floor", ok, detail))
    out.extend(state_path_checks(s))
    # with an agent account the Claude token lives in ITS home and this account must not (and cannot) read it
    for label, path in (("app key", str(s.key_path)),) + (() if s.agent_user else (("claude oauth file", s.oauth_file),)):
        ok, why = _mode_ok(path)
        out.append(Check(f"{label} file", ok, why))
    if not s.agent_user:
        out.append(token_shape(s.oauth_file))
        out.append(Check("agent account configured (APX_AGENT_USER)", True, "none: agent runs stay blocked (backlog S1b)"))
    if s.ci_user:
        from .runas import Launcher

        ci_launcher = launcher or Launcher(s.ci_user)
        out.extend(sandbox_checks(s, ci_launcher))
        out.extend(repo_tool_checks(s, ci_launcher))
    else:
        out.append(
            Check("sandbox account configured (APX_CI_USER)", False, "PR code still runs as the account that holds the secrets")
        )
    if s.agent_user:
        from .runas import Launcher as _L

        out.extend(agent_checks(s, agent_launcher or _L(s.agent_user)))
    out.append(spend_ceiling_check(s.db_path))
    out.append(sprint_check(s.db_path))
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
    discovered: dict[str, int] = {}
    try:
        held = enroll.held_by_policy() if s.discovery else None
    except enroll.ERRORS:
        held = None  # unreadable policy: no repo counts as discoverable, extras stay out of scope
    for repo in sorted(s.installations):
        try:
            repos = cache.api_for(repo)("GET", "/installation/repositories?per_page=100")["repositories"]  # type: ignore[index]
            names = {r["full_name"] for r in repos}
            extra = names - ALLOWED_REPOS - set(s.installations)
            if held is not None:  # with discovery on, the owner's unheld repos are discovered (enroll.py), not out of scope
                for r in sorted(extra):
                    if enroll.why_not(r, s.owner, held) is None:
                        discovered[r] = s.installations[repo]
                extra -= set(discovered)
            out.append(
                Check(
                    f"installation for {repo}",
                    repo in names and not extra,
                    f"covers {sorted(names)}" + (f"; OUT OF SCOPE: {sorted(extra)}" if extra else ""),
                )
            )
        except Exception as e:  # noqa: BLE001
            out.append(Check(f"installation for {repo}", False, f"{type(e).__name__}"))
    if s.discovery:
        found = {r: enroll.Found(r, i, "shadow", "discovered; checks only") for r, i in discovered.items()}
        cache.installations = {**s.installations, **discovered}
        try:
            if s.ci_user:
                from .runas import Launcher as _CI

                ci = launcher or _CI(s.ci_user)
                tools = lambda r, p: [f"{c.name}: {c.detail}" for c in tool_checks_for(s, ci, r, p) if not c.ok]  # noqa: E731
            found, _ = enroll.promote(s, found, cache.api_for, tools if s.ci_user else None)
        except Exception as e:  # noqa: BLE001 - report, never crash the doctor
            found = {r: enroll.Found(r, i, "shadow", f"could not check promotion ({type(e).__name__})") for r, i in discovered.items()}
        name = "discovered repos (App installed, not in APX_INSTALLATIONS)"
        out.append(Check(name, True, "; ".join(discovered_lines(found)) or "none"))
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
