"""auth-pack, db-pack and db-advisory-pack: each starts from a complete repo, removes one item's evidence, and expects exactly that item reported.

Auth is judgment (an advisory rule that only warns): "don't build your own auth" cannot be detected reliably. The DB pack is enforced, because a
database with no tested backup and no migration runbook is the failure that is worst to learn about late. Records are self-attested."""

import datetime

import pytest
from test_pack_rules import named, record, run, tree

from autopilot.standard import engine, load_checks, packs

STALE = (datetime.date.today() - datetime.timedelta(days=400)).isoformat()


# --- auth ----------------------------------------------------------------------------------------------------------------

AUTH = {
    "package.json": '{"dependencies": {"@clerk/nextjs": "5"}}',
    "src/lib/rate-limit.ts": "export async function checkRateLimit(ip: string) { return true; }\n",
    "src/lib/account.ts": "export async function deleteAccount(id: string) { /* removes the user and their data */ }\n",
    "docs/threat-model.md": record("Threat model"),
}
AUTH_ITEMS = {
    "signup-abuse": "src/lib/rate-limit.ts",
    "account-deletion": "src/lib/account.ts",
    "threat-model": "docs/threat-model.md",
}


def test_a_repo_with_no_auth_capability_skips_the_auth_pack(tmp_path):
    tree(tmp_path, {"README.md": "x\n"})
    assert run(tmp_path, "auth-pack").result == "skip"


def test_a_complete_auth_repo_passes(tmp_path):
    tree(tmp_path, AUTH)
    r = run(tmp_path, "auth-pack")
    assert (r.result, r.findings) == ("pass", [])


@pytest.mark.parametrize("item", sorted(AUTH_ITEMS))
def test_removing_one_auth_item_reports_exactly_that_item(tmp_path, item):
    tree(tmp_path, {k: v for k, v in AUTH.items() if k != AUTH_ITEMS[item]})
    r = run(tmp_path, "auth-pack")
    assert r.result == "fail" and named(r.findings) == [item], r.findings
    assert "auth detected" in r.findings[0]


def test_hand_rolled_auth_with_no_managed_provider_and_no_decision_is_reported(tmp_path):
    files = dict(AUTH)
    files["package.json"] = '{"dependencies": {"jsonwebtoken": "9", "bcrypt": "5"}}'
    tree(tmp_path, files)
    r = run(tmp_path, "auth-pack")
    assert r.result == "fail" and named(r.findings) == ["managed-auth"], r.findings


def test_a_decision_record_about_auth_satisfies_managed_auth_for_hand_rolled_auth(tmp_path):
    files = dict(AUTH)
    files["package.json"] = '{"dependencies": {"jsonwebtoken": "9"}}'
    files["docs/decisions/0003-own-auth.md"] = record("Why we run our own auth", verified=None)
    tree(tmp_path, files)
    assert run(tmp_path, "auth-pack").result == "pass"


def test_a_captcha_dependency_satisfies_signup_abuse_without_a_rate_limit_file(tmp_path):
    files = {k: v for k, v in AUTH.items() if k != AUTH_ITEMS["signup-abuse"]}
    files["package.json"] = '{"dependencies": {"@clerk/nextjs": "5", "@marsidev/react-turnstile": "1"}}'
    tree(tmp_path, files)
    assert run(tmp_path, "auth-pack").result == "pass"


def test_a_delete_account_route_satisfies_account_deletion(tmp_path):
    files = {k: v for k, v in AUTH.items() if k != AUTH_ITEMS["account-deletion"]}
    files["src/app/api/account/delete/route.ts"] = "export const DELETE = () => new Response('ok');\n"
    tree(tmp_path, files)
    assert run(tmp_path, "auth-pack").result == "pass"


def test_an_auth_decision_record_does_not_satisfy_signup_abuse_or_deletion(tmp_path):
    # one record about auth must not pass items it says nothing about
    files = {k: v for k, v in AUTH.items() if k not in (AUTH_ITEMS["signup-abuse"], AUTH_ITEMS["account-deletion"])}
    files["docs/decisions/0003-own-auth.md"] = record("Why we run our own auth", verified=None)
    tree(tmp_path, files)
    r = run(tmp_path, "auth-pack")
    assert r.result == "fail" and named(r.findings) == ["account-deletion", "signup-abuse"], r.findings


def test_LIMIT_a_rate_limit_that_is_named_but_never_applied_passes(tmp_path):
    # The check is a pattern over code. A function called checkRateLimit that no route calls still satisfies it. Recorded, not caught.
    tree(tmp_path, AUTH)
    assert run(tmp_path, "auth-pack").result == "pass"


# --- db ------------------------------------------------------------------------------------------------------------------

DB = {
    "package.json": '{"dependencies": {"@prisma/client": "5"}}',
    "docs/gates/db-backups.md": record("Database backups and restore drill"),
    "docs/runbooks/migrations.md": record("Safe migrations", verified=None),
    "docs/threat-model.md": record("Threat model"),
}
DB_ITEMS = {
    "backups": "docs/gates/db-backups.md",
    "safe-migrations": "docs/runbooks/migrations.md",
    "threat-model": "docs/threat-model.md",
}


def test_a_repo_with_no_database_skips_the_db_pack(tmp_path):
    tree(tmp_path, {"README.md": "x\n"})
    assert run(tmp_path, "db-pack").result == "skip"


def test_a_complete_db_repo_passes(tmp_path):
    tree(tmp_path, DB)
    r = run(tmp_path, "db-pack")
    assert (r.result, r.findings) == ("pass", [])


@pytest.mark.parametrize("item", sorted(DB_ITEMS))
def test_removing_one_db_item_reports_exactly_that_item(tmp_path, item):
    tree(tmp_path, {k: v for k, v in DB.items() if k != DB_ITEMS[item]})
    r = run(tmp_path, "db-pack")
    assert r.result == "fail" and named(r.findings) == [item], r.findings
    assert "db detected" in r.findings[0]


