"""`ap rollout --ci` and the pure `bump_files`: a fake GitHub behind the injected transport. No network."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import tempfile
from pathlib import Path

import pytest

from autopilot import cli, release_ci, rollout_ci

OWNER = "RyanJHamby"
KIT = f"{OWNER}/autopilot-kit"
OLD, NEW = "a" * 40, "b" * 40
API = "https://api.github.com"
BRANCH = f"autopilot/kit-bump-{NEW[:7]}"

PORTFOLIO = {
    "owner": OWNER,
    "repos": {
        "alpha": {"tier": "A", "mode": "standard", "enabled": True},
        "beta": {"tier": "B", "mode": "standard", "enabled": True},
        "gamma": {"tier": "B", "mode": "standard", "enabled": True},
        "held": {"tier": "B", "mode": "standard", "enabled": True, "hold_until": "2999-01-01T00:00:00Z"},
        "dormant": {"tier": "C", "mode": "dormant", "enabled": True},
        "secret": {"tier": "A", "mode": "standard", "enabled": True, "data_class": "restricted"},
        "off": {"tier": "A", "mode": "standard", "enabled": False},
    },
}
CANDIDATES = ["alpha", "beta", "gamma"]


def bsha(data: bytes) -> str:
    return cli._blob_sha(data)


def scaffold(sha: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    """What a repo on the shared kit at `sha` looks like: the real `ap init --kit` output plus a stack marker."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "pyproject.toml").write_text("[project]\nname='x'\n")
        for rel, content in (extra or {}).items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(content)
        cli.init_repo(root, "B", "standard", central=(KIT, sha))
        # a second pass, as a previous rollout would have made: init_repo drops the user-owned files from the manifest on re-run
        cli.init_repo(root, "B", "standard", central=(KIT, sha))
        return {str(p.relative_to(root)): p.read_text() for p in root.rglob("*") if p.is_file()}


