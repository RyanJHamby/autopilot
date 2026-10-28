import base64
import subprocess

import pytest

from autopilot.apx import checks, committer


class FakeApi:
    def __init__(self):
        self.calls = []

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path.endswith("/git/commits/BASE"):
            return {"tree": {"sha": "TREE0"}}
        if path.endswith("/git/blobs"):
            return {"sha": "B" + str(len(self.calls))}
        if path.endswith("/git/trees"):
            return {"sha": "TREE1"}
        if path.endswith("/git/commits"):
            return {"sha": "C1"}
        if path.endswith("/pulls"):
            return {"number": 7}
        return {}


def test_check_run_payload_and_truncation():
    a = FakeApi()
    checks.post_check(a, "o/r", "abc", "guard / guard", False, "x" * 70000, details_url="http://u")
    m, p, b = a.calls[0]
    assert (m, p) == ("POST", "/repos/o/r/check-runs")
    assert b["name"] == "guard / guard" and b["conclusion"] == "failure" and b["status"] == "completed"
    assert len(b["output"]["summary"]) < 65535 and b["details_url"] == "http://u"
    checks.post_check(a, "o/r", "abc", "build", True, "")
    assert a.calls[1][2]["conclusion"] == "success" and a.calls[1][2]["output"]["summary"] == "build"
    checks.post_pending(a, "o/r", "abc", "guard / guard")
    assert a.calls[2][2]["status"] == "in_progress" and "conclusion" not in a.calls[2][2]


def test_commit_flow_order_unsigned_author_and_deletion():
    a = FakeApi()
    ch = [committer.FileChange("a.txt", "100644", b"hi"), committer.FileChange("old.txt", "100644", None)]
    out = committer.commit_and_pr(a, "o/r", "BASE", "agent/5-1", ch, message="m", title="t", body="b", base_branch="main")
    assert out == {"commit": "C1", "pr_number": 7}

    def at(suffix, method="POST"):
        return next(i for i, c in enumerate(a.calls) if c[0] == method and c[1].endswith(suffix))

    assert at("/git/commits") < at("/git/refs") < at("/pulls")
    commit_body = next(c[2] for c in a.calls if c[1].endswith("/git/commits") and c[0] == "POST")
    assert "author" not in commit_body and "committer" not in commit_body and commit_body["parents"] == ["BASE"]
    tree_body = next(c[2] for c in a.calls if c[1].endswith("/git/trees"))
    assert tree_body["base_tree"] == "TREE0"
    assert {e["path"]: e["sha"] for e in tree_body["tree"]}["old.txt"] is None
    blob = next(c[2] for c in a.calls if c[1].endswith("/git/blobs"))
    assert base64.b64decode(blob["content"]) == b"hi"


def test_only_agent_branches_and_nonempty():
    with pytest.raises(ValueError):
        committer.commit_and_pr(
            FakeApi(),
            "o/r",
            "BASE",
            "main",
            [committer.FileChange("a", "100644", b"x")],
            message="m",
            title="t",
            body="b",
            base_branch="main",
        )
    with pytest.raises(ValueError):
        committer.commit_and_pr(FakeApi(), "o/r", "BASE", "agent/1-1", [], message="m", title="t", body="b", base_branch="main")


def _repo(tmp_path):
    def g(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)

    g("init", "-q")
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    (tmp_path / "keep.txt").write_text("k")
    (tmp_path / "gone.txt").write_text("g")
    g("add", ".")
    # commit-tree makes an unsigned scratch commit without touching any signing config
    tree = subprocess.run(["git", "-C", str(tmp_path), "write-tree"], check=True, capture_output=True, text=True).stdout.strip()
    sha = subprocess.run(
        ["git", "-C", str(tmp_path), "commit-tree", tree, "-m", "init"], check=True, capture_output=True, text=True
    ).stdout.strip()
    g("update-ref", "HEAD", sha)
    return g


def test_changes_from_worktree_reads_adds_mods_deletes_and_exec_bit(tmp_path):
    _repo(tmp_path)
    (tmp_path / "keep.txt").write_text("k2")
    (tmp_path / "gone.txt").unlink()
    (tmp_path / "new.sh").write_text("#!/bin/sh\n")
    (tmp_path / "new.sh").chmod(0o755)
    got = {c.path: c for c in committer.changes_from_worktree(tmp_path, "HEAD")}
    assert got["keep.txt"].content == b"k2"
    assert got["gone.txt"].content is None
    assert got["new.sh"].mode == "100755"


def test_changes_from_worktree_refuses_symlink(tmp_path):
    _repo(tmp_path)
    (tmp_path / "ln").symlink_to("keep.txt")
    with pytest.raises(ValueError):
        committer.changes_from_worktree(tmp_path, "HEAD")
