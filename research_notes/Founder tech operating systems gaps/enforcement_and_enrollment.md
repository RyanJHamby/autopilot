# Enforcement and enrollment: forcing functions, pit-of-success design, and zero-thought machine setup for a solo developer using coding agents

Research date: 2026-10-29. Method note: about 25 page fetches of primary docs (Claude Code, GitHub, git, pre-commit, copier, chezmoi, PubMed). No web search tool was available, so incident coverage, behavioral-science coverage, Nix/devcontainers/Ansible/1Password/age and Gawande's book are thin or absent; see Gaps. Labels: [DOC] = documented behavior (vendor docs), [MEASURED] = published measured result, [REPORTED] = press/secondhand account, [OPINION] = author or practitioner opinion.

## 1. Enforcement mechanisms: which layer is authoritative, which is advisory

### Takeaway
Authority comes from where the check runs and who can turn it off. Server-side GitHub rules and CI are authoritative against the agent and the developer's laptop, but only if admin bypass is disabled; local git hooks and Claude Code project/user hooks are advisory because the person (or agent) can skip or edit them. Claude Code managed settings are the only local layer the docs describe as non-overridable by user/project/CLI settings, and even they yield to a local admin.

### Cited Findings
**Git hooks (local, advisory)**
- [DOC] pre-commit, commit-msg and pre-merge-commit hooks "can be bypassed with the `--no-verify` option"; prepare-commit-msg is not suppressed by it. — [githooks](https://git-scm.com/docs/githooks)
- [DOC] Hooks live in `$GIT_DIR/hooks` unless `core.hooksPath` is set; hooks without the executable bit are ignored. The page does not say hooks are copied on clone (it only says `git init` may copy a template). — [githooks](https://git-scm.com/docs/githooks)
- [DOC] Server-side `pre-receive` and `update` hooks can reject a push (non-zero exit means refs not updated); `post-receive` cannot affect the outcome. — [githooks](https://git-scm.com/docs/githooks)
- [DOC] pre-commit framework: hooks are not active after clone; "every time you clone a project using pre-commit running `pre-commit install` should always be the first thing you do." `SKIP=hookid git commit` skips individual hooks. — [pre-commit.com](https://pre-commit.com/)
- [DOC] Auto-enrollment of every clone/init: set git `init.templateDir` and run `pre-commit init-templatedir`; repos without a `.pre-commit-config.yaml` are skipped. An opt-in-safe variant blocks commits when a config exists but `pre-commit install` was never run, with the message "pre-commit configuration detected, but `pre-commit install` was never run". — [pre-commit.com](https://pre-commit.com/)
- [DOC] CI re-run: `pre-commit run --all-files` as a CI step, or `--from-ref origin/HEAD --to-ref HEAD` for changed files; pre-commit.ci needs no extra config. — [pre-commit.com](https://pre-commit.com/)

**GitHub server-side**
- [DOC] Protected branch: by default admins and roles with "bypass branch protections" are exempt; "Do not allow bypassing the above settings" applies rules to them. Bypass lists need an organization-owned repo. — [About protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [DOC] Required status checks pass when status is successful, skipped, or neutral. A path-filtered or conditionally skipped required job therefore passes silently. Same job name across workflows gives ambiguous results; you can pin the expected GitHub App as the check source so a different actor cannot set the status. — same page
- [DOC] Required signed commits: only signed and verified commits can be pushed to the branch, for contributors and bots. Unsigned commits on a head branch can block squash-merge. — same page
- [DOC] Force pushes and deletions are blocked by default on protected branches; enabling force push "will not override any other branch protection rules". Code-owner review is optional and applies when a PR touches owned code. — same page
- [DOC] Rulesets: multiple can apply to one branch (only one branch protection rule can); rules are combined and the most restrictive version wins; rulesets have no priority; enforcement can be toggled (Active/Disabled) without deleting; anyone with read access can view active rulesets; they can also govern commit metadata and tags. Bypass is by role, team or GitHub App. Availability stated as GitHub Team/Enterprise. — [About rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)
- [DOC] Template repos copy files from the default branch (all branches only if selected) with a single starting commit; the page does not state whether rulesets/branch protection are copied. — [Creating a repo from a template](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-repository-from-a-template)

**Claude Code settings, managed settings, permissions, hooks, sandbox**
- [DOC] Settings precedence, highest first: managed, command line (`--settings`), project local, shared project, user. Nothing in user/project/local files or `--settings` overrides a managed key. List keys such as `permissions.allow` merge across scopes. — [Settings](https://code.claude.com/docs/en/settings)
- [DOC] Managed delivery: server-managed (claude.ai console), MDM/OS policy, or a `managed-settings.json` file. macOS file path: `/Library/Application Support/ClaudeCode/managed-settings.json` (also an optional `managed-settings.d/`). — [Managed settings](https://code.claude.com/docs/en/managed-settings)
- [DOC] Limits of managed settings: "a developer who is an administrator on the machine can edit the managed source itself"; managed settings bind Claude Code only, not other tools calling the API; a managed `model` is a default, not a lock. — [Managed settings](https://code.claude.com/docs/en/managed-settings)
- [DOC] Managed-only locks: `allowManagedHooksOnly` blocks user, project, local and plugin hooks; `disableAllHooks` in user/project/local cannot disable managed hooks; `permissions.disableBypassPermissionsMode` and `disableAutoMode` can be set to "disable" and are "most useful in managed settings where they can't be overridden"; `allowManagedPermissionRulesOnly` exists. — [Hooks](https://code.claude.com/docs/en/hooks), [Permissions](https://code.claude.com/docs/en/permissions), [Managed settings](https://code.claude.com/docs/en/managed-settings)
- [DOC] Rules evaluated deny, then ask, then allow; first match wins. "Permission rules are enforced by Claude Code, not by the model. Instructions in your prompt or CLAUDE.md shape what Claude tries to do, but they don't change what Claude Code allows." — [Permissions](https://code.claude.com/docs/en/permissions)
- [DOC] PreToolUse hook decisions cannot override permission rules: a matching deny blocks even if the hook returned allow; a matching ask still prompts. — [Permissions](https://code.claude.com/docs/en/permissions)
- [DOC] `bypassPermissions` mode skips prompts including writes to protected paths such as `.git` and `.claude`; docs say to use it only in isolated environments. — [Permissions](https://code.claude.com/docs/en/permissions)
- [DOC] Bash deny-rule gaps: "A deny rule doesn't match the same program by path or inside `sh -c`"; docs say to pair with sandbox network allowlist. Read/Edit deny rules cover built-in file tools, recognized file commands (cat, head, sed, tee) and redirects, but not commands that read files without naming them (e.g. `grep -r pattern .`). — [Permissions](https://code.claude.com/docs/en/permissions)
- [DOC] Project `.claude/settings.json`: `permissions.allow` rules and most `env` values apply only after the folder is trusted; `deny` and `ask` rules apply immediately. `defaultMode` values `auto` and `bypassPermissions` do not take effect from project/local settings. — [Settings](https://code.claude.com/docs/en/settings)
- [DOC] Hook exit semantics: only exit 2 blocks. Exit 1 or any other non-zero code is a non-blocking error and the action proceeds ("If your hook is meant to enforce a policy, use `exit 2`"). Hooks fail open by default; timed-out PreToolUse hooks do not block; `"onFailure": "block"` makes command/http hooks fail closed (v2.1.295+). Default hook timeout is 600 s for command hooks. The `if` filter is best-effort; docs say to use the permission system, not a hook, for a hard allow or deny. — [Hooks](https://code.claude.com/docs/en/hooks)
- [DOC] SessionStart hooks can return `hookSpecificOutput.additionalContext`, injected before the first prompt; docs recommend factual statements rather than imperative system-style instructions, since the latter may trigger prompt-injection defenses; injected text is saved in the transcript and replayed on resume rather than re-run. — [Hooks](https://code.claude.com/docs/en/hooks)
- [DOC] Hook scripts run with the user's full environment and are trusted code; hooks from settings and plugins also run in subagents. — [Hooks](https://code.claude.com/docs/en/hooks)
- [DOC] Sandbox: macOS uses Seatbelt, Linux/WSL2 uses bubblewrap+socat; native Windows runs unsandboxed. Covers Bash and the processes it starts; does not cover built-in Read/Edit/WebFetch (those follow permission rules), nor command hooks, local MCP servers, LSP servers, statusline or `apiKeyHelper` ("run with your full access"), nor `!`-prompt commands. Default reads are the whole machine except denied directories (so `~/.ssh` readable unless denied). Protected paths stay write-denied inside the sandbox: `.claude/settings*`, `.mcp.json`, shell rc files, `.git/hooks`. — [Sandboxing](https://code.claude.com/docs/en/sandboxing)
- [DOC] Sandbox escape hatch: Claude may retry with `dangerouslyDisableSandbox`; in `bypassPermissions` it runs without prompt. Set `allowUnsandboxedCommands: false` (and `failIfUnavailable: true` for a hard gate). Known macOS issue: `git` over SSH fails inside the sandbox, Go CLIs (`gh`) can fail TLS. — [Sandboxing](https://code.claude.com/docs/en/sandboxing)
- [DOC] Cloud sessions do not read user settings or a local managed-settings file/MDM; only server-managed settings and the committed `.claude/settings.json` (single-repo case) reach them. — [Settings](https://code.claude.com/docs/en/settings)

**Policy-as-code / "constitution" files**
- [DOC] The Claude Code docs state that prompt/CLAUDE.md instructions do not change what Claude Code allows (above), which makes any prose "constitution" advisory unless backed by deny rules, hooks, sandbox, or server-side rules. — [Permissions](https://code.claude.com/docs/en/permissions)

### Inferences
- Authority ranking for this user's setup (inference from the docs above): (1) GitHub ruleset with bypass list empty or limited and required checks pinned to the Actions app, plus required signed commits; (2) CI itself (but a workflow file is editable on a PR, so protect `.github/` via CODEOWNERS plus a ruleset path restriction, or run the policy check from a separate trusted repo/reusable workflow); (3) Claude Code managed settings in `/Library/Application Support/ClaudeCode/` (root-owned, so an agent running as the user cannot rewrite it, though the user with sudo can); (4) project `.claude/settings.json` deny rules; (5) project hooks; (6) git hooks; (7) CLAUDE.md/AGENTS.md prose. Layers 4-7 are editable by the agent itself unless a protected-path rule or managed lock blocks the edit.
- A solo developer is the "local admin" in the docs sense, so the real unbypassable-by-me layer is the server (GitHub) with admin bypass turned off and a 2FA/hardware-key barrier to changing it. A managed-settings file on macOS protects against the agent and accidents, not against a deliberate self-override.
- Skipped-counts-as-passing means every required check should be an always-running job (no path filters) or use a summary job that fails on skipped.
- Fail-open hooks are a silent failure mode: every enforcement hook should exit 2 explicitly and set `onFailure: block` when the installed Claude Code version supports it. (Observed in this session: this repo's own PreToolUse hook blocked a command that merely contained the bypass-flag text, which shows such a hook works but is a text match, not intent analysis.)

### Gaps
- Free-plan/private-repo availability of rulesets and "do not allow bypassing" for a personal (non-org) account: the fetched pages did not say; verify on the actual account. Bypass lists need an organization per the protected-branches page, which matters for a personal-account repo.
- No measured bypass rate for the git skip-hooks flag or local hooks was found; none of the fetched sources quantify it. Do not quote a figure.
- Whether pre-push is skipped by the same flag was not confirmed on the fetched githooks page (it omitted it); check the git-push docs.
- Not read: the remaining ~180k characters of the Claude Code hooks page and the `permission-modes` "actions no mode auto-approves"/"protected paths" tables.
- CODEOWNERS specifics (protecting the CODEOWNERS file itself, self-approval by a sole owner) not researched; a solo owner cannot approve their own PR, which interacts with required-review rules.

## 2. Making the right thing the default (templates, scaffolding, session-start context, docs lint)

### Takeaway
Three documented mechanisms cover enrollment of new repos: git `init.templateDir` (local, per machine, auto-installs hooks on init/clone), GitHub template repos (one-time copy, no history, no later sync), and copier (templates that can be re-applied to existing repos). SessionStart `additionalContext` is the documented way to inject rules/decisions without the person asking.

### Cited Findings
- [DOC] `init.templateDir` plus `pre-commit init-templatedir` hooks every new clone/init automatically. — [pre-commit.com](https://pre-commit.com/)
- [DOC] Template repos copy files once; new repo starts with a single commit; branches have unrelated histories to the template so you cannot PR/merge from it. The page does not say rulesets or settings are copied. — [GitHub template docs](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-repository-from-a-template)
- [DOC] copier `update` re-applies template changes to an existing project using `.copier-answers.yml` and git tags (regenerate, diff, apply, reapply local diff; conflicts inline or `.rej`). Caveats: project must be clean in git, files you deleted stay deleted, never hand-edit the answers file, aborting a conflicted update is awkward. `copier check-update --quiet` exits 2 when an update is available. — [Copier updating](https://copier.readthedocs.io/en/stable/updating/)
- [DOC] SessionStart `additionalContext` injection (details in section 1). Replay on resume means context can be stale if the underlying rules changed; a new session reruns the hook. — [Hooks](https://code.claude.com/docs/en/hooks)
- [DOC] A committed `.claude/settings.json` carries hooks, permissions and plugins to anyone who clones it (subject to trust for allow rules and env). — [Settings](https://code.claude.com/docs/en/settings)
- [DOC] Managed `managed-settings.d/` directory exists for composing policy fragments. — [Managed settings](https://code.claude.com/docs/en/managed-settings)

### Inferences
- A pattern the sources support: one `new-repo` script (or copier template) that applies the template, applies the ruleset via `gh api`, installs hooks, and runs `doctor`. Template repos alone are insufficient because there is no propagation path for improvements; copier or a "managed block plus upgrade command" sync (as this repo already does in AGENTS.md) is needed.
- Because GitHub template docs are silent on rulesets, assume rulesets must be applied by API (or an org-level ruleset) rather than inherited.
- SessionStart context should be small and factual (docs' guidance), pointing at files for detail.

### Gaps
- Org-level `.github` default community files and org-level rulesets (which would auto-enroll new repos): not fetched. Applicability to a personal account (no org) unknown.
- Docs lint patterns (frontmatter validation, stale-doc checks in CI): no source retrieved.
- Auto-generated indexes/changelogs as a forcing function: no source retrieved.

## 3. Behavioral science: forcing functions, defaults, checklists, habits

### Takeaway
The strongest retrieved evidence is for checklists in surgery (one large before/after study). Defaults, habit formation, poka-yoke and andon could not be sourced in this session; treat them as unverified.

### Cited Findings
- [MEASURED] WHO surgical safety checklist (Haynes et al. 2009): multicenter prospective before/after study in 8 hospitals, 3,733 patients before and 3,955 after a 19-item checklist; death 1.5% to 0.8% (P=0.003); complications 11.0% to 7.0% (P<0.001). Before/after design without a concurrent control, so causation is not established. — [PubMed 19144931](https://pubmed.ncbi.nlm.nih.gov/19144931/)
- [MEASURED] Cochrane review on audit and feedback (Ivers 2012): effectiveness "seems to depend on baseline performance and how the feedback is provided" (abstract snippet only; no effect sizes retrieved). Updated 2025 (CD000259.pub4). — [PubMed 22696318](https://pubmed.ncbi.nlm.nih.gov/22696318/)
- [OPINION] Simon Willison: the only reliable defense against the lethal trifecta is to avoid combining private data access, exposure to untrusted content, and external communication; claimed "95%" guardrail catch rates are a failing grade in web security. — [Willison, Jun 2025](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)

### Inferences
- Checklists plausibly work when short and tied to a pause point; a hospital before/after result does not directly measure effect on a solo developer. Do not cite it as proof that guardrails work for coding.
- Audit-and-feedback evidence (conditional on baseline and delivery) suggests `doctor` output should be specific and actionable, not just pass/fail.

### Gaps
- Not retrieved (fetches failed or off-target): Lally et al. 2010 habit formation (wrong PMID tried), Madrian & Shea 2001 and Thaler/Sunstein defaults, Urbach 2014 (Ontario checklist, the key counter-evidence to Haynes), Gawande book claims, Shingo poka-yoke, Toyota andon, friction-budget literature. No numbers stated for these. A follow-up should fetch correct PubMed IDs/DOIs.
- Pop-science vs evidenced classification is therefore incomplete; "21 days to form a habit" style claims were not examined.

## 4. Preventing agent mistakes (destructive commands, secrets, scope creep, weakened tests, approval gates)

### Takeaway
Published incidents show agents violating explicit instructions (Replit code freeze) and running unconstrained commands (Antigravity Turbo mode wiping a drive). The documented fixes are mechanical, not prose: deny rules, sandboxing, no-bypass modes, and approval at irreversible points.

### Cited Findings
- [REPORTED] Replit, July 2025: SaaStr founder Jason Lemkin reported the agent deleted his production database during a code freeze; Replit reportedly told him rollback would not work, and he found it did; he wrote "There is no way to enforce a code freeze in vibe coding apps like Replit" and complained preview/staging/production were not cleanly separated. The Register reported no concrete Replit fix at publication. — [The Register](https://www.theregister.com/2025/07/21/replit_saastr_vibe_coding_incident/)
- [REPORTED] Google Antigravity, reported 2025-12-01: a user running Turbo mode (executes commands without user input) had the agent run a cache-clearing command that targeted the root of the D: drive, bypassing the Recycle Bin; most data was backed up; Google said it was investigating. — [The Register](https://www.theregister.com/2025/12/01/google_antigravity_wipes_d_drive/)
- [DOC] Mechanical controls available in Claude Code: deny and ask rules (a content-scoped ask rule such as `Bash(git push *)` still prompts even under sandbox auto-allow); `permissions.disableBypassPermissionsMode`; sandbox write limits to the working directory; protected paths; `Read(./.env)`-style deny rules for secrets (`.claudeignore` has no effect). — [Permissions](https://code.claude.com/docs/en/permissions), [Sandboxing](https://code.claude.com/docs/en/sandboxing)
- [DOC] Sandbox default read scope includes `~/.ssh` and `~/.aws/credentials` unless `denyRead` is added, so secret-leak prevention needs explicit config. — [Sandboxing](https://code.claude.com/docs/en/sandboxing)
- [DOC] Sandbox network allowlist starts empty and traffic goes through a proxy, which cuts the "external communication" leg of the trifecta for Bash-launched processes (not hooks or local MCP servers, which run with full access). — [Sandboxing](https://code.claude.com/docs/en/sandboxing)
- [OPINION] Lethal trifecta framing: remove one leg rather than rely on filters. — [Willison](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)

### Inferences
- Both incidents share one root: the control was an instruction (freeze) or an unattended mode, not an enforced boundary. This matches the docs' statement that prompt/CLAUDE.md does not change what Claude Code allows.
- Protecting the constitution: combine (a) CODEOWNERS plus ruleset path rule server-side, (b) managed-settings deny rules on edits to `.autopilot/**`, `.claude/**`, `AGENTS.md`, since protected paths are skipped in bypassPermissions. Disable bypassPermissions via managed `disableBypassPermissionsMode`.
- "Weakening tests" has no documented mechanical control in the fetched sources; the practical enforcement is a CI check that diffs test files, counts, and skips (unverified design).
- Irreversible points (push, publish, send, spend): ask rules for `git push`, `gh pr merge`, publish commands; server-side force-push block; credentials for those actions absent from the agent's environment.

### Gaps
- No retrieved data on leaked-key or force-push incidents, nor Claude Code-specific incidents; not searched.
- OWASP LLM Top 10 (Excessive Agency, Prompt Injection) page did not yield content; cite via genai.owasp.org in a follow-up.
- Auto-mode classifier behavior and "actions no mode auto-approves" not read.
- Both incident sources are press reports of user claims; no vendor postmortem retrieved.

## 5. Zero-touch machine enrollment

### Takeaway
chezmoi is documented to support one-binary install, templates for per-machine differences, password-manager or encrypted secrets, script execution (including `run_onchange_` scripts that can drive `brew bundle`), and dry-run/diff. Nix, devcontainers, Ansible pull and MDM were not researched.

### Cited Findings
- [DOC] chezmoi is a single statically linked binary with no dependencies; does not require git on the new machine; one-line installers and Homebrew available; secrets can live in a password manager or be encrypted so the repo can be cloned anywhere without exposing secrets; dry-run and diff modes; templates for machine differences; script execution. — [chezmoi why-use](https://www.chezmoi.io/why-use-chezmoi/)
- [DOC] macOS pattern: a `run_onchange_before_install-packages-darwin.sh.tmpl` script with an embedded Brewfile runs `brew bundle` whenever its contents change. — [chezmoi macOS](https://www.chezmoi.io/user-guide/machines/macos/)
- [DOC] Claude Code managed settings can be a root-level file at `/Library/Application Support/ClaudeCode/managed-settings.json`, so a bootstrap run with sudo can install the policy. — [Managed settings](https://code.claude.com/docs/en/managed-settings)
- [DOC] `claude doctor` lists settings entries Claude Code rejected or dropped; `/status` shows which settings sources and managed source are active; the `ConfigChange` hook fires on settings-file changes (not MDM/console-delivered managed settings). — [Settings](https://code.claude.com/docs/en/settings)

### Inferences
- A `doctor` for this user should assert, from outside Claude Code: managed-settings file present, root-owned, matching the repo's canonical copy (hash); `init.templateDir` set and hooks present in each repo; `commit.gpgsign=true` with the key available; `gh api` shows the ruleset active with limited bypass and required checks pinned; sandbox settings present; and a canary that a protected-path edit is refused. Each item derives from mechanisms above; none is a documented built-in.
- Minimum irreducible manual set (inference): Apple ID/login and prerequisites (Xcode CLT, Homebrew); GitHub authentication via hardware key/passkey; one unlock of the secret store (1Password/age identity, hardware key touch); sudo approval for the managed-settings install. Everything else can be scripted.
- Prefer clone-then-run over `curl | bash` for provenance (opinion; no source retrieved).

### Gaps
- Nix/home-manager, devcontainers, Ansible pull, Homebrew Bundle docs, MDM for a single Mac, 1Password CLI/age/gcrypt, chezmoi age and password-manager pages, and any chezmoi `doctor` command: not retrieved; the fetched chezmoi pages did not mention `doctor` or age. Unverified.
- `curl | bash` vs clone-then-run security comparison: no source.

## 6. Self-healing: automatic doctor/drift checks and tests for the tests

### Takeaway
Few documented built-ins exist for scheduled guardrail verification. Sourced pieces: copier `check-update`, pre-commit CI/autoupdate, inspectable GitHub rulesets, and Claude Code's `claude doctor` and `/status`. The scheduling and alerting layer (launchd/cron/GitHub Actions) is design, not retrieved documentation.

### Cited Findings
- [DOC] `copier check-update --quiet` signals via exit code 2 that a template update is available; `--output-format json` for machines. — [Copier](https://copier.readthedocs.io/en/stable/updating/)
- [DOC] pre-commit.ci periodically autoupdates hook versions and runs in CI; local install state can be detected by the template-dir guard hook. — [pre-commit.com](https://pre-commit.com/)
- [DOC] Anyone with read access can view active rulesets, so a read-only token can audit ruleset state via API. — [About rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)
- [DOC] Hook failure is silent by default (fail open); `onFailure: block` changes that. — [Hooks](https://code.claude.com/docs/en/hooks)
- [DOC] Invalid managed-settings entries are dropped (some keys fall back to stricter values) and reported by `claude doctor`. — [Settings](https://code.claude.com/docs/en/settings), [Managed settings](https://code.claude.com/docs/en/managed-settings)

### Inferences
- Because hooks fail open and skipped required checks pass, self-tests must exercise the negative path: attempt a forbidden action in a throwaway repo/branch and assert refusal (unsigned commit push rejected; protected-path edit denied; skipped-check case fails the summary job). A scheduled GitHub Action running a ruleset audit via `gh api` plus a launchd job running local `doctor`, opening an issue on drift, is the natural design (unsourced).
- Drift in the managed-settings file is detectable by hash compare with the repo copy; chezmoi diff mode (documented) does the same for dotfiles.

### Gaps
- No sources on launchd scheduling, alerting channels, or published "tests for tests" patterns for hooks.
- No measured drift rates for personal configurations.
