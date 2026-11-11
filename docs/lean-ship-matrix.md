# Lean Ship Stack: what each tip becomes here

Source: "Lean Ship Stack: 100+ Workflow & Small-Company Setup Tips" (2026-11-10, 232 tips). This file decides, for every tip, where it
lives in this system, so a tip is either automatic, owned by a named gate, or deliberately not done. Written 2026-11-10 as step A7 of
the plan; classification is judgment, not measurement. Nothing here quotes a benchmark number.

## Buckets

| Code | Meaning | Mechanism |
|---|---|---|
| **D** | Day-0 default: a new repo gets it from the scaffold | `ap new` / template item, plus a standard rule when the file alone proves it |
| **T** | Capability tripwire: required once the repo gains the capability (payments, LLM, auth, DB, deploy, public) | A rule that detects the capability from repo content and requires a pack of artifacts (Phase C) |
| **S** | Stage attestation: a human act that cannot be detected from code | Seeded draft step/artifact in the pawl bet at beta or first charge (Phase E) |
| **M** | Machine or personal: once per laptop or account | `admin` repo (Brewfile, doctor check, bootstrap) |
| **C** | Company ops: legal, finance, admin | Existing pawl deliverables (`llc`, `financial-separation`) and the first-charge step list |
| **P** | Practice: judgment, no automation worth building | Stays in AGENTS.md or the weekly review |
| **X** | Not doing now, with a reason | Revisit at a quarterly review |

Status: **done** = already enforced somewhere (named), **partial** = exists but has a gap, **gap** = nothing yet.

## Gaps found outside the tip list (from the 2026-11-10 exploration)
1. ~~The managed CODEOWNERS block has no `/CODEOWNERS` line, so repos without a `*` catch-all fail `codeowners-cover-protected-paths`.~~
   Resolved 2026-11-10, and the diagnosis was wrong: the managed block writes `.github/CODEOWNERS`, which its `/.github/` entry already covers.
   The rule was demanding a separate root `CODEOWNERS` entry, a false positive in the rule (fixed in `engine.py`, with tests), not a gap in the block.
2. Two incompatible repo-creation paths: `ap new --create` (ruleset `autopilot-main`, required job `test`/`check`) and
   `admin/scripts/new-repo.sh` + `protect-repo.sh` (classic protection, required check `ci`, a third template at `admin/templates/repo`).
3. The daily doctor cannot list GitHub repos (log shows every repo "cannot audit"), so the `enforce_after=2026-11-10` audit of new repos is blind.
4. The scaffolder writes no git hook; `core.write` cannot set an exec bit; nothing sets up hooks in a fresh clone.
5. No per-repo floor: a new rule can only start at `warn` for everyone.
6. apx is hard-coded to three repos, so a new private repo has no working server-side check.
7. Pawl guards are self-attested (`have-a-guarded-repo` passes for any non-empty `repo`); no step seeding; evidence refs are free text.
8. `ap standard converge` audits whatever local clone it finds without fetching, and only files issues.
9. `control` pushes straight to main, so the guard-immutability ratchet (PR-only) does not run on those pushes.
10. Local `core.hooksPath` in autopilot overrides the global gitleaks pre-push for that repo.

## 1. Local machine and dev environment
| # | Tip | Bucket | Status | Where / note |
|---|---|---|---|---|
| 1 | One-command bootstrap | D | partial | `make check` exists; add `setup`/`dev` for product kind |
| 2 | Pin tool versions (mise) | X | | mise not installed; language-level pins (`requires-python`, node `engines`) instead |
| 3 | direnv per project | X | | needs the secrets-manager choice (56) first |
| 4 | Dotfiles repo | M | done | `admin` repo |
| 5 | Brewfile | M | partial | exists; add zizmor, actionlint, osv-scanner, shellcheck |
| 6 | Fast CLI kit | X | | personal preference; agents already use rg/jq |
| 7 | Better git UX | X | | personal |
| 8 | Editor matches CI | D | gap | `.editorconfig` in scaffold |
| 9 | Text expansion | X | | personal |
| 10 | Local services in containers | T | gap | DB pack (compose + seed) |
| 11 | Local model for cheap tasks | X | | low value now |
| 12 | Tested backups | M | gap | quarterly restore of one file; calendar item |
| 149 | Encrypt and lock the machine | M | gap | add a doctor check (disk encryption, auto-lock) |
| 150 | Keys in an agent, not on disk | M | gap | decide later; signing key is a file today |
| 151 | tmux/zellij | X | | personal |
| 152 | "Agent needs you" notifications | M | gap | low priority; hook exists as a tool |
| 153 | Always-on dev box | X | | apx Mac already runs agents |
| 154 | Separate browser profile for consoles | X | | personal |
| 155 | Test the rebuild yearly | M | partial | `admin/scripts/bootstrap.sh` exists; schedule the test |

