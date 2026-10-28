import pytest

from autopilot.fabric import firewall as fw


def _lines(text):
    return [ln.strip() for ln in text.splitlines()]


@pytest.mark.parametrize("lane", sorted(fw.LANES))
def test_default_policy_is_drop_and_input_is_closed(lane):
    t = fw.render_nft(lane)
    assert "hook forward priority 0; policy drop;" in t
    assert 'iifname "apbr0" counter drop' in t  # nothing else reaches the host from the sandbox


@pytest.mark.parametrize("lane", sorted(fw.LANES))
def test_blocked_ranges_are_dropped_before_any_accept(lane):
    ls = _lines(fw.render_nft(lane))
    drop_private = next(i for i, ln in enumerate(ls) if "ip daddr {" in ln and ln.endswith("counter drop"))
    first_forward_accept = next(i for i, ln in enumerate(ls) if "@allow4" in ln and "accept" in ln)
    assert drop_private < first_forward_accept
    for cidr in ("10.0.0.0/8", "192.168.0.0/16", "169.254.0.0/16", "100.64.0.0/10", "127.0.0.0/8"):
        assert cidr in ls[drop_private]


def test_ipv6_is_dropped_outright():
    assert 'meta nfproto ipv6 counter drop' in fw.render_nft("exec")


def test_only_tcp_443_is_ever_accepted_outbound():
    t = fw.render_nft("ci")
    accepts = [ln.strip() for ln in t.splitlines() if "accept" in ln and "@allow4" in ln]
    assert accepts and all("tcp dport 443" in ln for ln in accepts)


def test_dns_goes_only_to_the_pinned_resolver():
    t = fw.render_nft("exec", dns_ip="10.77.0.1")
    dns = [ln for ln in t.splitlines() if "dport 53" in ln]
    assert len(dns) == 2 and all("ip daddr 10.77.0.1" in ln for ln in dns)


def test_resolver_has_no_default_upstream_and_lists_only_lane_hosts():
    conf = fw.render_dnsmasq("exec")
    assert "no-resolv" in conf
    names = {ln.split("/")[1] for ln in conf.splitlines() if ln.startswith("server=/")}
    assert names == set(fw.LANES["exec"])
    assert all(f"nftset=/{h}/4#inet#apfab#allow4" in conf for h in names)


def test_lanes_do_not_leak_each_others_hosts():
    assert "api.anthropic.com" not in fw.LANES["ci"] and "api.anthropic.com" not in fw.LANES["trusted"]
    assert not set(fw.REGISTRIES) & set(fw.LANES["exec"])  # the secret-bearing lane cannot fetch arbitrary packages
    assert set(fw.LANES["trusted"]) == set(fw.GITHUB)


def test_no_wildcards_or_ips_in_any_lane():
    for lane in fw.LANES:
        fw.hosts(lane)  # raises on anything that is not a plain hostname
    fw.LANES["bad"] = ("*.evil.com",)
    try:
        with pytest.raises(ValueError):
            fw.hosts("bad")
    finally:
        del fw.LANES["bad"]


def test_unknown_lane_is_refused():
    with pytest.raises(ValueError):
        fw.render_nft("everything")
