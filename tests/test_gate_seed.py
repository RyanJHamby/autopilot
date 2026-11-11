"""`ap gate seed BET GATE`: add a gate's manual steps to the control repo as draft pawl steps.

Every write to a control repo with [sync] on commits and pushes to main, one push per step, so seeding is dry-run by default, uses
`--no-push` unless asked, and is idempotent through explicit ids. These tests run the REAL pawl on throwaway control repos, and use a real
local bare repository as the remote to prove that nothing is pushed unless --push says so."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from autopilot import cli
from autopilot.gates import command, core
from autopilot.standard import waivers

pytestmark = pytest.mark.skipif(shutil.which("pawl") is None, reason="pawl is not installed")


def pawl(root, *args, check=True):
    r = subprocess.run(["pawl", "--root", str(root), *args], capture_output=True, text=True)
    if check:
        assert r.returncode == 0, r.stdout + r.stderr
    return r


def gate_cfg():
    return {
        "title": "A gate",
        "items": [
            {"id": "repo", "kind": "repo-standard", "title": "Meets the standard"},
            {"id": "field", "kind": "bet-field", "field": "money_gate", "title": "Money gate set"},
            {"id": "one", "kind": "step", "title": "First manual task", "note": "Tip 1."},
            {"id": "two", "kind": "step", "title": "Second manual task", "note": "Tip 2."},
            {"id": "three", "kind": "step", "title": "Third manual task", "note": "Tip 3."},
        ],
    }


@pytest.fixture
def control(tmp_path):
    root = tmp_path / "control"
    root.mkdir()
    pawl(root, "init")
    pawl(root, "new", "proj", "--type", "product")
    return root


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and ".git/" not in str(p):
            h.update(str(p.relative_to(root)).encode() + p.read_bytes())
    return h.hexdigest()


def steps(control, bet="proj"):
    return json.loads(pawl(control, "steps", bet, "--json").stdout)["data"]["steps"]


@pytest.fixture
def world(control, monkeypatch):
    monkeypatch.setattr(cli, "load_portfolio", lambda: {"owner": "o", "repos": {}})
    monkeypatch.setattr(waivers, "read_base", lambda root: ("", ""))
    monkeypatch.setattr(command, "load_gates", lambda: {"gates": {"charge": gate_cfg()}})
    return control


def seed(control, *extra, bet="proj", gate="charge"):
    return cli.main(["gate", "seed", bet, gate, "--control", str(control), *extra])


# --- the plan ---------------------------------------------------------------------------------------------------------------------


def test_only_step_items_are_seeded_and_each_gets_a_gate_prefixed_explicit_id(control):
    plan = core.seed_plan("charge", gate_cfg(), "proj", control)
    assert [s.step_id for s in plan] == ["g-charge-one", "g-charge-two", "g-charge-three"]
    assert all(not s.exists for s in plan)


def test_a_step_already_in_pawl_is_marked_existing_by_id_not_by_title(control):
    pawl(control, "step", "add", "proj", "First manual task", "--id", "other-id", "--note", "x")  # same title, different id
    pawl(control, "step", "add", "proj", "Something else", "--id", "g-charge-two", "--note", "x")  # same id, different title
    exists = {s.step_id: s.exists for s in core.seed_plan("charge", gate_cfg(), "proj", control)}
    assert exists == {"g-charge-one": False, "g-charge-two": True, "g-charge-three": False}


def test_the_command_has_explicit_id_draft_and_no_push_unless_asked(control):
    s = core.seed_plan("charge", gate_cfg(), "proj", control)[0]
    no_push = core.seed_command(control, "proj", s, push=False)
    assert no_push[:4] == ["pawl", "--root", str(control), "--no-push"] and "--draft" in no_push
    assert no_push[no_push.index("--id") + 1] == "g-charge-one" and no_push[no_push.index("--note") + 1] == "Tip 1."
    assert "--no-push" not in core.seed_command(control, "proj", s, push=True)


# --- dry run and apply ------------------------------------------------------------------------------------------------------------------


def test_a_dry_run_prints_the_exact_commands_and_writes_nothing(world, capsys):
    before = tree_hash(world)
    assert seed(world) == 0
    out = capsys.readouterr().out
    assert "[dry run]" in out and "g-charge-one" in out and "g-charge-three" in out and "--no-push" in out and "--draft" in out
    assert "--apply" in out
    assert tree_hash(world) == before and steps(world) == []


def test_apply_adds_exactly_the_missing_steps_as_drafts_with_their_notes(world, capsys):
    assert seed(world, "--apply") == 0
    got = {s["id"]: s for s in steps(world)}
    assert set(got) == {"g-charge-one", "g-charge-two", "g-charge-three"}
    assert all(s["source"] == "draft" and s["state"] == "todo" for s in got.values())
    assert got["g-charge-two"]["note"] == "Tip 2." and got["g-charge-two"]["title"] == "Second manual task"


def test_a_second_run_adds_nothing(world, capsys):
    seed(world, "--apply")
    capsys.readouterr()
    before = tree_hash(world)
    assert seed(world, "--apply") == 0
    assert "nothing to seed" in capsys.readouterr().out
    assert tree_hash(world) == before and len(steps(world)) == 3


def test_a_half_finished_seed_resumes_and_leaves_what_is_there_alone(world):
    pawl(world, "step", "add", "proj", "First manual task", "--id", "g-charge-one", "--note", "Tip 1.")
    pawl(world, "step", "done", "proj", "g-charge-one")
    assert seed(world, "--apply") == 0
    got = {s["id"]: s for s in steps(world)}
    assert set(got) == {"g-charge-one", "g-charge-two", "g-charge-three"}
    assert got["g-charge-one"]["state"] == "done", "an existing step is never edited or reset"


def test_seeded_steps_show_up_as_todo_in_gate_show(world, capsys):
    seed(world, "--apply")
    capsys.readouterr()
    cli.main(["gate", "show", "proj", "charge", "--control", str(world), "--json"])
    states = {i["id"]: i["state"] for i in json.loads(capsys.readouterr().out)["items"]}
    assert states["one"] == states["two"] == states["three"] == "todo"


# --- errors -----------------------------------------------------------------------------------------------------------------------------


def test_an_unknown_bet_gate_or_control_is_a_clear_error_and_writes_nothing(world, tmp_path, capsys):
    before = tree_hash(world)
    assert seed(world, "--apply", bet="nope") == 2 and "No bet named" in capsys.readouterr().out
    assert seed(world, "--apply", gate="bogus") == 2 and "charge" in capsys.readouterr().out
    assert cli.main(["gate", "seed", "proj", "charge", "--control", str(tmp_path), "--apply"]) == 2
    assert "control repo" in capsys.readouterr().out
    assert tree_hash(world) == before


def test_a_gate_with_no_manual_steps_has_nothing_to_seed(world, monkeypatch, capsys):
    only_repo = {"title": "G", "items": [{"id": "repo", "kind": "repo-standard", "title": "t"}]}
    monkeypatch.setattr(command, "load_gates", lambda: {"gates": {"charge": only_repo}})
    assert seed(world, "--apply") == 0 and "no manual steps" in capsys.readouterr().out


def test_a_failure_part_way_stops_and_says_exactly_what_was_written():
    calls = []

    def flaky(cmd, **kw):
        calls.append(cmd)
        if len(calls) == 2:
            return subprocess.CompletedProcess(cmd, 2, "", "pawl: boom")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    plan = [core.Seed("a", "g-x-a", "A", "n", False), core.Seed("b", "g-x-b", "B", "n", False), core.Seed("c", "g-x-c", "C", "n", False)]
    written, err = core.apply_seed(plan, Path("/c"), "proj", push=False, run=flaky)
    assert written == ["g-x-a"] and "boom" in err and len(calls) == 2, "it stops at the first failure and does not carry on"


def test_a_duplicate_reported_by_pawl_is_a_skip_not_a_failure():
    def dup(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 2, "", "pawl: proj already has a step 'g-x-a'. Edit it with pawl step edit proj g-x-a.")

    written, err = core.apply_seed([core.Seed("a", "g-x-a", "A", "n", False)], Path("/c"), "proj", push=False, run=dup)
    assert written == [] and err is None


# --- what reaches the remote ------------------------------------------------------------------------------------------------------------


@pytest.fixture
def synced(control, tmp_path, monkeypatch):
    """A control repo with [sync] push on and a real bare repository as origin, like pawl's own sync tests."""
    cfg = tmp_path / "gitconfig"
    cfg.write_text("[user]\n\tname = t\n\temail = t@t\n[commit]\n\tgpgsign = false\n[init]\n\tdefaultBranch = main\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    remote = tmp_path / "origin.git"
    for cmd, cwd in ((["git", "init", "--bare", "-q", "-b", "main", str(remote)], tmp_path), (["git", "init", "-q", "-b", "main"], control)):
        subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)
    for args in (["add", "-A"], ["commit", "-qm", "init"], ["remote", "add", "origin", str(remote)], ["push", "-q", "-u", "origin", "main"]):
        subprocess.run(["git", *args], cwd=control, check=True, capture_output=True)
    (control / "pawl.toml").write_text((control / "pawl.toml").read_text() + "\n[sync]\npush = true\n")
    for args in (["add", "-A"], ["commit", "-qm", "enable sync"], ["push", "-q", "origin", "main"]):
        subprocess.run(["git", *args], cwd=control, check=True, capture_output=True)
    return control, remote


def subjects(repo, ref="main"):
    return subprocess.run(["git", "log", "--format=%s", ref], cwd=repo, capture_output=True, text=True, check=True).stdout.splitlines()


def test_by_default_nothing_is_pushed_but_each_step_is_committed_locally(world, synced, capsys):
    control, remote = synced
    remote_before = subjects(remote)
    assert seed(control, "--apply") == 0
    local = subjects(control)
    assert local[:3] == ["pawl: step add proj"] * 3, local[:4]
    assert subjects(remote) == remote_before, "--no-push must leave the remote exactly as it was"


def test_push_sends_each_commit_to_the_remote(world, synced):
    control, remote = synced
    assert seed(control, "--apply", "--push") == 0
    assert subjects(remote)[:3] == ["pawl: step add proj"] * 3


def test_the_message_after_a_local_only_seed_says_how_to_push(world, synced, capsys):
    control, _ = synced
    seed(control, "--apply")
    out = capsys.readouterr().out
    assert "pawl sync" in out and "not pushed" in out
