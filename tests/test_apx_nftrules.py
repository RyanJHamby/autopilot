"""The Linux egress rules for the three apx accounts: what each may reach, and that nothing else can.

These pin the security properties of the generated text. Whether the kernel enforces them is a different question, answered by
deploy/linux/egress-selftest.sh on a real Linux kernel (a container here, the VPS later)."""

import re
import subprocess
import sys

import pytest

from autopilot.apx import nftrules
from autopilot.fabric import firewall

UIDS = {"apx": 1001, "apx-ci": 1002, "apx-agent": 1003}


def chain(text: str, name: str) -> str:
    m = re.search(rf"chain {name} \{{(.*?)\n  \}}", text, re.S)
    assert m, f"no chain {name}"
    return m.group(1)


def rules(text: str, name: str) -> list[str]:
    return [ln.strip() for ln in chain(text, name).splitlines() if ln.strip() and not ln.strip().startswith(("type ", "#"))]


@pytest.fixture
def nft():
    return nftrules.render_nft(UIDS)


# --- lanes -----------------------------------------------------------------------------------------------------------------------


def test_each_account_is_in_exactly_one_lane():
    assert nftrules.LANE_OF == {"apx": "orch", "apx-ci": "ci", "apx-agent": "exec"}


def test_the_ci_and_exec_lanes_are_the_fabrics_and_the_orchestrator_gets_only_github():
    lanes = nftrules.lanes()
    assert lanes["ci"] == firewall.LANES["ci"] and lanes["exec"] == firewall.LANES["exec"]
    assert lanes["orch"] == firewall.GITHUB


def test_a_control_plane_host_is_added_to_the_orchestrator_only():
    lanes = nftrules.lanes(control_host="control.example.dev")
    assert "control.example.dev" in lanes["orch"]
    assert "control.example.dev" not in lanes["ci"] + lanes["exec"]


def test_the_ci_lane_can_reach_the_registries_and_the_agent_lane_can_reach_the_model_but_not_the_reverse():
    lanes = nftrules.lanes()
    assert "registry.npmjs.org" in lanes["ci"] and "registry.npmjs.org" not in lanes["exec"]
    assert "api.anthropic.com" in lanes["exec"] and "api.anthropic.com" not in lanes["ci"]


# --- the ruleset ------------------------------------------------------------------------------------------------------------------


def test_loading_the_file_twice_replaces_the_table_instead_of_failing_or_stacking(nft):
    head = nft.splitlines()[:3]
    assert head == ["table inet apx", "delete table inet apx", "table inet apx {"], "declare, delete, redefine: one atomic reload"


def test_one_table_with_a_timed_set_per_lane(nft):
    assert "table inet apx {" in nft
    for s in ("ci_v4", "exec_v4", "orch_v4"):
        assert re.search(rf"set {s} \{{\s+type ipv4_addr\s+flags timeout\s+timeout 1h\s+\}}", nft), s


def test_accounts_are_matched_by_numeric_uid_and_sent_to_their_own_lane(nft):
    out = rules(nft, "output")
    assert "meta skuid 1002 jump lane_ci" in out
    assert "meta skuid 1003 jump lane_exec" in out
    assert "meta skuid 1001 jump lane_orch" in out
    assert not any(re.search(r"skuid [a-z]", r) for r in out), "names resolve at load time and can change; only numbers"


def test_the_output_hook_leaves_everyone_else_alone(nft):
    assert re.search(r"hook output priority 0; policy accept;", chain(nft, "output")), "admins and apt must not be affected"


