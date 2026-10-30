import subprocess
from pathlib import Path

from autopilot import specs

GOOD = """---
id: {id}
goal: Add the thing so that the lesson renders with a checklist.
acceptance:
  - uv run pytest tests/test_thing.py
scope:
  - src/thing/py
  - tests/test_thing.py
risk_tier: 2
{extra}---

body

{log}"""


def write(d: Path, id: str, extra: str = "", log: str = "") -> Path:
    p = d / f"{id}.md"
    p.write_text(GOOD.format(id=id, extra=extra, log=log))
    return p


def test_log_entries_reads_only_the_log_section():
    body = "text\n## Notes\n- not this\n## Log\n- 2026-10-29 filed #5\n- 2026-10-30 merged\n## After\n- nor this\n"
    assert specs.log_entries(body) == ["2026-10-29 filed #5", "2026-10-30 merged"]


def test_index_orders_active_first_and_flags_missing_issue(tmp_path):
    write(tmp_path, "aaa-draft")
    write(tmp_path, "bbb-active", extra="status: active\n")
    (tmp_path / "_TEMPLATE.md").write_text("---\nid: x\n---\n")
    rows = specs.load(tmp_path)
    assert [r.id for r in rows] == ["bbb-active", "aaa-draft"]
    assert any("no `issue:`" in p for p in rows[0].problems)
    assert rows[1].status == "draft" and rows[1].problems == []


def test_done_needs_a_log_entry_and_unknown_status_is_flagged(tmp_path):
    write(tmp_path, "ccc-done", extra="status: done\n")
    write(tmp_path, "ddd-odd", extra="status: wip\n")
    write(tmp_path, "eee-ok", extra="status: done\n", log="## Log\n- 2026-10-29 merged in #9\n")
    by = {r.id: r for r in specs.load(tmp_path)}
    assert any("no entry saying why" in p for p in by["ccc-done"].problems)
    assert any("not one of" in p for p in by["ddd-odd"].problems)
    assert by["eee-ok"].problems == []


def test_a_ready_spec_the_handshake_rejects_is_a_problem(tmp_path):
    p = tmp_path / "fff-bad.md"
    p.write_text("---\nid: fff-bad\nstatus: ready\ngoal: short\n---\n")
    r = specs.read_spec(p)
    assert r.verdict != "ACCEPTED" and any("handshake" in x for x in r.problems)


def test_id_must_match_file_name(tmp_path):
    p = write(tmp_path, "ggg-name")
    p.rename(tmp_path / "other.md")
    assert any("does not match" in x for x in specs.read_spec(tmp_path / "other.md").problems)


def test_last_change_and_history_come_from_git(tmp_path):
    p = write(tmp_path, "hhh-git")
    g = lambda *a: subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)  # noqa: E731
    g("init", "-q")
    g("add", p.name)
    g("-c", "user.email=t@e.com", "-c", "user.name=t", "-c", "commit.gpgsign=false", "commit", "-qm", "spec: add hhh")
    assert "spec: add hhh" in specs.last_changed(p)
    assert len(specs.history(p)) == 1


def test_render_empty_and_table(tmp_path):
    assert "No specs yet" in specs.render([])
    write(tmp_path, "iii-row", extra="status: ready\nissue: 12\n")
    out = specs.render(specs.load(tmp_path))
    assert "| ready | iii-row | #12 |" in out
