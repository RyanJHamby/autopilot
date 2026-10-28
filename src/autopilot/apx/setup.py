"""apx setup helper: creates the GitHub App through GitHub's app-manifest flow with ONE click from the owner.

  python -m autopilot.apx.setup

What it does: serves a one-shot page on 127.0.0.1 that posts a least-privilege manifest to GitHub; GitHub asks the owner
to confirm (the click) and redirects back with a code; the code is exchanged for the App's credentials, and the private key
goes straight into a mode-600 file. The key is never printed, logged or held in a variable beyond the write. Then it waits
for the owner to install the App (second click), discovers the installation, writes a settings file containing ONLY paths
and ids, prompts (hidden) for the Claude token, and runs the doctor.

Never touches anything outside the state directory (default ~/.apx). Creating an OS user for isolation is a separate,
admin-password step documented in docs/apx-runbook.md.
"""

from __future__ import annotations

import getpass
import html
import json
import os
import secrets
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .doctor import REQUIRED, kit_automerge
from .planner import ALLOWED_REPOS

APP_NAME = "autopilot-apx"


def build_manifest(redirect_url: str, name: str = APP_NAME) -> dict:
    """Exactly the permissions apx needs (the doctor's REQUIRED set), no webhook, private to the owner."""
    return {
        "name": name,
        "url": "https://github.com/RyanJHamby/autopilot",
        "redirect_url": redirect_url,
        "public": False,
        "hook_attributes": {"url": "https://example.invalid/unused", "active": False},
        "default_permissions": dict(REQUIRED),
        "default_events": [],
    }


def form_page(manifest: dict, state: str) -> str:
    """Auto-submitting form: the manifest is HTML-escaped into a hidden field, posted to GitHub (not to this machine)."""
    m = html.escape(json.dumps(manifest), quote=True)
    return (
        "<!doctype html><meta charset=utf-8><title>apx setup</title>"
        f'<form id=f method=post action="https://github.com/settings/apps/new?state={html.escape(state)}">'
        f'<input type=hidden name=manifest value="{m}"></form>'
        "<p>Sending the apx App manifest to GitHub. Click <b>Create GitHub App</b> on the next page.</p>"
        "<script>document.getElementById('f').submit()</script>"
    )


