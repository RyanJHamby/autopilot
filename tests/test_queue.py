import pytest

from autopilot import queue
from autopilot.apx.batch import Batch, BatchError, Item, parse

B = Batch("b", (Item(1), Item(2, depends_on=(1,)), Item(3), Item(4), Item(5), Item(6)))


def st(prs, labels):
    return dict(queue.item_states(B, prs, labels))


def pr(n, state="OPEN", merged=None):
    return {"headRefName": f"agent/{n}-x", "state": state, "mergedAt": merged}


def test_states():
    labels = {2: {"agent-ready"}, 3: {"agent-ready", "hold"}, 4: set(), 5: {"agent-ready"}}
    s = st([pr(1, "MERGED", "t")], labels)
    assert s[1] == "merged"
    assert s[2] == "ready"
    assert s[3].startswith("held")
    assert s[4] == "needs-label"
    assert s[5] == "ready"
    assert s[6] == "issue-closed-or-missing"


def test_waiting_and_pr_open_and_closed_unmerged():
    labels = {1: {"agent-ready"}, 2: {"agent-ready"}}
    s = st([], labels)
    assert s[2] == "waiting #1" and s[1] == "ready"
    assert st([pr(1)], labels)[1] == "pr-open"
    assert st([pr(1, "CLOSED")], labels)[1].startswith("closed-unmerged")


def test_non_agent_branches_ignored():
    assert st([{"headRefName": "feat/1-x", "state": "MERGED", "mergedAt": "t"}], {1: {"agent-ready"}})[1] == "ready"


def test_render_counts_merged():
    out = queue.render(B, queue.item_states(B, [pr(1, "MERGED", "t")], {}))
    assert out.startswith("batch b: 1/6 merged") and "after #1" in out


def test_scaffold_roundtrips_through_planner_parser(tmp_path):
    p = queue.scaffold("b1", ["10", "11:10", "12:10,11"], tmp_path / "x")
    b = parse(p.read_text())
    assert [(i.issue, i.depends_on) for i in b.items] == [(10, ()), (11, (10,)), (12, (10, 11))]


def test_scaffold_refuses_bad_and_existing(tmp_path):
    with pytest.raises(BatchError):
        queue.scaffold("b1", ["1:1"], tmp_path)
    with pytest.raises(BatchError):
        queue.scaffold("BAD ID", ["1"], tmp_path)
    assert not list(tmp_path.glob("*"))
    queue.scaffold("b1", ["1"], tmp_path)
    with pytest.raises(FileExistsError):
        queue.scaffold("b1", ["2"], tmp_path)
