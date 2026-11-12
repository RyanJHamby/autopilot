# Agentic workflow practices and portable, reproducible setups (as of 2026-10-29)

Method note: only a page-fetch tool was available (no web search). Everything below comes from pages fetched directly; Claude Code docs were fetched at code.claude.com and reflect late-2026 versions (they mention Sonnet 5.5, Claude Code v2.1.2xx-v2.1.299). Topics I could NOT source are listed under Gaps in each section rather than filled from memory.

## 1. Agent-workflow practices (AGENTS.md/CLAUDE.md, hooks, subagents, worktrees, plan-then-execute, specs, tests, handoffs, cloud agents, CI) and documented failure modes

### Takeaway
Vendor docs and practitioners converge on: a short instruction file holding only what the agent cannot infer; deterministic enforcement (hooks, deny rules, sandbox, CI) for anything that cannot have exceptions; a verification command the agent can run; plan/spec separate from execution; one isolated checkout per parallel agent; and human review as the real bottleneck. Quantitative evidence is thin: adoption surveys exist, but I found no controlled measurements of these practices.

### Cited Findings
**Instruction files**
- AGENTS.md is an open plain-Markdown "README for agents", no required fields; common sections are overview, build/test commands, code style, testing, security; stewarded by the Agentic AI Foundation (Linux Foundation); site claims 60k+ open-source projects; supported by Codex, Cursor, Copilot coding agent, Gemini CLI, Aider, Zed, Windsurf, Amp, Devin, Jules and others. Nearest file to the edited file wins; user chat prompts override all. Migration tip: rename to AGENTS.md and symlink the old name. (Adoption figure is self-reported by the site.) — [agents.md](https://agents.md)
- Codex reads `~/.codex/AGENTS.md` (or `AGENTS.override.md`), then walks from the git root down to cwd, one file per directory, concatenated root-first so nearer files override; default cap 32 KiB (`project_doc_max_bytes`); `project_doc_fallback_filenames` in `~/.codex/config.toml` lets it read other names; chain built once per run/session. — [Codex AGENTS.md guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- Claude Code: CLAUDE.md loads every session so every line costs attention on every task. Include only: exact test/typecheck/lint commands, misleading spots in the code, decisions not in the repo, things you corrected twice. Memory guide recommends staying under 200 lines; `/init` generates a draft and "the work is mostly removing lines"; `/doctor` suggests cuts; `/doctor prompt-audit` flags stale/contradictory instructions; personal prefs go in gitignored `CLAUDE.local.md`. — [Claude Code best practices](https://code.claude.com/docs/en/best-practices)
- "If you keep adding emphasis to a CLAUDE.md line and Claude still misses it, that's a sign the line belongs in a hook." CLAUDE.md is guidance Claude may decide does not apply; hooks, deny rules, managed settings are deterministic. — [best practices](https://code.claude.com/docs/en/best-practices)
- Mitchell Hashimoto ("harness engineering"): each time an agent errs, change the setup so it cannot recur, either by adding lines to AGENTS.md or by building small scripts/tools (screenshots, filtered test runs) and listing them in AGENTS.md. Also: end-of-day agents (last 30 min), delegate "slam dunks" to background agents, split planning and execution sessions, give agents a way to verify, turn off notifications; he reports an agent running ~10-20% of the working day (self-estimate). — [Mitchell Hashimoto](https://mitchellh.com/writing/my-ai-adoption-journey)

**Hooks, guardrails, verification**
- Stop hook: runs when Claude tries to finish; exit code 2 sends stderr back and forces more work; Claude Code overrides after eight consecutive blocks (cap adjustable via `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`). `prompt`/`agent` hooks are model-judged and thus not deterministic; use `command`/`http` hooks plus `onFailure: "block"` for real enforcement. Hooks you only have as preferences should be deleted. — [best practices](https://code.claude.com/docs/en/best-practices)
- Deterministic-vs-advisory table: what it can touch -> deny rules, strict sandbox, managed settings; when it's done -> tests, typecheck, Stop hook, CI. Auto mode (default in new terminal sessions per these docs) uses a classifier that runs after deny/ask rules and PreToolUse hooks. — [best practices](https://code.claude.com/docs/en/best-practices)
- `@file` references do not trigger PreToolUse hooks; use Read deny rules or `CLAUDE_CODE_DISABLE_FILE_MENTIONS=1` to block. — [common workflows](https://code.claude.com/docs/en/common-workflows)
- Settings: `permissions.defaultMode` values `auto` and `bypassPermissions` do not take effect from project/local settings (user or managed only; before v2.1.257 bypass worked from any file). — [settings](https://code.claude.com/docs/en/settings)
- Armin Ronacher (June 2025, older): runs Claude Code with permissions disabled via a `claude-yolo` alias, suggests Docker to contain risk; prefers plain scripts/Makefile targets over MCP; log service output to file so agent can read it; keep tools fast, hangs are worse than crashes; observed failures include agents starting a second server on the same port and forgetting permission checks that live in other files. — [lucumr.pocoo.org](https://lucumr.pocoo.org/2025/6/12/agentic-coding/)

**Subagents and context**
- Anthropic context engineering: "context rot" (recall degrades as the window fills, across all models); compaction; structured note-taking to files (NOTES.md/todo); subagents return condensed ~1-2k-token summaries; just-in-time retrieval via paths/grep rather than preloading; hybrid with CLAUDE.md preloaded. — [Anthropic engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Subagents in `.claude/agents/*.md` can be restricted (e.g. `tools: Read, Grep, Glob`) so a reviewer cannot edit, enforced by the harness. Reviewer prompt should say "skip style", otherwise a reviewer "will always find something" and you accumulate needless abstractions. — [best practices](https://code.claude.com/docs/en/best-practices)
- Session hygiene: `/clear` between unrelated tasks; after two failed corrections `/clear` and write a better prompt instead of a third correction; `/rewind` rolls back code/conversation. — [best practices](https://code.claude.com/docs/en/best-practices)

**Plan-then-execute, specs, tests**
- Plan mode (`--permission-mode plan`, Shift+Tab) proposes without editing. The docs' spec pattern: write `SPEC.md`, start a fresh session to build from it, then point a reviewer subagent at the same SPEC.md. — [common workflows](https://code.claude.com/docs/en/common-workflows); [best practices](https://code.claude.com/docs/en/best-practices)
- GitHub Spec Kit flow: `/speckit-constitution` (once) -> specify -> plan -> tasks -> implement -> converge (repeat implement/converge until "Converged"); requires Python 3.11+, uv; repo warns to review each step and that community catalog entries are not audited. — [github/spec-kit](https://github.com/github/spec-kit)
- Harper Reed (Feb 2025, flagged older and self-described as short-lived): brainstorm to `spec.md`, reasoning model to `prompt_plan.md`, `todo.md` checklist the tool ticks off (state across sessions), then execute step by step; notes it is solo-oriented and easy to "get over my skis". — [harper.blog](https://harper.blog/2025/02/16/my-llm-codegen-workflow-atm/)
- Simon Willison (Oct 2025): write the spec yourself so review is easier; send a "scout" agent to find the sticky bits without intending to land its code; use agents for research/PoCs and small maintenance (deprecation warnings); architect-then-fresh-implementer flow credited to Jesse Vincent. — [simonwillison.net](https://simonwillison.net/2025/Oct/5/parallel-coding-agents/)
- Test-first / verification: Hashimoto and the Claude docs both stress giving the agent a self-check (tests, typecheck). I found no quantitative study comparing test-first vs not. — [Hashimoto](https://mitchellh.com/writing/my-ai-adoption-journey); [best practices](https://code.claude.com/docs/en/best-practices)

**Parallel agents and worktrees**
- `claude -w <name>` creates an isolated worktree session; worktrees lack gitignored files, so list small files in `.worktreeinclude` (copied, not linked), use `worktree.symlinkDirectories` for big dirs, or put the install command in CLAUDE.md. Unnamed empty worktrees auto-delete. Docs say each parallel piece of work should get its own checkout. — [common workflows](https://code.claude.com/docs/en/common-workflows); [best practices](https://code.claude.com/docs/en/best-practices)
- Contrast: Willison uses separate fresh clones (often in /tmp), had not adopted worktrees; Ronacher's baseline is separate checkouts and he found cloud/CI background agents unreliable (2025). — [Willison](https://simonwillison.net/2025/Oct/5/parallel-coding-agents/); [Ronacher](https://lucumr.pocoo.org/2025/6/12/agentic-coding/)
- Willison: review is the bottleneck, he can land about one significant change at a time. — [Willison](https://simonwillison.net/2025/Oct/5/parallel-coding-agents/)

**Background/cloud agents, scheduling, PR autonomy**
- Scheduling options: cloud routines (run with laptop off, can trigger on schedule, API or GitHub events), desktop scheduled tasks, GitHub Actions, `/loop`. Prompts for scheduled tasks must define success and where results go since the run cannot ask questions. `claude -p` for CI/hooks; `--bare` skips hooks, skills, plugins, MCP and CLAUDE.md so the run behaves the same everywhere. `claude --from-pr N` finds the session linked to a PR. — [common workflows](https://code.claude.com/docs/en/common-workflows); [best practices](https://code.claude.com/docs/en/best-practices)
- Docs' autonomy checklist: what can it do, can it check its own work, what is it allowed to touch ("permission rules, dontAsk, the sandbox, a worktree, the one branch it may push to"). — [best practices](https://code.claude.com/docs/en/best-practices)
- Cloud sessions: default "Trusted" network allowlist (package registries, GitHub, cloud SDKs); GitHub ops go through a proxy that keeps real credentials outside the VM; network secrets are injected by an agent proxy so the session never sees them. — [cloud environments](https://code.claude.com/docs/en/cloud-environments)

**Failure modes (documented)**
- Context rot / kitchen-sink sessions, repeated corrections polluting context, over-long CLAUDE.md lines being ignored — [best practices](https://code.claude.com/docs/en/best-practices); [Anthropic engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Error compounding: one practitioner estimates 5% per-action error gives about 60% success over 10 turns (author's back-of-envelope, not measured; same post disputes METR-style benchmarks as overstating real-world performance) — [nilenso](https://blog.nilenso.com/blog/2025/09/15/ai-unit-of-work/)
- YOLO/permission-skipping is only reasonable if malicious instructions cannot reach context; local agents have a large blast radius; network-enabled cloud agents can leak private code — [Willison](https://simonwillison.net/2025/Oct/5/parallel-coding-agents/)
- Spec Kit and plugin catalogs are unaudited third-party code — [spec-kit](https://github.com/github/spec-kit)

**Adoption evidence**
- Pragmatic Engineer survey, 906 respondents, 27 Jan-17 Feb 2026: 95% use AI weekly; 55% regularly use agents; among regular agent users Claude Code 71%, Copilot 46%, Cursor 39%; Claude Code "most loved" 46% vs Cursor 19%; 70% use 2-4 tools. Self-selected newsletter readers; some content paywalled. — [Pragmatic Engineer](https://newsletter.pragmaticengineer.com/p/ai-tooling-2026)

### Inferences
- For a solo dev with many small repos, the converged minimum is: short AGENTS.md (commands + gotchas) per repo, one deterministic gate (Stop hook or required CI) that mirrors the acceptance command, deny rules for secrets/destructive commands, worktree-per-task, and an agent-only-pushes-to-agent-branches rule. This matches the autopilot repo's own conventions (agent/* branches, constitution), which the sources independently recommend ("the one branch it may push to").
- Because Codex, Cursor and others read AGENTS.md while Claude Code reads CLAUDE.md, keeping AGENTS.md as the source and a thin CLAUDE.md that imports/symlinks it is the portable choice (agents.md documents the symlink approach; Claude-side import syntax not verified here beyond the repo's existing setup).
- The "200 lines" and "32 KiB" figures are the only concrete size guidance found; treat both as ceilings, not targets.

### Gaps
- No sources fetched on: Kiro specs, Cursor rules/docs, Geoffrey Huntley (Ralph loop), Steve Yegge, Boris Cherny, Thorsten Ball, Kent Beck, Addy Osmani, HN threads. Not claimed here.
- No quantitative study (beyond the surveys above) of context rot thresholds, test-first uplift, or incident rates for destructive agent commands/secret leakage; I did not find sourced incident statistics.
- Nothing verified on agent PR + required-CI patterns beyond Anthropic's generic guidance (branch protection specifics, GitHub Copilot coding agent docs not fetched).

## 2. Portable, reproducible dev environments (dotfiles, Nix, Brewfile, devcontainers, VMs, secrets)

### Takeaway
Only chezmoi and a topic-organized dotfiles repo (Holman style) were sourced; the chezmoi + password-manager route is the best-documented fit for a macOS solo dev who also needs Linux VMs. Nix/home-manager, devcontainers/Codespaces, Brewfile, sops/age were not researched and remain unsourced.

### Cited Findings
- chezmoi: single static binary with no dependencies (no required git/runtime), one source of truth and one command per machine, templates handle per-machine differences without branches, dry-run/diff modes, script execution, one-line install and config generation for new machines; the docs argue that bare repos, stow, yadm, dotbot etc. need extra work for machine differences and secrets (vendor-authored comparison, treat as advocacy). — [chezmoi why-use](https://www.chezmoi.io/why-use-chezmoi/)
- chezmoi + 1Password: template functions `onepasswordRead` (`op://vault/item/field`), `onepassword`, `onepasswordDocument`; interactive sign-in prompt unless `onepassword.prompt=false`; do not use the prompt on shared machines (session token visible in process args); service-account and Connect modes are marked experimental, single-account only, and error if env vars conflict. Implication: headless VMs need service account token or pre-auth. — [chezmoi 1Password](https://www.chezmoi.io/user-guide/password-managers/1password/)
- Zach Holman's dotfiles: public, forkable, organized by topic directories. (Older, long-running reference; no date verified.) — [holman/dotfiles](https://github.com/holman/dotfiles)
- Claude Code reproducibility: `CLAUDE_CONFIG_DIR` relocates settings/history/plugins; `--bare` makes headless runs ignore machine/repo config; `~/.claude.json` holds account, MCP configs and trust decisions and is self-written (not meant to be hand-edited or synced; backups under `~/.claude/backups/`). — [settings](https://code.claude.com/docs/en/settings); [best practices](https://code.claude.com/docs/en/best-practices)

### Inferences
- Reproducible core for this user: Brewfile (macOS) + chezmoi (dotfiles, templates for OS differences) + 1Password CLI refs (no secrets in repo) + a bootstrap script that installs chezmoi and runs `chezmoi init --apply`. This is inference from the chezmoi docs; no source measured adoption or sustainability by solo devs.
- Do not sync `~/.claude.json` or credentials; sync only declarative files (settings.json, CLAUDE.md, skills, agents, hooks scripts).

### Gaps
- No sourced evidence on what solo developers sustain vs over-engineer (Nix, home-manager, yadm, stow, devcontainers, Codespaces, cloud dev VMs, sops/age, gcrypt). Not researched.
- No published dotfiles from well-known engineers that include `.claude/` config were verified.

## 3. Syncing Claude Code config across machines; plugins/marketplaces

### Takeaway
Anthropic's own answer is the plugin marketplace: a git repo with `.claude-plugin/marketplace.json` that bundles skills/commands/hooks/agents/MCP, registered by settings keys so any machine (including CI and containers) gets the same set. User-level files live in `~/.claude/` and project-level in the repo, so a dotfiles repo plus a private marketplace covers both.

### Cited Findings
- Settings scopes: user `~/.claude/settings.json`; shared project `.claude/settings.json` (commit it); project local `.claude/settings.local.json` (personal, gitignored); managed. Precedence: managed > CLI `--settings` > local > shared project > user; array keys like `permissions.allow` merge across files. Hook/permission edits hot-reload. Strict JSON (no comments/trailing commas). — [settings](https://code.claude.com/docs/en/settings)
- If `~/.claude/settings.json` is a symlink to a read-only or generated file, changes made in-app are lost next session. — [settings](https://code.claude.com/docs/en/settings)
- Marketplace = directory or git repo with `.claude-plugin/marketplace.json`; may be private; `claude plugin marketplace add owner/repo` then `claude plugin install name@marketplace`; sources: relative path, `github`, `git-subdir`, `url`, `archive`, `npm`, `command`; pin to `ref`/`sha`; `claude plugin validate`. Plugin skills are namespaced `/plugin:skill`. — [create a marketplace](https://code.claude.com/docs/en/plugin-marketplaces)
- Declarative install: `extraKnownMarketplaces` + `enabledPlugins` (`plugin@marketplace`) in settings; in a repo's `.claude/settings.json` the marketplace registers only after the folder is trusted, and plugins pointing to external sources still need `claude plugin install --scope project`. Cloud sessions do not load repo-declared marketplaces/plugins. — [plugins for organizations](https://code.claude.com/docs/en/plugins/org); [settings](https://code.claude.com/docs/en/settings)
- Containers/CI: build a seed with `CLAUDE_CODE_PLUGIN_CACHE_DIR=/opt/seed claude plugin marketplace add ...`, then `CLAUDE_CODE_PLUGIN_SEED_DIR=/opt/seed` at runtime (read-only, no clone); in `-p` runs plugins install in background unless `CLAUDE_CODE_SYNC_PLUGIN_INSTALL=1`; private marketplaces in CI need `GH_TOKEN` + `gh auth setup-git`. — [plugins for organizations](https://code.claude.com/docs/en/plugins/org)
- Cloud sessions read only the committed repo (`CLAUDE.md`, `.claude/settings.json` for single-repo sessions), not `~/.claude` or `settings.local.json`. — [settings](https://code.claude.com/docs/en/settings)
- Memory in this user's setup is under `~/.claude/projects/<path>/memory` (observed locally; no source on syncing it).

### Inferences
- Portable layout: repo-level behavior in committed `AGENTS.md` + `.claude/settings.json` + `.claude/agents/`; personal cross-repo skills in a private marketplace repo (versioned, replayable on any VM via two CLI commands); user `settings.json` and global CLAUDE.md in chezmoi; auto-memory and `~/.claude.json` treated as per-machine/unsynced.
- `CLAUDE_CODE_PLUGIN_SEED_DIR` is the cleanest path for baking the setup into a VM/container image.

### Gaps
- No well-known engineer's published Claude Code config repo was fetched; community "awesome" lists not evaluated.
- Whether auto-memory syncs across machines: not found in sources fetched.

## 4. Remote access: Tailscale, always-on hosts, phone control

### Takeaway
Anthropic ships first-party phone/browser control of a local session (Remote Control) and cloud sessions; the host must stay awake and logged in. Tailscale SSH is the documented private-network option. Wake-on-LAN, Mac mini/Pi host guides, and pitfalls beyond the vendor-listed limits were not sourced.

### Cited Findings
- Remote Control: connects claude.ai/code or the Claude iOS/Android app to a session running on your machine; code and filesystem stay local; local MCP and config remain available; session reconnects after laptop sleep/network drop; outbound HTTPS only, no inbound ports; requires Pro/Max/Team/Enterprise login (API keys unsupported); transcript is stored on Anthropic servers while connected; if the `claude` process or terminal stops, the session goes offline; `claude remote-control` server mode supports `--spawn worktree` so each on-demand session gets its own worktree (default `same-dir` can conflict); optional Trusted Devices needs sign-in under 18h old. — [Remote Control](https://code.claude.com/docs/en/remote-control)
- Cloud sessions can be started from phone/desktop/terminal (`claude --cloud`) and run on a clean clone, so they work with the laptop off; Willison uses async cloud agents for risky tasks, launchable from phone. — [cloud environments](https://code.claude.com/docs/en/cloud-environments); [Willison](https://simonwillison.net/2025/Oct/5/parallel-coding-agents/)
- Self-hosted environments exist (org infrastructure, default-deny egress option) for routing cloud sessions to your own runner. — [cloud environments](https://code.claude.com/docs/en/cloud-environments)
- Tailscale SSH: `tailscale set --ssh` on host; auth by node keys and ACL `ssh` rules (accept/check, check re-auth default 12h); server side only on Linux and macOS, and on macOS only with the open-source `tailscaled` variant (not the App Store/standalone GUI app); port 22 only; restarting `tailscaled` kills sessions. — [Tailscale SSH](https://tailscale.com/kb/1193/tailscale-ssh)
- Hashimoto: runs background agents while doing other work, kills desktop notifications and checks at natural breaks. — [Hashimoto](https://mitchellh.com/writing/my-ai-adoption-journey)

### Inferences
- A small always-on Mac/Linux box running `claude remote-control --spawn worktree` plus Tailscale SSH fallback covers phone driving without exposing ports; the box must not sleep (macOS power settings) and must keep the process alive (launchd/tmux). Inference, not tested or sourced.

### Gaps
- No sources on wake-on-LAN, Mac mini vs Pi hosts, tmux/mosh patterns, or third-party phone clients; no pitfalls beyond those listed above.

## 5. Session/thread management for many parallel agents

### Takeaway
Tooling is converging on named sessions, PR-linked sessions, a monitoring view for background agents, and file-based notes/specs as the handoff medium. Evidence on what people actually do day to day is mostly from a few blog posts.

### Cited Findings
- `claude --continue` (latest in cwd), `--resume`/`/resume` picker, `/clear <name>` names the session you leave so you can return; naming/branching in the sessions docs (not read). — [common workflows](https://code.claude.com/docs/en/common-workflows); [best practices](https://code.claude.com/docs/en/best-practices)
- Sessions are linked to PRs when created via `gh pr create`; `claude --from-pr 1234` or pasting the PR URL in the resume picker finds them. A "background agents" view (agent-view) monitors parallel sessions and shows PR status. — [common workflows](https://code.claude.com/docs/en/common-workflows)
- Handoff via files: notes/todo files persist across context resets (Anthropic), `todo.md` checklist the agent ticks (Reed), `SPEC.md` as the contract for a fresh build session (Anthropic docs). — [Anthropic engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents); [harper.blog](https://harper.blog/2025/02/16/my-llm-codegen-workflow-atm/); [best practices](https://code.claude.com/docs/en/best-practices)
- Hashimoto's "always have an agent running" goal and end-of-day launches imply a morning review queue; Willison caps himself at one landed significant change at a time. — [Hashimoto](https://mitchellh.com/writing/my-ai-adoption-journey); [Willison](https://simonwillison.net/2025/Oct/5/parallel-coding-agents/)

### Inferences
- With many small repos, the PR (agent branch + linked session + acceptance commands in the issue) is the natural unit of tracking and handoff; a repo journal (this user's `docs/journal.md`/`pow log`) is the durable record. Inference.

### Gaps
- Did not read the sessions or agent-view docs in full; no data on third-party session managers (tmux, cmux, Conductor, etc.) or on how many parallel sessions practitioners sustain.
