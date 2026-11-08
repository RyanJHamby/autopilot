"""List the owner's repos from GitHub, gate them, audit each against the standard.

Everything that touches the network or the disk takes an injected function, so tests use fakes. Nothing here writes into a
real checkout: a repo without a local clone is audited from a shallow throwaway clone."""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from autopilot.scaffold import core as scaffold
from autopilot.standard import command as check_command
from autopilot.standard import engine

LIMIT = 1000  # `gh repo list` default is 30; ap scan's 200 would silently drop repos for a larger account
NEW_DAYS = 14
FIELDS = "name,isFork,isArchived,visibility,isTemplate,createdAt,pushedAt"


class ListError(Exception):
    """GitHub could not be asked. The job must fail loudly: an empty list would read as 'everything is fine'."""


@dataclass
class Listed:
    name: str
    fork: bool = False
    archived: bool = False
    public: bool | None = None
    template: bool = False
    created_at: str = ""


@dataclass
class Audit:
    name: str
    public: bool | None = None
    skipped: str | None = None  # why this repo was not audited
    gaps: list[str] = field(default_factory=list)  # failing rules, "rule-id: first finding"
    fail_level: int = 0  # how many of the gaps are fail-level rules
    fixable: list[str] = field(default_factory=list)  # files `ap standard fix` would create
    new: bool = False  # created in the last NEW_DAYS days
    in_portfolio: bool = False
    note: str = ""


def parse_list(text: str) -> list[Listed]:
    try:
        rows = json.loads(text)
    except json.JSONDecodeError as e:
        raise ListError(f"gh repo list returned something that is not JSON: {e}") from e
    if not isinstance(rows, list):
        raise ListError("gh repo list did not return a list")
    out = []
    for r in rows:
        vis = str(r.get("visibility", "")).upper()
        out.append(
            Listed(
                name=r["name"],
                fork=bool(r.get("isFork")),
                archived=bool(r.get("isArchived")),
                public={"PUBLIC": True, "PRIVATE": False, "INTERNAL": False}.get(vis),
                template=bool(r.get("isTemplate")),
                created_at=r.get("createdAt") or "",
            )
        )
    return out


def list_repos(owner: str, run: Callable = subprocess.run, limit: int = LIMIT) -> list[Listed]:
    try:
        r = run(["gh", "repo", "list", owner, "--limit", str(limit), "--json", FIELDS], capture_output=True, text=True)
    except OSError as e:
        raise ListError(f"gh could not run: {e}") from e
    if r.returncode != 0:
        raise ListError(f"gh repo list failed: {(r.stderr or '').strip() or 'no message'}")
    repos = parse_list(r.stdout)
    if len(repos) >= limit:
        raise ListError(
            f"gh returned {len(repos)} repos, the limit: some may be missing. Raise LIMIT rather than trust a cut-off list."
        )
    return repos


def gate(r: Listed, owner: str, portfolio: dict) -> str | None:
    """Why a listed repo is not audited, or None."""
    entry = (portfolio.get("repos") or {}).get(r.name) or {}
    if r.fork:
        return "fork"
    if r.archived:
        return "archived"
    if r.name.lower() == owner.lower():
        return "profile repo"
    if r.name in (portfolio.get("excluded") or []):
        return "in `excluded:` in policy/portfolio.yaml"
    if r.template:
        return "template repo"
    if entry.get("data_class") == "restricted":
        return "data_class is restricted"
    return None


def is_new(created_at: str, today: date, days: int = NEW_DAYS) -> bool:
    try:
        made = datetime.fromisoformat(created_at.replace("Z", "+00:00")).date()
    except ValueError:
        return False
    return 0 <= (today - made).days <= days


def checkout(name: str, owner: str, root: Path, repo_name, run: Callable = subprocess.run):
    """A local clone if one exists under `root`; otherwise a shallow throwaway clone. Returns (path, tempdir or None, error)."""
    found = check_command.find_clone(name, root, repo_name)
    if found is not None:
        return found, None, ""
    tmp = tempfile.TemporaryDirectory(prefix="converge-")
    r = run(["gh", "repo", "clone", f"{owner}/{name}", tmp.name + "/repo", "--", "--depth", "1"], capture_output=True, text=True)
    if r.returncode != 0:
        tmp.cleanup()
        return None, None, (r.stderr or "").strip() or "clone failed"
    return Path(tmp.name) / "repo", tmp, ""


def audit(listed: Listed, path: Path, owner: str, portfolio: dict, today: date) -> Audit:
    """Run the standard and the scaffolder's planner against one checkout. Reads only."""
    entry = (portfolio.get("repos") or {}).get(listed.name)
    a = Audit(listed.name, public=listed.public, new=is_new(listed.created_at, today), in_portfolio=entry is not None)
    ctx = scaffold.read_ctx(
        path,
        listed.name,
        owner,
        listed.public,
        holder=(entry or {}).get("holder") or portfolio.get("holder"),
        kind=(entry or {}).get("kind"),
        restricted=(entry or {}).get("data_class") == "restricted",
    )
    why = scaffold.refusal(ctx)
    if why:
        a.skipped = why
        return a
    repo = engine.Repo(path, entry=entry, slug=None, gh=check_command.offline_gh, github_public=listed.public)
    for res in engine.run(repo):
        if res.result == "fail":
            a.gaps.append(f"{res.id}: {res.findings[0] if res.findings else 'failed'}")
            a.fail_level += res.level == "fail"
    a.fixable = [x.path for x in scaffold.plan(path, ctx) if x.status == "create"]
    return a
