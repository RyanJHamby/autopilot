import datetime as dt

from autopilot.apx.github import GitHubError
from autopilot.apx.update_verify import verify

REPO, BRANCH, RUN, CAND, HEADSHA = "o/r", "main", "aaa", "bbb", "ccc"
MERGED = dt.datetime(2026, 10, 30, 12, 0, tzinfo=dt.timezone.utc)
NOW = MERGED + dt.timedelta(minutes=20)
CHECKS = ["apx / guard", "apx / build"]


class Fake:
    """GitHub as far as verify() looks; each field is one way to make the answer 'no'."""

    def __init__(self, **kw):
        self.head = kw.get("head", CAND)
        self.status = kw.get("status", "ahead")
        self.behind = kw.get("behind", 0)
        self.verified = kw.get("verified", True)
        self.pulls = kw.get("pulls", [{"number": 7, "merge_commit_sha": CAND}])
        self.merged_at = kw.get("merged_at", MERGED.isoformat())
        self.merged_by = kw.get("merged_by", "Owner")
        self.labels = kw.get("labels", [])
        self.runs = kw.get("runs", [{"name": n, "conclusion": "success", "app": {"slug": "autopilot-apx"}} for n in CHECKS])
        self.boom = kw.get("boom")

    def __call__(self, method, path, body=None):
        if self.boom:
            raise self.boom
        if path.endswith(f"/git/ref/heads/{BRANCH}"):
            return {"object": {"sha": self.head}}
        if "/compare/" in path:
            return {"status": self.status, "behind_by": self.behind}
        if path.endswith(f"/commits/{CAND}"):
            return {"commit": {"verification": {"verified": self.verified}}}
        if path.endswith(f"/commits/{CAND}/pulls"):
            return self.pulls
        if path.endswith("/pulls/7"):
            return {
                "merged_at": self.merged_at,
                "merged_by": {"login": self.merged_by} if self.merged_by else None,
                "labels": [{"name": n} for n in self.labels],
                "head": {"sha": HEADSHA},
            }
        if path.startswith(f"/repos/{REPO}/commits/{HEADSHA}/check-runs"):
            return {"check_runs": self.runs}
        raise AssertionError(path)


def run(fake=None, **kw):
    kw.setdefault("now", NOW)
    return verify(fake or Fake(), REPO, BRANCH, RUN, CAND, owner="owner", required_checks=CHECKS, **kw)


def test_everything_holds_so_it_adopts():
    assert run() == (True, "ok")


def test_each_rule_refuses_alone():
    cases = {
        "not the head": Fake(head="zzz"),
        "fast-forward": Fake(status="diverged", behind=2),
        "fast-forward ": Fake(status="ahead", behind=1),
        "Verified": Fake(verified=False),
        "exactly one PR": Fake(pulls=[]),
        "someone other": Fake(merged_by="apx-bot"),
        "not merged": Fake(merged_at=None),
        "labelled hold": Fake(labels=["hold"]),
        "required check": Fake(runs=[{"name": "apx / guard", "conclusion": "success", "app": {"slug": "autopilot-apx"}}]),
    }
    for want, fake in cases.items():
        ok, why = run(fake)
        assert not ok and want in why, (want, why)


def test_a_failing_or_pending_required_check_refuses():
    for concl in ("failure", None):
        runs = [{"name": n, "conclusion": concl, "app": {"slug": "autopilot-apx"}} for n in CHECKS]
        assert not run(Fake(runs=runs))[0]


def test_a_same_named_check_from_another_app_does_not_count():
    runs = [{"name": n, "conclusion": "success", "app": {"slug": "github-actions"}} for n in CHECKS]
    assert not run(Fake(runs=runs))[0]


def test_owner_match_ignores_case_but_a_missing_merger_refuses():
    assert run(Fake(merged_by="OWNER"))[0]
    assert not run(Fake(merged_by=None))[0]


def test_settling_delay_boundary_is_inclusive():
    assert not run(now=MERGED + dt.timedelta(minutes=14, seconds=59))[0]
    assert run(now=MERGED + dt.timedelta(minutes=15))[0]


def test_hold_switch_and_already_running_refuse_without_any_network():
    def never(*a, **k):
        raise AssertionError("must not call GitHub")

    assert verify(never, REPO, BRANCH, RUN, CAND, owner="owner", required_checks=CHECKS, hold_switch=True) == (
        False,
        "HOLD switch is on",
    )
    assert not verify(never, REPO, BRANCH, CAND, CAND, owner="owner", required_checks=CHECKS)[0]


def test_any_read_error_means_no():
    ok, why = run(Fake(boom=GitHubError(502, "/x", "bad gateway")))
    assert not ok and "could not verify" in why
