"""`ap standard check`: run the standard against repos, one path or the whole enabled portfolio."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import date
from pathlib import Path

from autopilot.standard import engine, waivers

MARK = {"pass": "ok", "fail": "FAIL", "unknown": "?", "skip": "skip", "waived": "waived"}


def offline_gh(cmd, **kw):
    """Stands in for gh with --offline: every question comes back unanswerable, so the result is `unknown`."""
    return subprocess.CompletedProcess(cmd, 1, "", "offline")


DEFAULT_ROOTS = ("~/dev", "~/Documents")  # where this owner keeps clones; repos live in both


def roots_of(root) -> list[Path]:
    """`--root` as a list of directories: None means the defaults, a single path or string is one root."""
    items = DEFAULT_ROOTS if root is None else [root] if isinstance(root, (str, Path)) else list(root)
    return [Path(r).expanduser() for r in items]


def find_clones(name: str, root, repo_name) -> list[Path]:
    """Every checkout of GitHub repo `name` under the roots. Matched by origin remote, not directory name: ~/dev/drillpad is the
    clone of drillpad-workspace. A directory reached by two paths counts once."""
    seen, out = set(), []
    for r in roots_of(root):
        for d in sorted(p for p in r.iterdir() if (p / ".git").exists()) if r.is_dir() else []:
            key = d.resolve()
            if key not in seen and repo_name(d) == name:
                seen.add(key)
                out.append(d)
    return out


def _git(d: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(["git", "-C", str(d), *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def _head_time(d: Path) -> int:
    rc, out = _git(d, "log", "-1", "--format=%ct")
    return int(out) if rc == 0 and out.isdigit() else 0


def describe_clone(d: Path) -> dict:
    """Branch, dirty, and how far behind origin, from local git only. Behind is as of the last fetch, so it also says how long ago that
    was: a clone that was never fetched cannot know it is behind, and must not read as current."""
    rc, branch = _git(d, "rev-parse", "--abbrev-ref", "HEAD")
    _, changed = _git(d, "status", "--porcelain", "--untracked-files=no")
    behind = ahead = None
    rc_ref, ref = _git(d, "symbolic-ref", "-q", "refs/remotes/origin/HEAD")
    if rc_ref == 0 and ref:
        rb, b = _git(d, "rev-list", "--count", f"HEAD..{ref}")
        ra, a = _git(d, "rev-list", "--count", f"{ref}..HEAD")
        if rb == 0 and ra == 0 and b.isdigit() and a.isdigit():
            behind, ahead = int(b), int(a)
    _, common = _git(d, "rev-parse", "--git-common-dir")  # a worktree keeps FETCH_HEAD in the main repo's git dir
    fetch_head = (d / common) / "FETCH_HEAD" if common else None
    days = (time.time() - fetch_head.stat().st_mtime) / 86400 if fetch_head and fetch_head.exists() else None
    return {"branch": branch if rc == 0 else "?", "dirty": bool(changed), "behind": behind, "ahead": ahead, "fetched_days": days}


def describe_text(info: dict) -> str:
    parts = [f"branch {info['branch']}", "dirty" if info["dirty"] else "clean"]
    if info["behind"] is None:
        parts.append("no origin ref to compare")
    else:
        count = f"behind {info['behind']}" + (f", ahead {info['ahead']}" if info["ahead"] else "")
        days = info["fetched_days"]
        parts.append(f"{count} (never fetched)" if days is None else f"{count} (last fetched {'today' if days < 1 else f'{days:.0f}d ago'})")
    return ", ".join(parts)


def pick_clone(name: str, candidates: list[Path]) -> tuple[Path | None, str]:
    """The clone to audit and a note when there was a choice. A real checkout (one with a `.git` directory) beats a task worktree,
    however new the worktree's commit, because a worktree is a branch someone is working on, not the repo. Among those the newest HEAD
    commit wins (the live checkout beats a stale copy) and the first by name breaks a tie, so the choice is deterministic."""
    if not candidates:
        return None, ""
    real = [d for d in candidates if (d / ".git").is_dir()] or candidates
    best = max(real, key=_head_time)  # max keeps the first of equals, which is name order
    if len(candidates) == 1:
        return best, ""
    rest = [d for d in candidates if d != best]
    shown = ", ".join(f"{d} ({describe_text(describe_clone(d))})" for d in rest[:3])
    more = f", and {len(rest) - 3} more" if len(rest) > 3 else ""
    return best, f"{len(candidates)} clones of {name}: auditing {best} (newest real checkout); also {shown}{more}"


def find_clone(name: str, root, repo_name) -> Path | None:
    return pick_clone(name, find_clones(name, root, repo_name))[0]


def check_one(
    path: Path, portfolio: dict, repo_name, gh, wvs: list[dict], today: date
) -> tuple[str, list[engine.Result], list[str]]:
    """Check one repo. GitHub's answer about public/private wins over the portfolio's flag, and a disagreement is a note."""
    name = repo_name(path)
    entry = (portfolio.get("repos") or {}).get(name)
    slug = f"{portfolio['owner']}/{name}" if entry is not None else None
    notes = []
    public = engine.github_public(slug, gh)
    if public is not None and entry is not None and public != bool(entry.get("public", False)):
        notes.append(
            f"{name}: GitHub says {'public' if public else 'private'} but policy/portfolio.yaml says "
            f"{'public' if entry.get('public', False) else 'not public'}; GitHub's answer was used"
        )
    results = engine.run(engine.Repo(path, entry=entry, slug=slug, gh=gh, github_public=public))
    waivers.apply(results, name, wvs, today)
    return name, results, notes


def render(name: str, path: Path, results: list[engine.Result], info: str = "") -> str:
    lines = [f"== {name}  ({path})" + (f"  [{info}]" if info else "")]
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
    clone_notes: list[str] = []
    if ns.portfolio:
        for name, entry in (portfolio.get("repos") or {}).items():
            if entry.get("enabled"):
                path, why = pick_clone(name, find_clones(name, ns.root, repo_name))
                clone_notes += [why] if why else []
                targets.append((name, path))
    if not targets:
        print("nothing to check: give a repo path, or --portfolio")
        return 2

    code, report, errors = 0, [], []
    for label, path in targets:
        if path is None or not path.is_dir():
            searched = ", ".join(str(r) for r in roots_of(ns.root))
            errors.append(f"no clone of {label} under {searched} (matched by origin remote name)")
            code = 1
            continue
        name, results, repo_notes = check_one(path, portfolio, repo_name, gh, wvs, today)
        info = describe_clone(path)
        if info["behind"]:
            repo_notes.append(f"{name}: the clone at {path} is {info['behind']} commit(s) behind origin as of its last fetch; pull before trusting this")
        notes += repo_notes
        code = max(code, engine.exit_code(results, strict=ns.strict))
        report.append((name, path, results, info))
    notes += clone_notes

    if ns.json:
        out = {"repos": [engine.to_json(n, r) | {"path": str(p), "clone": i} for n, p, r, i in report], "errors": errors, "notes": notes}
        print(json.dumps(out, indent=2))
    else:
        for n, p, r, i in report:
            print(render(n, p, r, describe_text(i)))
        for e in errors:
            print(f"ERROR {e}")
        for n in notes:
            print(f"NOTE {n}")
    return code
