"""deploy/linux/beat.sh, the apx dead-man heartbeat, run for real against a local HTTP server with a stub systemctl and a curl shim.
No network, no systemd, no Worker: the Worker side is tested in agent-kit (watcher/test)."""

import configparser
import http.server
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BEAT = ROOT / "deploy" / "linux" / "beat.sh"
UNIT = ROOT / "deploy" / "linux" / "systemd" / "apx-beat.service"
TIMER = ROOT / "deploy" / "linux" / "systemd" / "apx-beat.timer"
SECRET = "beatSECRETbbbb1234"

pytestmark = pytest.mark.skipif(shutil.which("curl") is None or shutil.which("stat") is None, reason="needs curl and GNU stat")


@pytest.fixture
def server():
    hits: list[tuple[str, str]] = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            hits.append(("POST", self.path))
            self.send_response(200 if self.path == f"/beat/{SECRET}" else 404)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", hits
    srv.shutdown()


def run(tmp: Path, url: str, *, status_age_min: float | None = 1, active: str = "inactive", cred: str | None = None, env=None):
    bindir = tmp / "bin"
    bindir.mkdir(exist_ok=True)
    (bindir / "systemctl").write_text(f"#!/bin/sh\necho {active}\n")
    real_curl = shutil.which("curl")
    (bindir / "curl").write_text(f'#!/bin/sh\necho "$*" >> "{tmp}/curl-args"\nexec "{real_curl}" "$@"\n')
    for f in bindir.iterdir():
        f.chmod(0o755)
    creds = tmp / "creds"
    creds.mkdir(exist_ok=True)
    (creds / "watcher").write_text(cred if cred is not None else f"WATCHER_URL={url}\nWATCHER_BEAT_SECRET={SECRET}\n")
    status = tmp / "status.json"
    if status_age_min is None:
        status.unlink(missing_ok=True)
    else:
        status.write_text("{}")
        t = time.time() - status_age_min * 60
        os.utime(status, (t, t))
    e = {
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "CREDENTIALS_DIRECTORY": str(creds),
        "APX_STATUS": str(status),
        "APX_BEAT_ALLOW_HTTP": "1",
    }
    e.update(env or {})
    return subprocess.run(["sh", str(BEAT)], capture_output=True, text=True, env=e, timeout=30)


def test_fresh_status_sends_one_heartbeat_with_the_secret_off_the_command_line(tmp_path, server):
    url, hits = server
    r = run(tmp_path, url, status_age_min=3)
    assert r.returncode == 0 and "heartbeat sent" in r.stdout
    assert hits == [("POST", f"/beat/{SECRET}")]
    assert SECRET not in (tmp_path / "curl-args").read_text(), "the secret must not reach curl's argv (ps)"
    assert "--config -" in (tmp_path / "curl-args").read_text()
    assert SECRET not in r.stdout + r.stderr


def test_stale_status_sends_nothing_so_the_worker_alerts(tmp_path, server):
    url, hits = server
    r = run(tmp_path, url, status_age_min=40)
    assert r.returncode == 0 and "no heartbeat sent" in r.stdout and "40 min ago" in r.stdout
    assert hits == []


def test_a_running_pass_counts_as_alive_even_with_an_old_status(tmp_path, server):
    url, hits = server
    r = run(tmp_path, url, status_age_min=90, active="activating")
    assert r.returncode == 0 and "a pass is running" in r.stdout
    assert len(hits) == 1


def test_no_status_file_sends_nothing(tmp_path, server):
    url, hits = server
    r = run(tmp_path, url, status_age_min=None)
    assert r.returncode == 0 and "no status file" in r.stdout and hits == []


def test_the_age_limit_is_configurable(tmp_path, server):
    url, hits = server
    assert "heartbeat sent" in run(tmp_path, url, status_age_min=40, env={"APX_BEAT_MAX_AGE_MIN": "60"}).stdout
    assert "no heartbeat sent" in run(tmp_path, url, status_age_min=40, env={"APX_BEAT_MAX_AGE_MIN": "30"}).stdout
    assert run(tmp_path, url, env={"APX_BEAT_MAX_AGE_MIN": "15m"}).returncode == 1


@pytest.mark.parametrize(
    "cred",
    [
        "",
        "WATCHER_URL=https://w.example\n",
        f"WATCHER_URL=https://w.example/path\nWATCHER_BEAT_SECRET={SECRET}\n",
        f"WATCHER_URL=ftp://w.example\nWATCHER_BEAT_SECRET={SECRET}\n",
        'WATCHER_URL=https://w.example\nWATCHER_BEAT_SECRET=bad"secret\n',
    ],
    ids=["empty", "no-secret", "path", "scheme", "quote"],
)
def test_a_bad_credential_is_refused_with_exit_1_and_no_request(tmp_path, server, cred):
    url, hits = server
    r = run(tmp_path, url, cred=cred)
    assert r.returncode == 1 and hits == [] and not (tmp_path / "curl-args").exists()
    assert 'bad"secret' not in r.stdout


def test_plain_http_needs_the_test_flag(tmp_path, server):
    url, hits = server
    r = run(tmp_path, url, env={"APX_BEAT_ALLOW_HTTP": "0"})
    assert r.returncode == 1 and hits == []


def test_watcher_down_is_one_line_and_exit_0(tmp_path):
    r = run(tmp_path, "http://127.0.0.1:9")
    assert r.returncode == 0 and r.stdout.strip() == "apx-beat: heartbeat failed (watcher unreachable?)"


def test_missing_credential_directory_is_exit_1(tmp_path, server):
    url, _ = server
    r = run(tmp_path, url, env={"CREDENTIALS_DIRECTORY": str(tmp_path / "nope")})
    assert r.returncode == 1 and "no watcher credential" in r.stdout


def test_the_unit_runs_as_its_own_account_with_the_secret_as_a_credential_and_no_privilege():
    cp = configparser.ConfigParser(strict=False, interpolation=None, delimiters=("=",))
    cp.optionxform = str  # type: ignore[assignment]
    cp.read_string(UNIT.read_text())
    s = cp["Service"]
    assert s["DynamicUser"] == "yes" and "User" not in s
    assert s["LoadCredential"] == "watcher:/etc/apx-beat/watcher"
    assert s["ExecStart"] == "/usr/local/sbin/apx-beat", "root-owned copy outside /srv/apx, which apx can write"
    assert s["NoNewPrivileges"] == "yes" and s["ProtectSystem"] == "strict" and s["CapabilityBoundingSet"] == ""
    assert "/srv/apx/current" not in UNIT.read_text()
    t = TIMER.read_text()
    assert "NOT enabled" in t and "disable --now" in t and re.search(r"^OnUnitInactiveSec=5min$", t, re.M)


def test_bootstrap_installs_the_beat_script_root_owned_outside_srv_apx():
    b = (ROOT / "deploy" / "linux" / "bootstrap.sh").read_text()
    assert 'put root:root 755 /usr/local/sbin/apx-beat <"$here/beat.sh"' in b
    assert "enable --now apx-beat" not in b.replace("systemctl enable --now apx-beat.timer", ""), "bootstrap must not enable it"


def test_beat_script_is_valid_sh_and_executable():
    assert subprocess.run(["sh", "-n", str(BEAT)]).returncode == 0
    assert BEAT.stat().st_mode & 0o111
