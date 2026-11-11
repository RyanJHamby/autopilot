"""`ap enable REPO`: reviving a repo is the moment agents start writing code in it, so it is held to the *current* standard, not the one
it was grandfathered under. An old repo normally only warns about rules newer than it; here those warnings are blockers unless the owner
says --allow-gaps. Pausing, resuming and re-asserting `enabled` on repos that already run are not revivals and are never gated."""

import argparse
import datetime
import os
import subprocess
from pathlib import Path

import pytest

from autopilot import cli
from autopilot.standard import command, engine, waivers

NAME = "proj"
REAL_RUN = subprocess.run


def git(cwd, *args, date="2025-01-01"):
    env = {**os.environ, "GIT_AUTHOR_DATE": f"{date}T12:00:00+00:00", "GIT_COMMITTER_DATE": f"{date}T12:00:00+00:00"}
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(var, None)
    return REAL_RUN(["git", "-c", "commit.gpgsign=false", "-c", "user.email=t@t", "-c", "user.name=t", *args],
                    cwd=cwd, capture_output=True, text=True, env=env, check=True)


def old_repo(root: Path, name: str = NAME, files=None) -> Path:
    """A repo born long before the day-0 rules, with a fake origin so repo_name finds it."""
    d = root / name
    d.mkdir(parents=True)
    for rel, text in {"README.md": "x\n", **(files or {})}.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(text)
    git(d, "init", "-q", "-b", "main")
    git(d, "add", ".")
    git(d, "commit", "-qm", "first")
    git(d, "remote", "add", "origin", f"https://github.com/o/{name}.git")
    return d


# --- the engine's force_new -----------------------------------------------------------------------------------------------------


def test_force_new_holds_an_old_repo_to_the_rules_it_was_grandfathered_under(tmp_path):
    root = old_repo(tmp_path)
    normal = engine.run(engine.Repo(root), only=["hook-wired"])[0]
    forced = engine.run(engine.Repo(root, force_new=True), only=["hook-wired"])[0]
    assert (normal.level, forced.level) == ("warn", "fail") and normal.result == forced.result == "fail"


def test_force_new_beats_a_known_age(tmp_path):
    root = old_repo(tmp_path)
    r = engine.run(engine.Repo(root, born_on=datetime.date(2020, 1, 1), force_new=True), only=["hook-wired"])[0]
    assert r.level == "fail"


# --- the revive check ----------------------------------------------------------------------------------------------------------


def gh_for(public=False):
    def gh(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, "false" if public else "true", "")

    return gh


PF = {"owner": "o", "repos": {NAME: {"enabled": False, "mode": "dormant"}}}


def test_the_revive_check_lists_every_fail_level_gap_an_old_repo_was_excused_from(tmp_path):
    old_repo(tmp_path)
    path, gaps, notes = command.revive_check(NAME, PF, [tmp_path], None, lambda d: NAME, gh_for(), [], datetime.date(2026, 11, 10))
    assert path == tmp_path / NAME
    ids = {g.split(":")[0] for g in gaps}
    assert {"hook-wired", "secret-scan-wired", "standard-wired"} <= ids


def test_a_clean_repo_has_no_revive_gaps(tmp_path):
    from autopilot.scaffold import core

    d = tmp_path / NAME
    d.mkdir()
    ctx = core.Ctx(name=NAME, owner="o", public=False, kind="app", empty=True, has_workflows=True)
    core.write(d, core.plan(d, ctx))
    for rel in ("AGENTS.md",):
        (d / rel).write_text("# rules\n")
    (d / "CLAUDE.md").write_text("@AGENTS.md\n")
    git(d, "init", "-q", "-b", "main")
    git(d, "add", ".")
    git(d, "commit", "-qm", "first")
    git(d, "remote", "add", "origin", f"https://github.com/o/{NAME}.git")
    _, gaps, _ = command.revive_check(NAME, PF, [tmp_path], None, lambda p: NAME, gh_for(), [], datetime.date(2026, 11, 10))
    assert gaps == []


def test_a_live_waiver_excuses_a_revive_gap(tmp_path):
    old_repo(tmp_path)
    today = datetime.date(2026, 11, 10)
    wv = {"repo": NAME, "rule": "hook-wired", "owner": "me", "reason": "adopting next week", "granted": today, "expires": today + datetime.timedelta(days=10)}
    _, gaps, _ = command.revive_check(NAME, PF, [tmp_path], None, lambda d: NAME, gh_for(), [wv], today)
    assert "hook-wired" not in {g.split(":")[0] for g in gaps}


