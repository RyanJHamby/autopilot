import datetime as dt

from autopilot import report

NOW = dt.datetime(2026, 10, 16, tzinfo=dt.timezone.utc)


def pr(n, state="MERGED", merged=True, hours=2, labels=(), head="agent/1-2", title="t", body=""):
    c = NOW - dt.timedelta(days=1)
    return {
        "number": n,
        "title": title,
        "body": body,
        "headRefName": head,
        "state": state,
        "createdAt": c.isoformat(),
        "mergedAt": (c + dt.timedelta(hours=hours)).isoformat() if merged else None,
        "closedAt": None,
        "labels": [{"name": x} for x in labels],
    }


def test_counts_rate_and_median():
    prs = [pr(1, hours=1), pr(2, hours=3), pr(3, state="CLOSED", merged=False), pr(4, state="OPEN", merged=False)]
    c = report.scorecard(prs, since=NOW - dt.timedelta(days=7))
    assert (c["opened"], c["merged"], c["closed_unmerged"], c["open"]) == (4, 2, 1, 1)
    assert c["merge_rate"] == 0.67 and c["median_hours_to_merge"] == 2.0


def test_human_branches_and_old_prs_ignored():
    old = pr(9)
    old["createdAt"] = (NOW - dt.timedelta(days=30)).isoformat()
    c = report.scorecard([pr(1, head="feature/x"), old], since=NOW - dt.timedelta(days=7))
    assert c["opened"] == 0 and c["merge_rate"] is None


def test_reverts_and_classes():
    prs = [
        pr(1, labels=["automerged", "automerged:docs-only"]),
        pr(2, labels=["automerged:docs-only"]),
        pr(3),
        pr(10, head="revert-1", title='Revert "t"', body="Reverts #1"),
    ]
    c = report.scorecard(prs, since=NOW - dt.timedelta(days=7))
    assert c["by_class"]["docs-only"] == {"merged": 2, "reverted": 1}
    assert c["by_class"]["human-merged"]["merged"] == 1 and c["reverted"] == 1


def test_promotion_needs_clean_streak_and_not_already_enabled():
    c = {
        "by_class": {
            "docs-only": {"merged": 12, "reverted": 0},
            "tests-add-only": {"merged": 12, "reverted": 1},
            "generated": {"merged": 3, "reverted": 0},
            "human-merged": {"merged": 50, "reverted": 0},
        }
    }
    assert report.promotion_candidates(c, []) == ["docs-only"]
    assert report.promotion_candidates(c, ["docs-only"]) == []
