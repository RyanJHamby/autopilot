from autopilot.apx import intake


def test_acceptance_commands_reads_only_the_acceptance_section():
    body = "## Goal\\n`not this`\\n\\n## Acceptance (commands)\\n- [ ] `uv run pytest -q`\\n- `ruff check .`\\n\\n## Scope\\n- `src/x.py`\\n".replace(
        "\\n", "\n"
    )
    assert intake.acceptance_commands(body) == ["uv run pytest -q", "ruff check ."]


def test_problem_cases():
    assert intake.problem("") and "Acceptance" in intake.problem("")
    assert intake.problem("## Acceptance\n- done when it looks right\n")  # no backticked command
    assert "not a runnable command" in intake.problem("## Acceptance\n- `eyeball it`\n")
    assert intake.problem("## Acceptance\n- `uv run pytest`\n- `eyeball it`\n")  # every item must be runnable
    assert intake.problem("## Acceptance\n- [ ] `uv run pytest tests/test_x.py`\n") is None
    assert intake.problem(None) is not None  # type: ignore[arg-type]
