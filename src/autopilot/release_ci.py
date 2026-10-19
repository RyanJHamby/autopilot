"""`ap release --ci`: the release runs unattended as a GitHub App, merging only what it has just verified.

Flow after a human merged a kit/** change to autopilot main:
    kit PR (contents API) -> verified kit merge -> approval PR -> provenance check run -> verified approval merge.
Rollout stays a separate manual command (the App is not installed on the downstream repos).

Hard rules, each enforced in the client as well as in the callers, so a bug in one cannot defeat the other:
- REST only (stdlib urllib, injected transport), authenticated by GH_TOKEN, the App installation token.
- Commits are made through the contents API WITHOUT author/committer fields, so GitHub signs them.
- Writes go only to the kit repo and the approvals repo; branches are created, never moved.
- A merge request is sent only with `sha=<verified head sha>` and merge_method=merge, after the checks in
  merge_kit_pr / merge_approval_pr passed. Any API error, odd shape, timeout or mismatch raises and the run exits 1.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from autopilot import cli
from autopilot import provenance as prov
from autopilot import provenance_ci as pci

API = "https://api.github.com"
HEX40 = prov.HEX40
MAX_STEPS = 6  # actions per run; the real flow needs 4 (open kit PR, merge, open approval PR, merge)
CHECK_TIMEOUT = 600.0  # seconds to wait for the provenance check run
CHECK_DELAY, CHECK_DELAY_MAX = 5.0, 60.0
CHECK_NAME = "provenance"
CHECK_APP = "github-actions"
APPROVED_FILE = "APPROVED"


class CIError(cli.ReleaseError):
    """Refusal or failure; the run stops and exits 1."""


# --- REST client --------------------------------------------------------------------------------------------------------


def _default_http(method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, OSError) as e:
        raise CIError(f"{method} {url}: {e}") from e


class GitHub:
    """Minimal REST client. `http(method, url, headers, body) -> (status, bytes)` is looked up at call time, so tests (and
    monkeypatching the module default) take effect after construction."""

    def __init__(self, token: str | None = None, http: Callable | None = None, api: str = API, write_repos=None):
        self.token = os.environ.get("GH_TOKEN", "") if token is None else token
        if not self.token:
            raise CIError("GH_TOKEN (the App installation token) is not set")
        self._http = http
        self.api = api
        self.write_repos = set(write_repos) if write_repos is not None else None

    def _guard(self, method: str, url: str, body: dict | None) -> None:
        if method not in ("GET", "POST", "PUT", "DELETE"):
            raise CIError(f"method {method} not allowed")
        if not url.startswith(self.api + "/"):
            raise CIError(f"refusing request outside {self.api}")
        if method == "GET":
            return
        m = re.match(re.escape(self.api) + r"/repos/([\w.-]+/[\w.-]+)/", url)
        if not m or (self.write_repos is not None and m.group(1) not in self.write_repos):
            raise CIError(f"refusing to write to {url}")
        body = body or {}
        if any("force" in k.lower() for k in body):
            raise CIError("refusing a request with a force flag")
        path = url.split("?")[0]
        if "/contents/" in path and ({"author", "committer"} & set(body)):
            raise CIError("contents writes must not set author/committer (GitHub signs the commit only when it chooses them)")
        if path.endswith("/merge"):
            if not (method == "PUT" and set(body) == {"sha", "merge_method"}):
                raise CIError("a merge request must be exactly PUT {sha, merge_method}")
            if not HEX40.fullmatch(str(body["sha"])) or body["merge_method"] != "merge":
                raise CIError("a merge request must pin a 40-hex sha and use merge_method=merge")

    def request(self, method: str, path: str, body: dict | None = None) -> tuple[int, object]:
        url = path if path.startswith("https://") else f"{self.api}/{path.lstrip('/')}"
        self._guard(method, url, body)
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "autopilot-release-ci",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        http = self._http if self._http is not None else _default_http  # call-time binding
        status, raw = http(method, url, headers, data)
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = None
        return status, parsed

    def get_json(self, path: str):
        """Doubles as the `gh` argument of cli.gather_release_state: JSON or ReleaseError."""
        status, j = self.request("GET", path)
        if status != 200 or j is None:
            raise CIError(f"GET {path} -> HTTP {status}")
        return j

    def opener(self, url: str) -> tuple[int, bytes]:
        """GET in the (status, bytes) shape provenance_ci.changed_files expects."""
        status, j = self.request("GET", url)
        return status, json.dumps(j).encode() if j is not None else b""

    def write(self, method: str, path: str, body: dict, ok: tuple[int, ...]) -> dict:
        status, j = self.request(method, path, body)
        if status not in ok or not isinstance(j, dict):
            msg = j.get("message") if isinstance(j, dict) else ""
            raise CIError(f"{method} {path} -> HTTP {status} {msg or ''}".strip())
        return j


# --- reading ------------------------------------------------------------------------------------------------------------


def managed(path: str) -> bool:
    """Paths export_kit owns in the kit repo; everything else there stays untouched."""
    return path == "README.md" or path.startswith(".github/workflows/") or path.startswith("runtime/")


def render_kit() -> dict[str, bytes]:
    with tempfile.TemporaryDirectory(prefix="ap-release-ci-") as td:
        files = cli.export_kit(Path(td))
        return {rel: (Path(td) / rel).read_bytes() for rel in files}


def default_branch(c: GitHub, repo: str) -> str:
    j = c.get_json(f"repos/{repo}")
    b = j.get("default_branch") if isinstance(j, dict) else None
    if not isinstance(b, str) or not b:
        raise CIError(f"cannot read the default branch of {repo}")
    return b


def branch_head(c: GitHub, repo: str, branch: str) -> str:
    j = c.get_json(f"repos/{repo}/git/ref/heads/{branch}")
    sha = j.get("object", {}).get("sha") if isinstance(j, dict) else None
    if not isinstance(sha, str) or not HEX40.fullmatch(sha):
        raise CIError(f"cannot resolve {repo}@{branch}")
    return sha


def tree_entries(c: GitHub, repo: str, ref: str) -> dict[str, tuple[str, str]]:
    """{path: (mode, blob sha)} of a commit's whole tree. Truncated lists and non-file entries are refused."""
    t = c.get_json(f"repos/{repo}/git/trees/{ref}?recursive=1")
    if not isinstance(t, dict) or t.get("truncated") or not isinstance(t.get("tree"), list):
        raise CIError(f"tree of {repo}@{ref} unavailable or truncated")
    out: dict[str, tuple[str, str]] = {}
    for e in t["tree"]:
        if e.get("type") == "tree":
            continue
        if e.get("type") != "blob" or not isinstance(e.get("path"), str):
            raise CIError(f"unexpected tree entry in {repo}@{ref}: {e.get('path')!r} ({e.get('type')})")
        out[e["path"]] = (e.get("mode"), e.get("sha"))
    return out


