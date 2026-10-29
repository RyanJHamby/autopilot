import base64
import json
import subprocess

import pytest

from autopilot.apx import app_auth, gitops


def openssl(*a, input=None):
    return subprocess.run(["openssl", *a], input=input, capture_output=True, check=True)


@pytest.fixture()
def keys(tmp_path):
    key = tmp_path / "app.pem"
    pub = tmp_path / "app.pub"
    openssl("genrsa", "-out", str(key), "2048")
    key.chmod(0o600)
    openssl("rsa", "-in", str(key), "-pubout", "-out", str(pub))
    return key, pub


def b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def test_jwt_claims_and_signature_verify(keys, tmp_path):
    key, pub = keys
    jwt = app_auth.make_jwt("123", key, now=1_000_000)
    h, b, s = jwt.split(".")
    claims = json.loads(b64d(b))
    assert json.loads(b64d(h)) == {"alg": "RS256", "typ": "JWT"}
    assert claims == {"iat": 1_000_000 - 60, "exp": 1_000_000 + 540, "iss": "123"}
    sig = tmp_path / "sig"
    sig.write_bytes(b64d(s))
    r = subprocess.run(
        ["openssl", "dgst", "-sha256", "-verify", str(pub), "-signature", str(sig)],
        input=f"{h}.{b}".encode(),
        capture_output=True,
    )
    assert r.returncode == 0, r.stderr


def test_bad_key_path_raises_without_echoing_it(tmp_path):
    with pytest.raises(RuntimeError) as e:
        app_auth.make_jwt("1", tmp_path / "missing.pem")
    assert "missing.pem" not in str(e.value)


class FakeFactory:
    def __init__(self):
        self.calls = []
        self.n = 0

    def __call__(self, token):
        def api(method, path, body=None):
            self.calls.append((token, method, path))
            self.n += 1
            return {"token": f"ghs_{self.n}", "expires_at": "2026-10-28T14:00:00Z"}

        return api


def test_token_cache_reuses_until_margin_then_refreshes(keys):
    key, _ = keys
    f = FakeFactory()
    import datetime as dt

    base = dt.datetime(2026, 10, 28, 13, 0, tzinfo=dt.timezone.utc).timestamp()
    c = app_auth.TokenCache("1", key, {"o/r": 9}, clock=lambda: base, api_factory=f)
    t1 = c.token_for("o/r")
    assert t1 == "ghs_1" and c.token_for("o/r") == "ghs_1"
    assert len(f.calls) == 1 and f.calls[0][1:] == ("POST", "/app/installations/9/access_tokens")
    c.clock = lambda: base + 3600 - 100  # inside the refresh margin
    assert c.token_for("o/r") == "ghs_2"


def test_unconfigured_repo_is_refused(keys):
    key, _ = keys
    with pytest.raises(KeyError):
        app_auth.TokenCache("1", key, {"o/r": 9}, api_factory=FakeFactory()).token_for("o/other")


def plumbing(d, *a):
    return subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True, text=True).stdout.strip()


def make_remote(tmp_path):
    w = tmp_path / "w"
    w.mkdir()
    plumbing(w, "init", "-q")
    plumbing(w, "config", "user.email", "t@example.com")
    plumbing(w, "config", "user.name", "t")

    def commit(files, parent, ref):
        for n, t in files.items():
            (w / n).write_text(t)
        plumbing(w, "add", "-A")
        args = ["commit-tree", plumbing(w, "write-tree"), "-m", "c"] + (["-p", parent] if parent else [])
        sha = plumbing(w, *args)
        plumbing(w, "update-ref", ref, sha)
        return sha

    base = commit({"a.txt": "1\n"}, None, "refs/heads/main")
    head = commit({"b.txt": "2\n"}, base, "refs/heads/pr")
    return w, base, head


def test_checkout_pr_has_base_ref_and_detached_head(tmp_path):
    remote, base, head = make_remote(tmp_path)
    dest = tmp_path / "co"
    gitops.checkout_pr("o/r", head, "main", dest, None, url=str(remote))
    assert plumbing(dest, "rev-parse", "HEAD") == head
    assert gitops.base_sha(dest, "main") == base
    assert (dest / "b.txt").exists()


def test_token_travels_in_env_not_argv_or_config(tmp_path, monkeypatch):
    remote, base, head = make_remote(tmp_path)
    seen = []
    real = subprocess.run

    def spy(argv, **kw):
        seen.append((argv, kw.get("env") or {}))
        return real(argv, **kw)

    monkeypatch.setattr(gitops.subprocess, "run", spy)
    dest = tmp_path / "co"
    gitops.checkout_pr("o/r", head, "main", dest, "ghs_SECRET", url=str(remote))
    assert not any("ghs_SECRET" in " ".join(a) for a, _ in seen)
    assert any("GIT_CONFIG_VALUE_0" in e for _, e in seen)
    assert "ghs_SECRET" not in (dest / ".git" / "config").read_text()


