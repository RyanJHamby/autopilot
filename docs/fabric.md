# Secure compute fabric (self-hosted runners)

Status: components built and unit-tested; **nothing has run on a real host yet.** Plan and red-team notes: see the secure compute fabric plan.

## Pieces (all in `src/autopilot/fabric/`)
- `firewall.py`: renders the nftables ruleset and the dnsmasq allowlist per lane (`trusted`, `ci`, `exec`). Private ranges, link-local/metadata, CGNAT/tailnet and all IPv6 are dropped before any accept; default policy drop; the sandbox can reach only DNS on the host and tcp/443 to IPs the allowlisting resolver just resolved for a listed name.
- `ctl.py`: decides which sandbox to start for which queued job (in-scope repos only, one lane per job, per-lane and per-repo caps, JIT single-use runner body). Dry-run poller only; starting sandboxes is not implemented.
- `redteam_probe.sh`: runs inside a sandbox; every attack must fail (LAN, metadata, arbitrary hosts, DoH/DoT, DNS tunnelling, IPv6, host/credential exposure, pids limit, lane isolation) and the allowed paths must work. Exit status = number of leaks.

## Host bring-up checklist (not yet done)
1. Isolated network first (own VLAN/guest segment, router drops the segment's access to every other device). Without this, do not run untrusted code on a home host.
2. `python -m autopilot.fabric.firewall nft --lane ci > apfab.nft && nft -c -f apfab.nft` (**the ruleset syntax has not been checked by `nft` yet; `nft` is not installed on the dev machine**). Then load it and the dnsmasq file (`... dnsmasq --lane ci`).
3. Rootless podman + gVisor (`runsc`) per job, read-only rootfs, cgroup pids/memory/CPU limits, job timeout, no host mounts, no docker socket.
4. Run `LANE=ci redteam_probe.sh` inside a sandbox: must exit 0. Wire it to run weekly and on any change here.
5. Controller user and sandboxes are separate OS users; the controller holds the only credential able to register runners.

## Known weak points (be honest in reviews)
- **Registering repo runners needs the repository Administration permission.** That credential is broad (repo settings), so it must live only on the controller, never in a sandbox, and its App should be installed on the three in-scope repos only. A GitHub organization with org-level runner permission would be narrower; consider it later.
- The nft/dnsmasq files are untested against the real tools so far. A name allowed by the list can still resolve to a shared CDN address that other tenants use; this is why exec's list is tiny and the token is the only secret in that lane.
- A sandbox escape (kernel/hypervisor 0-day) is not prevented by any of this; the network segment is the backstop.
