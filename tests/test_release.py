"""`ap release`: pure planner + thin executors, driven by a fake gh. Nothing here touches the network."""

from __future__ import annotations

import argparse

import pytest

from autopilot import cli

SHA = "a" * 40
MAIN = "c" * 40  # autopilot main's head, the source= of the approval
TREE = {"runtime/x.py": "1" * 40, "README.md": "2" * 40}
APPROVALS = "me/autopilot-approved"


class World:
    """Fake GitHub: records every request, answers from mutable state."""

    def __init__(self):
        self.calls: list[str] = []
        self.main_publish = dict(TREE)
        self.kit_prs: list[dict] = []
        self.approval_prs: list[dict] = []
        self.bump_prs: dict[str, list[dict]] = {}
        self.kit_tree = dict(TREE)
        self.approved: list[str] = []
        self.fail = False

    def gh(self, path: str):
        self.calls.append(path)
        if self.fail:
            raise cli.ReleaseError(f"GET {path} failed")
        if path == "repos/me/autopilot/commits/main":
            return {"sha": MAIN}
        if "/git/trees/" in path and path.startswith("repos/me/kit/"):
            return {"truncated": False, "tree": [{"type": "blob", "path": p, "sha": h} for p, h in self.kit_tree.items()]}
        if path.startswith("repos/me/kit/pulls"):
            return self.kit_prs
        if path.startswith(f"repos/{APPROVALS}/pulls"):
            return self.approval_prs
        if "/pulls?" in path:
            return self.bump_prs.get(path.split("/pulls")[0].removeprefix("repos/"), [])
        raise AssertionError(path)


def pr(state="open", sha=None):
    return {"html_url": "https://github.com/x/pull/1", "state": "closed" if state == "merged" else state,
            "merged_at": "2026-10-18T00:00:00Z" if state == "merged" else None, "merge_commit_sha": sha}  # fmt: skip


@pytest.fixture
def world(monkeypatch):
    w = World()
    am = cli._load_runtime("automerge")
    monkeypatch.setattr(am, "fetch_approved", lambda kit: list(w.approved))
    monkeypatch.setattr(cli, "_load_runtime", lambda n: am)
    monkeypatch.setattr(cli, "main_publish_tree", lambda gh, repo, ref="main": dict(w.main_publish))
    monkeypatch.setattr(cli, "publish_tree", lambda: dict(TREE))
    monkeypatch.setattr(
        cli, "load_portfolio", lambda: {"owner": "me", "repos": {"r1": {"enabled": True}, "off": {"enabled": False}}}
    )
    return w


def ns(apply=False):
    return argparse.Namespace(kit_repo="me/kit", branch="release/v1", autopilot_repo="me/autopilot", only=[], apply=apply)


class Rec:
    def __init__(self):
        self.ran: list[str] = []

    def executors(self):
        return {
            "open_kit_pr": lambda n: self.ran.append("open_kit_pr") or "https://github.com/me/kit/pull/9",
            "open_approval_pr": lambda n, sha, src: self.ran.append(f"open_approval_pr {sha} source={src}") or 0,
            "rollout": lambda n, sha: self.ran.append(f"rollout {sha}") or 0,
        }


def plan(world):
    return cli.plan_release(cli.gather_release_state(ns(), world.gh))[0]


def test_planner_each_transition(world):
    assert plan(world) == "open_kit_pr"  # nothing done
    world.kit_prs = [pr("open")]
    assert plan(world) == "wait"  # kit PR open
    world.kit_prs = [pr("merged", SHA)]
    assert plan(world) == "open_approval_pr"  # kit merged
    world.approval_prs = [pr("open")]
    assert plan(world) == "wait"  # approval open
    world.approval_prs = [pr("merged", "b" * 40)]
    world.approved = [SHA]
    assert plan(world) == "rollout"  # approval merged, no bump PRs yet
    world.bump_prs = {"me/r1": [pr("open")]}
    assert plan(world) == "done"  # rollout done


def test_closed_prs_and_unrecorded_approval_refuse(world):
    world.kit_prs = [pr("closed")]
    assert plan(world) == "refuse"
    world.kit_prs = [pr("merged", SHA)]
    world.approval_prs = [pr("closed")]
    assert plan(world) == "refuse"
    world.approval_prs = [pr("merged", "b" * 40)]  # merged but sha not on APPROVED: fail closed
    assert plan(world) == "refuse"


def test_resume_uses_kit_merge_sha(world):
    world.kit_prs = [pr("merged", SHA)]
    rec = Rec()
    assert cli.cmd_release(ns(apply=True), world.gh, rec.executors()) == 0
    assert rec.ran == [f"open_approval_pr {SHA} source={MAIN}"]  # the approval records the commit the tree was compared against
    world.approved = [SHA]
    rec.ran.clear()
    assert cli.cmd_release(ns(apply=True), world.gh, rec.executors()) == 0
    assert rec.ran == [f"rollout {SHA}"]


def test_main_head_sha_fails_closed(world):
    assert cli.main_head_sha(world.gh, "me/autopilot") == MAIN
    for bad in (None, {}, {"sha": "main"}, {"sha": "C" * 40}, [1]):
        with pytest.raises(cli.ReleaseError):
            cli.main_head_sha(lambda p, b=bad: b, "me/autopilot")


