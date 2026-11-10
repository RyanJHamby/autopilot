"""`ap standard converge`: audit every repo the owner has on GitHub and report the ones that miss the standard."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import date, datetime
from pathlib import Path

from autopilot.converge import core, issues


def order(audits: list[core.Audit]) -> list[core.Audit]:
    """New repos first (that is the signal this job exists for), then by how badly they miss the standard."""
    return sorted(audits, key=lambda a: (not a.new, -a.fail_level, -len(a.gaps), a.name))


def render(audits: list[core.Audit], skipped: list[tuple[str, str]], errors: list[str]) -> str:
    lines = []
    bad = [a for a in order(audits) if a.gaps and not a.skipped]
    ok = [a for a in audits if not a.gaps and not a.skipped]
    for a in bad:
        flags = (
            ("  NEW" if a.new else "") + ("" if a.in_portfolio else "  not in portfolio") + (f"  [{a.note}]" if a.note else "")
        )
        vis = {True: "public", False: "private", None: "unknown"}[a.public]
        lines.append(f"{a.name}  ({vis}){flags}")
        lines.append(
            f"  {len(a.gaps)} gap(s), {a.fail_level} fail-level; `ap standard fix` would create {len(a.fixable)} file(s)"
        )
        lines += [f"  - {g}" for g in a.gaps]
    if ok:
        lines.append("conformant: " + ", ".join(sorted(a.name for a in ok)))
    inner = [(a.name, a.skipped) for a in audits if a.skipped]
    for name, why in sorted(skipped + inner):
        lines.append(f"skipped {name}: {why}")
    lines += [f"ERROR {e}" for e in errors]
    lines.append(f"{len(audits) - len(inner)} audited, {len(bad)} with gaps, {len(skipped) + len(inner)} skipped")
    return "\n".join(lines)


STATUS = Path.home() / ".autopilot" / "converge" / "last.json"


def write_status(path: Path, payload: dict) -> str:
    """Record how the last scheduled run went, so a silent failure is visible. A write failure is reported, never fatal."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"time": datetime.now().astimezone().isoformat(timespec="seconds"), **payload}, indent=2) + "\n"
        )
    except OSError as e:
        return f"could not write the status file {path}: {e}"
    return ""


def in_scope(r: core.Listed, portfolio: dict, today: date) -> bool:
    """Repos the job audits by default: anything in the portfolio, and anything created recently."""
    return r.name in (portfolio.get("repos") or {}) or core.is_new(r.created_at, today)


def cmd_converge(
    ns: argparse.Namespace,
    *,
    load_portfolio,
    run=subprocess.run,
    today: date | None = None,
    status_path: Path | None = None,
) -> int:
    status_path = status_path or STATUS  # resolved at call time so tests can redirect it
    portfolio = load_portfolio()
    owner = ns.owner or portfolio["owner"]
    today = today or date.today()
    try:
        listed = core.list_repos(owner, run=run)
    except core.ListError as e:
        print(f"ERROR cannot list {owner}'s repos: {e}")
        if getattr(ns, "apply", False):
            write_status(status_path, {"ok": False, "exit": 1, "errors": [f"cannot list repos: {e}"]})
        return 1

    show_all = bool(getattr(ns, "all", False))
    only = set(getattr(ns, "only", None) or [])
    skipped: list[tuple[str, str]] = []
    audits: list[core.Audit] = []
    errors: list[str] = []
    outside = 0
    for r in sorted(listed, key=lambda x: x.name):
        if only and r.name not in only:
            continue  # --only: nothing else is cloned, read or reported
        why = core.gate(r, owner, portfolio)
        if why:
            skipped.append((r.name, why))
            continue
        if not only and not show_all and not in_scope(r, portfolio, today):
            outside += 1  # never cloned or read: an old repo nobody asked this job to look at
            continue
        path, tmp, err = core.checkout(r.name, owner, run=run)
        if path is None:
            errors.append(f"{r.name}: could not get a checkout ({err})")
            continue
        try:
            a = core.audit(r, path, owner, portfolio, today)
            a.note = "audited from a shallow clone of GitHub's default branch"
            audits.append(a)
        finally:
            tmp.cleanup()

    for name in sorted(only - {r.name for r in listed}):
        errors.append(f"--only {name}: no such repo among {owner}'s repos on GitHub")
    ops = [issues.plan(a, owner, run) for a in order(audits) if a.in_portfolio or a.new]
    ineligible = [a.name for a in audits if not (a.in_portfolio or a.new)]
    failed = [o for o in ops if o.kind == "error"]
    if getattr(ns, "apply", False):
        for o in ops:
            err = issues.apply(o, owner, run)
            if err:
                errors.append(f"{o.repo}: issue {o.kind} failed ({err})")
    errors += [f"{o.repo}: {o.note}" for o in failed]

    if ns.json:
        print(
            json.dumps(
                {
                    "owner": owner,
                    "applied": bool(getattr(ns, "apply", False)),
                    "audits": [a.__dict__ for a in order(audits)],
                    "issues": [o.__dict__ for o in ops],
                    "skipped": [{"repo": n, "why": w} for n, w in skipped],
                    "outside_scope": outside,
                    "errors": errors,
                },
                indent=2,
            )
        )
    else:
        print(render(audits, skipped, errors))
        verb = "" if getattr(ns, "apply", False) else "would "
        for o in ops:
            if o.kind in ("create", "update", "close"):
                print(f"  {verb}{o.kind} issue on {o.repo}: {o.title or o.note}")
            elif o.kind == "disabled":
                print(f"  no issue on {o.repo}: {o.note}")
        for name in ineligible:
            print(f"  no issue on {name}: not in the portfolio and not new, so the job never files into it")
        if outside:
            print(f"{outside} older repo(s) outside the portfolio were not audited; pass --all to include them")
        if not getattr(ns, "apply", False) and any(o.kind in ("create", "update", "close") for o in ops):
            print("dry run: no issue was filed. Re-run with --apply to file them.")
    if getattr(ns, "apply", False):
        counts = {k: sum(o.kind == k for o in ops) for k in ("create", "update", "close", "unchanged", "disabled")}
        bad = write_status(
            status_path,
            {
                "ok": not errors,
                "exit": 1 if errors else 0,
                "audited": len(audits),
                "with_gaps": sum(bool(a.gaps) and not a.skipped for a in audits),
                "issues": counts,
                "errors": errors,
            },
        )
        if bad:
            print(f"WARNING {bad}")
    return 1 if errors else 0
