"""One `standard-gap` issue per non-conformant repo: filed once, edited in place on later runs, closed when the repo conforms.

Only `plan` decides; `apply` only executes what `plan` returned. A failed lookup is an error for that repo and files
nothing, so a flaky `gh` can never create duplicates."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from autopilot.converge.core import Audit

LABEL = "standard-gap"
LABEL_COLOR = "FBCA04"
PREFIX = "standard: "


@dataclass
class Op:
    kind: str  # create | update | close | unchanged | none | error
    repo: str
    number: int | None = None
    title: str = ""
    body: str = ""
    note: str = ""


def title(a: Audit) -> str:
    return f"{PREFIX}{len(a.gaps)} gap{'s' if len(a.gaps) != 1 else ''}"


def body(a: Audit, owner: str) -> str:
    lines = [
        "The project standard (`ap standard check`) found these gaps. Filed by `ap standard converge`; this issue is edited in",
        "place on every run and closes itself when the repo conforms. Nothing was pushed or changed in the repository.",
        "",
        "## Gaps",
        *[f"- {g}" for g in a.gaps],
        "",
    ]
    if a.fixable:
        lines += [
            "## What `ap standard fix` would add",
            *[f"- `{p}`" for p in a.fixable],
            "",
            f"Run `ap standard fix --apply` from a clean, freshly pulled clone of `{owner}/{a.name}`, review the diff, and open the PR yourself.",
        ]
    else:
        lines.append("`ap standard fix` has nothing to add here; these gaps need a human edit (see `ap standard check`).")
    return "\n".join(lines) + "\n"


def lookup(repo_slug: str, run: Callable = subprocess.run) -> tuple[dict | None, str]:
    """The open standard-gap issue, if any. (issue or None, error). A failed lookup is an error, never 'none found'."""
    cmd = [
        "gh",
        "issue",
        "list",
        "-R",
        repo_slug,
        "--label",
        LABEL,
        "--state",
        "open",
        "--json",
        "number,title,body",
        "--limit",
        "5",
    ]
    try:
        r = run(cmd, capture_output=True, text=True)
    except OSError as e:
        return None, f"gh could not run: {e}"
    if r.returncode != 0:
        return None, (r.stderr or "").strip() or "gh issue list failed"
    try:
        rows = json.loads(r.stdout or "[]")
    except json.JSONDecodeError:
        return None, "gh issue list returned something that is not JSON"
    return (rows[0] if rows else None), ""


def _norm(text: str | None) -> str:
    return (text or "").replace("\r\n", "\n").strip()


def plan(a: Audit, owner: str, run: Callable = subprocess.run) -> Op:
    slug = f"{owner}/{a.name}"
    existing, err = lookup(slug, run)
    if err:
        return Op("error", a.name, note=f"could not look up existing issues: {err}")
    if a.skipped:
        return Op("none", a.name, note=f"skipped: {a.skipped}")
    if not a.gaps:
        return Op("close", a.name, existing["number"], note="conforms now") if existing else Op("none", a.name, note="conforms")
    t, b = title(a), body(a, owner)
    if existing is None:
        return Op("create", a.name, None, t, b)
    if existing.get("title") == t and _norm(existing.get("body")) == _norm(b):
        return Op("unchanged", a.name, existing["number"], t, b)
    return Op("update", a.name, existing["number"], t, b)


def apply(op: Op, owner: str, run: Callable = subprocess.run) -> str:
    """Execute one op. Returns an error string, or '' on success."""
    slug = f"{owner}/{op.repo}"
    if op.kind == "create":
        run(
            [
                "gh",
                "label",
                "create",
                LABEL,
                "--color",
                LABEL_COLOR,
                "--description",
                "Missing standard files",
                "--force",
                "-R",
                slug,
            ],
            capture_output=True,
            text=True,
        )
        cmd = ["gh", "issue", "create", "-R", slug, "--title", op.title, "--body", op.body, "--label", LABEL]
    elif op.kind == "update":
        cmd = ["gh", "issue", "edit", str(op.number), "-R", slug, "--title", op.title, "--body", op.body]
    elif op.kind == "close":
        cmd = ["gh", "issue", "close", str(op.number), "-R", slug, "--comment", "The repo now conforms to the standard; closing."]
    else:
        return ""
    r = run(cmd, capture_output=True, text=True)
    return "" if r.returncode == 0 else ((r.stderr or "").strip() or f"gh issue {op.kind} failed")
