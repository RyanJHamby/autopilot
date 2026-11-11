"""The standard's burn-down: each converge run records how many gaps every repo has, split by how much they weigh, and the digest shows
the trend. Without it a repo with 17 gaps looks the same this week as last, and nobody can tell whether the retrofit is moving."""

import json
from datetime import date

from autopilot import digest
from autopilot.converge import command, core

TODAY = date(2026, 11, 8)
OLD, NEW = "2025-01-01T00:00:00Z", "2026-11-12T00:00:00Z"


def audit_of(tmp_path, created, dirname="proj"):
    root = tmp_path / dirname
    root.mkdir()
    (root / "README.md").write_text("bare\n")
    return core.audit(core.Listed("proj", public=True, created_at=created), root, "Ryan", {"owner": "Ryan", "repos": {}}, TODAY)


# --- counting a gap by what it weighs ------------------------------------------------------------------------------------


def test_an_old_repo_has_its_new_rule_failures_counted_as_grandfathered_not_fail_level(tmp_path):
    a = audit_of(tmp_path, OLD)
    assert a.grandfathered > 0 and a.warn > 0
    assert a.fail_level + a.warn + a.grandfathered == len(a.gaps), "every gap is counted exactly once"


def test_a_new_repo_has_the_same_rules_counted_as_fail_level(tmp_path):
    old = audit_of(tmp_path, OLD, "old")
    new = audit_of(tmp_path, NEW, "new")
    assert new.grandfathered == 0 and new.fail_level > old.fail_level
    assert new.fail_level + new.warn + new.grandfathered == len(new.gaps)


# --- the history file ----------------------------------------------------------------------------------------------------


def counts(**repos):
    return {name: {"fail_level": f, "warn": w, "grandfathered": g} for name, (f, w, g) in repos.items()}


def test_each_run_appends_one_line_and_never_rewrites_the_past(tmp_path):
    path = tmp_path / "deep" / "history.jsonl"
    assert command.append_history(path, counts(a=(1, 2, 3))) == ""
    assert command.append_history(path, counts(a=(0, 2, 3))) == ""
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [r["repos"]["a"]["fail_level"] for r in rows] == [1, 0] and all("time" in r for r in rows)


def test_a_history_write_failure_is_reported_not_raised(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert "could not write" in command.append_history(blocker / "history.jsonl", counts(a=(0, 0, 0)))


def test_reading_returns_the_last_two_valid_runs_and_skips_corrupt_lines(tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_text('{"time": "t1", "repos": {}}\nnot json\n{"time": "t2", "repos": {}}\n\n{"time": "t3", "repos": {}}\n')
    assert [r["time"] for r in digest.read_history(path)] == ["t2", "t3"]


def test_reading_a_missing_or_empty_history_is_just_empty(tmp_path):
    assert digest.read_history(tmp_path / "nope.jsonl") == []
    (tmp_path / "empty.jsonl").write_text("")
    assert digest.read_history(tmp_path / "empty.jsonl") == []


# --- the digest section --------------------------------------------------------------------------------------------------


def row(**repos):
    return {"time": "2026-11-10T09:00:00-05:00", "repos": counts(**repos)}


def test_the_section_shows_each_repo_now_against_last_time(tmp_path):
    text = "\n".join(digest.standard_section([row(a=(5, 8, 4)), row(a=(3, 8, 4))]))
    assert "a: 3 fail-level (was 5), 8 warn (was 8), 4 grandfathered (was 4)" in text


def test_the_worst_repo_comes_first(tmp_path):
    lines = digest.standard_section([row(a=(0, 1, 0), b=(0, 1, 0)), row(a=(0, 1, 0), b=(4, 1, 0))])
    assert lines.index(next(x for x in lines if x.startswith("- b:"))) < lines.index(next(x for x in lines if x.startswith("- a:")))


def test_a_repo_with_no_gaps_is_counted_not_listed():
    text = "\n".join(digest.standard_section([row(a=(0, 0, 0), b=(1, 0, 0)), row(a=(0, 0, 0), b=(1, 0, 0))]))
    assert "- b:" in text and "- a:" not in text and "1 repo(s) conform" in text


def test_a_repo_seen_for_the_first_time_has_no_was():
    text = "\n".join(digest.standard_section([row(a=(1, 0, 0)), row(a=(1, 0, 0), fresh=(2, 0, 0))]))
    assert "fresh: 2 fail-level (new since last run)" in text


def test_with_one_run_it_shows_the_counts_and_says_there_is_nothing_to_compare_yet():
    text = "\n".join(digest.standard_section([row(a=(2, 1, 0))]))
    assert "a: 2 fail-level, 1 warn, 0 grandfathered" in text and "no earlier run to compare" in text


def test_with_no_history_it_says_converge_has_not_recorded_a_run():
    text = "\n".join(digest.standard_section([]))
    assert "converge has not recorded a run" in text


def test_the_digest_includes_the_section_only_when_given_one():
    import datetime as dt

    now = dt.datetime(2026, 11, 10, tzinfo=dt.timezone.utc)
    assert "Standard burn-down" not in digest.render([], {}, now)
    assert "Standard burn-down" in digest.render([], {}, now, standard=["- a: 1 fail-level"])
