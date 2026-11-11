"""The `since` floor: a rule's declared level binds only repos born on or after its date; older repos are grandfathered to warn.

A new repo is strict by construction and an old repo is never broken overnight, with no per-repo field to forget.
"""

import datetime
import os
import subprocess

import pytest

from autopilot.standard import engine, load_checks, validate

BASE = {
    "title": "t",
    "level": "fail",
    "label": "audited",
    "why": "w",
    "fix": "f",
}


def rules(**extra):
    # `journal-present` is a real check that fails on a bare repo, so it stands in for any new rule.
    return {"checks": [{"id": "journal-present", **BASE, **extra}]}


def git(root, *args, date=None):
    env = {**os.environ}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"{date}T12:00:00+00:00"
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(var, None)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "user.email=t@t", "-c", "user.name=t", *args],
                   cwd=root, check=True, capture_output=True, env=env)


def sub(root, name):
    p = root / name
    p.mkdir()
    return p


def born(root, date):
    (root / "README.md").write_text("x\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", ".")
    git(root, "commit", "-qm", "first", date=date)
    return root


def run_one(root, **extra):
    (r,) = engine.run(engine.Repo(root), rules=rules(**extra))
    return r


# --- validation ----------------------------------------------------------------------------------------------------


def data(**extra):
    return {"standard_version": 1, "checks": [{"id": "some-rule", **BASE, **extra}]}


def test_since_accepts_an_iso_date_string_or_a_yaml_date():
    assert validate(data(since="2026-11-10")) == []
    assert validate(data(since=datetime.date(2026, 11, 10))) == []


@pytest.mark.parametrize("bad", ["soon", "2026-13-40", "10/11/2026", 20261110, ""])
def test_since_rejects_anything_that_is_not_a_date(bad):
    problems = validate(data(since=bad))
    assert any("since" in p for p in problems), problems


def test_a_rule_without_since_is_unchanged():
    assert validate(data()) == []


# --- behaviour -----------------------------------------------------------------------------------------------------


def test_a_repo_born_on_or_after_since_keeps_the_declared_level(tmp_path):
    r = run_one(born(tmp_path, "2026-11-10"), since="2026-11-10")
    assert (r.level, r.result) == ("fail", "fail")


def test_an_older_repo_is_grandfathered_to_warn_but_still_reported_as_failing(tmp_path):
    r = run_one(born(tmp_path, "2026-10-01"), since="2026-11-10")
    assert (r.level, r.result) == ("warn", "fail")
    assert any("grandfathered" in f and "2026-11-10" in f for f in r.findings), r.findings


def test_grandfathering_is_not_noise_on_a_pass(tmp_path):
    root = born(tmp_path, "2026-10-01")
    (root / "docs").mkdir()
    (root / "docs/journal.md").write_text("x\n")
    r = run_one(root, since="2026-11-10")
    assert r.result == "pass" and not any("grandfathered" in f for f in r.findings)


def test_a_rule_without_since_ignores_the_repos_age(tmp_path):
    r = run_one(born(tmp_path, "2020-01-01"))
    assert (r.level, r.result) == ("fail", "fail")


def test_a_warn_rule_stays_warn_whatever_the_age(tmp_path):
    r = run_one(born(tmp_path, "2026-12-01"), since="2026-11-10", level="warn")
    assert r.level == "warn"


def test_a_repo_with_no_commit_yet_is_new_and_strict(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")  # what `ap new` leaves before the first commit
    r = run_one(tmp_path, since="2026-11-10")
    assert r.level == "fail"


def test_a_plain_directory_is_treated_as_new_and_strict(tmp_path):
    assert run_one(tmp_path, since="2026-11-10").level == "fail"


def test_a_directory_inside_another_repo_does_not_borrow_that_repos_age(tmp_path):
    outer = born(sub(tmp_path, "outer"), "2020-01-01")
    inner = outer / "inner"
    inner.mkdir()
    assert run_one(inner, since="2026-11-10").level == "fail"


def test_a_shallow_clone_of_an_old_repo_is_grandfathered_not_mistaken_for_new(tmp_path):
    src = born(sub(tmp_path, "src"), "2020-01-01")
    (src / "more.txt").write_text("y\n")
    git(src, "add", ".")
    git(src, "commit", "-qm", "later", date="2026-11-11")  # the only commit a depth-1 clone can see
    dest = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{src}", str(dest)], check=True, capture_output=True)
    assert run_one(dest, since="2026-11-10").level == "warn"


def test_exit_code_follows_the_effective_level(tmp_path):
    old = engine.run(engine.Repo(born(sub(tmp_path, "o"), "2026-10-01")), rules=rules(since="2026-11-10"))
    new = engine.run(engine.Repo(born(sub(tmp_path, "n"), "2026-11-11")), rules=rules(since="2026-11-10"))
    assert engine.exit_code(old) == 0
    assert engine.exit_code(new) == 1


def test_the_shipped_rules_still_validate():
    assert validate(load_checks()) == []


# --- an age the caller knows beats the one the checkout can show --------------------------------------------------------------


def test_a_known_age_overrides_the_first_commit_date(tmp_path):
    root = born(tmp_path, "2020-01-01")  # the history says old
    new = engine.run(engine.Repo(root, born_on=datetime.date(2026, 11, 12)), rules=rules(since="2026-11-10"))[0]
    assert new.level == "fail"
    root2 = born(sub(tmp_path, "r2"), "2026-11-20")  # the history says new
    old = engine.run(engine.Repo(root2, born_on=datetime.date(2025, 1, 1)), rules=rules(since="2026-11-10"))[0]
    assert old.level == "warn"


def test_a_known_age_works_where_there_is_no_history_at_all(tmp_path):
    # A shallow clone: no real first commit, but GitHub says when the repo was created.
    (tmp_path / "README.md").write_text("x\n")
    assert engine.run(engine.Repo(tmp_path, born_on=datetime.date(2025, 1, 1)), rules=rules(since="2026-11-10"))[0].level == "warn"
    assert engine.run(engine.Repo(tmp_path, born_on=datetime.date(2026, 11, 10)), rules=rules(since="2026-11-10"))[0].level == "fail"