def test_an_explicit_path_is_used_instead_of_searching(tmp_path):
    elsewhere = old_repo(tmp_path / "wherever", name="odd-dir")
    path, _, _ = command.revive_check(NAME, PF, [tmp_path / "nowhere"], elsewhere, lambda d: NAME, gh_for(), [], datetime.date(2026, 11, 10))
    assert path == elsewhere


def test_no_clone_anywhere_is_none(tmp_path):
    path, gaps, notes = command.revive_check(NAME, PF, [tmp_path], None, lambda d: NAME, gh_for(), [], datetime.date(2026, 11, 10))
    assert path is None and gaps == []


# --- ap enable ---------------------------------------------------------------------------------------------------------------


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A portfolio with the dormant repo, a fake gh that records `variable set`, and no real waivers file."""
    monkeypatch.setattr(cli, "load_portfolio", lambda: PF)
    monkeypatch.setattr(waivers, "read_base", lambda root: ("", ""))
    sets = []

    def fake(cmd, **kw):
        if cmd[:1] != ["gh"]:
            return REAL_RUN(cmd, **kw)
        if cmd[:3] == ["gh", "variable", "set"]:
            sets.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, "true", "")

    monkeypatch.setattr(cli.subprocess, "run", fake)
    return type("W", (), {"sets": sets, "root": tmp_path})


def enable(root, **kw):
    ns = argparse.Namespace(cmd="enable", repo=NAME, apply=True, allow_gaps=False, path=None, root=[str(root)])
    for k, v in kw.items():
        setattr(ns, k, v)
    return cli.cmd_vars(ns)


def test_enable_refuses_a_repo_with_gaps_and_sets_nothing(world, capsys):
    old_repo(world.root)
    assert enable(world.root) == 1
    out = capsys.readouterr().out
    assert "hook-wired" in out and "--allow-gaps" in out
    assert world.sets == []


def test_a_dry_run_also_prints_the_gaps_and_refuses(world, capsys):
    old_repo(world.root)
    assert enable(world.root, apply=False) == 1
    assert "hook-wired" in capsys.readouterr().out and world.sets == []


def test_allow_gaps_proceeds_and_still_lists_what_was_waved_through(world, capsys):
    old_repo(world.root)
    assert enable(world.root, allow_gaps=True) == 0
    assert "hook-wired" in capsys.readouterr().out
    assert len(world.sets) == 1 and "AUTOPILOT_ENABLED" in world.sets[0]


def test_enable_refuses_when_there_is_no_clone_to_check(world, capsys):
    assert enable(world.root) == 1
    assert "no clone" in capsys.readouterr().out and world.sets == []


def test_allow_gaps_does_not_override_a_missing_clone_it_cannot_see_the_repo(world, capsys):
    assert enable(world.root, allow_gaps=True) == 1 and world.sets == []


def test_pause_and_resume_are_never_gated(world):
    for cmd in ("pause", "resume"):
        assert enable(world.root, cmd=cmd) == 0
    assert len(world.sets) == 2


def test_enable_with_no_repo_named_reasserts_the_enabled_repos_without_gating(world, monkeypatch):
    pf = {"owner": "o", "repos": {"live": {"enabled": True}}}
    monkeypatch.setattr(cli, "load_portfolio", lambda: pf)
    assert enable(world.root, repo=None) == 0 and len(world.sets) == 1


def test_a_restricted_repo_is_still_refused(world, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_portfolio", lambda: {"owner": "o", "repos": {NAME: {"data_class": "restricted"}}})
    assert enable(world.root) == 1 and "restricted" in capsys.readouterr().out and world.sets == []


def test_a_failed_variable_set_is_a_failure_not_a_silent_zero(world, monkeypatch):
    old_repo(world.root)

    def failing(cmd, **kw):
        if cmd[:3] == ["gh", "variable", "set"]:
            return subprocess.CompletedProcess(cmd, 1, "", "forbidden")
        return REAL_RUN(cmd, **kw) if cmd[:1] != ["gh"] else subprocess.CompletedProcess(cmd, 0, "true", "")

    monkeypatch.setattr(cli.subprocess, "run", failing)
    assert enable(world.root, allow_gaps=True) == 1


def test_onboard_finish_stops_when_the_enable_step_refuses(monkeypatch):
    monkeypatch.setattr(cli, "load_portfolio", lambda: PF)
    monkeypatch.setattr(cli, "cmd_ruleset", lambda ns: 0)
    monkeypatch.setattr(cli, "cmd_vars", lambda ns: 1)
    ran = []
    monkeypatch.setattr(cli, "cmd_preflight", lambda ns: ran.append(ns) or 0)
    ns = argparse.Namespace(finish=True, repo=NAME, apply=True, check=["test"], kit_repo=None, allow_gaps=False)
    assert cli.cmd_onboard(ns) == 1 and ran == []
