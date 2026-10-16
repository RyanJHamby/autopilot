from autopilot import retro


def test_run_classification():
    c = retro.classify_run
    assert c({"conclusion": "success"}) is None and c({"conclusion": "cancelled"}) is None
    assert c({"conclusion": "timed_out"}) == "timeout"
    assert c({"conclusion": "failure", "guard_output": "  - [comms] a.py: outbound"}) == "guard:comms"
    assert c({"conclusion": "failure", "failed_step": "Run anthropics/claude-code-action@x"}) == "agent-error"
    assert c({"conclusion": "failure", "failed_step": "Install deps (npm ci)"}) == "infra:install-deps-npm-ci"
    assert c({"conclusion": "failure"}) == "failed-unknown"


def test_pr_classification():
    c = retro.classify_pr
    assert c({"state": "MERGED", "mergedAt": "x"}) is None and c({"state": "OPEN"}) is None
    assert c({"state": "CLOSED", "ci": "red"}) == "ci-red"
    assert c({"state": "CLOSED", "comments": 2}) == "rejected-by-owner"
    assert c({"state": "CLOSED"}) == "closed-no-reason"
    assert c({"state": "CLOSED", "guard_output": "[size] big"}) == "guard:size"


def test_packet_only_marks_repeated_causes():
    cnt = retro.causes([{"conclusion": "failure", "failed_step": "claude"}] * 2 + [{"conclusion": "timed_out"}], [])
    md = retro.packet(cnt, {"agent-error": ["run 1: refused", "run 2: refused"], "timeout": ["run 3"]})
    assert "| agent-error | 2 | yes |" in md and "| timeout | 1 | no (seen once) |" in md
    assert "## agent-error" in md and "## timeout" not in md
    assert "No failures" in retro.packet(retro.causes([], []), {})
