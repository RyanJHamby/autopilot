"""ship-kit: one command from a committed kit branch to merged bump PRs.

Run by the owner, as the owner (their `gh` login). Running it is the deliberate act: it shows what it will ship and asks
once (`--yes` skips the question). It never runs on its own and it stops on the first red check.

  1. preflight: signed commits only, clean tree, on top of origin/main, changes only under kit/, tests/ and docs/, at least one in kit/
  2. the test suite
  3. push the branch (never force), open or reuse the PR, wait for green, merge it with the owner's admin bypass
  4. watch the release workflow the merge starts
  5. for each bump PR the release opened: check it is the rollout App's, on an `autopilot/kit-bump-<sha>` branch for the sha
     just approved, wait for green, and merge it pinned to the head it checked, unless the downstream automerge already did

Only `gh pr ...`, `gh run ...`, `gh repo view` and `git` run here. Nothing is merged except the PR it opened and the bump PRs
it verified. A red check leaves the PR open and the exit code non-zero.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

ALLOWED_PREFIXES = ("kit/", "tests/", "docs/")
BUMP_HEAD = re.compile(r"^autopilot/kit-bump-([0-9a-f]{7,40})$")
BUMP_AUTHORS = frozenset({"app/autopilot-rollout", "autopilot-rollout[bot]"})
PR_URL = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)$")
KIT_SHA_LINE = re.compile(r"\bkit_sha=([0-9a-f]{40})\b")
BUMP_LINE = re.compile(r"[\w.-]+/[\w.-]+: (https://github\.com/[\w.-]+/[\w.-]+/pull/\d+)")

POLL = 10.0
NO_CHECKS_GRACE = 120.0
RUN_APPEARS_TIMEOUT = 180.0
OK_BUCKETS = ("pass", "skipping")
BAD_BUCKETS = ("fail", "cancel")

Run = Callable[[Sequence[str]], tuple[int, str]]


class Stop(Exception):
    """A reason to stop that the owner should read. Nothing past the stopping point has run."""


@dataclass
class Env:
    run: Run
    say: Callable[[str], None] = print
    ask: Callable[[str], str] = input
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    timeout: float = 20 * 60.0


@dataclass
class Result:
    shipped: list[str] = field(default_factory=list)
    left_open: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def sh(cmd: Sequence[str]) -> tuple[int, str]:
    p = subprocess.run(list(cmd), capture_output=True, text=True)
    return p.returncode, p.stdout


def _json(text: str, default):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return default


def _out(env: Env, cmd: Sequence[str]) -> str:
    rc, out = env.run(cmd)
    if rc != 0:
        raise Stop(f"`{' '.join(cmd)}` failed (exit {rc})")
    return out.strip()


def _split_url(url: str) -> tuple[str, str]:
    m = PR_URL.match(url)
    if not m:
        raise Stop(f"not a pull request URL: {url!r}")
    return f"{m.group(1)}/{m.group(2)}", m.group(3)


def preflight(env: Env) -> tuple[str, list[str]]:
    branch = _out(env, ["git", "branch", "--show-current"])
    if not branch or branch == "main":
        raise Stop("run this from a branch with your kit change committed, not from main")
    if _out(env, ["git", "status", "--porcelain", "--untracked-files=no"]):
        raise Stop("working tree has uncommitted changes; commit them (signed) or stash them first")
    _out(env, ["git", "fetch", "origin", "main"])
    if env.run(["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"])[0] != 0:
        raise Stop("branch is not on top of origin/main; update it from main first")
    files = [f for f in _out(env, ["git", "diff", "--name-only", "origin/main...HEAD"]).splitlines() if f]
    if not files:
        raise Stop("no changes against origin/main")
    outside = [f for f in files if not f.startswith(ALLOWED_PREFIXES)]
    if outside:
        raise Stop(f"ship-kit only ships kit/, tests/ and docs/ changes; also touched: {outside[:5]}")
    if not any(f.startswith("kit/") for f in files):
        raise Stop("no kit/ file changed; there is nothing to release")
    for line in _out(env, ["git", "log", "--format=%H %G?", "origin/main..HEAD"]).splitlines():
        sha, _, sig = line.partition(" ")
        if sig != "G":
            raise Stop(f"commit {sha[:7]} is not signed with a good signature (status {sig!r}); sign it, never skip signing")
    return branch, files


def run_tests(env: Env) -> None:
    rc, out = env.run(["env", "PYTHONPATH=src", "uv", "run", "python", "-m", "pytest", "-q"])
    if rc != 0:
        tail = "\n".join(out.strip().splitlines()[-15:])
        raise Stop(f"tests failed; nothing was pushed\n{tail}")


def wait_checks(env: Env, repo: str, number: str, what: str) -> None:
    start = env.clock()
    while True:
        _, out = env.run(["gh", "pr", "checks", number, "--repo", repo, "--json", "name,bucket"])
        checks = _json(out, [])
        if checks:
            bad = [c["name"] for c in checks if c.get("bucket") in BAD_BUCKETS]
            if bad:
                raise Stop(f"{what}: checks failed: {bad}")
            if all(c.get("bucket") in OK_BUCKETS for c in checks):
                return
        elif env.clock() - start > NO_CHECKS_GRACE:
            raise Stop(f"{what}: no checks reported after {int(NO_CHECKS_GRACE)}s")
        if env.clock() - start > env.timeout:
            raise Stop(f"{what}: checks still pending after {int(env.timeout // 60)} minutes")
        env.sleep(POLL)


def open_pr(env: Env, repo: str, branch: str) -> str:
    _out(env, ["git", "push", "-u", "origin", branch])
    rc, out = env.run(["gh", "pr", "view", branch, "--repo", repo, "--json", "number,state,url"])
    existing = _json(out, {}) if rc == 0 else {}
    if existing.get("state") == "OPEN":
        return str(existing["url"])
    title = _out(env, ["git", "log", "-1", "--format=%s"])
    body = "Kit change shipped with ship-kit: merging this starts the release workflow."
    out = _out(env, ["gh", "pr", "create", "--repo", repo, "--base", "main", "--head", branch, "--title", title, "--body", body])
    url = out.splitlines()[-1].strip() if out else ""
    _split_url(url)
    return url


def merge_kit_pr(env: Env, repo: str, number: str) -> str:
    _out(env, ["gh", "pr", "merge", number, "--repo", repo, "--merge", "--admin"])
    start = env.clock()
    while True:
        view = _json(_out(env, ["gh", "pr", "view", number, "--repo", repo, "--json", "state,mergeCommit"]), {})
        if view.get("state") == "MERGED" and (view.get("mergeCommit") or {}).get("oid"):
            return view["mergeCommit"]["oid"]
        if env.clock() - start > 120:
            raise Stop(f"PR #{number} did not report as merged within 2 minutes")
        env.sleep(POLL)


def watch_release(env: Env, repo: str, merge_sha: str) -> tuple[str, str]:
    start = env.clock()
    while True:
        rc, out = env.run(
            [
                "gh",
                "run",
                "list",
                "--repo",
                repo,
                "--workflow",
                "release",
                "--commit",
                merge_sha,
                "--json",
                "databaseId,url",
                "--limit",
                "5",
            ]
        )
        runs = _json(out, []) if rc == 0 else []
        if runs:
            run_id, url = str(runs[0]["databaseId"]), runs[0]["url"]
            break
        if env.clock() - start > RUN_APPEARS_TIMEOUT:
            raise Stop(f"the release workflow never started for {merge_sha[:7]}; look at the Actions tab")
        env.sleep(POLL)
    env.say(f"  release run {url}")
    if env.run(["gh", "run", "watch", run_id, "--repo", repo, "--exit-status", "--interval", "10"])[0] != 0:
        raise Stop(f"the release run failed: {url}")
    return run_id, url


def release_outputs(env: Env, repo: str, run_id: str) -> tuple[str | None, list[str]]:
    log = _out(env, ["gh", "run", "view", run_id, "--repo", repo, "--log"])
    m = KIT_SHA_LINE.search(log)
    urls: list[str] = []
    for u in BUMP_LINE.findall(log):
        if u not in urls:
            urls.append(u)
    return (m.group(1) if m else None), urls


def handle_bump(env: Env, owner: str, url: str, kit_sha: str, result: Result) -> None:
    try:
        repo, number = _split_url(url)
        if repo.split("/")[0] != owner:
            raise Stop(f"{url}: not in {owner}'s repos; not touching it")
        fields = "state,author,headRefName,headRefOid"
        view = _json(_out(env, ["gh", "pr", "view", number, "--repo", repo, "--json", fields]), {})
        if view.get("state") == "MERGED":
            result.shipped.append(f"{url} (merged by the repo's own automerge)")
            return
        if view.get("state") != "OPEN":
            raise Stop(f"{url}: state is {view.get('state')}")
        m = BUMP_HEAD.match(view.get("headRefName", ""))
        if (view.get("author") or {}).get("login") not in BUMP_AUTHORS or not m or not kit_sha.startswith(m.group(1)):
            raise Stop(f"{url}: not the rollout App's bump for {kit_sha[:7]}; leaving it for you")
        wait_checks(env, repo, number, url)
        view = _json(_out(env, ["gh", "pr", "view", number, "--repo", repo, "--json", fields]), {})
        if view.get("state") == "MERGED":
            result.shipped.append(f"{url} (merged by the repo's own automerge)")
            return
        if view.get("state") != "OPEN" or not BUMP_HEAD.match(view.get("headRefName", "")):
            raise Stop(f"{url}: changed while waiting; leaving it for you")
        head = view["headRefOid"]
        _out(env, ["gh", "pr", "merge", number, "--repo", repo, "--merge", "--admin", "--match-head-commit", head])
        result.shipped.append(f"{url} (merged by ship-kit at {head[:7]})")
    except Stop as e:
        result.left_open.append(str(e))


def report_superseded(env: Env, repos: list[str], keep: list[str], result: Result) -> None:
    for repo in repos:
        rc, out = env.run(
            ["gh", "pr", "list", "--repo", repo, "--state", "open", "--json", "number,headRefName,url", "--limit", "50"]
        )
        for pr in _json(out, []) if rc == 0 else []:
            if BUMP_HEAD.match(pr.get("headRefName", "")) and pr["url"] not in keep:
                result.notes.append(f"older bump PR still open: {pr['url']}  (close: gh pr close {pr['number']} --repo {repo})")


def confirmed(env: Env, n_files: int) -> bool:
    """Only an explicit "y" counts. No terminal to ask on (EOF) is a no, never a crash and never a yes."""
    try:
        answer = env.ask(f"Push, merge to main with admin bypass, and release? {n_files} file(s) [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() == "y"


def ship(env: Env, *, assume_yes: bool, dry_run: bool) -> Result:
    result = Result()
    branch, files = preflight(env)
    repo = _out(env, ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"])
    owner = repo.split("/")[0]
    env.say(f"ship-kit: branch {branch} -> {repo}")
    env.say(_out(env, ["git", "diff", "--stat", "origin/main...HEAD"]))
    run_tests(env)
    env.say("tests pass")
    if dry_run:
        env.say("dry run: stopping before the push")
        return result
    if not assume_yes and not confirmed(env, len(files)):
        raise Stop("not confirmed; nothing was pushed (no terminal to ask on? pass --yes)")
    url = open_pr(env, repo, branch)
    pr_repo, number = _split_url(url)
    env.say(f"PR {url}")
    wait_checks(env, pr_repo, number, "kit PR")
    merge_sha = merge_kit_pr(env, pr_repo, number)
    result.shipped.append(f"{url} (merged at {merge_sha[:7]})")
    run_id, run_url = watch_release(env, repo, merge_sha)
    kit_sha, bump_urls = release_outputs(env, repo, run_id)
    if not kit_sha:
        result.notes.append(f"release run {run_url} published nothing new (the kit tree was unchanged)")
        return result
    result.notes.append(f"approved kit sha {kit_sha}")
    for bump in bump_urls:
        env.say(f"bump PR {bump}")
        handle_bump(env, owner, bump, kit_sha, result)
    own = sorted({_split_url(b)[0] for b in bump_urls if PR_URL.match(b) and _split_url(b)[0].split("/")[0] == owner})
    report_superseded(env, own, bump_urls, result)
    return result


def print_result(env: Env, result: Result) -> int:
    env.say("")
    for line in result.shipped:
        env.say(f"  done:  {line}")
    for line in result.notes:
        env.say(f"  note:  {line}")
    for line in result.left_open:
        env.say(f"  OPEN:  {line}")
    return 1 if result.left_open else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ship-kit", description=__doc__.split("\n\n")[0])
    ap.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    ap.add_argument("--dry-run", action="store_true", help="run the preflight and the tests, then stop before pushing")
    ap.add_argument("--timeout-minutes", type=int, default=20, help="how long to wait on any one set of checks")
    ns = ap.parse_args(argv)
    env = Env(run=sh, timeout=ns.timeout_minutes * 60.0)
    try:
        return print_result(env, ship(env, assume_yes=ns.yes, dry_run=ns.dry_run))
    except Stop as e:
        env.say(f"STOPPED: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
