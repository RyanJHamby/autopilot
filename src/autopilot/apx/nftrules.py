"""Egress allowlist for the three apx accounts on a Linux host: nftables rules plus the dnsmasq config that feeds them.

Each account's outbound traffic is matched by numeric uid (`meta skuid`) and sent to its own lane. A lane may open TCP 443 only to
addresses its own resolver answers recorded for the names that lane allows, never to a private, link-local or metadata range, and the
resolver itself is the only loopback service it can reach. Everything else, including all IPv6, is refused. DNS from the three accounts is
redirected to a local allowlist resolver, so a name outside the list simply does not resolve (this also closes DNS tunnelling).

Everyone else on the host (the admin, apt, the resolver itself) is untouched: the output hook's policy is accept.

This module only renders text. Whether the kernel enforces it is checked by deploy/linux/egress-selftest.sh on a real Linux kernel.

    python -m autopilot.apx.nftrules nft --uid apx=1001 --uid apx-ci=1002 --uid apx-agent=1003
    python -m autopilot.apx.nftrules dnsmasq [--control-host NAME]
"""

import argparse
import ipaddress
import re
import sys

from autopilot.fabric import firewall

# which lane each account is in; one account, one lane
LANE_OF = {"apx": "orch", "apx-ci": "ci", "apx-agent": "exec"}
DEFAULT_DNS_PORT = 5354
SET_TIMEOUT = "1h"
_LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


def _hostname(name: object) -> str:
    """A plain lowercase DNS name: no wildcards, no whitespace or newlines (config injection), no bare IPs."""
    if not isinstance(name, str) or not name or len(name) > 253:
        raise ValueError(f"not a usable hostname: {name!r}")
    labels = name.split(".")
    if len(labels) < 2 or not all(_LABEL.fullmatch(x) for x in labels):
        raise ValueError(f"not a plain lowercase hostname: {name!r}")
    if labels[-1].isdigit():
        raise ValueError(f"a bare IP address is not a hostname: {name!r}")
    return name


def lanes(control_host: str | None = None) -> dict[str, tuple[str, ...]]:
    """lane -> allowed names. The orchestrator gets GitHub, plus the control-plane host if one is given; nobody else gets that host."""
    orch = firewall.GITHUB + ((_hostname(control_host),) if control_host is not None else ())
    return {"ci": firewall.LANES["ci"], "exec": firewall.LANES["exec"], "orch": orch}


def _port(dns_port: object) -> int:
    if isinstance(dns_port, bool) or not isinstance(dns_port, int) or not 1024 <= dns_port <= 65535:
        raise ValueError(f"dns_port must be an int from 1024 to 65535, got {dns_port!r}")
    return dns_port


def _check_uids(uids: dict[str, int]) -> dict[str, int]:
    if set(uids) != set(LANE_OF):
        raise ValueError(f"need exactly the accounts {sorted(LANE_OF)}, got {sorted(uids)}")
    for name, uid in uids.items():
        if isinstance(uid, bool) or not isinstance(uid, int):
            raise ValueError(f"uid for {name} must be a number, got {uid!r}")
        if uid == 0:
            raise ValueError(f"uid for {name} is root (0); refusing to put root in a sandbox lane")
        if uid < 0:
            raise ValueError(f"uid for {name} must be positive, got {uid}")
    if len(set(uids.values())) != len(uids):
        raise ValueError("two accounts share a uid, so they would share a lane")
    return uids


def render_nft(uids: dict[str, int], dns_port: int = DEFAULT_DNS_PORT) -> str:
    uids = _check_uids(uids)
    port = _port(dns_port)
    blocked = ", ".join(firewall.BLOCKED_V4)
    lane_names = ("ci", "exec", "orch")
    out = [
        "table inet apx",  # declare, then delete, then redefine: reloading the file replaces the table in one transaction
        "delete table inet apx",
        "table inet apx {",
    ]
    for lane in lane_names:
        out += [
            f"  set {lane}_v4 {{",
            "    type ipv4_addr",
            "    flags timeout",
            f"    timeout {SET_TIMEOUT}",
            "  }",
            "",
        ]
    out += ["  chain output {", "    type filter hook output priority 0; policy accept;"]
    for name in sorted(LANE_OF):
        out.append(f"    meta skuid {uids[name]} jump lane_{LANE_OF[name]}")
    out += ["  }", ""]
    for lane in lane_names:
        out += [
            f"  chain lane_{lane} {{",
            "    ct state established,related accept",
            f"    ip daddr 127.0.0.1 udp dport {port} accept",
            f"    ip daddr 127.0.0.1 tcp dport {port} accept",
            f"    ip daddr @{lane}_v4 ip daddr != {{ {blocked} }} tcp dport 443 accept",
            "    reject",
            "  }",
            "",
        ]
    members = ", ".join(str(u) for u in sorted(uids.values()))
    out += [
        "  chain dns {",
        "    type nat hook output priority -100; policy accept;",
        f"    meta skuid {{ {members} }} udp dport 53 redirect to :{port}",
        f"    meta skuid {{ {members} }} tcp dport 53 redirect to :{port}",
        "  }",
        "}",
    ]
    return "\n".join(out) + "\n"


def render_dnsmasq(control_host: str | None = None, upstream: str = "9.9.9.9", dns_port: int = DEFAULT_DNS_PORT) -> str:
    port = _port(dns_port)
    try:
        up = ipaddress.IPv4Address(upstream)
    except (ipaddress.AddressValueError, ValueError) as e:
        raise ValueError(f"upstream must be an IPv4 address, got {upstream!r}") from e
    by_host: dict[str, list[str]] = {}
    for lane, names in lanes(control_host).items():
        for h in names:
            by_host.setdefault(h, []).append(lane)
    hosts = sorted(by_host)
    lines = [
        "# generated by autopilot.apx.nftrules; do not edit",
        "listen-address=127.0.0.1",
        "bind-interfaces",
        f"port={port}",
        "no-resolv",  # no default upstream: a name not listed below gets no answer
        "no-hosts",
    ]
    lines += [f"server=/{h}/{up}" for h in hosts]
    lines += ["nftset=/{}/{}".format(h, ",".join(f"4#inet#apx#{lane}_v4" for lane in sorted(by_host[h]))) for h in hosts]
    return "\n".join(lines) + "\n"


def _uid_arg(text: str) -> tuple[str, int]:
    name, sep, num = text.partition("=")
    if not sep or not num.isdigit():
        raise argparse.ArgumentTypeError(f"expected NAME=UID with a number, got {text!r}")
    return name, int(num)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="autopilot.apx.nftrules")
    sub = p.add_subparsers(dest="what", required=True)
    n = sub.add_parser("nft", help="print the nftables ruleset")
    n.add_argument("--uid", action="append", type=_uid_arg, default=[], metavar="NAME=UID")
    n.add_argument("--dns-port", type=int, default=DEFAULT_DNS_PORT)
    d = sub.add_parser("dnsmasq", help="print the allowlist resolver config")
    d.add_argument("--control-host")
    d.add_argument("--upstream", default="9.9.9.9")
    d.add_argument("--dns-port", type=int, default=DEFAULT_DNS_PORT)
    a = p.parse_args(argv)
    try:
        if a.what == "nft":
            text = render_nft(dict(a.uid), a.dns_port)
        else:
            text = render_dnsmasq(a.control_host, a.upstream, a.dns_port)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
