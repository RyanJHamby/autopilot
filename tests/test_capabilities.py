"""Capability detection: what a repo can do, read from its own content, offline.

Every false positive and false negative here was found by surveying the real repos on 2026-11-10, so each test is a case that really
happened or really would: an employer named Stripe in a CSV, a dependency that is only an optional extra, a Gemini call with no SDK."""

import json
import subprocess

import pytest

from autopilot.standard import capabilities as cap


def tree(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return root


def found(root):
    return {name: ev for name, ev in cap.capabilities(root).items()}


def pkg(**sections):
    return json.dumps(sections)


# --- dependencies ------------------------------------------------------------------------------------------------------


def test_a_runtime_dependency_is_a_capability_and_names_where(tmp_path):
    tree(tmp_path, {"package.json": pkg(dependencies={"stripe": "^23.1.0", "openai": "^7.0.0"})})
    got = found(tmp_path)
    assert set(got) == {"payments", "llm"}
    assert any("stripe" in e.detail and "package.json" in e.path for e in got["payments"])


def test_a_dev_dependency_is_not_a_capability(tmp_path):
    tree(tmp_path, {"package.json": pkg(devDependencies={"stripe": "1", "openai": "1"})})
    assert found(tmp_path) == {}


def test_an_optional_python_extra_is_not_a_capability_but_a_real_dependency_is(tmp_path):
    optional = '[project]\nname = "x"\ndependencies = ["pyyaml"]\n[project.optional-dependencies]\nllm = ["anthropic>=0.40"]\n'
    tree(tmp_path / "a", {"pyproject.toml": optional})
    assert found(tmp_path / "a") == {}
    real = '[project]\nname = "x"\ndependencies = ["anthropic>=0.40", "psycopg2-binary==2.9"]\n'
    tree(tmp_path / "b", {"pyproject.toml": real})
    assert set(found(tmp_path / "b")) == {"llm", "db"}


def test_requirements_files_count_but_a_dev_requirements_file_does_not(tmp_path):
    tree(tmp_path, {"requirements.txt": "# deps\nsqlalchemy==2.1.1\n-r other.txt\n", "requirements-dev.txt": "stripe\nopenai\n"})
    assert set(found(tmp_path)) == {"db"}


def test_a_lockfile_alone_is_never_a_capability(tmp_path):
    tree(tmp_path, {"package-lock.json": pkg(packages={"node_modules/stripe": {"version": "1"}}), "uv.lock": 'name = "openai"\n'})
    assert found(tmp_path) == {}


def test_a_scoped_package_and_a_prefix_family_are_recognised(tmp_path):
    tree(tmp_path, {"package.json": pkg(dependencies={"@anthropic-ai/sdk": "1", "@ai-sdk/openai": "1", "@clerk/nextjs": "1"})})
    assert set(found(tmp_path)) == {"llm", "auth"}


def test_a_nested_manifest_in_a_monorepo_counts(tmp_path):
    tree(tmp_path, {"apps/web/package.json": pkg(dependencies={"stripe": "1"})})
    assert set(found(tmp_path)) == {"payments"}


# --- source signals: no SDK needed -------------------------------------------------------------------------------------


def test_gemini_by_raw_fetch_with_no_sdk_is_detected(tmp_path):
    src = 'const URL = "https://generativelanguage.googleapis.com/v1beta/auth_tokens";\nfetch(URL, {headers: {"x-goog-api-key": k}});\n'
    tree(tmp_path, {"src/lib/ai/gemini-voice-session.ts": src})
    assert set(found(tmp_path)) == {"llm"}


def test_stripe_by_raw_fetch_with_no_sdk_is_detected(tmp_path):
    tree(tmp_path, {"src/billing.py": 'import requests\nrequests.post("https://api.stripe.com/v1/checkout/sessions")\n'})
    assert set(found(tmp_path)) == {"payments"}


def test_an_api_key_read_from_the_environment_in_source_is_a_capability(tmp_path):
    tree(tmp_path, {"src/lib/ai/provider.ts": "const k = process.env.OPENAI_API_KEY;\n", "src/pay.py": "k = os.environ.get('STRIPE_SECRET_KEY')\n"})
    assert set(found(tmp_path)) == {"llm", "payments"}


def test_a_lazy_import_inside_try_is_detected(tmp_path):
    tree(tmp_path, {"src/coach.py": "def make():\n    try:\n        import anthropic\n    except ImportError:\n        return None\n"})
    assert set(found(tmp_path)) == {"llm"}


def test_hand_rolled_session_crypto_is_auth_but_a_webhook_hmac_is_not(tmp_path):
    session = 'import { createHmac } from "crypto";\nexport const sign = (s) => createHmac("sha256", k).update(s).digest("hex");\n// session cookie\nconst session = 1;\n'
    tree(tmp_path / "a", {"lib/auth.ts": session})
    assert set(found(tmp_path / "a")) == {"auth"}
    webhook = 'import { createHmac } from "crypto";\nexport const verify = (body, sig) => createHmac("sha256", k).update(body).digest("hex") === sig;\n'
    tree(tmp_path / "b", {"lib/verify.ts": webhook})
    assert found(tmp_path / "b") == {}


# --- file signals ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["vercel.json", "Dockerfile", "fly.toml", "netlify.toml", "render.yaml"])
def test_a_deploy_config_file_is_deploy_even_nested(tmp_path, name):
    tree(tmp_path, {f"apps/control-plane/{name}": "{}\n"})
    assert set(found(tmp_path)) == {"deploy"}


def test_migrations_are_a_database(tmp_path):
    tree(tmp_path, {"supabase/migrations/0001_core.sql": "create table t();\n"})
    assert set(found(tmp_path)) == {"db"}


# --- false positives: things that name a capability but are not one ------------------------------------------------------


def test_an_employer_named_stripe_in_prose_and_data_is_not_payments(tmp_path):
    tree(tmp_path, {"START_HERE.md": "Interview at Stripe next week\n", "docs/inputs/companies.csv": "Stripe,infra\n", "notes/stripe.txt": "stripe\n"})
    assert found(tmp_path) == {}


def test_a_test_fixture_or_scanner_rule_naming_stripe_is_not_payments(tmp_path):
    tree(
        tmp_path,
        {
            "tests/test_secret_scan.py": 'KEY = "sk_live_x"\nrequests.post("https://api.stripe.com/v1/x")\n',
            "src/app.test.ts": 'fetch("https://api.stripe.com/v1/x")\n',
            "src/__golden__/case.ts": 'process.env.OPENAI_API_KEY\n',
            ".autopilot/tier.py": 'RISKY = re.compile("stripe|billing")\n',
        },
    )
    assert found(tmp_path) == {}


def test_env_names_in_docs_templates_and_workflows_are_not_a_capability(tmp_path):
    tree(
        tmp_path,
        {
            "docs/setup.md": "export ANTHROPIC_API_KEY=...\n",
            "src/pawl/data/template/agent-evals.yml": "env:\n  ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}\n",
            "examples/tidewater/app.py": "k = os.environ['OPENAI_API_KEY']\n",
            ".github/workflows/ci.yml": "env: {OPENAI_API_KEY: x}\n",
        },
    )
    assert found(tmp_path) == {}


def test_a_signal_only_in_a_comment_is_not_a_capability(tmp_path):
    tree(
        tmp_path,
        {
            "src/a.ts": "// previously called https://api.openai.com/v1/x with process.env.OPENAI_API_KEY\n/* api.stripe.com */\nconst x = 1;\n",
            "src/b.py": "# import anthropic\nx = 1\n",
        },
    )
    assert found(tmp_path) == {}


def test_a_url_in_a_string_is_not_mistaken_for_a_comment(tmp_path):
    tree(tmp_path, {"src/a.ts": 'const u = "https://api.openai.com/v1/chat";\n'})
    assert set(found(tmp_path)) == {"llm"}


def test_a_bare_hostname_in_a_network_allowlist_is_not_a_call(tmp_path):
    # The real autopilot/fabric/firewall.py: a sandbox allowlist names api.anthropic.com, it does not call it.
    src = 'GITHUB = ("github.com",)\nLANES = {"exec": GITHUB + ("api.anthropic.com",), "x": ("api.stripe.com",)}\n'
    tree(tmp_path, {"src/fabric/firewall.py": src})
    assert found(tmp_path) == {}


def test_a_full_url_with_a_scheme_is_a_call_including_a_websocket(tmp_path):
    tree(tmp_path, {"src/a.ts": 'const ws = new WebSocket("wss://generativelanguage.googleapis.com/ws/x");\n'})
    assert set(found(tmp_path)) == {"llm"}


def test_a_python_docstring_that_names_a_url_or_an_import_is_not_a_capability(tmp_path):
    doc = (
        '"""Calls https://api.openai.com/v1/x and does `import anthropic`.\n\nSet process.env.OPENAI_API_KEY.\n"""\n'
        "def f():\n    \'\'\'also https://api.stripe.com/v1/y\'\'\'\n    return 1\n"
    )
    tree(tmp_path, {"src/mod.py": doc})
    assert found(tmp_path) == {}


def test_vendored_and_build_directories_are_ignored(tmp_path):
    sig = 'fetch("https://api.stripe.com/v1/x");\n'
    tree(tmp_path, {f"{d}/x.js": sig for d in ("node_modules/stripe", ".venv/lib", ".next/server", "dist", "build", ".claude/worktrees/agent-1/src")})
    assert found(tmp_path) == {}


def test_a_file_over_the_size_cap_is_skipped(tmp_path):
    tree(tmp_path, {"src/big.js": 'fetch("https://api.stripe.com/v1/x");\n' + "x" * (600 * 1024)})
    assert found(tmp_path) == {}


# --- git behaviour -----------------------------------------------------------------------------------------------------


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_new_uncommitted_code_counts_because_that_is_when_the_tripwire_must_fire(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    tree(tmp_path, {"src/pay.ts": 'fetch("https://api.stripe.com/v1/x");\n'})
    assert set(found(tmp_path)) == {"payments"}


def test_a_gitignored_directory_is_ignored_even_if_it_contains_a_signal(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    tree(tmp_path, {".gitignore": "vendor_copy/\n", "vendor_copy/x.js": 'fetch("https://api.stripe.com/v1/x");\n', "src/ok.ts": "const a = 1;\n"})
    assert found(tmp_path) == {}


def test_a_directory_inside_another_repo_does_not_scan_the_parent(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    tree(tmp_path, {"src/pay.ts": 'fetch("https://api.stripe.com/v1/x");\n'})
    inner = tmp_path / "inner"
    inner.mkdir()
    (inner / "a.txt").write_text("x\n")
    assert found(inner) == {}


# --- hosted ------------------------------------------------------------------------------------------------------------


def test_hosted_means_deployed_and_has_users_or_payments(tmp_path):
    tree(tmp_path / "a", {"vercel.json": "{}", "package.json": pkg(dependencies={"@supabase/ssr": "1", "openai": "1"})})
    assert cap.hosted(cap.capabilities(tmp_path / "a")) is True
    tree(tmp_path / "b", {"package.json": pkg(dependencies={"openai": "1"})})  # a local tool with its own key
    assert cap.hosted(cap.capabilities(tmp_path / "b")) is False
    tree(tmp_path / "c", {"vercel.json": "{}", "package.json": pkg(dependencies={"openai": "1"})})  # deployed, but nobody to bill or log in
    assert cap.hosted(cap.capabilities(tmp_path / "c")) is False


def test_evidence_is_specific_enough_to_print(tmp_path):
    tree(tmp_path, {"src/lib/ai.ts": '\n\nfetch("https://api.openai.com/v1/x");\n'})
    (e,) = found(tmp_path)["llm"]
    assert e.path == "src/lib/ai.ts" and "line 3" in e.detail
