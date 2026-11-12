"""Tranche 3, all advisory (they can only warn): llm-advisory, payments-advisory, db-hygiene and mail packs.

Each test starts from a complete repo, removes one item's evidence, and expects exactly that item reported. These are judgment calls
(a small app may reasonably skip some), so none of them can fail a repo."""

import pytest
from test_pack_rules import STALE, named, record, run, tree

from autopilot.standard import capabilities, load_checks, packs


def without(files, path):
    return {k: v for k, v in files.items() if k != path}


# --- llm ----------------------------------------------------------------------------------------------------------------------

LLM = {
    "package.json": '{"dependencies": {"openai": "5", "zod": "3"}}',
    "src/lib/prompts.ts": "export const PROMPT_VERSION = 'v3';\nexport const SYSTEM = 'Be brief.';\n",
    "src/lib/llm.ts": "export const models = { primary: 'model-a', fallbackModel: 'model-b' };\n",
}
LLM_ITEMS = {"versioned-prompts": "src/lib/prompts.ts", "model-fallback": "src/lib/llm.ts"}


def test_a_repo_with_no_llm_skips_the_llm_advisory_pack(tmp_path):
    tree(tmp_path, {"README.md": "x\n"})
    assert run(tmp_path, "llm-advisory-pack").result == "skip"


def test_a_complete_llm_repo_passes(tmp_path):
    tree(tmp_path, LLM)
    r = run(tmp_path, "llm-advisory-pack")
    assert (r.result, r.findings) == ("pass", []), r.findings


@pytest.mark.parametrize("item", sorted(LLM_ITEMS))
def test_removing_one_llm_item_reports_exactly_that_item(tmp_path, item):
    tree(tmp_path, without(LLM, LLM_ITEMS[item]))
    r = run(tmp_path, "llm-advisory-pack")
    assert r.result == "fail" and named(r.findings) == [item], r.findings


def test_without_a_validation_library_boundary_validation_is_reported(tmp_path):
    files = dict(LLM, **{"package.json": '{"dependencies": {"openai": "5"}}'})
    tree(tmp_path, files)
    assert named(run(tmp_path, "llm-advisory-pack").findings) == ["boundary-validation"]


def test_a_prompt_version_that_only_appears_in_a_comment_does_not_count(tmp_path):
    files = dict(LLM, **{"src/lib/prompts.ts": "// PROMPT_VERSION goes here later\nexport const SYSTEM = 'Be brief.';\n"})
    tree(tmp_path, files)
    assert named(run(tmp_path, "llm-advisory-pack").findings) == ["versioned-prompts"]


def test_a_decision_record_satisfies_the_fallback_and_litellm_provides_one(tmp_path):
    a = dict(without(LLM, "src/lib/llm.ts"), **{"docs/decisions/0006-model-fallback.md": record("No model fallback", verified=None)})
    tree(tmp_path / "a", a)
    assert run(tmp_path / "a", "llm-advisory-pack").result == "pass"
    b = dict(without(LLM, "src/lib/llm.ts"), **{"package.json": '{"dependencies": {"litellm": "1", "zod": "3"}}'})
    tree(tmp_path / "b", b)
    assert run(tmp_path / "b", "llm-advisory-pack").result == "pass"


def test_LIMIT_a_fallback_that_is_configured_but_never_used_passes(tmp_path):
    # Pattern over code: naming a fallback model is enough, whether or not the call path ever switches to it. Recorded, not caught.
    tree(tmp_path, LLM)
    assert run(tmp_path, "llm-advisory-pack").result == "pass"


# --- payments testing ---------------------------------------------------------------------------------------------------------

PAY = {
    "package.json": '{"dependencies": {"stripe": "23"}}',
    "docs/runbooks/payments-testing.md": record("How payments are tested against the provider", verified=None),
}


def test_a_repo_with_no_payments_skips_the_payments_advisory_pack(tmp_path):
    tree(tmp_path, {"README.md": "x\n"})
    assert run(tmp_path, "payments-advisory-pack").result == "skip"