## 2. Repo hygiene and git
| # | Tip | Bucket | Status | Where / note |
|---|---|---|---|---|
| 13 | Standard make targets | D | partial | `check` everywhere; add `setup`, `audit`, `dev` |
| 14 | Pre-commit hooks | D | gap | `.githooks/pre-commit` + `make setup` symlink (composes with global hooks; verified 2026-11-10) |
| 15 | Strict linters | D | partial | ruff default in templates |
| 16 | Strict types | D | gap | typecheck inside `make check` for product kind |
| 17 | Small signed commits | M | done | doctor critical check + ruleset signatures |
| 18 | Repo template | D | done | `ap new`, `repo-template` |
| 19 | README that onboards | D | partial | `how-this-was-built` rule; quickstart is judgment |
| 20 | Decision records | D | gap | `docs/decisions/README.md` |
| 21 | .editorconfig/.gitattributes | D | gap | with 8 |
| 22 | Locked, auto-updated deps | D | partial | Dependabot exists; add cooldown + grouping |
| 156 | Architecture boundaries | X | | no layered repo yet |
| 157 | Dead code / unused deps | X | | revisit in `make audit` later |
| 158 | Generate, don't hand-write | P | | judgment |
| 159 | Size limits | X | | autopilot guard has `max_diff_lines` for agent PRs |
| 160 | Agent-ready issues | D | partial | templates + `agent-ready` label via `ap launch` |
| 161 | Protect agent-instruction files | D | done | CODEOWNERS rule + guard (see gap 1) |
| 162 | One monorepo | X | | conflicts with repo-per-bet design |

## 3. Agent workflow on a budget
| # | Tip | Bucket | Status | Where / note |
|---|---|---|---|---|
| 23 | AGENTS.md in every repo | D | done | `thin-claude-md`, `agents-md-budget` |
| 24 | Spec before code | D | done | `specs/`, handshake |
| 25 | Tier your models | D | done | `policy/portfolio.yaml` defaults |
| 26 | Done = green checks | D | partial | state `make check` in the AGENTS block |
| 27 | Worktrees | P | done | practice (push only from the main checkout) |
| 28 | Scoped permissions | D | partial | managed repos only; non-managed repos get none |
| 29 | Sandbox risky runs | X | | apx isolation covers the executor |
| 30 | Prompt library | X | | low value |
| 31 | Keep context small | D | done | `agents-md-budget` |
| 32 | Failure log | P | done | journal, `pow log` |
| 33 | Open-source fallback agent | X | | `docs/pi-runner-handoff.md` exists |
| 34 | Diff review checklist | D | gap | PR template fields |
| 35 | Scripts for repeat lookups | X | | |
| 163 | Untrusted input can give orders | P | done | autopilot constitution |
| 164 | No write-credential agents on public input | P | done | constitution |
| 165 | Split read/write tools in CI | P | partial | workflow split |
| 166 | Egress allowlists | M | partial | `deploy/apx-egress.sh` |
| 167 | Vet, pin, patch MCP servers | D | done | guard denies MCP families |
| 168 | Agent hooks | M | done | admin guardrail hooks |
| 169 | Fresh-context review | P | done | `reviewer` role |
| 170 | Progress files | X | | journal and handoffs exist |
| 171 | Own agent benchmark | X | | kb evals exist |
| 172 | Budget per run | D | done | `max_turns`, cost controls |

