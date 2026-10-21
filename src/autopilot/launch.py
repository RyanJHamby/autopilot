"""launch-repo: one command from "a repo exists" to "autopilot runs on it" (part 1: the framework and the first four stages).

Run by the owner, as the owner (their `gh` login). It prints the plan, asks once (`--yes` skips the question), then runs
stages in order. Every stage is idempotent and read-back verified: it checks whether it is already done, does it if not,
then re-reads GitHub and stops if the change did not take. Re-running after a stop continues where it stopped.

  1. repo settings   Actions may open PRs; AUTOPILOT_DEBUG=false
  2. labels          the labels the dispatcher reads
  3. scaffold        thin callers pinned to the latest APPROVED kit sha, as a PR, merged (callers must be on the default
                     branch before a ruleset requires `guard / guard`)
  4. secret          CLAUDE_CODE_OAUTH_TOKEN, read hidden (or from --token-env) and piped to `gh secret set` on stdin only

Part 2 adds: App installations, the ruleset and enabling, the portfolio entry, and the steering issues.
Never force-pushes, never skips signing, never prints the token. Nothing runs without the one confirmation.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from . import ship
from .ship import Stop, _json, _out, sh

INIT_BRANCH = "autopilot/init"
SECRET = "CLAUDE_CODE_OAUTH_TOKEN"
NAME_RE = re.compile(r"^[\w.-]+$")
LABELS = {
    "agent-ready": ("0E8A16", "An agent may pick this up"),
    "hard": ("5319E7", "Needs the stronger model"),
    "hold": ("FBCA04", "Do not dispatch"),
    "needs-human": ("B60205", "Waiting on the owner"),
    "p0": ("B60205", "Highest priority"),
    "p1": ("D93F0B", "High priority"),
    "retry": ("C5DEF5", "Run again"),
    "blocked": ("000000", "Blocked on something external"),
    "agent-working": ("1D76DB", "An agent is on it (managed by autopilot)"),
}
SKIP_CHECKS = ("guard", "automerge", "dispatch", "handshake", "agent")
APPLY_WAIT = 120.0


def sh_in(cmd: Sequence[str], text: str) -> tuple[int, str]:
    p = subprocess.run(list(cmd), input=text, capture_output=True, text=True)
    return p.returncode, p.stdout


def _load_portfolio() -> dict:
    from . import cli

    return cli.load_portfolio()


def _latest_approved(kit_repo: str) -> str:
    from . import cli

    try:
        return cli._latest_approved(kit_repo)
    except SystemExit as e:
        raise Stop(str(e)) from e


def _hidden(prompt: str) -> str:
    try:
        return getpass.getpass(prompt)
    except EOFError:
        raise Stop("no terminal to read the token on; export it and pass --token-env NAME") from None


@dataclass
class Ctx:
    slug: str
    owner: str
    name: str
    tier: str
    mode: str
    kit_repo: str
    kit_sha: str
    repo_id: int
    default_branch: str
    token_env: str | None = None


@dataclass
class LaunchEnv(ship.Env):
    run_in: Callable[[Sequence[str], str], tuple[int, str]] = sh_in
    secret: Callable[[str], str] = _hidden
    portfolio: Callable[[], dict] = field(default=lambda: _load_portfolio())  # late-bound so tests can replace the loader
    approved: Callable[[str], str] = _latest_approved
    scaffold: Callable[..., str] | None = None

    def __post_init__(self) -> None:
        self.scaffold = self.scaffold or real_scaffold


@dataclass
class Stage:
    name: str
    done: Callable[[LaunchEnv, Ctx], bool]
    apply: Callable[[LaunchEnv, Ctx], None]


def _ok(env: LaunchEnv, cmd: Sequence[str]) -> bool:
    return env.run(cmd)[0] == 0


def _poll(env: LaunchEnv, pred: Callable[[], bool], what: str) -> None:
    start = env.clock()
    while not pred():
        if env.clock() - start > APPLY_WAIT:
            raise Stop(f"{what}: not visible on GitHub after {int(APPLY_WAIT)}s")
        env.sleep(5.0)


def preflight(env: LaunchEnv, ns: argparse.Namespace) -> Ctx:
    if not NAME_RE.match(ns.repo.split("/")[-1]) or ns.repo.count("/") > 1:
        raise Stop(f"not a repo name: {ns.repo!r}")
    pf = env.portfolio()
    owner = pf["owner"]
    slug = ns.repo if "/" in ns.repo else f"{owner}/{ns.repo}"
    name = slug.split("/")[1]
    if slug.split("/")[0] != owner:
        raise Stop(f"{slug} is not in {owner}'s account; launch only touches the owner's repos")
    if name in (pf.get("excluded") or []):
        raise Stop(f"{name} is excluded in policy/portfolio.yaml")
    entry = (pf.get("repos") or {}).get(name, {})
    if entry.get("data_class") == "restricted":
        raise Stop(f"{name} is data_class restricted; autopilot never runs on it")
    rc, out = env.run(["gh", "api", f"repos/{slug}"])
    repo = _json(out, {}) if rc == 0 else {}
    if not repo.get("id"):
        raise Stop(f"cannot read {slug}: does it exist, and does your gh login have access?")
    if repo.get("archived"):
        raise Stop(f"{slug} is archived")
    if not (repo.get("permissions") or {}).get("admin"):
        raise Stop(f"your gh login is not an admin of {slug}; rulesets and secrets need admin")
    if not repo.get("private", True) and not ns.allow_public:
        raise Stop(f"{slug} is public (a prompt-injection surface); pass --allow-public to launch it anyway")
    tier = ns.tier or entry.get("tier")
    mode = ns.mode or entry.get("mode")
    if tier not in ("A", "B", "C") or mode not in ("standard", "yolo", "dormant"):
        raise Stop(f"{name} is new: pass --tier A|B|C --mode standard|yolo")
    if mode == "dormant":
        raise Stop("launch enables the repo, so mode dormant makes no sense; pass --mode standard or yolo")
    kit_repo = ns.kit_repo or f"{owner}/autopilot-kit"
    return Ctx(
        slug=slug,
        owner=owner,
        name=name,
        tier=tier,
        mode=mode,
        kit_repo=kit_repo,
        kit_sha=env.approved(kit_repo),
        repo_id=int(repo["id"]),
        default_branch=repo.get("default_branch") or "main",
        token_env=ns.token_env,
    )


# --- 1 repo settings ---------------------------------------------------------------------------------------------


def _variables(env: LaunchEnv, ctx: Ctx) -> dict[str, str]:
    rc, out = env.run(["gh", "variable", "list", "-R", ctx.slug, "--json", "name,value"])
    return {v["name"]: v["value"] for v in _json(out, [])} if rc == 0 else {}


def _can_open_prs(env: LaunchEnv, ctx: Ctx) -> bool:
    rc, out = env.run(["gh", "api", f"repos/{ctx.slug}/actions/permissions/workflow"])
    return rc == 0 and _json(out, {}).get("can_approve_pull_request_reviews") is True


def settings_done(env: LaunchEnv, ctx: Ctx) -> bool:
    return _can_open_prs(env, ctx) and "AUTOPILOT_DEBUG" in _variables(env, ctx)


def settings_apply(env: LaunchEnv, ctx: Ctx) -> None:
    if not _can_open_prs(env, ctx):
        _out(
            env,
            ["gh", "api", "--method", "PUT", f"repos/{ctx.slug}/actions/permissions/workflow",
             "-F", "can_approve_pull_request_reviews=true", "-f", "default_workflow_permissions=read"],
        )  # fmt: skip
    if "AUTOPILOT_DEBUG" not in _variables(env, ctx):
        _out(env, ["gh", "variable", "set", "AUTOPILOT_DEBUG", "--body", "false", "-R", ctx.slug])


# --- 2 labels ----------------------------------------------------------------------------------------------------


def _labels(env: LaunchEnv, ctx: Ctx) -> set[str]:
    rc, out = env.run(["gh", "label", "list", "-R", ctx.slug, "--json", "name", "--limit", "200"])
    return {x["name"] for x in _json(out, [])} if rc == 0 else set()


def labels_done(env: LaunchEnv, ctx: Ctx) -> bool:
    return set(LABELS) <= _labels(env, ctx)


def labels_apply(env: LaunchEnv, ctx: Ctx) -> None:
    have = _labels(env, ctx)
    for name, (color, desc) in LABELS.items():
        if name not in have:
            _out(env, ["gh", "label", "create", name, "-R", ctx.slug, "--color", color, "--description", desc])


# --- 3 scaffold --------------------------------------------------------------------------------------------------


def scaffolded(env: LaunchEnv, ctx: Ctx) -> bool:
    return _ok(env, ["gh", "api", f"repos/{ctx.slug}/contents/.autopilot/manifest.json?ref={ctx.default_branch}"])


def _wait_scaffold_checks(env: LaunchEnv, repo: str, number: str, url: str) -> None:
    """A brand-new repo may have no CI at all; the scaffold is deterministic from the approved kit sha, so no checks is fine.
    A failing check is not."""
    start = env.clock()
    while True:
        _, out = env.run(["gh", "pr", "checks", number, "--repo", repo, "--json", "name,bucket"])
        checks = _json(out, [])
        if any(c.get("bucket") in ship.BAD_BUCKETS for c in checks):
            raise Stop(f"{url}: checks failed: {[c['name'] for c in checks if c.get('bucket') in ship.BAD_BUCKETS]}")
        if checks and all(c.get("bucket") in ship.OK_BUCKETS for c in checks):
            return
        if not checks and env.clock() - start > ship.NO_CHECKS_GRACE:
            return
        if env.clock() - start > env.timeout:
            raise Stop(f"{url}: checks still pending after {int(env.timeout // 60)} minutes")
        env.sleep(ship.POLL)


def _open_pr_for(env: LaunchEnv, repo: str, head: str) -> str | None:
    rc, out = env.run(["gh", "pr", "list", "-R", repo, "--head", head, "--state", "open", "--json", "url", "--limit", "1"])
    found = _json(out, []) if rc == 0 else []
    return found[0]["url"] if found else None


def scaffold_apply(env: LaunchEnv, ctx: Ctx) -> None:
    url = _open_pr_for(env, ctx.slug, INIT_BRANCH) or env.scaffold(env, ctx)
    repo, number = ship._split_url(url)
    _wait_scaffold_checks(env, repo, number, url)
    _out(env, ["gh", "pr", "merge", number, "--repo", repo, "--merge", "--admin"])
    _poll(env, lambda: scaffolded(env, ctx), "scaffold on the default branch")


def real_scaffold(env: LaunchEnv, ctx: Ctx) -> str:
    from . import cli

    dest = Path(tempfile.mkdtemp(prefix="ap-launch-")) / ctx.name
    _out(env, ["gh", "repo", "clone", ctx.slug, str(dest)])
    rc = cli.cmd_init(
        argparse.Namespace(
            repo=str(dest),
            tier=ctx.tier,
            mode=ctx.mode,
            kit=f"{ctx.kit_repo}@{ctx.kit_sha}",
            allow_sensitive=False,
            dry_run=False,
        )
    )
    if rc:
        raise Stop("scaffold refused (reason printed above); nothing was pushed")
    g = ["git", "-C", str(dest)]
    _out(env, [*g, "add", "-A"])
    _out(env, [*g, "commit", "-q", "-S", "-m", "autopilot: scaffold on the shared kit"])
    rc, _ = env.run([*g, "push", "-q", "-u", "origin", INIT_BRANCH])
    if rc:
        raise Stop(f"could not push {INIT_BRANCH} (does the branch already exist without a PR? delete it on GitHub and re-run)")
    body = (
        f"Thin caller workflows pinned to `{ctx.kit_repo}@{ctx.kit_sha}`, plus config, constitution and deny rules. "
        "Nothing runs until the repo is enabled.\n\n\U0001f916 Generated with [Claude Code](https://claude.com/claude-code)"
    )
    out = _out(
        env,
        ["gh", "pr", "create", "-R", ctx.slug, "--base", ctx.default_branch, "--head", INIT_BRANCH,
         "--title", "autopilot: scaffold on the shared kit", "--body", body],
    )  # fmt: skip
    return out.splitlines()[-1].strip()


# --- 4 secret ----------------------------------------------------------------------------------------------------


def _secrets(env: LaunchEnv, ctx: Ctx) -> set[str]:
    rc, out = env.run(["gh", "secret", "list", "-R", ctx.slug, "--json", "name"])
    return {x["name"] for x in _json(out, [])} if rc == 0 else set()


def secret_done(env: LaunchEnv, ctx: Ctx) -> bool:
    return SECRET in _secrets(env, ctx)


def secret_apply(env: LaunchEnv, ctx: Ctx) -> None:
    if ctx.token_env:
        token = os.environ.get(ctx.token_env, "")
        if not token:
            raise Stop(f"--token-env {ctx.token_env} is not set in your environment")
    else:
        token = env.secret(f"{SECRET} (from `claude setup-token`; input is hidden): ")
    token = token.strip()
    if not token:
        raise Stop("empty token; nothing was set")
    rc, _ = env.run_in(["gh", "secret", "set", SECRET, "-R", ctx.slug], token)
    if rc:
        raise Stop(f"gh secret set failed for {ctx.slug}")


STAGES = [
    Stage("repo settings", settings_done, settings_apply),
    Stage("labels", labels_done, labels_apply),
    Stage("scaffold merged", scaffolded, scaffold_apply),
    Stage("token secret", secret_done, secret_apply),
]


@dataclass
class Report:
    rows: list[tuple[str, bool, str]] = field(default_factory=list)

    @property
    def green(self) -> bool:
        return all(ok for _, ok, _ in self.rows)


def launch(env: LaunchEnv, ns: argparse.Namespace) -> Report:
    ctx = preflight(env, ns)
    env.say(f"launch-repo: {ctx.slug} tier {ctx.tier} mode {ctx.mode}, kit {ctx.kit_repo}@{ctx.kit_sha[:7]}")
    todo = [s for s in STAGES if not s.done(env, ctx)]
    for s in STAGES:
        env.say(f"  {'todo' if s in todo else 'ok  '}  {s.name}")
    report = Report()
    if ns.dry_run or not todo:
        report.rows = [(s.name, s not in todo, "already done" if s not in todo else "would run") for s in STAGES]
        if ns.dry_run:
            env.say("dry run: nothing was changed")
        return report
    if not ns.yes and not _confirmed(env, ctx, todo):
        raise Stop("not confirmed; nothing was changed (no terminal to ask on? pass --yes)")
    for s in todo:
        env.say(f"  ...   {s.name}")
        s.apply(env, ctx)
        if not s.done(env, ctx):
            raise Stop(f"{s.name}: ran, but GitHub does not read back as done; stopping so you can look")
        env.say(f"  done  {s.name}")
    report.rows = [(s.name, s.done(env, ctx), "") for s in STAGES]
    return report


def _confirmed(env: LaunchEnv, ctx: Ctx, todo: list[Stage]) -> bool:
    try:
        answer = env.ask(f"Run {len(todo)} stage(s) on {ctx.slug}, including merging PRs with your admin login? [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() == "y"


def print_report(env: LaunchEnv, report: Report) -> int:
    env.say("")
    for name, ok, note in report.rows:
        env.say(f"  {'ok ' if ok else 'RED'}  {name}{('  ' + note) if note else ''}")
    if report.green:
        env.say("\nlaunched. Next: write specs/ or open issues labelled agent-ready, and fill in the charter issue.")
    return 0 if report.green else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="launch-repo", description=__doc__.split("\n\n")[0])
    ap.add_argument("repo", help="repo name (or owner/name)")
    ap.add_argument("--tier", choices=["A", "B", "C"])
    ap.add_argument("--mode", choices=["standard", "yolo"])
    ap.add_argument("--kit-repo")
    ap.add_argument("--token-env", help="name of an environment variable holding the token (otherwise a hidden prompt)")
    ap.add_argument("--allow-public", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--timeout-minutes", type=int, default=20)
    ns = ap.parse_args(argv)
    env = LaunchEnv(run=sh, timeout=ns.timeout_minutes * 60.0)
    try:
        return print_report(env, launch(env, ns))
    except Stop as e:
        env.say(f"STOPPED: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