def test_a_payments_repo_with_a_testing_record_passes(tmp_path):
    tree(tmp_path, PAY)
    assert run(tmp_path, "payments-advisory-pack").result == "pass"


def test_a_payments_repo_without_the_record_is_reported(tmp_path):
    tree(tmp_path, without(PAY, "docs/runbooks/payments-testing.md"))
    r = run(tmp_path, "payments-advisory-pack")
    assert r.result == "fail" and named(r.findings) == ["contract-testing"], r.findings


def test_LIMIT_contract_tests_that_live_only_in_the_test_directory_are_not_seen(tmp_path):
    # The scanner never reads tests/ (so a mock in a fixture cannot fake a capability). Real contract tests there are invisible, which is
    # why the evidence is a record saying how they are run, not the tests themselves.
    files = without(PAY, "docs/runbooks/payments-testing.md")
    files["tests/stripe-contract.test.ts"] = "it('replays a recorded webhook', () => {});\n"
    tree(tmp_path, files)
    assert run(tmp_path, "payments-advisory-pack").result == "fail"


# --- db hygiene ---------------------------------------------------------------------------------------------------------------

DBH = {
    "package.json": '{"dependencies": {"pg": "8", "drizzle-orm": "0.3"}}',
    "migrations/0001_roles.sql": "create role app_ro;\ngrant select on all tables in schema public to app_ro;\n",
    "src/db.ts": "import { Pool } from 'pg';\nexport const pool = new Pool({ max: 10 });\n",
    "db/seed.ts": "await db.insert(users).values(fakeUser());\n",
}
DBH_ITEMS = {"least-privilege-roles": "migrations/0001_roles.sql", "connection-pooling": "src/db.ts", "no-prod-data-in-dev": "db/seed.ts"}


def test_a_repo_with_no_database_skips_db_hygiene(tmp_path):
    tree(tmp_path, {"README.md": "x\n"})
    assert run(tmp_path, "db-hygiene-pack").result == "skip"


def test_a_complete_db_repo_passes_db_hygiene(tmp_path):
    tree(tmp_path, DBH)
    r = run(tmp_path, "db-hygiene-pack")
    assert (r.result, r.findings) == ("pass", []), r.findings


@pytest.mark.parametrize("item", sorted(DBH_ITEMS))
def test_removing_one_db_hygiene_item_reports_exactly_that_item(tmp_path, item):
    tree(tmp_path, without(DBH, DBH_ITEMS[item]))
    r = run(tmp_path, "db-hygiene-pack")
    assert r.result == "fail" and named(r.findings) == [item], r.findings


def test_a_repo_that_reaches_its_database_only_through_supabase_js_is_not_asked_about_pooling(tmp_path):
    # supabase-js talks to PostgREST, not to Postgres directly, so a connection pool is not this repo's problem
    files = {k: v for k, v in DBH.items() if k != "src/db.ts"}
    files["package.json"] = '{"dependencies": {"@supabase/supabase-js": "2"}}'
    tree(tmp_path, files)
    r = run(tmp_path, "db-hygiene-pack")
    assert "connection-pooling" not in named(r.findings), r.findings


def test_a_pooler_url_or_a_pooling_decision_satisfies_pooling(tmp_path):
    a = dict(without(DBH, "src/db.ts"), **{"src/db.ts": "export const url = process.env.DB + '?pgbouncer=true';\n"})
    tree(tmp_path / "a", a)
    assert run(tmp_path / "a", "db-hygiene-pack").result == "pass"
    b = dict(without(DBH, "src/db.ts"), **{"docs/decisions/0007-connection-pooling.md": record("No pooling needed", verified=None)})
    tree(tmp_path / "b", b)
    assert run(tmp_path / "b", "db-hygiene-pack").result == "pass"


def test_a_dev_data_runbook_satisfies_no_prod_data_in_dev(tmp_path):
    files = dict(without(DBH, "db/seed.ts"), **{"docs/runbooks/dev-data.md": record("Dev data is synthetic", verified=None)})
    tree(tmp_path, files)
    assert run(tmp_path, "db-hygiene-pack").result == "pass"


