"""payments-pack, llm-pack and deploy-pack: each starts from a complete repo, removes one item's files, and expects exactly that item reported.

The fixtures mirror the live stencil checkout, the only repo that has all of these capabilities today (surveyed 2026-11-10)."""

import datetime
import os
import subprocess

import pytest

from autopilot.standard import engine

FRESH = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()
STALE = (datetime.date.today() - datetime.timedelta(days=400)).isoformat()


def record(title, verified=FRESH):
    body = "\n".join(f"Line {i} of real content about {title.lower()}." for i in range(8))
    return f"# {title}\n\n{body}\n" + (f"\nVerified: {verified}\n" if verified else "")


def tree(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return root


def run(root, rule):
    (r,) = engine.run(engine.Repo(root), only=[rule])
    return r


def named(findings):
    """The item ids a rule reported as missing (each finding line after the first is `item-id: ...`)."""
    return sorted(f.split(":")[0] for f in findings[1:])


# --- payments ----------------------------------------------------------------------------------------------------------

PAYMENTS = {
    "package.json": '{"dependencies": {"stripe": "^23"}}',
    "src/app/api/stripe/webhook/route.ts": "const event = stripe.webhooks.constructEvent(raw, sig, secret);\n",
    "supabase/migrations/0005_events.sql": "create table processed_stripe_events (event_id text primary key);\n",
    "docs/threat-model.md": record("Threat model"),
    "public/terms.html": "<h1>Terms and refund policy</h1>\n",
    ".github/CODEOWNERS": "/src/app/api/stripe/ @me\n/src/lib/stripe.ts @me\n",
}
PAYMENT_ITEMS = {
    "webhook-signature": "src/app/api/stripe/webhook/route.ts",
    "event-dedupe": "supabase/migrations/0005_events.sql",
    "threat-model": "docs/threat-model.md",
    "terms-and-refunds": "public/terms.html",
    "billing-owned": ".github/CODEOWNERS",
}


def test_a_repo_with_no_payment_capability_skips_the_payments_pack(tmp_path):
    tree(tmp_path, {"README.md": "x\n"})
    assert run(tmp_path, "payments-pack").result == "skip"


def test_a_complete_payments_repo_passes(tmp_path):
    tree(tmp_path, PAYMENTS)
    r = run(tmp_path, "payments-pack")
    assert (r.result, r.findings) == ("pass", [])


@pytest.mark.parametrize("item", sorted(PAYMENT_ITEMS))
def test_removing_one_payments_item_reports_exactly_that_item(tmp_path, item):
    files = {k: v for k, v in PAYMENTS.items() if k != PAYMENT_ITEMS[item]}
    if item == "webhook-signature":  # the route file is also where the capability shows; keep the dependency, drop the check
        files["src/app/api/stripe/webhook/route.ts"] = "export const POST = () => new Response('ok');\n"
    tree(tmp_path, files)
    r = run(tmp_path, "payments-pack")
    assert r.result == "fail" and named(r.findings) == [item], r.findings
    assert "payments detected" in r.findings[0]


def test_a_decision_record_about_idempotency_satisfies_event_dedupe_when_there_is_no_table(tmp_path):
    files = {k: v for k, v in PAYMENTS.items() if k != PAYMENT_ITEMS["event-dedupe"]}
    files["docs/decisions/0002-webhook-idempotency.md"] = record("Webhook idempotency", verified=None)
    tree(tmp_path, files)
    assert run(tmp_path, "payments-pack").result == "pass"


def test_a_raw_fetch_to_stripe_with_no_sdk_still_needs_the_pack(tmp_path):
    tree(tmp_path, {"src/pay.ts": 'await fetch("https://api.stripe.com/v1/checkout/sessions", {method: "POST"});\n'})
    r = run(tmp_path, "payments-pack")
    assert r.result == "fail" and "api.stripe.com" in r.findings[0]


def test_LIMIT_a_signature_function_that_is_named_but_never_called_passes(tmp_path):
    # The check is a pattern over code, so `constructEvent` appearing anywhere satisfies it. Recorded, not caught.
    files = dict(PAYMENTS)
    files["src/app/api/stripe/webhook/route.ts"] = "function constructEvent() {}\nexport const POST = () => new Response('ok');\n"
    tree(tmp_path, files)
    assert run(tmp_path, "payments-pack").result == "pass"


# --- llm ---------------------------------------------------------------------------------------------------------------

LLM_HOSTED = {
    "package.json": '{"dependencies": {"openai": "^7", "@supabase/ssr": "1"}}',
    "vercel.json": "{}",
    "src/lib/rate-limit.ts": "export async function checkRateLimit(user: string) { return true; }\n",
    "src/lib/eval/judge.ts": "export const judge = 1;\n",
    "docs/gates/llm-spend.md": record("LLM spend caps"),
    "docs/runbooks/llm-kill-switch.md": record("LLM kill switch", verified=None),
}
LLM_ITEMS = {
    "spend-cap": "docs/gates/llm-spend.md",
    "kill-switch": "docs/runbooks/llm-kill-switch.md",
    "per-user-limit": "src/lib/rate-limit.ts",
    "evals": "src/lib/eval/judge.ts",
}


def test_a_complete_hosted_llm_repo_passes(tmp_path):
    tree(tmp_path, LLM_HOSTED)
    r = run(tmp_path, "llm-pack")
    assert (r.result, r.findings) == ("pass", [])


@pytest.mark.parametrize("item", sorted(LLM_ITEMS))
def test_removing_one_llm_item_reports_exactly_that_item(tmp_path, item):
    tree(tmp_path, {k: v for k, v in LLM_HOSTED.items() if k != LLM_ITEMS[item]})
    r = run(tmp_path, "llm-pack")
    assert r.result == "fail" and named(r.findings) == [item], r.findings


def test_a_local_tool_with_its_own_key_owes_nothing(tmp_path):
    # drillpad's shape: an LLM user, not deployed, nobody to bill or log in.
    tree(tmp_path, {"src/coach.py": "import anthropic\nkey = os.environ.get('ANTHROPIC_API_KEY')\n"})
    assert run(tmp_path, "llm-pack").result == "pass"


def test_a_deployed_llm_app_with_no_users_or_payments_is_not_hosted(tmp_path):
    tree(tmp_path, {"package.json": '{"dependencies": {"openai": "1"}}', "vercel.json": "{}"})
    assert run(tmp_path, "llm-pack").result == "pass"


def test_the_per_user_limit_is_only_required_when_there_are_users(tmp_path):
    files = {k: v for k, v in LLM_HOSTED.items() if k != "src/lib/rate-limit.ts"}
    files["package.json"] = '{"dependencies": {"openai": "1", "stripe": "1"}}'  # hosted by payments, but no auth capability
    tree(tmp_path, files)
    assert "per-user-limit" not in named(run(tmp_path, "llm-pack").findings)


def test_a_stale_spend_cap_record_is_reported(tmp_path):
    files = dict(LLM_HOSTED)
    files["docs/gates/llm-spend.md"] = record("LLM spend caps", verified=STALE)
    tree(tmp_path, files)
    r = run(tmp_path, "llm-pack")
    assert named(r.findings) == ["spend-cap"] and "stale" in "\n".join(r.findings)


def test_a_spend_cap_record_with_no_verified_date_is_reported(tmp_path):
    files = dict(LLM_HOSTED)
    files["docs/gates/llm-spend.md"] = record("LLM spend caps", verified=None)
    tree(tmp_path, files)
    assert named(run(tmp_path, "llm-pack").findings) == ["spend-cap"]


def test_gemini_with_no_sdk_makes_a_repo_an_llm_repo(tmp_path):
    tree(tmp_path, {"vercel.json": "{}", "package.json": '{"dependencies": {"@supabase/ssr": "1"}}',
                    "src/lib/gemini.ts": 'const URL = "https://generativelanguage.googleapis.com/v1beta/auth_tokens";\n'})
    r = run(tmp_path, "llm-pack")
    assert r.result == "fail" and "generativelanguage" in r.findings[0]


def test_LIMIT_a_filler_record_with_a_fresh_date_passes(tmp_path):
    # A record is self-attested: nothing can tell a real spend cap from eight plausible sentences. Recorded, not caught.
    files = dict(LLM_HOSTED)
    files["docs/gates/llm-spend.md"] = "# Caps\n\n" + "\n".join(["We have a cap on every provider account."] * 8) + f"\nVerified: {FRESH}\n"
    tree(tmp_path, files)
    assert run(tmp_path, "llm-pack").result == "pass"


# --- deploy ------------------------------------------------------------------------------------------------------------

DEPLOY = {
    "vercel.json": "{}",
    "package.json": '{"dependencies": {"@sentry/nextjs": "9"}}',
    "src/app/api/health/route.ts": "export const GET = () => Response.json({ ok: true });\n",
    "docs/runbooks/rollback.md": record("Rollback", verified=None),
}
DEPLOY_ITEMS = {"health-endpoint": "src/app/api/health/route.ts", "rollback-runbook": "docs/runbooks/rollback.md"}


def test_a_repo_with_no_deploy_config_skips_the_deploy_pack(tmp_path):
    tree(tmp_path, {"README.md": "x\n"})
    assert run(tmp_path, "deploy-pack").result == "skip"


def test_a_complete_deployed_repo_passes(tmp_path):
    tree(tmp_path, DEPLOY)
    r = run(tmp_path, "deploy-pack")
    assert (r.result, r.findings) == ("pass", [])


@pytest.mark.parametrize("item", ["health-endpoint", "rollback-runbook", "error-tracking"])
def test_removing_one_deploy_item_reports_exactly_that_item(tmp_path, item):
    files = dict(DEPLOY)
    if item == "error-tracking":
        files["package.json"] = '{"dependencies": {"next": "16"}}'
    else:
        files.pop(DEPLOY_ITEMS[item])
    tree(tmp_path, files)
    r = run(tmp_path, "deploy-pack")
    assert r.result == "fail" and named(r.findings) == [item], r.findings


def test_a_health_route_is_found_as_a_directory_or_a_file(tmp_path):
    files = {k: v for k, v in DEPLOY.items() if k != DEPLOY_ITEMS["health-endpoint"]}
    files["app/healthz.py"] = "def healthz():\n    return 'ok'\n"
    tree(tmp_path, files)
    assert run(tmp_path, "deploy-pack").result == "pass"


def test_a_nested_deploy_config_in_a_monorepo_counts(tmp_path):
    tree(tmp_path, {"apps/web/vercel.json": "{}"})
    r = run(tmp_path, "deploy-pack")
    assert r.result == "fail" and "vercel.json" in r.findings[0]


# --- the date floor ----------------------------------------------------------------------------------------------------


def git_born(root, date):
    env = {**os.environ, "GIT_AUTHOR_DATE": f"{date}T12:00:00+00:00", "GIT_COMMITTER_DATE": f"{date}T12:00:00+00:00"}
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(var, None)
    for args in (["init", "-q", "-b", "main"], ["add", "."], ["commit", "-qm", "first"]):
        subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "user.email=t@t", "-c", "user.name=t", *args],
                       cwd=root, check=True, capture_output=True, env=env)


@pytest.mark.parametrize("rule", ["payments-pack", "llm-pack", "deploy-pack"])
def test_the_pack_rules_are_dated_fail_level_enforced_rules(rule):
    from autopilot.standard import load_checks

    (c,) = [c for c in load_checks()["checks"] if c["id"] == rule]
    assert str(c["since"]) == "2026-11-10" and c["level"] == "fail" and c["label"] == "enforced"


def test_an_old_repo_reports_the_same_gaps_at_warn_and_a_new_repo_at_fail(tmp_path):
    for name, born in (("old", "2026-10-01"), ("new", "2026-11-11")):
        root = tree(tmp_path / name, {"package.json": '{"dependencies": {"stripe": "1"}}'})
        git_born(root, born)
    old, new = run(tmp_path / "old", "payments-pack"), run(tmp_path / "new", "payments-pack")
    assert (old.level, old.result) == ("warn", "fail") and (new.level, new.result) == ("fail", "fail")
    assert engine.exit_code([old]) == 0 and engine.exit_code([new]) == 1
    assert "grandfathered" in old.findings[0] and old.findings[1:] == new.findings  # same gaps; the old repo just says why it is only a warning
