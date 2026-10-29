# Raspberry Pi runner: handoff (paused 2026-10-28)

Pick this up whenever. Nothing here is urgent: the Pi is an optional extra compute host for the secure compute fabric (see `docs/fabric.md` and the plan in `~/.claude/plans/groovy-strolling-scott.md`). Autopilot runs fine on GitHub Actions without it.

## Where we stopped

- Hardware: Raspberry Pi 4 Model B Rev 1.4, 4 GB RAM, 29 GB microSD.
- The SD card was reflashed from the Mac with Raspberry Pi Imager v2.0.12:
  - OS: Raspberry Pi OS Lite 64-bit
  - hostname `ap-runner`, username `ap-19032`
  - SSH on, key-only, public key = `~/.ssh/ap-runner.pub`
  - Raspberry Pi Connect: off
  - **Wi-Fi: left blank on purpose** (planned to use Ethernet)
- `ssh -i ~/.ssh/ap-runner ap-19032@ap-runner.local` hangs. Cause: no Ethernet cable and no Wi-Fi configured, so the Pi is not on the network. Nothing is broken.
- The Pi's old install (desktop OS, user `pi`, hostname `raspberrypi`) is gone after the reflash.
- Ryan does not use Ethernet, so the next step is Wi-Fi.

## To do next (Ryan, about 15 min)

1. Check the router for a **guest network** setting. Check that guests cannot see other devices. If there is no guest network, or it can still see your devices, tell Claude. Then prefer the Oracle VM for anything untrusted.
2. Put the SD card in the Mac, reopen Raspberry Pi Imager, and reflash with the same settings as above, except:
   - Wi-Fi page: enter the home network name and password, choose SECURE NETWORK. The password goes straight into Imager and Claude never sees it.
   - Localisation: set the country. Wi-Fi will not turn on without it.
3. Eject the card (Finder, then eject; or `diskutil eject /dev/diskN`). Put it in the Pi and power on. Wait 2-3 minutes.
4. Tell Claude. It will find the Pi and SSH in with `~/.ssh/ap-runner`.

## After SSH works (Claude does these)

Read-only checks first:
- `/dev/kvm` present? (Pi 4 KVM is flaky; if absent, use gVisor or rootless Podman.)
- cgroup v2 and memory controller on
- SSH config (key-only, no root, no password)
- listening ports
- `vcgencmd get_throttled` (power/undervoltage) and firmware version

Then hardening, in this order:
1. OS updates, unattended security upgrades, SSH hardening, no password login.
2. Install rootless Podman, and gVisor if there is no KVM.
3. Render the firewall with `src/autopilot/fabric/firewall.py`, check it with `nft -c -f` BEFORE loading it (nft syntax is still unverified), then load it.
4. Run `src/autopilot/fabric/redteam_probe.sh` on the Pi, never on the Mac. Every attack in it must FAIL.
5. Move the Pi to the router's guest network and re-run the probe from there. Confirm it cannot reach the Mac.
6. Only then register it as a runner (JIT, ephemeral, one job each). The JIT config needs a broad repo credential. It lives on the controller only, never inside a sandbox, and the Pi never holds admin-level GitHub credentials.

## Security rules that still apply

- No GitHub admin token, SSH keys to other machines, or Tailscale on the Pi.
- Default-deny egress in both directions. Allowed: GitHub (and Anthropic for the exec lane, registries for the CI lane).
- Ephemeral per-job sandbox, secretless except the main-only `autopilot-exec` Environment lane.
- Never use the Pi for anything in the no-outbound rule (no Slack, email, calendars, social).
- Only autopilot, drillpad-workspace and stencil repos are in scope.
- Be honest about what it proves: "no known path to LAN or secrets, tested every run", never "100% protected".

## Using the SD card and Pi day to day

- Always shut the Pi down cleanly (`sudo shutdown -h now`, wait for the green LED to stop) before removing power. Pulling power is the main cause of SD corruption.
- Eject the card from the Mac before removing it. Do not leave it mounted.
- Budget SD wear: a 250 GB USB SSD booting the Pi (Crucial MX500 in a UASP enclosure, or SanDisk Extreme or Samsung T7) is the long-term fix for power-loss and wear problems. Under $10/yr in electricity.

## Fallback

If the home network cannot isolate the Pi, skip it. Use an Oracle Cloud Always Free ARM VM instead (VM.Standard.A1.Flex, 4 OCPU / 24 GB, no LAN exposure; gVisor, no KVM). Ryan said "yes, set up both" earlier; this is the other half.

## Open items that do not depend on the Pi

- Private-repo Actions minutes are capped; nothing can run until the spending limit is raised or the Nov 1 reset.
- Merge open autopilot PRs: #79 (keep-alive), #82 (automerge no-op skip), #83 (Environment-gated secret + redteam-secrets probe), #84 (fabric firewall + controller).
- Add the token as an Environment secret (`CLAUDE_CODE_OAUTH_TOKEN` in `autopilot-exec`) after a fresh `claude setup-token`, using `read -rs` into `gh secret set`. Never paste it.