## 4. Testing and verification
| # | Tip | Bucket | Status | Where / note |
|---|---|---|---|---|
| 36 | Critical-path smoke test | T | partial | deploy and payments packs; stencil has `smoke` |
| 37 | Fast unit suite | P | | `make check` budget about 10 s for the hook |
| 38 | Property-based tests | X | | advisory line in payments pack (money math) |
| 39 | Contract tests for external APIs | T | gap | payments pack (recorded fixtures) |
| 40 | Guard the tests | D | partial | autopilot `patchcheck` covers agent PRs only |
| 41 | Coverage on changed lines | X | | |
| 42 | Mutation testing | X | | |
| 43 | Deterministic test data | P | | |
| 44 | Zero tolerance for flakes | P | | |
| 173 | Red-green proof | X | | |
| 174 | Real database in tests | T | gap | DB pack, advisory |
| 175 | Runtime validation at boundaries | T | gap | payments and LLM packs, advisory |
| 176 | Visual regression | X | | |
| 177 | Fuzz risky inputs | X | | |
| 178 | Snapshot API shapes | X | | |
| 179 | No raw prod data in dev | T | gap | DB pack, advisory |

## 5. CI/CD
| # | Tip | Bucket | Status | Where / note |
|---|---|---|---|---|
| 45 | Branch protection, even solo | M | partial | ruleset exists; private-repo behaviour on this plan unverified |
| 46 | CI runs make check | D | done | templates |
| 47 | Cache everything | X | | CI does not run on Actions for private repos |
| 48 | Path filters | X | | same |
| 49 | Preview deploys | X | | Vercel default |
| 50 | Merge deploys + tested rollback | T | gap | deploy pack: rollback doc |
| 51 | Safe migrations | T | gap | DB pack |
| 52 | Feature flags | T | gap | kill switch only (LLM and payments packs) |
| 53 | Automatic release notes | X | | CHANGELOG for packages exists |
| 54 | Auto-merge safe updates | D | partial | managed repos only |
| 180 | Pin Actions to SHA | D | done | enforced rule |
| 181 | Minimal `permissions:` | D | done | enforced rule |
| 182 | Avoid `pull_request_target` | D | done | enforced rule |
| 183 | No `github.event.*` in `run:` | D | gap | covered by `workflow-lint-wired` (zizmor) |
| 184 | Lint workflows | D | gap | `workflow-lint-wired` |
| 185 | Build once, promote | X | | |
| 186 | Protected prod environment | T | gap | deploy pack, advisory (plan dependent) |
| 187 | Post-deploy checks, auto-rollback | X | | autonomy level 3; later |
| 188 | Nightly CI | X | | |

## 6. Security and secrets
| # | Tip | Bucket | Status | Where / note |
|---|---|---|---|---|
| 55 | Secret scanning | D | partial | global pre-push gitleaks exists; add to repo `make check` (`secret-scan-wired`) |
| 56 | Secrets manager | S | gap | choose once (M), attest per product at beta |
| 57 | Password manager, passkeys, 2FA | M | gap | not detectable; checklist in admin runbook |
| 58 | Separate dev and prod | T | gap | deploy pack: environments doc |
| 59 | Short-lived credentials (OIDC) | D | done | trusted publishing in the release template |
| 60 | Dependency audits | D | gap | `make audit` |
| 61 | Lightweight static analysis | T | gap | public pack: CodeQL |
| 62 | Don't build your own auth | T | gap | auth pack, advisory |
| 63 | Automated DB backups, restore drill | T | gap | DB pack; scale guard `restore-from-backup` exists |
| 64 | Protect your domains | S | gap | attest when a domain is bought |
| 189 | Dependency cooldowns | D | gap | Dependabot `cooldown` + `dependency-cooldown` rule |
| 190 | Block install scripts | D | gap | node: `.npmrc ignore-scripts` + `install-scripts-off` |
| 191 | Install-time scanner | X | | |
| 192 | Assume dev-machine credential theft | M | partial | short-lived tokens; registry 2FA |
| 193 | Bot identity for agents | D | done | rollout and apx Apps |
| 194 | Least-privilege DB roles | T | gap | DB pack |
| 195 | Verify webhooks | T | gap | payments pack |
| 196 | One-page threat model | T | gap | `docs/threat-model.md` shared by payments, auth, LLM, DB packs |
| 197 | Rotation drill | S | gap | scale gate |

