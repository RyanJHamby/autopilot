"""deploy-advisory-pack: what a hosted app with real users needs to be run, not just shipped (uptime, logs, retention, cron heartbeats,
environments). Advisory: whether each applies depends on the product, so it can only warn. Each test starts from a complete repo, removes one
item's evidence, and expects exactly that item reported."""

import pytest
from test_pack_rules import named, record, run, tree

from autopilot.standard import capabilities, load_checks, packs

HOSTED = {
    "package.json": '{"dependencies": {"next": "16", "stripe": "23", "pino": "9", "@supabase/ssr": "0.12"}}',
    "vercel.json": '{"framework": "nextjs"}',
    "src/lib/logger.ts": "import pino from 'pino';\nexport const log = pino({ redact: ['req.headers.authorization'] });\n",
    "docs/gates/uptime.md": record("Uptime and certificate monitoring"),
    "docs/runbooks/logging.md": record("Log retention and PII scrubbing", verified=None),
    "docs/runbooks/environments.md": record("Dev and prod are separate", verified=None),
    "docs/runbooks/prod-protection.md": record("Production deploys need approval", verified=None),
}
ITEMS = {
    "uptime-monitor": "docs/gates/uptime.md",
    "structured-logs": "src/lib/logger.ts",
    "log-retention": "docs/runbooks/logging.md",
    "dev-prod-separation": "docs/runbooks/environments.md",
    "protected-prod": "docs/runbooks/prod-protection.md",
}


def hosted(**changes):
    files = dict(HOSTED)
    files.update(changes)
    return {k: v for k, v in files.items() if v is not None}


def test_a_repo_that_is_not_deployed_skips_the_pack(tmp_path):
    tree(tmp_path, {"README.md": "x\n"})
    assert run(tmp_path, "deploy-advisory-pack").result == "skip"


def test_a_complete_hosted_repo_passes(tmp_path):
    tree(tmp_path, hosted())
    r = run(tmp_path, "deploy-advisory-pack")
    assert (r.result, r.findings) == ("pass", []), r.findings


@pytest.mark.parametrize("item", sorted(ITEMS))
def test_removing_one_item_reports_exactly_that_item(tmp_path, item):
    files = hosted()
    if item == "structured-logs":
        files["package.json"] = '{"dependencies": {"next": "16", "stripe": "23", "@supabase/ssr": "0.12"}}'
    del files[ITEMS[item]]
    tree(tmp_path, files)
    r = run(tmp_path, "deploy-advisory-pack")
    assert r.result == "fail" and named(r.findings) == [item], r.findings


def test_a_deployed_static_site_with_no_users_or_payments_is_not_asked_for_hosted_items(tmp_path):
    # deploy alone is not "hosted": nobody logs in and nobody pays, so uptime and retention records are not demanded
    tree(tmp_path, {"vercel.json": "{}", "index.html": "<p>hi</p>\n"})
    r = run(tmp_path, "deploy-advisory-pack")
    assert r.result == "pass", r.findings


def test_a_logging_dependency_or_a_python_logger_satisfies_structured_logs(tmp_path):
    files = hosted(**{"src/lib/logger.ts": None, "package.json": '{"dependencies": {"next": "16", "stripe": "23", "winston": "3", "@supabase/ssr": "1"}}'})
    tree(tmp_path, files)
    assert run(tmp_path, "deploy-advisory-pack").result == "pass"


def test_an_unverified_uptime_record_is_rejected_like_the_other_external_facts(tmp_path):
    tree(tmp_path, hosted(**{"docs/gates/uptime.md": record("Uptime and certificate monitoring", verified=None)}))
    r = run(tmp_path, "deploy-advisory-pack")
    assert r.result == "fail" and named(r.findings) == ["uptime-monitor"] and "Verified" in r.findings[1]


# --- cron heartbeats ----------------------------------------------------------------------------------------------------------

CRON_ROUTE = {"src/app/api/cron/cleanup/route.ts": "export async function GET() { return Response.json({ ok: true }); }\n"}


def test_a_repo_with_no_scheduled_jobs_is_not_asked_for_heartbeats(tmp_path):
    tree(tmp_path, hosted())
    assert "cron-heartbeat" not in " ".join(run(tmp_path, "deploy-advisory-pack").findings)