def test_dry_run_makes_no_writes(world, capsys):
    rec = Rec()
    assert cli.cmd_release(ns(apply=False), world.gh, rec.executors()) == 0
    assert rec.ran == []
    assert "[dry run]" in capsys.readouterr().out
    world.kit_prs = [pr("merged", SHA)]
    assert cli.cmd_release(ns(apply=False), world.gh, rec.executors()) == 0
    assert rec.ran == []
    assert all(c.startswith("repos/") for c in world.calls)  # only GETs through the fake


def test_stops_with_url_when_kit_pr_not_merged(world, capsys):
    world.kit_prs = [pr("open")]
    rec = Rec()
    assert cli.cmd_release(ns(apply=True), world.gh, rec.executors()) == 0
    assert rec.ran == [] and "https://github.com/x/pull/1" in capsys.readouterr().out


def test_refuses_on_tree_mismatch(world, capsys):
    world.main_publish["runtime/x.py"] = "9" * 40  # main differs from the tree we would publish
    rec = Rec()
    assert cli.cmd_release(ns(apply=True), world.gh, rec.executors()) == 1
    assert rec.ran == [] and "differs from what export_kit makes" in capsys.readouterr().err


def test_refuses_when_merged_kit_lacks_published_tree(world):
    world.kit_prs = [pr("merged", SHA)]
    world.kit_tree["runtime/x.py"] = "9" * 40
    rec = Rec()
    assert cli.cmd_release(ns(apply=True), world.gh, rec.executors()) == 1
    assert rec.ran == []


def test_fails_closed_on_api_error(world, capsys):
    world.fail = True
    rec = Rec()
    assert cli.cmd_release(ns(apply=True), world.gh, rec.executors()) == 1
    assert rec.ran == [] and "failing closed" in capsys.readouterr().err


def test_fails_closed_on_truncated_tree(world, monkeypatch):
    monkeypatch.undo()  # use the real main_publish_tree against a truncated answer
    with pytest.raises(cli.ReleaseError):
        cli.main_publish_tree(lambda p: {"truncated": True, "tree": []}, "me/autopilot")


def test_main_publish_tree_runs_export_kit_on_main_blobs(monkeypatch):
    """The guard exports main's kit/ with the real export_kit: same input as local gives the same tree, a changed file does not."""
    kit = cli.KIT
    blobs, tree = {}, []
    for f in sorted(kit.rglob("*")):
        if f.is_file():
            data = f.read_bytes()
            sha = cli._blob_sha(data)
            blobs[sha] = data
            tree.append({"type": "blob", "path": f"kit/{f.relative_to(kit)}", "sha": sha})

    def gh(path):
        if "/git/trees/" in path:
            return {"truncated": False, "tree": tree}
        import base64

        return {"encoding": "base64", "content": base64.b64encode(blobs[path.rsplit("/", 1)[1]]).decode()}

    assert cli.main_publish_tree(gh, "me/autopilot") == cli.publish_tree()
    wf = next(e for e in tree if e["path"].startswith("kit/workflows/"))
    blobs[wf["sha"]] = blobs[wf["sha"]] + b"\n# tampered\n"  # content no longer matches its sha: fails closed
    with pytest.raises(cli.ReleaseError):
        cli.main_publish_tree(gh, "me/autopilot")


def test_real_executors_never_merge(world, monkeypatch):
    """Drive the real executors with git/gh stubbed; no command may contain a merge."""
    seen: list[list[str]] = []

    def fake_run(*args, cwd=None, check=True):
        seen.append(list(args))
        if args[:3] == ("gh", "repo", "clone"):
            import pathlib

            pathlib.Path(args[4]).mkdir(parents=True, exist_ok=True)
        if args[:2] == ("git", "symbolic-ref"):
            return "origin/main\n"
        if args[:2] == ("git", "status"):
            return " M x\n"
        if args[:3] == ("gh", "pr", "create"):
            return "https://github.com/me/kit/pull/9\n"
        return ""

    class R:
        returncode = 1
        stdout = ""
        stderr = ""

    monkeypatch.setattr(cli, "_run", fake_run)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: seen.append(list(a[0])) or R())

    def fake_export(dest):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "README.md").write_text("x")
        return ["README.md"]

    monkeypatch.setattr(cli, "export_kit", fake_export)
    assert cli.exec_open_kit_pr(ns()) == "https://github.com/me/kit/pull/9"
    kit_pushes = [c for c in seen if list(c[:2]) == ["git", "push"]]
    cli.exec_open_approval_pr(ns(), SHA, MAIN)
    flat = [" ".join(c) for c in seen]
    assert any(c.startswith("git commit -q -S") for c in flat)  # signed local commit
    assert not any(a == "merge" or a.endswith("/merge") for c in seen for a in c)  # argv-level; PR prose may say "merge"
    assert not any("--method" in c or "PUT" in c or "-X" in c for c in flat)
    # the release's own push never forces (the older `ap approve` push is outside this test's claim)
    assert kit_pushes and not any(a in ("-f", "--force", "--force-with-lease") for c in kit_pushes for a in c)
