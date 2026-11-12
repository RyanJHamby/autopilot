# Tool and stack selection: frameworks and habits of solo founders and small teams

Method note: this session had WebFetch but no web search tool. I fetched primary sources by known URL (about 16 calls). Many guessed URLs returned 404 (Levels' stack pages, Pragmatic Engineer 2025 post, Bezos 2015 letter on aboutamazon.com, Paul Graham pages other than startupideas). Anything not listed below is a gap, not a finding. Nothing here comes from training memory unless marked.

## Which decision frameworks are well-regarded, and what do indie/YC-style founders standardize on?

### Takeaway
Four frameworks have primary sources I could verify: innovation tokens (McKinley, 2015 classic), one-way/two-way doors (Bezos, 2015 letter, classic), the Thoughtworks Radar ring model (current, April 2026), and appetite-based time-boxing (Shape Up). I could not verify any named founder's stack (Levels, Marc Lou, etc.) from a primary source this session.

### Cited Findings
- (Classic, 2015) McKinley: each company gets "about three" innovation tokens; they are a roughly fixed supply and companies overestimate how many they have. — [Choose Boring Technology](https://mcfunley.com/choose-boring-technology)
- Spending a token examples: writing a website in NodeJS, adopting MongoDB, year-old service discovery tech; building your own database is "serious trouble". (These are 2015 examples; the tech has since matured, the principle is what travels.) — [McKinley](https://mcfunley.com/choose-boring-technology)
- "Boring" is not "bad": examples given are MySQL, Postgres, PHP, Python, Memcached, cron. Unknown unknowns are far more numerous with new technology. — [McKinley](https://mcfunley.com/choose-boring-technology)
- McKinley's adoption check: ask how you would solve it with what you already have; write down exactly what about the current stack makes the problem too hard; if the new tool replaces something, commit to migrating the old functionality on a timeline. — [McKinley](https://mcfunley.com/choose-boring-technology)
- (Classic, 2016 letter) Bezos: irreversible decisions are "one-way doors" (Type 1), to be made "methodically, carefully, slowly, with great deliberation and consultation"; most are reversible "two-way doors" (Type 2) that "can and should be made quickly by high judgment individuals or small groups." Large orgs wrongly apply Type 1 process to Type 2 decisions. — [Amazon 2016 shareholder letter (SEC copy)](https://www.sec.gov/Archives/edgar/data/1018724/000119312516530910/d168744dex991.htm)
- Same letter family: decide with about 70% of the information you wish you had; waiting for 90% is usually slow. (Fetched from the Amazon-hosted 2016 letter page, which used "two-way doors" language but not "Type 1/2" labels in the extract.) — [Amazon 2016 letter](https://www.aboutamazon.com/news/company-news/2016-letter-to-shareholders)
- Thoughtworks Radar is a twice-yearly snapshot; rings are Adopt, Trial, Assess, Caution (the older "Hold" ring is now called Caution). Latest is Volume 34, April 2026. — [Radar FAQ](https://www.thoughtworks.com/radar/faq); [Radar home](https://www.thoughtworks.com/radar)
- Radar April 2026 themes relevant to tool choice: evaluating technology is getting harder in an agentic world (terms precede settled meaning; tools too young to assess); "cognitive debt" from AI-generated code; coding agents need "harnesses" (feedforward: skills, spec-driven development; feedback: linters, type checkers, tests, mutation testing). — [Radar home](https://www.thoughtworks.com/radar)
- Shape Up: "appetite" inverts estimation ("Appetites start with a number and end with a design"); fixed time, variable scope; circuit breaker = "Cancel projects that don't ship in one cycle by default instead of extending them by default" (six-week cycle). — [Shape Up ch.3](https://basecamp.com/shapeup/1.2-chapter-03)
- Stack Overflow 2025 usage (all respondents): PostgreSQL 55.6%, MySQL 40.5%, SQLite 37.5%; Python 57.9%, TypeScript 43.6%; Rust 14.8% (14th); AWS 43.3%, Cloudflare 20.1%. This shows Postgres and SQLite as the default data layers, not any specific founder's choice. — [SO Survey 2025 technology](https://survey.stackoverflow.co/2025/technology)
- Paul Graham (startupideas) gives no stack guidance; his stance is that being able to build lets you prototype an idea quickly, and to sell before building ("go sell the product ASAP"). — [PG, How to Get Startup Ideas](https://www.paulgraham.com/startupideas.html)

### Inferences
- Tokens + two-way doors combine into a usable rule: spend a token only where the choice is a one-way door AND is core to the product's differentiation; everything reversible gets a fast default.
- The Radar's four rings are a cheap template for a personal per-language/tool list (adopt/trial/assess/avoid) reviewed twice a year.
- Postgres/SQLite/Python/TypeScript dominance in the SO data is consistent with "boring default" behavior at population scale, but is not evidence about what any solo founder standardizes on.

### Gaps
- Could not verify Pieter Levels' stack (PHP/jQuery/SQLite/single VPS is widely repeated but I have no fetched primary source), Marc Lou's stack, or Tailscale/Fly/Vercel/Supabase-centric claims. levels.io URLs I guessed returned 404. Needs search or a HN/Indie Hackers thread.
- No YC Startup School material fetched on "default stack."

## How do solo founders limit tool sprawl, evaluate and retire tools; is there evidence that a written per-project stack rationale improves outcomes?

### Takeaway
The best-supported practice for recording choices is the lightweight Architecture Decision Record (Nygard, 2011; Thoughtworks Radar Adopt in 2017-2018). I found no empirical study showing that written stack rationales improve outcomes; support is practitioner consensus only.

### Cited Findings
- Nygard ADR: five parts (Title, Status [proposed/accepted/deprecated/superseded with pointer], Context, Decision in "We will..." form, Consequences including negative); keep to one or two pages; write like "a conversation with a future developer"; short records are more likely to stay current. — [Nygard, Documenting Architecture Decisions](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- Thoughtworks put lightweight ADRs in Adopt (Nov 2017, May 2018): record design decisions for future team members, store them in source control; "no reason not to adopt" for most projects. The blip has since left the current radar. — [Radar blip](https://www.thoughtworks.com/radar/techniques/lightweight-architecture-decision-records)
- ADR community site: a decision log of ADRs captures the decision, trade-offs and consequences; links to template variants (Y-statement, MADR) and a 2015 paper comparing seven templates. — [adr.github.io](https://adr.github.io/)
- Derek Sivers' filter for commitments: "If you're not saying 'HELL YEAH!' about something, say no." — [Sivers](https://sive.rs/hellyeah)
- McKinley's retirement rule: adopting a replacement tool implies committing to migrate and remove the old one on a proposed timeline. — [McKinley](https://mcfunley.com/choose-boring-technology)

### Inferences
- A "Status: superseded" field in ADRs doubles as a tool-retirement log, which fits a solo operator with many repos (one short file per repo, or one shared decisions file with per-repo sections).
- Combining McKinley's "write down what is too hard about the current stack" with an ADR "Context" section gives a single, cheap, written rationale.

### Gaps
- No empirical evidence found (no study, no survey) that written per-project stack rationale improves outcomes. Say this plainly in the report.
- No fetched sources on how named solo founders cap tool counts or run subscription audits.

## Language/framework choice for systems/data-infra vs web SaaS

### Takeaway
I did not obtain credible-engineer guidance for this question. Only usage data was fetched.

### Cited Findings
- Rust used by 14.8% of all SO 2025 respondents (14.5% of professionals, 23.1% of learners). Admired/desired rankings were not retrievable. — [SO Survey 2025 technology](https://survey.stackoverflow.co/2025/technology)

### Inferences
- McKinley's token logic implies: for a performance-sensitive project, the language/runtime may be the one place to spend a token (the differentiator), and everything around it (DB, CI, hosting) should stay boring. This is my inference, not a cited recommendation.

### Gaps
- No sources fetched on Rust vs C++ vs Go for infrastructure, Postgres/SQLite-centric data stack arguments, or "start with a monolith" guidance. Needs targeted search (e.g. Discord/Figma/Cloudflare engineering posts, Matklad, Pragmatic Engineer).

## Portfolio management across many small projects: tiering, kill criteria, stage gates

### Takeaway
Shape Up's appetite and circuit breaker are the strongest verified kill/time-box mechanism; PG and Sivers give idea-selection filters. No published multi-project scoring rubric from founders was retrieved.

### Cited Findings
- Circuit breaker: projects not shipped in one cycle are cancelled by default; extending requires an active decision. — [Shape Up ch.3](https://basecamp.com/shapeup/1.2-chapter-03)
- PG idea filters: look for problems you have; test "who wants this right now?"; favor a small group that wants it a lot over a large group that mildly likes it; defer the "could this be big?" filter; sell before building; ask whether you would use it yourself. — [PG](https://www.paulgraham.com/startupideas.html)
- Sivers: default to no unless "hell yeah". — [Sivers](https://sive.rs/hellyeah)

### Inferences
- For a career-evidence portfolio, appetite = a fixed calendar budget per repo, with "ship or archive" as the default at the end (circuit breaker), logged in a decision record.
- Tiering (e.g. flagship / maintained / experiment) is my suggestion; no cited source.

### Gaps
- No published rubrics (Rob Walling, Justin Jackson, Indie Hackers, YC) retrieved; no evidence on time-box lengths used by solo founders for spikes.

## How practitioners choose and combine AI coding tools in 2025-2026, and how often they re-evaluate

### Takeaway
Pragmatic Engineer's Jan-Feb 2026 survey shows most engineers combine multiple tools, with Claude Code now #1 among its (subscriber) respondents; the fast churn implies re-evaluating roughly quarterly to semiannually, though no source states a re-evaluation cadence.

### Cited Findings
- Pragmatic Engineer survey (906 responses, 27 Jan to 17 Feb 2026, published 3 Mar 2026): Claude Code #1 (released May 2025, "zero to #1 in only eight months"), chatbots #2, GitHub Copilot #3 (46% nine months earlier, barely risen), Cursor #4 (mentions up about 35% in nine months), Codex #5 (about 60% of Cursor's usage). Gemini CLI, OpenCode, Antigravity about 10% each. — [Pragmatic Engineer](https://newsletter.pragmaticengineer.com/p/ai-tooling-2026)
- 70% of respondents use two to four tools, 15% one, 15% five or more; common setup is Claude Code in a terminal with an IDE open to review. — [Pragmatic Engineer](https://newsletter.pragmaticengineer.com/p/ai-tooling-2026)
- Company size: Claude Code used by 75% of the smallest companies; Copilot leads at 10,000+ employees (56%). Anecdotally Cursor power users add Claude Code while keeping Cursor. — [Pragmatic Engineer](https://newsletter.pragmaticengineer.com/p/ai-tooling-2026)
- Caveat: sample is newsletter subscribers (self-selected, likely early adopters); full report paywalled.
- Stack Overflow 2025 (broader population): 84% use or plan to use AI tools; 47.1% daily; among agent users ChatGPT 81.7%, Copilot 67.9%, Gemini 47.4%, Claude Code 40.8%; favorable sentiment fell to 59.7% from 70%+; trust in accuracy 32.7% vs 45.7% distrust; top frustration (66%) "almost right, but not quite". — [SO Survey 2025 AI](https://survey.stackoverflow.co/2025/ai)
- The two surveys differ sharply on Claude Code share (Pragmatic Engineer is much higher), reflecting different populations and time (mid-2025 vs early 2026).
- Thoughtworks Radar Apr 2026 advises putting agents on a "leash" with harnesses (skills, spec-driven development, tests, linters) and least-privilege security. — [Radar](https://www.thoughtworks.com/radar)

### Inferences
- A defensible personal policy: one primary agent (terminal) plus one review surface, with the rest on "assess"; re-run a small fixed benchmark task on each candidate on a schedule (my suggestion).
- Tool-agnostic assets (AGENTS.md, specs, tests) lower switching cost and make the tool choice a two-way door.

### Gaps
- No source states how often practitioners re-evaluate AI tools; cadence is inferred from release churn only.
- No head-to-head quality benchmarks (Claude Code vs Cursor vs Codex) fetched; avoid quoting any.
