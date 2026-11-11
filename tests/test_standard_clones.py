"""Which clone of a repo gets audited, and what is said about it.

The motivating case is real: one repo had a stale copy under ~/dev (4 commits behind) and its live checkout under ~/Documents, and the
old rule (first directory name in ~/dev) audited the stale one. These tests use real git repos with dated commits and a real local
origin, so "behind N" is computed by git, not faked."""

import os
import subprocess
from pathlib import Path

import pytest

from autopilot import cli
from autopilot.standard import command

NAME = "proj"


def sh(cwd, *args, date=None):
    env = {**os.environ}
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(var, None)
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"{date}T12:00:00+00:00"
    r = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd, capture_output=True, text=True, env=env, check=True,
    )
    return r.stdout.strip()


def repo_in(root: Path, dirname: str, date: str, name: str = NAME) -> Path:
    """A one-commit repo at root/dirname, dated `date`, whose origin URL says it is the GitHub repo `name`."""
    d = root / dirname
    d.mkdir(parents=True)
    (d / "README.md").write_text("x\n")
    sh(d, "init", "-q", "-b", "main")
    sh(d, "add", ".")
    sh(d, "commit", "-qm", "first", date=date)
    sh(d, "remote", "add", "origin", f"https://github.com/o/{name}.git")
    return d


def by_origin(d: Path) -> str:
    return sh(d, "remote", "get-url", "origin").rsplit("/", 1)[-1].removesuffix(".git")


# --- choosing among clones ---------------------------------------------------------------------------------------------


def test_the_clone_with_the_newest_commit_wins_whatever_its_directory_name(tmp_path):
    dev, docs = tmp_path / "dev", tmp_path / "docs"
    repo_in(dev, "aaa-stale", "2026-10-01")  # first by name, but old
    live = repo_in(docs, "zzz-live", "2026-11-09")
    assert command.find_clone(NAME, [dev, docs], by_origin) == live


def test_when_commits_are_equally_new_the_first_by_name_wins_so_the_choice_is_deterministic(tmp_path):
    first = repo_in(tmp_path, "a", "2026-11-01")
    repo_in(tmp_path, "b", "2026-11-01")
    assert command.find_clone(NAME, tmp_path, by_origin) == first


def test_every_root_is_searched_and_a_single_path_or_string_still_works(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    only_in_b = repo_in(b, "x", "2026-11-01")
    assert command.find_clone(NAME, [a, b], by_origin) == only_in_b  # a does not exist at all
    assert command.find_clone(NAME, b, by_origin) == only_in_b
    assert command.find_clone(NAME, str(b), by_origin) == only_in_b


def test_a_repo_with_no_clone_anywhere_is_none(tmp_path):
    assert command.find_clone(NAME, [tmp_path], by_origin) is None


def test_a_clone_reachable_by_two_paths_is_one_candidate(tmp_path):
    real = repo_in(tmp_path / "dev", "x", "2026-11-01")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "link").symlink_to(real)
    assert len(command.find_clones(NAME, [tmp_path / "dev", tmp_path / "docs"], by_origin)) == 1


def test_the_note_names_every_clone_when_there_are_several_and_is_empty_for_one(tmp_path):
    stale = repo_in(tmp_path / "dev", "stale", "2026-10-01")
    live = repo_in(tmp_path / "docs", "live", "2026-11-09")
    chosen, note = command.pick_clone(NAME, [stale, live])
    assert chosen == live and "2 clones of proj" in note and str(live) in note and str(stale) in note
    assert command.pick_clone(NAME, [live]) == (live, "")
    assert command.pick_clone(NAME, []) == (None, "")


def test_a_worktree_never_beats_the_main_checkout_even_with_a_newer_commit(tmp_path):
    # A task worktree on a feature branch is not "the repo"; the checkout with a real .git directory is.
    main = repo_in(tmp_path, "main-checkout", "2026-10-01")
    wt = tmp_path / "task-wt"
    sh(main, "worktree", "add", "-q", "-b", "feature", str(wt))
    (wt / "f.txt").write_text("f\n")
    sh(wt, "add", ".")
    sh(wt, "commit", "-qm", "newer", date="2026-11-09")
    assert (wt / ".git").is_file() and (main / ".git").is_dir()
    assert command.find_clone(NAME, tmp_path, by_origin) == main


def test_worktrees_are_chosen_only_when_there_is_no_main_checkout(tmp_path):
    main = repo_in(tmp_path / "elsewhere", "main-checkout", "2026-10-01")
    wt = tmp_path / "wts" / "only-wt"
    (tmp_path / "wts").mkdir()
    sh(main, "worktree", "add", "-q", "-b", "feature", str(wt))
    assert command.find_clone(NAME, tmp_path / "wts", by_origin) == wt


def test_the_note_lists_at_most_three_others_and_counts_the_rest(tmp_path):
    clones = [repo_in(tmp_path, f"c{i}", f"2026-10-0{i + 1}") for i in range(7)]
    best, note = command.pick_clone(NAME, clones)
    assert best == clones[-1] and "7 clones of proj" in note
    assert note.count("branch main") == 3 and "and 3 more" in note


