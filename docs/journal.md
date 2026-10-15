# autopilot: engineering journal

Dated notes on what I tried, what happened, and why I made each call, including
the dead ends. Entries are appended with `pow log` and `pow run`, so dates match
commit history. Raw outputs for any number quoted in the README live in
[`results/`](../results/).

## 2026-10-13 23:02 EDT (at 8b2614b)

Chose GitHub Actions (not claude.ai routines) as primary runtime: routines attach all claude.ai connectors (Gmail, Calendar, Todoist, Asana) by default and use them unprompted, which violates the no-outbound-action rule. Gate counts agent-exec.yml runs from GitHub itself instead of a committed ledger so an agent cannot forge its own budget.

## 2026-10-14 09:02 EDT (at be75af1)

Built ap CLI + repo templates. Found ~/dev/drillpad is the drillpad-workspace repo, so ap resolves repo identity from the git remote, not the directory. Open verification items V1-V4 listed in README; the pilot must settle them before wave 1.

## 2026-10-15 08:05 EDT (at e673090)

gate counted skipped/cancelled agent-exec runs toward the daily cap; smoke issue #8 was blocked at 2/2 with zero real runs. Fixed to exclude them; failures still count (conservative).

## 2026-10-15 08:24 EDT (at 4b7cc82)

smoke #8 first real run: action rejected github-actions actor (needs allowed_bots), then model call died in 2s with is_error and no usage, message hidden by show_full_output=false. Added AUTOPILOT_DEBUG var switch.

## 2026-10-15 10:33 EDT (at 0381f97)

First real agent run on #8: token ok after clipboard mixups (secret held command text); agent obeyed constitution and commented needs-human instead of forcing it. Blocker: mcp__* deny blocked github_file_ops (the signed-commit path). Fix: allow commit_files, specific mcp deny families, no plain git commit. Log shows only github_file_ops MCP exists in the runtime - no connectors.
