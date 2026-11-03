"""`ap standard check`: run the standard against repos, one path or the whole enabled portfolio."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import date
from pathlib import Path

from autopilot.standard import engine, waivers

MARK = {"pass": "ok", "fail": "FAIL", "unknown": "?", "skip": "skip", "waived": "waived"}


def offline_gh(cmd, **kw):
    """Stands in for gh with --offline: every question comes back unanswerable, so the result is `unknown`."""
    return subprocess.CompletedProcess(cmd, 1, "", "offline")


def find_clone(name: str, root: Path, repo_name) -> Path | None:
    """The checkout of GitHub repo `name` under `root`. Matched by origin remote, not directory name: ~/dev/drillpad is
    the clone of drillpad-workspace."""
    for d in sorted(p for p in root.iterdir() if (p / ".git").exists()) if root.is_dir() else []:
        if repo_name(d) == name:
            return d
    return None


def check_one(path: Path, portfolio: dict, repo_name, gh, wvs: list[dict], today: date) -> tuple[str, list[engine.Result]]:
    name = repo_name(path)
    entry = (portfolio.get("repos") or {}).get(name)
    slug = f"{portfolio['owner']}/{name}" if entry is not None else None
    results = engine.run(engine.Repo(path, entry=entry, slug=slug, gh=gh))
    waivers.apply(results, name, wvs, today)
    return name, results


def render(name: str, path: Path, results: list[engine.Result]) -> str:
    lines = [f"== {name}  ({path})"]
    for r in results:
        tag = f"{r.label}, {r.level}-level"
        head = f"  {MARK[r.result]:7} {r.id}  [{tag}]"
        lines.append(f"{head}  {r.findings[0]}" if r.findings else head)
        lines += [f"  {'':7} {'':{len(r.id)}}  {f}" for f in r.findings[1:]]
    counts = {k: sum(r.result == k for r in results) for k in MARK}
    lines.append("  " + ", ".join(f"{n} {k}" for k, n in counts.items() if n))
    return "\n".join(lines)


def cmd_standard(ns: argparse.Namespace, *, repo_name, load_portfolio, policy_root: Path) -> int:
    portfolio = load_portfolio()
    today = date.today()
    text, note = waivers.read_base(policy_root)
    wvs, notes = waivers.parse(text)
    notes = ([note] if note else []) + notes
    gh = offline_gh if ns.offline else subprocess.run

    targets: list[tuple[str, Path | None]] = [(Path(r).expanduser().name, Path(r).expanduser().resolve()) for r in ns.repos]
    if ns.portfolio:
        root = Path(ns.root).expanduser()
        for name, entry in (portfolio.get("repos") or {}).items():
            if entry.get("enabled"):
                targets.append((name, find_clone(name, root, repo_name)))
    if not targets:
        print("nothing to check: give a repo path, or --portfolio")
        return 2

    code, report, errors = 0, [], []
    for label, path in targets:
        if path is None or not path.is_dir():
            errors.append(f"no clone of {label} under {ns.root} (matched by origin remote name)")
            code = 1
            continue
        name, results = check_one(path, portfolio, repo_name, gh, wvs, today)
        code = max(code, engine.exit_code(results, strict=ns.strict))
        report.append((name, path, results))

    if ns.json:
        out = {"repos": [engine.to_json(n, r) | {"path": str(p)} for n, p, r in report], "errors": errors, "notes": notes}
        print(json.dumps(out, indent=2))
    else:
        for n, p, r in report:
            print(render(n, p, r))
        for e in errors:
            print(f"ERROR {e}")
        for n in notes:
            print(f"NOTE {n}")
    return code
