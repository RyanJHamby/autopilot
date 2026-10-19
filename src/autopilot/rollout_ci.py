"""`ap rollout --ci`: the pin-bump PRs of a rollout, opened unattended by a dedicated GitHub App (`autopilot-rollout`).

This App is deliberately NOT the release App: different token variable, different installation, different job.
Hard rules, each enforced in the client as well as in the callers:
- It opens PRs and never merges anything. Each downstream repo's own automerge (class kit-bump) merges its bump. Any request
  whose path mentions a merge is refused by the client, and DELETE is never sent.
- REST only (stdlib urllib, injected transport), authenticated by ROLLOUT_TOKEN, the App installation token. No other token
  variable is read; the release token must never be usable here.
- Commits go through the contents API WITHOUT author/committer fields, so GitHub signs them. Branches are created, never moved.
- Runs only for a 40-hex kit sha that is on the owner's autopilot-kit APPROVED list; otherwise it refuses everything.
- One repo failing never stops the others, but the exit code is then 1.
"""

from __future__ import annotations

import base64
import os
import re
import sys
import urllib.request
from collections.abc import Callable

from autopilot import cli
from autopilot.release_ci import CIError, GitHub, branch_head, default_branch, open_pr, put_file, tree_entries

TOKEN_ENV = "ROLLOUT_TOKEN"


class RolloutGitHub(GitHub):
    """The release client, narrowed further: no merge endpoint, no DELETE, writes only to the portfolio repos."""

    def _guard(self, method: str, url: str, body: dict | None) -> None:
        path = url.split("?")[0]
        if method == "DELETE":
            raise CIError("rollout never deletes anything")
        if method != "GET" and (
            (path.endswith("/merge") and "/contents/" not in path) or re.search(r"/pulls/\d+/(merge|update-branch|reviews)", path)
        ):
            raise CIError("rollout never merges, approves or updates a PR; the downstream repo's own automerge does that")
        if method == "PUT" and "/contents/" not in path:
            raise CIError("the only PUT rollout sends is a contents write")
        if method == "POST" and not re.search(r"/(git/refs|pulls)$", path):
            raise CIError("the only POSTs rollout sends create a branch or a PR")
        super()._guard(method, url, body)


def make_client(portfolio_slugs, http: Callable | None = None) -> RolloutGitHub:
    token = os.environ.get(TOKEN_ENV, "")
    if not token:
        raise CIError(f"{TOKEN_ENV} (the autopilot-rollout App installation token) is not set")
    return RolloutGitHub(token=token, http=http, write_repos=set(portfolio_slugs))


def anonymous_opener(url: str) -> str:
    """Read APPROVED without any credential: the approvals repo is public, and this App is not installed on it."""
    h = {"Accept": "application/vnd.github.raw+json", "User-Agent": "autopilot-rollout-ci"}
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=10).read().decode()


