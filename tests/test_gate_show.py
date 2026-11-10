"""`ap gate show BET GATE`: where a bet stands against a gate, read-only.

pawl's state is read through the REAL pawl against a throwaway control repo (never the real ledger), so the JSON shapes and states are the
ones pawl actually produces. The repo check is injected, except in the one test that runs the real standard on a real git repo."""

import hashlib
import json
import os
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


@pytest.fixture
def control(tmp_path):
    root = tmp_path / "control"
    root.mkdir()
    pawl(root, "init")
    pawl(root, "new", "proj", "--type", "product")
    pawl(root, "new", "llc", "--type", "deliverable")
    return root


def gate(*items):
    return {"title": "A gate", "items": list(items)}


def step(id_="demo", title="Do the thing"):
    return {"id": id_, "kind": "step", "title": title, "note": "Tip 1."}


def evaluate(control, g, repo=None, bet="proj", gate_name="charge"):
    check = repo or (lambda thesis: (None, [], []))
    return {i.id: i for i in core.evaluate(gate_name, g, bet, control, check)}


def tree_hash(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and ".git/" not in str(p):
            h.update(str(p.relative_to(root)).encode() + p.read_bytes())
    return h.hexdigest()


# --- step items ---------------------------------------------------------------------------------------------------------------------


def test_a_step_that_was_never_seeded_says_so(control):
    it = evaluate(control, gate(step()))["demo"]
    assert it.state == "not-seeded" and "ap gate seed" in it.detail


def test_a_seeded_step_is_todo_then_done_and_a_dropped_step_is_not_owed(control):
    pawl(control, "step", "add", "proj", "Do the thing", "--id", "g-charge-demo", "--note", "Tip 1.", "--draft")
    assert evaluate(control, gate(step()))["demo"].state == "todo"
    pawl(control, "step", "done", "proj", "g-charge-demo")
    assert evaluate(control, gate(step()))["demo"].state == "done"
    pawl(control, "step", "undo", "proj", "g-charge-demo")
    pawl(control, "step", "drop", "proj", "g-charge-demo")
    it = evaluate(control, gate(step()))["demo"]
    assert it.state == "done" and "dropped" in it.detail


def test_a_step_is_matched_by_its_gate_prefixed_id_so_two_gates_do_not_collide(control):
    pawl(control, "step", "add", "proj", "t", "--id", "g-beta-demo", "--note", "Tip 1.")
    pawl(control, "step", "done", "proj", "g-beta-demo")
    assert evaluate(control, gate(step()), gate_name="charge")["demo"].state == "not-seeded"
    assert evaluate(control, gate(step()), gate_name="beta")["demo"].state == "done"


# --- bet-artifact items ---------------------------------------------------------------------------------------------------------------


ENTITY = {"id": "entity", "kind": "bet-artifact", "bet": "llc", "artifacts": ["filing", "ein"], "title": "Entity formed"}


def test_a_cross_bet_artifact_is_verified_from_pawls_own_state(control):
    pawl(control, "artifact", "add", "llc", "filing", "Formation filing", "--where", "docs/f.pdf")
    pawl(control, "artifact", "add", "llc", "ein", "EIN letter", "--where", "docs/e.pdf")
    it = evaluate(control, gate(ENTITY))["entity"]
    assert it.state == "todo" and "filing" in it.detail and "ein" in it.detail
    pawl(control, "artifact", "deliver", "llc", "filing", "--ref", "docs/f.pdf")
    it = evaluate(control, gate(ENTITY))["entity"]
    assert it.state == "todo" and "ein" in it.detail and "filing" not in it.detail
    pawl(control, "artifact", "deliver", "llc", "ein", "--ref", "docs/e.pdf")
    assert evaluate(control, gate(ENTITY))["entity"].state == "done"


def test_an_artifact_the_other_bet_does_not_even_have_is_todo_not_done(control):
    it = evaluate(control, gate(ENTITY))["entity"]
    assert it.state == "todo" and "no artifact" in it.detail


def test_a_bet_that_does_not_exist_is_unknown_not_a_pass(control):
    missing = {**ENTITY, "bet": "ghost"}
    it = evaluate(control, gate(missing))["entity"]
    assert it.state == "unknown" and "ghost" in it.detail


# --- bet-field items --------------------------------------------------------------------------------------------------------------------


def field_item(name):
    return {"id": name.replace("_", "-"), "kind": "bet-field", "field": name, "title": f"{name} is set"}


def test_a_bet_field_is_done_only_when_it_is_filled_in(control):
    item = field_item("money_gate")
    assert evaluate(control, gate(item))["money-gate"].state == "todo"
    pawl(control, "set", "proj", "money_gate", "first paying customer")
    assert evaluate(control, gate(item))["money-gate"].state == "done"


def test_a_numeric_field_of_zero_counts_as_not_set(control):
    item = field_item("price_monthly")
    assert evaluate(control, gate(item))["price-monthly"].state == "todo"


# --- repo-standard items -------------------------------------------------------------------------------------------------------------------


REPO = {"id": "repo", "kind": "repo-standard", "title": "Meets the standard"}


def test_repo_standard_lists_the_gaps_and_is_done_when_there_are_none(control, tmp_path):
    seen = {}

    def gaps(thesis):
        seen["repo"] = thesis.get("repo")
        return tmp_path, ["hook-wired: no hook", "secret-scan-wired: no scan"], []

    it = evaluate(control, gate(REPO), repo=gaps)["repo"]
    assert it.state == "todo" and "hook-wired" in it.detail and "secret-scan-wired" in it.detail
    assert evaluate(control, gate(REPO), repo=lambda t: (tmp_path, [], []))["repo"].state == "done"


def test_repo_standard_is_unknown_when_there_is_no_clone_to_look_at(control):
    it = evaluate(control, gate(REPO), repo=lambda t: (None, [], []))["repo"]
    assert it.state == "unknown" and "clone" in it.detail


def test_repo_standard_is_unknown_when_the_bet_names_no_repo(control):
    # The real check returns (None, [], []) for an empty repo field, and the bet's own bet.toml says why there is no clone.
    it = evaluate(control, gate(REPO), repo=lambda t: (None, [], []))["repo"]
    assert it.state == "unknown" and "names no repo" in it.detail


def test_the_real_command_says_the_bet_names_no_repo_when_the_field_is_empty(control, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_portfolio", lambda: {"owner": "o", "repos": {}})
    monkeypatch.setattr(waivers, "read_base", lambda root: ("", ""))
    monkeypatch.setattr(command, "load_gates", lambda: {"gates": {"charge": gate(REPO)}})
    assert cli.main(["gate", "show", "proj", "charge", "--control", str(control)]) == 1
    assert "names no repo" in capsys.readouterr().out


# --- how each item is known --------------------------------------------------------------------------------------------------------------


def test_each_item_says_how_it_is_known_so_a_tick_is_not_mistaken_for_proof(control):
    g = gate(REPO, ENTITY, field_item("money_gate"), step())
    got = {i.kind: i.how for i in core.evaluate("charge", g, "proj", control, lambda t: (None, [], []))}
    assert "code" in got["repo-standard"] and "recorded" in got["bet-artifact"]
    assert "bet.toml" in got["bet-field"] and "self-attested" in got["step"]


# --- the verdict and the command -----------------------------------------------------------------------------------------------------------


def test_ready_only_when_every_item_is_done(control, tmp_path):
    items = core.evaluate("charge", gate(step(), field_item("money_gate")), "proj", control, lambda t: (None, [], []))
    assert core.ready(items) is False
    pawl(control, "step", "add", "proj", "t", "--id", "g-charge-demo", "--note", "Tip 1.")
    pawl(control, "step", "done", "proj", "g-charge-demo")
    pawl(control, "set", "proj", "money_gate", "first paying customer")
    items = core.evaluate("charge", gate(step(), field_item("money_gate")), "proj", control, lambda t: (None, [], []))
    assert core.ready(items) is True


def test_unknown_is_not_ready(control):
    assert core.ready(evaluate(control, gate(REPO), repo=lambda t: (None, [], [])).values()) is False


def test_the_render_names_every_item_and_a_summary(control):
    items = core.evaluate("charge", gate(step(), ENTITY), "proj", control, lambda t: (None, [], []))
    text = core.render("proj", "charge", gate(step(), ENTITY), items)
    assert "charge" in text and "A gate" in text and "demo" in text and "entity" in text and "0 of 2 done" in text and "Not ready" in text


@pytest.fixture
def world(control, monkeypatch):
    monkeypatch.setattr(cli, "load_portfolio", lambda: {"owner": "o", "repos": {}})
    monkeypatch.setattr(waivers, "read_base", lambda root: ("", ""))
    monkeypatch.setattr(command, "load_gates", lambda: {"gates": {"charge": gate(step(), field_item("money_gate"))}})
    return control


def run_show(control, *extra):
    return cli.main(["gate", "show", "proj", "charge", "--control", str(control), *extra])


def test_show_exits_1_when_not_ready_and_0_when_ready(world, capsys):
    assert run_show(world) == 1
    pawl(world, "step", "add", "proj", "t", "--id", "g-charge-demo", "--note", "Tip 1.")
    pawl(world, "step", "done", "proj", "g-charge-demo")
    pawl(world, "set", "proj", "money_gate", "first paying customer")
    assert run_show(world) == 0 and "Ready" in capsys.readouterr().out


def test_show_never_writes_to_the_control_repo(world):
    before = tree_hash(world)
    run_show(world)
    run_show(world, "--json")
    assert tree_hash(world) == before


def test_show_json_has_a_stable_shape(world, capsys):
    run_show(world, "--json")
    data = json.loads(capsys.readouterr().out)
    assert data["bet"] == "proj" and data["gate"] == "charge" and data["ready"] is False
    assert {i["id"] for i in data["items"]} == {"demo", "money-gate"}
    assert all({"id", "kind", "title", "state", "detail", "how"} <= set(i) for i in data["items"])


def test_an_unknown_bet_or_gate_is_a_clear_error_exit_2(world, capsys):
    assert cli.main(["gate", "show", "nope", "charge", "--control", str(world)]) == 2
    assert "No bet named" in capsys.readouterr().out
    assert cli.main(["gate", "show", "proj", "bogus", "--control", str(world)]) == 2
    assert "charge" in capsys.readouterr().out  # lists the gates that do exist


def test_a_control_path_that_is_not_a_control_repo_is_a_clear_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_portfolio", lambda: {"owner": "o", "repos": {}})
    assert cli.main(["gate", "show", "proj", "charge", "--control", str(tmp_path)]) == 2
    assert "control repo" in capsys.readouterr().out


def test_without_pawl_on_the_path_items_that_need_it_are_unknown_with_no_traceback(world, capsys, monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    code = run_show(world)
    out = capsys.readouterr().out
    assert code in (1, 2) and "Traceback" not in out and ("pawl" in out)


def test_the_control_repo_is_found_from_the_flag_then_the_environment_then_the_default(tmp_path, monkeypatch):
    monkeypatch.delenv("PAWL_ROOT", raising=False)
    assert core.resolve_control(None) == Path("~/dev/control").expanduser()
    monkeypatch.setenv("PAWL_ROOT", str(tmp_path / "env"))
    assert core.resolve_control(None) == tmp_path / "env"
    assert core.resolve_control(str(tmp_path / "flag")) == tmp_path / "flag"


# --- the real standard on a real repo -------------------------------------------------------------------------------------------------


def test_repo_standard_runs_the_real_standard_on_the_bets_repo_as_if_it_were_new(control, tmp_path, monkeypatch, capsys):
    clones = tmp_path / "clones"
    repo = clones / "proj"
    repo.mkdir(parents=True)
    (repo / "README.md").write_text("x\n")
    env = {**os.environ, "GIT_AUTHOR_DATE": "2025-01-01T12:00:00+00:00", "GIT_COMMITTER_DATE": "2025-01-01T12:00:00+00:00"}
    for args in (["init", "-q", "-b", "main"], ["add", "."], ["-c", "commit.gpgsign=false", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
                 ["remote", "add", "origin", "https://github.com/o/proj.git"]):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)
    pawl(control, "set", "proj", "repo", "o/proj")
    monkeypatch.setattr(cli, "load_portfolio", lambda: {"owner": "o", "repos": {}})
    monkeypatch.setattr(waivers, "read_base", lambda root: ("", ""))
    monkeypatch.setattr(command, "load_gates", lambda: {"gates": {"charge": gate(REPO)}})
    assert cli.main(["gate", "show", "proj", "charge", "--control", str(control), "--root", str(clones)]) == 1
    out = capsys.readouterr().out
    assert "hook-wired" in out, "an old repo is held to the rules it was grandfathered under"
