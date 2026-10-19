"""`ap release --ci`: a fake GitHub (git objects, branches, PRs, check runs) behind the injected transport. No network."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from pathlib import Path

import pytest

from autopilot import cli, release_ci

SRC = "c" * 40
BRANCH = "release/ccccccc"
KIT, APPROVALS = "me/kit", "me/autopilot-approved"
OLD_APPROVED = "# Kit shas the owner approved.\n" + "9" * 40 + "  earlier source=" + "8" * 40 + "\n"
API = "https://api.github.com"


def bsha(data: bytes) -> str:
    return cli._blob_sha(data)


class World:
    """Just enough GitHub: repos with commits (full trees), branches, PRs, contents/refs/merge/compare/check-runs endpoints."""

    def __init__(self, render: dict[str, bytes]):
        self.render = render
        self.n = 0
        self.commits: dict[str, dict] = {}
        self.blobs: dict[str, bytes] = {}
        self.repos: dict[str, dict] = {}
        self.reqs: list[tuple[str, str, dict | None]] = []
        self.fail = None  # callable(method, path) -> status | None
        self.checks = lambda repo, head: [self.run(head)]
        self.corrupt_merge = False
        kit_tree = {"LICENSE": b"mit\n", "runtime/old.py": b"old\n", "README.md": b"stale readme\n"}
        for p, data in render.items():
            if p not in ("README.md", "runtime/automerge.py"):  # present-but-stale and missing files to exercise puts
                kit_tree[p] = data
        kit_tree["runtime/automerge.py"] = b"stale\n"
        self.add_repo(KIT, kit_tree)
        self.add_repo(APPROVALS, {"APPROVED": OLD_APPROVED.encode()})

    # -- state helpers
    def sha(self, label: str) -> str:
        self.n += 1
        return hashlib.sha1(f"{label}{self.n}".encode()).hexdigest()  # noqa: S324

    def commit(self, tree: dict[str, bytes | tuple], parent: str | None) -> str:
        out = {}
        for p, v in tree.items():
            if isinstance(v, tuple):
                out[p] = v
            else:
                self.blobs[bsha(v)] = v
                out[p] = ("100644", bsha(v))
        sha = self.sha("commit")
        self.commits[sha] = {"tree": out, "parent": parent}
        return sha

    def add_repo(self, repo: str, files: dict[str, bytes]) -> None:
        c = self.commit(files, None)
        self.repos[repo] = {"default": "main", "branches": {"main": c}, "prs": []}

    def head(self, repo: str, branch: str) -> str:
        return self.repos[repo]["branches"][branch]

    def tree(self, repo: str, ref: str) -> dict:
        return self.commits[self.resolve(repo, ref)]["tree"]

    def resolve(self, repo: str, ref: str) -> str:
        return self.repos[repo]["branches"].get(ref, ref)

    def text(self, repo: str, ref: str, path: str) -> str:
        return self.blobs[self.tree(repo, ref)[path][1]].decode()

    def make_branch(self, repo: str, branch: str, edits: dict[str, bytes | None], open_pr: bool = True, base="main") -> None:
        """A branch off base with edits applied (None deletes), plus an open PR for it."""
        raw = dict(self.tree(repo, base))
        for p, data in edits.items():
            if data is None:
                raw.pop(p, None)
            else:
                self.blobs[bsha(data)] = data
                raw[p] = ("100644", bsha(data))
        self.repos[repo]["branches"][branch] = self.commit(raw, self.head(repo, base))
        if open_pr:
            self.add_pr(repo, branch, base)

    def add_pr(self, repo: str, branch: str, base: str) -> dict:
        prs = self.repos[repo]["prs"]
        pr = {
            "number": len(prs) + 1,
            "branch": branch,
            "base": base,
            "state": "open",
            "merged_at": None,
            "merge_commit_sha": None,
        }
        prs.append(pr)
        return pr

    def pr_json(self, repo: str, pr: dict) -> dict:
        return {
            "number": pr["number"],
            "html_url": f"https://github.com/{repo}/pull/{pr['number']}",
            "state": pr["state"],
            "merged_at": pr["merged_at"],
            "merge_commit_sha": pr["merge_commit_sha"],
            "head": {"sha": self.head(repo, pr["branch"]), "ref": pr["branch"], "repo": {"full_name": repo}},
            "base": {"ref": pr["base"]},
        }

    def run(self, head, status="completed", conclusion="success", slug="github-actions", name="provenance", sha=None, id=1):
        return {
            "id": id,
            "name": name,
            "head_sha": sha or head,
            "status": status,
            "conclusion": conclusion,
            "app": {"slug": slug},
        }

    def is_ancestor(self, a: str, b: str) -> bool:
        while b:
            if a == b:
                return True
            b = self.commits[b]["parent"]
        return False

    # -- transport
    def http(self, method, url, headers, body):
        assert url.startswith(API + "/") and headers["Authorization"] == "Bearer tok"
        path, _, query = url[len(API) + 1 :].partition("?")
        data = json.loads(body) if body else None
        self.reqs.append((method, f"{path}?{query}" if query else path, data))
        if self.fail and (st := self.fail(method, path)):
            return st, b'{"message": "boom"}'
        st, out = self.route(method, path, query, data)
        return st, json.dumps(out).encode()

    def route(self, method, path, query, body):  # noqa: C901
        m = re.fullmatch(r"repos/([^/]+/[^/]+)(?:/(.*))?", path)
        assert m, path
        repo, rest = m.group(1), m.group(2) or ""
        r = self.repos[repo]
        if method == "GET" and rest == "":
            return 200, {"default_branch": r["default"]}
        if method == "GET" and (g := re.fullmatch(r"git/ref/heads/(.+)", rest)):
            return (200, {"object": {"sha": r["branches"][g.group(1)]}}) if g.group(1) in r["branches"] else (404, {})
        if method == "GET" and (g := re.fullmatch(r"git/trees/(.+)", rest)):
            tree = self.tree(repo, g.group(1))
            return 200, {
                "truncated": False,
                "tree": [{"type": "blob", "path": p, "mode": mo, "sha": h} for p, (mo, h) in tree.items()],
            }
        if method == "POST" and rest == "git/refs":
            name = body["ref"].removeprefix("refs/heads/")
            if name in r["branches"]:
                return 422, {"message": "Reference already exists"}
            r["branches"][name] = body["sha"]
            return 201, {}
        if g := re.fullmatch(r"contents/(.+)", rest):
            p = g.group(1)
            if method == "GET":
                ref = query.split("ref=")[1]
                t = self.tree(repo, ref)
                if p not in t:
                    return 404, {}
                return 200, {"encoding": "base64", "sha": t[p][1], "content": base64.encodebytes(self.blobs[t[p][1]]).decode()}
            b = body["branch"]
            cur = dict(self.tree(repo, b))
            if method == "PUT":
                if p in cur and body.get("sha") != cur[p][1]:
                    return 409, {"message": "sha mismatch"}
                if p not in cur and "sha" in body:
                    return 422, {}
                data = base64.b64decode(body["content"])
                self.blobs[bsha(data)] = data
                cur[p] = ("100644", bsha(data))
            else:
                if p not in cur or body.get("sha") != cur[p][1]:
                    return 409, {}
                del cur[p]
            r["branches"][b] = self.commit(cur, r["branches"][b])
            return (201 if method == "PUT" else 200), {"content": {}}
        if method == "POST" and rest == "pulls":
            pr = self.add_pr(repo, body["head"], body["base"])
            assert body["head"] in r["branches"]
            return 201, self.pr_json(repo, pr)
        if method == "GET" and rest == "pulls":
            q = dict(kv.split("=", 1) for kv in query.split("&"))
            branch = q["head"].split(":", 1)[1]
            want = q["state"]
            return 200, [
                self.pr_json(repo, p)
                for p in reversed(r["prs"])
                if p["branch"] == branch and (want == "all" or p["state"] == want)
            ]
        if method == "GET" and (g := re.fullmatch(r"compare/([0-9a-f]+)\.\.\.([0-9a-f]+)", rest)):
            a, b = g.groups()
            if self.is_ancestor(a, b):
                return 200, {"status": "ahead" if a != b else "identical", "behind_by": 0}
            return 200, {"status": "diverged", "behind_by": 1}
        if method == "GET" and (g := re.fullmatch(r"pulls/(\d+)/files", rest)):
            pr = r["prs"][int(g.group(1)) - 1]
            head, base = self.tree(repo, pr["branch"]), self.tree(repo, pr["base"])
            return 200, [{"filename": p} for p in sorted(set(head) | set(base)) if head.get(p) != base.get(p)]
        if method == "PUT" and (g := re.fullmatch(r"pulls/(\d+)/merge", rest)):
            pr = r["prs"][int(g.group(1)) - 1]
            if body["sha"] != self.head(repo, pr["branch"]):
                return 409, {"message": "Head branch was modified"}
            tree = dict(self.tree(repo, pr["branch"]))
            if self.corrupt_merge:
                tree.pop(sorted(p for p in tree if p.startswith("runtime/"))[0])
            sha = self.commit(tree, r["branches"][pr["base"]])
            r["branches"][pr["base"]] = sha
            pr.update(state="closed", merged_at="2026-10-19T00:00:00Z", merge_commit_sha=sha)
            return 200, {"merged": True}
        if method == "GET" and (g := re.fullmatch(r"commits/([0-9a-f]+)/check-runs", rest)):
            runs = self.checks(repo, g.group(1))
            return 200, {"total_count": len(runs), "check_runs": runs}
        raise AssertionError(f"unrouted {method} {path}")

    # -- assertions
    def writes(self):
        return [q for q in self.reqs if q[0] != "GET"]

    def merges(self):
        return [q for q in self.reqs if q[0] == "PUT" and q[1].endswith("/merge")]


@pytest.fixture(scope="module")
def render():
    return release_ci.render_kit()


@pytest.fixture
def world(monkeypatch, render):
    w = World(render)
    am = cli._load_runtime("automerge")
    monkeypatch.setattr(
        am,
        "fetch_approved",
        lambda kit: [ln.split()[0] for ln in w.text(APPROVALS, "main", "APPROVED").splitlines() if re.match(r"[0-9a-f]{40}", ln)],
    )
    monkeypatch.setattr(cli, "_load_runtime", lambda n: am)
    monkeypatch.setattr(cli, "main_publish_tree", lambda gh, repo, ref="main": {p: bsha(b) for p, b in render.items()})
    monkeypatch.setattr(
        cli, "load_portfolio", lambda: (_ for _ in ()).throw(AssertionError("CI must not look at downstream repos"))
    )
    return w


def ns(apply=True, **kw):
    d = dict(kit_repo=KIT, branch=None, autopilot_repo="me/autopilot", source=SRC, only=[], apply=apply, ci=True)
    return argparse.Namespace(**{**d, **kw})


class Clock:
    def __init__(self):
        self.t = 0.0
        self.sleeps: list[float] = []

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s

    def now(self):
        return self.t


def go(world, apply=True, token="tok", **kw):
    clk = Clock()
    c = release_ci.GitHub(token=token, http=world.http, write_repos={KIT, APPROVALS})
    rc = release_ci.run(ns(apply=apply, **kw), c, sleep=clk.sleep, clock=clk.now)
    return rc, clk


def kit_merged(world, render):
    """Put the world in the state 'kit PR merged' by running the first half of the flow."""
    world.make_branch(KIT, BRANCH, {p: render[p] for p in render} | {"runtime/old.py": None})
    pr = world.repos[KIT]["prs"][0]
    world.http(
        "PUT",
        f"{API}/repos/{KIT}/pulls/1/merge",
        {"Authorization": "Bearer tok"},
        json.dumps({"sha": world.head(KIT, BRANCH), "merge_method": "merge"}).encode(),
    )
    world.reqs.clear()
    return pr["merge_commit_sha"]


# ---- the whole flow ----------------------------------------------------------------------------------------------------


def test_full_release_without_a_human(world, render, capsys):
    rc, _ = go(world)
    out = capsys.readouterr()
    assert rc == 0, out.err
    main = world.tree(KIT, "main")
    assert {p: h for p, (_, h) in main.items() if release_ci.managed(p)} == {p: bsha(b) for p, b in render.items()}
    assert "LICENSE" in main and "runtime/old.py" not in main  # unmanaged kept, stale managed file removed
    kit_sha = world.repos[KIT]["prs"][0]["merge_commit_sha"]
    approved = world.text(APPROVALS, "main", "APPROVED")
    assert approved == OLD_APPROVED + f"{kit_sha}  release {BRANCH} source={SRC}\n"
    assert [q[1] for q in world.merges()] == [f"repos/{KIT}/pulls/1/merge", f"repos/{APPROVALS}/pulls/1/merge"]
    assert "rollout is a separate manual command" in out.out


def test_every_write_is_safe(world):
    assert go(world)[0] == 0
    for method, path, body in world.writes():
        assert path.split("/")[1] and re.match(rf"repos/({KIT}|{APPROVALS})/", path), path
        assert "force" not in json.dumps(body).lower()
        if "/contents/" in path:
            assert not ({"author", "committer"} & set(body)), path  # GitHub signs the commit
        if path.endswith("/merge"):
            assert set(body) == {"sha", "merge_method"} and body["merge_method"] == "merge"
            assert re.fullmatch(r"[0-9a-f]{40}", body["sha"])
        if path.endswith("git/refs"):
            assert method == "POST"
    assert not [q for q in world.reqs if "graphql" in q[1]]


def test_merges_pin_the_verified_head(world):
    assert go(world)[0] == 0
    for _, path, body in world.merges():
        repo = path.split("/pulls/")[0].removeprefix("repos/")
        number = int(path.split("/pulls/")[1].split("/")[0])
        assert body["sha"] == world.head(repo, world.repos[repo]["prs"][number - 1]["branch"])


def test_dry_run_makes_zero_writes(world, capsys):
    rc, _ = go(world, apply=False)
    assert rc == 0 and world.writes() == []
    assert "[dry run]" in capsys.readouterr().out
    assert world.reqs and all(q[0] == "GET" for q in world.reqs)


def test_dry_run_with_open_kit_pr_does_not_merge(world, render):
    world.make_branch(KIT, BRANCH, dict(render))
    assert go(world, apply=False)[0] == 0 and world.writes() == []


def test_nothing_to_publish_stops_cleanly(world, render, capsys):
    world.repos[KIT]["branches"]["main"] = world.commit({p: b for p, b in render.items()}, None)
    assert go(world)[0] == 0 and world.writes() == []
    assert "nothing to publish" in capsys.readouterr().out


def test_resumable_after_kit_merge_skips_to_approval(world, render):
    kit_sha = kit_merged(world, render)
    rc, _ = go(world)
    assert rc == 0
    assert not [q for q in world.writes() if f"repos/{KIT}/" in q[1]]  # nothing more done in the kit repo
    assert kit_sha in world.text(APPROVALS, "main", "APPROVED")
    assert [q[1] for q in world.merges()] == [f"repos/{APPROVALS}/pulls/1/merge"]


def test_rerun_after_everything_is_a_noop(world):
    assert go(world)[0] == 0
    world.reqs.clear()
    assert go(world)[0] == 0
    assert world.writes() == []


# ---- kit merge preconditions -------------------------------------------------------------------------------------------


def tampers(render):
    flip = render["runtime/automerge.py"] + b" "  # one byte
    return {
        "one byte": {"runtime/automerge.py": flip},
        "extra managed file": {"runtime/evil.py": b"x=1\n"},
        "extra workflow": {".github/workflows/evil.yml": b"on: push\n"},
        "missing file": {"runtime/automerge.py": None},
        "unmanaged change": {"LICENSE": b"gpl\n"},
        "stale file kept": {"runtime/old.py": b"old\n"},
    }


@pytest.mark.parametrize("name", list(tampers({"runtime/automerge.py": b""})))
def test_tampered_kit_head_is_never_merged(world, render, name, capsys):
    world.make_branch(KIT, BRANCH, dict(render) | {"runtime/old.py": None} | tampers(render)[name])
    rc, _ = go(world)
    assert rc == 1 and world.merges() == []
    assert "not merging" in capsys.readouterr().err


def test_kit_head_equal_to_export_is_merged(world, render):
    world.make_branch(KIT, BRANCH, dict(render) | {"runtime/old.py": None})
    assert go(world)[0] == 0 and len(world.merges()) == 2


def test_kit_base_moved_since_the_pr_refuses(world, render):
    world.make_branch(KIT, BRANCH, dict(render) | {"runtime/old.py": None})
    world.repos[KIT]["branches"]["main"] = world.commit({**world.tree(KIT, "main"), "NOTES": b"n"}, world.head(KIT, "main"))
    assert go(world)[0] == 1 and world.merges() == []


def test_base_moved_but_trees_still_agree_still_refuses(world, render):
    """A head equal to the export is not enough if the base tip moved: the merge result is then not the verified tree."""
    world.make_branch(KIT, BRANCH, dict(render) | {"runtime/old.py": None})
    world.repos[KIT]["branches"]["main"] = world.commit(
        {**world.tree(KIT, "main"), "runtime/automerge.py": render["runtime/automerge.py"]}, world.head(KIT, "main")
    )
    assert go(world)[0] == 1 and world.merges() == []


def test_merged_kit_that_does_not_match_stops_before_approval(world, render, capsys):
    world.corrupt_merge = True
    rc, _ = go(world)
    assert rc == 1 and "tamper guard" in capsys.readouterr().err
    assert not [q for q in world.writes() if APPROVALS in q[1]]


def test_existing_branch_without_pr_fails_closed(world, render):
    world.repos[KIT]["branches"][BRANCH] = world.head(KIT, "main")
    rc, _ = go(world)
    assert rc == 1
    assert [q[:2] for q in world.writes()] == [("POST", f"repos/{KIT}/git/refs")]  # tried the plain create, got 422, stopped


def test_closed_kit_pr_refuses(world, render):
    world.make_branch(KIT, BRANCH, dict(render))
    world.repos[KIT]["prs"][0]["state"] = "closed"
    assert go(world)[0] == 1 and world.writes() == []


# ---- approval merge preconditions --------------------------------------------------------------------------------------


@pytest.fixture
def approval_ready(world, render):
    kit_sha = kit_merged(world, render)
    line = f"{kit_sha}  release {BRANCH} source={SRC}\n"
    branch = f"approve-{kit_sha[:7]}"
    return world, kit_sha, line, branch


def make_approval(w, kit_sha, branch, text_or_tree):
    edits = text_or_tree if isinstance(text_or_tree, dict) else {"APPROVED": text_or_tree.encode()}
    w.make_branch(APPROVALS, branch, edits)


def test_good_approval_pr_merges_with_the_checked_head(approval_ready):
    w, kit_sha, line, branch = approval_ready
    make_approval(w, kit_sha, branch, OLD_APPROVED + line)
    assert go(w)[0] == 0
    (m,) = w.merges()
    assert m[2]["sha"] == w.head(APPROVALS, branch)


def test_approval_pr_touching_another_file_refuses(approval_ready):
    w, kit_sha, line, branch = approval_ready
    make_approval(w, kit_sha, branch, {"APPROVED": (OLD_APPROVED + line).encode(), "README.md": b"hi"})
    assert go(w)[0] == 1 and w.merges() == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda old, line: old.replace("earlier", "edited") + line,  # edits an old line
        lambda old, line: old + line + "a" * 40 + "  smuggled\n",  # extra approval
        lambda old, line: old + line.replace(SRC, "d" * 40),  # wrong source
        lambda old, line: "",  # wipes the file
        lambda old, line: old + "not a hex line\n" + line,
    ],
)
def test_bad_approved_content_refuses(approval_ready, mutate):
    w, kit_sha, line, branch = approval_ready
    make_approval(w, kit_sha, branch, mutate(OLD_APPROVED, line))
    assert go(w)[0] == 1 and w.merges() == []


def test_already_approved_sha_refuses(approval_ready):
    w, kit_sha, line, branch = approval_ready
    w.repos[APPROVALS]["branches"]["main"] = w.commit({"APPROVED": (OLD_APPROVED + line).encode()}, w.head(APPROVALS, "main"))
    c = release_ci.GitHub(token="tok", http=w.http, write_repos={KIT, APPROVALS})
    with pytest.raises(release_ci.CIError, match="already"):
        release_ci.open_approval_pr(c, ns(branch=BRANCH), kit_sha, SRC)
    assert w.writes() == []


def test_approval_base_moved_refuses(approval_ready):
    w, kit_sha, line, branch = approval_ready
    make_approval(w, kit_sha, branch, OLD_APPROVED + line)
    w.repos[APPROVALS]["branches"]["main"] = w.commit({"APPROVED": (OLD_APPROVED + "#c\n").encode()}, w.head(APPROVALS, "main"))
    assert go(w)[0] == 1 and w.merges() == []


# ---- provenance check run ----------------------------------------------------------------------------------------------


def checks_case(w, kit_sha, line, branch, checks):
    make_approval(w, kit_sha, branch, OLD_APPROVED + line)
    w.checks = checks


BAD_CHECKS = {
    "missing": lambda w: lambda repo, head: [],
    "pending forever": lambda w: lambda repo, head: [w.run(head, status="in_progress", conclusion=None)],
    "queued forever": lambda w: lambda repo, head: [w.run(head, status="queued", conclusion=None)],
    "failure": lambda w: lambda repo, head: [w.run(head, conclusion="failure")],
    "neutral": lambda w: lambda repo, head: [w.run(head, conclusion="neutral")],
    "skipped": lambda w: lambda repo, head: [w.run(head, conclusion="skipped")],
    "cancelled": lambda w: lambda repo, head: [w.run(head, conclusion="cancelled")],
    "other head sha": lambda w: lambda repo, head: [w.run(head, sha="e" * 40)],
    "other app": lambda w: lambda repo, head: [w.run(head, slug="evil-app")],
    "other name": lambda w: lambda repo, head: [w.run(head, name="lint")],
    "latest run failed": lambda w: lambda repo, head: [w.run(head, id=1), w.run(head, conclusion="failure", id=2)],
}


@pytest.mark.parametrize("name", list(BAD_CHECKS))
def test_provenance_not_green_on_the_exact_head_refuses(approval_ready, name):
    w, kit_sha, line, branch = approval_ready
    checks_case(w, kit_sha, line, branch, BAD_CHECKS[name](w))
    rc, clk = go(w)
    assert rc == 1 and w.merges() == []
    assert clk.t <= release_ci.CHECK_TIMEOUT + release_ci.CHECK_DELAY_MAX  # bounded


def test_provenance_pending_then_green_merges_after_backoff(approval_ready):
    w, kit_sha, line, branch = approval_ready
    calls = {"n": 0}

    def checks(repo, head):
        calls["n"] += 1
        return [w.run(head, status="in_progress", conclusion=None)] if calls["n"] < 4 else [w.run(head)]

    checks_case(w, kit_sha, line, branch, checks)
    rc, clk = go(w)
    assert rc == 0 and len(w.merges()) == 1
    assert clk.sleeps == [5.0, 10.0, 20.0]


def test_rerun_green_after_earlier_failure_is_accepted(approval_ready):
    w, kit_sha, line, branch = approval_ready
    checks_case(w, kit_sha, line, branch, lambda repo, head: [w.run(head, conclusion="failure", id=1), w.run(head, id=2)])
    assert go(w)[0] == 0


def test_head_moving_while_waiting_refuses(approval_ready):
    w, kit_sha, line, branch = approval_ready
    make_approval(w, kit_sha, branch, OLD_APPROVED + line)

    def checks(repo, head):
        w.repos[APPROVALS]["branches"][branch] = w.commit({"APPROVED": (OLD_APPROVED + line + "f" * 40 + "  x\n").encode()}, head)
        return [w.run(head)]

    w.checks = checks
    assert go(w)[0] == 1 and w.merges() == []


# ---- failing closed ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,frag,merge_requests",
    [
        ("GET", "git/trees", 0),
        ("GET", "compare", 0),
        ("GET", "check-runs", 1),  # the kit merge happened; the approval merge needs the check run
        ("PUT", "/contents/", 0),
        ("POST", "/pulls", 0),
        ("PUT", "/merge", 1),  # the one (failed) attempt, never retried
        ("POST", "git/refs", 0),
    ],
)
def test_api_errors_fail_closed(world, method, frag, merge_requests):
    world.fail = lambda m, p: 500 if m == method and frag in p else None
    rc, _ = go(world)
    assert rc == 1
    assert len(world.merges()) == merge_requests


def test_merge_error_response_is_not_success(world, render):
    world.make_branch(KIT, BRANCH, dict(render) | {"runtime/old.py": None})
    world.fail = lambda m, p: 405 if p.endswith("/merge") else None
    assert go(world)[0] == 1


def test_missing_token_fails_closed(world, monkeypatch, capsys):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert release_ci.run(ns()) == 1
    assert "GH_TOKEN" in capsys.readouterr().err


def test_source_is_required_and_validated(world):
    assert go(world, source=None)[0] == 1
    assert go(world, source="main")[0] == 1
    assert world.reqs == []


def test_step_budget_is_bounded(world, monkeypatch):
    monkeypatch.setattr(release_ci, "MAX_STEPS", 1)
    rc, _ = go(world)
    assert rc == 1 and len(world.merges()) == 0  # opened the kit PR (1 step), then refused to go on


def test_source_is_used_instead_of_resolving_main(world):
    assert go(world, apply=False)[0] == 0
    assert not [q for q in world.reqs if "commits/main" in q[1]]


# ---- the client and the module itself ----------------------------------------------------------------------------------


def client(world):
    return release_ci.GitHub(token="tok", http=world.http, write_repos={KIT, APPROVALS})


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("PUT", f"repos/{KIT}/pulls/1/merge", {"merge_method": "merge"}),  # no sha
        ("PUT", f"repos/{KIT}/pulls/1/merge", {"sha": "abc", "merge_method": "merge"}),  # short sha
        ("PUT", f"repos/{KIT}/pulls/1/merge", {"sha": "a" * 40, "merge_method": "squash"}),
        ("PUT", f"repos/{KIT}/pulls/1/merge", {"sha": "a" * 40, "merge_method": "merge", "commit_title": "x"}),
        ("PUT", f"repos/{KIT}/contents/x", {"content": "", "message": "m", "branch": "b", "committer": {"name": "a"}}),
        ("PUT", f"repos/{KIT}/contents/x", {"content": "", "message": "m", "branch": "b", "author": {"name": "a"}}),
        ("POST", f"repos/{KIT}/git/refs", {"ref": "refs/heads/x", "sha": "a" * 40, "force": True}),
        ("PATCH", f"repos/{KIT}/git/refs/heads/main", {"sha": "a" * 40}),
        ("POST", "repos/me/other/git/refs", {"ref": "refs/heads/x", "sha": "a" * 40}),
        ("POST", "graphql", {"query": "{}"}),
    ],
)
def test_client_refuses_unsafe_requests(world, method, path, body):
    with pytest.raises(release_ci.CIError):
        client(world).request(method, path, body)
    assert world.reqs == []


def test_transport_is_bound_at_call_time(world, monkeypatch):
    c = release_ci.GitHub(token="tok", write_repos={KIT})
    monkeypatch.setattr(release_ci, "_default_http", world.http)
    assert c.get_json(f"repos/{KIT}")["default_branch"] == "main"


def test_module_has_no_graphql_subprocess_git_or_force():
    src = Path(release_ci.__file__).read_text()
    for banned in (
        "subprocess",
        "graphql",
        "os.system",
        "gh api",
        "git push",
        "git commit",
        "git clone",
        "--force",
        "force_push",
    ):
        assert banned not in src.lower(), banned
    assert not re.search(r"\bimport (subprocess|shlex)\b", src)
    assert src.count("/merge") == 2  # the guard and the single merge_pr call


def test_cli_flag_routes_to_ci(monkeypatch):
    seen = {}
    monkeypatch.setattr(release_ci, "run", lambda n: seen.setdefault("ns", n) and 0)
    assert cli.main(["release", "--ci", "--kit-repo", KIT, "--source", SRC]) == 0
    assert seen["ns"].ci and seen["ns"].source == SRC and seen["ns"].apply is False
