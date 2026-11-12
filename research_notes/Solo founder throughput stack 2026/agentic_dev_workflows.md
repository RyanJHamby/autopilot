# AI-assisted and agentic development workflows for solo developers (state as of 2026-11-09)

Method note: I had WebFetch only (no search tool), about 17 fetches, mostly vendor primary docs plus METR. Coverage of independent practitioner write-ups, academic papers, DORA numbers, OpenAI Codex feature docs and Cursor review/parallel-agent features is thin. Those are listed under Gaps. Model names and dates below are as reported on the fetched vendor pages and were not independently cross-checked.

## Which agentic coding tools are leading now, and what are their latest capabilities?

### Takeaway
Claude Code, OpenAI Codex and Cursor have converged on the same feature set: local terminal and IDE agents, cloud or background agents, parallel sessions, subagents, skills, MCP and scheduled or event-triggered runs. I could verify the details for Claude Code best, and Cursor and Codex only through their changelogs. I did not find a head-to-head quality comparison, so "leading" here means feature breadth, not measured superiority.

### Cited Findings
- Claude Code runs in terminal, VS Code, JetBrains, a desktop app, the web and mobile. All surfaces share one engine, so CLAUDE.md, settings and MCP servers carry across. — [Claude Code overview](https://code.claude.com/docs/en/overview)
- Claude Code can read AGENTS.md in place of CLAUDE.md. It also builds "auto memory" across sessions. — [Claude Code overview](https://code.claude.com/docs/en/overview)
- Claude Code parallelism comes in several forms. Subagents have a lead agent that coordinates and merges. Background agents are full sessions started with `claude --bg` and watched in `claude agents`. A cloud session can be pulled into a terminal with `claude --teleport`. — [Claude Code overview](https://code.claude.com/docs/en/overview)
- Agent view (`claude agents`) is labelled a research preview. Each background session is moved into its own git worktree under `.claude/worktrees/` on first edit. On finishing, it is instructed to commit and push its branch and may open a draft PR. It never pushes to main or master, force-pushes, or merges. Sessions are reclaimed after about an hour unattached, and each session uses subscription quota independently. — [Agent view docs](https://code.claude.com/docs/en/agent-view.md)
- `/batch` splits a large mechanical change into 5 to 30 units. Each unit gets its own worktree and opens a PR after you approve the plan. — [Best practices](https://code.claude.com/docs/en/best-practices.md)
- Claude Code scheduling has three forms. Cloud scheduled tasks (formerly routines) run with the machine off and can fire on API calls or GitHub events. Desktop scheduled tasks run locally. `/loop` repeats a prompt inside a session. — [Claude Code overview](https://code.claude.com/docs/en/overview)
- Claude Code CI and chat integrations: GitHub Actions, GitLab CI/CD, GitHub Code Review on every PR, Slack (`@Claude` with a bug report returns a PR), Chrome debugging, and the Agent SDK. Headless mode is `claude -p`. — [Claude Code overview](https://code.claude.com/docs/en/overview)
- Hooks (PreToolUse, PostToolUse, Stop and others) and skills are first-class. New terminal and VS Code sessions default to "auto mode", where a classifier model reviews risky actions. — [Best practices](https://code.claude.com/docs/en/best-practices.md); [Security](https://code.claude.com/docs/en/security.md)
- Anthropic is donating the Agent Skills open standard to the Agentic AI Foundation (announced Oct 22, 2026). It says more than 70 agent platforms have integrated it since December 2025. — [Anthropic news](https://www.anthropic.com/news)
- Anthropic's listed model releases: Claude Mythos and Fable 5.1 (Sep 15, 2026), Opus 5.5 (Sep 22, which it says costs 40% less than Opus 5 on typical workloads), Sonnet 5.5 (Sep 28, which it says is 30%+ faster and up to 30% cheaper than Sonnet 5), and Haiku 5.5 (Oct 7, pitched for subagents). These are vendor claims. — [Anthropic news](https://www.anthropic.com/news)
- Cursor changelog, newest first. Nov 6, 2026: voice chat with agents (Grok Voice). Nov 5: cloud agents can build, set up and deploy web apps and share them by link. Oct 20: Agent SDK generally available, with agents as a folder of code, evals, and triggers from GitHub, GitLab, Bitbucket, Slack, webhooks or cron. Oct 16: cloud agent canvases, and an Environments API in beta (up to 300 repos). — [Cursor changelog](https://cursor.com/changelog)
- Codex CLI: v0.167.0 (Nov 6, 2026) adds an "agent command center" (`codex agents --no-daemon`) and a subagent picker that prioritizes pending approvals. v0.166.0 (Oct 29) added a GPT-6.1 Terra model to the catalogs. MCP and skills improvements are in both releases. — [Codex changelog](https://learn.chatgpt.com/docs/changelog) (the developers.openai.com URL redirected here; I only read the first ~100k of 221k characters)
- METR published predeployment evaluation summaries for GPT-5.6 Sol (Jun 26, 2026) and Claude Opus 5.5 (Sep 22, 2026). I did not read their contents. — [METR blog index](https://metr.org/blog)

### Inferences
- The tool choice matters less than the workflow around it. All three vendors ship worktree or cloud isolation, subagents, skills, MCP and scheduled runs, and Agent Skills is becoming a cross-vendor standard. Skills and AGENTS.md written once should carry across tools.
- Claude Code supports AGENTS.md, so a repo that keeps AGENTS.md as the canonical file (as this repo does) avoids lock-in.
- Features such as agent view are "research preview", so expect interface churn.

### Gaps
- No Cursor documentation on parallel agents, worktrees or Bugbot reviews appeared in the changelog entries I read. Codex cloud tasks, IDE and code review were not visible in the part of the changelog I read.
- No independent head-to-head benchmark of the three tools. I did not fetch SWE-bench or Terminal-Bench style leaderboards.
- Other tools (Gemini CLI, Copilot agent, Devin, Windsurf, Jules, open-source agents) were not researched.

## Which workflows give the most throughput for a solo dev?

### Takeaway
The vendor guidance that best matches solo use is: write a spec first, give the agent a runnable definition of done, run independent sessions in separate worktrees, and approve at the end. Controlled evidence that any one of these workflows raises throughput is missing; the support is vendor guidance and practitioner opinion.

### Cited Findings
- Anthropic recommends a specific prompt over a vague one, and an interview-then-`SPEC.md` step. The build then starts in a fresh session so it has clean context and a written definition of done. The same file is later what a reviewer checks against. — [Best practices](https://code.claude.com/docs/en/best-practices.md)
- Plan mode (Shift+Tab) lets Claude explore and propose before editing. Anthropic says this prevents expensive rework. — [Costs](https://code.claude.com/docs/en/costs.md)
- Keep CLAUDE.md short (the cost guide says aim under 200 lines). It should hold build and test commands, conventions and gotchas. Move workflow-specific instructions into skills, which load on demand. — [Costs](https://code.claude.com/docs/en/costs.md); [Best practices](https://code.claude.com/docs/en/best-practices.md)
- Anthropic's guidance on instructions: guidance in CLAUDE.md is advisory and "Claude is allowed to decide a guideline doesn't apply". Anything that must happen every time should be a hook, deny rule or managed setting. If you keep adding emphasis to a line, move it to a hook. — [Best practices](https://code.claude.com/docs/en/best-practices.md)
- Parallel sessions: give each its own checkout (`claude -w name`). Worktrees lack gitignored files such as `.env` and installed dependencies, so list small files in `.worktreeinclude` and symlink large directories. — [Best practices](https://code.claude.com/docs/en/best-practices.md)
- Before leaving a task unattended, Anthropic lists five questions: does it know what done looks like, can it check its own work, what is it allowed to touch, what stops it (`--max-turns`, `--max-budget-usd`), and who signs off on the result. — [Best practices](https://code.claude.com/docs/en/best-practices.md)
- Issue-to-PR pipelines exist as product features: Slack-to-PR, GitHub Actions, cloud scheduled tasks triggered by GitHub events, Cursor Agent SDK triggers from GitHub, GitLab, Bitbucket, Slack, webhooks or cron. — [Claude Code overview](https://code.claude.com/docs/en/overview); [Cursor changelog](https://cursor.com/changelog)
- Anthropic's list of things to stop doing: piling on emphasis or ALL CAPS, telling the model to "keep going" or "don't be lazy" (more likely to cause over-work), and delegating to a subagent in the hope of a better answer (a fresh reviewer helps, plain delegation does not). — [Best practices](https://code.claude.com/docs/en/best-practices.md)

### Inferences
- For one person the binding constraint is review attention, not generation. Parallel agents multiply the review queue, so the useful ceiling is probably how many diffs you can review well. I found no measurement of that ceiling.
- Tasks with machine-checkable acceptance (failing test first) are the best fit for unattended runs. Design-heavy work fits plan-then-execute with a human in the loop.

### Gaps
- No controlled study comparing spec-driven, plan-then-execute or worktree-parallel workflows against ad hoc prompting.
- No concrete solo-developer write-ups with numbers (PRs per week, merge rates) were retrieved. I did not search for practitioner blogs.
- Spec-Kit, Kiro and other spec-driven tooling were not researched.

## What review and verification loops work, and what failure modes are documented?

### Takeaway
The documented loop is: failing test or goal condition, enforced by a Stop hook or CI, plus a read-only reviewer on a fresh context, with a human approving the merge. Documented failure modes are mostly in vendor guidance, not in incident data; I found no quantified rates for hallucinated work or test weakening.

### Cited Findings
- "Claude stops when the work looks done." Without something runnable, the human becomes the test suite. Anthropic advises asking for evidence (the command and its output, or a screenshot) rather than accepting "all tests pass". — [Best practices](https://code.claude.com/docs/en/best-practices.md)
- Three ways to give a check: say so in the prompt, `/goal <condition>` (a separate model checks the condition after each turn), or a `Stop` hook (exit code 2 sends Claude back to work). Only the hook is enforced by the harness. The doc says a Stop hook that blocks eight stops in a row is cut off. — [Best practices](https://code.claude.com/docs/en/best-practices.md)
- `prompt` and `agent` hooks ask another model to decide, so they are not deterministic. Use `command` or `http` hooks for real enforcement. — [Best practices](https://code.claude.com/docs/en/best-practices.md)
- Independent review: a custom subagent restricted to `tools: Read, Grep, Glob` is a reviewer that cannot edit, enforced by the harness. A second session that did not watch the code being written is called "the easiest independent reviewer you can get". — [Best practices](https://code.claude.com/docs/en/best-practices.md)
- Reviewer prompt caution: "A reviewer that's asked to find problems will always find something." Tell it to report only correctness gaps and skip style, or you get extra abstraction layers and tests for impossible cases. — [Best practices](https://code.claude.com/docs/en/best-practices.md)
- Anthropic keeps the enforced rule set small: every hook or deny rule will sometimes misfire, and around forty enforced rules is a smell that most are preferences. — [Best practices](https://code.claude.com/docs/en/best-practices.md)
- Auto mode is a classifier judging each action, "like any judgment call it can be wrong". Never-rules belong in deny rules and hooks, which run before the classifier. — [Best practices](https://code.claude.com/docs/en/best-practices.md)
- Security: Anthropic states "no system is completely immune" to prompt injection. Recommended practices: do not pipe untrusted content in, review commands, run in VMs, use the bash sandbox (filesystem and network isolation), and treat MCP servers as trusted code (Anthropic does not security-audit them). `.mcp.json` does not show every server, since plugins and connectors can add more. — [Security](https://code.claude.com/docs/en/security.md)
- Cloud sessions run in isolated VMs with limited network by default. GitHub credentials stay on Anthropic's servers behind a proxy that rejects branch deletions and tag pushes. Branch protection is applied through the connected GitHub access, and "a rule that access can bypass doesn't block a session's push". — [Security](https://code.claude.com/docs/en/security.md)
- METR, Oct 6, 2026: "AI systems could cover up misbehavior"; Oct 22, 2026: red-teaming OpenAI's internal agent monitoring; Sep 30, 2026: testimony to the U.S. Senate on AI agent incidents. Titles only, contents unread. — [METR blog index](https://metr.org/blog)
- Cost blowups are documented: long sessions never cleared, Opus left as default, idle-session scheduled tasks and cross-session messages, uncapped goal check-ins (capped at three per goal from v2.1.246), and agent teams. — [Costs](https://code.claude.com/docs/en/costs.md)

### Inferences
- "Weakened tests" and "hallucinated completion" are the failure modes the above controls target (evidence demand, Stop hook, read-only reviewer). The vendor docs imply them but do not quantify them. In my own repo's terms, the AGENTS.md rule "never weaken or delete tests" is advisory unless backed by a hook or CI check on test-file diffs. That is my inference, not a sourced recommendation.
- A reviewer from the same model family shares blind spots. I found no evidence either way on cross-model review.

### Gaps
- No measured rates of agent-introduced test weakening, hallucinated work or security regressions.
- No incident reports or academic prompt-injection benchmarks were retrieved. METR post contents were not read.
- Human review budget: no study found on how much review per agent PR is adequate.
- Bugbot, CodeRabbit and other review products were not researched.

## What measured evidence exists on productivity?

### Takeaway
The best controlled evidence is METR's two randomized studies, and both are on experienced open-source maintainers in their own mature repos. The 2025 result was a 19% slowdown, and the late-2025 follow-up found a point-estimate speedup with confidence intervals spanning zero, which METR itself calls unreliable because of selection effects. There is no clean measurement of solo founders on greenfield work.

### Cited Findings
- METR RCT (published Jul 10, 2025): 16 experienced open-source developers, 246 issues, randomized to AI allowed or not, mostly Cursor Pro with Claude 3.5/3.7 Sonnet. AI-allowed tasks took 19% longer (95% CI +2% to +39%). Developers forecast a 24% speedup beforehand and still believed about 20% afterward. — [METR 2025 study](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/); CI from [METR 2026 update](https://metr.org/blog/2026-02-24-uplift-update/)
- METR's own caveats: small sample, possible non-representative participants, learning effects beyond about 50 hours of Cursor use not ruled out, results do not show AI fails to help in other settings (such as less experienced developers or unfamiliar codebases). The 2025 page itself is marked out of date. — [METR 2025 study](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/)
- METR update (Feb 2026), late-2025 tools: 57 developers, 143 repos, 800+ tasks, started Aug 2025, pay cut from $150 to $50 per hour. Original developers: estimated 18% speedup (CI -38% to +9% in time terms, so it includes a slowdown). New developers: 4% speedup (CI -15% to +9%). METR says developers are "likely more sped up now" but the data is only weak evidence. — [METR 2026 update](https://metr.org/blog/2026-02-24-uplift-update/)
- METR says the central estimate is probably a poor proxy for real productivity and may be a lower bound. Reasons: developers refused to work without AI, 30% to 50% withheld tasks they did not want to do without AI, some chose different tasks when using agents, and concurrent agents made time logging hard. — [METR 2026 update](https://metr.org/blog/2026-02-24-uplift-update/)
- DORA 2025 report ("State of AI-assisted Software Development") headline: AI is "an amplifier, magnifying an organization's existing strengths and weaknesses". I could not retrieve its numbers. — [DORA 2025](https://dora.dev/research/2025/dora-report/)
- Anthropic's cost data (vendor, usage not productivity): average about $13 per developer per active day, $150-250 per developer per month, under $30 per active day for 90% of users. — [Costs](https://code.claude.com/docs/en/costs.md)
- Vendor claims of model improvement (cheaper, faster, "leads in agentic coding") are in Anthropic's announcements. These are marketing statements, not independent measurements. — [Anthropic news](https://www.anthropic.com/news)

### Inferences
- Self-reports are unreliable: METR found a roughly 40-point gap between perceived (+20%) and measured (-19%) effect in 2025. Treat "I feel 5x faster" claims, including mine, as unmeasured.
- Applying METR to a solo founder is a stretch in both directions. METR studied experts in familiar, mature codebases (where AI is expected to help least), while a founder on greenfield work is closer to METR's "new developers on smaller, greenfield repos" group, which showed only a 4% point estimate with a wide interval. Neither supports a large multiplier.
- This is consistent with a project that records its own measurements (`pow run`) instead of quoting vendor figures.

### Gaps
- No DORA, Stack Overflow, Faros, GitClear or academic numbers retrieved (DORA page had none). Treat any figure from those as not verified here.
- No study of solo founders, agentic workflows with parallel agents, or code quality and maintenance cost over time.
- METR time-horizon benchmark results and the Opus 5.5 and GPT-5.6 Sol evaluation summaries were not read.

## What are cost and model-selection practices?

### Takeaway
Anthropic's guidance is to default to a mid-tier model at medium effort, raise effort or model for hard debugging and design, use the small model for simple subagents, and keep context small. Subagents and agent teams multiply spend.

### Cited Findings
- "Sonnet handles most coding tasks well and costs less than Opus. Reserve Opus for complex architectural decisions or multi-step reasoning." Set `model: haiku` for simple subagents. A switch to Opus also applies to subagents that inherit the session model. — [Costs](https://code.claude.com/docs/en/costs.md)
- The best-practices page says the default Opus 5.5 handles most coding well, Sonnet costs less on routine work, and Fable 5.1 must be chosen explicitly with `/model fable`. Opus, Sonnet and Haiku 5.5 default to `medium` effort. `high` or `xhigh` is for easy-to-overlook cases (code you did not write, flaky tests, schema changes). `max` is for hard unattended problems and "tends to overthink" otherwise. Note the two Anthropic pages differ on which model is the default. — [Best practices](https://code.claude.com/docs/en/best-practices.md); [Costs](https://code.claude.com/docs/en/costs.md)
- Thinking cannot be turned off on the 5.5 models or the Fable models. Thinking tokens bill as output tokens. — [Costs](https://code.claude.com/docs/en/costs.md)
- Agent teams use roughly 7x the tokens of a standard session when teammates run in plan mode. Disabled by default. Recommended: Sonnet for teammates, small teams, shut down finished teammates. — [Costs](https://code.claude.com/docs/en/costs.md)
- Cost reducers: `/clear` between tasks, delegate verbose output (test runs, logs) to subagents, prefer CLI tools (`gh`, `aws`) over MCP servers, keep MCP servers disabled when unused, use hooks to filter output, use skills instead of long CLAUDE.md, and use specific prompts. — [Costs](https://code.claude.com/docs/en/costs.md)
- Unattended-run caps: `--max-turns`, `--max-budget-usd`, spend limits. `/usage` shows per-skill, subagent, plugin and MCP attribution plus recommendations. — [Best practices](https://code.claude.com/docs/en/best-practices.md); [Costs](https://code.claude.com/docs/en/costs.md)
- Subscription users draw from rolling five-hour and weekly windows, shared across models (but a model-family-specific limit can be sidestepped by switching families). Each background session consumes quota independently. — [Costs](https://code.claude.com/docs/en/costs.md); [Agent view](https://code.claude.com/docs/en/agent-view.md)
- Claude Code's cost examples are computed at list price locally and are estimates, not invoices. — [Costs](https://code.claude.com/docs/en/costs.md)

### Inferences
- A sensible solo default, consistent with the sources: mid-tier model at medium effort for implementation, stronger model or higher effort for design and hard debugging, cheapest model for read-only subagents such as search and log triage, with a budget cap on any unattended job. The cost guide's $150-250 per month average is for enterprise developers, not solo founders running many parallel agents.
- Because parallel agents and teams multiply token use, the throughput gain from parallelism has a direct per-task cost. I found no figures on cost per merged PR.

### Gaps
- No pricing figures per model (per-million-token rates) retrieved; consult the Anthropic and OpenAI pricing pages.
- No comparison of subscription versus API economics for heavy solo use, and no OpenAI or Cursor cost guidance retrieved.
- No evidence on whether cheaper models give equal results on routine work; only vendor advice.
