"""apx daemon: wires settings, App auth, the planner, the executor and the real lanes together.

Safe by default: `run_once` is a dry run unless BOTH `live=True` and APX_LIVE=1 are set. In shadow mode (APX_SHADOW, default
on) checks are posted under non-required names (`apx / guard`, `apx / build`) so they cannot satisfy or block merges until
the owner cuts a repo over. Secrets are read from files with mode 600 (never argv, never logged).
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "kit" / "runtime"))
import gate  # noqa: E402
import runner as kit_runner  # noqa: E402

from . import cilane, claude_runner, committer, gitops, guardlane, mergelane, report, status  # noqa: E402
from .app_auth import TokenCache  # noqa: E402
from .executor import Deps, IssueResult, execute  # noqa: E402
from .github import Api, GitHubError, make_api  # noqa: E402
from .ledger import Ledger  # noqa: E402
from .planner import ALLOWED_REPOS, Action, load_cfg, plan  # noqa: E402
from .redact import redact, register  # noqa: E402
from .runas import Launcher  # noqa: E402
from .sandbox import SandboxLanes, run_agent_in_sandbox  # noqa: E402
from .usage import repo_usage, usage_line  # noqa: E402


class ConfigError(RuntimeError):
    pass


# The check names each repo's ruleset REQUIRES (read from the live rulesets; integration_id is "any"). A repo listed in
# APX_AUTHORITATIVE gets apx's checks under exactly these names, so apx can satisfy the merge rules instead of Actions.
REQUIRED_CONTEXTS = {
    "RyanJHamby/autopilot": ("guard / guard", "test"),
    "RyanJHamby/stencil": ("guard / guard", "build"),
    "RyanJHamby/drillpad-workspace": ("guard / guard", "test"),
}


def read_secret_file(path: str) -> str:
    p = Path(path)
    st = p.stat()
    if st.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ConfigError(f"{p.name}: permissions too open; chmod 600")
    return p.read_text().strip()


@dataclass
class Settings:
    owner: str
    app_id: str
    key_path: Path
    installations: dict[str, int]
    oauth_file: str
    kit_repo: str
    kit_ref: str
    db_path: str = "apx.sqlite"
    work_dir: Path = field(default_factory=lambda: Path(tempfile.gettempdir()) / "apx-work")
    shadow: bool = True
    default_branch: str = "main"
    control_url: str = ""
    webhook_secret_file: str = ""
    authoritative: frozenset = frozenset()
    cutover: frozenset = frozenset()
    ci_toolchain_links: tuple = (".cargo",)
    # Sandbox accounts (backlog S1/S1b). ci_user runs a PR's code with no access to the App key or Claude token; agent_user runs
    # the model with only the Claude token. Unset = today's behaviour for checks, and agent runs stay OFF.
    ci_user: str = ""
    ci_work: str = "/Users/apx-ci/work"
    shared_dir: str = "/Users/Shared/apx"
    agent_user: str = ""
    agent_work: str = ""  # default /Users/<agent_user>/work
    agent_binary: str = ""  # default /Users/<agent_user>/.local/bin/claude

    @classmethod
    def from_env(cls, env: dict | None = None) -> "Settings":
        e = os.environ if env is None else env
        try:
            inst = dict(p.split("=", 1) for p in e["APX_INSTALLATIONS"].split(","))
            s = cls(
                owner=e.get("APX_OWNER", "RyanJHamby"),
                app_id=e["APX_APP_ID"],
                key_path=Path(e["APX_KEY_PATH"]),
                installations={k: int(v) for k, v in inst.items()},
                # with a dedicated agent account the token lives in ITS home and the orchestrator never reads it
                oauth_file=e.get("APX_OAUTH_FILE")
                or (f"/Users/{e['APX_AGENT_USER']}/.apx/claude-oauth" if e.get("APX_AGENT_USER") else e["APX_OAUTH_FILE"]),
                kit_repo=e["APX_KIT_REPO"],
                kit_ref=e["APX_KIT_REF"],
                db_path=e.get("APX_DB", "apx.sqlite"),
                work_dir=Path(e.get("APX_WORK", str(Path(tempfile.gettempdir()) / "apx-work"))),
                shadow=e.get("APX_SHADOW", "1") != "0",
                control_url=e.get("APX_CONTROL_URL", ""),
                webhook_secret_file=e.get("APX_WEBHOOK_SECRET_FILE", ""),
                authoritative=frozenset(r for r in e.get("APX_AUTHORITATIVE", "").split(",") if r),
                cutover=frozenset(r for r in e.get("APX_CUTOVER", "").split(",") if r),
                ci_toolchain_links=tuple(n for n in e.get("APX_CI_TOOLCHAIN_LINKS", ".cargo").split(",") if n),
                ci_user=e.get("APX_CI_USER", ""),
                ci_work=e.get("APX_CI_WORK", "/Users/apx-ci/work"),
                shared_dir=e.get("APX_SHARED", "/Users/Shared/apx"),
                agent_user=e.get("APX_AGENT_USER", ""),
                agent_work=e.get("APX_AGENT_WORK", ""),
                agent_binary=e.get("APX_AGENT_BINARY", ""),
            )
        except KeyError as ex:
            raise ConfigError(f"missing setting {ex}") from None
        bad = set(s.installations) - ALLOWED_REPOS
        if bad:
            raise ConfigError(f"repos outside scope: {sorted(bad)}")
        try:
            for u in (s.ci_user, s.agent_user):
                if u:
                    Launcher(u).wrap(["true"], "/", {}, [])  # same validation the launcher applies: no root, no apx, plain names
        except ValueError as ex:
            raise ConfigError(str(ex)) from None
        if s.ci_user and s.ci_user == s.agent_user:
            raise ConfigError("APX_CI_USER and APX_AGENT_USER must be different accounts")
        stray = (set(s.authoritative) | set(s.cutover)) - set(s.installations)
        if stray:
            raise ConfigError(f"APX_AUTHORITATIVE / APX_CUTOVER name repos that are not installed: {sorted(stray)}")
        try:
            guardlane.validate_kit(s.kit_repo, s.kit_ref)
        except guardlane.KitError as ex:
            raise ConfigError(str(ex)) from None
        return s

    def full_loop(self, repo: str) -> bool:
        """True when apx, not Actions, runs this repo end to end: agent runs, rebases and the merge lane as well as checks."""
        return (not self.shadow) or repo in self.cutover

    def agents_allowed(self, repo: str) -> bool:
        """Agent runs need the full loop AND a dedicated agent account. Without one the model would run as the account that
        holds the App key, so they stay off even if the repo is cut over (backlog gate S1b)."""
        return self.full_loop(repo) and bool(self.agent_user)

    def contexts(self, repo: str) -> dict[str, str]:
        """Shadow names are non-required (cannot satisfy or block a merge). A repo that is authoritative, or any repo once
        shadow mode is off, posts the names its ruleset requires."""
        if self.shadow and repo not in self.authoritative and repo not in self.cutover:
            return {"guard": "apx / guard", "ci": "apx / build"}
        guard, ci = REQUIRED_CONTEXTS[repo]
        return {"guard": guard, "ci": ci}


def routed_api(cache: TokenCache) -> Api:
    """One callable that picks the right installation token from the /repos/{owner}/{name}/ prefix of each path."""

    def api(method: str, path: str, body: dict | None = None):
        m = re.match(r"^/repos/([^/]+/[^/]+)(?:/|$)", path)
        if not m:
            raise ValueError(f"unroutable path {path}")
        return cache.api_for(m.group(1))(method, path, body)

    return api


def parse_detail(detail: str) -> dict:
    """Planner puts `model=sonnet effort=medium turns=40` in Action.detail."""
    kv = dict(p.split("=", 1) for p in detail.split() if "=" in p)
    return {"model": kv.get("model", "sonnet"), "effort": kv.get("effort", "medium"), "turns": int(kv.get("turns", 25))}


def work_on_issue(
    s: Settings,
    api: Api,
    token_for,
    repo: str,
    issue: int,
    run_id: int,
    detail: str,
    *,
    binary: str = "claude",
    url: str | None = None,
    read_token_for=None,
    run_agent=None,
) -> IssueResult:
    """Issue -> worktree -> untrusted model -> trusted patch check -> trusted signed commit and PR. Never merges.
    With a dedicated agent account the model runs there (holding only the Claude token and a read-only repo token) and its changes
    come back as data; this account then makes the commit."""
    d = parse_detail(detail)
    iss = api("GET", f"/repos/{repo}/issues/{issue}")
    comments = api("GET", f"/repos/{repo}/issues/{issue}/comments?per_page=100")
    cfg = load_cfg(api, repo, s.default_branch)
    commands = cilane.parse_commands(cfg)
    prompt = claude_runner.build_prompt(
        repo,
        issue,
        iss["title"],
        iss.get("body") or "",
        claude_runner.owner_comments(comments, s.owner),  # type: ignore[index,arg-type]
    )
    head = api("GET", f"/repos/{repo}/git/ref/heads/{s.default_branch}")["object"]["sha"]  # type: ignore[index]
    if s.agent_user:
        if read_token_for is None:
            raise ConfigError("an agent account is configured but no read-only token source was provided")
        req = {
            "repo": repo,
            "base_sha": head,
            "base_branch": s.default_branch,
            "issue": issue,
            "prompt": prompt,
            "model": d["model"],
            "effort": d["effort"],
            "max_turns": d["turns"],
            "commands": commands,
            "work_root": s.agent_work or f"/Users/{s.agent_user}/work",
            "binary": s.agent_binary or f"/Users/{s.agent_user}/.local/bin/claude",
        }
        run = run_agent or (
            lambda r, tok: run_agent_in_sandbox(
                Launcher(s.agent_user),
                r,
                tok,
                python=f"{s.shared_dir}/venv/bin/python",
                code_dir=f"{s.shared_dir}/autopilot",
                home=f"/Users/{s.agent_user}",
            )
        )
        res, changes = run(req, read_token_for(repo))
        if not res.get("ok"):
            why = "; ".join(res.get("violations") or []) or res.get("error", "agent run failed")
            return IssueResult(False, res.get("summary", ""), why, turns=res.get("turns"), model=d["model"])
        summary, turns = res.get("summary", ""), res.get("turns")
    else:
        wt = s.work_dir / f"{repo.replace('/', '_')}-{issue}-{run_id}"
        gitops.checkout_pr(repo, head, s.default_branch, wt, token_for(repo), url=url, root=s.work_dir)
        home = s.work_dir / f"home-{run_id}"
        home.mkdir(parents=True, exist_ok=True)
        r = claude_runner.ClaudeRunner(
            read_secret_file(s.oauth_file), home=home, commands=commands, prompt=prompt, effort=d["effort"], binary=binary
        )
        out = kit_runner.process(r, kit_runner.Task(issue=issue, prompt="", model=d["model"], max_turns=d["turns"]), wt)
        if not out.ok:
            return IssueResult(False, out.summary, "; ".join(out.violations), turns=out.usage.turns, model=d["model"])
        changes = committer.changes_from_worktree(wt, head)
        summary, turns = out.summary, out.usage.turns
    branch = f"agent/{issue}-{run_id}"
    body = (
        f"Refs #{issue}\n\n{summary[-3000:]}\n\n"
        "Opened by apx (the owner-run executor); patch passed the kit guard before commit.\n\n"
        "🤖 Generated with [Claude Code](https://claude.com/claude-code)"
    )
    pr = committer.commit_and_pr(
        api,
        repo,
        head,
        branch,
        changes,
        message=f"{iss['title']}\n\nRefs #{issue}\n\nCo-Authored-By: Claude <noreply@anthropic.com>",  # type: ignore[index]
        title=f"{iss['title']} (agent #{issue})",  # type: ignore[index]
        body=body,
        base_branch=s.default_branch,
    )
    return IssueResult(True, summary, pr_number=pr["pr_number"], turns=turns, model=d["model"])


def failing_ci_text(api: Api, repo: str, sha: str, ci_contexts: list[str], limit: int = 4000) -> str:
    """What apx itself reported for the failing CI check on this head (only checks posted by the apx App). On a public repo that is
    step names and timings; on a private one it includes the redacted tail of the failing command."""
    runs = api("GET", f"/repos/{repo}/commits/{sha}/check-runs?per_page=100")["check_runs"]  # type: ignore[index]
    out = [
        f"{c['name']}: {c.get('conclusion')}\n{(c.get('output') or {}).get('summary') or ''}"
        for c in runs
        if (c.get("app") or {}).get("slug") == "autopilot-apx" and c["name"] in ci_contexts and c.get("conclusion") == "failure"
    ]
    return redact("\n\n".join(out))[:limit] or "(no failure text was available)"


def fix_pr(
    s: Settings,
    api: Api,
    repo: str,
    issue: int,
    pr_number: int,
    head_sha: str,
    detail: str,
    ci_contexts: list[str],
    *,
    read_token_for,
    run_agent=None,
) -> IssueResult:
    """Red CI on an agent PR -> the model (as the agent account) edits a checkout of the PR head -> apx adds one commit to that same branch.
    Needs the dedicated agent account: a fix never runs the model in the orchestrator's account."""
    if not s.agent_user:
        raise ConfigError("fixing a PR needs a dedicated agent account")
    if read_token_for is None:
        raise ConfigError("an agent account is configured but no read-only token source was provided")
    d = parse_detail(detail)
    pr = api("GET", f"/repos/{repo}/pulls/{pr_number}")
    branch = pr["head"]["ref"]  # type: ignore[index]
    iss = api("GET", f"/repos/{repo}/issues/{issue}")
    comments = api("GET", f"/repos/{repo}/issues/{issue}/comments?per_page=100")
    commands = cilane.parse_commands(load_cfg(api, repo, s.default_branch))
    prompt = claude_runner.build_fix_prompt(
        repo,
        issue,
        iss["title"],  # type: ignore[index]
        iss.get("body") or "",  # type: ignore[union-attr]
        claude_runner.owner_comments(comments, s.owner),  # type: ignore[arg-type]
        failing_ci_text(api, repo, head_sha, ci_contexts),
    )
    req = {
        "repo": repo,
        "base_sha": head_sha,
        "base_branch": s.default_branch,
        "issue": issue,
        "prompt": prompt,
        "model": d["model"],
        "effort": d["effort"],
        "max_turns": d["turns"],
        "commands": commands,
        "work_root": s.agent_work or f"/Users/{s.agent_user}/work",
        "binary": s.agent_binary or f"/Users/{s.agent_user}/.local/bin/claude",
    }
    run = run_agent or (
        lambda r, tok: run_agent_in_sandbox(
            Launcher(s.agent_user),
            r,
            tok,
            python=f"{s.shared_dir}/venv/bin/python",
            code_dir=f"{s.shared_dir}/autopilot",
            home=f"/Users/{s.agent_user}",
        )
    )
    res, changes = run(req, read_token_for(repo))
    if not res.get("ok"):
        why = "; ".join(res.get("violations") or []) or res.get("error", "agent run failed")
        return IssueResult(False, res.get("summary", ""), why, turns=res.get("turns"), model=d["model"])
    if not changes:
        return IssueResult(False, res.get("summary", ""), "the model made no change", turns=res.get("turns"), model=d["model"])
    try:
        committer.commit_to_branch(
            api,
            repo,
            branch,
            head_sha,
            changes,
            message=f"Fix CI for #{issue} (attempt by apx)\n\nRefs #{issue}\n\nCo-Authored-By: Claude <noreply@anthropic.com>",
        )
    except committer.StaleHeadError as e:
        return IssueResult(False, res.get("summary", ""), str(e), turns=res.get("turns"), model=d["model"])
    return IssueResult(True, res.get("summary", ""), pr_number=pr_number, turns=res.get("turns"), model=d["model"])


