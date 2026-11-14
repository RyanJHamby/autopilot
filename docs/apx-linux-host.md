# The apx host on Linux (host move, stage 1)

Why: apx runs pull-request code and model output. On a Mac that also holds personal files, its isolation is three accounts on a shared kernel and disk, and `pf` cannot do a
per-host allowlist. This page is the runbook for the replacement: a small always-on Debian or Ubuntu server that holds **nothing but apx's own secrets**, with a real egress
allowlist, rebuilt from a script. It does not replace [apx-runbook.md](apx-runbook.md) for day-to-day operation or [apx-compromise.md](apx-compromise.md) for incidents; it
replaces the Mac install steps. [apx-host-move.md](apx-host-move.md) is still the rule for the cutover: **never two live hosts.**

No provider name, hostname or address belongs in this public repo. Keep those in your private notes.

## What was verified, and where

| Claim | Verified | Not verified |
|---|---|---|
| The egress rules refuse everything except each lane's own names on 443 | Real Linux kernel (linuxkit 6.10, nftables 1.1.3, dnsmasq 2.91) in a throwaway container with only `NET_ADMIN`: `scripts/linux-egress-test.sh`, 42 checks, each "blocked" case paired with a control, and broken rules make it fail | The VPS's own kernel and provider network |
| `bootstrap.sh` builds the accounts and layout, is idempotent, and the sandbox accounts cannot reach apx's files or become apx | A Debian container: `scripts/linux-bootstrap-test.sh`, including negative controls that open the split on purpose | A real server image, real systemd ordering, sshd |
| The probe on the real host catches a leak | The container, against the real internet, with a deliberately opened lane | The VPS itself: **run `egress-probe.sh` there** |
| The units are syntactically valid | `systemd-analyze verify` in the container | They have never been started under a running systemd |
| dnsmasq works as an unprivileged account holding only `CAP_NET_ADMIN` | Container, via `setpriv` ambient capabilities | The same under `AmbientCapabilities=` in systemd |
| PR code cannot read the job's parent environment, `apx-ci` cannot sudo elsewhere, a suspended App kills its minted tokens, a `setup-token` token can be revoked | Nothing | All four are still on [apx-compromise.md](apx-compromise.md)'s unverified list |

Anything in the right-hand column stays "unverified" until you have run it on the server.

## What the allowlist does not close

- Names the allowlist permits are reachable on 443 by design. Their addresses are shared with other customers of the same hosts, so an attacker with code execution in a lane can
  still talk to GitHub (for example, to push to a repo they control if a token allowed it). The 1-hour, single-repo, read-only token is the control that matters there, not the firewall.
- **Loopback, unprivileged ports (a deliberate trade-off).** Repo test suites start local servers and connect to `127.0.0.1`, so the `apx-ci` and `apx-agent` lanes may open TCP
  to any port from 1024 up on `127.0.0.1` (IPv4 only). Code running in those lanes can therefore reach every service the host has listening on `127.0.0.1` at such a port. Still refused:
  privileged loopback ports (sshd on 22 and the like), UDP on loopback other than the allowlist resolver, every other `127.x` address, all IPv6 (so `::1`), and everything the `apx`
  orchestrator account does on loopback beyond the resolver (that lane got no new rule). DNS is unchanged: port 53 from the three accounts is still redirected to the resolver.
  To see what is exposed, list the listeners and look at the ones bound to `127.0.0.1` (or `0.0.0.0`) at port 1024 or above: `sudo ss -ltnp`. The bootstrap installs no loopback service
  except the allowlist resolver (dnsmasq on `127.0.0.1:5354`); anything else there is something you added, so give it its own authentication or move it to a Unix socket.
- A subdomain of an allowed name resolves if the name's real DNS answers it. That is only a channel to whoever controls that zone, which for these names is not an attacker.
- PR code and apx share a kernel. A local privilege-escalation bug could reach the App key. A per-job sandbox (rootless podman or gVisor) is the later answer (stage 2, below).
- The Claude token is tied to your plan; a hard-capped API key for the executor is worth deciding at provisioning.