## 7. Observability and ops
| # | Tip | Bucket | Status | Where / note |
|---|---|---|---|---|
| 65 | Error tracking | T | gap | deploy pack |
| 66 | Uptime and TLS checks | T | gap | deploy pack |
| 67 | Structured logs | T | gap | deploy pack, advisory |
| 68 | Real health endpoint | T | gap | deploy pack |
| 69 | Golden signals | X | | |
| 70 | Alert on what users feel | S | gap | beta gate |
| 71 | Runbook per alert | D | gap | `docs/runbooks/README.md` |
| 72 | 15-minute postmortems | D | gap | `docs/postmortems/` template |
| 73 | Status page | X | | until there are paying users |
| 74 | Log retention and PII scrubbing | T | gap | deploy and payments packs, advisory |
| 198 | SLO for the core flow | S | partial | scale guard `hold-the-slo` |
| 199 | OpenTelemetry | X | | |
| 200 | Heartbeats for cron jobs | T | gap | deploy pack (stencil has cron routes) |
| 201 | Business-metric alerts | S | gap | first-charge gate |
| 202 | Telemetry agents can read | X | | |
| 203 | Audit log of agent actions | D | partial | trace and ledger |
| 204 | Deploy markers | X | | |

## 8. Infra and cost control
| # | Tip | Bucket | Status | Where / note |
|---|---|---|---|---|
| 75 | Billing alerts everywhere | S | gap | beta gate, one artifact per account |
| 76 | Hard caps on LLM spend | T | gap | LLM pack (applies to stencil now) |
| 77 | A boring stack | P | | |
| 78 | Infra as code | X | | |
| 79 | Free-tier ledger | S | gap | beta gate, low priority |
| 80 | Scale to zero | P | | |
| 81 | Cheap LLM features | T | gap | LLM pack, advisory |
| 82 | Monthly cost review | P | partial | `spend-controls` bet |
| 83 | Kill switches | T | gap | LLM and payments packs |
| 84 | Domains and DNS in one place | C | gap | with the entity |
| 205 | Per-user quotas on AI features | T | gap | LLM pack |
| 206 | Database branching | X | | |
| 207 | Storage lifecycle rules | X | | |
| 208 | Connection pooling | T | gap | DB pack, advisory |
| 209 | Backups in a second provider | S | gap | scale gate |
| 210 | Startup credit programs | C | | after the entity exists |

## 9. Product, distribution and analytics
| # | Tip | Bucket | Status | Where / note |
|---|---|---|---|---|
| 85 | Landing page with one CTA | P | done | pawl probe guards (channel, offer) |
| 86 | Five-event funnel | S | gap | beta gate |
| 87 | Email deliverability | T | gap | mail SDK detected: SPF/DKIM/DMARC attestation |
| 88 | Payments with tested webhooks | T | gap | payments pack |
| 89 | In-app feedback link | S | gap | beta gate |
| 90 | Public changelog | X | | |
| 91 | SEO basics | X | | |
| 92 | Build-in-public cadence | P | done | `blogs-and-social` bet |
| 93 | Customer interview script | P | done | guard `talk-to-ten-buyers` |
| 94 | Measure time to value | X | | |
| 95 | Simple pricing page | S | gap | first-charge gate |
| 96 | Legal pages | S | gap | beta (collects data) and first-charge (terms, refunds) |
| 211 | Launch channel list | P | | |
| 212 | App store optimization | X | | no mobile app is live |
| 213 | Referral or share loop | X | | |
| 214 | Real testimonials only | P | | |
| 215 | Experiment discipline | P | partial | forecast and kill rule at probe |
| 216 | Signup abuse defenses | T | gap | LLM and auth packs |

## 10. Knowledge, planning and personal ops
| # | Tip | Bucket | Status | Where / note |
|---|---|---|---|---|
| 97 | One capture inbox | P | done | Todoist |
| 98 | Gate ideas before starting | P | done | pawl |
| 99 | WIP limit | P | done | pawl limits |
| 100 | Dev journal | D | done | `journal-present`, `pow log` |
| 101 | Searchable notes vault | P | done | kb, claude-docs |
| 102 | Deep-work blocks | P | done | pawl schedule |
| 103 | Weekly review | P | done | `weekly-review` bet |
| 104 | Quarterly kill, keep, double down | P | done | pawl clocks, betting table |
| 105 | Templates for recurring docs | D | partial | postmortem added with 72 |
| 106 | Automate chores | M | done | launchd doctor and converge |
| 217 | A "not doing" list | P | done | this file (the X rows) |
| 218 | Notification hygiene | X | | |
| 219 | Retro when a project ships or dies | P | partial | `sunset-or-park` bet |
| 220 | Monthly public update | P | done | `blogs-and-social` |