def _read_files(c: GitHub, repo: str, head: str, tree: dict[str, tuple[str, str]], fetch: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in fetch:
        mode, _ = tree[p]
        if mode != "100644":
            raise CIError(f"{repo}:{p} has mode {mode}; refusing to rewrite a non-regular file")
        j = c.get_json(f"repos/{repo}/contents/{p}?ref={head}")
        if not isinstance(j, dict) or j.get("encoding") != "base64":
            raise CIError(f"cannot read {repo}:{p}")
        try:
            out[p] = base64.b64decode(j.get("content", "")).decode()
        except (ValueError, UnicodeDecodeError) as e:
            raise CIError(f"{repo}:{p} is not valid text") from e
    return out


def _existing_pr(c: GitHub, repo: str, branch: str) -> bool:
    owner = repo.split("/")[0]
    prs = c.get_json(f"repos/{repo}/pulls?state=all&per_page=5&head={owner}:{branch}")
    if not isinstance(prs, list):
        raise CIError(f"unexpected PR list in {repo}")
    return bool(prs)


def _branch_exists(c: GitHub, repo: str, branch: str) -> bool:
    status, _ = c.request("GET", f"repos/{repo}/git/ref/heads/{branch}")
    if status == 200:
        return True
    if status == 404:
        return False
    raise CIError(f"GET ref {branch} in {repo} -> HTTP {status}")


def bump_repo(c: GitHub, slug: str, entry: dict, kit: str, sha: str, apply: bool) -> str:
    """One repo. Returns a one-line outcome; raises CIError when this repo must be reported as failed."""
    base = default_branch(c, slug)
    head = branch_head(c, slug, base)
    tree = tree_entries(c, slug, head)
    tier, mode = entry.get("tier", "B"), entry.get("mode", "standard")
    fetch, present = cli.bump_inputs(list(tree), kit, sha, tier, mode)
    files = _read_files(c, slug, head, tree, fetch) | {p: "" for p in present}
    if "autopilot-kit" not in files.get(".github/workflows/agent-exec.yml", ""):
        return "not on the shared kit yet; migrate it with `ap init --kit` first (rollout only bumps pins); skipped"
    changes = cli.bump_files(files, kit, sha, tier, mode)
    if not changes:
        return f"already on {sha[:7]}"
    if any(v is None for v in changes.values()):
        raise CIError("the bump needs file deletions (an old copy-mode install); run the local `ap rollout` for this repo")
    branch = cli._rollout_branch(sha)
    if _branch_exists(c, slug, branch):
        if _existing_pr(c, slug, branch):
            return f"{branch} already has a PR; skipped"
        raise CIError(f"branch {branch} exists but has no PR; not touching it (delete it or open the PR by hand)")
    if not apply:
        return f"[dry run] would open a pin-bump PR -> {sha[:7]} ({len(changes)} file(s))"
    c.write("POST", f"repos/{slug}/git/refs", {"ref": f"refs/heads/{branch}", "sha": head}, ok=(201,))
    for p, content in sorted(changes.items()):
        put_file(c, slug, branch, p, content.encode(), tree[p][1] if p in tree else None, f"autopilot: bump kit to {sha[:7]}")
    url = open_pr(
        c,
        slug,
        branch,
        base,
        f"autopilot: bump kit to {sha[:7]}",
        f"Pin bump to the owner-approved kit `{sha}`. Auto-merges after checks if this repo has the `kit-bump` class; otherwise yours to review.",
    )
    return url


def run(ns, client: GitHub | None = None, *, portfolio: dict | None = None, approved: list[str] | None = None) -> int:
    """Exit 0 = every selected repo is done or intentionally skipped; 1 = refusal or any repo failed."""
    m = re.fullmatch(r"([\w.-]+/[\w.-]+)@([0-9a-f]{40})", getattr(ns, "kit", "") or "")
    if not m:
        print("rollout --ci: --kit must look like OWNER/REPO@<40-hex sha>", file=sys.stderr)
        return 1
    kit, sha = m.groups()
    pf = portfolio if portfolio is not None else cli.load_portfolio()
    owner = pf["owner"]
    if kit != f"{owner}/autopilot-kit":
        print(f"rollout --ci: refusing: the kit must be {owner}/autopilot-kit, not {kit}", file=sys.stderr)
        return 1
    if approved is None:
        approved = cli._load_runtime("automerge").fetch_approved(kit, opener=anonymous_opener)
    if sha not in approved:
        print(f"rollout --ci: refusing: {sha[:7]} is not on {kit}'s APPROVED list", file=sys.stderr)
        return 1
    apply = bool(getattr(ns, "apply", False))
    targets = []
    for name, e in cli.rollout_candidates(pf, getattr(ns, "only", None)):
        if cli._load_runtime_picker_held(e):
            print(f"{name}: held by the owner until {e['hold_until']}; skipped")
            continue
        targets.append((name, cli._slug(name, owner), e))
    try:
        c = client or make_client(s for _, s, _ in targets)
    except CIError as e:
        print(f"rollout --ci: failing closed: {e}", file=sys.stderr)
        return 1
    failed = []
    for name, slug, e in targets:
        try:
            print(f"{slug}: {bump_repo(c, slug, e, kit, sha, apply)}")
        except Exception as ex:  # noqa: BLE001 - one repo's failure (API error, odd shape) must not stop the others
            failed.append(slug)
            print(f"{slug}: FAILED: {ex}", file=sys.stderr)
    if failed:
        print(f"rollout --ci: {len(failed)} repo(s) failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0
