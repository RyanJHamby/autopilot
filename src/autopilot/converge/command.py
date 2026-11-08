"""`ap standard converge`: audit every repo the owner has on GitHub and report the ones that miss the standard."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import date
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


def in_scope(r: core.Listed, portfolio: dict, today: date) -> bool:
    """Repos the job audits by default: anything in the portfolio, and anything created recently."""
    return r.name in (portfolio.get("repos") or {}) or core.is_new(r.created_at, today)


def cmd_converge(ns: argparse.Namespace, *, repo_name, load_portfolio, run=subprocess.run, today: date | None = None) -> int:
    portfolio = load_portfolio()
    owner = ns.owner or portfolio["owner"]
    today = today or date.today()
    try:
        listed = core.list_repos(owner, run=run)
    except core.ListError as e:
        print(f"ERROR cannot list {owner}'s repos: {e}")
        return 1

    show_all = bool(getattr(ns, "all", False))
    skipped: list[tuple[str, str]] = []
    audits: list[core.Audit] = []
    errors: list[str] = []
    outside = 0
    for r in sorted(listed, key=lambda x: x.name):
        why = core.gate(r, owner, portfolio)
        if why:
            skipped.append((r.name, why))
            continue
        if not show_all and not in_scope(r, portfolio, today):
            outside += 1  # never cloned or read: an old repo nobody asked this job to look at
            continue
        path, tmp, err = core.checkout(r.name, owner, Path(ns.root).expanduser(), repo_name, run=run)
        if path is None:
            errors.append(f"{r.name}: could not get a checkout ({err})")
            continue
        try:
            a = core.audit(r, path, owner, portfolio, today)
            if tmp is not None:
                a.note = "audited from a shallow clone"
            audits.append(a)
        finally:
            if tmp is not None:
                tmp.cleanup()

    ops = [issues.plan(a, owner, run) for a in order(audits) if a.in_portfolio or a.new]
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
        if outside:
            print(f"{outside} older repo(s) outside the portfolio were not audited; pass --all to include them")
        if not getattr(ns, "apply", False) and any(o.kind in ("create", "update", "close") for o in ops):
            print("dry run: no issue was filed. Re-run with --apply to file them.")
    return 1 if errors else 0
