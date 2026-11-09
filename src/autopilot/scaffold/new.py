"""`ap new NAME --kind K`: a new local repo that starts on the standard. mkdir, `git init`, the files `ap standard fix` would write.

Local only. It makes no commit, creates nothing on GitHub and pushes nothing: those stay owner steps, printed at the end."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

from autopilot.scaffold import core
from autopilot.scaffold import templates as t
from autopilot.standard import engine

NEW_KINDS = ("library", "cli", "app", "notes")
NAME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def check_name(name: str, owner: str) -> str | None:
    if not NAME_OK.match(name) or name.endswith(".git"):
        return "a repo name is letters, digits, '.', '_' or '-', and starts with a letter or digit"
    if name.lower() == owner.lower():
        return "that is the profile repo's name; its README is the profile, not a project"
    return None


def create(
    root: Path, name: str, kind: str, owner: str, holder: str | None, public: bool, run=subprocess.run
) -> tuple[Path, list[str], list[core.Action]]:
    """Returns (path, files written, plan). Raises ValueError, and leaves nothing behind, if it cannot proceed."""
    why = check_name(name, owner)
    if why:
        raise ValueError(why)
    path = root / name
    if path.exists():
        raise ValueError(
            f"{path} already exists; `ap new` only makes a new directory (use `ap standard fix` on an existing repo)"
        )
    ctx = core.Ctx(name=name, owner=owner, public=public, holder=holder, kind=kind, empty=True, visibility="chosen with ap new")
    ctx.ecosystems = ["uv"] if kind in core.PACKAGE_KINDS else []
    actions = core.plan(path, ctx)  # path does not exist yet: plan only reads it
    blocked = [a for a in actions if a.status == "blocked"]
    if blocked:
        raise ValueError("; ".join(f"{a.path}: {a.note}" for a in blocked))
    path.mkdir(parents=True)
    try:
        made = run(["git", "-C", str(path), "init", "-q", "-b", "main"], capture_output=True, text=True)
        if made.returncode != 0:
            raise ValueError(f"git init failed: {made.stderr.strip()}")
        written = core.write(path, actions)
        if not (path / "README.md").exists():
            (path / "README.md").write_text(t.readme(name), encoding="utf-8")
            written.append("README.md")
    except BaseException:
        import shutil

        shutil.rmtree(path, ignore_errors=True)
        raise
    return path, sorted(written), actions


def next_steps(name: str, owner: str, public: bool) -> list[str]:
    vis = "--public" if public else "--private"
    return [
        f"cd {name} && pow init",
        "git add -A && git commit -S -m 'Start on the standard'   (signed, by you)",
        f"gh repo create {owner}/{name} {vis} --source . --push   (outward-facing: yours to run)",
        f"add {name} to policy/portfolio.yaml if autopilot should manage it, and set the ruleset",
    ]


def cmd_new(ns: argparse.Namespace, *, load_portfolio, run=subprocess.run) -> int:
    portfolio = load_portfolio()
    owner = ns.owner or portfolio["owner"]
    holder = ns.holder or portfolio.get("holder")
    try:
        path, written, _ = create(Path(ns.root).expanduser(), ns.name, ns.kind, owner, holder, bool(ns.public), run=run)
    except ValueError as e:
        print(f"ERROR {e}")
        return 1
    for p in written:
        print(f"  wrote {p}")
    results = engine.run(engine.Repo(path, github_public=bool(ns.public)))
    todo = [f"{r.id}: {'; '.join(r.findings)}" for r in results if r.result == "fail"]
    print(f"{path}: {len(written)} file(s), git initialised on main, nothing committed.")
    if todo:
        print("Still failing the standard (expected until the steps below):")
        for line in todo:
            print(f"  - {line}")
    print("Your steps (nothing outward-facing was done):")
    for i, s in enumerate(next_steps(ns.name, owner, bool(ns.public)), 1):
        print(f"  {i}. {s}")
    return 0