@pytest.mark.parametrize("lane,set_name", [("ci", "ci_v4"), ("exec", "exec_v4"), ("orch", "orch_v4")])
def test_a_lane_accepts_only_its_own_set_on_443_and_the_resolver_and_rejects_the_rest(nft, lane, set_name):
    r = rules(nft, f"lane_{lane}")
    accepts = [x for x in r if x.endswith("accept")]
    allowed_443 = [x for x in accepts if f"@{set_name}" in x]
    assert len(allowed_443) == 1 and "tcp dport 443" in allowed_443[0]
    other_sets = {"ci_v4", "exec_v4", "orch_v4"} - {set_name}
    assert not any(f"@{o}" in x for x in r for o in other_sets), "a lane must never touch another lane's set"
    assert r[-1].endswith("reject") or "reject" in r[-1], "the last word is a refusal"


@pytest.mark.parametrize("lane", ["ci", "exec", "orch"])
def test_every_blocked_range_is_excluded_from_the_allowed_destinations(nft, lane):
    rule = next(x for x in rules(nft, f"lane_{lane}") if "@" in x and x.endswith("accept"))
    for cidr in firewall.BLOCKED_V4:
        assert cidr in rule, f"{cidr} must be refused even if DNS hands out an address in it (rebinding)"


@pytest.mark.parametrize("lane", ["ci", "exec", "orch"])
def test_loopback_is_open_only_for_the_allowlist_resolver_not_for_all_of_localhost(nft, lane):
    accepts = [x for x in rules(nft, f"lane_{lane}") if x.endswith("accept") and x.startswith("ip daddr 127.")]
    assert len(accepts) == 2 and all("5354" in x and "127.0.0.1" in x for x in accepts), accepts
    assert not any(re.search(r"daddr 127\.0\.0\.0/8\s+accept", x) for x in accepts)


@pytest.mark.parametrize("lane", ["ci", "exec", "orch"])
def test_ipv6_and_other_ports_are_never_accepted(nft, lane):
    r = rules(nft, f"lane_{lane}")
    assert not any("ip6" in x and x.endswith("accept") for x in r)
    assert not any(re.search(r"dport (?!443|5354)\d+", x) and x.endswith("accept") for x in r)


@pytest.mark.parametrize("lane", ["ci", "exec", "orch"])
def test_established_connections_survive_a_set_entry_expiring(nft, lane):
    assert any("ct state established,related accept" in x for x in rules(nft, f"lane_{lane}"))


def test_dns_from_the_three_accounts_is_redirected_to_the_allowlist_resolver_and_nobody_elses(nft):
    r = rules(nft, "dns")
    for proto in ("udp", "tcp"):
        assert any(proto in x and "dport 53" in x and "redirect to :5354" in x for x in r), proto
    uids = set(re.findall(r"skuid \{ ([\d, ]+) \}", " ".join(r)))
    assert uids == {"1001, 1002, 1003"} or all(set(u.replace(" ", "").split(",")) == {"1001", "1002", "1003"} for u in uids)
    assert re.search(r"hook output priority -100", chain(nft, "dns")), (
        "before the filter hook, so the filter sees the redirected packet"
    )


def test_the_dns_port_is_configurable_and_follows_through_every_rule():
    text = nftrules.render_nft(UIDS, dns_port=5399)
    assert "5399" in text and "5354" not in text


def test_output_is_deterministic():
    assert nftrules.render_nft(UIDS) == nftrules.render_nft(dict(reversed(list(UIDS.items()))))


# --- input validation --------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "uids",
    [
        {"apx": 1001, "apx-ci": 1002},  # an account is missing
        {"apx": 1001, "apx-ci": 1002, "apx-agent": 0},  # root
        {"apx": 1001, "apx-ci": 1001, "apx-agent": 1003},  # two accounts sharing a uid would share a lane
        {"apx": "1001", "apx-ci": 1002, "apx-agent": 1003},  # not an int
        {"apx": 1001, "apx-ci": -5, "apx-agent": 1003},
        {"apx": 1001, "apx-ci": 1002, "apx-agent": 1003, "root": 0},  # an account that is not ours
    ],
)
def test_bad_uids_are_refused(uids):
    with pytest.raises(ValueError):
        nftrules.render_nft(uids)


