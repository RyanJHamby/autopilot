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

## Log (append below)

- 2026-10-21: file created. `gh api repos/actions/*` allow rule added to `~/.claude/settings.json`; denial persisted
  in the same session.
