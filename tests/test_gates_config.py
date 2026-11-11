"""gates.yaml: the checklists a bet must clear before real users arrive (`beta`) and before the first payment (`charge`).

The validator encodes pawl's own limits, because a step that pawl would reject is only discovered when someone runs `seed --apply`
against the real ledger, which is the worst time."""

import re

import pytest

from autopilot import gates


def cfg(**gate):
    base = {"title": "T", "items": [{"id": "a-step", "kind": "step", "title": "Do the thing", "note": "Tip 1."}]}
    return {"gates": {"charge": {**base, **gate}}}


def one(item):
    return {"gates": {"charge": {"title": "T", "items": [item]}}}


def problems(data):
    return gates.validate(data)


# --- the shipped file ---------------------------------------------------------------------------------------------------------------


def test_the_shipped_gates_validate():
    assert problems(gates.load_gates()) == []


def test_there_is_a_beta_gate_and_a_charge_gate():
    assert {"beta", "charge"} <= set(gates.load_gates()["gates"])


def test_every_seeded_step_id_fits_pawls_limit_and_is_unique_across_gates():
    seen = set()
    for gate, g in gates.load_gates()["gates"].items():
        for item in g["items"]:
            if item["kind"] != "step":
                continue
            sid = gates.step_id(gate, item["id"])
            assert re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", sid), sid
            assert sid not in seen, sid
            seen.add(sid)


def test_every_step_cites_the_tip_it_comes_from():
    for gate, g in gates.load_gates()["gates"].items():
        for item in g["items"]:
            if item["kind"] == "step":
                assert re.search(r"\bTips? \d+", item["note"]), f"{gate}/{item['id']} has no tip reference"


def test_legal_and_tax_steps_say_to_confirm_with_a_professional():
    # This is a checklist, not legal or tax advice, and the steps must not read as if it were.
    legal = {"sales-tax", "tax-set-aside", "insurance", "legal-pages", "privacy-page"}
    seen = set()
    for g in gates.load_gates()["gates"].values():
        for item in g["items"]:
            if item["id"] in legal:
                seen.add(item["id"])
                assert re.search(r"professional|CPA|lawyer", item["title"] + item["note"], re.I), item["id"]
    assert seen == legal, f"expected each of {legal - seen} to exist"


def test_the_charge_gate_checks_the_entity_and_the_business_account_in_the_ledger():
    items = {i["id"]: i for i in gates.load_gates()["gates"]["charge"]["items"]}
    assert items["entity-formed"]["kind"] == "bet-artifact" and items["entity-formed"]["bet"] == "llc"
    assert {"filing", "ein"} <= set(items["entity-formed"]["artifacts"])
    assert items["business-account"]["bet"] == "financial-separation" and "account" in items["business-account"]["artifacts"]


def test_both_gates_hold_the_repo_to_the_current_standard():
    for name in ("beta", "charge"):
        assert any(i["kind"] == "repo-standard" for i in gates.load_gates()["gates"][name]["items"]), name


# --- validation --------------------------------------------------------------------------------------------------------------------


def test_a_good_config_is_valid():
    assert problems(cfg()) == []


@pytest.mark.parametrize(
    "mutate,expect",
    [
        (lambda c: c["gates"]["charge"].pop("title"), "title"),
        (lambda c: c["gates"]["charge"].update(items=[]), "items"),
        (lambda c: c["gates"].update({"Bad Name": c["gates"]["charge"]}), "gate name"),
    ],
)
def test_a_malformed_gate_is_reported(mutate, expect):
    data = cfg()
    mutate(data)
    assert any(expect in p for p in problems(data)), problems(data)


@pytest.mark.parametrize(
    "item,expect",
    [
        ({"id": "Bad_Id", "kind": "step", "title": "t", "note": "n"}, "id must be"),
        ({"id": "x", "kind": "vibes", "title": "t"}, "kind must be"),
        ({"id": "x", "kind": "step", "note": "n"}, "needs a title"),
        ({"id": "x", "kind": "step", "title": "t"}, "needs a note"),
        ({"id": "x", "kind": "step", "title": "t" * 201, "note": "n"}, "title is at most 200"),
        ({"id": "x", "kind": "step", "title": "t", "note": "n" * 301}, "note is at most 300"),
        ({"id": "x" * 32, "kind": "step", "title": "t", "note": "n"}, "step id"),
        ({"id": "x", "kind": "bet-artifact", "title": "t", "artifacts": ["a"]}, "needs `bet`"),
        ({"id": "x", "kind": "bet-artifact", "title": "t", "bet": "llc"}, "needs `artifacts`"),
        ({"id": "x", "kind": "bet-artifact", "title": "t", "bet": "Not A Slug", "artifacts": ["a"]}, "bet must be"),
        ({"id": "x", "kind": "bet-field", "title": "t"}, "needs `field`"),
        ({"id": "x", "kind": "bet-field", "title": "t", "field": "favourite_colour"}, "unknown bet field"),
        ({"id": "x", "kind": "repo-standard"}, "needs a title"),
        ({"id": "x", "kind": "step", "title": "t", "note": "n", "tips": ["one"]}, "tips must be"),
    ],
)
def test_each_kind_of_mistake_in_an_item_is_reported(item, expect):
    assert any(expect in p for p in problems(one(item))), problems(one(item))


def test_a_duplicate_item_id_within_a_gate_is_reported():
    data = cfg(items=[{"id": "x", "kind": "repo-standard", "title": "t"}, {"id": "x", "kind": "repo-standard", "title": "t"}])
    assert any("duplicate" in p for p in problems(data))


def test_the_step_id_is_prefixed_with_the_gate_so_two_gates_never_collide():
    assert gates.step_id("charge", "sales-tax") == "g-charge-sales-tax"
    assert gates.step_id("beta", "sales-tax") != gates.step_id("charge", "sales-tax")