# --- describing a clone: branch, dirty, behind --------------------------------------------------------------------------


def with_real_origin(tmp_path):
    """(origin bare repo, clone) where the clone really is a git clone, so origin/HEAD exists."""
    seed = repo_in(tmp_path, "seed", "2026-11-01")
    origin = tmp_path / "origin.git"
    sh(tmp_path, "clone", "-q", "--bare", str(seed), str(origin))
    clone = tmp_path / "clone"
    sh(tmp_path, "clone", "-q", str(origin), str(clone))
    return origin, clone


def push_one_more_commit(tmp_path, origin):
    other = tmp_path / "other"
    sh(tmp_path, "clone", "-q", str(origin), str(other))
    (other / "new.txt").write_text("n\n")
    sh(other, "add", ".")
    sh(other, "commit", "-qm", "later", date="2026-11-09")
    sh(other, "push", "-q", "origin", "HEAD")


def test_a_fresh_clone_is_on_main_clean_and_not_behind(tmp_path):
    _, clone = with_real_origin(tmp_path)
    info = command.describe_clone(clone)
    assert (info["branch"], info["dirty"], info["behind"], info["ahead"]) == ("main", False, 0, 0)


def test_a_clone_is_reported_behind_only_after_a_fetch_shows_it(tmp_path):
    origin, clone = with_real_origin(tmp_path)
    push_one_more_commit(tmp_path, origin)
    assert command.describe_clone(clone)["behind"] == 0  # nothing fetched yet: local git cannot know
    sh(clone, "fetch", "-q")
    info = command.describe_clone(clone)
    assert info["behind"] == 1 and info["fetched_days"] is not None and info["fetched_days"] < 1


def test_a_clone_that_was_never_fetched_says_so_instead_of_claiming_it_is_current(tmp_path):
    _, clone = with_real_origin(tmp_path)
    info = command.describe_clone(clone)
    assert info["fetched_days"] is None
    assert "never fetched" in command.describe_text(info)


def test_an_edited_tracked_file_makes_a_clone_dirty_but_an_untracked_one_does_not(tmp_path):
    _, clone = with_real_origin(tmp_path)
    (clone / "scratch.txt").write_text("x\n")
    assert command.describe_clone(clone)["dirty"] is False
    (clone / "README.md").write_text("changed\n")
    assert command.describe_clone(clone)["dirty"] is True


def test_the_text_says_branch_dirty_and_behind(tmp_path):
    origin, clone = with_real_origin(tmp_path)
    push_one_more_commit(tmp_path, origin)
    sh(clone, "fetch", "-q")
    (clone / "README.md").write_text("changed\n")
    text = command.describe_text(command.describe_clone(clone))
    assert "branch main" in text and "dirty" in text and "behind 1" in text


def test_a_repo_with_no_origin_ref_is_described_without_inventing_a_count(tmp_path):
    d = repo_in(tmp_path, "solo", "2026-11-01")  # remote URL is fake, nothing was ever fetched
    info = command.describe_clone(d)
    assert info["behind"] is None and "no origin ref" in command.describe_text(info)


# --- the command ------------------------------------------------------------------------------------------------------------


@pytest.fixture
def portfolio(monkeypatch):
    pf = {"owner": "o", "repos": {NAME: {"enabled": True}}}
    monkeypatch.setattr(cli, "load_portfolio", lambda: pf)
    return pf


def test_portfolio_check_audits_the_live_clone_and_says_there_were_two(tmp_path, portfolio, capsys):
    stale = repo_in(tmp_path / "dev", "aaa-stale", "2026-10-01")
    live = repo_in(tmp_path / "docs", "zzz-live", "2026-11-09")
    cli.main(["standard", "check", "--offline", "--portfolio", "--root", str(tmp_path / "dev"), "--root", str(tmp_path / "docs")])
    out = capsys.readouterr().out
    assert f"== {NAME}  ({live})" in out
    assert "NOTE" in out and "2 clones of proj" in out and str(stale) in out


def test_portfolio_check_prints_a_one_line_clone_header(tmp_path, portfolio, capsys):
    repo_in(tmp_path / "dev", "only", "2026-11-09")
    cli.main(["standard", "check", "--offline", "--portfolio", "--root", str(tmp_path / "dev")])
    assert "branch main" in capsys.readouterr().out


def test_json_output_carries_the_clone_details(tmp_path, portfolio, capsys):
    import json

    repo_in(tmp_path / "dev", "only", "2026-11-09")
    cli.main(["standard", "check", "--offline", "--portfolio", "--root", str(tmp_path / "dev"), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["repos"][0]["clone"]["branch"] == "main"


def test_a_missing_clone_names_every_root_that_was_searched(tmp_path, portfolio, capsys):
    cli.main(["standard", "check", "--offline", "--portfolio", "--root", str(tmp_path / "a"), "--root", str(tmp_path / "b")])
    out = capsys.readouterr().out
    assert "no clone of proj" in out and str(tmp_path / "a") in out and str(tmp_path / "b") in out


def test_with_no_root_given_the_defaults_are_dev_and_documents():
    assert command.DEFAULT_ROOTS == ("~/dev", "~/Documents")
