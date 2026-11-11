"""The pack evaluator: the three kinds of item a capability pack can require.

`code` items look at the repo's code, `record` items need a real written record (no stub, and for external facts a dated one that goes
stale), and `codeowners` items need a human owner on the risky paths. These tests use a synthetic pack so each kind is tested alone."""

import datetime

import pytest

from autopilot.standard import capabilities as cap
from autopilot.standard import packs

TODAY = datetime.date(2026, 11, 10)


def tree(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return root


def run(root, items, needs="payments", today=TODAY):
    """Evaluate a one-pack synthetic config against `root`; returns {item id: (ok, finding)}."""
    pack = {"needs": needs, "items": items}
    return {r.id: (r.ok, r.finding) for r in packs.evaluate(cap.Scan(root), pack, today=today)}


def code(id_="i", **kw):
    return {"id": id_, "kind": "code", "title": "t", "fix": "do the thing", **kw}


def record(id_="r", **kw):
    return {"id": id_, "kind": "record", "title": "t", "fix": "write it", "path": ["docs/r.md"], **kw}


GOOD = "# Threat model\n\n" + "\n".join(f"Line {i} of real content about what could go wrong." for i in range(8)) + "\n"


# --- code items --------------------------------------------------------------------------------------------------------


def test_a_code_item_passes_when_a_regex_matches_code_and_fails_otherwise(tmp_path):
    tree(tmp_path, {"src/webhook.ts": "const e = stripe.webhooks.constructEvent(body, sig, secret);\n"})
    assert run(tmp_path, [code(match=[r"constructEvent|construct_event"])])["i"][0] is True
    assert run(tmp_path, [code(match=[r"idempotency"])])["i"][0] is False


def test_a_code_item_ignores_a_match_that_is_only_in_a_comment_or_a_test(tmp_path):
    tree(tmp_path, {"src/a.ts": "// constructEvent is not used here\nconst x = 1;\n", "tests/a.test.ts": "constructEvent();\n"})
    assert run(tmp_path, [code(match=[r"constructEvent"])])["i"][0] is False


def test_a_code_item_can_be_satisfied_by_a_path_glob_even_in_a_docs_or_public_dir(tmp_path):
    tree(tmp_path / "with", {"public/terms.html": "<h1>Terms</h1>\n"})
    tree(tmp_path / "without", {"public/index.html": "<h1>Home</h1>\n"})
    items = [code(paths=["**/terms*", "**/refund*"])]
    assert run(tmp_path / "with", items)["i"][0] is True
    assert run(tmp_path / "without", items)["i"][0] is False


def test_a_path_glob_matches_a_route_directory_and_a_nested_health_file(tmp_path):
    tree(tmp_path, {"src/app/api/health/route.ts": "export const GET = () => 1;\n"})
    assert run(tmp_path, [code(paths=["**/health*/**", "**/health*"])])["i"][0] is True


def test_a_code_item_can_be_satisfied_by_a_runtime_dependency(tmp_path):
    tree(tmp_path, {"package.json": '{"dependencies": {"@sentry/nextjs": "9"}}'})
    assert run(tmp_path, [code(deps=["@sentry/*", "sentry-sdk"])])["i"][0] is True


def test_a_dev_dependency_does_not_satisfy_a_dependency_item(tmp_path):
    tree(tmp_path, {"package.json": '{"devDependencies": {"@sentry/nextjs": "9"}}'})
    assert run(tmp_path, [code(deps=["@sentry/*"])])["i"][0] is False


def test_include_sql_lets_a_migration_satisfy_an_item_that_code_alone_would_not(tmp_path):
    tree(tmp_path, {"supabase/migrations/0005_events.sql": "create table processed_stripe_events (id text primary key);\n"})
    assert run(tmp_path, [code(match=[r"processed_\w*events"])])["i"][0] is False
    assert run(tmp_path, [code(match=[r"processed_\w*events"], include_sql=True)])["i"][0] is True


def test_a_code_item_with_no_way_to_pass_is_a_config_error_not_a_silent_pass():
    assert any("needs match, paths or deps" in p for p in packs.validate({"packs": {"p": {"needs": "payments", "items": [code()]}}}))


# --- when: an item that only applies in some repos ----------------------------------------------------------------------


def test_a_hosted_only_item_is_skipped_for_a_local_tool(tmp_path):
    tree(tmp_path, {"package.json": '{"dependencies": {"openai": "1"}}'})
    assert run(tmp_path, [code(match=["zzz"], when="hosted")], needs="llm") == {}


def test_a_hosted_only_item_applies_once_the_repo_is_deployed_with_users(tmp_path):
    tree(tmp_path, {"package.json": '{"dependencies": {"openai": "1", "@supabase/ssr": "1"}}', "vercel.json": "{}"})
    assert run(tmp_path, [code(match=["zzz"], when="hosted")], needs="llm")["i"][0] is False


def test_an_auth_only_item_needs_auth_to_be_present(tmp_path):
    tree(tmp_path, {"package.json": '{"dependencies": {"openai": "1"}}'})
    assert run(tmp_path, [code(match=["zzz"], when="auth")], needs="llm") == {}
    tree(tmp_path, {"package.json": '{"dependencies": {"openai": "1", "next-auth": "1"}}'})
    assert run(tmp_path, [code(match=["zzz"], when="auth")], needs="llm")["i"][0] is False


# --- record items: a real written record -------------------------------------------------------------------------------


def test_a_record_must_exist(tmp_path):
    ok, why = run(tmp_path, [record()])["r"]
    assert ok is False and "docs/r.md" in why


def test_a_record_passes_with_real_content(tmp_path):
    tree(tmp_path, {"docs/r.md": GOOD})
    assert run(tmp_path, [record()])["r"][0] is True


@pytest.mark.parametrize("marker", ["TODO: fill in", "TBD", "FIXME", "<fill me in>", "REPLACE-ME"])
def test_a_record_with_placeholder_text_is_a_stub_not_a_record(tmp_path, marker):
    tree(tmp_path, {"docs/r.md": GOOD + f"\n{marker}\n"})
    ok, why = run(tmp_path, [record()])["r"]
    assert ok is False and "placeholder" in why


def test_a_record_that_is_only_headings_and_a_line_or_two_is_too_short(tmp_path):
    tree(tmp_path, {"docs/r.md": "# Title\n\n## Section\n\nOne line.\n"})
    ok, why = run(tmp_path, [record(min_lines=5)])["r"]
    assert ok is False and "too short" in why


def test_the_first_existing_candidate_path_is_the_one_checked(tmp_path):
    tree(tmp_path, {"docs/runbooks/b.md": GOOD})
    assert run(tmp_path, [record(path=["docs/a.md", "docs/runbooks/b.md"])])["r"][0] is True


# --- dated records: external facts the repo can only record --------------------------------------------------------------


def dated(date_line):
    return GOOD + date_line + "\n"


def test_a_dated_record_needs_a_verified_date(tmp_path):
    tree(tmp_path, {"docs/r.md": GOOD})
    ok, why = run(tmp_path, [record(verified=True)])["r"]
    assert ok is False and "Verified" in why


def test_a_fresh_verified_date_passes(tmp_path):
    tree(tmp_path, {"docs/r.md": dated("Verified: 2026-11-01")})
    assert run(tmp_path, [record(verified=True)])["r"][0] is True


def test_the_verified_line_may_be_bold_or_lowercase(tmp_path):
    tree(tmp_path, {"docs/r.md": dated("**verified:** 2026-11-01")})
    assert run(tmp_path, [record(verified=True)])["r"][0] is True


def test_a_record_older_than_180_days_is_stale(tmp_path):
    tree(tmp_path, {"docs/r.md": dated("Verified: 2026-04-01")})  # 223 days before TODAY
    ok, why = run(tmp_path, [record(verified=True)])["r"]
    assert ok is False and "stale" in why and "2026-04-01" in why


def test_the_staleness_boundary_is_inclusive_at_180_days(tmp_path):
    on_the_line = (TODAY - datetime.timedelta(days=180)).isoformat()
    over = (TODAY - datetime.timedelta(days=181)).isoformat()
    tree(tmp_path / "a", {"docs/r.md": dated(f"Verified: {on_the_line}")})
    tree(tmp_path / "b", {"docs/r.md": dated(f"Verified: {over}")})
    assert run(tmp_path / "a", [record(verified=True)])["r"][0] is True
    assert run(tmp_path / "b", [record(verified=True)])["r"][0] is False


def test_a_verified_date_in_the_future_is_rejected(tmp_path):
    tree(tmp_path, {"docs/r.md": dated("Verified: 2027-01-01")})
    ok, why = run(tmp_path, [record(verified=True)])["r"]
    assert ok is False and "future" in why


@pytest.mark.parametrize("bad", ["Verified: soon", "Verified: 2026-13-45", "Verified: 11/01/2026"])
def test_a_malformed_verified_date_is_rejected(tmp_path, bad):
    tree(tmp_path, {"docs/r.md": dated(bad)})
    assert run(tmp_path, [record(verified=True)])["r"][0] is False


# --- codeowners items --------------------------------------------------------------------------------------------------


def test_a_codeowners_item_needs_an_entry_on_the_risky_paths(tmp_path):
    item = {"id": "owned", "kind": "codeowners", "title": "t", "fix": "own it", "cover": "stripe|billing"}
    tree(tmp_path / "a", {".github/CODEOWNERS": "/src/app/api/stripe/ @me\n/src/lib/stripe.ts @me\n"})
    tree(tmp_path / "b", {".github/CODEOWNERS": "* @me\n"})
    tree(tmp_path / "c", {})
    assert run(tmp_path / "a", [item])["owned"][0] is True
    assert run(tmp_path / "b", [item])["owned"][0] is False  # a catch-all does not single out billing
    assert run(tmp_path / "c", [item])["owned"][0] is False


def test_codeowners_is_found_at_the_root_and_in_docs_too(tmp_path):
    item = {"id": "owned", "kind": "codeowners", "title": "t", "fix": "own it", "cover": "billing"}
    tree(tmp_path / "a", {"CODEOWNERS": "/billing/ @me\n"})
    tree(tmp_path / "b", {"docs/CODEOWNERS": "/billing/ @me\n"})
    assert run(tmp_path / "a", [item])["owned"][0] is True
    assert run(tmp_path / "b", [item])["owned"][0] is True


def test_a_commented_out_codeowners_line_does_not_count(tmp_path):
    item = {"id": "owned", "kind": "codeowners", "title": "t", "fix": "own it", "cover": "billing"}
    tree(tmp_path, {".github/CODEOWNERS": "# /billing/ @me\n"})
    assert run(tmp_path, [item])["owned"][0] is False


# --- findings and validation -------------------------------------------------------------------------------------------


def test_a_failing_item_says_what_is_missing_and_how_to_fix_it(tmp_path):
    ok, why = run(tmp_path, [code(match=["zzz"])])["i"]
    assert ok is False and "do the thing" in why


def test_the_pack_helper_reports_a_skip_when_the_capability_is_absent(tmp_path):
    cfg = {"packs": {"payments": {"needs": "payments", "items": [code(match=["zzz"])]}}}
    outcome, findings = packs.check_pack(cap.Scan(tmp_path), "payments", cfg, today=TODAY)
    assert outcome == "skip" and "no payments capability" in findings[0]


def test_the_pack_helper_names_the_evidence_and_every_missing_item(tmp_path):
    tree(tmp_path, {"package.json": '{"dependencies": {"stripe": "1"}}'})
    items = [code("a", match=["zzz"]), code("b", match=["qqq"])]
    cfg = {"packs": {"payments": {"needs": "payments", "items": items}}}
    outcome, findings = packs.check_pack(cap.Scan(tmp_path), "payments", cfg, today=TODAY)
    text = "\n".join(findings)
    assert outcome == "fail" and "payments detected" in findings[0] and "stripe" in findings[0]
    assert "a:" in text and "b:" in text


def test_the_pack_helper_passes_when_everything_is_present(tmp_path):
    tree(tmp_path, {"package.json": '{"dependencies": {"stripe": "1"}}', "src/w.ts": "constructEvent();\n"})
    cfg = {"packs": {"payments": {"needs": "payments", "items": [code(match=["constructEvent"])]}}}
    assert packs.check_pack(cap.Scan(tmp_path), "payments", cfg, today=TODAY) == ("pass", [])


def good_pack():
    return {"packs": {"p": {"needs": "payments", "items": [code(match=["x"]), record()]}}}


def test_validation_accepts_a_good_config_and_rejects_each_kind_of_mistake():
    assert packs.validate(good_pack()) == []
    for mutate, expect in (
        (lambda d: d["packs"]["p"].update(needs="teleportation"), "needs"),
        (lambda d: d["packs"]["p"]["items"][0].update(kind="vibes"), "kind"),
        (lambda d: d["packs"]["p"]["items"][1].update(id="i"), "duplicate"),
        (lambda d: d["packs"]["p"]["items"][0].pop("fix"), "fix"),
        (lambda d: d["packs"]["p"]["items"][1].pop("path"), "path"),
        (lambda d: d["packs"]["p"]["items"][0].update(when="sometimes"), "when"),
    ):
        data = good_pack()
        mutate(data)
        assert any(expect in p for p in packs.validate(data)), expect


def test_the_shipped_packs_file_validates():
    assert packs.validate(packs.load_packs()) == []
