from autopilot.apx import spike as sp

REPO = "RyanJHamby/autopilot"


def api_for(verified=True, runs=None, ref="agent/0-spike", slug="autopilot-apx"):
    runs = (
        runs
        if runs is not None
        else [
            {"name": "apx / guard", "status": "completed", "conclusion": "success", "app": {"slug": slug}},
            {"name": "apx / build", "status": "completed", "conclusion": "success", "app": {"slug": slug}},
        ]
    )

    def api(method, path, body=None):
        assert method == "GET"  # the checker is strictly read-only
        if path.endswith("/pulls/5"):
            return {"head": {"ref": ref, "sha": "s" * 40}}
        if "/pulls/5/commits" in path:
            return [
                {
                    "sha": "c" * 40,
                    "commit": {"verification": {"verified": verified, "reason": "valid" if verified else "unsigned"}},
                }
            ]
        if "/check-runs" in path:
            return {"check_runs": runs}
        raise AssertionError(path)

    return api


def go(**kw):
    return {
        r.name: r
        for r in sp.check_spike(api_for(**kw), REPO, 5, app_slug="autopilot-apx", expect_contexts=["apx / guard", "apx / build"])
    }


def test_all_unknowns_confirmed():
    r = go()
    assert all(x.ok for x in r.values()), {n: x.detail for n, x in r.items() if not x.ok}
    text, ok = sp.render(list(r.values()))
    assert ok and "all unknowns confirmed" in text


def test_unverified_commits_are_reported_with_the_reason():
    r = go(verified=False)["every commit is Verified"]
    assert not r.ok and "unsigned" in r.detail


def test_missing_or_incomplete_checks_fail():
    assert not go(runs=[])["check run 'apx / guard' posted and completed"].ok
    pending = [{"name": "apx / guard", "status": "in_progress", "conclusion": None, "app": {"slug": "autopilot-apx"}}]
    assert not go(runs=pending)["check run 'apx / guard' posted and completed"].ok


def test_check_posted_by_someone_else_fails_the_provenance_line():
    r = go(slug="github-actions")
    assert not r["'apx / guard' was posted by the apx App"].ok


def test_head_must_be_an_agent_branch():
    assert not go(ref="main")["head branch is agent/*"].ok
