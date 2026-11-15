"""Where apx keeps the state that must outlive a release and be shared by the daemon and the updater: the ledger and the work dir.

The Linux units run the daemon from /srv/apx/current (a link to releases/<sha>) and the updater from /srv/apx/updater, each with
PrivateTmp=yes. A relative ledger path then lands inside the release (a fresh ledger, so fresh daily caps, after every switch) and a
work dir under /tmp is a different directory for each unit (so the updater never sees the daemon's lock). These pin the durable defaults,
the doctor's refusal of the unsafe ones, and the one-time copy of the old per-release ledger."""

import os
import sqlite3
from pathlib import Path

import pytest
from test_apx_daemon import env
from test_apx_doctor import run as run_doctor
from test_apx_doctor import settings as doctor_settings

from autopilot.apx import daemon as dm
from autopilot.apx import doctor as dr
from autopilot.apx import hostenv
from autopilot.apx.github import GitHubError


@pytest.fixture
def linux(monkeypatch):
    monkeypatch.setattr(hostenv, "is_darwin", lambda: False)


@pytest.fixture
def mac(monkeypatch):
    monkeypatch.setattr(hostenv, "is_darwin", lambda: True)


def defaults_env(tmp_path, home: str) -> dict:
    e = env(tmp_path, HOME=home)
    del e["APX_DB"], e["APX_WORK"]
    return e


def by_name(checks):
    return {c.name: c for c in checks}


DB, WORK = "ledger path (APX_DB)", "work dir (APX_WORK, shared by the daemon and the updater)"


# --- the defaults --------------------------------------------------------------------------------------------------------------------


def test_unset_paths_default_to_the_apx_state_dir_not_the_release_or_tmp(tmp_path, linux):
    s = dm.Settings.from_env(defaults_env(tmp_path, "/home/apx"))
    assert s.db_path == "/home/apx/.apx/apx.sqlite"
    assert s.work_dir == Path("/home/apx/.apx/work")


def test_apx_state_moves_both_and_explicit_settings_still_win(tmp_path):
    e = defaults_env(tmp_path, "/home/apx")
    e["APX_STATE"] = "/var/lib/apx"
    s = dm.Settings.from_env(e)
    assert (s.db_path, s.work_dir) == ("/var/lib/apx/apx.sqlite", Path("/var/lib/apx/work"))
    s = dm.Settings.from_env(env(tmp_path))
    assert (s.db_path, s.work_dir) == (str(tmp_path / "db.sqlite"), tmp_path / "work")


def test_the_mac_layout_keeps_what_apx_setup_already_writes(tmp_path, mac):
    from autopilot.apx import setup

    state = Path("/Users/apx/.apx")
    written = dict(ln.split("=", 1) for ln in setup.render_env(state, "1", {"RyanJHamby/autopilot": 1}, "a" * 40).splitlines())
    s = dm.Settings.from_env(defaults_env(tmp_path, "/Users/apx"))
    assert (s.db_path, str(s.work_dir)) == (written["APX_DB"], written["APX_WORK"])


def test_daemon_and_updater_resolve_the_same_paths_from_their_own_working_directories(tmp_path, monkeypatch):
    shared = tmp_path / "srv"
    (shared / "releases" / "a").mkdir(parents=True)
    (shared / "updater").mkdir()
    (shared / "current").symlink_to(shared / "releases" / "a")
    e = defaults_env(tmp_path, str(tmp_path / "home"))
    seen = []
    for cwd in (shared / "current", shared / "updater"):  # apx.service and apx-updater.service WorkingDirectory
        monkeypatch.chdir(cwd)
        s = dm.Settings.from_env(e)
        seen.append((s.db_path, s.work_dir))
    assert seen[0] == seen[1]
    assert all(os.path.isabs(p) for p in seen[0])


def test_the_ledger_survives_a_release_switch(tmp_path, monkeypatch):
    shared = tmp_path / "srv"
    for sha in ("a", "b"):
        (shared / "releases" / sha).mkdir(parents=True)
    cur = shared / "current"
    e = defaults_env(tmp_path, str(tmp_path / "home"))
    (tmp_path / "home" / ".apx").mkdir(parents=True)
    paths = []
    for sha in ("a", "b"):
        if cur.is_symlink():
            cur.unlink()
        cur.symlink_to(shared / "releases" / sha)
        monkeypatch.chdir(cur)
        s = dm.Settings.from_env(e)
        paths.append(os.path.realpath(s.db_path))
        db = sqlite3.connect(s.db_path)
        db.execute("create table if not exists t (sha text)")
        db.execute("insert into t values (?)", (sha,))
        db.commit()
        rows = [r[0] for r in db.execute("select sha from t")]
        db.close()
    assert paths[0] == paths[1]
    assert rows == ["a", "b"]  # release b sees what release a wrote
    assert not any((shared / "releases" / sha / "apx.sqlite").exists() for sha in ("a", "b"))


# --- the doctor ----------------------------------------------------------------------------------------------------------------------


def _s(tmp_path, db, work):
    s = dm.Settings.from_env(env(tmp_path))
    s.db_path, s.work_dir, s.shared_dir = db, Path(work), "/srv/apx"
    return s