## Steps

### 1. You: buy and lock down the server (nothing here is done by an agent)

Small x86 VPS, Debian 12 or Ubuntu 24.04, about 4 vCPU, 16 GB RAM, 40 GB disk (my estimate from the preflight thresholds, not a measurement). Create your own admin
account with your SSH key, turn on the provider's firewall to allow SSH from your own IP only, and nothing else inbound (apx polls; it has no webhook port).

Many small VPS images ship with **no swap**. Without it, a memory spike kills a process outright (the OOM killer) instead of slowing
it down, and "heavy swap" can't serve as a resize signal. On a 12 GB box a 4 GB swap file with `vm.swappiness=10` (used only under real
pressure) is enough. As your admin account:

```
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/90-swappiness.conf
```

Check with `free -h` (Swap: 4.0Gi) after a reboot. Verified on the first real Linux host on 2026-11-14.

### 2. Preflight (read-only)

```
git clone https://github.com/RyanJHamby/autopilot.git && cd autopilot
bash deploy/linux/preflight.sh
```
Fix every FAIL. `node`, `npm` and `uv` WARNs are handled in step 5.

### 3. Bootstrap

```
DRY_RUN=1 ADMIN_USER=<your admin account> bash deploy/linux/bootstrap.sh     # preview, changes nothing
sudo ADMIN_USER=<your admin account> bash deploy/linux/bootstrap.sh          # do it; add CONTROL_HOST=<name> if a control plane exists
```
It refuses to touch SSH unless your account already has a key, so it cannot lock you out. It starts the egress rules and the resolver, and **installs but does not enable** the
apx and updater timers. Run it again any time: a second run changes nothing.

### 4. Secrets (new ones; never copied from the old host)

1. GitHub > the `autopilot-apx` App > **Generate a private key**. Do **not** delete the old key yet.
2. Copy it over SSH once, then delete it from your laptop:
   ```
   scp new-app.pem <you>@<server>:/tmp/app.pem
   sudo install -m 600 -o apx -g apx /tmp/app.pem /home/apx/.apx/app.pem && sudo shred -u /tmp/app.pem
   ```
3. Model token: run `claude setup-token` on your laptop, then on the server, as your admin account (the token is read without echo, so it is never in shell history or a process list):
   ```
   read -rs T < /dev/tty; printf '%s' "$T" | sudo install -m 600 -o apx-agent -g apx-agent /dev/stdin /home/apx-agent/.apx/claude-oauth; unset T
   ```
4. `/home/apx/.apx/apx.env` (as `apx`; paths and ids only, no secret inside). Start from this, with all three repos' installation ids:
   ```
   APX_APP_ID=<app id>
   APX_KEY_PATH=/home/apx/.apx/app.pem
   APX_INSTALLATIONS=RyanJHamby/autopilot=<installation id>
   APX_KIT_REPO=RyanJHamby/autopilot-kit
   APX_KIT_REF=<an approved kit sha, 40 hex>
   APX_CI_USER=apx-ci
   APX_AGENT_USER=apx-agent
   ```
   Shadow mode is on until `APX_SHADOW=0` is added. Start with `autopilot` only; add the other repos later.

### 5. Toolchains (your decision; the script installs none of them)

The sandbox accounts can only reach GitHub, the package registries and (agent only) the model API, so install tools as your admin account and copy them in.
`uv` is needed in `/home/apx-ci/.local/bin` (`clang++` and `rustc` for `drillpad-workspace`: see host tools below); the `claude` CLI is needed at `/home/apx-agent/.local/bin/claude`. Pin exact
versions and verify checksums yourself; I have not run these installs on a server, so treat the preflight and doctor as the test.

