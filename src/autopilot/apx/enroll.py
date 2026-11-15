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

import base64
import datetime as dt
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from . import caps, cilane, repo_ci
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
    state: str  # "shadow" or "live" (promote)
    reason: str
    private_ci: bool = False  # live as a checks-only repo with a repo_ci.json spec (as APX_PRIVATE_CI)
    contexts: tuple = ()  # live, not private: (guard, ci) as the default branch's ruleset requires them


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
    live = {r: f for r, f in found.items() if f.state == "live"}
    return replace(
        s,
        installations={**s.installations, **{r: f.installation for r, f in found.items()}},
        discovered=s.discovered | frozenset(found),
        shadow_only=s.shadow_only | shadow,
        private_ci=s.private_ci | frozenset(r for r, f in live.items() if f.private_ci),
        cutover=s.cutover | frozenset(r for r, f in live.items() if not f.private_ci),  # the full loop, as APX_CUTOVER
        live_contexts={**s.live_contexts, **{r: f.contexts for r, f in live.items() if not f.private_ci}},
    )


# --- promotion: `apx: live` in the repo's own default-branch .autopilot/repo.yaml ---------------------------------------------------

YAML_PATH = ".autopilot/repo.yaml"
WEB_FLOW = "web-flow"  # GitHub's committer for web edits; GitHub signs those commits


def owner_set_it(api, repo: str, branch: str, owner: str) -> str | None:
    """None if the latest commit touching repo.yaml on the default branch is Verified and either sits in PRs that the OWNER merged,
    or (no PR) was authored by the owner and committed by the owner or GitHub's web editor. A forged author alone is not enough:
    the committer must match too, and an apx lane merge does not count. Else the reason."""
    commits = api("GET", f"/repos/{repo}/commits?sha={branch}&path={YAML_PATH}&per_page=1")
    if not commits:
        return f"no commit touches {YAML_PATH}"
    c = commits[0]
    if not ((c.get("commit") or {}).get("verification") or {}).get("verified"):
        return f"latest {YAML_PATH} commit is not Verified"
    prs = [p for p in api("GET", f"/repos/{repo}/commits/{c['sha']}/pulls") if p.get("merged_at")]
    if prs:
        for p in prs:
            merger = ((api("GET", f"/repos/{repo}/pulls/{p['number']}").get("merged_by") or {}).get("login") or "").lower()
            if merger != owner.lower():
                return f"{YAML_PATH} change merged by someone other than the owner ({merger or 'unknown'})"
        return None
    author, committer = ((c.get("author") or {}).get("login") or ""), ((c.get("committer") or {}).get("login") or "")
    if author.lower() == owner.lower() and committer.lower() in (owner.lower(), WEB_FLOW):
        return None
    return f"latest {YAML_PATH} commit is not by the owner (author {author or '?'}, committer {committer or '?'})"


def ruleset_contexts(api, repo: str, branch: str) -> tuple[tuple, str | None]:
    """(guard, ci) from the default branch's required status checks, which must be `guard / guard` and exactly one other."""
    rules = api("GET", f"/repos/{repo}/rules/branches/{branch}")
    req = [c["context"] for r in rules if r.get("type") == "required_status_checks" for c in r["parameters"]["required_status_checks"]]
    others = [c for c in req if c != "guard / guard"]
    if "guard / guard" not in req or len(others) != 1:
        return (), f"the {branch} ruleset must require `guard / guard` and exactly one CI check (requires {sorted(req)})"
    return ("guard / guard", others[0]), None


def _decide(api, repo: str, owner: str, tools_for) -> tuple[str | None, bool, tuple]:
    """(reason it stays shadow or None, private_ci, contexts)."""
    branch = api("GET", f"/repos/{repo}")["default_branch"]
    try:
        f = api("GET", f"/repos/{repo}/contents/{YAML_PATH}?ref={branch}")
        cfg = yaml.safe_load(base64.b64decode(f["content"])) or {}
    except GitHubError as e:
        if e.status == 404:
            return f"no {YAML_PATH} on {branch}", False, ()
        raise
    if not isinstance(cfg, dict) or cfg.get("apx") != "live":
        return f"{YAML_PATH} does not say `apx: live`", False, ()
    why = owner_set_it(api, repo, branch, owner)
    if why:
        return why, False, ()
    private, contexts = cfg.get("private_ci") is True, ()
    if private and repo_ci.spec_for(repo) is None:
        return "private_ci: true but repo_ci.json has no entry for it", True, ()
    if not private:
        if not cilane.parse_ci_steps(cfg):
            return f"no `ci:` list in {YAML_PATH}", False, ()
        contexts, why = ruleset_contexts(api, repo, branch)
        if why:
            return why, False, ()
    if tools_for is None:
        return "host tools cannot be checked without a sandbox account (APX_CI_USER)", private, ()
    problems = tools_for(repo, private)
    if problems:
        return "host tools: " + "; ".join(problems), private, ()
    return None, private, contexts


def promote(s, found: dict[str, Found], api_for, tools_for) -> tuple[dict[str, Found], list[str]]:
    """Each discovered repo, live if its repo.yaml earns it (see _decide), else shadow with the reason. tools_for(repo, private) returns
    the failing host-tool checks (the doctor's, as the sandbox account), or is None when there is no sandbox account. Read-only."""
    out, log = {}, []
    for r, f in found.items():
        try:
            why, private, contexts = _decide(api_for(r), r, s.owner if s else "RyanJHamby", tools_for)
        except ERRORS as e:
            why, private, contexts = f"could not read its settings ({type(e).__name__})", False, ()
        if why is None:
            out[r] = replace(f, state="live", reason="apx: live set by the owner", private_ci=private, contexts=contexts)
        else:
            out[r] = replace(f, state="shadow", reason=why)
        if out[r].state == "live" or why != f"{YAML_PATH} does not say `apx: live`":
            log.append(f"enroll: {r} {out[r].state} ({out[r].reason})")
    return out, log
