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
