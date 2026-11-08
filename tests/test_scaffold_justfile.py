"""The scaffolder serves a `justfile` (rule `commands-documented`) so every repo has run/test commands that devbook can index.

A repo satisfies the rule with a `justfile` or an `AGENTS.md` `## Commands` section. Private repos get it too."""

import re
from pathlib import Path

import pytest

from autopilot.scaffold import core

ECOSYSTEMS = ["uv", "pip", "npm", "cargo", "gomod"]


def make(tmp_path: Path, files: dict[str, str], name: str = "proj") -> Path:
    root = tmp_path / name
    root.mkdir()
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return root


def action(root: Path, public: bool = True) -> core.Action:
    c = core.read_ctx(root, root.name, "Ryan", public, holder="Ryan Hamby", kind="app")
    found = [a for a in core.plan(root, c) if a.path == "justfile"]
    assert found, "the scaffolder has no justfile item yet"
    return found[0]


def test_a_uv_repo_without_commands_gets_a_justfile_with_documented_recipes(tmp_path):
    a = action(make(tmp_path, {"pyproject.toml": "[project]\n", "uv.lock": ""}))
    assert a.status == "create" and a.rule == "commands-documented"
    assert re.search(r"^# .+\ntest:", a.content, re.M), "test must be the first recipe line after a # doc comment"
    assert "uv run pytest" in a.content
    assert "\n\t" in a.content or "\n    " in a.content


@pytest.mark.parametrize("eco", ECOSYSTEMS)
def test_every_known_ecosystem_gets_a_test_recipe(eco):
    c = core.Ctx(name="proj", owner="Ryan", public=True, holder="Ryan Hamby", year=2026, ecosystems=[eco])
    a = {x.path: x for x in core.plan(Path("/nonexistent-devbook-root"), c)}["justfile"]
    assert a.status == "create"
    assert re.search(r"^test:", a.content, re.M)


def test_a_private_repo_gets_it_too(tmp_path):
    assert action(make(tmp_path, {"pyproject.toml": "", "uv.lock": ""}), public=False).status == "create"


def test_an_existing_justfile_is_left_alone(tmp_path):
    root = make(tmp_path, {"justfile": "mine:\n\ttrue\n", "uv.lock": ""})
    assert action(root).status == "exists"
    assert (root / "justfile").read_text() == "mine:\n\ttrue\n"


def test_an_agents_md_commands_section_satisfies_the_rule(tmp_path):
    root = make(tmp_path, {"AGENTS.md": "# x\n\n## Commands\n\n- `make check`\n", "uv.lock": ""})
    a = action(root)
    assert a.status == "skip" and "Commands" in a.note


def test_no_known_ecosystem_means_nothing_is_guessed(tmp_path):
    assert action(make(tmp_path, {"README.md": "notes\n"})).status == "skip"


def test_write_creates_it_once_and_a_second_run_creates_nothing(tmp_path):
    root = make(tmp_path, {"pyproject.toml": "", "uv.lock": ""})
    c = core.read_ctx(root, "proj", "Ryan", False, kind="app")
    assert "justfile" in core.write(root, core.plan(root, c))
    assert (root / "justfile").is_file()
    assert [a.path for a in core.plan(root, c) if a.status == "create"] == []


def test_the_rule_is_declared_as_proposed_until_the_owner_adds_it_to_checks_yaml():
    assert "commands-documented" in core.PROPOSED_RULES