@pytest.mark.parametrize(
    "repo,sha,branch",
    [("o/r", "abc", "main"), ("o", "a" * 40, "main"), ("o/r", "a" * 40, "main; rm -rf"), ("o/r", "A" * 40, "main")],
)
def test_checkout_rejects_bad_inputs(tmp_path, repo, sha, branch):
    with pytest.raises(ValueError):
        gitops.checkout_pr(repo, sha, branch, tmp_path / "x", None)


def test_checkout_is_repeatable_into_the_same_directory(tmp_path):
    remote, base, head = make_remote(tmp_path)
    root = tmp_path / "work"
    dest = root / "pr-x"
    gitops.checkout_pr("o/r", head, "main", dest, None, url=str(remote), root=root)
    (dest / "leftover.txt").write_text("from the previous pass")
    gitops.checkout_pr("o/r", head, "main", dest, None, url=str(remote), root=root)  # used to fail: remote origin already exists
    assert not (dest / "leftover.txt").exists() and plumbing(dest, "rev-parse", "HEAD") == head


def test_checkout_refuses_to_clear_outside_root_or_non_checkouts(tmp_path):
    remote, base, head = make_remote(tmp_path)
    root = tmp_path / "work"
    root.mkdir()
    outside = tmp_path / "elsewhere"
    (outside / ".git").mkdir(parents=True)
    with pytest.raises(ValueError):
        gitops.checkout_pr("o/r", head, "main", outside, None, url=str(remote), root=root)
    plain = root / "not-a-checkout"
    plain.mkdir()
    (plain / "precious.txt").write_text("keep")
    with pytest.raises(ValueError):
        gitops.checkout_pr("o/r", head, "main", plain, None, url=str(remote), root=root)
    assert (plain / "precious.txt").exists() and (outside / ".git").exists()
    with pytest.raises(ValueError):
        gitops.checkout_pr("o/r", head, "main", root, None, url=str(remote), root=root)  # never the root itself
    with pytest.raises(ValueError):
        gitops.checkout_pr("o/r", head, "main", outside, None, url=str(remote))  # existing dir, no root given


def test_prune_removes_only_old_scratch_and_keeps_kit_and_lock(tmp_path):
    import os
    import time

    for name in ["pr-a", "main-b", "home-1", "tmpabc", "kit", "other"]:
        (tmp_path / name).mkdir()
    (tmp_path / "apx.lock").write_text("")
    old = time.time() - 3 * 24 * 3600
    for name in ["pr-a", "tmpabc", "kit", "other"]:
        os.utime(tmp_path / name, (old, old))
    removed = gitops.prune_work(tmp_path, max_age_seconds=24 * 3600)
    assert sorted(removed) == ["pr-a", "tmpabc"]  # old scratch only
    assert (tmp_path / "kit").exists() and (tmp_path / "other").exists() and (tmp_path / "apx.lock").exists()
    assert (tmp_path / "main-b").exists() and (tmp_path / "home-1").exists()  # fresh scratch stays


def test_a_hung_git_command_times_out_instead_of_holding_the_lock_forever(tmp_path, monkeypatch):
    def hang(argv, **kw):
        assert kw.get("timeout") == gitops.GIT_TIMEOUT  # every git call is bounded
        raise subprocess.TimeoutExpired(argv, kw["timeout"])

    monkeypatch.setattr(gitops.subprocess, "run", hang)
    with pytest.raises(RuntimeError, match="timed out"):
        gitops._git(tmp_path, None, "fetch")


def test_the_agent_token_is_read_only_single_repo_and_cached_separately(keys):
    key, _ = keys
    calls = []

    def factory(token):
        def api(method, path, body=None):
            calls.append((path, body))
            n = len(calls)
            return {"token": f"tok{n}-" + "x" * 12, "expires_at": "2099-01-01T00:00:00Z"}

        return api

    c = app_auth.TokenCache("1", key, {"o/stencil": 9}, api_factory=factory)
    ro = c.read_token_for("o/stencil")
    assert calls[0] == (
        "/app/installations/9/access_tokens",
        {"repositories": ["stencil"], "permissions": {"contents": "read", "metadata": "read"}},
    )
    assert c.read_token_for("o/stencil") == ro and len(calls) == 1  # cached
    full = c.token_for("o/stencil")
    assert full != ro and calls[1][1] == {}  # the full-permission token is a separate request with no restriction
    with pytest.raises(KeyError):
        c.read_token_for("o/other")
    from autopilot.apx import redact

    assert ro not in redact.redact(f"leak {ro}")  # registered for redaction like every token we mint


def test_prune_also_clears_old_agent_checkouts(tmp_path):
    import os
    import time

    (tmp_path / "agent-o_r-abc").mkdir()
    (tmp_path / "keepme").mkdir()
    t = time.time() - 3 * 24 * 3600
    for n in ("agent-o_r-abc", "keepme"):
        os.utime(tmp_path / n, (t, t))
    assert gitops.prune_work(tmp_path, max_age_seconds=24 * 3600) == ["agent-o_r-abc"]
    assert (tmp_path / "keepme").exists()