def test_db_hygiene_is_separate_from_the_existing_real_database_advisory(tmp_path):
    tree(tmp_path, {"package.json": '{"dependencies": {"@prisma/client": "5"}}'})
    assert named(run(tmp_path, "db-advisory-pack").findings) == ["real-db-in-tests"]


# --- mail ---------------------------------------------------------------------------------------------------------------------

MAIL = {
    "package.json": '{"dependencies": {"resend": "4"}}',
    "docs/gates/email-deliverability.md": record("Email deliverability: SPF, DKIM and DMARC"),
}


def test_a_repo_that_sends_no_mail_skips_the_mail_pack(tmp_path):
    tree(tmp_path, {"README.md": "x\n"})
    assert run(tmp_path, "mail-pack").result == "skip"


def test_a_mail_repo_with_a_fresh_record_passes(tmp_path):
    tree(tmp_path, MAIL)
    assert run(tmp_path, "mail-pack").result == "pass"


def test_a_mail_repo_without_the_record_is_reported(tmp_path):
    tree(tmp_path, without(MAIL, "docs/gates/email-deliverability.md"))
    r = run(tmp_path, "mail-pack")
    assert r.result == "fail" and named(r.findings) == ["mail-auth-records"] and "mail detected" in r.findings[0], r.findings


@pytest.mark.parametrize("verified,why", [(None, "Verified"), (STALE, "stale")])
def test_an_undated_or_stale_deliverability_record_is_rejected(tmp_path, verified, why):
    files = dict(MAIL, **{"docs/gates/email-deliverability.md": record("Email deliverability", verified=verified)})
    tree(tmp_path, files)
    r = run(tmp_path, "mail-pack")
    assert r.result == "fail" and why in r.findings[1]


@pytest.mark.parametrize(
    "files",
    [
        {"package.json": '{"dependencies": {"nodemailer": "6"}}'},
        {"package.json": '{"dependencies": {"@sendgrid/mail": "8"}}'},
        {"src/mail.ts": "await fetch('https://api.postmarkapp.com/email', { method: 'POST' });\n"},
        {"src/mail.ts": "const key = process.env.RESEND_API_KEY;\n"},
        {"requirements.txt": "sendgrid==6.11\n"},
    ],
)
def test_the_mail_capability_is_detected_from_a_dependency_a_call_or_a_key(tmp_path, files):
    tree(tmp_path, files)
    assert "mail" in capabilities.capabilities(tmp_path)


def test_a_mail_library_that_is_only_a_dev_dependency_is_not_a_mail_capability(tmp_path):
    tree(tmp_path, {"package.json": '{"devDependencies": {"nodemailer": "6"}, "dependencies": {"next": "16"}}'})
    assert "mail" not in capabilities.capabilities(tmp_path)


# --- how they are declared ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("rule", ["llm-advisory-pack", "payments-advisory-pack", "db-hygiene-pack", "mail-pack"])
def test_every_new_rule_is_judgment_and_can_only_warn(rule):
    r = {c["id"]: c for c in load_checks()["checks"]}[rule]
    assert (r["level"], r["label"], r["evidence"]) == ("warn", "advisory", "judgment")


def test_the_packs_file_is_valid_and_each_pack_needs_what_it_is_named_for():
    data = packs.load_packs()
    assert packs.validate(data) == []
    needs = {n: p["needs"] for n, p in data["packs"].items()}
    assert needs["llm-advisory"] == "llm" and needs["payments-advisory"] == "payments"
    assert needs["db-hygiene"] == "db" and needs["mail"] == "mail"


def test_driver_is_an_allowed_condition_and_mail_an_allowed_capability():
    assert "driver" in packs.WHEN and "mail" in packs.NEEDS


def test_the_standard_document_lists_every_new_rule():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "STANDARD.md").read_text(encoding="utf-8")
    for rule in ("llm-advisory-pack", "payments-advisory-pack", "db-hygiene-pack", "mail-pack"):
        assert f"`{rule}`" in text, rule
