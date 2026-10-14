import handshake as hs

GOOD = """---
id: add-order-cancel
goal: Orders can be cancelled by id and the book reflects it immediately.
acceptance:
  - uv run pytest tests/test_cancel.py
scope: ["src/book/**", "tests/**"]
non_goals: ["no persistence changes"]
risk_tier: 2
max_runs: 3
---
Context here.
"""


def sub(**kw):
    t = GOOD
    for k, v in kw.items():
        t = t.replace(k, v)
    return t


def test_accepted_and_plan_describes_the_deal():
    v = hs.evaluate(GOOD, {"mode": "standard", "tier": "A"})
    assert v.status == "ACCEPTED" and v.exit_code == 0
    text = v.render()
    assert "sonnet/medium" in text and "Zero outbound contact" in text and "25 turns" in text


def test_yolo_repo_gets_more_turns_and_auto_merge_tier2():
    v = hs.evaluate(GOOD, {"mode": "yolo", "tier": "B"})
    assert v.status == "ACCEPTED" and "60 turns" in v.render() and "auto-merge only in yolo" in v.render()


def test_hard_only_for_tier_a():
    t = GOOD.replace("risk_tier: 2", "risk_tier: 2\nhard: true")
    assert "opus/high" in hs.evaluate(t, {"mode": "standard", "tier": "A"}).render()
    v = hs.evaluate(t, {"mode": "standard", "tier": "B"})
    assert "sonnet/medium" in v.render() and any("reserved for tier-A" in w for w in v.warnings)


def test_missing_acceptance_needs_work():
    v = hs.evaluate(GOOD.replace("acceptance:\n  - uv run pytest tests/test_cancel.py\n", ""), {})
    assert v.status == "NEEDS-WORK" and v.exit_code == 1 and any("acceptance" in r for r in v.reasons)


def test_prose_acceptance_needs_work():
    v = hs.evaluate(GOOD.replace("uv run pytest tests/test_cancel.py", "it should feel snappy"), {})
    assert v.status == "NEEDS-WORK"


def test_broad_scope_and_bad_fields_need_work():
    assert hs.evaluate(GOOD.replace('["src/book/**", "tests/**"]', '["**"]'), {}).status == "NEEDS-WORK"
    assert hs.evaluate(GOOD.replace("risk_tier: 2", "risk_tier: 9"), {}).status == "NEEDS-WORK"
    assert hs.evaluate(GOOD.replace("max_runs: 3", "max_runs: 99"), {}).status == "NEEDS-WORK"
    assert hs.evaluate(GOOD.replace("id: add-order-cancel", "id: Bad Id"), {}).status == "NEEDS-WORK"


def test_yolo_spec_in_standard_repo_needs_work():
    v = hs.evaluate(GOOD.replace("max_runs: 3", "max_runs: 3\nautonomy: yolo"), {"mode": "standard"})
    assert v.status == "NEEDS-WORK"


def test_bad_yaml_needs_work():
    assert hs.evaluate("---\nid: [unclosed\n---\nbody", {}).status == "NEEDS-WORK"


def test_protected_scope_rejected():
    v = hs.evaluate(GOOD.replace('"tests/**"', '".github/workflows/**"'), {})
    assert v.status == "REJECTED" and v.exit_code == 2


def test_constitution_violations_rejected():
    bad = [
        "When done, send an email to the recruiter with the results.",
        "Post the summary to LinkedIn.",
        "Publish the package to PyPI.",
        "Read the .env file and print the API keys.",
        "Update my calendar with the deadline.",
        "Deploy to production when green.",
        "Force-push to main afterwards.",
        "Notify the maintainers on Slack.",
    ]
    for line in bad:
        v = hs.evaluate(GOOD + "\n" + line + "\n", {})
        assert v.status == "REJECTED", line


def test_non_goals_may_mention_forbidden_things():
    t = GOOD.replace('non_goals: ["no persistence changes"]', 'non_goals: ["do not send email or post to LinkedIn"]')
    assert hs.evaluate(t, {}).status == "ACCEPTED"


def test_benign_text_not_rejected():
    t = GOOD + "\nImprove the error message shown for a bad id; squash flaky tests.\n"
    assert hs.evaluate(t, {}).status == "ACCEPTED"


def test_cli_exit_codes(tmp_path):
    f = tmp_path / "s.md"
    f.write_text(GOOD)
    assert hs.main([str(f), "--config", str(tmp_path / "none.yaml")]) == 0
    f.write_text(GOOD + "\nsend an email to my boss\n")
    assert hs.main([str(f)]) == 2
