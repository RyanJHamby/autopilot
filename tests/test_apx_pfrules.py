"""The pf egress rules (backlog S4 first slice). pfctl is macOS-only, so these check the generated text; the syntax check runs by hand."""

import re
import subprocess
from pathlib import Path

import pytest

from autopilot.apx import pfrules

ROOT = Path(__file__).resolve().parent.parent


def rules_for(user, text=None):
    return [ln for ln in (text or pfrules.generate()).splitlines() if ln.endswith(f"user {user}")]


def test_each_account_gets_the_five_rules_in_order():
    for u in pfrules.DEFAULT_USERS:
        r = rules_for(u)
        assert [x.split(" user ")[0] for x in r][0] == "pass out quick on lo0 all"
        assert r[1].startswith("block out quick inet6 all")
        assert r[2].startswith("block out quick inet from any to {")
        assert r[3] == f"pass out quick inet proto tcp from any to any port 443 user {u}"
        assert r[4] == f"block out quick all user {u}"
        assert len(r) == 5


def test_the_private_block_precedes_the_443_pass():
    """pf takes the first `quick` match: if the pass came first, 443 to the router would be allowed."""
    for u in pfrules.DEFAULT_USERS:
        r = rules_for(u)
        assert r.index(next(x for x in r if "to {" in x)) < r.index(next(x for x in r if "port 443" in x))


def test_every_private_range_and_the_metadata_address_are_blocked():
    text = pfrules.generate()
    for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "100.64.0.0/10"):
        assert net in text
    assert "169.254.0.0/16" in pfrules.PRIVATE_V4  # covers 169.254.169.254


def test_no_rule_applies_to_everyone():
    for ln in pfrules.generate().splitlines():
        if ln and not ln.startswith("#"):
            assert re.search(r" user [a-z][a-z0-9_-]*$", ln), ln


def test_only_443_is_ever_passed_off_loopback():
    for ln in pfrules.generate().splitlines():
        if ln.startswith("pass") and "lo0" not in ln:
            assert "port 443" in ln and "proto tcp" in ln


def test_a_bad_account_name_is_refused_not_spliced_into_the_rules():
    for bad in ("", "apx ci", "apx-ci; pass out all", "ROOT", "a\nb"):
        with pytest.raises(ValueError):
            pfrules.generate((bad,))
    with pytest.raises(ValueError):
        pfrules.generate(())


def test_the_scripts_are_valid_bash_and_preview_by_default():
    for name in ("apx-egress.sh", "apx-egress-probe.sh"):
        assert subprocess.run(["bash", "-n", str(ROOT / "deploy" / name)], capture_output=True).returncode == 0
    text = (ROOT / "deploy" / "apx-egress.sh").read_text()
    assert 'DO="${DO:-0}"' in text and '[ "$DO" != 1 ]' in text
    install = text.index("install -m 644")
    assert text.index('[ -f "$BAK" ] || cp "$CONF" "$BAK"') < text.index('>> "$CONF"') and install < text.index('>> "$CONF"')
    assert "UNDO" in text


def test_the_probe_fails_when_a_forbidden_connection_succeeds():
    body = (ROOT / "deploy" / "apx-egress-probe.sh").read_text()
    assert 'exit "$leaks"' in body and "must_pass" in body  # a vacuous probe (nothing reachable) is itself reported
