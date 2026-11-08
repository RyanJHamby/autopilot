"""`ap standard converge`: audit every repo the owner has on GitHub and report the ones that miss the standard."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import date
from pathlib import Path

from autopilot.converge import core


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


def cmd_converge(ns: argparse.Namespace, *, repo_name, load_portfolio, run=subprocess.run, today: date | None = None) -> int:
    portfolio = load_portfolio()
    owner = ns.owner or portfolio["owner"]
    today = today or date.today()
    try:
        listed = core.list_repos(owner, run=run)
    except core.ListError as e:
        print(f"ERROR cannot list {owner}'s repos: {e}")
        return 1

    skipped: list[tuple[str, str]] = []
    audits: list[core.Audit] = []
    errors: list[str] = []
    for r in sorted(listed, key=lambda x: x.name):
        why = core.gate(r, owner, portfolio)
        if why:
            skipped.append((r.name, why))
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

    if ns.json:
        print(
            json.dumps(
                {
                    "owner": owner,
                    "audits": [a.__dict__ for a in order(audits)],
                    "skipped": [{"repo": n, "why": w} for n, w in skipped],
                    "errors": errors,
                },
                indent=2,
            )
        )
    else:
        print(render(audits, skipped, errors))
    return 1 if errors else 0