def write_private(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # created 600: never world-readable, even briefly
    with os.fdopen(fd, "w") as fh:
        fh.write(data)


def exchange_code(code: str, state_dir: Path, *, post=None) -> dict:
    """Trade the one-time code for the App. Only id and slug are returned; the key is written, the rest is discarded."""

    def default_post(url: str) -> dict:
        req = urllib.request.Request(url, data=b"", method="POST", headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    r = (post or default_post)(f"https://api.github.com/app-manifests/{code}/conversions")
    write_private(state_dir / "app.pem", r["pem"])
    # client_secret and webhook_secret are deliberately dropped: apx uses neither
    return {"id": str(r["id"]), "slug": r["slug"]}


class _Handler(BaseHTTPRequestHandler):
    server_version = "apx-setup"

    def log_message(self, *a):  # no request logging: URLs carry a one-time code
        pass

    def _send(self, code: int, body: str):
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        srv = self.server
        if u.path == "/":
            return self._send(200, form_page(srv.manifest, srv.state))  # type: ignore[attr-defined]
        if u.path == "/callback":
            q = parse_qs(u.query)
            if q.get("state", [""])[0] != srv.state or not q.get("code"):  # type: ignore[attr-defined]
                return self._send(400, "bad state")
            try:
                srv.result = exchange_code(q["code"][0], srv.state_dir, post=srv.post)  # type: ignore[attr-defined]
            except Exception as e:  # noqa: BLE001
                srv.error = type(e).__name__  # type: ignore[attr-defined]
                return self._send(500, "exchange failed; see the terminal")
            return self._send(200, "<p>App created. You can close this tab and go back to the terminal.</p>")
        self._send(404, "not found")


def run_manifest_flow(state_dir: Path, *, open_browser=webbrowser.open, post=None, timeout: int = 600) -> dict:
    state = secrets.token_urlsafe(24)
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    srv.manifest = build_manifest(f"http://127.0.0.1:{port}/callback")  # type: ignore[attr-defined]
    srv.state, srv.state_dir, srv.post, srv.result, srv.error = state, state_dir, post, None, None  # type: ignore[attr-defined]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        open_browser(f"http://127.0.0.1:{port}/")
        end = time.time() + timeout
        while time.time() < end and srv.result is None and srv.error is None:  # type: ignore[attr-defined]
            time.sleep(0.2)
    finally:
        srv.shutdown()
        srv.server_close()
    if srv.error:  # type: ignore[attr-defined]
        raise RuntimeError(f"manifest exchange failed ({srv.error})")  # type: ignore[attr-defined]
    if srv.result is None:  # type: ignore[attr-defined]
        raise TimeoutError("no confirmation received; run again and click Create GitHub App")
    return srv.result  # type: ignore[attr-defined]


def discover_installation(api_app, api_for_token, *, sleep=time.sleep, tries: int = 200) -> dict[str, int]:
    """Poll until the owner has installed the App; return {repo: installation_id} limited to the allowed repos.

    api_app: JWT-authenticated callable. api_for_token(installation_id) -> callable authenticated as that installation."""
    for _ in range(tries):
        inst = api_app("GET", "/app/installations")
        if inst:
            out: dict[str, int] = {}
            for i in inst:  # type: ignore[union-attr]
                repos = api_for_token(i["id"])("GET", "/installation/repositories?per_page=100")["repositories"]  # type: ignore[index]
                for r in repos:
                    if r["full_name"] in ALLOWED_REPOS:
                        out[r["full_name"]] = i["id"]
            return out
        sleep(3)
    raise TimeoutError("App not installed yet; install it on autopilot, drillpad-workspace and stencil, then run again")


def render_env(state_dir: Path, app_id: str, installations: dict[str, int], kit_ref: str) -> str:
    """Paths and ids only. Safe to read aloud: it contains no secret."""
    inst = ",".join(f"{r}={i}" for r, i in sorted(installations.items()))
    return (
        f"APX_APP_ID={app_id}\n"
        f"APX_KEY_PATH={state_dir / 'app.pem'}\n"
        f"APX_INSTALLATIONS={inst}\n"
        f"APX_OAUTH_FILE={state_dir / 'claude-oauth'}\n"
        "APX_KIT_REPO=RyanJHamby/autopilot-kit\n"
        f"APX_KIT_REF={kit_ref}\n"
        f"APX_DB={state_dir / 'apx.sqlite'}\n"
        f"APX_WORK={state_dir / 'work'}\n"
    )


def main(argv: list[str] | None = None) -> int:
    from . import app_auth
    from .github import make_api

    state_dir = Path(os.environ.get("APX_STATE", str(Path.home() / ".apx")))
    print(f"State directory: {state_dir} (mode 700). The private key will be written there; it is never printed.")
    if not (state_dir / "app.pem").exists():
        print("Opening your browser. On GitHub, click 'Create GitHub App'.")
        app = run_manifest_flow(state_dir)
        (state_dir / "app.id").write_text(app["id"])
        print(f"App created: {app['slug']} (id {app['id']})")
    else:
        app = {"id": (state_dir / "app.id").read_text().strip(), "slug": APP_NAME}
        print(f"Reusing the existing key in {state_dir}.")
    print(f"Now install it: https://github.com/apps/{app['slug']}/installations/new")
    print("Choose 'Only select repositories' and pick exactly: autopilot, drillpad-workspace, stencil.")
    api_app = make_api(app_auth.make_jwt(app["id"], state_dir / "app.pem"))

    def api_for_token(iid: int):
        tok = api_app("POST", f"/app/installations/{iid}/access_tokens", {})["token"]  # type: ignore[index]
        return make_api(tok)

    installations = discover_installation(api_app, api_for_token)
    approved = kit_automerge.fetch_approved("RyanJHamby/autopilot-kit")
    if not approved:
        print("Could not read the APPROVED kit list; set APX_KIT_REF by hand in the settings file.", file=sys.stderr)
    write_private(state_dir / "apx.env", render_env(state_dir, app["id"], installations, approved[-1] if approved else "0" * 40))
    if not (state_dir / "claude-oauth").exists() and sys.stdin.isatty():
        print("Run `claude setup-token` in another terminal, then paste the token here (hidden):")
        write_private(state_dir / "claude-oauth", getpass.getpass("token: ").strip() + "\n")
    print(f"Settings written to {state_dir / 'apx.env'} (paths and ids only).")
    print(f"Next: set -a; . {state_dir / 'apx.env'}; set +a; python -m autopilot.apx.daemon --doctor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
