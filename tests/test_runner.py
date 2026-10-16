import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kit" / "runtime"))
from runner import RunResult, Task, Usage, process  # noqa: E402


def make_worktree(tmp_path):
    def g(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)

    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    g("config", "commit.gpgsign", "false")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    g("add", "-A")
    g("commit", "-qm", "base")
    return tmp_path


class Stub:
    name = "stub"

    def __init__(self, edit):
        self.edit = edit

    def run(self, task, worktree):
        self.edit(worktree)
        return RunResult("did a thing", Usage(input_tokens=10, output_tokens=5))


def run(tmp_path, edit, **kw):
    return process(Stub(edit), Task(issue=1, prompt="p"), make_worktree(tmp_path), **kw)


def test_clean_edit_is_committable_and_usage_passes_through(tmp_path):
    o = run(tmp_path, lambda w: (w / "src" / "b.py").write_text("def f():\n    return 2\n"))
    assert o.ok and "src/b.py" in o.patch and o.usage.output_tokens == 5 and o.summary == "did a thing"


def test_runner_that_changes_nothing_is_not_ok(tmp_path):
    o = run(tmp_path, lambda w: None)
    assert not o.ok and "empty patch" in o.violations[0]


def test_protected_path_blocked_even_though_runner_wrote_it(tmp_path):
    def edit(w):
        (w / ".github" / "workflows").mkdir(parents=True)
        (w / ".github" / "workflows" / "x.yml").write_text("on: push\n")

    o = run(tmp_path, edit)
    assert not o.ok and any("protected-path" in v for v in o.violations)


def test_symlink_and_executable_blocked(tmp_path):
    def edit(w):
        (w / "src" / "link").symlink_to("/etc/passwd")
        s = w / "src" / "run.sh"
        s.write_text("echo hi\n")
        s.chmod(0o755)

    o = run(tmp_path, edit)
    kinds = " ".join(o.violations)
    assert not o.ok and "symlink" in kinds and "mode" in kinds


def test_secret_in_new_file_blocked(tmp_path):
    o = run(tmp_path, lambda w: (w / "src" / "k.py").write_text('K = "AKIAABCDEFGHIJKLMNOP"\n'))
    assert not o.ok and any("secret" in v for v in o.violations)


def test_runner_cannot_hide_changes_by_committing_them(tmp_path):
    def edit(w):
        (w / ".github").mkdir()
        (w / ".github" / "ci.yml").write_text("x: 1\n")
        for a in (["add", "-A"], ["commit", "-qm", "sneaky"]):
            subprocess.run(["git", "-C", str(w), *a], check=True, capture_output=True)
        (w / "src" / "b.py").write_text("y = 2\n")  # innocuous follow-up edit

    o = run(tmp_path, edit)
    assert not o.ok and any("protected-path" in v for v in o.violations)
