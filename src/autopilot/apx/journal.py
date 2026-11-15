"""Append-only journal conflicts, resolved by apx itself.

Every PR appends an entry to the end of the repo's journal (a proof-of-work rule), so parallel PRs conflict there as soon as one
merges. When a trusted PR is `dirty` and the ONLY files changed on both sides are allowlisted journals (journal_files.json), and
both sides purely appended to each (the merge-base copy is a byte prefix of main's and of the PR's), apx writes the merge itself:
main's text, then the PR's new text.

API only: blobs, a tree, a two-parent commit and a ref update through the Git Data API. Nothing is cloned and no PR code runs. A
commit an App creates this way is signed by GitHub, which matters for repos whose rules require verified signatures. The ref
update never forces, so if the branch moved since it was read the update fails and the next pass tries again. Anything less
clear-cut (an edited journal, any other file changed on both sides, markers in the result) is left for a human.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from .github import Api, GitHubError

KIND = "resolve-journal"
ALLOWLIST_FILE = Path(__file__).with_name("journal_files.json")
# What the resolver needs from the App; the doctor's REQUIRED already grants it (pinned by a test), so no new permission.
NEEDS = {"contents": "write", "pull_requests": "read"}
MAX_FILES = 300  # the compare API lists at most 300 files: at that size we cannot see every change, so we do nothing
_MARKER = re.compile(rb"^(?:(?:<{7}|>{7}|\|{7}) |={7}\r?$)", re.M)
_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class AllowlistError(ValueError):
    pass


def _paths(v, where: str) -> tuple[str, ...]:
    if not isinstance(v, list) or not v:
        raise AllowlistError(f"{where}: a non-empty list of paths")
    for p in v:
        if not isinstance(p, str) or not p or p.startswith("/") or ".." in p.split("/") or any(c in p for c in "*?[\\"):
            raise AllowlistError(f"{where}: {p!r} is not a plain repo-relative path")
    return tuple(v)


def load_allowlist(path: Path = ALLOWLIST_FILE) -> dict[str, tuple[str, ...]]:
    """{"*": default paths, "owner/repo": override}. Exact paths only (no globs): a wider match could merge real code."""
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict) or set(data) - {"default", "repos"} or "default" not in data:
        raise AllowlistError("journal_files.json: an object with 'default' and optional 'repos'")
    out = {"*": _paths(data["default"], "default")}
    repos = data.get("repos", {})
    if not isinstance(repos, dict):
        raise AllowlistError("repos: an object of owner/repo -> paths")
    for repo, v in repos.items():
        if not _REPO.match(str(repo)):
            raise AllowlistError(f"repos: {repo!r} is not owner/repo")
        out[repo] = _paths(v, repo)
    return out


def journal_files(repo: str, allow: dict | None = None) -> tuple[str, ...]:
    allow = load_allowlist() if allow is None else allow
    return allow.get(repo, allow["*"])


def has_markers(data: bytes) -> bool:
    return bool(_MARKER.search(data))


def merge_appended(base: bytes, main: bytes, head: bytes) -> bytes | None:
    """main + what the PR appended, or None unless both sides only appended to a newline-terminated base."""
    if not (main.startswith(base) and head.startswith(base)):
        return None
    if base and not base.endswith(b"\n"):
        return None  # an "append" could have extended the last line: not provably an append
    tail = head[len(base) :]
    if not tail:
        return main
    out = main if main.endswith(b"\n") or not main else main + b"\n"
    if out.endswith(b"\n\n") and tail.startswith(b"\n"):
        tail = tail[1:]  # main already ends with a blank line: do not stack a second one
    return out + tail


@dataclass
class Prepared:
    number: int
    branch: str
    head_sha: str
    main_sha: str
    resolved: dict[str, bytes]  # journal path -> merged content
    main_paths: set[str] = field(default_factory=set)  # every path main changed since the merge base


QUIET = ""  # not a candidate at all (not dirty, not trusted): nothing worth a note


def _changed(files: list) -> set[str]:
    out = set()
    for f in files:
        out.add(f["filename"])
        if f.get("previous_filename"):
            out.add(f["previous_filename"])
    return out


def _read(api: Api, repo: str, path: str, sha: str) -> bytes | None:
    try:
        f = api("GET", f"/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={sha}")
    except GitHubError as e:
        if e.status == 404:
            return None
        raise
    if not isinstance(f, dict) or f.get("type") != "file" or f.get("encoding") != "base64":
        return None  # e.g. over the contents API's size limit: not read, so not merged
    return base64.b64decode(f.get("content") or "")


def prepare(api: Api, repo: str, number: int, default_branch: str, allow: tuple[str, ...], prefixes: tuple[str, ...]):
    """(Prepared, note) when apx can resolve PR #number now, else (None, why). Read-only."""
    pr = api("GET", f"/repos/{repo}/pulls/{number}")
    head = pr.get("head") or {}  # type: ignore[union-attr]
    branch = head.get("ref") or ""
    if (head.get("repo") or {}).get("full_name") != repo or not branch.startswith(prefixes) or pr.get("state") != "open":  # type: ignore[union-attr]
        return None, QUIET
    if pr.get("mergeable_state") != "dirty" or (pr.get("base") or {}).get("ref") != default_branch:  # type: ignore[union-attr]
        return None, QUIET
    head_sha = head["sha"]
    main_sha = api("GET", f"/repos/{repo}/git/ref/heads/{urllib.parse.quote(default_branch)}")["object"]["sha"]  # type: ignore[index]
    side_pr = api("GET", f"/repos/{repo}/compare/{main_sha}...{head_sha}")
    base_sha = side_pr["merge_base_commit"]["sha"]  # type: ignore[index]
    side_main = api("GET", f"/repos/{repo}/compare/{base_sha}...{main_sha}")
    files_pr, files_main = side_pr.get("files") or [], side_main.get("files") or []  # type: ignore[union-attr]
    if len(files_pr) >= MAX_FILES or len(files_main) >= MAX_FILES:
        return None, "conflicted; too many changed files to check, left for a human"
    main_paths = _changed(files_main)
    both = sorted(_changed(files_pr) & main_paths)
    if not both:
        return None, "conflicted but no file changed on both sides; left for a human"
    other = [p for p in both if p not in allow]
    if other:
        return None, f"conflict outside the journal ({', '.join(other[:5])}); left for a human"
    resolved = {}
    for path in both:
        b, m, h = (_read(api, repo, path, s) for s in (base_sha, main_sha, head_sha))
        if b is None or m is None or h is None:
            return None, f"{path} missing or unreadable on one side; needs a human"
        r = merge_appended(b, m, h)
        if r is None:
            return None, f"journal edited not appended ({path}); needs a human"
        if has_markers(r):
            return None, f"{path} would contain conflict markers; needs a human"
        resolved[path] = r
    return Prepared(number, branch, head_sha, main_sha, resolved, main_paths), f"journal-only conflict ({', '.join(both)})"


