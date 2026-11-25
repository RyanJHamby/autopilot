"""Weekly red-team job (backlog S7): try the exfiltration paths as the sandbox accounts and require every one of them to fail.

No second probe implementation: the secret-read probes are the doctor's own negative checks (`sandbox_checks`, `agent_checks`: "the
account CANNOT read ..."), and the network probes are deploy/linux/egress-probe.sh (App-key-free, run through `sudo`). A probe that
SUCCEEDS is red: one ledger row (kind 'redteam', conclusion 'failure', the probe names in the note), a doctor FAIL (`doctor_check`), and a
"check failed" line in the pass log, which makes status.json not ok and so reaches the existing silent-failure alert.

It starts nothing inside the work-hours freeze (freeze_gate.frozen_reason, the same resolver as every other job), runs at most once a week
after a green result, and is retried on the next pass after a red or missing one. It needs no network destination beyond what the probes
already use.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import subprocess
from pathlib import Path
from typing import Callable

from . import freeze_gate, hostenv
from .ledger import Ledger

KIND = "redteam"
LEDGER_REPO = "apx-host"  # the ledger's repo column is free text; this row is about the host, not a repo
INTERVAL = dt.timedelta(days=7)
CHECK_NAME = "red-team probes (weekly: every exfiltration path must fail)"
EGRESS_SCRIPTS = {"linux": "deploy/linux/egress-probe.sh", "darwin": "deploy/apx-egress-probe.sh"}


def egress_argv(s) -> list[str]:
    rel = EGRESS_SCRIPTS["darwin" if hostenv.is_darwin() else "linux"]
    return ["/usr/bin/sudo", "-n", "/bin/bash", str(Path(s.code_dir()) / rel)]


def run_egress(argv: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as e:
        return 255, type(e).__name__
    return p.returncode, p.stdout


def due(led: Ledger, now: dt.datetime) -> bool:
    """False while a green run is less than a week old; a red run does not count, so it is retried on the next pass."""
    since = (now - INTERVAL).astimezone(dt.timezone.utc).isoformat()
    row = led.db.execute(
        "select 1 from runs where kind=? and conclusion='success' and created_at >= ? limit 1", (KIND, since)
    ).fetchone()
    return row is None


def _negative_checks(checks) -> list:
    return [c for c in checks if "CANNOT" in c.name]


def probe(s, ci_launcher, agent_launcher, egress_run: Callable) -> tuple[int, list[str], list[str]]:
    """(probes tried, probes that SUCCEEDED, notes). Success of a probe is the bad outcome."""
    from . import doctor  # lazy: the doctor imports this module for its check

    tried, leaked, notes = 0, [], []
    checks = []
    if s.ci_user:
        checks += _negative_checks(doctor.sandbox_checks(s, ci_launcher))
    if s.agent_user:
        checks += _negative_checks(doctor.agent_checks(s, agent_launcher))
    tried += len(checks)
    leaked += [f"{c.name} ({c.detail})" for c in checks if not c.ok]
    rc, out = egress_run(egress_argv(s))
    bad = [ln.strip() for ln in out.splitlines() if ln.startswith(("LEAK", "BROKEN"))]
    if bad:  # BROKEN is a failed control: a refusal then proves nothing, so it is red too
        tried += sum(ln.startswith(("ok", "LEAK", "BROKEN")) for ln in out.splitlines())
        leaked += [f"egress {ln}" for ln in bad]
    elif rc == 0:
        tried += sum(ln.startswith("ok") for ln in out.splitlines())
    else:
        notes.append(f"egress probe not run (exit {rc}: {out.strip().splitlines()[0][:100] if out.strip() else 'no output'})")
    return tried, leaked, notes


def run_weekly(
    s,
    led: Ledger,
    *,
    now: dt.datetime | None = None,
    ci_launcher=None,
    agent_launcher=None,
    egress_run: Callable = run_egress,
) -> list[str]:
    """One pass's worth of the job: pass-log lines (empty when nothing ran). Never raises: a crash is itself reported as red."""
    now = now or dt.datetime.now(dt.timezone.utc)
    if not (s.ci_user or s.agent_user) or freeze_gate.frozen_reason() is not None or not due(led, now):
        return []
    from .runas import Launcher

    run_id = led.start(LEDGER_REPO, 0, kind=KIND, now=now)
    try:
        tried, leaked, notes = probe(
            s,
            ci_launcher or Launcher(s.ci_user),
            agent_launcher or Launcher(s.agent_user),
            egress_run,
        )
    except Exception as e:  # noqa: BLE001 - a probe that cannot run must not read as "nothing leaked"
        tried, leaked, notes = 0, [f"red-team job crashed ({type(e).__name__})"], []
    note = "; ".join(leaked + notes)
    led.finish(run_id, "failure" if leaked else "success", note=note or None, now=now)
    if leaked:
        return [f"redteam check failed: {len(leaked)} exfiltration probe(s) SUCCEEDED: {'; '.join(leaked)}"[:300], *notes]
    return [f"redteam: all {tried} exfiltration probes were refused (green)", *notes]


def doctor_check(db_path: str, now: dt.datetime | None = None):
    """The doctor's view: FAIL while the latest red-team result is red. No result yet is an advisory, not a failure."""
    from .doctor import Check

    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        led = Ledger.read_only(db_path)
        try:
            row = led.db.execute(
                "select created_at, conclusion, note from runs where kind=? and status='completed' order by id desc limit 1", (KIND,)
            ).fetchone()
        finally:
            led.db.close()
    except sqlite3.Error as e:
        return Check(CHECK_NAME, True, f"no result yet (ledger {db_path} unreadable or empty: {type(e).__name__})")
    if row is None:
        return Check(CHECK_NAME, True, "no result yet: the first run happens outside the work-hours freeze")
    if row["conclusion"] != "success":
        return Check(CHECK_NAME, False, f"RED at {row['created_at']}: {row['note'] or 'a probe succeeded'}")
    return Check(CHECK_NAME, True, f"green at {row['created_at']}" + (f"; {row['note']}" if row["note"] else ""))