**Node is per repo.** Stencil's CI needs Node 20 and autopilot's needs Node 22, so there is no single `node` on the sandbox PATH. Which repo uses which is data in
`src/autopilot/apx/repo_toolchains.json` (`"RyanJHamby/stencil": ["node@20"]`). For each job, apx puts that repo's directory first on the sandbox PATH, so `node`, `npm` and
`npx` come from it (npm's own `#!/usr/bin/env node` line resolves through the same PATH). A repo with no entry (today `drillpad-workspace` and the private repos) keeps the default PATH.
`node@20` means the directory `/srv/apx/toolchains/node-20/bin`; an entry with a full version, `node@20.18.1`, means `node-20.18.1`. If a declared directory is missing the repo's
checks fail before the sandbox starts, with a message naming it; nothing falls back to another Node. Only the sandboxed lane does this: with no `APX_CI_USER` the checks run as `apx`
on its own PATH.

Install each one as your admin account (never `apx-ci`), from the official tarball, with the checksum verified. No installer script is piped into a shell, and I have written no
checksum here because I have not checked one: you take it from the release's own `SHASUMS256.txt`.

```
V=<the exact Node version you chose for this line, after reading its release notes>
case "$(uname -m)" in x86_64) A=x64 ;; aarch64) A=arm64 ;; *) echo "unsupported: $(uname -m)"; false ;; esac
cd "$(mktemp -d)"
curl -fsSLO "https://nodejs.org/dist/v$V/node-v$V-linux-$A.tar.xz"
curl -fsSLO "https://nodejs.org/dist/v$V/SHASUMS256.txt"
curl -fsSLO "https://nodejs.org/dist/v$V/SHASUMS256.txt.sig"
```
1. Check the signature on the checksum list: `gpg --verify SHASUMS256.txt.sig SHASUMS256.txt`, against a release signing key you imported from the Node.js project's own
   published list of release keys (`nodejs/release-keys`). Compare the key fingerprint with that list yourself; a "good signature" from a key you have not matched proves nothing.
2. Check the tarball against the list: `grep " node-v$V-linux-$A.tar.xz\$" SHASUMS256.txt | sha256sum -c -` must print `OK`. Write the version and the checksum you verified in your
   private notes, not in this repo.
3. Unpack it root-owned, so the sandbox accounts can run it but not change it:
   ```
   sudo install -d -m 755 -o root -g root /srv/apx/toolchains
   sudo mkdir /srv/apx/toolchains/node-<MAJOR>          # stops if it exists: never unpack over a toolchain in use
   sudo tar -xJf "node-v$V-linux-$A.tar.xz" -C /srv/apx/toolchains/node-<MAJOR> --strip-components=1 --no-same-owner
   sudo chown -R root:root /srv/apx/toolchains/node-<MAJOR> && sudo chmod -R go-w /srv/apx/toolchains/node-<MAJOR>
   ```
   Do this twice: `node-20` with a 20.x version (for stencil) and `node-22` with a 22.x version (for autopilot).
4. Try it as the sandbox account: `sudo -u apx-ci /srv/apx/toolchains/node-20/bin/node --version` (and 22).
5. Run the preflight again with `apx.env` loaded (`set -a; . /home/apx/.apx/apx.env; set +a; bash deploy/linux/preflight.sh`). For every repo in `APX_INSTALLATIONS` or
   `APX_PRIVATE_CI` it fails if the directory is missing, the binary is not there, `node --version` is not the declared version, or the directory or binary is group- or
   world-writable. (Before `apx.env` exists it only says it skipped the check.)

To change a version later, unpack the new one next to the old (`node-<new>`), change the entry in `repo_toolchains.json` in a PR, and remove the old directory once nothing declares it.
The sandbox still sees no secrets from this: the directories sit outside every account's home, hold no credentials, and the job's environment is still the same short allowlist.

**Host tools per repo.** Beyond Node, each repo's CI needs tools from the host itself. Which ones is data: the `"tools"` list of a private repo's entry in
`src/autopilot/apx/repo_ci.json` (repos in `APX_PRIVATE_CI`), and `"repos"` in `src/autopilot/apx/host_tools.json` for the autopilot-managed repos, whose own
`.autopilot/repo.yaml` lists commands but not tools (`drillpad-workspace` needs `clang++` and `rustc`, `stencil` needs `node`, `npm` and `npx` from its toolchain).
Where being on the PATH is not enough, `"probes"` in the same file holds a command that must succeed, per tool, for every repo that declares it: `gitleaks git --help` must show
the `git` subcommand (Ubuntu's apt gitleaks 8.18 runs but has none), `clang++` must compile, link and run a one-line C++20 program with `-fsanitize=undefined`, and `rustc` must
accept `--edition 2021`. The doctor (step 6) runs these as `apx-ci`, on the same PATH that repo's sandbox job gets, and prints one FAIL per repo and tool with the install hint.
To add a tool or a probe, change the data in a PR; no code names a repo.

- `clang++`: `sudo apt-get install clang libclang-rt-dev`. On Ubuntu 24.04, `clang` alone does not bring the UBSan runtime, so the probe fails to link until
  `libclang-rt-dev` is there. Install from apt, into `/usr/bin`: drillpad-workspace runs its compilers with `PATH=/usr/bin:/bin:$HOME/.cargo/bin`, so a copy only in `/usr/local/bin`
  would pass the doctor and still fail its tests (`src/drillpad/runner/_proc.py` in that repo).
- `rustc`: `sudo apt-get install rustc` (also `/usr/bin`, for the same reason).
- `gitleaks`: not from apt. As your admin account, download the release tarball for your architecture and its checksums file from the gitleaks project's GitHub releases page,
  check the tarball with `sha256sum -c` against that file (`grep` the tarball's line into it, as for Node above), then
  `sudo install -m 755 -o root -g root gitleaks /usr/local/bin/gitleaks`. Write the version and checksum you verified in your private notes, not here.
  `gitleaks git --help` as `apx-ci` must show `gitleaks git` in its usage.

### 6. Doctor, then shadow

```
sudo -u apx -H sh -c 'set -a; . /home/apx/.apx/apx.env; set +a; PYTHONPATH=/srv/apx/current/src /srv/apx/venv/bin/python -m autopilot.apx.daemon --doctor'
sudo bash deploy/linux/egress-probe.sh
```
Both must be clean before anything is enabled. The doctor's `<repo>: host tool <tool>` lines are the per-repo host tools above. (In the container test, the doctor's sandbox checks passed on real Linux, and its only failure was the missing `claude` CLI, which step 5 is for.) The probe tries to break out as each sandbox account (private and metadata addresses, an arbitrary public host, IPv6, SSH to GitHub, DoT, another
resolver, and loopback: a privileged port and `::1` must be refused, an unprivileged IPv4 port must work for `apx-ci` and `apx-agent` and stay refused for `apx`, using throwaway listeners the probe
starts and stops itself) and also requires the allowed path to work, so a refusal cannot mean "no connectivity". Then:
```
sudo systemctl enable --now apx.timer apx-updater.timer
journalctl -u apx.service -f
```
The updater runs dry until you add a drop-in (`systemctl edit apx-updater.service`) that sets `Environment=APX_UPDATE_LIVE=1` and passes `--live`. Stop adoption any time: `touch /srv/apx/HOLD`.

### 7. Cut over from the Mac (you cannot reach the Mac, and that is fine)

The Mac only acts while it holds the old App key and token, and the server has new ones, so revoking the old ones retires the Mac whether or not it is still running.

1. When the server's shadow output looks right on `autopilot`, set the pause variable on the three repos for the few minutes of the switch (`gh variable set AUTOPILOT_PAUSED --body true --repo <repo>`), which closes the window where both hosts could act.
2. In `apx.env` set `APX_SHADOW=0` (and enroll the other repos, one at a time). The file is read at the start of every pass, so no restart is needed.
3. Delete the **old** private key in the App's settings. From then the Mac's copy is dead. Revoke the old model token in your Claude account settings (I have not verified the exact menu).
4. Delete `AUTOPILOT_PAUSED` for one repo, watch a pass, then the rest.
5. A week with no problems is the done-condition (backlog X1). Stencil is enrolled only after the probe is green on this server.

If the new server misbehaves: `sudo DO=1 bash deploy/linux/retire.sh` stops its timers (it previews without `DO=1`); it deletes nothing and leaves the egress rules running.

## Operating it

- Stop immediately: `sudo systemctl disable --now apx.timer apx-updater.timer` (or `retire.sh`). Status: `systemctl list-timers 'apx*'`, `journalctl -u apx.service`.
- Fail closed: `apx.service` and `apx-updater.service` `Require=` the rules and the resolver, so if the rules fail to load, apx does not run.
- Egress rules changed? Re-run `bootstrap.sh`; it re-renders, checks with `nft -c`, and reloads. The resolver config is only read on start, so the script restarts it.
- Moving to a newer release by hand (while the updater is still in dry-run), with `SHA` set to the full commit id of a commit on `main`:

  ```
  sudo APX_SHA=$SHA ADMIN_USER=$ADMIN_USER bash deploy/linux/bootstrap.sh
  sudo bash deploy/linux/egress-probe.sh
  ```

  With `APX_SHA` set, bootstrap hands the release to `deploy/linux/release.sh` before it renders the rules. That script fetches `main` into
  `/srv/apx/autopilot` and moves its `main` there, fetches into `/srv/apx/updater` (which is cloned from that clone), and refuses a sha that is
  not on `origin/main`. It builds `releases/$SHA` aside and renames it in, refuses if the release's `HEAD` is not `$SHA` or its tree is
  dirty, checks the updater out at `$SHA`, and only then switches `current` (a temp link, then `mv -T`), so `current` never points at a
  missing directory. The old target is kept as `/srv/apx/previous`, and the rollback is printed: the same bootstrap command with the old sha.
  Any refusal stops bootstrap before the rules are touched and leaves `current` as it was. `DRY_RUN=1` prints the steps. Check that the
  probe ends `sealed`. Without `APX_SHA`, bootstrap still never moves an existing `current`. Run bootstrap from a checkout new enough to have `release.sh`.

  Fallback, by hand, if `release.sh` itself is in the way (each `git` and link step as apx, i.e. `sudo -u apx ...`): `git -C /srv/apx/autopilot fetch -q origin`,
  `git -C /srv/apx/autopilot checkout -q --detach $SHA`, `git -C /srv/apx/autopilot branch -f main origin/main`, `git -C /srv/apx/updater fetch -q origin`,
  `git clone -q --no-hardlinks /srv/apx/autopilot /srv/apx/releases/$SHA` and check it out at `$SHA`, check that
  `git -C /srv/apx/releases/$SHA rev-parse HEAD` prints `$SHA`, then `ln -sfn releases/$SHA /srv/apx/.current.new && mv -T /srv/apx/.current.new /srv/apx/current`,
  bootstrap without `APX_SHA` (it re-renders the rules and checks the updater out at the same commit), and the probe. On the first host
  (2026-11-14) skipping a fetch stopped bootstrap with `reference is not a tree`, and pointing `current` at a release directory before it
  existed left the host broken until the link was put back.
- Compromise: follow [apx-compromise.md](apx-compromise.md). Where it says `launchctl bootout`, use `systemctl disable --now apx.timer apx-updater.timer`; where it names `/Users/apx/...`,
  the paths here are `/home/apx/...`, `/home/apx-agent/...` and `/srv/apx`. It has not been rewritten for Linux yet, and its steps have never been drilled.

## Not built yet

- **An alert if apx stops.** The Mac's notifier is a local `osascript` popup and does nothing here. A dead-man's-switch (the host pings a service on every good pass; the service alerts you
  when pings stop) needs an outside service, so it is your choice and not assumed.
- **Stage 2 isolation:** a per-job rootless podman or gVisor sandbox, and moving the CI half to hosted runners (which would take all PR code off this host, at the cost of the Actions spending limit).
- **A hard-capped API key** for the executor instead of your plan's token.
- **The Mac host's own cleanup:** personal files on it are a separate job; this migration only retires its access.
