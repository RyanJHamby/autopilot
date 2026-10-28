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
import runner as kit_runner  # noqa: E402

from . import cilane, claude_runner, committer, gitops, guardlane, mergelane, report  # noqa: E402
from .app_auth import TokenCache  # noqa: E402
from .executor import Deps, IssueResult, execute  # noqa: E402
from .github import Api, make_api  # noqa: E402
from .ledger import Ledger  # noqa: E402
from .planner import ALLOWED_REPOS, Action, load_cfg, plan  # noqa: E402


class ConfigError(RuntimeError):
    pass


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
                oauth_file=e["APX_OAUTH_FILE"],
                kit_repo=e["APX_KIT_REPO"],
                kit_ref=e["APX_KIT_REF"],
                db_path=e.get("APX_DB", "apx.sqlite"),
                work_dir=Path(e.get("APX_WORK", str(Path(tempfile.gettempdir()) / "apx-work"))),
                shadow=e.get("APX_SHADOW", "1") != "0",
                control_url=e.get("APX_CONTROL_URL", ""),
                webhook_secret_file=e.get("APX_WEBHOOK_SECRET_FILE", ""),
            )
        except KeyError as ex:
            raise ConfigError(f"missing setting {ex}") from None
        bad = set(s.installations) - ALLOWED_REPOS
        if bad:
            raise ConfigError(f"repos outside scope: {sorted(bad)}")
        try:
            guardlane.validate_kit(s.kit_repo, s.kit_ref)
        except guardlane.KitError as ex:
            raise ConfigError(str(ex)) from None
        return s

    def contexts(self, repo: str) -> dict[str, str]:
        return {"guard": "apx / guard", "ci": "apx / build"} if self.shadow else {"guard": "guard / guard", "ci": "build"}


def routed_api(cache: TokenCache) -> Api:
    """One callable that picks the right installation token from the /repos/{owner}/{name}/ prefix of each path."""

    def api(method: str, path: str, body: dict | None = None):
        m = re.match(r"^/repos/([^/]+/[^/]+)/", path)
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
) -> IssueResult:
    """Issue -> worktree -> untrusted model -> trusted patch check -> trusted signed commit and PR. Never merges."""
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
    branch = f"agent/{issue}-{run_id}"
    body = (
        f"Refs #{issue}\n\n{out.summary[-3000:]}\n\n"
        "Opened by apx (the owner-run executor); patch passed the kit guard before commit.\n\n"
        "🤖 Generated with [Claude Code](https://claude.com/claude-code)"
    )
    res = committer.commit_and_pr(
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
    return IssueResult(True, out.summary, pr_number=res["pr_number"], turns=out.usage.turns, model=d["model"])


def make_report(s: Settings):
    """Ledger reporting is optional: both the URL and the secret file must be configured."""
    if not (s.control_url and s.webhook_secret_file):
        return None
    return report.make_reporter(s.control_url, read_secret_file(s.webhook_secret_file))


def select_automerge(s: Settings, merge):
    """The merge lane exists only after cutover; in shadow mode Actions still merges and apx must not."""
    return None if s.shadow else merge


def build_deps(s: Settings, api: Api, token_for, details: dict[str, str]) -> Deps:
    kit = guardlane.fetch_kit(s.kit_repo, s.kit_ref, s.work_dir / "kit" / s.kit_ref)

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
        repo_cfg = (
            yaml.safe_load(_git_show(co, f"origin/{s.default_branch}:.autopilot/repo.yaml")) or {}
        )  # commands come from the BASE branch only
        cmds = cilane.parse_ci_steps(repo_cfg)
        home = Path(tempfile.mkdtemp(dir=s.work_dir))
        return cilane.summarize(cilane.run_commands(co, cmds, home=home), cmds)

    def work(repo: str, issue: int, run_id: int) -> IssueResult:
        return work_on_issue(s, api, token_for, repo, issue, run_id, details.get(f"{repo}#{issue}", ""))

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

    return Deps(checkout, guard, ci, work, select_automerge(s, merge), make_report(s))


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


def _run_once_locked(s: Settings, *, live: bool, api_factory) -> list[str]:
    gitops.prune_work(s.work_dir)
    really_live = live and os.environ.get("APX_LIVE") == "1"
    cache = TokenCache(s.app_id, s.key_path, s.installations, api_factory=api_factory)
    api = routed_api(cache)
    ledger = Ledger(s.db_path)
    ledger.abandon_stale(dt.timedelta(hours=2))
    repos = {
        r: {"default_branch": s.default_branch, "contexts": list(s.contexts(r).values()), "merge": not s.shadow}
        for r in s.installations
    }
    planned = plan(api, ledger, repos, s.owner)
    actions: list[Action] = [a for r in planned.values() for a in r["actions"]]
    log = [f"{repo}: {len(r['actions'])} action(s) - {r['note']}" for repo, r in planned.items()]
    if not really_live:
        return log + execute(api, ledger, None, actions, contexts={}, head_refs={}, dry_run=True)  # type: ignore[arg-type]
    details = {f"{a.repo}#{a.ref}": a.detail for a in actions if a.kind == "run-agent"}
    heads = {}
    for repo in s.installations:
        for pr in api("GET", f"/repos/{repo}/pulls?state=open&per_page=100"):  # type: ignore[union-attr]
            heads[(repo, pr["head"]["sha"])] = pr["head"]["ref"]
    deps = build_deps(s, api, cache.token_for, details)
    ctx = {r: s.contexts(r) for r in s.installations}
    return log + execute(api, ledger, deps, actions, contexts=ctx, head_refs=heads, dry_run=False)


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
    try:
        for line in run_once(Settings.from_env(), live=ns.live):
            print(line)
    except ConfigError as e:
        print(f"apx config error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
