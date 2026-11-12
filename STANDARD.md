# Project standard

Status: **v0 draft, standard version 1.** The rule list and labels are in
[`src/autopilot/standard/checks.yaml`](src/autopilot/standard/checks.yaml). Run them with `ap standard check REPO`, or
`ap standard check --portfolio` for every enabled repo. Every rule has a check. The engine runs from the CLI on a
machine and, offline, from a CI step in `ci.yml`.

This file says what a repo should have and how each rule is backed. It makes no claim that following it improves how
well agents work. Where a rule is judgment, it says so.

## How each rule is backed

| Label | Meaning | Can it fail a run? |
|---|---|---|
| `enforced` | CI or a ruleset blocks the change | Yes, and it blocks the merge |
| `audited` | `ap standard check` reports it when someone runs it | Yes, but nothing blocks a merge |
| `advisory` | Judgment, not enforced anywhere | No, it only warns |

The `fail`-level rules are the `enforced` ones: six from the start, then five day-0 rules and four capability-pack rules (all `since: 2026-11-10`, see "Phasing a
rule in" and "Capability packs"). They are enforced by the `ci.yml` step
`uv run ap standard check . --offline`, which exits non-zero when one of them fails. That step runs offline, so it
never asks GitHub anything. Two limits: nothing has yet run on GitHub Actions, so "enforced" is the design until a real
pull request shows the step blocking; and whether the step is a *required* status check depends on the ruleset, which
is an owner setting. A test checks that the CI step exists whenever any rule claims `enforced`.

A third limit, which applies to every `enforced` rule and matters most for a repo made by `ap new`: that CI step exists only
in autopilot's own `ci.yml`. A new repo's `ci.yml` runs `make check`, not `ap standard check`, so for it these rules are audited
when someone runs `ap standard check` or when `converge` runs, not blocked by CI. What actually stops a bad commit there is the
local hook and `make check`, which the day-0 rules verify are wired. The day-0 rules audit that wiring and nothing more: they
cannot tell whether a scan catches a secret (a scaffold test checks that with real gitleaks) or whether `make quick` does any work.

A result is `pass`, `fail`, `unknown`, `skip` or `waived`. `unknown` means the check couldn't be answered, for example
because `gh` isn't installed, the ruleset can't be read, or a workflow file doesn't parse. It is never counted as a pass,
and `--strict` makes it fail a level-`fail` rule. `skip` means the rule doesn't apply to this repo, and is still printed.
`waived` is a failure covered by a live waiver, below.

A rule's **level** says what a failing result does to the run: `fail` exits non-zero, `warn` prints. New rules start at
`warn` until the portfolio is clean, so adding a rule never breaks a repo overnight.

## The rules

| Rule | Level | Label | Applies to |
|---|---|---|---|
| `pinned-actions` | fail | enforced | all |
| `workflow-permissions` | fail | enforced | all |
| `no-privileged-triggers` | fail | enforced | all |
| `secret-exposed-workflows` | fail | enforced | all |
| `codeowners-cover-protected-paths` | fail | enforced | all |
| `no-tracked-secrets` | fail | enforced | all |
| `thin-claude-md` | warn | audited | all |
| `one-check-entrypoint` | warn | audited | all |
| `license-present` | warn | audited | public repos |
| `ruleset-present` | warn | audited | all |
| `hook-wired` | fail | enforced | all |
| `secret-scan-wired` | fail | enforced | all |
| `workflow-lint-wired` | fail | enforced | all |
| `dependency-cooldown` | fail | enforced | all |
| `install-scripts-off` | warn | audited | all |
| `standard-wired` | fail | enforced | all |
| `ui-no-vibe-tells` | fail | enforced | all |
| `payments-pack` | fail | enforced | all |
| `llm-pack` | fail | enforced | all |
| `deploy-pack` | fail | enforced | all |
| `db-pack` | fail | enforced | all |
| `auth-pack` | warn | advisory | all |
| `db-advisory-pack` | warn | advisory | all |
| `deploy-advisory-pack` | warn | advisory | all |
| `agents-md-budget` | warn | advisory | all |
| `how-this-was-built` | warn | advisory | all |
| `journal-present` | warn | advisory | all |
| `dependency-updates` | warn | advisory | all |
| `gitignore-present` | warn | advisory | all |
| `templates-present` | warn | advisory | all |
| `commands-documented` | warn | advisory | all |
| `security-policy` | warn | advisory | public repos |
| `contributing-present` | warn | advisory | public repos |

Each rule's reason and fix are in `checks.yaml`, which is the single source. A test fails if this table and that file
disagree.

## Which repos a rule applies to

`applies_to` is derived from keys that already exist in `policy/portfolio.yaml` (`public`, `data_class`). There is no
separate "repo kind" field, and this standard doesn't read a product's stage: stage belongs to the bets ledger, and
reading it here would create a second policy file.

A rule can also report `skip` when the repo has nothing for it to check. `dependency-updates` skips a repo with no
manifests and no workflows, and `one-check-entrypoint` skips a repo with no manifests, workflows or Makefile (a
docs-only repo, for example). A skip is shown as a skip, never as a pass, and a repo that has something to update or
run but no config or check still fails.

## Phasing a rule in: `since`

A rule can carry `since: YYYY-MM-DD` in `checks.yaml`. Its declared level binds only repos whose first commit is on or after
that date; older repos are **grandfathered to `warn`**. The failure is still printed, with a "grandfathered" note, so nothing is
hidden; it just can't fail a run. Fixing the repo clears it. This is how a new rule is strict for new repos from day one
without breaking an old repo overnight, and there is no per-repo field to forget.

How a repo's age is read, and the edge cases:
- Age is the author date of the repo's first commit (the earliest, if there are several roots).
- A directory with no commit yet, or one that is not a git repo of its own, counts as **new**. `ap new` leaves a repo in that
  state until its first commit, so a brand-new repo is strict from the start. A subdirectory never borrows a parent repo's age.
- A **shallow clone** counts as old, because it cannot see its real first commit and its boundary commit is recent. This keeps
  `converge`'s shallow audits from mistaking an old repo for a new one. It also means a very new repo audited through a shallow
  clone is grandfathered; audit it from a full clone to see its full level.
- A rewritten history changes a repo's age. The goal is to stop forgetting, not to resist someone rewriting their own repo.

## Capability packs

A repo that can take payments, call an LLM, run a deployment or hold a database must have the pack for that capability (sign-in and a real database in tests are advisory packs: they warn and never fail). The capability is read from the
repo's own content (`src/autopilot/standard/capabilities.py`), so the requirement appears the moment the capability does, with nothing to
remember or record. What each pack requires is in `src/autopilot/standard/packs.yaml`.

| Rule | Detected from | Requires |
|---|---|---|
| `payments-pack` | a payments dependency, a call to a payment API by URL, or a `STRIPE_*` env read | webhook signature check, event dedupe (or a decision record on idempotency), a threat model, a terms page, billing paths in CODEOWNERS |
| `llm-pack` | an LLM dependency, a call to an LLM API by URL, an `import`, or an `*_API_KEY` env read | when **hosted** (deployed, with users or payments): a dated spend-cap record, a kill-switch runbook, an eval suite; when there are users: a per-user limit |
| `deploy-pack` | `vercel.json`, a Dockerfile, `fly.toml`, `netlify.toml`, `render.yaml` | a health endpoint, error tracking, a rollback runbook |
| `db-pack` | a database dependency (Prisma, Supabase, SQLAlchemy and similar) or a migrations directory | a dated backup-and-restore record (`docs/gates/db-backups.md`), a migration runbook (`docs/runbooks/migrations.md`), a threat model |
| `auth-pack` (advisory) | a sign-in dependency (Clerk, Auth.js, Supabase Auth, and also `jsonwebtoken` or `bcrypt`) | a managed provider or a decision record, a rate limit or CAPTCHA, account deletion, a threat model |
| `db-advisory-pack` (advisory) | the same database signal | a real database in tests, seen as a compose file, a local Supabase config or a `testcontainers` module outside the test directories (the scanner never reads `tests/`) |
| `deploy-advisory-pack` (advisory) | the same deploy signal; most items only when the app is hosted (deployed, and people sign in or pay); the heartbeat item only when there are scheduled jobs (a `cron` directory or `crons` in `vercel.json`) | an uptime monitor record (dated), structured logs, a log-retention note, a dev/prod separation note, a gated-deploy note, a heartbeat ping for each scheduled job. Notes are self-attested. The heartbeat check is a word match, so a keep-alive that is called a heartbeat also passes |

Detection is scoped so a mention is not a capability: runtime dependencies only (not dev dependencies, optional extras or lockfiles), code
files only (not docs, tests, fixtures, examples, templates or agent config), comments and Python docstrings stripped, and a call needs a URL
with a scheme (a hostname in a sandbox allowlist is not a call). A call made with no SDK, such as Gemini by raw `fetch`, is still found.

Two kinds of item, and the difference matters:
- A **code** item is checked against the code: it passes only if the pattern, path or dependency is really there. It is a pattern, so it
  cannot tell a signature check that runs from one that is merely named (a `limit` test records that).
- A **record** item is **self-attested**. The repo can hold a note that a spend cap is set on each provider account; it cannot prove the
  cap exists. A record must exist, hold no placeholder text, and be long enough to say something; where it states an external fact it
  must carry a `Verified: YYYY-MM-DD` line, and it fails as stale after 180 days. That forces the question, dates the answer and asks
  again, and nothing more: a plausible filler record with a fresh date passes (a `limit` test records that too).

These rules carry `enforced` like the others, with the same third limit described above: for a repo made by `ap new`, nothing runs
`ap standard check` in CI, so the pack is checked when `make check` runs it, when `converge` runs, or when someone runs the standard.

## UI and landing pages

Partly enforced. The rule `ui-no-vibe-tells` (`since: 2026-11-11`, so strict for new repos and a warning for older ones) scans
UI source (css, html, tsx, jsx, vue, svelte) and fails on what a pattern can see: fonts, Lucide and sparkle icons, em dashes,
emoji and checkmark glyphs, pastel and pure-white colors, radial and purple gradients, glass, left stripes, large radii and
shadows, hover animations, three-column grids, "it's not X, it's Y", testimonials, and an email field with no privacy or terms
page. It cannot judge layout, whether a demo is real, or whether a testimonial is true: those are on the agent and the owner.
It applies to any landing page, marketing site, dashboard or app screen an agent builds. The goal is a UI that looks designed, not generated. Before building one,
pick a real palette and type scale from the product itself (its logo, its domain, a reference the owner names), and
avoid every item below. If the owner explicitly asks for one of them, do it for that item only and say so.

**Color**
- No pastel colors: no washed-out, low-saturation tints as the main palette or as fills (pastel blue, mint, peach, lavender).
- No rainbow coloring, neon colors, or purple-and-black.
- No harsh gradients, radial orbs, or blurred glow blobs.
- No pure white (`#fff`) page background. Use an off-white or a real dark.

**Layout and components**
- No three feature cards in a row, no bento grids, no three pricing tiers by default.
- No colored left stripe on cards or callouts.
- No liquid glass or glassmorphism, no drop shadows as the main depth cue, no dot-grid backgrounds.
- No soft, uniformly large corner radius on everything. Pick one radius and use it deliberately.
- No fake terminal window as decoration.
- Fake testimonials are banned outright (they are also a false claim). Use none, or a real quote with a name and a source.

**Type, icons, copy**
- No Inter, Geist or Space Grotesk as the default face. Choose a font on purpose.
- No Lucide icons or sparkle icons by default; no emojis as icons or bullets; no checkmark-bullet lists.
- No em dashes. Use a period, a comma or a colon.
- No "it's not X, it's Y" phrasing.

**Motion and states**
- No hover animations for their own sake and no animated arrows.
- Use skeleton loaders, not a bare spinner or an empty flash.

**Substance**
- Show the real product: an actual screenshot, recording or live demo, not a mockup of one.
- Ship a terms of service and a privacy policy before a page collects an email or takes payment (the `payments-pack` already
  requires a terms page).

Source: a checklist of vibe-coded design tells the owner saved on 2026-11-11. Where a UI deliberately breaks a line
above, record why in the repo's `docs/journal.md`.

## Gates

What the packs cannot see from code (whether the entity exists, whether the payment account is in the business's name, whether sales tax was
decided) is a **gate**: a checklist a bet clears before real users arrive (`beta`) and before the first payment (`charge`). `ap gate show BET
GATE` reports where a bet stands, read-only; `ap gate seed` adds the manual steps to the control repo as draft pawl steps. Each item says how
it is known, and the manual steps are self-attested. See `docs/gates.md`.

## Waivers

A repo that can't meet a rule yet needs a waiver. Waivers live in one central file, `policy/waivers.yaml` in the
autopilot checkout, one entry per repo and rule with an `owner`, a `reason`, and `granted` and `expires` dates at most 30
days apart. They are read from `origin/main`, not the working tree, so a pull request can't waive its own failure. An
expired waiver stops applying and the rule fails again. An entry that is malformed is ignored and reported, never
half-applied. If `origin/main` can't be found, no waiver is applied. The file doesn't exist yet: creating it is an owner
edit (`policy/**` is protected).

Only a `fail` can be waived. An `unknown` has nothing to waive.

## What is measured and what isn't

- The rules marked `advisory` are judgment. Whether a short `AGENTS.md` helps an agent is unproven: one paper reports
  that context files don't generally improve task success, and I have only read its abstract.
- The 60-line figure is a starting value, not a measured threshold.
- Nothing here has been shown to raise first-pass success. Measuring that needs your own numbers, captured with
  `pow run`.

## Open decisions (owner)

1. **Tier numbering.** `specs/_TEMPLATE.md` numbers risk tiers 1, 2, 3 while `kit/runtime/tier.py` uses 0, 1, 2. This
   standard doesn't choose.
2. **Required check.** Make the CI job a required status check in the `autopilot-main` ruleset, or the step can fail
   without blocking the merge.
3. **Rulesets on your plan.** Checked 2026-11-10: the account plan is `pro`, and the private repo `pawl` carries an
   `autopilot-main` ruleset. That shows private repos accept rulesets on this plan. It does not show a ruleset blocking a
   merge on a private repo; only the public-repo block (autopilot PR #188) has been seen.

## Related

A product repo is either autopilot-managed or pawl-scaffolded, never both: the two disagree about who owns `.claude/`,
`.mcp.json`, and the list of protected paths.
