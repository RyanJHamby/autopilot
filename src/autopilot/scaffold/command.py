"""`ap standard fix`: show, or with --apply write, the standard files a repo is missing. Never commits or pushes."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from autopilot.scaffold import core
from autopilot.standard import command as check_command
from autopilot.standard import engine

BRANCH = "standard/scaffold"
MARK = {"create": "create", "exists": "exists", "skip": "skip", "blocked": "BLOCKED"}


def targets(ns, portfolio: dict, repo_name) -> list[tuple[str, Path | None]]:
    """Same resolution as `ap standard check`: explicit paths, plus enabled portfolio repos found by origin name."""
    out: list[tuple[str, Path | None]] = [(Path(r).expanduser().name, Path(r).expanduser().resolve()) for r in ns.repos]
    if ns.portfolio:
        root = Path(ns.root).expanduser()
        for name, entry in (portfolio.get("repos") or {}).items():
            if entry.get("enabled"):
                out.append((name, check_command.find_clone(name, root, repo_name)))
    return out


def context(path: Path, portfolio: dict, repo_name, gh, ns) -> core.Ctx:
    name = repo_name(path)
    entry = (portfolio.get("repos") or {}).get(name)
    owner = portfolio["owner"]
    slug = f"{owner}/{name}" if entry is not None else None
    asked = engine.github_public(slug, gh)
    repo = engine.Repo(path, entry=entry, slug=slug, gh=gh, github_public=asked)
    return core.read_ctx(
        path,
        name,
        owner,
        repo.public,
        holder=ns.holder or (entry or {}).get("holder") or portfolio.get("holder"),
        kind=ns.kind or (entry or {}).get("kind"),
        restricted=(entry or {}).get("data_class") == "restricted",
        visibility=visibility(repo.public, asked, entry),
    )


def visibility(public: bool | None, asked: bool | None, entry: dict | None) -> str:
    """Say where the public/private answer came from. A repo's files depend on it, so it is never left implicit."""
    word = {True: "public", False: "private", None: "unknown"}[public]
    if asked is not None:
        said = f"{word} per GitHub"
        if entry is not None and bool(entry.get("public", False)) != asked:
            said += " (portfolio disagrees; GitHub used)"
        return said
    if entry is not None:
        return f"{word} per portfolio (GitHub not asked or unreachable)"
    return "unknown (not in the portfolio and GitHub not asked or unreachable)"


def git(path: Path, *args: str, run=subprocess.run) -> subprocess.CompletedProcess:
    return run(["git", "-C", str(path), *args], capture_output=True, text=True)


def render(
    name: str, path: Path, actions: list[core.Action], why: str | None, visibility: str = "", layout: list[str] | None = None
) -> str:
    lines = [f"== {name}  ({path})" + (f"  [{visibility}]" if visibility else "")]
    if why:
        lines.append(f"  REFUSED  {why}")
    for a in actions:
        rule = f"[{a.rule}]" if a.rule else "[convention]"
        lines.append(f"  {MARK[a.status]:8} {a.path}  {rule}  {a.note}")
    for note in layout or []:
        lines.append(f"  layout   {note}  (advisory; nothing is moved)")
    counts = {k: sum(a.status == k for a in actions) for k in MARK}
    lines.append("  " + ", ".join(f"{n} {k}" for k, n in counts.items() if n))
    return "\n".join(lines)


def apply_one(path: Path, actions: list[core.Action], run=subprocess.run) -> tuple[list[str], str | None]:
    """Write on a fresh branch in a clean tree. Returns (files written, error). Nothing is committed."""
    if not any(a.status == "create" for a in actions):
        return [], None
    if not (path / ".git").exists():
        return [], "not a git checkout"
    dirty = git(path, "status", "--porcelain", run=run)
    if dirty.returncode != 0:
        return [], f"git status failed: {dirty.stderr.strip()}"
    if dirty.stdout.strip():
        return [], "working tree is not clean: commit or stash first, so the scaffold is its own reviewable diff"
    made = git(path, "checkout", "-b", BRANCH, run=run)
    if made.returncode != 0:
        return [], f"could not create branch {BRANCH}: {made.stderr.strip()}"
    return core.write(path, actions), None


def cmd_fix(ns: argparse.Namespace, *, repo_name, load_portfolio, run=subprocess.run, gh=None) -> int:
    portfolio = load_portfolio()
    gh = gh or (check_command.offline_gh if ns.offline else subprocess.run)
    todo = targets(ns, portfolio, repo_name)
    if not todo:
        print("nothing to do: give a repo path, or --portfolio")
        return 2

    code, report, errors = 0, [], []
    for label, path in todo:
        if path is None or not path.is_dir():
            errors.append(f"no clone of {label} under {ns.root} (matched by origin remote name)")
            code = 1
            continue
        ctx = context(path, portfolio, repo_name, gh, ns)
        actions = core.plan(path, ctx)
        why = core.refusal(ctx)
        written: list[str] = []
        if ns.apply and not why:
            written, err = apply_one(path, actions, run=run)
            if err:
                errors.append(f"{ctx.name}: {err}")
                code = 1
        report.append((ctx.name, path, actions, why, written, ctx.visibility, core.layout_notes(path, ctx)))

    if ns.json:
        out = {
            "applied": bool(ns.apply),
            "repos": [
                {
                    "repo": n,
                    "path": str(p),
                    "visibility": vis,
                    "refused": why,
                    "written": w,
                    "layout": lay,
                    "actions": [{"path": a.path, "status": a.status, "rule": a.rule, "note": a.note} for a in acts],
                }
                for n, p, acts, why, w, vis, lay in report
            ],
            "errors": errors,
        }
        print(json.dumps(out, indent=2))
    else:
        for n, p, acts, why, w, vis, lay in report:
            print(render(n, p, acts, why, vis, lay))
            if w:
                print(f"  wrote {len(w)} file(s) on branch {BRANCH}; review with `git diff`, then commit yourself")
        for e in errors:
            print(f"ERROR {e}")
        if not ns.apply and any(a.status == "create" for _, _, acts, *_ in report for a in acts):
            print("dry run: nothing was written. Re-run with --apply to write on a new branch.")
    return code