def make_report(s: Settings):
    """Ledger reporting is optional: both the URL and the secret file must be configured."""
    if not (s.control_url and s.webhook_secret_file):
        return None
    return report.make_reporter(s.control_url, read_secret_file(s.webhook_secret_file))


def ci_lane(s: Settings, co: Path) -> tuple[bool, str]:
    """Run the repo's `ci:` steps (from the BASE branch only) in a scratch HOME that has just the owner-chosen toolchain
    directories linked in."""
    repo_cfg = yaml.safe_load(_git_show(co, f"origin/{s.default_branch}:.autopilot/repo.yaml")) or {}
    cmds = cilane.parse_ci_steps(repo_cfg)
    home = Path(tempfile.mkdtemp(dir=s.work_dir))
    res = cilane.run_commands(co, cmds, home=home, toolchain_links=list(s.ci_toolchain_links), real_home=Path.home())
    return cilane.summarize(res, cmds)


def select_automerge(s: Settings, merge):
    """The merge lane exists only once some repo is cut over (the planner then offers it only for those repos); with
    everything in shadow mode Actions still merges and apx must not."""
    return merge if (not s.shadow or s.cutover) else None


def build_deps(s: Settings, api: Api, token_for, details: dict[str, str], read_token_for=None) -> Deps:
    # with a sandbox account the kit lives where that account can read it; otherwise next to the rest of the work
    kit_root = Path(s.shared_dir) / "kit" if s.ci_user else s.work_dir / "kit"
    kit = guardlane.fetch_kit(s.kit_repo, s.kit_ref, kit_root / s.kit_ref)
    if s.ci_user:
        if read_token_for is None:
            # PR code runs in this lane; the full installation token (checks:write, contents:write) must never reach it
            raise ConfigError("a CI account is configured but no read-only token source was provided")
        lanes = SandboxLanes(
            Launcher(s.ci_user),
            base_branch=s.default_branch,
            kit_dir=str(kit),
            work_root=s.ci_work,
            python=f"{s.shared_dir}/venv/bin/python",
            code_dir=f"{s.shared_dir}/autopilot",
            home=f"/Users/{s.ci_user}",
            token_for=read_token_for,
            steps_for=lambda repo: [list(x) for x in cilane.parse_ci_steps(load_cfg(api, repo, s.default_branch))],
            toolchain_links=list(s.ci_toolchain_links),
        )
        sb_checkout, sb_guard, sb_ci = lanes.checkout, lanes.guard, lanes.ci
    else:
        sb_checkout = sb_guard = sb_ci = None

    def checkout(repo: str, sha: str) -> Path:
        return gitops.checkout_pr(
            repo,
            sha,
            s.default_branch,
            s.work_dir / f"pr-{repo.replace('/', '_')}-{sha[:12]}",
            token_for(repo),
            root=s.work_dir,
        )

    def guard(co: Path, head_ref: str):
        tmp = Path(tempfile.mkdtemp(dir=s.work_dir))
        return guardlane.run_guard(co, kit, base=f"origin/{s.default_branch}", head="HEAD", head_ref=head_ref, tmp=tmp)

    def ci(co: Path):
        return ci_lane(s, co)

    def work(repo: str, issue: int, run_id: int) -> IssueResult:
        return work_on_issue(
            s, api, token_for, repo, issue, run_id, details.get(f"{repo}#{issue}", ""), read_token_for=read_token_for
        )

    def merge(repo: str, pr: int, sha: str) -> tuple[int, str]:
        # default-branch checkout, so the merge policy is what the owner merged, never the PR's copy
        co = gitops.checkout_pr(
            repo,
            api("GET", f"/repos/{repo}/git/ref/heads/{s.default_branch}")["object"]["sha"],
            s.default_branch,  # type: ignore[index]
            s.work_dir / f"main-{repo.replace('/', '_')}-{pr}",
            token_for(repo),
            root=s.work_dir,
        )
        tmp = Path(tempfile.mkdtemp(dir=s.work_dir))
        return mergelane.run_automerge(
            co,
            kit,
            repo=repo,
            pr=pr,
            head_sha=sha,
            token=token_for(repo),
            owner=s.owner,
            kit_repo=s.kit_repo,
            base=f"origin/{s.default_branch}",
            tmp=tmp,
        )

    def fix(repo: str, issue: int, run_id: int, pr: int, sha: str, detail: str) -> IssueResult:
        return fix_pr(s, api, repo, issue, pr, sha, detail, [s.contexts(repo)["ci"]], read_token_for=read_token_for)

    return Deps(
        sb_checkout or checkout, sb_guard or guard, sb_ci or ci, work, select_automerge(s, merge), make_report(s), fix_ci=fix
    )


