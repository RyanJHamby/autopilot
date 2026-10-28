import http.client
import os
import stat
import threading

import pytest

from autopilot.apx import doctor, setup


def mode(p):
    return stat.S_IMODE(os.stat(p).st_mode)


def test_manifest_asks_for_exactly_the_doctors_permissions_and_nothing_else():
    m = setup.build_manifest("http://127.0.0.1:1/callback")
    assert m["default_permissions"] == doctor.REQUIRED
    assert m["default_events"] == [] and m["public"] is False and m["hook_attributes"]["active"] is False
    for banned in ("administration", "workflows", "secrets", "environments", "actions", "members"):
        assert banned not in m["default_permissions"]


def test_form_page_escapes_the_manifest_and_posts_only_to_github():
    page = setup.form_page({"name": 'x"><script>alert(1)</script>'}, "st&te")
    assert 'action="https://github.com/settings/apps/new?state=st&amp;te"' in page
    assert "<script>alert(1)</script>" not in page.split("<script>document")[0]  # the injected markup is escaped
    assert page.count("action=") == 1


def test_private_files_are_created_600_in_a_700_directory(tmp_path):
    p = tmp_path / "state" / "app.pem"
    setup.write_private(p, "secret")
    assert mode(p) == 0o600 and mode(p.parent) == 0o700 and p.read_text() == "secret"


def test_exchange_writes_key_privately_and_returns_only_id_and_slug(tmp_path):
    out = setup.exchange_code(
        "code123",
        tmp_path,
        post=lambda url: {"id": 42, "slug": "autopilot-apx", "pem": "PEMDATA", "client_secret": "cs", "webhook_secret": "ws"},
    )
    assert out == {"id": "42", "slug": "autopilot-apx"}
    assert (tmp_path / "app.pem").read_text() == "PEMDATA" and mode(tmp_path / "app.pem") == 0o600
    assert not any(
        "cs" == f.read_text() or "ws" == f.read_text() for f in tmp_path.iterdir() if f.is_file()
    )  # other secrets dropped


def test_callback_rejects_a_wrong_state_without_exchanging(tmp_path):
    calls = []
    opened = []

    def open_browser(url):
        opened.append(url)
        port = int(url.rsplit(":", 1)[1].split("/")[0])
        # a forged callback first (must be refused), then the genuine one
        c = http.client.HTTPConnection("127.0.0.1", port)
        c.request("GET", "/callback?code=evil&state=wrong")
        assert c.getresponse().status == 400
        page = http.client.HTTPConnection("127.0.0.1", port)
        page.request("GET", "/")
        body = page.getresponse().read().decode()
        state = body.split("state=")[1].split('"')[0]
        g = http.client.HTTPConnection("127.0.0.1", port)
        g.request("GET", f"/callback?code=good&state={state}")
        assert g.getresponse().status == 200

    def post(url):
        calls.append(url)
        return {"id": 7, "slug": "autopilot-apx", "pem": "P"}

    t = threading.Thread(target=lambda: None)
    t.start()
    res = setup.run_manifest_flow(
        tmp_path, open_browser=lambda u: threading.Thread(target=open_browser, args=(u,)).start(), post=post, timeout=10
    )
    t.join()
    assert res == {"id": "7", "slug": "autopilot-apx"} and calls == ["https://api.github.com/app-manifests/good/conversions"]


def test_install_discovery_keeps_only_allowed_repos_and_waits_until_installed():
    seen = {"n": 0}

    def api_app(method, path, body=None):
        seen["n"] += 1
        return [] if seen["n"] < 3 else [{"id": 99}]

    def api_for_token(iid):
        return lambda m, p, b=None: {"repositories": [{"full_name": "RyanJHamby/stencil"}, {"full_name": "RyanJHamby/resume"}]}

    out = setup.discover_installation(api_app, api_for_token, sleep=lambda s: None)
    assert out == {"RyanJHamby/stencil": 99} and seen["n"] == 3  # waited, and the out-of-scope repo is never recorded
    with pytest.raises(TimeoutError):
        setup.discover_installation(lambda *a, **k: [], api_for_token, sleep=lambda s: None, tries=2)


def test_rendered_env_contains_paths_and_ids_but_no_secret(tmp_path):
    env = setup.render_env(tmp_path, "42", {"RyanJHamby/stencil": 9, "RyanJHamby/autopilot": 9}, "a" * 40)
    assert "APX_INSTALLATIONS=RyanJHamby/autopilot=9,RyanJHamby/stencil=9" in env
    assert f"APX_KEY_PATH={tmp_path / 'app.pem'}" in env
    for bad in ("BEGIN", "PRIVATE", "ghs_", "sk-ant"):
        assert bad not in env
    # the daemon accepts what setup writes
    from autopilot.apx import daemon as dm

    (tmp_path / "app.pem").write_text("x")
    (tmp_path / "claude-oauth").write_text("x")
    vals = dict(line.split("=", 1) for line in env.strip().splitlines())
    assert dm.Settings.from_env(vals).app_id == "42"
