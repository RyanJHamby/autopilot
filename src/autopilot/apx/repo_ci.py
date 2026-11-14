"""CI for the private repos apx can check while hosted GitHub Actions is off: admin, control, pawl, agent-kit.

The per-repo spec is DATA in repo_ci.json: repo -> the check contexts to post (exactly the names the repo's branch protection
requires, so no ruleset change is needed), the commands behind each context, and the tools the host must have. It lives here, not
in policy/portfolio.yaml, because agents may not edit that file; the owner can move it. Nothing is hardcoded per repo in code.

Commands come from this file (trusted, merged by the owner), never from the PR, and go through the same filter as repo.yaml `ci:`
steps (cilane.parse_ci_steps): no shell, plain characters only. A repo runs only when the owner lists it in APX_PRIVATE_CI.

    python3 -m autopilot.apx.repo_ci check-tools OWNER/REPO,OWNER/REPO [--path DIR]   (used by the host preflight scripts)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from . import cilane

SPEC_FILE = Path(__file__).with_name("repo_ci.json")
TOOL = re.compile(r"^[A-Za-z0-9._+-]+$")
CONTEXT = re.compile(r"^[A-Za-z0-9._()/ -]+$")


@dataclass(frozen=True)
class Check:
    context: str
    steps: tuple[tuple[str, str], ...]  # (command, relative dir)


@dataclass(frozen=True)
class RepoCi:
    checks: tuple[Check, ...]
    tools: tuple[str, ...]

    def contexts(self) -> list[str]:
        return [c.context for c in self.checks]

    def as_job(self) -> list[dict]:
        """The shape the executor and the sandbox job pass around (plain JSON)."""
        return [{"context": c.context, "steps": [list(s) for s in c.steps]} for c in self.checks]


def parse_spec(repo: str, raw: dict) -> RepoCi:
    tools = tuple(raw.get("tools") or ())
    if any(not isinstance(t, str) or not TOOL.match(t) for t in tools):
        raise ValueError(f"{repo}: tool names must be plain executable names")
    checks = []
    for c in raw.get("checks") or ():
        ctx = c.get("context", "")
        if not isinstance(ctx, str) or not ctx.strip() or not CONTEXT.match(ctx):
            raise ValueError(f"{repo}: bad check context {ctx!r}")
        steps = tuple(cilane.parse_ci_steps({"ci": c.get("steps") or []}))
        if not steps:
            raise ValueError(f"{repo}: check {ctx!r} has no steps; a check that runs nothing must not look green")
        checks.append(Check(ctx, steps))
    if not checks:
        raise ValueError(f"{repo}: no checks configured")
    if len({c.context for c in checks}) != len(checks):
        raise ValueError(f"{repo}: duplicate check context")
    return RepoCi(tuple(checks), tools)


def load_specs(path: Path = SPEC_FILE) -> dict[str, RepoCi]:
    raw = json.loads(Path(path).read_text())
    return {repo: parse_spec(repo, body) for repo, body in raw.items()}


def spec_for(repo: str) -> RepoCi | None:
    return load_specs().get(repo)


def parse_repos(value: str) -> list[str]:
    return [r.strip() for r in (value or "").split(",") if r.strip()]


def check_tools(repos: list[str], search_path: str, which=shutil.which) -> tuple[list[str], bool]:
    """(PASS/FAIL lines, all ok). A repo with no spec is a FAIL: naming it in APX_PRIVATE_CI could never have worked."""
    specs = load_specs()
    lines, ok = [], True
    for repo in repos:
        spec = specs.get(repo)
        if spec is None:
            lines.append(f"FAIL  {repo} is in APX_PRIVATE_CI but has no CI spec (known: {', '.join(sorted(specs))})")
            ok = False
            continue
        for tool in spec.tools:
            found = which(tool, path=search_path)
            if found:
                lines.append(f"PASS  {tool} found for {repo} CI")
            else:
                lines.append(f"FAIL  {tool} missing for {repo} CI (searched {search_path})")
                ok = False
    return lines, ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ct = sub.add_parser("check-tools")
    ct.add_argument("repos", help="comma-separated, the value of APX_PRIVATE_CI")
    ct.add_argument("--path", default=os.environ.get("PATH", ""), help="the PATH apx-ci will have")
    ns = ap.parse_args(argv)
    lines, ok = check_tools(parse_repos(ns.repos), ns.path)
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