def test_doctor_fails_a_relative_ledger_path(tmp_path, linux):
    c = by_name(dr.state_path_checks(_s(tmp_path, "apx.sqlite", "/home/apx/.apx/work")))[DB]
    assert not c.ok and "relative" in c.detail


@pytest.mark.parametrize("db", ["/srv/apx/current/apx.sqlite", "/srv/apx/releases/abc/apx.sqlite", "/tmp/apx.sqlite", "/var/tmp/x.db"])
def test_doctor_fails_a_ledger_inside_the_releases_or_a_tmp_dir(tmp_path, linux, db):
    c = by_name(dr.state_path_checks(_s(tmp_path, db, "/home/apx/.apx/work")))[DB]
    assert not c.ok, c.detail


@pytest.mark.parametrize("work", ["/tmp/apx-work", "/var/tmp/apx-work", "/tmp"])
def test_doctor_fails_a_tmp_work_dir_on_linux(tmp_path, linux, work):
    c = by_name(dr.state_path_checks(_s(tmp_path, "/home/apx/.apx/apx.sqlite", work)))[WORK]
    assert not c.ok and "PrivateTmp" in c.detail


def test_doctor_fails_a_relative_work_dir(tmp_path, linux):
    c = by_name(dr.state_path_checks(_s(tmp_path, "/home/apx/.apx/apx.sqlite", "work")))[WORK]
    assert not c.ok and "relative" in c.detail


def test_doctor_passes_the_durable_paths_and_shows_them_resolved(tmp_path, linux):
    out = by_name(dr.state_path_checks(_s(tmp_path, "/home/apx/.apx/apx.sqlite", "/home/apx/.apx/work")))
    # The doctor reports resolved paths; on macOS /home is itself a symlink, so compare against the same resolution.
    assert out[DB].ok and out[DB].detail == os.path.realpath("/home/apx/.apx/apx.sqlite")
    assert out[WORK].ok and out[WORK].detail == os.path.realpath("/home/apx/.apx/work")


def test_a_tmp_work_dir_on_the_mac_is_not_a_failure(tmp_path, mac):
    assert by_name(dr.state_path_checks(_s(tmp_path, "/Users/apx/.apx/apx.sqlite", "/tmp/apx-work")))[WORK].ok


def test_the_full_doctor_runs_the_state_path_checks(tmp_path):
    out = run_doctor(doctor_settings(tmp_path, ci_user="apx-ci"))
    assert out[DB].ok and out[WORK].ok, (out[DB].detail, out[WORK].detail)


# --- the one-time copy of the old per-release ledger -----------------------------------------------------------------------------------


def _ledger(path: Path, value: str) -> None:
    db = sqlite3.connect(path)
    db.execute("create table if not exists t (v text)")
    db.execute("delete from t")
    db.execute("insert into t values (?)", (value,))
    db.commit()
    db.close()


def _value(path: Path) -> str:
    db = sqlite3.connect(path)
    try:
        return db.execute("select v from t").fetchone()[0]
    finally:
        db.close()


def test_the_old_ledger_is_copied_once_and_never_moved(tmp_path):
    old, new = tmp_path / "release" / "apx.sqlite", tmp_path / "home" / ".apx" / "apx.sqlite"
    old.parent.mkdir()
    _ledger(old, "from the release")
    note = hostenv.adopt_old_ledger(new, old)
    assert note and str(old) in note and str(new) in note
    assert _value(new) == "from the release" and old.exists()  # copied, the original left in place
    assert (new.stat().st_mode & 0o777) == 0o600 and (new.parent.stat().st_mode & 0o777) == 0o700
    _ledger(old, "changed later")
    assert hostenv.adopt_old_ledger(new, old) is None  # once: an existing ledger is never overwritten
    assert _value(new) == "from the release"


def test_nothing_to_copy_is_a_no_op(tmp_path):
    new = tmp_path / "home" / ".apx" / "apx.sqlite"
    assert hostenv.adopt_old_ledger(new, tmp_path / "missing.sqlite") is None
    assert not new.exists()
    same = tmp_path / "same.sqlite"
    _ledger(same, "x")
    assert hostenv.adopt_old_ledger(same, same) is None


def test_the_first_pass_on_the_default_copies_the_release_ledger_and_says_so(tmp_path, monkeypatch, capsys):
    release, home = tmp_path / "releases" / "a", tmp_path / "home"
    release.mkdir(parents=True)
    _ledger(release / "apx.sqlite", "old pass")
    for k, v in defaults_env(tmp_path, str(home)).items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("APX_DB", raising=False)
    monkeypatch.delenv("APX_WORK", raising=False)
    monkeypatch.delenv("APX_STATE", raising=False)
    monkeypatch.delenv("APX_LIVE", raising=False)
    monkeypatch.chdir(release)
    s = dm.Settings.from_env()

    def factory(token):
        def api(method, path, body=None):
            if path.startswith("/app/"):
                return {"token": "t", "expires_at": "2099-01-01T00:00:00Z"}
            raise GitHubError(404, path, "")

        return api

    dm.run_once(s, api_factory=factory)
    assert _value(home / ".apx" / "apx.sqlite") == "old pass"
    assert (release / "apx.sqlite").exists()
    assert "copied the per-release ledger" in capsys.readouterr().out