def test_a_backup_record_with_no_verified_date_is_rejected(tmp_path):
    files = dict(DB)
    files["docs/gates/db-backups.md"] = record("Database backups and restore drill", verified=None)
    tree(tmp_path, files)
    r = run(tmp_path, "db-pack")
    assert r.result == "fail" and named(r.findings) == ["backups"] and "Verified" in r.findings[1]


def test_a_backup_record_verified_more_than_180_days_ago_is_stale(tmp_path):
    files = dict(DB)
    files["docs/gates/db-backups.md"] = record("Database backups and restore drill", verified=STALE)
    tree(tmp_path, files)
    r = run(tmp_path, "db-pack")
    assert r.result == "fail" and "stale" in r.findings[1]


def test_a_backup_record_with_placeholder_text_is_rejected(tmp_path):
    files = dict(DB)
    files["docs/gates/db-backups.md"] = record("Database backups and restore drill") + "\nTODO: set the retention period\n"
    tree(tmp_path, files)
    r = run(tmp_path, "db-pack")
    assert r.result == "fail" and named(r.findings) == ["backups"] and "placeholder" in r.findings[1]


def test_a_supabase_migrations_directory_alone_makes_the_db_capability_appear(tmp_path):
    tree(tmp_path, {"supabase/migrations/0001_init.sql": "create table t (id int);\n"})
    r = run(tmp_path, "db-pack")
    assert r.result == "fail" and "db detected" in r.findings[0]
    assert named(r.findings) == ["backups", "safe-migrations", "threat-model"]


# --- db advisory ---------------------------------------------------------------------------------------------------------


def test_the_real_database_in_tests_advisory_skips_without_a_database(tmp_path):
    tree(tmp_path, {"README.md": "x\n"})
    assert run(tmp_path, "db-advisory-pack").result == "skip"


def test_a_db_repo_with_no_real_database_in_its_tests_is_reported(tmp_path):
    tree(tmp_path, {"package.json": '{"dependencies": {"@prisma/client": "5"}}'})
    r = run(tmp_path, "db-advisory-pack")
    assert r.result == "fail" and named(r.findings) == ["real-db-in-tests"], r.findings


@pytest.mark.parametrize(
    "evidence",
    [
        {"docker-compose.yml": "services:\n  db:\n    image: postgres:16\n"},
        {"src/test-support/testcontainers.ts": "import { PostgreSqlContainer } from '@testcontainers/postgresql';\n"},
        {"supabase/config.toml": "project_id = 'x'\n"},
    ],
)
def test_a_compose_file_a_testcontainers_import_or_a_local_supabase_config_satisfies_it(tmp_path, evidence):
    files = {"package.json": '{"dependencies": {"@prisma/client": "5"}}', **evidence}
    tree(tmp_path, files)
    assert run(tmp_path, "db-advisory-pack").result == "pass"


def test_LIMIT_a_real_database_started_only_inside_a_test_directory_is_not_seen(tmp_path):
    # The scanner never reads tests/ (so a mock in a fixture cannot fake a capability), which also means a testcontainers setup that lives only
    # there is invisible. Recorded, not caught: put the setup outside the test directory, or accept the advisory warning.
    tree(
        tmp_path,
        {
            "package.json": '{"dependencies": {"@prisma/client": "5"}}',
            "tests/setup.ts": "import { PostgreSqlContainer } from '@testcontainers/postgresql';\n",
        },
    )
    assert run(tmp_path, "db-advisory-pack").result == "fail"


# --- how the rules are declared ------------------------------------------------------------------------------------------


def rules():
    return {c["id"]: c for c in load_checks()["checks"]}


def test_the_db_pack_is_enforced_with_the_same_date_floor_as_the_other_packs():
    r = rules()["db-pack"]
    assert (r["level"], r["label"]) == ("fail", "enforced")
    assert str(r["since"]) == str(rules()["payments-pack"]["since"])


@pytest.mark.parametrize("rule", ["auth-pack", "db-advisory-pack"])
def test_the_auth_and_db_advisory_packs_are_judgment_and_can_only_warn(rule):
    r = rules()[rule]
    assert (r["level"], r["label"], r["evidence"]) == ("warn", "advisory", "judgment")


def test_every_pack_has_a_rule_and_every_pack_rule_has_a_pack():
    declared = {name for name in packs.load_packs()["packs"]}
    wired = {cid[: -len("-pack")] for cid in rules() if cid.endswith("-pack")}
    assert declared == wired


def test_the_packs_file_is_valid_and_the_new_packs_need_the_capability_they_are_named_for():
    data = packs.load_packs()
    assert packs.validate(data) == []
    assert data["packs"]["auth"]["needs"] == "auth"
    assert data["packs"]["db"]["needs"] == "db" and data["packs"]["db-advisory"]["needs"] == "db"


def test_an_old_repo_gets_the_db_pack_as_a_warning_and_a_new_repo_as_a_failure(tmp_path):
    """The since floor applies to the new rule like the other packs: a repo that predates it is warned, a repo born on or after it is failed."""
    tree(tmp_path, {"package.json": '{"dependencies": {"@prisma/client": "5"}}'})
    (old,) = engine.run(engine.Repo(tmp_path, born_on=datetime.date(2025, 1, 1)), only=["db-pack"])
    (new,) = engine.run(engine.Repo(tmp_path, born_on=datetime.date(2026, 11, 10)), only=["db-pack"])
    assert (old.result, old.level) == ("fail", "warn") and any("grandfathered" in f for f in old.findings)
    assert (new.result, new.level) == ("fail", "fail")