class World:
    def __init__(self):
        self.repos: dict[str, dict] = {}
        self.blobs: dict[str, bytes] = {}
        self.reqs: list[tuple[str, str, dict | None]] = []
        self.fail = None  # callable(method, path) -> status | None
        self.n = 0

    def commit(self, files: dict[str, bytes]) -> tuple[str, dict]:
        tree = {}
        for p, data in files.items():
            self.blobs[bsha(data)] = data
            tree[p] = ("100644", bsha(data))
        self.n += 1
        return hashlib.sha1(f"c{self.n}".encode()).hexdigest(), tree  # noqa: S324

    def add_repo(self, slug: str, files: dict[str, str]) -> None:
        sha, tree = self.commit({p: c.encode() for p, c in files.items()})
        self.repos[slug] = {"commits": {sha: tree}, "branches": {"main": sha}, "prs": []}

    def tree(self, slug: str, ref: str) -> dict:
        r = self.repos[slug]
        return r["commits"][r["branches"].get(ref, ref)]

    def text(self, slug: str, ref: str, path: str) -> str:
        return self.blobs[self.tree(slug, ref)[path][1]].decode()

    def http(self, method, url, headers, body):
        assert url.startswith(API + "/") and headers["Authorization"] == "Bearer rolltok"
        path, _, query = url[len(API) + 1 :].partition("?")
        data = json.loads(body) if body else None
        self.reqs.append((method, path, data))
        if self.fail and (st := self.fail(method, path)):
            return st, b'{"message": "boom"}'
        st, out = self.route(method, path, query, data)
        return st, json.dumps(out).encode()

    def route(self, method, path, query, body):  # noqa: C901
        m = re.fullmatch(r"repos/([^/]+/[^/]+)(?:/(.*))?", path)
        assert m, path
        slug, rest = m.group(1), m.group(2) or ""
        r = self.repos[slug]
        if method == "GET" and rest == "":
            return 200, {"default_branch": "main"}
        if method == "GET" and (g := re.fullmatch(r"git/ref/heads/(.+)", rest)):
            b = g.group(1)
            return (200, {"object": {"sha": r["branches"][b]}}) if b in r["branches"] else (404, {})
        if method == "GET" and (g := re.fullmatch(r"git/trees/(.+)", rest)):
            tree = r["commits"][g.group(1)]
            entries = [{"type": "blob", "path": p, "mode": mo, "sha": h} for p, (mo, h) in tree.items()]
            return 200, {"truncated": False, "tree": entries}
        if method == "POST" and rest == "git/refs":
            name = body["ref"].removeprefix("refs/heads/")
            if name in r["branches"]:
                return 422, {"message": "exists"}
            r["branches"][name] = body["sha"]
            return 201, {}
        if g := re.fullmatch(r"contents/(.+)", rest):
            p = g.group(1)
            if method == "GET":
                t = self.tree(slug, query.split("ref=")[1])
                if p not in t:
                    return 404, {}
                content = base64.encodebytes(self.blobs[t[p][1]]).decode()
                return 200, {"encoding": "base64", "sha": t[p][1], "content": content}
            assert method == "PUT"
            b = body["branch"]
            cur = dict(self.tree(slug, b))
            if (p in cur) != ("sha" in body) or ("sha" in body and body["sha"] != cur[p][1]):
                return 422, {"message": "sha mismatch"}
            data = base64.b64decode(body["content"])
            self.blobs[bsha(data)] = data
            cur[p] = ("100644", bsha(data))
            sha, tree = self.commit({q: self.blobs[h] for q, (_, h) in cur.items()})
            r["commits"][sha] = tree
            r["branches"][b] = sha
            return 201, {"content": {}}
        if method == "GET" and rest == "pulls":
            q = dict(kv.split("=", 1) for kv in query.split("&"))
            branch = q["head"].split(":", 1)[1]
            return 200, [{"number": p["number"]} for p in r["prs"] if p["branch"] == branch]
        if method == "POST" and rest == "pulls":
            assert body["head"] in r["branches"]
            r["prs"].append({"number": len(r["prs"]) + 1, "branch": body["head"], "title": body["title"], "body": body["body"]})
            return 201, {"html_url": f"https://github.com/{slug}/pull/{len(r['prs'])}"}
        raise AssertionError(f"unrouted {method} {path}")

    def writes(self):
        return [q for q in self.reqs if q[0] != "GET"]

    def pr_repos(self):
        return sorted(s for s, r in self.repos.items() if r["prs"])


@pytest.fixture
def world(monkeypatch):
    w = World()
    for name in CANDIDATES + ["held", "dormant", "secret", "off", "outsider"]:
        w.add_repo(f"{OWNER}/{name}", scaffold(OLD))
    monkeypatch.setenv("ROLLOUT_TOKEN", "rolltok")
    monkeypatch.setenv("GH_TOKEN", "WRONG-release-token")
    return w


def ns(apply=True, **kw):
    return argparse.Namespace(**{**dict(kit=f"{KIT}@{NEW}", only=[], apply=apply, ci=True), **kw})


def go(world, apply=True, approved=None, **kw):
    slugs = [f"{OWNER}/{n}" for n in PORTFOLIO["repos"]] + [f"{OWNER}/outsider"]
    c = rollout_ci.make_client(slugs, http=world.http)
    return rollout_ci.run(ns(apply, **kw), c, portfolio=PORTFOLIO, approved=[NEW] if approved is None else approved)


# ---- bump_files (pure) ------------------------------------------------------------------------------------------------------


def test_bump_files_rewrites_pins_and_manifest():
    out = cli.bump_files(scaffold(OLD), KIT, NEW, "B", "standard")
    assert out and ".autopilot/manifest.json" in out
    assert all(v is not None for v in out.values())
    callers = [p for p in out if p.startswith(".github/workflows/")]
    assert callers and all(NEW in out[p] and OLD not in out[p] for p in callers)
    assert json.loads(out[".autopilot/manifest.json"])["files"][callers[0]] == cli._sha(out[callers[0]].encode())
    assert OLD not in "".join(v for v in out.values())


