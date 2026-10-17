from autopilot import preflight as p

A = "a" * 40
GOOD = {
    "secrets": ["CLAUDE_CODE_OAUTH_TOKEN"],
    "variables": {"AUTOPILOT_ENABLED": "true"},
    "ruleset": {"checks": ["guard / guard", "build"], "signatures": True, "codeowner": True},
    "codeowners_catchall": False,
    "codeowners_has_block": True,
    "caller_shas": [A],
    "approved": [A],
    "latest_approved": A,
    "last_exec": "success",
    "open_agent_prs": 1,
    "max_open_prs": 3,
    "agent_ready": 4,
    "merge_classes": ["docs-only"],
}


def levels(f):
    return [lv for lv, _ in p.evaluate(f)]


def test_healthy_repo_has_no_failures_or_warnings():
    assert p.summarize(p.evaluate(GOOD))[1:] == (0, 0)


def test_each_blocker_is_a_fail():
    for patch, needle in [
        ({"secrets": []}, "CLAUDE_CODE_OAUTH_TOKEN"),
        ({"variables": {}}, "AUTOPILOT_ENABLED"),
        ({"variables": {"AUTOPILOT_ENABLED": "true", "AUTOPILOT_PAUSED": "true"}}, "PAUSED"),
        ({"ruleset": None}, "ruleset"),
        ({"ruleset": {"checks": ["build"], "signatures": True, "codeowner": True}}, "guard / guard"),
        ({"ruleset": {"checks": ["guard / guard", "build"], "signatures": False, "codeowner": True}}, "signed"),
        ({"caller_shas": []}, "shared kit"),
        ({"caller_shas": [A, "b" * 40]}, "disagree"),
        ({"approved": []}, "NOT on the approved list"),
        ({"last_exec": "failure"}, "last agent run"),
        ({"billing_suspect": True}, "billing"),
        ({"codeowners_has_block": False}, "protected-paths block"),
        ({"data_class": "restricted"}, "restricted"),
    ]:
        res = p.evaluate({**GOOD, **patch})
        assert any(lv == p.FAIL and needle in m for lv, m in res), needle


def test_warnings_dont_block():
    for patch, needle in [
        ({"codeowners_catchall": True}, "catch-all"),
        ({"last_exec": None}, "no agent run yet"),
        ({"open_agent_prs": 3}, "cap"),
        ({"agent_ready": 0}, "nothing to do"),
        ({"merge_classes": []}, "no auto-merge classes"),
        ({"latest_approved": "c" * 40}, "newer approved kit"),
        ({"ruleset": {"checks": ["guard / guard"], "signatures": True, "codeowner": True}}, "CI check"),
    ]:
        res = p.evaluate({**GOOD, **patch})
        assert any(lv == p.WARN and needle in m for lv, m in res), needle
        assert p.FAIL not in [lv for lv, _ in res], needle


def test_debug_on_a_public_repo_is_a_fail():
    f = {**GOOD, "variables": {"AUTOPILOT_ENABLED": "true", "AUTOPILOT_DEBUG": "true"}}
    assert p.FAIL not in levels(f)
    assert p.FAIL in levels({**f, "public": True})