def find_open_pr(c: GitHub, repo: str, branch: str, base_branch: str) -> dict:
    owner = repo.split("/")[0]
    prs = c.get_json(f"repos/{repo}/pulls?state=open&per_page=5&head={owner}:{branch}")
    if not isinstance(prs, list) or len(prs) != 1:
        raise CIError(f"expected exactly one open PR from {branch} in {repo}")
    pr = prs[0]
    try:
        number, head, ref = pr["number"], pr["head"]["sha"], pr["head"]["ref"]
        head_repo, base = pr["head"]["repo"]["full_name"], pr["base"]["ref"]
    except (KeyError, TypeError) as e:
        raise CIError(f"unexpected PR shape in {repo}") from e
    if not (
        isinstance(number, int) and HEX40.fullmatch(str(head)) and ref == branch and head_repo == repo and base == base_branch
    ):
        raise CIError(f"PR for {branch} in {repo} is not a same-repo PR from that branch to {base_branch}")
    return pr


def require_fast_forward(c: GitHub, repo: str, base_sha: str, head: str) -> None:
    """The merge result must equal the head tree: the head is ahead of the base tip and not behind it."""
    j = c.get_json(f"repos/{repo}/compare/{base_sha}...{head}")
    if not isinstance(j, dict) or j.get("status") != "ahead" or j.get("behind_by") != 0:
        raise CIError(
            f"{repo}: PR head is not strictly ahead of the base tip; refusing (the merge could differ from what was verified)"
        )


def file_text(c: GitHub, repo: str, path: str, ref: str) -> tuple[str, str]:
    """(text, blob sha) of one file at a ref."""
    j = c.get_json(f"repos/{repo}/contents/{path}?ref={ref}")
    if not isinstance(j, dict) or j.get("encoding") != "base64" or not isinstance(j.get("sha"), str):
        raise CIError(f"cannot read {repo}:{path}@{ref}")
    try:
        return base64.b64decode(j.get("content", "")).decode(), j["sha"]
    except (ValueError, UnicodeDecodeError) as e:
        raise CIError(f"{repo}:{path} is not valid text") from e


