"""Build/test lane: run a repo's declared check commands against a PR checkout and summarise for a check run.

The commands come from the BASE branch's .autopilot/repo.yaml (`commands:`), never from the PR, so a PR cannot swap in
its own. They run WITHOUT a shell (argv split) in a scrubbed environment: no GitHub token, no OAuth token, no cloud
creds. Real isolation (separate OS user, rootless container, egress firewall) is the host's job, see docs/fabric.md; this
module only guarantees what it controls: no shell, no secrets in env, wall-clock limit, bounded output.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

SAFE_CMD = re.compile(r"^[A-Za-z0-9._:/@=+ -]+$")
ENV_ALLOW = ("PATH", "LANG", "LC_ALL", "TERM", "TMPDIR", "CI")
TAIL = 4000  # chars of output kept per command


@dataclass
class CmdResult:
    cmd: str
    ok: bool
    seconds: float
    output: str
    note: str = ""


def parse_ci_steps(cfg: dict) -> list[tuple[str, str]]:
    """The repo's CI, from the `ci:` list in .autopilot/repo.yaml (BASE branch only). NOT `commands:`, which is the agent's
    tool allowlist (prefixes like `uv run`), not runnable checks. Each entry is a command string, or {run, dir} to run in a
    subdirectory. Returns [(command, relative_dir)]. Anything unsafe raises; an absent list means nothing is checked."""
    steps: list[tuple[str, str]] = []
    for item in cfg.get("ci") or []:
        run, sub = (item, "") if isinstance(item, str) else (item.get("run", ""), item.get("dir", "") or "")
        run = str(run).strip()
        if not run or not SAFE_CMD.match(run):
            raise ValueError(f"ci step {run!r} is empty or has characters that are not allowed")
        parts = Path(sub).parts
        if Path(sub).is_absolute() or ".." in parts or not re.fullmatch(r"[A-Za-z0-9._/-]*", sub):
            raise ValueError(f"ci step dir {sub!r} must be a plain relative path inside the checkout")
        steps.append((run, sub))
    return steps


def parse_commands(cfg: dict) -> list[str]:
    cmds = []
    for c in cfg.get("commands") or []:
        c = str(c).strip()
        if not SAFE_CMD.match(c):
            raise ValueError(f"command {c!r} has characters that are not allowed")
        cmds.append(c)
    return cmds


def ci_env(home: Path, source: dict | None = None) -> dict:
    src = os.environ if source is None else source
    env = {k: src[k] for k in ENV_ALLOW if k in src}
    env.update({"HOME": str(home), "CI": "true"})
    return env


SAFE_LINK = re.compile(r"^\.[A-Za-z0-9_-]+$")  # a single dot-directory name such as .cargo, never a path


def link_toolchains(home: Path, real_home: Path, names: list[str]) -> list[str]:
    """CI runs with a fresh, empty HOME so a PR's tests cannot see ~/.ssh or any credentials. Some repos look for their
    compilers under $HOME (drillpad-workspace finds rustc in $HOME/.cargo/bin), so the named toolchain directories are
    symlinked into that scratch home. Only plain dot-directory names are accepted, and the owner chooses them."""
    linked = []
    for n in names:
        if not SAFE_LINK.match(n):
            raise ValueError(f"toolchain link {n!r} must be a single dot-directory name like .cargo")
        src = real_home / n
        if src.is_dir() and not (home / n).exists():
            (home / n).symlink_to(src)
            linked.append(n)
    return linked


def run_commands(
    checkout: Path,
    commands: list,
    *,
    home: Path,
    timeout_each: int = 1800,
    source_env: dict | None = None,
    toolchain_links: list[str] | None = None,
    real_home: Path | None = None,
) -> list[CmdResult]:
    """Run each command in order; stop at the first failure (later commands often depend on earlier ones)."""
    results: list[CmdResult] = []
    if toolchain_links:
        link_toolchains(home, real_home or Path.home(), toolchain_links)
    for item in commands:
        cmd, sub = (item, "") if isinstance(item, str) else item
        label = f"{sub}: {cmd}" if sub else cmd
        t0 = time.monotonic()
        try:
            p = subprocess.run(
                shlex.split(cmd),
                cwd=(checkout / sub) if sub else checkout,
                env=ci_env(home, source_env),
                capture_output=True,
                text=True,
                timeout=timeout_each,
            )
            out = (p.stdout + p.stderr)[-TAIL:]
            results.append(
                CmdResult(
                    label, p.returncode == 0, time.monotonic() - t0, out, "" if p.returncode == 0 else f"exit {p.returncode}"
                )
            )
        except subprocess.TimeoutExpired:
            results.append(CmdResult(label, False, time.monotonic() - t0, "", f"timed out after {timeout_each}s"))
        except FileNotFoundError:
            results.append(CmdResult(label, False, time.monotonic() - t0, "", "command not found"))
        if not results[-1].ok:
            break
    return results


def summarize(results: list[CmdResult], planned: list[str]) -> tuple[bool, str]:
    """(ok, markdown). An empty plan is NOT a pass: a lane that checked nothing must not look green."""
    if not planned:
        return False, "no `ci:` steps configured in .autopilot/repo.yaml; nothing was checked"
    lines = []
    for r in results:
        lines.append(f"- {'PASS' if r.ok else 'FAIL'} `{r.cmd}` ({r.seconds:.1f}s){' - ' + r.note if r.note else ''}")
    skipped = planned[len(results) :]
    lines += [
        f"- SKIPPED `{c if isinstance(c, str) else (c[1] + ': ' if c[1] else '') + c[0]}` (an earlier command failed)"
        for c in skipped
    ]
    ok = len(results) == len(planned) and all(r.ok for r in results)
    if not ok:
        bad = next((r for r in results if not r.ok), None)
        if bad and bad.output:
            lines += ["", "```", bad.output.strip(), "```"]
    return ok, "\n".join(lines)
