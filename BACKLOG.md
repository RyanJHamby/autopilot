# autopilot backlog

Specs live in `specs/` (template: `specs/_TEMPLATE.md`; check with `ap handshake specs/<id>.md`). Each has machine-checkable
acceptance commands, so an agent can be dispatched on it. **Agent-safe** = periphery only. **Human-only** = anything on the
guard path: agents never edit these, they can only propose through a PR the owner reviews line by line.

## Agent-safe (specs ready)
| spec | what | tier |
|---|---|---|
| report-cost | run-points per merged PR in `ap report` | 1 |
| ap-digest | `ap digest` markdown summary for the owner | 2 |
| ap-upgrade | safe kit-sha bump across central repos | 2 |
| inbox-page | control-plane Inbox of open agent PRs | 2 |
| scorecard-ui | outcome numbers in the portfolio (hold: needs a human migration first) | 2 |

## Human-only (guard path; never delegated)
- Stencil onboarding: secret, Claude App install, central migration PR, ruleset, enable (after 5pm ET 2026-10-16).
- Failure-retro workflow and `lessons.md` convention (touches workflows and agent prompts).
- Weekly auditor role and monthly bench harness (workflows, prompts, model routing).
- Runner adapter interface and second runner (Codex or open weights) incl. red-team round.
- Promotion of auto-merge classes (a loosening; `ap report` suggests, owner decides).
- Anything in: `kit/runtime/{guard,gate,tier,automerge,demote,handshake}.py`, `kit/workflows/**`, `kit/callers/**`, `policy/**`,
  `apps/control-plane/{proxy.ts,lib/auth.ts,lib/githubApp.ts,lib/levers.ts,supabase/**}`.

## Parked by the owner
order-book-engine, tokenomics-bench, drillpad (public), stock-screener, fillcast; Zonevex restart pending the owner's docs.
