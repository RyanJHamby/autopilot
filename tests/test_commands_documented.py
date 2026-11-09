"""`commands-documented`: a repo passes with a justfile or an AGENTS.md `## Commands` section, and fails with neither."""

from pathlib import Path

import pytest

from autopilot.standard import engine


def result(tmp_path: Path, files: dict[str, str]) -> str:
    root = tmp_path / "r"
    root.mkdir()
    for rel, text in files.items():
        (root / rel).write_text(text)
    return engine.run(engine.Repo(root, github_public=True), only=["commands-documented"])[0].result


@pytest.mark.parametrize("name", ["justfile", "Justfile", ".justfile"])
def test_a_justfile_passes(tmp_path, name):
    assert result(tmp_path, {name: "test:\n\tpytest\n"}) == "pass"


def test_an_agents_commands_section_passes(tmp_path):
    assert result(tmp_path, {"AGENTS.md": "# a\n\n## Commands\n- test: pytest\n"}) == "pass"


def test_neither_fails(tmp_path):
    assert result(tmp_path, {"README.md": "hi", "AGENTS.md": "# a\n\n## Commandsish nope\n"}) == "fail"


def test_the_rule_is_a_warning_not_a_failure():
    from autopilot import standard

    rule = next(c for c in standard.load_checks()["checks"] if c["id"] == "commands-documented")
    assert rule["level"] == "warn"
