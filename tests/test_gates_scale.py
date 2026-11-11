"""The scale gate (before real growth) and the two beta steps the Lean Ship matrix assigned but gates.yaml lacked.

Gates are data; these tests pin that each tip the matrix hands to a gate is a real, seedable step that names its tip number."""

import re
from pathlib import Path

import pytest

from autopilot import gates

DOC = (Path(__file__).resolve().parents[1] / "docs" / "gates.md").read_text(encoding="utf-8")


def gate(name):
    return {i["id"]: i for i in gates.load_gates()["gates"][name]["items"]}


SCALE_STEPS = {"rotation-drill": 197, "slo": 198, "second-backup": 209, "vendor-exit": 145}
BETA_STEPS = {"domains": 64, "free-tier-ledger": 79}


def tips_in(item):
    return {int(n) for m in re.findall(r"Tips? ([\d, and]+)", item.get("note", "")) for n in re.findall(r"\d+", m)}


def test_the_whole_gates_file_is_still_valid():
    assert gates.validate(gates.load_gates()) == []


def test_there_is_a_scale_gate_that_holds_the_repo_to_the_standard_and_has_the_four_steps():
    items = gate("scale")
    assert items["repo-standard"]["kind"] == "repo-standard"
    assert set(SCALE_STEPS) <= set(items)
    for ident in SCALE_STEPS:
        assert items[ident]["kind"] == "step", ident


@pytest.mark.parametrize("ident,tip", sorted(SCALE_STEPS.items()))
def test_each_scale_step_names_the_tip_it_covers(ident, tip):
    assert tip in tips_in(gate("scale")[ident])


@pytest.mark.parametrize("ident,tip", sorted(BETA_STEPS.items()))
def test_the_beta_gate_has_the_domain_and_free_tier_steps_and_they_name_their_tips(ident, tip):
    item = gate("beta")[ident]
    assert item["kind"] == "step" and tip in tips_in(item)


def test_the_original_beta_and_charge_steps_are_still_there():
    assert {"uptime", "dev-prod", "privacy-page", "billing-alerts"} <= set(gate("beta"))
    assert {"sales-tax", "dunning", "legal-pages", "recovery-record"} <= set(gate("charge"))


def test_step_ids_fit_pawls_limits_for_every_gate():
    pawl_id = gates.PAWL_ID
    for name, g in gates.load_gates()["gates"].items():
        for item in g["items"]:
            if item["kind"] == "step":
                assert pawl_id.fullmatch(gates.step_id(name, item["id"])), (name, item["id"])


def test_seeding_the_scale_gate_would_not_collide_with_beta_or_charge():
    ids = [gates.step_id(n, i["id"]) for n, g in gates.load_gates()["gates"].items() for i in g["items"] if i["kind"] == "step"]
    assert len(ids) == len(set(ids))


def test_the_doc_names_every_gate_that_exists_and_gives_the_right_count():
    named = set(re.findall(r"^- `(\w+)`:", DOC, flags=re.M))
    assert named == set(gates.load_gates()["gates"]), named
    count = len(gates.load_gates()["gates"])
    assert f"There are {['zero', 'one', 'two', 'three', 'four', 'five'][count]}:" in DOC


# --- the real pawl accepts the real steps ---------------------------------------------------------------------------------------------

import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402

from autopilot import cli  # noqa: E402
from autopilot.standard import waivers  # noqa: E402


@pytest.mark.skipif(shutil.which("pawl") is None, reason="pawl is not installed")
@pytest.mark.parametrize("name", ["beta", "scale"])
def test_the_real_pawl_accepts_every_step_of_the_real_gate_and_a_second_seed_adds_nothing(tmp_path, monkeypatch, name):
    root = tmp_path / "control"
    root.mkdir()
    for args in (["init"], ["new", "proj", "--type", "product"]):
        r = subprocess.run(["pawl", "--root", str(root), *args], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
    monkeypatch.setattr(cli, "load_portfolio", lambda: {"owner": "o", "repos": {}})
    monkeypatch.setattr(waivers, "read_base", lambda root: ("", ""))

    def listed():
        out = subprocess.run(["pawl", "--root", str(root), "steps", "proj", "--json"], capture_output=True, text=True).stdout
        return sorted(s["id"] for s in json.loads(out)["data"]["steps"])

    wanted = sorted(gates.step_id(name, i["id"]) for i in gate(name).values() if i["kind"] == "step")
    assert cli.main(["gate", "seed", "proj", name, "--control", str(root), "--apply"]) == 0
    assert listed() == wanted
    assert cli.main(["gate", "seed", "proj", name, "--control", str(root), "--apply"]) == 0
    assert listed() == wanted