def test_bump_files_equals_a_scaffold_at_the_new_sha():
    out = cli.bump_files(scaffold(OLD), KIT, NEW, "B", "standard")
    assert {**scaffold(OLD), **out} == scaffold(NEW)


def test_bump_files_none_when_unchanged_or_not_on_the_shared_kit():
    assert cli.bump_files(scaffold(NEW), KIT, NEW, "B", "standard") is None
    copy_mode = scaffold(OLD)
    copy_mode[".github/workflows/agent-exec.yml"] = "name: vendored\n"
    assert cli.bump_files(copy_mode, KIT, NEW, "B", "standard") is None
    assert cli.bump_files({}, KIT, NEW) is None


def test_bump_files_leaves_hand_edited_managed_files_alone(capsys):
    files = scaffold(OLD)
    files[".github/workflows/guard.yml"] += "# hand edit\n"
    out = cli.bump_files(files, KIT, NEW, "B", "standard")
    assert ".github/workflows/guard.yml" not in out and "hand" in capsys.readouterr().err


def test_bump_inputs_lists_managed_files_and_marker_presence():
    files = scaffold(OLD, {"sub/Cargo.toml": "", "package-lock.json": "{}"})
    fetch, present = cli.bump_inputs(list(files), KIT, NEW)
    assert ".github/workflows/agent-exec.yml" in fetch and ".autopilot/manifest.json" in fetch
    assert set(present) == {"pyproject.toml", "sub/Cargo.toml", "package-lock.json"}
    assert "README.md" not in fetch


# ---- rollout --ci -----------------------------------------------------------------------------------------------------------


def test_opens_prs_in_exactly_the_candidate_repos(world, capsys):
    assert go(world) == 0, capsys.readouterr().err
    assert world.pr_repos() == sorted(f"{OWNER}/{n}" for n in CANDIDATES)
    pr = world.repos[f"{OWNER}/alpha"]["prs"][0]
    assert pr["branch"] == BRANCH and pr["title"] == f"autopilot: bump kit to {NEW[:7]}"
    assert pr["body"].startswith(f"Pin bump to the owner-approved kit `{NEW}`.") and "kit-bump" in pr["body"]
    guard = ".github/workflows/guard.yml"
    assert world.text(f"{OWNER}/alpha", BRANCH, guard) == scaffold(NEW)[guard]
    assert world.text(f"{OWNER}/alpha", "main", guard) == scaffold(OLD)[guard]
    for n in ("held", "dormant", "secret", "off", "outsider"):
        assert BRANCH not in world.repos[f"{OWNER}/{n}"]["branches"]
    written = {"/".join(q[1].split("/")[1:3]) for q in world.writes()}
    assert written == {f"{OWNER}/{n}" for n in CANDIDATES}


def test_never_merges_and_never_sets_author_committer_or_force(world):
    assert go(world) == 0
    assert world.writes()
    for method, path, body in world.writes():
        assert not path.endswith("/merge") and not re.search(r"/pulls/\d+/", path)
        assert method in ("POST", "PUT")
        assert not ({"author", "committer"} & set(body or {}))
        assert not any("force" in k.lower() for k in body or {})
        assert (method == "PUT") == ("/contents/" in path)
    assert not [q for q in world.reqs if q[0] == "DELETE"]


def test_client_refuses_merges_and_deletes(world):
    c = rollout_ci.make_client([f"{OWNER}/alpha"], http=world.http)
    bad_contents = {"content": "", "branch": "b", "message": "m"}
    for method, path, body in [
        ("PUT", f"repos/{OWNER}/alpha/pulls/1/merge", {"sha": "c" * 40, "merge_method": "merge"}),
        ("POST", f"repos/{OWNER}/alpha/pulls/1/merge", {}),
        ("PUT", f"repos/{OWNER}/alpha/pulls/1/update-branch", {}),
        ("POST", f"repos/{OWNER}/alpha/pulls/1/reviews", {"event": "APPROVE"}),
        ("DELETE", f"repos/{OWNER}/alpha/git/refs/heads/x", None),
        ("PATCH", f"repos/{OWNER}/alpha/pulls/1", {}),
        ("PUT", f"repos/{OWNER}/outsider/contents/x", bad_contents),
        ("PUT", f"repos/{OWNER}/alpha/contents/x", {**bad_contents, "committer": {"name": "x"}}),
        ("POST", f"repos/{OWNER}/alpha/git/refs", {"ref": "r", "sha": "c" * 40, "force": True}),
    ]:
        with pytest.raises(release_ci.CIError):
            c.request(method, path, body)
    assert world.reqs == []


