import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kit" / "runtime"))
from patchcheck import check_patch  # noqa: E402


def d(path, body="+x = 1\n", head="", other=None):
    return f"diff --git a/{other or path} b/{path}\n{head}--- a/{path}\n+++ b/{path}\n@@ -0,0 +1 @@\n{body}"


def kinds(t, **kw):
    return {v.check for v in check_patch(t, **kw)}


def test_clean_patch_passes():
    assert check_patch(d("src/a.py", "+def f():\n+    return 1\n")) == []


def test_symlink_submodule_mode_binary_rename():
    assert "symlink" in kinds(d("link", head="new file mode 120000\n"))
    assert "submodule" in kinds(d("sub", head="new file mode 160000\n"))
    assert "mode" in kinds(d("run.sh", head="new file mode 100755\n"))
    assert "mode" in kinds(d("run.sh", head="old mode 100644\nnew mode 100755\n"))
    assert "binary" in kinds(d("a.png", body="", head="GIT binary patch\n"))
    assert "binary" in kinds("diff --git a/x b/x\nBinary files a/x and b/x differ\n")
    assert "rename" in kinds(d("new.py", other="old.py"))


def test_path_tricks_and_git_internals():
    for p in ["../outside.py", "/etc/passwd", "a/../../b", ".git/hooks/pre-commit", "~/x"]:
        assert "path" in kinds(d(p)), p


def test_guard_rules_still_apply():
    assert "protected-path" in kinds(d(".github/workflows/ci.yml"))
    assert "secret" in kinds(d("a.py", '+K = "AKIAABCDEFGHIJKLMNOP"\n'))
    assert "comms" in kinds(d("a.py", "+import slack_sdk\n"))
    assert "size" in kinds(d("a.py", "+x\n" * 50), max_diff_lines=10)


def test_extra_protected_and_nul():
    assert "protected-path" in kinds(d("kit/runtime/guard.py"), protected=["kit/runtime/**"])
    assert "patch-format" in kinds(d("a.py") + "\x00")
