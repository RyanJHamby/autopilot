"""Per-repo toolchains for the apx sandbox: which Node (or other tool) a repo's CI runs with.

One host runs repos that need different versions (stencil: Node 20, autopilot: Node 22), so a single PATH cannot serve both. The
declaration is DATA in repo_toolchains.json (repo -> ["node@20"]). It lives next to repo_ci.json, not in a repo's own
.autopilot/repo.yaml, for three reasons: it is merged by the owner here and never read from a PR; the host preflight can check it
without the network; and the directory is derived from the entry, never taken from it, so the data cannot name an arbitrary path.

`node@20` means the directory <root>/node-20/bin, where <root> is <shared dir>/toolchains. The owner installs it there (root-owned,
so the sandbox account can read and run it but never write it; docs/apx-linux-host.md, step 5). The sandbox job's PATH gets that
directory first, for that repo's jobs only (sandbox.run_in_sandbox). The version is a prefix by whole segment: `node@20` accepts
20.x.y, `node@20.18.1` accepts exactly that.

    python3 -m autopilot.apx.toolchains check OWNER/REPO[=ID],OWNER/REPO [--root DIR]   (used by the host preflight scripts)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

DECLARED_FILE = Path(__file__).with_name("repo_toolchains.json")
ENTRY = re.compile(r"^([a-z][a-z0-9_-]*)@([0-9]+(?:\.[0-9]+){0,2})$")  # tool@MAJOR[.MINOR[.PATCH]]


def parse_entry(entry: str) -> tuple[str, str]:
    m = ENTRY.match(entry) if isinstance(entry, str) else None
    if not m:
        raise ValueError(f"bad toolchain entry {entry!r}: use tool@VERSION, such as node@20")
    return m.group(1), m.group(2)


def dir_name(entry: str) -> str:
    tool, version = parse_entry(entry)
    return f"{tool}-{version}"


def load_declared(path: Path | None = None) -> dict[str, tuple[str, ...]]:
    raw = json.loads(Path(path or DECLARED_FILE).read_text())
    out: dict[str, tuple[str, ...]] = {}
    for repo, entries in raw.items():
        if not isinstance(entries, list):
            raise ValueError(f"{repo}: toolchains must be a list")
        tools = [parse_entry(e)[0] for e in entries]
        dup = {t for t in tools if tools.count(t) > 1}
        if dup:
            raise ValueError(f"{repo}: more than one version of {sorted(dup)} (one PATH entry per tool)")
        out[repo] = tuple(entries)
    return out


def bin_dirs(repo: str, root: Path | str, declared: dict | None = None) -> list[str]:
    """The bin directories to put first on this repo's sandbox PATH; [] when the repo declares none (the default PATH, as before)."""
    d = load_declared() if declared is None else declared
    return [str(Path(root) / dir_name(e) / "bin") for e in d.get(repo, ())]


def _matches(have: str, want: str) -> bool:
    h, w = have.split("."), want.split(".")
    return h[: len(w)] == w


def _check_one(repo: str, entry: str, root: Path) -> tuple[str, bool]:
    tool, want = parse_entry(entry)
    b = Path(root) / dir_name(entry) / "bin"
    if not b.is_dir():
        return f"FAIL  {entry} for {repo} CI: {b} is missing (docs/apx-linux-host.md, step 5)", False
    exe = b / tool
    if not (exe.is_file() and os.access(exe, os.X_OK)):
        return f"FAIL  {entry} for {repo} CI: {exe} is missing or not executable", False
    loose = [str(p) for p in (b, exe) if stat.S_IMODE(os.stat(p).st_mode) & 0o022]
    if loose:
        return f"FAIL  {entry} for {repo} CI: {', '.join(loose)} is group- or world-writable; the sandbox account could replace it", False
    try:
        p = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=10, env={"PATH": str(b)})
    except (OSError, subprocess.SubprocessError):
        return f"FAIL  {entry} for {repo} CI: {exe} --version did not run", False
    m = re.search(r"\d+(?:\.\d+)+", p.stdout + p.stderr)
    have = m.group(0) if m else None
    if have is None or not _matches(have, want):
        return f"FAIL  {entry} for {repo} CI: {exe} reports {have or 'no version'}, expected {want}", False
    return f"PASS  {tool} {have} at {b} for {repo} CI (declared {entry})", True


def check_repos(repos: list[str], root: Path | str, declared: dict | None = None) -> tuple[list[str], bool]:
    """(PASS/FAIL lines, all ok) for the toolchains the given repos declare. A repo that declares none checks nothing."""
    d = load_declared() if declared is None else declared
    lines, ok, seen = [], True, set()
    for repo in repos:
        if repo in seen:
            continue
        seen.add(repo)
        for entry in d.get(repo, ()):
            line, good = _check_one(repo, entry, Path(root))
            lines.append(line)
            ok = ok and good
    return lines, ok


def parse_repos(value: str) -> list[str]:
    """Accepts the APX_INSTALLATIONS form (OWNER/REPO=ID,...) and the APX_PRIVATE_CI form (OWNER/REPO,...)."""
    return [p.split("=", 1)[0].strip() for p in (value or "").split(",") if p.split("=", 1)[0].strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("repos", help="comma-separated; APX_INSTALLATIONS and APX_PRIVATE_CI values both work")
    c.add_argument("--root", required=True, help="the toolchains directory, <shared dir>/toolchains")
    ns = ap.parse_args(argv)
    lines, ok = check_repos(parse_repos(ns.repos), ns.root)
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
