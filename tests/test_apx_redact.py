import pytest

from autopilot.apx import app_auth, checks, redact
from autopilot.apx import executor as ex
from autopilot.apx.ledger import Ledger
from autopilot.apx.planner import Action

# every secret-shaped value is assembled at runtime so this file itself holds nothing key-like
PEM = "-----BEGIN " + "RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA" + "x" * 40 + "\n-----END " + "RSA PRIVATE KEY-----"
SHAPES = {
    "claude": "sk-ant-" + "oat01-" + "Ab1_" * 10,
    "ghs": "gh" + "s_" + "A1b2C3d4" * 5,
    "ghp": "gh" + "p_" + "A1b2C3d4" * 5,
    "fine-grained": "github" + "_pat_" + "A1b2_" * 8,
    "aws": "AK" + "IA" + "ABCDEFGHIJKLMNOP",
    "slack": "xo" + "xb-" + "1234567890-abcdefghij",
    "jwt": "ey" + "JhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9" + ".eyJpc3MiOiIx" + "Zz9AbCdEf." + "abcdefghijklmnop",
}


@pytest.fixture(autouse=True)
def clean():
    redact.forget_all()
    yield
    redact.forget_all()


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_known_credential_shapes_are_removed(name):
    out = redact.redact(f"before {SHAPES[name]} after")
    assert SHAPES[name] not in out and redact.MARK in out and out.startswith("before") and out.endswith("after")


def test_private_key_blocks_are_removed_whole():
    out = redact.redact(f"x\n{PEM}\ny")
    assert "MIIEow" not in out and "BEGIN" not in out and out.startswith("x") and out.endswith("y")
    cut = redact.redact("start\n-----BEGIN " + "PRIVATE KEY-----\nabcdef")  # truncated block: still dropped to the end
    assert "abcdef" not in cut


def test_labelled_values_keep_the_label_and_lose_the_value():
    value = "Zq9" * 10
    for line in (f"token={value}", f'API_KEY: "{value}"', f"password = {value}", f"Authorization: Bearer {value}"):
        out = redact.redact(line)
        assert value not in out and redact.MARK in out
    assert redact.redact(f"token={value}").startswith("token=")


def test_registered_exact_values_are_removed_in_any_context_longest_first():
    redact.register("short")  # too short to register: ordinary words must survive
    redact.register("supersecretvalue123")
    redact.register("supersecretvalue123456")
    out = redact.redact("a supersecretvalue123456 b supersecretvalue123 c short")
    assert "supersecret" not in out and "456" not in out and out.endswith("c short")  # no tail left by the shorter prefix
    redact.register(None)
    redact.register("")


def test_ordinary_text_is_untouched_and_redaction_is_idempotent():
    text = "- PASS `uv run pytest -q` (64.9s)\n- FAIL `npm test` (1.2s) - exit 1\ntokenizer=fast"
    assert redact.redact(text) == text
    once = redact.redact(f"k {SHAPES['ghs']}")
    assert redact.redact(once) == once


def test_redaction_failure_withholds_instead_of_leaking(monkeypatch):
    class Boom:
        groups = 0

        def sub(self, *a, **k):
            raise RuntimeError("regex engine")

    monkeypatch.setattr(redact, "_SHAPES", [Boom()])
    out = redact.redact(f"secret {SHAPES['ghs']}")
    assert SHAPES["ghs"] not in out and "withheld" in out


def test_strip_output_blocks_keeps_step_lines_and_drops_raw_output():
    md = "- PASS `a` (1s)\n- FAIL `b` (2s) - exit 1\n\n```\nTraceback: SECRET_IN_OUTPUT\n```"
    out = redact.strip_output_blocks(md)
    assert "SECRET_IN_OUTPUT" not in out and "- FAIL `b` (2s)" in out and "withheld" in out


class Api:
    def __init__(self):
        self.calls = []

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        return {}


def test_every_posted_check_summary_is_redacted_including_registered_values():
    redact.register("registered-secret-value-1")
    a = Api()
    checks.post_check(a, "o/r", "abc", "build", False, f"boom {SHAPES['ghs']} and registered-secret-value-1")
    summary = a.calls[0][2]["output"]["summary"]
    assert SHAPES["ghs"] not in summary and "registered-secret-value-1" not in summary and redact.MARK in summary


def test_minted_installation_tokens_are_registered_automatically(tmp_path):
    token = "plain-opaque-" + "Qw7Zk" * 6  # deliberately matches no credential shape, so only registration can catch it
    assert redact.redact(f"leak {token}") == f"leak {token}"  # control: unregistered, it passes through

    class Factory:
        def __call__(self, t):
            return lambda method, path, body=None: {"token": token, "expires_at": "2099-01-01T00:00:00Z"}

    cache = app_auth.TokenCache("1", tmp_path / "k.pem", {"o/r": 9}, api_factory=Factory())
    monkey_jwt = app_auth.make_jwt
    app_auth.make_jwt = lambda *a, **k: "jwt"
    try:
        assert cache.token_for("o/r") == token
    finally:
        app_auth.make_jwt = monkey_jwt
    assert token not in redact.redact(f"leak {token}")  # minting registered it


def _deps(ci_out):
    d = ex.Deps(lambda r, s: None, lambda co, ref: (True, "clean"), lambda co: (False, ci_out), lambda *a: None)
    return d


def _posted_ci_summary(private_repos):
    api = Api()
    out = "- FAIL `pytest` (1s) - exit 1\n\n```\nRAW_TAIL_OUTPUT\n```"
    ex.execute(
        api,
        Ledger(),
        _deps(out),
        [Action("check-pr", "o/r", "abc1234", "")],
        contexts={"o/r": {"guard": "guard / guard", "ci": "build"}},
        head_refs={("o/r", "abc1234"): "agent/1-1"},
        dry_run=False,
        private_repos=private_repos,
    )
    return next(
        c[2]["output"]["summary"] for c in api.calls if c[2] and c[2].get("name") == "build" and c[2]["status"] == "completed"
    )


def test_public_or_unknown_repos_get_no_raw_output_but_confirmed_private_repos_do():
    assert "RAW_TAIL_OUTPUT" not in _posted_ci_summary(None)  # unknown -> treated as public
    assert "RAW_TAIL_OUTPUT" not in _posted_ci_summary(frozenset({"other/repo"}))
    assert "- FAIL `pytest` (1s)" in _posted_ci_summary(None)  # the step line survives
    assert "RAW_TAIL_OUTPUT" in _posted_ci_summary(frozenset({"o/r"}))


def test_output_containing_its_own_backtick_fences_cannot_leak_past_the_withheld_note():
    # real case: a failing lint run echoed source lines that themselves contain triple backticks
    raw = 'x = re.findall(r"^```mermaid\\n(.*?)^```", TEXT)\nSECRET_TAIL_AFTER_INNER_FENCE'
    md = "- FAIL `ruff` (1s) - exit 1\n\n```\n" + raw + "\n```"
    out = redact.strip_output_blocks(md)
    assert "SECRET_TAIL_AFTER_INNER_FENCE" not in out and "mermaid" not in out and "x = re" not in out
    assert out.startswith("- FAIL `ruff` (1s) - exit 1") and out.endswith(
        redact.WITHHELD
    )  # step line kept, nothing after the note


def test_summaries_without_a_fence_are_untouched():
    plain = "- PASS `uv sync` (1s)\n- PASS `pytest` (2s)"
    assert redact.strip_output_blocks(plain) == plain
    assert redact.strip_output_blocks("autopilot guard: clean") == "autopilot guard: clean"