def _git_show(co: Path, spec: str) -> str:
    import subprocess

    p = subprocess.run(["git", "-C", str(co), "show", spec], capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else ""


@contextlib.contextmanager
def single_instance(work_dir: Path):
    """Only one apx pass at a time per work dir: a timer tick that fires while a long agent run is still going must
    not start the same issue twice. Yields True if this process holds the lock, False if another pass does."""
    work_dir.mkdir(parents=True, exist_ok=True)
    fh = open(work_dir / "apx.lock", "w")
    try:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        yield True
    finally:
        fh.close()  # closing releases the flock, including after a crash


def run_once(s: Settings, *, live: bool = False, api_factory=make_api) -> list[str]:
    """One pass: plan, then execute. Dry-run unless live=True AND APX_LIVE=1."""
    with single_instance(s.work_dir) as got:
        if not got:
            return ["another apx pass is still running; skipping this tick"]
        return _run_once_locked(s, live=live, api_factory=api_factory)


def open_heads(api: Api, repos) -> tuple[dict[tuple[str, str], str], set[str]]:
    """{(repo, head sha): head branch} for every open PR, and the repos that could not be listed. One dropped connection must cost
    that repo this pass, never the whole pass (it used to raise out of the daemon)."""
    heads: dict[tuple[str, str], str] = {}
    failed: set[str] = set()
    for repo in repos:
        try:
            for pr in api("GET", f"/repos/{repo}/pulls?state=open&per_page=100"):  # type: ignore[union-attr]
                heads[(repo, pr["head"]["sha"])] = pr["head"]["ref"]
        except (GitHubError, OSError, KeyError, TypeError):
            failed.add(repo)
    return heads, failed


def readable_only(actions: list[Action], unreadable: set[str]) -> list[Action]:
    """Without a repo's PR heads none of its actions can be carried out safely, so they wait for the next pass."""
    return [a for a in actions if a.repo not in unreadable]


def private_repos(api: Api, repos) -> frozenset:
    """Repos confirmed private by the API. Anything we cannot confirm is treated as public, so its output is withheld."""
    out = set()
    for r in repos:
        try:
            if api("GET", f"/repos/{r}").get("private") is True:  # type: ignore[union-attr]
                out.add(r)
        except Exception:  # noqa: BLE001
            pass
    return frozenset(out)


def _register_known_secrets(s: Settings) -> None:
    # with an agent account the orchestrator cannot (and must not) read the Claude token
    for path in (s.webhook_secret_file,) if s.agent_user else (s.oauth_file, s.webhook_secret_file):
        try:
            if path:
                register(read_secret_file(path))
        except Exception:  # noqa: BLE001 - redaction setup must never stop a pass
            pass


def usage_lines(ledger: Ledger, repos) -> list[str]:
    """One usage line per repo for the status file. The cap is the gate's default for tier A: a repo's own cap lives in repo.yaml,
    which is fetched over the network during planning, so a tier B/C repo's remaining count here is approximate."""
    try:
        cap = int(gate.DEFAULTS["runs_per_day"]["A"])
        return [usage_line(repo_usage(ledger, r, cap=cap)) for r in sorted(repos)]
    except Exception as e:  # noqa: BLE001 - a meter must never break a pass
        return [f"usage meter unavailable: {type(e).__name__}"]


def _run_once_locked(s: Settings, *, live: bool, api_factory) -> list[str]:
    _register_known_secrets(s)
    gitops.prune_work(s.work_dir)
    really_live = live and os.environ.get("APX_LIVE") == "1"
    cache = TokenCache(s.app_id, s.key_path, s.installations, api_factory=api_factory)
    api = routed_api(cache)
    ledger = Ledger(s.db_path)
    ledger.abandon_stale(dt.timedelta(hours=2))
    repos = {
        r: {
            "default_branch": s.default_branch,
            "contexts": list(s.contexts(r).values()),
            "loop": s.full_loop(r),
            "merge": s.full_loop(r),
            "agents": s.agents_allowed(r),
            "ci_contexts": [s.contexts(r)["ci"]],
        }
        for r in s.installations
    }
    planned = plan(api, ledger, repos, s.owner)
    actions: list[Action] = [a for r in planned.values() for a in r["actions"]]
    log = [f"{repo}: {len(r['actions'])} action(s) - {r['note']}" for repo, r in planned.items()]
    log += usage_lines(ledger, s.installations)
    if not really_live:
        return log + execute(api, ledger, None, actions, contexts={}, head_refs={}, dry_run=True)  # type: ignore[arg-type]
    details = {f"{a.repo}#{a.ref}": a.detail for a in actions if a.kind == "run-agent"}
    heads, unreadable = open_heads(api, s.installations)
    for repo in sorted(unreadable):
        log.append(f"{repo}: skipped this pass (could not list open PRs)")
    actions = readable_only(actions, unreadable)
    deps = build_deps(s, api, cache.token_for, details, read_token_for=cache.read_token_for)
    ctx = {r: s.contexts(r) for r in s.installations}
    return log + execute(
        api,
        ledger,
        deps,
        actions,
        contexts=ctx,
        head_refs=heads,
        dry_run=False,
        private_repos=private_repos(api, s.installations),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="apx: owner-run executor (dry-run unless --live and APX_LIVE=1)")
    ap.add_argument("--once", action="store_true", help="one planning/execution pass, then exit")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--doctor", action="store_true", help="check the whole setup (read-only) and exit")
    ap.add_argument(
        "--spike-check", metavar="OWNER/REPO#PR", help="after the spike, verify what it was meant to prove (read-only)"
    )
    ap.add_argument("--app-slug", default="autopilot-apx")
    ns = ap.parse_args(argv)
    if ns.doctor:
        from .doctor import render, run_doctor

        try:
            text, ok = render(run_doctor(Settings.from_env()))
        except ConfigError as e:
            print(f"apx config error: {e}", file=sys.stderr)
            return 2
        print(text)
        return 0 if ok else 1
    if ns.spike_check:
        from .spike import check_spike
        from .spike import render as render_spike

        try:
            st = Settings.from_env()
            repo, pr = ns.spike_check.rsplit("#", 1)
            cache = TokenCache(st.app_id, st.key_path, st.installations)
            text, ok = render_spike(
                check_spike(
                    cache.api_for(repo), repo, int(pr), app_slug=ns.app_slug, expect_contexts=list(st.contexts(repo).values())
                )
            )
        except (ConfigError, ValueError, KeyError) as e:
            print(f"apx spike-check error: {type(e).__name__}: {e}", file=sys.stderr)
            return 2
        print(text)
        return 0 if ok else 1
    if not ns.once:
        print("only --once is implemented; run it from a systemd timer", file=sys.stderr)
        return 2
    status_path = os.environ.get("APX_STATUS", status.DEFAULT_STATUS)
    try:
        st = Settings.from_env()
    except ConfigError as e:
        print(f"apx config error: {e}", file=sys.stderr)
        return 2
    version = status.code_version(f"{st.shared_dir}/autopilot")
    try:
        lines = run_once(st, live=ns.live)
    except Exception as e:  # noqa: BLE001 - record that the pass died so the owner's watcher can say so, then fail loudly
        status.write_status(status_path, [f"pass crashed: {type(e).__name__}"], live=ns.live, version=version)
        raise
    for line in lines:
        print(line)
    status.write_status(status_path, lines, live=ns.live, version=version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
