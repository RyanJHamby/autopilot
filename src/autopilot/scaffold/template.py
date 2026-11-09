"""`ap standard template OUT_DIR`: render the generic hygiene layer into a directory, to publish as a GitHub template repo.

A template cannot fill in per-repo values (package name, kind, CI), so it carries only what every repo needs. The files come from
`core.plan` for a synthetic context, never from a second copy, so the template cannot drift from `ap standard fix`. Nothing here
creates or pushes a repo: that stays an owner step."""

from __future__ import annotations

import argparse
from pathlib import Path

from autopilot.scaffold import core
from autopilot.scaffold import templates as t

NAME = "repo-template"
README = "README.md"


def synthetic_ctx(owner: str, holder: str | None) -> core.Ctx:
    """A public, kind-less 'notes' repo that has workflows: the case where only the generic files apply."""
    return core.Ctx(name=NAME, owner=owner, public=True, holder=holder, kind="notes", has_workflows=True, visibility="template")


def render(out: Path, owner: str, holder: str | None) -> tuple[list[str], list[core.Action]]:
    """Write the template into `out`, which must be empty or absent. Returns (paths written, the plan it followed)."""
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError(f"{out} exists and is not empty; a template is rendered into a fresh directory")
    out.mkdir(parents=True, exist_ok=True)
    ctx = synthetic_ctx(owner, holder)
    actions = core.plan(out, ctx)
    blocked = [a for a in actions if a.status == "blocked"]
    if blocked:
        raise ValueError("; ".join(f"{a.path}: {a.note}" for a in blocked))
    written = core.write(out, actions)
    (out / README).write_text(t.template_readme(), encoding="utf-8")
    return sorted([*written, README]), actions


def cmd_template(ns: argparse.Namespace, *, load_portfolio) -> int:
    portfolio = load_portfolio()
    owner = ns.owner or portfolio["owner"]
    holder = ns.holder or portfolio.get("holder")
    try:
        written, _ = render(Path(ns.out_dir).expanduser(), owner, holder)
    except ValueError as e:
        print(f"ERROR {e}")
        return 1
    for p in written:
        print(f"  wrote {p}")
    print(
        f"{len(written)} file(s) in {ns.out_dir}. Nothing was committed or pushed; see docs/standard-template.md for the owner steps."
    )
    return 0