def test_dry_run_sends_zero_non_get_requests(world, capsys):
    assert go(world, apply=False) == 0
    assert world.reqs and not world.writes()
    assert capsys.readouterr().out.count("[dry run] would open") == len(CANDIDATES)
    assert world.pr_repos() == []


@pytest.mark.parametrize("approved", [[], ["c" * 40]])
def test_unapproved_sha_refuses_everything(world, approved, capsys):
    assert rollout_ci.run(ns(), None, portfolio=PORTFOLIO, approved=approved) == 1
    assert world.reqs == [] and world.pr_repos() == [] and "not on" in capsys.readouterr().err


def test_refuses_bad_sha_and_foreign_kit(world, capsys):
    for kit in (f"{KIT}@{NEW[:7]}", f"{KIT}@{'B' * 40}", f"someone/autopilot-kit@{NEW}", f"{OWNER}/other@{NEW}", ""):
        assert rollout_ci.run(ns(kit=kit), None, portfolio=PORTFOLIO, approved=[NEW]) == 1
    assert world.reqs == []
    assert "must be" in capsys.readouterr().err


def test_reads_approved_with_the_anonymous_opener(world, monkeypatch):
    seen = {}
    am = cli._load_runtime("automerge")
    monkeypatch.setattr(cli, "_load_runtime", lambda n: am)
    monkeypatch.setattr(am, "fetch_approved", lambda kit, opener=None: seen.update(kit=kit, opener=opener) or [NEW])
    c = rollout_ci.make_client([f"{OWNER}/alpha"], http=world.http)
    assert rollout_ci.run(ns(apply=False, only=["alpha"]), c, portfolio=PORTFOLIO) == 0
    assert seen == {"kit": KIT, "opener": rollout_ci.anonymous_opener}


def test_already_bumped_repo_is_skipped(world, capsys):
    world.add_repo(f"{OWNER}/beta", scaffold(NEW))
    assert go(world) == 0
    assert world.pr_repos() == [f"{OWNER}/alpha", f"{OWNER}/gamma"]
    assert f"{OWNER}/beta: already on {NEW[:7]}" in capsys.readouterr().out
    assert not [q for q in world.writes() if "/beta/" in q[1]]


def test_repo_not_on_the_shared_kit_is_skipped(world, capsys):
    files = scaffold(OLD)
    files[".github/workflows/agent-exec.yml"] = "name: vendored\n"
    world.add_repo(f"{OWNER}/gamma", files)
    assert go(world) == 0
    assert world.pr_repos() == [f"{OWNER}/alpha", f"{OWNER}/beta"]
    assert "not on the shared kit yet" in capsys.readouterr().out


def test_existing_branch_with_pr_is_skipped_without_writes(world):
    slug = f"{OWNER}/alpha"
    world.repos[slug]["branches"][BRANCH] = world.repos[slug]["branches"]["main"]
    world.repos[slug]["prs"].append({"number": 7, "branch": BRANCH})
    assert go(world) == 0
    assert not [q for q in world.writes() if q[1].startswith(f"repos/{slug}/")]
    assert len(world.repos[slug]["prs"]) == 1
    assert world.pr_repos() == sorted(f"{OWNER}/{n}" for n in CANDIDATES)


