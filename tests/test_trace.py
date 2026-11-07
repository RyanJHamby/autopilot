"""trace: what a spec's acceptance commands really ran, read from pytest's JUnit XML."""

import subprocess
import sys

import pytest

from autopilot import cli, trace
from autopilot.trace import Case

SPEC = "---\nid: x\nacceptance:\n  - uv run pytest tests/test_a.py\n  - uv run ruff check .\n---\nbody\n"


def case(module, name, status="passed"):
    return Case(module, name, status)


def status_of(cases, spec=SPEC):
    return [r.status for r in trace.trace(spec, cases)]


def test_all_matching_tests_passing_is_green_and_ruff_is_not_traceable():
    assert status_of([case("tests.test_a", "test_one"), case("tests.test_a", "test_two")]) == ["green", "not-traceable"]


def test_a_failure_makes_it_failing_even_if_others_pass():
    assert status_of([case("tests.test_a", "t1"), case("tests.test_a", "t2", "failed")])[0] == "failing"


def test_a_collection_error_counts_as_failing(tmp_path):
    junit = tmp_path / "j.xml"
    junit.write_text(
        '<testsuites><testsuite><testcase classname="tests.test_a" name="t"><error message="x"/></testcase></testsuite></testsuites>'
    )
    assert status_of(trace.read_junit(junit))[0] == "failing"


def test_a_skipped_test_is_not_green():
    assert status_of([case("tests.test_a", "t1"), case("tests.test_a", "t2", "skipped")])[0] == "skipped"


def test_no_matching_test_is_not_run_which_is_the_hollow_link():
    assert status_of([case("tests.test_other", "t")])[0] == "not-run"
    assert status_of([])[0] == "not-run"


def test_failing_outranks_skipped():
    assert status_of([case("tests.test_a", "a", "skipped"), case("tests.test_a", "b", "failed")])[0] == "failing"


@pytest.mark.parametrize(
    ("command", "targets"),
    [
        ("uv run pytest tests/test_a.py", ["tests/test_a.py"]),
        ("python -m pytest -q tests/a.py tests/b.py", ["tests/a.py", "tests/b.py"]),
        ("pytest", []),
        ("pytest -q -k 'foo and bar' tests/a.py", ["tests/a.py"]),
        ("pytest --junitxml out.xml tests", ["tests"]),
        ("pytest tests/a.py::test_x", ["tests/a.py::test_x"]),
        ("uv run ruff check .", None),
        ("npm test", None),
        ("pytest 'unterminated", None),
    ],
)
def test_pytest_targets(command, targets):
    assert trace.pytest_targets(command) == targets


def test_a_directory_target_matches_every_module_under_it_but_not_a_prefix_lookalike():
    spec = "---\nacceptance:\n  - pytest tests\n---\n"
    assert status_of([case("tests.test_a", "t"), case("tests.sub.test_b", "t")], spec) == ["green"]
    assert status_of([case("tests_other.test_a", "t")], spec) == ["not-run"]


def test_a_module_target_does_not_match_a_longer_module_name():
    assert status_of([case("tests.test_a_extra", "t")])[0] == "not-run"


def test_a_selector_target_matches_only_that_test_and_ignores_parametrize_ids():
    spec = "---\nacceptance:\n  - pytest tests/test_a.py::test_one\n---\n"
    assert status_of([case("tests.test_a", "test_one[1]"), case("tests.test_a", "test_two", "failed")], spec) == ["green"]


def test_bare_pytest_covers_every_test():
    assert status_of([case("x.y", "t", "failed")], "---\nacceptance:\n  - pytest\n---\n") == ["failing"]


def test_tests_inside_a_class_match_their_module():
    assert status_of([case("tests.test_a.TestThing", "t")])[0] == "green"


@pytest.mark.parametrize("spec", ["no front matter", "---\nid: x\n---\n", "---\nacceptance: nope\n---\n", "---\n: [bad\n---\n"])
def test_a_spec_with_no_usable_acceptance_list_traces_to_nothing(spec):
    assert trace.trace(spec, []) == []


def test_non_string_acceptance_items_are_ignored():
    assert trace.acceptance("---\nacceptance:\n  - {a: b}\n  - pytest x\n---\n") == ["pytest x"]


def test_read_junit_understands_real_pytest_output(tmp_path):
    (tmp_path / "test_m.py").write_text(
        "import pytest\ndef test_ok(): assert 1\ndef test_bad(): assert 0\n@pytest.mark.skip\ndef test_skip(): pass\n"
        "@pytest.mark.xfail\ndef test_xf(): assert 0\n"
    )
    junit = tmp_path / "j.xml"
    subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}", "test_m.py"],
        cwd=tmp_path,
        capture_output=True,
    )
    got = {c.name: c.status for c in trace.read_junit(junit)}
    assert got == {"test_ok": "passed", "test_bad": "failed", "test_skip": "skipped", "test_xf": "skipped"}


def test_the_command_prints_warnings_and_only_fails_under_strict(tmp_path, capsys):
    spec = tmp_path / "s.md"
    spec.write_text(SPEC)
    junit = tmp_path / "j.xml"
    junit.write_text(
        '<testsuites><testsuite><testcase classname="tests.test_a" name="t"><skipped/></testcase></testsuite></testsuites>'
    )
    assert cli.main(["trace", str(spec), "--junit", str(junit)]) == 0
    assert "WARN skipped" in capsys.readouterr().out
    assert cli.main(["trace", str(spec), "--junit", str(junit), "--strict"]) == 1


def test_a_missing_file_is_an_error_not_a_pass(tmp_path, capsys):
    assert cli.main(["trace", str(tmp_path / "nope.md"), "--junit", str(tmp_path / "nope.xml")]) == 2