# --- writing ------------------------------------------------------------------------------------------------------------


def create_branch(c: GitHub, repo: str, branch: str, sha: str) -> None:
    """Plain create. A branch that already exists makes GitHub answer 422, which stops the run (never moved or overwritten)."""
    c.write("POST", f"repos/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": sha}, ok=(201,))


def put_file(c: GitHub, repo: str, branch: str, path: str, data: bytes, old_sha: str | None, message: str) -> None:
    body = {"message": message, "content": base64.b64encode(data).decode(), "branch": branch}
    if old_sha:
        body["sha"] = old_sha
    c.write("PUT", f"repos/{repo}/contents/{path}", body, ok=(200, 201))


def open_pr(c: GitHub, repo: str, head: str, base: str, title: str, body: str) -> str:
    j = c.write("POST", f"repos/{repo}/pulls", {"title": title, "head": head, "base": base, "body": body}, ok=(201,))
    return str(j.get("html_url", ""))


def open_kit_pr(c: GitHub, ns, render: dict[str, bytes], source: str) -> str:
    """Mirror `render` into the kit repo on ns.branch and open the PR. Returns "" when the kit repo already matches."""
    kit = ns.kit_repo
    base = default_branch(c, kit)
    base_sha = branch_head(c, kit, base)
    base_tree = tree_entries(c, kit, base_sha)
    puts = [
        (p, data, base_tree[p][1] if p in base_tree else None)
        for p, data in sorted(render.items())
        if base_tree.get(p) != ("100644", cli._blob_sha(data))
    ]
    deletes = [(p, base_tree[p][1]) for p in sorted(base_tree) if managed(p) and p not in render]
    if not puts and not deletes:
        return ""
    create_branch(c, kit, ns.branch, base_sha)
    for p, data, old in puts:
        put_file(c, kit, ns.branch, p, data, old, f"release: mirror {p} from autopilot {source[:7]}")
    for p, old in deletes:
        c.write(
            "DELETE",
            f"repos/{kit}/contents/{p}",
            {"message": f"release: remove {p} (not in autopilot {source[:7]} kit/)", "sha": old, "branch": ns.branch},
            ok=(200,),
        )
    body = (
        f"Mirror of `kit/` from autopilot `{source}`, exported by `ap release --ci`.\n\n"
        "The release job merges this PR only after re-reading its head tree and finding it identical to the export, "
        "and pins the merge to that head sha."
    )
    return open_pr(c, kit, ns.branch, base, f"release: mirror autopilot kit ({ns.branch})", body)


def verify_kit_head(head: dict[str, tuple[str, str]], base: dict[str, tuple[str, str]], render: dict[str, bytes]) -> list[str]:
    """Every difference between the PR head tree and (the export render over the base tip). Empty = safe to merge."""
    bad: list[str] = []
    want = {p: ("100644", cli._blob_sha(b)) for p, b in render.items()}
    for p in sorted(set(head) | set(want) | set(base)):
        if managed(p):
            if head.get(p) != want.get(p):
                bad.append(f"{p}: head has {head.get(p)}, export has {want.get(p)}")
        elif head.get(p) != base.get(p):
            bad.append(f"{p}: outside the managed paths but differs from the base branch")
    return bad


def merge_pr(c: GitHub, repo: str, number: int, head_sha: str) -> None:
    """The only merge call in this module. Callers must have verified `head_sha` first."""
    if not HEX40.fullmatch(head_sha):
        raise CIError("merge needs a verified head sha")
    j = c.write("PUT", f"repos/{repo}/pulls/{number}/merge", {"sha": head_sha, "merge_method": "merge"}, ok=(200,))
    if j.get("merged") is not True:
        raise CIError(f"{repo}#{number} was not merged: {j.get('message', '')}")


def merge_kit_pr(c: GitHub, ns, render: dict[str, bytes]) -> str:
    kit = ns.kit_repo
    base = default_branch(c, kit)
    pr = find_open_pr(c, kit, ns.branch, base)
    head = pr["head"]["sha"]
    base_sha = branch_head(c, kit, base)
    bad = verify_kit_head(tree_entries(c, kit, head), tree_entries(c, kit, base_sha), render)
    if bad:
        raise CIError("kit PR head tree differs from the export; not merging: " + "; ".join(bad[:5]))
    require_fast_forward(c, kit, base_sha, head)
    merge_pr(c, kit, pr["number"], head)
    return f"merged kit PR #{pr['number']} at head {head[:7]}"


