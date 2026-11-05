"""The standard's rule list: its schema, and that STANDARD.md can't drift from it."""

from pathlib import Path

import pytest

from autopilot import standard

ROOT = Path(__file__).resolve().parents[1]


def good_check(**overrides):
    check = {"id": "a-rule", "title": "t", "level": "fail", "label": "audited", "why": "w", "fix": "f"}
    return {**check, **overrides}


def data(*checks, version=1):
    return {"standard_version": version, "checks": list(checks)}


def test_the_shipped_rule_list_is_valid():
    assert standard.validate(standard.load_checks()) == []


def test_a_minimal_rule_is_valid():
    assert standard.validate(data(good_check())) == []


@pytest.mark.parametrize(
    ("bad", "expect"),
    [
        (good_check(level="block"), "level must be one of"),
        (good_check(label="mandatory"), "label must be one of"),
        (good_check(applies_to="everyone"), "applies_to must be one of"),
        (good_check(id="Not Kebab"), "lowercase words"),
        (good_check(why=""), "needs `why`"),
        (good_check(fix=None), "needs `fix`"),
        (good_check(label="enforced"), "must say what enforces it"),
        (good_check(label="advisory", level="warn"), "must say `evidence: judgment`"),
        (good_check(label="advisory", level="fail", evidence="judgment"), "can only warn"),
    ],
)
def test_validate_catches_each_kind_of_mistake(bad, expect):
    assert any(expect in p for p in standard.validate(data(bad))), standard.validate(data(bad))


def test_an_enforced_rule_that_names_its_mechanism_is_valid():
    assert standard.validate(data(good_check(label="enforced", enforced_by="ci.yml step `ap standard check`"))) == []


def test_duplicate_ids_are_caught():
    assert any("duplicate id" in p for p in standard.validate(data(good_check(), good_check())))


@pytest.mark.parametrize("version", [0, "1", None, True])
def test_the_version_must_be_a_positive_integer(version):
    assert any("standard_version" in p for p in standard.validate(data(good_check(), version=version)))


@pytest.mark.parametrize("checks", [None, [], "nope"])
def test_the_rule_list_must_not_be_empty(checks):
    assert any("non-empty list" in p for p in standard.validate({"standard_version": 1, "checks": checks}))


def test_every_advisory_rule_can_only_warn():
    for check in standard.load_checks()["checks"]:
        if check["label"] == "advisory":
            assert check["level"] == "warn", check["id"]


def test_every_enforced_rule_names_a_ci_step_that_exists():
    """`enforced` is a claim about ci.yml. If the step is removed or renamed, the claim must go with it."""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    enforced = [c for c in standard.load_checks()["checks"] if c["label"] == "enforced"]
    assert enforced, "expected the fail-level rules to be enforced"
    for check in enforced:
        step = check["enforced_by"].split("`")[1]
        assert step in ci, f"{check['id']} claims `{step}` but ci.yml has no such step"


def test_every_fail_level_rule_is_enforced():
    """A fail-level rule that only reports would be a promise nothing keeps."""
    for check in standard.load_checks()["checks"]:
        if check["level"] == "fail":
            assert check["label"] == "enforced", check["id"]


def rules_table():
    """The rows of STANDARD.md's "The rules" table, as {id: (level, label)}. Other tables are ignored."""
    rows, inside = {}, False
    for line in (ROOT / "STANDARD.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line == "## The rules"
        elif inside and line.startswith("| `"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows[cells[0].strip("`")] = (cells[1], cells[2])
    return rows


def test_standard_md_lists_exactly_the_rules_in_the_file():
    in_file = {c["id"] for c in standard.load_checks()["checks"]}
    in_doc = set(rules_table())
    assert in_doc, "found no rules table in STANDARD.md"
    assert in_doc == in_file, f"only in STANDARD.md: {in_doc - in_file}; only in checks.yaml: {in_file - in_doc}"


def test_standard_md_table_agrees_on_level_and_label():
    rows = rules_table()
    for check in standard.load_checks()["checks"]:
        assert rows[check["id"]] == (check["level"], check["label"]), check["id"]
