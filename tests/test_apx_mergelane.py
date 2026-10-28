import subprocess
import sys

from autopilot.apx import mergelane as ml


def test_env_is_allowlisted_with_token_and_repo_context(tmp_path):
    src = {"PATH": "/usr/bin", "AWS_SECRET_ACCESS_KEY": "a", "GITHUB_TOKEN": "g", "CLAUDE_CODE_OAUTH_TOKEN": "c"}
    env = ml.merge_env("ghs_app", "o/r", "o", "o/kit", tmp_path, src)
    assert set(env) == {"PATH", "HOME", "GH_TOKEN", "GH_REPO", "GITHUB_REPOSITORY_OWNER", "KIT_REPO"}
    assert env["GH_TOKEN"] == "ghs_app" and env["GH_REPO"] == "o/r"


def test_no_policy_means_nothing_to_do_and_no_subprocess(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not run automerge.py without a policy")

    monkeypatch.setattr(ml.subprocess, "run", boom)
    rc, out = ml.run_automerge(
        tmp_path,
        tmp_path,
        repo="o/r",
        pr=1,
        head_sha="a" * 40,
        token="t",
        owner="o",
        kit_repo="o/kit",
        base="origin/main",
        tmp=tmp_path,
    )
    assert rc == 0 and "nothing to do" in out


def test_policy_comes_from_checkout_and_argv_is_exact(tmp_path, monkeypatch):
    co = tmp_path / "co"
    (co / ".autopilot").mkdir(parents=True)
    (co / ".autopilot" / "merge-policy.yaml").write_text("auto_merge_classes: [docs-only]\n")
    seen = {}

    def fake(argv, **kw):
        seen["argv"], seen["env"], seen["cwd"] = argv, kw["env"], kw["cwd"]
        return subprocess.CompletedProcess(argv, 0, stdout="MERGE docs-only\n", stderr="")

    monkeypatch.setattr(ml.subprocess, "run", fake)
    tmp = tmp_path / "t"
    tmp.mkdir()
    sha = "b" * 40
    rc, out = ml.run_automerge(
        co,
        tmp_path / "kit",
        repo="o/r",
        pr=7,
        head_sha=sha,
        token="tok",
        owner="o",
        kit_repo="o/kit",
        base="origin/main",
        tmp=tmp,
        dry_run=True,
    )
    a = seen["argv"]
    assert rc == 0 and "MERGE" in out and a[0] == sys.executable and a[1].endswith("kit/runtime/automerge.py")
    assert a[a.index("--pr") + 1] == "7" and a[a.index("--head-sha") + 1] == sha and "--dry-run" in a
    assert (tmp / "merge-policy.yaml").read_text().startswith("auto_merge_classes")
    assert "tok" not in " ".join(a) and seen["cwd"] == co
