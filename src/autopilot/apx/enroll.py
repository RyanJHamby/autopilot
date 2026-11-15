"""Hands-off enrollment: a repo the owner installs the GitHub App on is picked up without editing apx.env.

Each pass lists the repositories of every installation apx.env already names (GET /installation/repositories with that installation's
token), cached for at most an hour next to the ledger. A listed repo that is NOT in APX_INSTALLATIONS is "discovered":
- it must belong to the owner's account, and policy/portfolio.yaml must not hold it back (`excluded:`, or a `repos:` entry with
  `mode: dormant` or `enabled: false`); otherwise it is ignored, and the doctor still calls it out of scope;
- it is handled in SHADOW mode: apx posts its non-required checks (`apx / guard`, `apx / build`) and nothing else. No agent runs, no
  merges, no branch updates, whatever APX_SHADOW says.

Why installing the App is enough to get checks: only the account owner can install the App on a repo, and shadow checks cannot block
or satisfy a merge. APX_INSTALLATIONS, APX_CUTOVER and APX_PRIVATE_CI keep working and win: a repo named there is never "discovered".
APX_DISCOVERY=0 turns discovery off (env repos only). Any error while listing or reading policy means no discovered repos this pass.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from . import caps
from .github import GitHubError

TTL = dt.timedelta(hours=1)
CACHE_NAME = "apx-discovered.json"
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
ERRORS = (GitHubError, OSError, KeyError, TypeError, ValueError, AttributeError, yaml.YAMLError)


class DiscoveryError(ValueError):
    pass


@dataclass(frozen=True)
class Found:
    repo: str
    installation: int
    state: str  # "shadow" (this module) or "live" (promotion)
    reason: str


def cache_path(s) -> Path:
    return Path(s.db_path).resolve().parent / CACHE_NAME


def _read_cache(path: Path, now: dt.datetime) -> dict[str, int] | None:
    try:
        raw = json.loads(path.read_text())
        at = dt.datetime.fromisoformat(raw["fetched_at"])
        repos = raw["repos"]
        if not (dt.timedelta(0) <= now - at <= TTL) or not isinstance(repos, dict):
            return None
        if not all(isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool) for k, v in repos.items()):
            return None
        return repos
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write_cache(path: Path, now: dt.datetime, repos: dict[str, int]) -> None:
    try:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"fetched_at": now.isoformat(), "repos": repos}, sort_keys=True))
        tmp.chmod(0o600)
        tmp.replace(path)
    except OSError:
        pass  # no cache only means the next pass asks GitHub again


def list_installed(api_for, installations: dict[str, int]) -> dict[str, int]:
    """{full_name: installation id} for every repo of every installation apx.env names. More than one page fails closed."""
    one_repo: dict[int, str] = {}
    for repo, inst in sorted(installations.items()):
        one_repo.setdefault(inst, repo)
    out: dict[str, int] = {}
    for inst, repo in sorted(one_repo.items()):
        body = api_for(repo)("GET", "/installation/repositories?per_page=100")
        repos = body["repositories"]
        if int(body.get("total_count", len(repos))) > len(repos):
            raise DiscoveryError("installation has more than 100 repositories; discovery reads one page only")
        for r in repos:
            if isinstance(r.get("full_name"), str) and REPO.match(r["full_name"]) and not r.get("archived"):
                out[r["full_name"]] = inst
    return out


def held_by_policy() -> set[str]:
    """Repo names (without owner) that policy keeps out: `excluded`, or `repos:` entries that are dormant or disabled."""
    raw = yaml.safe_load(Path(caps.PORTFOLIO_FILE).read_text())
    if not isinstance(raw, dict):
        raise DiscoveryError("policy is not a mapping")
    held = {str(n) for n in raw.get("excluded") or []}
    for name, entry in (raw.get("repos") or {}).items():
        if isinstance(entry, dict) and (entry.get("mode") == "dormant" or entry.get("enabled") is False):
            held.add(str(name))
    return held


def why_not(repo: str, owner: str, held: set[str]) -> str | None:
    """None if a listed repo may be discovered, else why not."""
    who, name = repo.split("/", 1)
    if who.lower() != owner.lower():
        return f"not owned by {owner}"
    if name in held:
        return "held back by policy/portfolio.yaml (excluded, dormant or enabled: false)"
    return None


def discover(s, api_for, now: dt.datetime | None = None) -> tuple[dict[str, Found], list[str]]:
    """({repo: Found} for this pass, log lines). Discovered repos are shadow here; promotion is applied by the caller."""
    if not s.discovery:
        return {}, ["discovery off (APX_DISCOVERY=0): apx.env repos only"]
    now = now or dt.datetime.now(dt.timezone.utc)
    path = cache_path(s)
    try:
        installed = _read_cache(path, now)
        if installed is None:
            installed = list_installed(api_for, s.installations)
            _write_cache(path, now, installed)
        held = held_by_policy()
    except ERRORS as e:
        return {}, [f"discovery failed ({type(e).__name__}): apx.env repos only this pass"]
    found = {
        r: Found(r, i, "shadow", "discovered (App installed); shadow by default")
        for r, i in sorted(installed.items())
        if r not in s.installations and why_not(r, s.owner, held) is None
    }
    return found, [f"discovered: {r} ({f.state}: {f.reason})" for r, f in found.items()]


def with_found(s, found: dict[str, Found]):
    """Settings for this pass: discovered repos added to the installations; shadow ones can only ever get shadow checks."""
    if not found:
        return s
    shadow = frozenset(r for r, f in found.items() if f.state == "shadow")
    return replace(
        s,
        installations={**s.installations, **{r: f.installation for r, f in found.items()}},
        discovered=s.discovered | frozenset(found),
        shadow_only=s.shadow_only | shadow,
    )


def promote(s, found, api_for, tools_for):  # stub: tests first
    raise NotImplementedError