## 11. Small company setup
| # | Tip | Bucket | Status | Where / note |
|---|---|---|---|---|
| 107 | Form the entity | C | open | `llc` deliverable, decide-by 2027-02-15 |
| 108 | EIN | C | open | `llc` |
| 109 | Separate bank account and card | C | open | `financial-separation` |
| 110 | Bookkeeping from day one | S | gap | first-charge gate |
| 111 | Clean IP ownership | C | open | guard `clear-your-conflicts` plus the `llc` work; keep employer detail out of repos |
| 112 | Company-owned accounts | S | gap | first-charge gate |
| 113 | Plan for taxes | S | gap | first-charge gate |
| 114 | Contract templates | X | | until a hire |
| 115 | Insurance once paying | S | gap | first-charge gate |
| 116 | Bus-factor doc | S | partial | admin runbook exists; per-product at first charge |
| 221 | NY publication, if NY | C | open | only if the entity is in NY; `llc` |
| 222 | D-U-N-S before app stores | C | | only for a store-published app |
| 223 | Name and trademark search | C | partial | done informally for one project |
| 224 | Compliance calendar | C | gap | after the entity |
| 225 | Privacy basics | S | gap | beta and first-charge gates |
| 226 | Decide sales tax and VAT early | S | gap | first-charge gate (merchant of record vs register) |
| 227 | Yearly subscription audit | C | partial | `spend-controls` bet |

## 12. Team practices
| # | Tip | Bucket | Status | Where / note |
|---|---|---|---|---|
| 117 | CODEOWNERS | D | partial | exists (see gap 1) |
| 118 | PR template | D | gap | with 34 |
| 119 | Day-one onboarding | X | | until a second person |
| 120 | One owner for agent config | X | | solo |
| 121 | Async-first | X | | solo |
| 122 | Light on-call | X | | solo |
| 123 | Four delivery metrics | X | | `ap report` covers agent PRs |
| 124 | Access lifecycle | X | | until a second person |
| 125 | AI usage policy | X | | until a second person |
| 126 | No self-merging risky paths | T | partial | autopilot tiers; payments pack adds a billing/auth lane |
| 228 | Paid trial before a hire | X | | |
| 229 | Scoped contractor access | X | | |
| 230 | Written decision rights | X | | |
| 231 | AI spend budget per person | X | | |
| 232 | Weekly demo | X | | |

## 13. Gaps: AI features, mobile, data, lifecycle, resilience
| # | Tip | Bucket | Status | Where / note |
|---|---|---|---|---|
| 127 | Evals as tests | T | partial | LLM pack requires an evals dir; stencil has eval-vision |
| 128 | Versioned prompts | T | gap | LLM pack, advisory |
| 129 | LLM tracing | X | | |
| 130 | Model fallbacks | T | gap | LLM pack, advisory |
| 131 | Automated store releases | X | | no mobile app is live |
| 132 | Mobile crash reporting | X | | same |
| 133 | Staged rollouts and forced updates | X | | same |
| 134 | Well-timed review prompts | X | | same |
| 135 | Account deletion and data export | T | gap | auth pack, advisory |
| 136 | Query monitoring | X | | |
| 137 | Data retention policy | S | gap | first-charge gate |
| 138 | Dunning | T | gap | payments pack (provider config evidence) |
| 139 | Support basics | S | gap | first-charge gate |
| 140 | Lifecycle emails | X | | |
| 141 | Performance budgets | X | | |
| 142 | Accessibility checks | X | | |
| 143 | Pre-launch load test | X | | before a real launch spike |
| 144 | Mirror your repos | M | partial | gcrypt tooling in the Brewfile; no schedule verified |
| 145 | Vendor exit plan | S | gap | scale gate |
| 146 | License checks | X | | before selling or open-sourcing a product |
| 147 | Cap side-project hours | P | done | pawl hours and caps |
| 148 | Protect sleep and energy | P | | |

## Sections 14 to 16 (guidance, not tips)
- Autonomy ladder: already modeled by autopilot tiers and auto-merge classes; payments, auth and migrations stay at level 1 (payments pack
  adds the CODEOWNERS lane).
- Buy vs build and tools to watch: reference only; revisit at the quarterly review.