def test_a_cron_route_without_a_heartbeat_is_reported(tmp_path):
    tree(tmp_path, hosted(**CRON_ROUTE))
    r = run(tmp_path, "deploy-advisory-pack")
    assert r.result == "fail" and named(r.findings) == ["cron-heartbeat"], r.findings


def test_vercel_crons_in_config_also_count_as_scheduled_jobs(tmp_path):
    tree(tmp_path, hosted(**{"vercel.json": '{"crons": [{"path": "/api/x", "schedule": "0 3 * * *"}]}'}))
    r = run(tmp_path, "deploy-advisory-pack")
    assert named(r.findings) == ["cron-heartbeat"], r.findings


@pytest.mark.parametrize(
    "evidence",
    [
        {"src/lib/ping.ts": "await fetch(process.env.HEALTHCHECKS_URL + '/hc-ping');\n"},
        {"src/lib/ping.ts": "import { cronitor } from 'cronitor';\n"},
        {"docs/decisions/0004-cron-heartbeat.md": record("Cron heartbeat", verified=None)},
    ],
)
def test_a_heartbeat_call_or_a_decision_record_satisfies_it(tmp_path, evidence):
    tree(tmp_path, hosted(**CRON_ROUTE, **evidence))
    assert run(tmp_path, "deploy-advisory-pack").result == "pass"


def test_the_word_heartbeat_in_a_comment_does_not_count(tmp_path):
    tree(tmp_path, hosted(**CRON_ROUTE, **{"src/lib/ping.ts": "// TODO add a heartbeat ping here\nexport const x = 1;\n"}))
    assert named(run(tmp_path, "deploy-advisory-pack").findings) == ["cron-heartbeat"]


def test_LIMIT_a_heartbeat_function_that_is_never_called_still_passes(tmp_path):
    # Pattern over code: a file that mentions hc-ping satisfies it whether or not any cron route calls it. Recorded, not caught.
    tree(tmp_path, hosted(**CRON_ROUTE, **{"src/lib/unused.ts": "export const url = 'https://hc-ping.com/abc';\n"}))
    assert run(tmp_path, "deploy-advisory-pack").result == "pass"


def test_an_error_tracker_alone_is_not_a_heartbeat(tmp_path):
    tree(tmp_path, hosted(**CRON_ROUTE, **{"package.json": '{"dependencies": {"next": "16", "stripe": "23", "pino": "9", "@sentry/nextjs": "9", "@supabase/ssr": "1"}}'}))
    assert named(run(tmp_path, "deploy-advisory-pack").findings) == ["cron-heartbeat"]


def test_LIMIT_the_word_heartbeat_for_something_else_satisfies_it(tmp_path):
    # A websocket keep-alive called "heartbeat" passes. The check is a word match, not an understanding of what the ping is for.
    tree(tmp_path, hosted(**CRON_ROUTE, **{"src/lib/socket.ts": "export function startHeartbeat(ws: WebSocket) { setInterval(() => ws.send('ping'), 3e4); }\n"}))
    assert run(tmp_path, "deploy-advisory-pack").result == "pass"


def test_has_cron_ignores_tests_and_docs(tmp_path):
    tree(tmp_path, {"tests/cron/test_x.py": "x = 1\n", "docs/cron/notes.md": "x\n"})
    assert capabilities.has_cron(capabilities.Scan(tmp_path)) is False


# --- how it is declared -------------------------------------------------------------------------------------------------------


def test_the_rule_is_judgment_and_can_only_warn():
    r = {c["id"]: c for c in load_checks()["checks"]}["deploy-advisory-pack"]
    assert (r["level"], r["label"], r["evidence"]) == ("warn", "advisory", "judgment")


def test_the_pack_is_valid_and_needs_the_deploy_capability():
    data = packs.load_packs()
    assert packs.validate(data) == []
    assert data["packs"]["deploy-advisory"]["needs"] == "deploy"


def test_cron_is_an_allowed_condition_and_an_unknown_one_is_rejected():
    assert "cron" in packs.WHEN
    bad = {"packs": {"x": {"needs": "deploy", "items": [{"id": "a", "kind": "record", "title": "t", "fix": "f", "path": ["p"], "when": "weekly"}]}}}
    assert any("when must be one of" in p for p in packs.validate(bad))