def approval_line(sha: str, ns, source: str) -> str:
    """Same shape `ap approve` writes: `<sha>  release <branch> source=<source>`."""
    return f"{sha}  " + " ".join(f"release {ns.branch} source={source}".split())


def open_approval_pr(c: GitHub, ns, sha: str, source: str) -> str:
    if not HEX40.fullmatch(sha) or not HEX40.fullmatch(source):
        raise CIError("approval needs a 40-hex kit sha and source")
    repo = cli._load_runtime("automerge").approvals_repo(ns.kit_repo)
    base = default_branch(c, repo)
    base_sha = branch_head(c, repo, base)
    text, blob = file_text(c, repo, APPROVED_FILE, base_sha)
    if sha in text:
        raise CIError(f"{sha[:7]} is already on APPROVED; not adding it again")
    line = approval_line(sha, ns, source)
    new = text.rstrip("\n") + f"\n{line}\n"
    bad = prov.verify_approved_diff(text, new)
    if bad:
        raise CIError("APPROVED edit would not be append-only: " + "; ".join(bad))
    branch = cli._approve_branch(sha)
    create_branch(c, repo, branch, base_sha)
    put_file(c, repo, branch, APPROVED_FILE, new.encode(), blob, f"approve kit {sha[:7]}")
    body = (
        f"Approves `{sha}` for automatic pin bumps (kit-bump class).\n\nAdds exactly: `{line}`\n\n"
        "Opened by `ap release --ci`; merged only after the `provenance` check run passes on this exact head sha."
    )
    return open_pr(c, repo, branch, base, f"approve kit {sha[:7]}", body)


def provenance_state(c: GitHub, repo: str, head: str) -> tuple[str, str]:
    """('success'|'failed'|'pending'|'missing', detail) for the `provenance` check run of GitHub Actions on exactly `head`."""
    j = c.get_json(f"repos/{repo}/commits/{head}/check-runs?check_name={CHECK_NAME}&per_page=100")
    runs = j.get("check_runs") if isinstance(j, dict) else None
    if not isinstance(runs, list) or j.get("total_count", len(runs)) > len(runs):
        raise CIError("check-runs answer unreadable or paginated")
    mine = [
        r
        for r in runs
        if isinstance(r, dict)
        and r.get("name") == CHECK_NAME
        and r.get("head_sha") == head
        and isinstance(r.get("app"), dict)
        and r["app"].get("slug") == CHECK_APP
    ]
    if not mine:
        return "missing", f"no {CHECK_NAME} check run from {CHECK_APP} on {head[:7]} yet"
    latest = max(mine, key=lambda r: r.get("id") or 0)
    if latest.get("status") != "completed":
        return "pending", f"{CHECK_NAME} is {latest.get('status')}"
    if latest.get("conclusion") == "success":
        return "success", ""
    return "failed", f"{CHECK_NAME} concluded {latest.get('conclusion')}"


def wait_for_provenance(
    c: GitHub, repo: str, head: str, sleep: Callable, clock: Callable, timeout: float = CHECK_TIMEOUT
) -> None:
    deadline = clock() + timeout
    delay = CHECK_DELAY
    while True:
        state, detail = provenance_state(c, repo, head)
        if state == "success":
            return
        if state == "failed":
            raise CIError(f"{detail}; not merging")
        if clock() >= deadline:
            raise CIError(f"timed out waiting for {CHECK_NAME} on {head[:7]} ({detail}); not merging")
        sleep(delay)
        delay = min(delay * 2, CHECK_DELAY_MAX)


