# apx GitHub App: setup (owner steps)

apx (the off-Actions executor, see the plan "OFF-ACTIONS EXECUTOR") needs its own GitHub App so that a mistake or leak
there cannot touch the control plane, the release flow or the rollout App. The agent (the model) never receives this
App's credentials; only the trusted committer and the check reporter use them.

## 1. Create the App (about 3 minutes, GitHub UI)

GitHub > Settings > Developer settings > GitHub Apps > New GitHub App.

| Field | Value |
|---|---|
| Name | `autopilot-apx` |
| Homepage URL | the autopilot repo URL |
| Webhook | **Off** (apx polls; no inbound anything) |
| Where can it be installed | Only on this account |

Repository permissions (everything else stays **No access**):

| Permission | Level | Why |
|---|---|---|
| Metadata | Read | required |
| Contents | Read and write | git data API: blobs, trees, commits, `agent/*` refs |
| Pull requests | Read and write | open PRs, read PR heads |
| Issues | Read and write | read `agent-ready` issues, add `needs-human` |
| Checks | Read and write | post the `guard` / `build` check runs |
| Variables (Actions) | Read | read `AUTOPILOT_ENABLED` / `AUTOPILOT_PAUSED` / `AUTOPILOT_HOLD_UNTIL` |

Never grant: Administration, Workflows, Secrets, Environments, Actions write, Members, Organization anything.
Without `Workflows`, GitHub itself refuses any push that changes `.github/workflows/**`, a second wall behind the guard.

## 2. Install it on exactly three repos

Install > Only select repositories > `autopilot`, `drillpad-workspace`, `stencil`. Nothing else, ever.

## 3. Private key

Generate a private key on the App page. It downloads once as a `.pem`.
- Keep it **only** on the executor host, mode `600`, owned by the executor's service user. Never in a repo, a chat, a
  ticket or a synced folder. apx reads the path from an environment variable; it never logs or copies it.
- Note the **App ID** and each **Installation ID** (Install page URL). Those are not secret.

## 4. Ruleset (do this before cutover, not now)

Pin required checks to this App so nobody else can post a passing `guard`:
`ap ruleset` currently pins only `{"context": name}`. The pin (`integration_id`) is added in a later PR that you merge;
until then Actions-posted checks keep working and apx posts under a non-required name (shadow mode).

## 5. Revoking

Suspend the App from its Install page, or `systemctl stop apx` on the host. Both stop everything immediately; the
Actions workflows remain as the fallback until they are disabled per repo.