def test_existing_branch_without_pr_fails_that_repo_only(world, capsys):
    slug = f"{OWNER}/alpha"
    world.repos[slug]["branches"][BRANCH] = world.repos[slug]["branches"]["main"]
    assert go(world) == 1
    err = capsys.readouterr().err
    assert f"{slug}: FAILED" in err and "no PR" in err
    assert world.pr_repos() == [f"{OWNER}/beta", f"{OWNER}/gamma"]
    assert not [q for q in world.writes() if q[1].startswith(f"repos/{slug}/")]


def test_api_500_on_one_repo_does_not_stop_the_rest(world, capsys):
    world.fail = lambda m, p: 500 if m == "PUT" and p.startswith(f"repos/{OWNER}/beta/contents/") else None
    assert go(world) == 1
    assert world.pr_repos() == [f"{OWNER}/alpha", f"{OWNER}/gamma"]
    assert f"{OWNER}/beta: FAILED" in capsys.readouterr().err


def test_read_error_on_one_repo_does_not_stop_the_rest(world):
    world.fail = lambda m, p: 500 if p == f"repos/{OWNER}/alpha" else None
    assert go(world) == 1
    assert world.pr_repos() == [f"{OWNER}/beta", f"{OWNER}/gamma"]


def test_only_limits_repos_and_ignores_non_portfolio_names(world):
    assert go(world, only=["beta", "outsider", "held"]) == 0
    assert world.pr_repos() == [f"{OWNER}/beta"]


def test_deletions_fail_closed(world, capsys):
    files = scaffold(OLD)
    files[".autopilot/guard.py"] = "old\n"
    manifest = json.loads(files[".autopilot/manifest.json"])
    manifest["files"][".autopilot/guard.py"] = cli._sha(b"old\n")
    files[".autopilot/manifest.json"] = json.dumps(manifest)
    world.add_repo(f"{OWNER}/alpha", files)
    assert go(world) == 1
    assert "deletions" in capsys.readouterr().err
    assert world.pr_repos() == [f"{OWNER}/beta", f"{OWNER}/gamma"]


def test_only_rollout_token_is_used(world, monkeypatch, capsys):
    monkeypatch.delenv("ROLLOUT_TOKEN")
    # GH_TOKEN is set by the fixture; with no ROLLOUT_TOKEN the run must fail closed rather than fall back to it
    assert rollout_ci.run(ns(), None, portfolio=PORTFOLIO, approved=[NEW]) == 1
    assert "ROLLOUT_TOKEN" in capsys.readouterr().err and world.reqs == []
    monkeypatch.setenv("ROLLOUT_TOKEN", "rolltok")
    assert go(world) == 0  # World.http asserts every request carried Bearer rolltok, never the GH_TOKEN value


def test_module_has_no_graphql_subprocess_git_force_or_release_token():
    src = Path(rollout_ci.__file__).read_text()
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
    assert "GH_TOKEN" not in src and "GITHUB_TOKEN" not in src
    assert not re.search(r"\bimport (subprocess|shlex)\b", src)
    assert src.count("os.environ") == 1


def test_cli_flag_routes_to_ci(monkeypatch):
    seen = {}
    monkeypatch.setattr(rollout_ci, "run", lambda n: seen.setdefault("ns", n) and 0)
    assert cli.main(["rollout", "--ci", "--kit", f"{KIT}@{NEW}", "--only", "alpha"]) == 0
    assert seen["ns"].ci and seen["ns"].only == ["alpha"] and seen["ns"].apply is False


# ---- release --ci hands over the approved sha ------------------------------------------------------------------------------------


def test_release_ci_writes_kit_sha_to_github_output(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    out.write_text("x=1\n")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    release_ci.announce_kit_sha(NEW)
    assert out.read_text() == f"x=1\nkit_sha={NEW}\n" and f"kit_sha={NEW}" in capsys.readouterr().out
    monkeypatch.delenv("GITHUB_OUTPUT")
    release_ci.announce_kit_sha(NEW)  # no file configured: print only
    with pytest.raises(release_ci.CIError):
        release_ci.announce_kit_sha("abc")
