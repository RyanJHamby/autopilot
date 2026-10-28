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