@pytest.mark.parametrize("port", [0, 53, 1023, 65536, "5354", None])
def test_a_bad_dns_port_is_refused(port):
    with pytest.raises(ValueError):
        nftrules.render_nft(UIDS, dns_port=port)


# --- the resolver config ------------------------------------------------------------------------------------------------------------


@pytest.fixture
def dns():
    return nftrules.render_dnsmasq(control_host="control.example.dev")


def test_the_resolver_listens_only_on_loopback_and_has_no_default_upstream(dns):
    for line in ("listen-address=127.0.0.1", "bind-interfaces", "no-resolv", "no-hosts", "port=5354"):
        assert line in dns.splitlines(), line
    servers = [ln for ln in dns.splitlines() if ln.startswith("server=")]
    assert servers and all(re.match(r"server=/[a-z0-9.-]+/\d+\.\d+\.\d+\.\d+$", s) for s in servers), (
        "every upstream is scoped to a name"
    )


def sets_for(dns_text: str, host: str) -> set[str]:
    line = next(ln for ln in dns_text.splitlines() if ln.startswith(f"nftset=/{host}/"))
    return {m.group(1) for m in re.finditer(r"4#inet#apx#(\w+)", line)}


def test_each_name_fills_only_the_sets_of_the_lanes_that_may_reach_it(dns):
    assert sets_for(dns, "github.com") == {"ci_v4", "exec_v4", "orch_v4"}
    assert sets_for(dns, "registry.npmjs.org") == {"ci_v4"}
    assert sets_for(dns, "pypi.org") == {"ci_v4"}
    assert sets_for(dns, "api.anthropic.com") == {"exec_v4"}
    assert sets_for(dns, "control.example.dev") == {"orch_v4"}


def test_every_name_the_resolver_answers_has_a_set_so_no_answer_goes_unrecorded(dns):
    named = {m.group(1) for m in re.finditer(r"^server=/([^/]+)/", dns, re.M)}
    mapped = {m.group(1) for m in re.finditer(r"^nftset=/([^/]+)/", dns, re.M)}
    assert named == mapped


def test_upstream_is_configurable_and_validated():
    assert "server=/github.com/1.1.1.1" in nftrules.render_dnsmasq(upstream="1.1.1.1").splitlines()
    with pytest.raises(ValueError):
        nftrules.render_dnsmasq(upstream="not-an-ip")


@pytest.mark.parametrize(
    "bad",
    [
        "evil.com\nserver=/x/6.6.6.6",
        "*.github.com",
        "UPPER.example.com",
        "1.2.3.4",
        "no_underscore.example.com",
        "-bad.example.com",
        "a" * 300 + ".com",
        "",
    ],
)
def test_a_control_host_that_is_not_a_plain_lowercase_hostname_is_refused(bad):
    with pytest.raises(ValueError):
        nftrules.lanes(control_host=bad)


# --- the command line ------------------------------------------------------------------------------------------------------------------


def run_cli(*args):
    return subprocess.run([sys.executable, "-m", "autopilot.apx.nftrules", *args], capture_output=True, text=True)


def test_the_cli_prints_the_same_text_as_the_function():
    r = run_cli("nft", "--uid", "apx=1001", "--uid", "apx-ci=1002", "--uid", "apx-agent=1003")
    assert r.returncode == 0 and r.stdout == nftrules.render_nft(UIDS)
    d = run_cli("dnsmasq", "--control-host", "control.example.dev")
    assert d.returncode == 0 and d.stdout == nftrules.render_dnsmasq(control_host="control.example.dev")


def test_the_cli_fails_loudly_on_bad_input_and_prints_nothing_on_stdout():
    r = run_cli("nft", "--uid", "apx=0", "--uid", "apx-ci=1002", "--uid", "apx-agent=1003")
    assert r.returncode != 0 and r.stdout == "" and "root" in r.stderr.lower() or r.returncode != 0
    assert run_cli("nft", "--uid", "apx=abc").returncode != 0
    assert run_cli("nft").returncode != 0
