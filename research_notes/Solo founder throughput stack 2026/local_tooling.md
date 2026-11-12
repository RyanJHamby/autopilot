# Local tooling and dev environment for solo developers on macOS (as of 2026-11-09)

Method note: this session had WebFetch only (no search tool). About 17 primary-source fetches (release pages, vendor sites, SO survey). Version numbers below were read from those pages on 2026-11-09. Many pages gave no year in the snippet; where noted, the year is inferred from asset timestamps or the fetch tool's statement. No independent benchmark was fetched, so every speed number below is a vendor claim unless stated.

## Terminals, shells, editors/IDEs, and coding-agent integration

### Takeaway
VS Code remains the default editor by a wide margin. Cursor is the leading AI-native fork. Claude Code already appears in the Stack Overflow 2025 IDE-usage question at 9.7%. Zed is gaining agent integration through ACP, so one editor can host external agents. Terminal and shell choices (Ghostty etc.) could not be verified beyond a nightly release page.

### Cited Findings
- Stack Overflow 2025 "IDE/editor used" (all respondents): VS Code 75.9%, Visual Studio 29%, IntelliJ 27.1%, Vim 24.3%, Cursor 17.9%, Neovim 14%, Xcode 10%, Claude Code 9.7%, Zed 7.3%, Windsurf 4.9%, Cline/Roo 2.2%, Aider 1.9%. Among professionals: VS Code 76.2, Cursor 19.3, Claude Code 10. This is self-reported survey data, 2025 edition (the 2026 edition was not fetched). — [Stack Overflow Dev Survey 2025](https://survey.stackoverflow.co/2025/technology)
- Cursor changelog, latest entry Nov 6, 2026: realtime voice chat with agents (Grok Voice); Nov 5 "Live apps" (cloud agents build, host and share web apps incl. DB and auth, paid plans); Oct 20 Agent SDK GA (agents as code folders, evals, `agent-sdk deploy`); Oct 16 cloud-agent Environments API beta (up to 300 repos). No version number or pricing change shown on page. — [Cursor changelog](https://cursor.com/changelog)
- Zed stable 1.27.0 (Nov 4, 2026): lower Agent Panel memory/CPU; agent checkpoints and "Restore Checkpoint" removed (use reject edits or Git). Zed supports external agents over ACP (session notices and context compaction added in 1.25.2). The page did not name Claude Code. — [Zed releases](https://zed.dev/releases/stable)
- Ghostty: the releases page showed only a nightly `tip` build (Nov 17, year not shown, odd relative to today's date); all macOS builds are universal. No tagged-release version could be read. — [Ghostty releases](https://github.com/ghostty-org/ghostty/releases)
- Playwright 1.62+ bundles the Playwright MCP server and `playwright-cli`; 1.64 added WebMCP support so agents can call page-defined tools. This is the main agent-integration point for browser verification. — [Playwright releases](https://github.com/microsoft/playwright/releases)
- pnpm 12.x has `pnpm approve` for agent "skills" shipped in packages: linked only after approval. — [pnpm releases](https://github.com/pnpm/pnpm/releases)

### Inferences
- A solo dev on a coding agent can keep VS Code or Zed as the editor and treat the agent (Claude Code CLI or similar) as a separate terminal process; the editor choice matters less than the agent's verification loop (tests, Playwright MCP).
- Cursor's direction (cloud agents, Agent SDK, hosted live apps) is toward a hosted platform with its own lock-in; for solo use that is an option, not a requirement.

### Gaps
- Not verified: current Ghostty tagged version, Warp, iTerm2, Kitty, WezTerm status; zsh vs fish vs nushell; Starship; JetBrains 2025/2026 survey; Claude Code, Codex CLI, Copilot, Windsurf current versions/pricing; Cursor pricing; State of JS/Dev 2025 results. No source fetched.

## Runtimes, version managers, package managers, fast toolchains, build tools, task runners

### Takeaway
The consolidated fast stack is mise (versions, env, tasks), uv (Python), pnpm or Bun (JS), Biome (lint/format JS-TS), and just or mise tasks. All are very actively released (several releases per week to month). Turborepo is the lightweight monorepo option; it is also moving into tool provisioning.

### Cited Findings
- mise: manages 1,000+ tools from a registry, pins versions in `mise.toml`, loads env vars (.env, secrets), runs tasks with dependencies in parallel, and can bootstrap a whole machine (packages, dotfiles, repos, services). `mise.lock` records resolved versions for CI and other machines. Releases several times a week; no current version named on page. — [mise](https://mise.jdx.dev/)
- uv 0.13.7 released Nov 3, 2026. 0.13.0 (Oct 9, 2026) made Python 3.15 the default download and has several breaking changes; 0.13.4 (Oct 20) addressed a root-CA security advisory (GHSA-hq85-5cpj-mr62); 0.13.7 improves the preview `uv audit` (OSV dedupe). uv is still pre-1.0. — [uv releases](https://github.com/astral-sh/uv/releases)
- Stack Overflow 2025: uv tag 9.5% of all respondents; Homebrew 25.7%; Make 23.2%; Vite 25.4%; npm 56.8%; pip 40.9%. — [SO 2025](https://survey.stackoverflow.co/2025/technology)
- Biome v2.6 blog post Oct 15, 2026: Markdown, YAML and SCSS formatting/linting; JS plugins for lint rules (developer preview); `biome inspect`. v2.5 passed 500 lint rules, added cross-file linting and watch mode; v2.4 added embedded CSS/GraphQL and HTML a11y rules. The blog gave no performance figures and no mention of type-aware linting. — [Biome blog](https://biomejs.dev/blog/)
- Bun v1.4.4 (Oct 22, 2026, year from asset timestamps) is current. Playwright 1.65 (Nov 5) can run under Bun (`bunx --bun playwright test`) with limits (no watch mode, no async stack frames). — [Bun releases](https://github.com/oven-sh/bun/releases); [Playwright releases](https://github.com/microsoft/playwright/releases)
- pnpm 12.18.0 (Nov 5, 2026; 11.28.11 same day on the 11.x line). Page mentions `minimumReleaseAge` (as a pnpr registry setting capped at 30 days), `pnpm publish --provenance`, and republish-integrity checks. Several security fixes in the 11.x/12.x lines (undici advisory GHSA-xjj6-f33q-929c, RUSTSEC-2026-0387). — [pnpm releases](https://github.com/pnpm/pnpm/releases)
- Turborepo 2.11.10 (Oct 20); canary 2.11.11 (Nov 6). 2.11.9 had many performance gains (lockfile handling, cache restores) and expanded `turbo setup`, which provisions and locks Node, pnpm, uv, Go and rustup; canary adds `turbo.lock` ("about 10x faster to create", vendor claim). — [Turborepo releases](https://github.com/vercel/turborepo/releases)
- just 1.59.0 (Oct 15, 2026). — [just releases](https://github.com/casey/just/releases)

### Inferences
- mise alone can replace asdf/nvm/pyenv/direnv and most of just for a solo repo; adding just is only worthwhile if you want a cross-tool, familiar Makefile-like file. Turborepo's `turbo setup` is starting to overlap with mise, so avoid running both as the tool provisioner.
- Pre-1.0 uv and fast-moving release trains (pnpm major jumped to 12) argue for pinning versions in mise.lock and reading breaking-change notes before upgrading.

### Gaps
- Not fetched: Nx, Turbopack status (Next.js 16 default bundler per the installed Vercel skill list, not independently verified here), ruff/ty current versions, tsgo (TypeScript native port), Node/Deno versions, Homebrew status. No independent benchmarks of uv/Biome/Bun speed were found; all speedups would be vendor claims.

## Local environment reproducibility (dotfiles, Brewfile, devcontainers, Nix, containers)

### Takeaway
Homebrew is used by about a quarter of surveyed developers; mise now covers machine bootstrap; devenv offers a Nix route that works on macOS. OrbStack is the common Docker Desktop alternative on Mac, but its benchmarks are vendor-published and dated; Apple's own `container` tool is active but pre-2.0 and churning.

### Cited Findings
- Docker usage 71.1% in SO 2025 (up 17 points from 2024, the largest jump of any technology surveyed); Podman 11.1%; Homebrew 25.7%. — [SO 2025](https://survey.stackoverflow.co/2025/technology)
- devenv (Nix-based): `devenv.nix` declares packages, 58 languages, 43 services, tasks, git hooks, SecretSpec (Keychain/1Password/dotenv), OCI container builds. Works on Linux, macOS, WSL; Nix must be installed first. Vendor claim: cold start 4832 ms vs warm 47 ms (~100x, one example). — [devenv](https://devenv.sh/)
- OrbStack: native Swift app; claims "starts in seconds", under 0.1% background CPU on Apple Silicon, under 10 MB disk out of box, Rosetta x86, Linux machines. Its only timing chart (17 min vs 45 min Docker Desktop to provision an environment) is labeled "as of August 2023", workload unspecified; "100x faster" quotes are user tweets. Pricing was not shown on the page. All vendor claims. — [OrbStack](https://orbstack.dev/)
- Apple `container` 1.7.1 (Nov 6): breaking CLI changes (`load-image` removed; cluster commands changed); macOS minimum not stated on the page. — [apple/container releases](https://github.com/apple/container/releases)
- mise can bootstrap dotfiles, packages, repos and services (see section above). — [mise](https://mise.jdx.dev/)

### Inferences
- For a solo Mac dev, a Brewfile plus mise (pinned with lockfile) plus a dotfiles repo is the lowest-friction reproducible setup; Nix/devenv buys stronger reproducibility at a learning cost that is hard to justify for one person unless you also ship Nix-built containers.
- Churn in Apple `container` (breaking changes in minor releases) suggests it is not yet a safe default.

### Gaps
- Not verified: OrbStack license terms for commercial/solo-founder use (check before relying on it; this is an unconfirmed risk), Docker Desktop pricing, Colima, devcontainers status, Determinate Nix, chezmoi/stow, nix-darwin. No independent OrbStack vs Docker Desktop benchmark found.

## CI speed and cost, pre-commit and secrets scanning, test strategy for a money path

### Takeaway
GitHub Actions free allowance is now stated as dollars of compute, and macOS runners cost about 10x Linux per minute, so keep CI on Linux and run macOS only when required. Gitleaks is in maintenance mode with a successor (Betterleaks). Playwright is current and agent-friendly for end-to-end tests of a payment flow.

### Cited Findings
- GitHub Actions: included compute $12/month on Free and $18/month on Pro (the page gives dollars, not minutes). Rates per minute: Linux 2-core x64 $0.006, Linux 2-core arm64 $0.005, Windows 2-core $0.010, macOS 3/4-core $0.062. Self-hosted runners are free and do not consume the allowance. Standard runners in public repos do not draw from the allowance. The page mentioned no 2026 changes. — [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- Gitleaks README: maintenance mode, "feature complete", future releases security patches only; points to Betterleaks (github.com/betterleaks/betterleaks) as the maintainer's new focus. A pre-commit example references v8.24.2. — [gitleaks](https://github.com/gitleaks/gitleaks)
- Playwright 1.65.0 (Nov 5): `failures` reporter and `onlyFailures` option for HTML/JSON/JUnit reporters; built-in exclusive lock for serial tests; Node 20 no longer tested; bundled MCP server. — [Playwright releases](https://github.com/microsoft/playwright/releases)
- devenv provides git hooks and tasks declaratively. — [devenv](https://devenv.sh/)

### Inferences
- Arithmetic (mine, from the rates above): $12 buys 2,000 Linux 2-core minutes or about 194 macOS minutes; $18 buys 3,000 or about 290. A solo dev with a Linux-only pipeline rarely exceeds the allowance.
- For a money path (checkout/payments), a small Playwright suite against a test-mode payment provider, run on Linux CI on every PR, plus unit tests for pricing/webhook logic, is the proportionate design; this is a recommendation, not something a fetched source states.
- Choose Betterleaks or gitleaks for pre-commit and CI secrets scanning; gitleaks still works but expect no new features.

### Gaps
- Not fetched: Actions cache behavior and limits, third-party runners (Blacksmith, Namespace, Depot, Warpbuild), Dagger, act, pre-commit vs lefthook vs prek, TruffleHog, GitHub native secret scanning/push protection for private repos on free plans, Betterleaks details (page not read), Stripe testing guidance. No source for CI-speed numbers.

## What is hyped but not worth a solo dev's time?

### Takeaway
Little was verifiable from the pages fetched; the evidence supports calling out a few categories as lower priority, but these are judgments, not sourced findings.

### Cited Findings
- Cursor's cloud-agent/Agent SDK/hosted live-apps features are platform expansions aimed at teams; the changelog gives no usage or outcome data. — [Cursor changelog](https://cursor.com/changelog)
- Several vendor speedup claims (devenv 100x, OrbStack "100x faster" tweets, Turborepo lockfile 10x) are single-example or anecdotal and not independently measured. — [devenv](https://devenv.sh/); [OrbStack](https://orbstack.dev/); [Turborepo releases](https://github.com/vercel/turborepo/releases)
- Apple `container` is shipping breaking CLI changes in minor releases. — [apple/container releases](https://github.com/apple/container/releases)
- Gitleaks is in maintenance mode. — [gitleaks](https://github.com/gitleaks/gitleaks)

### Inferences
- Likely low-value for one person: Nix beyond devenv-lite, Nx (monorepo orchestration for a single-app solo project; Turborepo or plain pnpm workspaces suffice), Kubernetes locally (28.5% usage per SO is mostly team contexts), switching editors for marginal AI features, self-hosted CI runners unless macOS minutes dominate.
- Treat any "N times faster" figure as unverified until reproduced with `pow run` on named hardware (per the repo's working agreement).

### Gaps
- No State of JS/Dev, JetBrains, or independent commentary fetched to back "hyped" judgments; the list above is inference.
