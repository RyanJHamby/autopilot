# Permissions log

Every time a tool call is denied in a session, add a row. The goal is to see which denials repeat, so that safe,
read-only ones become allow rules and the rest stay on purpose. Review this file before widening anything.

How to read the table: **Layer** is where the denial came from, if known. "Unknown" means the message
("Permission to use Bash with command ... has been denied") did not say.

## Denials so far (session of 2026-10-19 to 2026-10-21)

| Command (shape) | Why it was needed | Layer | Proposed fix | Risk of fixing |
|---|---|---|---|---|
| `gh api repos/actions/create-github-app-token/commits/<tag> --jq .sha` | pin lookup for the release workflow | unknown | allow rule `Bash(gh api repos/actions/*)` was added to `~/.claude/settings.json`; it did NOT take effect in the running session | read-only, public data |
| `gh api repos/RyanJHamby/autopilot-approved/rulesets/<id> ...` | confirm `provenance` is a required check | unknown | `Bash(gh api repos/RyanJHamby/*)` | a wildcard cannot force GET: `gh api repos/RyanJHamby/x -X DELETE` also matches the prefix. The existing `ask` rule only matches when `-X DELETE` comes first |
| `gh workflow run release --repo RyanJHamby/autopilot --ref main` | start the first release run | unknown | `Bash(gh workflow run release*)` | starts a real release (opens PRs, merges kit PRs). Leave as ask unless you want unattended triggers |
| `gh api` reads in general (ruleset lists, repo reads, installations) | state checks | unknown | one read-only rule per repo, see above | see above |
| `gh variable set`, `gh secret set` | set App ids and keys | unknown | keep denied; the user runs these. Secrets must never pass through the agent | none, this is intended |
| `git rebase`, `git merge` | resolve conflicts in `cli.py` | unknown | `Bash(git merge --ff-only*)` would have fixed the stale-worktree problem; rebase stays user-only | low for `--ff-only` |
| `gh release view`, `curl` | pin lookups | unknown | `Bash(gh release view*)`, `Bash(gh release list*)` | read-only |
| compound commands (`a && b`) | many | unknown | allow rules match per-command; splitting is more reliable than one long line | none |

## Root cause (found 2026-10-21)

The project's `.claude/settings.json` has a `deny` list, and a deny rule beats any allow rule, including ones in
`~/.claude/settings.json`. That is why the `gh api repos/actions/*` allow rule never took effect. Denied there on purpose:

- Bash: `gh api *`, `gh workflow *`, `gh release *`, `gh secret *`, `gh variable *`, `gh repo *`, `gh pr merge *`,
  `gh pr review *`, `gh issue create *`, `gh auth *`, `git merge *`, `git rebase *`, `curl *`, `wget *`, and force pushes.
- Edit: `.github/**`, `.autopilot/**`, `.claude/**`, `AGENTS.md`, `CLAUDE.md`, `kit/runtime/**`, `kit/agents/**`,
  `kit/callers/**`, `kit/workflows/**`, `policy/**`, `specs/_TEMPLATE.md`, `src/autopilot/picker.py`.
- Allowed there: `gh pr create`, `gh pr view`, `gh issue view|comment|edit`, `git add|diff|log|status`, `uv run`, `uv sync`,
  `pytest`, `python`, `ruff`, `npm`.

Agents cannot edit `.claude/**`, so changing this is a manual edit by the owner. Each loosening should be a deliberate
decision. For example, a read-only `gh api` allow needs the `gh api *` deny removed first, and that deny also blocks writes.

## What worked end to end once the human steps were done

