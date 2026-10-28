import subprocess
from pathlib import Path

import pytest

from autopilot.apx import guardlane as gl

KIT = Path(__file__).resolve().parent.parent / "kit"
# built at runtime so this file itself carries no key-shaped literal
FAKE_KEY = "AK" + "IA" + "ABCDEFGHIJKLMNOP"


def git(d, *a):
    return subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True, text=True).stdout.strip()


def commit(d, files, parent=None, ref="HEAD"):
    """Unsigned scratch commit built with plumbing so no signing config is touched."""
    for name, text in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    git(d, "add", "-A")
    tree = git(d, "write-tree")
    args = ["commit-tree", tree, "-m", "c"] + (["-p", parent] if parent else [])
    sha = git(d, *args)
    git(d, "update-ref", ref, sha)
    return sha


def mkrepo(tmp_path, base_cfg="", head_files=None):
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q")
    git(r, "config", "user.email", "t@example.com")  # CI runners have no global identity
    git(r, "config", "user.name", "t")
    base = commit(r, {"README.md": "x\n", ".autopilot/repo.yaml": base_cfg}, ref="refs/remotes/origin/main")
    git(r, "update-ref", "HEAD", base)
    head = commit(r, head_files or {}, parent=base, ref="refs/heads/work")
    git(r, "reset", "-q", "--hard", head)
    return r


def run(r, head_ref, tmp_path, name="t"):
    t = tmp_path / name
    t.mkdir()
    return gl.run_guard(r, KIT, base="origin/main", head="HEAD", head_ref=head_ref, tmp=t)


def test_validate_kit_rejects_bad_inputs():
    gl.validate_kit("o/kit", "a" * 40)
    for ref in ["", "main", "A" * 40, "a" * 39, "a" * 41, "g" * 40]:
        with pytest.raises(gl.KitError):
            gl.validate_kit("o/kit", ref)
    for repo in ["", "kit", "a/b/c", "o/k it", "o/k;rm"]:
        with pytest.raises(gl.KitError):
            gl.validate_kit(repo, "a" * 40)


def test_agent_ref_detection():
    assert gl.is_agent_ref("agent/12-3") and gl.is_agent_ref("claude/x")
    assert not gl.is_agent_ref("feature/agent/x") and not gl.is_agent_ref("main")


def test_clean_change_passes(tmp_path):
    r = mkrepo(tmp_path, head_files={"src/a.py": "x = 1\n"})
    ok, out = run(r, "agent/1-1", tmp_path)
    assert ok, out


def test_secret_fails_for_everyone(tmp_path):
    r = mkrepo(tmp_path, head_files={"src/a.py": f'K = "{FAKE_KEY}"\n'})
    ok, out = run(r, "feature/x", tmp_path)
    assert not ok and "secret" in out


def test_protected_path_blocked_only_for_agent_refs(tmp_path):
    r = mkrepo(tmp_path, head_files={".github/workflows/x.yml": "on: push\n"})
    assert not run(r, "agent/1-1", tmp_path)[0]
    assert run(r, "feature/x", tmp_path, "t2")[0]


def test_config_comes_from_base_not_head(tmp_path):
    # base forbids new deps via charter; the head branch tries to relax it by editing repo.yaml
    base_cfg = "charter:\n  allow_new_dependencies: false\n"
    r = mkrepo(
        tmp_path,
        base_cfg=base_cfg,
        head_files={
            ".autopilot/repo.yaml": "charter:\n  allow_new_dependencies: true\n",
            "package.json": '{\n  "dependencies": {\n    "left-pad": "1.0.0"\n  }\n}\n',
        },
    )
    ok, out = run(r, "agent/1-1", tmp_path)
    assert not ok and "new-dependency" in out
