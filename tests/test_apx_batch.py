import pytest

from autopilot.apx import batch
from autopilot.apx.batch import Batch, BatchError, Item

B = Batch(
    "b1", (Item(1, scope=("src/a/**",)), Item(2, depends_on=(1,)), Item(3, scope=("src/a/x.py",)), Item(4, scope=("docs/**",)))
)


def run(picked, merged=(), flight=(), limit=10, batches=(B,)):
    return batch.order_and_hold(picked, list(batches), set(merged), set(flight), limit)


def test_parse_ok():
    b = batch.parse("id: b1\nitems:\n  - issue: 1\n    scope: ['a/**']\n  - issue: 2\n    depends_on: [1]\n")
    assert b.items == (Item(1, (), ("a/**",)), Item(2, (1,), ()))


@pytest.mark.parametrize(
    "text",
    [
        "id: B1\nitems: [{issue: 1}]",
        "id: b1\nitems: []",
        "id: b1\nitems: [{issue: 1}, {issue: 1}]",
        "id: b1\nitems: [{issue: 1, depends_on: [1]}]",
        "id: b1\nitems: [{issue: 1, depends_on: [2]}, {issue: 2, depends_on: [1]}]",
        "id: b1\nitems: [{issue: '1'}]",
        "id: b1\nitems: [{issue: 1, scope: [3]}]",
        "id: b1\nitems: [{issue: 1, depends_on: [true]}]",
        ": : :",
    ],
)
def test_parse_rejects(text):
    with pytest.raises(BatchError):
        batch.parse(text)


def test_parse_all_drops_bad_and_duplicate_batches():
    good = "id: a\nitems: [{issue: 1}]"
    dup = "id: b\nitems: [{issue: 1}, {issue: 2}]"
    bad = "nope"
    assert [b.id for b in batch.parse_all([bad, good, dup])] == ["a"]


def test_dependency_holds_until_merged():
    run_now, held = run([2])
    assert run_now == [] and "#1" in held[2]
    assert run([2], merged={1})[0] == [2]


def test_dependency_not_satisfied_by_in_flight():
    assert run([2], flight={1})[0] == []


def test_scope_overlap_with_in_flight_held():
    assert run([3], flight={1})[0] == [] and "overlap" in run([3], flight={1})[1][3]


def test_scope_overlap_within_round_first_wins():
    assert run([1, 3])[0] == [1]


def test_disjoint_scopes_run_together():
    assert run([1, 4])[0] == [1, 4]


def test_unscoped_and_non_batch_issues_pass_through():
    assert run([99, 2], merged={1})[0] == [99, 2]


def test_manifest_order_beats_gate_order_within_batch_slots():
    b = Batch("b", (Item(10), Item(11), Item(12)))
    assert run([12, 99, 10], batches=(b,))[0] == [10, 99, 12]


def test_limit_applies_after_holds():
    assert run([2, 4, 99], limit=1)[0] == [4]


def test_overlap_prefix_logic():
    assert batch.overlaps(("src/**",), ("src/a/b.py",))
    assert not batch.overlaps(("src/a/**",), ("src/b/**",))
    assert not batch.overlaps((), ("src/**",))