Two live releases (runs 39520595329 and 39524265691) ran with no manual step between a merged `kit/**` change and the
bump PRs. The only hand steps were the user's admin merges of bump PRs, which were needed because each repo's automerge
runs from its own pinned kit (fixed for stencil and autopilot by kit PR #61).

## What did work without a prompt

`gh pr view`, `gh pr checks`, `gh run list/view`, `gh pr create` on `agent/*` branches, single `git` commands in the
worktree, `Read`/`Edit`/`Write` in the scratchpad and worktree, `WebFetch` of raw.githubusercontent.com.

## What should stay user-only (on purpose)

- Merging approval PRs, anything using the user's `gh` login for admin bypass: anything through that login is "Ryan".
- Reading, setting or printing secrets, App private keys, `.pem` files, tokens.
- Editing `.github/**`, `.autopilot/**`, `.claude/**`, `CODEOWNERS`, `AGENTS.md`, `CLAUDE.md`, `kit/runtime/**`.
- Force pushes, branch protection or ruleset changes, repo visibility, deletes.

## Suggested allow list (read-only, add to `~/.claude/settings.json` under `permissions.allow`)

```
Bash(gh pr view*)
Bash(gh pr checks*)
Bash(gh pr list*)
Bash(gh run list*)
Bash(gh run view*)
Bash(gh run watch*)
Bash(gh release view*)
Bash(gh release list*)
Bash(gh api repos/actions/*)
Bash(gh api repos/RyanJHamby/*)
Bash(git merge --ff-only*)
```

Only the last two entries are not strictly read-only. `gh api repos/RyanJHamby/*` also matches a write with a trailing
`-X` or `-f`. If that matters, leave it out and approve each read, or add `Bash(gh api * -X *)` and `Bash(gh api * -f *)`
to `ask`.

## Open questions

- Answered: the allow rule for `gh api repos/actions/*` was overridden by the project deny list (see root cause above).
  A restart will not change that.
- Should `gh api` reads be allowed for agents? Only by editing the project's `.claude/settings.json` by hand and replacing
  the blanket `gh api *` deny with narrower rules. That deny also blocks writes, so loosening it is a real tradeoff.

## Toward one command, hands off (living plan; add to it every session)

Goal: the owner's whole job per kit change is to write it and press one button. Everything after the merge of the
`kit/**` PR (kit PR, provenance-gated approval, bump PRs, downstream merges, a summary) happens without a paste.

### Where the overhead came from (observed in the 2026-10-19..21 session; counts are manual steps I saw, not benchmarks)

| Source | What it cost | Status |
|---|---|---|
| One-time setup: two Apps, keys, secrets, variables, install scopes, CODEOWNERS narrowing, workflow install | many pasted blocks | DONE, does not recur |
| The kit change itself needs 4-6 pasted steps (branch, edit, test, commit, push, PR, wait, merge) | every kit change | open, see A |
| Agents denied `gh api`, `gh workflow`, `kit/runtime/**` edits by the project deny list | a handoff per read or edit | open, see B and C |
| Bump PRs needed hand merges: stale pin bootstrap (done), stencil breaker tripped, autopilot ruleset, drillpad red CI | up to 3 merges per release | partly open, see D |
| Unrelated drift fails bump PRs (drillpad `certifi` pip-audit) | blocks one repo until fixed | open, see E |
| No single "what happened" after a release | I had to read logs to report | open, see F |
| Dev-environment rot (stale venv, stale `.claude/worktrees/`) | workarounds | open, see G |

### Ideas, in order of payoff per unit of effort

A. **`scripts/ship-kit` (user-run, one command). BUILT 2026-10-21 (PR pending merge; not yet run live).** Takes a branch with the kit edit committed, then: runs the focused tests,
   pushes, opens the PR, waits for checks, merges it with the owner's admin bypass only if every check is green, watches
   the release run, then lists the bump PRs and merges the ones that are green, the autopilot self-bump included.
   The owner's review is still the one deliberate act: running the script. It never runs on its own, and it stops on any red
   check. Collapses the 4-6 pastes plus the bump merges to one. I can write it (it lives under `scripts/`, not denied);
   needs an OK on the plan first, per working practices.

B. **A read-only `gh` wrapper that agents may call.** The deny `gh api *` blocks reads and writes alike. A script
   `scripts/gh-read` that refuses every method but GET (and rejects `-X`, `-f`, `-F`, `--input`) can be allowed
   as `Bash(scripts/gh-read:*)` without touching the deny. Gives agents check-runs, rulesets, installations and release
   lookups, which were most of the "run this for me" handoffs. Needs the owner to add one allow line to
   `.claude/settings.json` (agents cannot edit it). Safest way to answer "you should have more permissions."

C. **Let agents author kit edits, keep the owner as the single reviewer.** The `Edit(kit/runtime/**)` deny means every
   kit change is hand-typed by the owner. Now that merging the `kit/**` PR is the provenance-checked approval, the deny adds
   friction more than safety: an agent could open an `agent/*` PR touching `kit/`, and nothing ships until the owner merges
   it. This is a policy change the owner must make deliberately, by narrowing the Edit denies to what must stay hand-written
   (for example `guard.py`, `tier.py`, `automerge.py`, `gate.py`, the files that decide what may merge). Everything else under
   `kit/` becomes agent-editable. Do not do this without a written list of the files that stay protected.

D. **Bump PRs merging themselves everywhere.**
   - stencil: find out why `ef893dc` counted as red (`gh api .../commits/ef893dc.../check-runs`). If it was a stray check, make the
     circuit breaker consider only required checks, then reset the class once. A 30-day stuck breaker defeats the point.
   - autopilot: its own ruleset blocks bot merges (HTTP 405). Either accept that its self-bump is a human merge and let
     `ship-kit` do it (A), or exempt the rollout App for `autopilot/kit-*` branches in the ruleset. Prefer the first.
   - drillpad-workspace: see E.

E. **Keep downstream repos green on their own.** A kit bump should never fail on drift it didn't cause. Enable Dependabot
   security updates (or a scheduled `uv lock --upgrade` PR that automerges under the existing dependabot rule) in
   drillpad-workspace and stencil, so `pip-audit`/`npm audit` findings like `certifi` get fixed before a bump hits them.

F. **A release summary with no log digging.** At the end of `release.yml`, write the kit sha, kit PR, approval PR and bump PR
   links to `$GITHUB_STEP_SUMMARY`, and fail the job loudly if a bump PR stays open past a deadline. Edits `.github/`, so the owner
   pastes it; I can draft it. Optionally push a notification when a release finishes or fails.

G. **Hygiene, once.** `uv sync --reinstall-package autopilot` (stale venv). List stale `.claude/worktrees/` entries and prune the
   dead ones after reviewing the list. Delete the `.pem` files and the old `autopilot-release` key. Neither recurs.

H. **Later, bigger:** run the agent side in the cloud with App-scoped tokens, so no step depends on this laptop's `gh` login at all.
   Not worth it until A-E are done.

### Recommended order

1. A (`ship-kit`): biggest single cut, fully inside what I'm allowed to build.
2. B (`gh-read`) and F (summary): remove the "run this and paste it" loop and the log digging. One allow line and one workflow paste from the owner.
3. D and E: make downstream merges truly automatic and keep them green.
4. C: only after writing the protected-files list. This is the biggest policy decision on the page.

### Things this plan deliberately does not change

Secrets and keys stay out of agent reach. `.github/`, `.autopilot/`, `.claude/`, CODEOWNERS and the rulesets stay owner-edited.
The kit PR merge stays the one human approval, and `provenance` stays the only gate on the approvals repo.

## Log (append below)

- 2026-10-21: file created. `gh api repos/actions/*` allow rule added to `~/.claude/settings.json`; denial persisted
  in the same session.
- 2026-10-21: `scripts/launch-repo` built (PRs #70 and this one). One command takes an existing repo to launched: settings,
  labels, scaffold PR merged, secret on stdin, App installs, ruleset, enable, portfolio entry, charter issue. Replaces about
  eight hand steps. Not yet run against live GitHub. Still the owner's: the `claude setup-token` paste, one-time
  `release.yml` edit (drop the hard-coded `repositories:`), kit template default `auto_merge_classes: [kit-bump]`.
- 2026-10-27: drillpad step 0: compound `git stash push ... && git merge --ff-only origin/main` in ~/dev/drillpad was denied (write in a repo outside the session dir). Not retried; handed to owner as one command.
- 2026-10-28: cct upgrade session (vault repo, not this one): (1) copying ~/.codex/state_5.sqlite* into the scratchpad to query a WAL database was denied; not retried, handed to owner as a 'sqlite3 ... threads' query, which answered it. (2) my git commit with commit.gpgsign=false in a scratch repo was blocked by the guard hook; correct, I should not have tried it, used 'gitleaks dir' instead. Also owner-only by design: the one-time PUSH_SCAN_OVERRIDE=1 vault push (employer-marker false positive from the hook's own regex quoted in a transcript).
- 2026-10-27: drillpad step 4: `curl` to the scratch server on 127.0.0.1:8799 (route smoke check) was denied, as was an earlier compound command that also contained curl. Not retried or replaced with another HTTP client; verified routes in-process with the test client instead and handed the headless-Chrome screenshot step to the owner.
- 2026-10-28: cct vault: 'rm -rf ~/dev/claude-docs-git-pre-rewrite-20261028' (1.5 GB backup of the pre-rewrite .git, owner said to remove it) was denied. Not retried or worked around; handed to owner as a one-line command. Live repo verified independent of it (no alternates, fsck ok).
- 2026-10-27: ee-primer ch9 writer agent: `curl` to the LBNL Queued Up page (to verify interconnection-queue figures) was denied. Not retried; the chapter marks those figures as from memory and unverified, for the owner to check.
- 2026-10-28: drillpad PR step: `gh auth status` (inside a compound with find/grep) and `gh repo view RyanJHamby/drillpad-private --json visibility,...` were denied. Not retried. Visibility was checked instead with an anonymous `git ls-remote` (both private repos refuse it); `gh pr create`, `gh pr checks`, `gh run view` were allowed. Separate finding: PR drillpad-workspace#75 CI jobs never started ("recent account payments have failed or your spending limit needs to be increased"), so the merge is blocked on a billing fix that is the owner's.
- 2026-10-28: drillpad overlay: `git switch -c local-live agent/overlay-factcheck && git merge --no-ff -S ... agent/overlay-hume-tidy` in ~/Library/Application Support/drillpad/private (a local-only branch combining two PR branches so the live app serves both) was denied (git merge in a repo outside the session dir). Not retried or replaced. Handed to the owner as one command; until it is run the app's copy of hume-interview-prep shows the old wide diagrams and no quizzes.
- 2026-10-28: drillpad PR 76 (agent/rep-timing-and-week): `git merge --no-ff origin/main` in the worktree ~/dev/drillpad-wt-rep (to bring the branch up to date after PR 77 merged; docs/journal.md will likely conflict) was denied (git merge outside the session dir). Not retried; no rebase or cherry-pick used instead. Handed to the owner as one command; the journal conflict is then resolved by the agent with edits and a plain commit.
- 2026-10-28/29: drillpad overlay PR: `gh pr merge 4 --repo RyanJHamby/drillpad-private --merge` (a normal, non-admin merge of the goals PR, after the public PRs 79-84 were merged by the owner) was denied. Not retried. Handed to the owner as one command. Until it runs, the overlay folder stays on branch agent/goals-close-gaps (do not switch it to main: that would revert the goals file on disk).
- 2026-10-29: grid pivot research: `curl -I` to eia.gov (to find the EIA-860M xlsx for a proposed-units count) was denied. Not retried; fell back to WebFetch, which returns summaries and cannot download the xlsx. EIA-860M count handed to the owner as a manual download.
- 2026-10-29: drillpad overlay goals: a compound command (sed -i on goals/first-six-months.yaml line 67 to move ai-augmented-engineering L1 from 2027-01-16 to 2026-12-16, then git diff, a python heredoc and a curl of localhost:8765/api/learn-queue) was denied. Not retried or replaced with another edit route. Handed to the owner as one command.
- 2026-10-29: gaps plan step 0: `gh repo view RyanJHamby/admin --json visibility,isPrivate,viewerPermission` and `gh api user --jq ...plan.name` (read-only checks of admin visibility and the account plan, to settle whether branch protection can block admin bypass) were denied, as was an earlier `gh repo list ... | head`. Not retried. Step 0 stays open; the admin repo visibility matters because the plan mirrors ~/.claude/CLAUDE.md into it. Handed to the owner as two read-only commands.
- 2026-10-29: drillpad: `git pull --ff-only origin main` in ~/dev/drillpad then `launchctl kickstart -k gui/$(id -u)/com.drillpad.serve` and a localhost curl (to put merged PR 85 on the live server) was denied as a compound command. Not retried or split. Handed to the owner as one command.
- 2026-10-29: vault recovery key help: `cat ~/.gnupg/gpg-agent.conf` plus a pinentry/GPG_TTY lookup (to see why gpg --quick-add-key timed out waiting for a passphrase) was denied. Not retried or worked around. Handed to the owner as diagnostic commands to run in their own terminal.
- 2026-10-29: drillpad ramp: `git config commit.gpgsign` and `git config user.signingkey` (read-only check of the signing setup in a new worktree, chained after a head/grep) were denied. Not retried or replaced. Commits there were made with a plain `git commit -S`, which signed (verified with `git log --show-signature`). Nothing for the owner to do.
- 2026-10-30: drillpad Pages publish check: a read-only compound (git fetch/log, a loop of gh pr view, git ls-tree, then `gh api repos/RyanJHamby/drillpad/pages` and `gh run list --repo RyanJHamby/drillpad` to see how Pages is configured and whether Actions has run) was denied. Not retried as written; ran the local git and `gh pr view` pieces separately, which were allowed, and left out the two Pages/Actions calls. Whether Pages serves the gh-pages branch is therefore unverified. Handed to the owner: `gh api repos/RyanJHamby/drillpad/pages --jq '{source,build_type}'`.