def resolve(api: Api, repo: str, ref: str, prefixes: tuple[str, ...], allow: tuple[str, ...] | None = None) -> str:
    """Carry out one planned resolution. ref is "<pr>:<head sha>:<default branch>". Returns the log text; raises only on API errors."""
    number, planned_head, default_branch = ref.split(":", 2)
    allow = journal_files(repo) if allow is None else allow
    prep, why = prepare(api, repo, int(number), default_branch, allow, prefixes)
    if prep is None:
        return f"#{number} skipped: {why or 'no longer a journal-only conflict'}"
    if prep.head_sha != planned_head:
        return f"#{number} skipped: PR changed since it was planned"
    for data in prep.resolved.values():
        if has_markers(data):  # prepare refused these already; a second look right before the write costs nothing
            return f"#{number} skipped: result would contain conflict markers"
    head_tree = api("GET", f"/repos/{repo}/git/commits/{prep.head_sha}")["tree"]["sha"]  # type: ignore[index]
    main_tree = api("GET", f"/repos/{repo}/git/commits/{prep.main_sha}")["tree"]["sha"]  # type: ignore[index]
    listing = api("GET", f"/repos/{repo}/git/trees/{main_tree}?recursive=1")
    if listing.get("truncated"):  # type: ignore[union-attr]
        return f"#{number} skipped: main's tree is too large to read in one call"
    on_main = {e["path"]: e for e in listing["tree"] if e.get("type") != "tree"}  # type: ignore[index]
    # the merge result: the PR head's tree, plus main's version of every path only main changed, plus the merged journals
    entries = []
    for path in sorted(prep.main_paths - set(prep.resolved)):
        e = on_main.get(path)
        entries.append(
            {"path": path, "mode": e["mode"], "type": e["type"], "sha": e["sha"]}
            if e
            else {"path": path, "mode": "100644", "type": "blob", "sha": None}  # gone on main: delete it here too
        )
    for path, data in sorted(prep.resolved.items()):
        blob = api("POST", f"/repos/{repo}/git/blobs", {"content": base64.b64encode(data).decode(), "encoding": "base64"})
        mode = (on_main.get(path) or {}).get("mode", "100644")
        entries.append({"path": path, "mode": mode, "type": "blob", "sha": blob["sha"]})  # type: ignore[index]
    tree = api("POST", f"/repos/{repo}/git/trees", {"base_tree": head_tree, "tree": entries})
    names = ", ".join(sorted(prep.resolved))
    message = (
        f"Merge {default_branch} into {prep.branch}: keep both journal entries ({default_branch} first)\n\n"
        f"Resolved by apx: both sides only appended to {names}, so {default_branch}'s text comes first and this branch's new text follows."
    )
    # no author/committer: GitHub then signs the commit as the App, which repos that require verified signatures accept
    commit = api(
        "POST", f"/repos/{repo}/git/commits", {"message": message, "tree": tree["sha"], "parents": [prep.head_sha, prep.main_sha]}
    )  # type: ignore[index]
    try:
        api("PATCH", f"/repos/{repo}/git/refs/heads/{urllib.parse.quote(prep.branch)}", {"sha": commit["sha"], "force": False})  # type: ignore[index]
    except GitHubError as e:
        if e.status in (409, 422):
            return f"#{number} skipped: branch moved since it was read; retried next pass"
        raise
    return f"journal conflict resolved on #{number}: {commit['sha'][:7]} ({names})"  # type: ignore[index]
