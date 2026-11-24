"""S7: the weekly red-team job. Every exfiltration probe must FAIL; one that succeeds is a red ledger row, a doctor FAIL and a status problem.

The probes are the doctor's own negative checks (sandbox_checks, agent_checks) plus deploy/linux/egress-probe.sh: no second implementation.
The freeze is the real resolver with a frozen clock, so none of this depends on when the suite runs.
"""

import dataclasses
import datetime as dt

import pytest
from test_apx_doctor import AgentStub, Stub, run, settings
from test_apx_freeze_gate import MON_7PM, MON_9AM, policy_file

from autopilot.apx import doctor as dr
from autopilot.apx import freeze_gate as fg
from autopilot.apx import redteam, status
from autopilot.apx.ledger import Ledger

UTC = dt.timezone.utc
NOW = MON_7PM.astimezone(UTC)  # outside the work-hours freeze


@pytest.fixture(autouse=True)
def open_window(tmp_path, monkeypatch):
    policy_file(tmp_path, monkeypatch)
    monkeypatch.setattr(fg, "_clock", lambda: NOW)


def egress_ok(argv):
    return 0, "ok    github on 443\nok    arbitrary host\nok    dns tunnel\n"


def egress_leak(argv):
    return 2, "ok    github on 443\nLEAK  arbitrary host\nLEAK  ipv6\n"


def job(tmp_path, led, *, ci=None, agent=None, egress=egress_ok, now=NOW):
    s = settings(tmp_path, ci_user="apx-ci", agent_user="apx-agent")
    return redteam.run_weekly(s, led, now=now, ci_launcher=ci or Stub(), agent_launcher=agent or AgentStub(), egress_run=egress)


def rows(led):
    return [dict(r) for r in led.db.execute("select * from runs where kind='redteam' order by id")]


def test_all_probes_failing_is_green(tmp_path):
    led = Ledger()
    lines = job(tmp_path, led)
    (row,) = rows(led)
    assert row["conclusion"] == "success" and row["status"] == "completed"
    assert not status.problems_in(lines)


@pytest.mark.parametrize("what", ["App key", "Claude token", "orchestrator home"])
def test_the_sandbox_account_reading_a_secret_is_red(tmp_path, what):
    led = Ledger()
    lines = job(tmp_path, led, ci=Stub(leak=(what,)))
    (row,) = rows(led)
    assert row["conclusion"] == "failure" and what in row["note"]
    assert status.problems_in(lines)


def test_the_agent_account_reading_the_write_key_is_red(tmp_path):
    led = Ledger()
    lines = job(tmp_path, led, agent=AgentStub(leak=("App key",)))
    assert rows(led)[0]["conclusion"] == "failure"
    assert status.problems_in(lines)


def test_a_network_leak_is_red(tmp_path):
    led = Ledger()
    lines = job(tmp_path, led, egress=egress_leak)
    (row,) = rows(led)
    assert row["conclusion"] == "failure" and "arbitrary host" in row["note"]
    assert status.problems_in(lines)


def test_a_broken_control_is_red_because_a_refusal_then_proves_nothing(tmp_path):
    led = Ledger()
    job(tmp_path, led, egress=lambda argv: (1, "BROKEN github on 443 (unreachable)\n"))
    assert rows(led)[0]["conclusion"] == "failure"


def test_an_egress_probe_that_cannot_run_is_noted_not_called_green_silently(tmp_path):
    led = Ledger()
    lines = job(tmp_path, led, egress=lambda argv: (2, "run as root\n"))
    (row,) = rows(led)
    assert row["conclusion"] == "success" and "egress probe not run" in row["note"]
    assert any("egress probe not run" in ln for ln in lines)


def test_does_not_run_inside_the_freeze_window(tmp_path, monkeypatch):
    monkeypatch.setattr(fg, "_clock", lambda: MON_9AM)
    led = Ledger()

    def boom(argv):
        raise AssertionError("a probe ran inside the freeze")

    lines = job(tmp_path, led, egress=boom, ci=Stub(dead=True), now=MON_9AM.astimezone(UTC))
    assert rows(led) == [] and lines == []


def test_runs_once_a_week(tmp_path):
    led = Ledger()
    job(tmp_path, led)
    assert job(tmp_path, led, now=NOW + dt.timedelta(days=3)) == []
    job(tmp_path, led, now=NOW + dt.timedelta(days=7, minutes=1))
    assert len(rows(led)) == 2


def test_a_red_result_is_retried_the_next_pass_not_a_week_later(tmp_path):
    led = Ledger()
    job(tmp_path, led, egress=egress_leak)
    job(tmp_path, led, now=NOW + dt.timedelta(hours=1))
    assert [r["conclusion"] for r in rows(led)] == ["failure", "success"]


def test_no_sandbox_accounts_means_nothing_to_probe(tmp_path):
    led = Ledger()
    s = settings(tmp_path)
    assert redteam.run_weekly(s, led, now=NOW, egress_run=egress_ok) == [] and rows(led) == []


# ---- the doctor -------------------------------------------------------------------------------------------------------------


def db_with(tmp_path, **kw):
    path = tmp_path / "apx.sqlite"
    led = Ledger(str(path))
    job(tmp_path, led, **kw)
    led.db.close()
    return str(path)


def test_doctor_check_passes_after_a_green_run(tmp_path):
    c = redteam.doctor_check(db_with(tmp_path), now=NOW)
    assert c.ok and "green" in c.detail


def test_doctor_check_fails_after_a_red_run(tmp_path):
    c = redteam.doctor_check(db_with(tmp_path, egress=egress_leak), now=NOW)
    assert not c.ok and "arbitrary host" in c.detail


def test_doctor_check_with_no_run_yet_is_an_advisory(tmp_path):
    assert redteam.doctor_check(str(tmp_path / "none.sqlite"), now=NOW).ok


def test_run_doctor_fails_on_a_red_ledger_row(tmp_path):
    s = dataclasses.replace(settings(tmp_path, ci_user="apx-ci", agent_user="apx-agent"), db_path=db_with(tmp_path, egress=egress_leak))
    out = run(s, agent_launcher=AgentStub())
    assert not out[redteam.CHECK_NAME].ok
    assert dr.render(list(out.values()))[1] is False