def merge_approval_pr(c: GitHub, ns, sha: str, source: str, sleep: Callable, clock: Callable) -> str:
    repo = cli._load_runtime("automerge").approvals_repo(ns.kit_repo)
    base = default_branch(c, repo)
    pr = find_open_pr(c, repo, cli._approve_branch(sha), base)
    number, head = pr["number"], pr["head"]["sha"]
    files = pci.changed_files(c.opener, repo, number)
    if files != [APPROVED_FILE]:
        raise CIError(f"approval PR changes {sorted(set(files)) or 'no files'}; only {APPROVED_FILE} may change")
    base_sha = branch_head(c, repo, base)
    base_text, _ = file_text(c, repo, APPROVED_FILE, base_sha)
    head_text, _ = file_text(c, repo, APPROVED_FILE, head)
    bad = prov.verify_approved_diff(base_text, head_text)
    if bad:
        raise CIError("approval diff is not an append of new shas: " + "; ".join(bad))
    base_lines = set(base_text.splitlines())
    added = [ln for ln in head_text.splitlines() if ln not in base_lines]
    if added != [approval_line(sha, ns, source)]:
        raise CIError(f"approval PR adds {added!r}, not exactly the expected line")
    require_fast_forward(c, repo, base_sha, head)
    wait_for_provenance(c, repo, head, sleep, clock)
    again = find_open_pr(c, repo, cli._approve_branch(sha), base)
    if again["number"] != number or again["head"]["sha"] != head:
        raise CIError("approval PR head moved while waiting for the check; not merging")
    merge_pr(c, repo, number, head)
    return f"merged approval PR #{number} at head {head[:7]}"


# --- the loop -----------------------------------------------------------------------------------------------------------


def run(ns, client: GitHub | None = None, *, sleep: Callable = time.sleep, clock: Callable = time.monotonic) -> int:
    """gather -> plan -> execute -> re-gather, at most MAX_STEPS actions. Exit 0 = done, 1 = any refusal or error."""
    try:
        return _run(ns, client, sleep, clock)
    except (cli.ReleaseError, prov.ProvenanceError, ValueError) as e:
        print(f"release --ci: failing closed: {e}", file=sys.stderr)
        return 1


def _run(ns, client, sleep, clock) -> int:
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", ns.kit_repo or ""):
        raise CIError("--kit-repo must be OWNER/REPO")
    source = getattr(ns, "source", None) or ""
    if not HEX40.fullmatch(source):
        raise CIError("--ci needs --source <40-hex autopilot commit> (in Actions: $GITHUB_SHA)")
    ns.branch = ns.branch or f"release/{source[:7]}"
    if not re.fullmatch(r"release/[\w.-]+", ns.branch):
        raise CIError("--branch must be release/NAME")
    approvals = cli._load_runtime("automerge").approvals_repo(ns.kit_repo)
    c = client or GitHub(write_repos={ns.kit_repo, approvals})
    render = render_kit()
    publish = {p: cli._blob_sha(b) for p, b in render.items()}
    taken: list[str] = []
    while True:
        st = cli.gather_release_state(ns, c.get_json, publish=publish, check_rollout=False)
        for label, status in cli._release_steps(st):
            print(f"  [{status}] {label}")
        action, detail = cli.plan_release(st)
        if action == "refuse":
            print(f"release --ci: refusing: {detail}", file=sys.stderr)
            return 1
        if action == "rollout":
            print(f"approved {st['sha'][:7]} from autopilot {source[:7]}; rollout is a separate manual command (`ap rollout`)")
            break
        if action == "done":
            print(detail)
            break
        if action == "wait":
            kit_pr, ap = st["kit_pr"], st["approval_pr"]
            if kit_pr and kit_pr["state"] == "open":
                action, detail = "merge_kit_pr", "verify and merge the kit PR"
            elif st["sha"] and ap and ap["state"] == "open":
                action, detail = "merge_approval_pr", "wait for provenance, verify and merge the approval PR"
            else:
                raise CIError(f"waiting on something the App cannot advance: {detail}")
        if not getattr(ns, "apply", False):
            print(f"[dry run] next: {detail}")
            break
        if len(taken) >= MAX_STEPS:
            raise CIError(f"step budget ({MAX_STEPS}) exhausted: {', '.join(taken)}")
        print(f"next: {detail}")
        if action == "open_kit_pr":
            url = open_kit_pr(c, ns, render, source)
            if not url:
                print("kit repo already matches this tree: nothing to publish")
                break
            taken.append(f"opened kit PR {url}")
        elif action == "merge_kit_pr":
            taken.append(merge_kit_pr(c, ns, render))
        elif action == "open_approval_pr":
            taken.append(f"opened approval PR {open_approval_pr(c, ns, st['sha'], source)}")
        else:
            taken.append(merge_approval_pr(c, ns, st["sha"], source, sleep, clock))
        print(f"  -> {taken[-1]}")
    if taken:
        print("steps taken: " + "; ".join(taken))
    return 0
