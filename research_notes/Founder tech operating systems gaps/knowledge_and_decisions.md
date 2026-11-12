# Knowledge and decision systems: records, staleness, agent-readable KBs (as of 2026-10-29)

Scope note: about 19 fetches, all primary sources. No web-search tool was available, so coverage is limited to pages fetched directly. Items not verified are listed under Gaps, not asserted.

## Q1. Decision records: formats, minimal templates, supersession conventions, evidence they work

### Takeaway
The durable convention across Nygard, MADR, Microsoft and Oxide is short, numbered, append-only records. Changed decisions get a new record that links to the old one, and the old one is marked superseded, not edited or deleted. Solo-scale practice reduces to Nygard's 5 fields or MADR "minimal", with status and date. Rigorous measured evidence that ADRs "work" was not found; support is practitioner assertion.

### Cited Findings
- Nygard's original ADR (2011, old source) has five sections: Title (short noun phrase), Context (forces, neutral facts), Decision (active voice, "We will..."), Status, Consequences (including negative and neutral) — [Nygard/Cognitect](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- Nygard statuses: proposed, accepted, deprecated or superseded; a superseding ADR is referenced from the old one — [Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- Nygard's rationale for brevity: "Large documents go out of date, and most readers never open them"; small modular records are likelier to be maintained and read — [Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- Numbering is sequential and monotonic, and numbers are never reused. Reversed decisions are kept, marked superseded, because "it's still relevant to know that it was the decision" — [Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- MADR 4.0.0 (released 2024-09-17) full template: Title; Context and Problem Statement (required); Decision Drivers (optional); Considered Options (required); Decision Outcome with chosen option and justification (required); Consequences, Confirmation, Pros/Cons of Options, More Information (all optional). Front matter: status `{proposed | rejected | accepted | deprecated | ... | superseded by ADR-0123}`, date (last updated), optional decision-makers/consulted/informed. Bare and minimal template variants exist — [MADR](https://adr.github.io/madr/)
- MADR gives no explicit trigger criteria for when to write an ADR. It says "any (important) decision should be captured in a structured way" and that "architecturally significant" is debated — [MADR](https://adr.github.io/madr/)
- Microsoft Azure Well-Architected guidance (updated 2026-04): ADR is an "append-only log. Don't go back and edit accepted records"; if a decision changes, write a new record that supersedes and link the two — [Microsoft Learn](https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record)
- Same Microsoft page: include only choices that affect structure, key quality attributes, or are hard to reverse. Record the confidence level of the decision, since low confidence flags it for revisit. Split multi-phase decisions into separate records. Keep records "pithy, assertive, on-topic, and factual". The record must stand alone without links to design docs. Retroactively generate ADRs for brownfield work — [Microsoft Learn](https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record)
- Microsoft's failure mode for unrecorded decisions: they get forgotten, leading to repeated debates or changes that "unknowingly contradict the original intent" — [Microsoft Learn](https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record)
- Oxide RFDs: states are prediscussion, ideation, discussion, published, committed, abandoned. "committed" means implemented, so the RFD describes how a system works. "abandoned" marks non-viable ideas. Numbered, one directory per RFD (`rfd/0042/README.adoc`), created on a branch named for the number, merged to master by PR after about 3-5 business days of comment. Published RFDs can still be updated via separate PR branches. Triggers include process changes, architecture/design decisions, customer-facing or internal API/CLI changes, test designs — [Oxide RFD 1](https://rfd.shared.oxide.computer/rfd/0001)
- AGENTS.md/CLAUDE.md for this very repo already encode the "log decisions" rule via `pow log`. This is a local fact from the session's CLAUDE.md, not a web source.

### Inferences
- Nygard and Microsoft differ on immutability. Nygard keeps the old record and marks it; Microsoft says never edit accepted records. Oxide allows in-place updates to published RFDs and has a "committed" state, so it is closer to a living spec. For a solo user: append-only ADRs for choices, living docs for "how it works now".
- Scaled down, an ADR is about 10 lines: title, date, status (with `superseded by NNNN`), context, decision, consequences, confidence. This fits MADR minimal and Microsoft's advice.
- Oxide's RFD gets its benefit from review by colleagues. A solo user gets only the "write it down, number it" half; the review step has no solo equivalent.

### Gaps
- No measured evidence (surveys, studies) on ADR effectiveness or shelfware rates was found. The claims above are practitioner or vendor assertion.
- Not fetched: Amazon 6-pagers, one-way/two-way door memo (Bezos shareholder letter), Stripe, Basecamp (Shape Up/handbook), Google design docs, adr-tools, log4brains. No sourced claims for these.
- The MADR minimal template contents were not shown on the fetched page.

## Q2. Staleness: review dates, as-of stamps, bitemporal graphs, evergreen notes, PARA/Zettelkasten/Johnny.Decimal, what survives for years

### Takeaway
The sourced staleness mechanisms are: supersession links (ADRs), validity windows with invalidation not deletion (Graphiti/Zep), periodic audit of instruction files (Claude Code), and review-cadence metadata (Microsoft docs carry `ms.update-cycle: 1095-days` front matter). Evidence on what solo founders sustain for years is thin in what was fetched; Steph Ango's low-structure vault is the one concrete, long-running example.

### Cited Findings
- Graphiti keeps facts with validity windows: "When information changes, old facts are invalidated, not deleted." It can answer what is true now or what was true at a past time, and every fact links to the source episode. Marketing-level description; the bitemporal field names were not confirmed on the page — [Graphiti repo](https://github.com/getzep/graphiti)
- Zep paper (Jan 2025): Graphiti is a "temporally-aware knowledge graph engine." Reported DMR 94.8% vs MemGPT 93.4%; LongMemEval accuracy gains up to 18.5%; response latency down 90% vs baseline. These are vendor-authored results — [arXiv 2501.13956](https://arxiv.org/abs/2501.13956)
- Graphiti requires a graph database (Neo4j 5.26, FalkorDB, Neptune plus OpenSearch; Kuzu deprecated), Python 3.10+, and by default an OpenAI key. Self-hosted only — [Graphiti repo](https://github.com/getzep/graphiti)
- Microsoft docs use per-page metadata `ms.date` and `ms.update-cycle: 1095-days` (a 3-year review cycle) — [Microsoft Learn page front matter](https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record)
- Matuschak: evergreen notes are "written and organized to evolve, contribute, and accumulate over time, across projects"; principles listed: atomic, concept-oriented, densely linked, associative ontology preferred over hierarchical taxonomy. He admits "It's hard to write notes that are worth developing over time" — [Matuschak](https://notes.andymatuschak.org/Evergreen_notes)
- Steph Ango (Obsidian CEO): very few folders, no nested subfolders, categories via a property, `YYYY-MM-DD` dates everywhere, daily notes used only as link targets, one vault, avoids delegating review and maintenance to LLMs. "A consistent style... collapses hundreds of future decisions into one" — [Ango, "How I use Obsidian"](https://stephango.com/vault)
- Claude Code docs instruct periodic review of CLAUDE.md files and rules to remove outdated or conflicting instructions, and ship `/doctor prompt-audit`, which flags instructions written for older models, references to nonexistent files or commands, and contradictions — [Claude Code memory docs](https://code.claude.com/docs/en/memory)
- Claude Code auto memory prompts the model, when MEMORY.md nears its limit, to keep one line per entry, move detail to topic files, and "merge or drop stale entries" — [Claude Code memory docs](https://code.claude.com/docs/en/memory)

### Inferences
- Two temporal patterns scale down to markdown: (1) supersession links between immutable records; (2) a `date`/`as-of` and optional `review-by` front-matter field on mutable fact notes, with a grep for overdue dates. Graphiti-style bitemporality (valid time vs recorded time) is heavy for under-10k notes. A cheap approximation is `valid_from`, `superseded_by`, `recorded` fields.
- Ango's approach (flat, properties, ISO dates) works well for grep and for LLM tools, since consistent property names are greppable.

### Gaps
- Not fetched: PARA (Forte), Zettelkasten sources, Johnny.Decimal, Logseq/Notion setups, Simon Willison / Eugene Yan / swyx / Geoffrey Litt posts. No sourced claims.
- No longitudinal data on what solo founders keep up for years was found, only Ango's self-report.

## Q3. LLM-agent knowledge bases: AGENTS.md/CLAUDE.md, memory, progressive disclosure, MCP memory servers, FTS vs embeddings

### Takeaway
Anthropic's own guidance favors a small always-loaded file plus just-in-time retrieval through grep/glob and file paths, not a pre-built vector index. The Claude Code team reports agentic search beat embedding RAG "by a lot" but on internal judgment, not formal benchmarks. No benchmark comparing FTS vs embeddings for under 10k notes was found.

### Cited Findings
- Claude Code loads CLAUDE.md at session start; target is under 200 lines per file, since longer files consume context and reduce adherence. Use path-scoped `.claude/rules/` (`paths:` frontmatter) for instructions that apply to part of the codebase — [Claude Code memory docs](https://code.claude.com/docs/en/memory)
- `@path` imports allow recursion to a maximum depth of four hops, but they do not reduce context cost because imported files load with the importer — [Claude Code memory docs](https://code.claude.com/docs/en/memory)
- Auto memory: Claude writes its own notes per repository (shared across worktrees); the first 200 lines or 25KB of MEMORY.md load every session, and detail belongs in separate topic files read on demand. The index is a pointer file — [Claude Code memory docs](https://code.claude.com/docs/en/memory)
- CLAUDE.md is context, not enforcement; it is delivered as a user message, with no guarantee of compliance. For hard blocks use a PreToolUse hook. Contradictory instructions may be resolved arbitrarily — [Claude Code memory docs](https://code.claude.com/docs/en/memory)
- Claude Code reads AGENTS.md directly (needs v2.1.277+), or via `@AGENTS.md` import in CLAUDE.md; the import is recommended where direct reading is unavailable — [Claude Code memory docs](https://code.claude.com/docs/en/memory)
- AGENTS.md: open plain-Markdown "README for agents"; the site claims 60k+ open-source projects (self-reported); nearest file in the tree wins; explicit user prompts override; the OpenAI main repo had 88 AGENTS.md files; supported by Codex, Cursor, Copilot agent, Gemini CLI, Aider, Zed, and others — [agents.md](https://agents.md)
- Anthropic context engineering post (2025): agents keep "lightweight identifiers (file paths, stored queries, web links)" and load data at runtime; progressive disclosure lets agents "incrementally discover relevant context"; file sizes, names and timestamps are relevance signals. Structured note-taking (NOTES.md, to-do lists) persists outside the context window. Compaction retains decisions and unresolved bugs. Claude Code is hybrid: CLAUDE.md up front, glob/grep on demand, avoiding "stale indexing" issues; runtime exploration is slower than precomputed retrieval — [Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Boris Cherny (Claude Code creator): they tried RAG with an off-the-shelf embedding provider, and agentic search "outperformed everything. By a lot." Based on internal impressions, not formal benchmarks. Reasons given: index drift, the security liability of an index living somewhere, cost is latency and tokens. CLAUDE.md is "the simplest thing that could work" — [Latent Space interview](https://www.latent.space/p/claude-code)
- Basic Memory: knowledge graph in plain Markdown files, local-first, usable in any editor, connects via MCP to Claude, Cursor, VS Code, Obsidian and others; cloud option exists. The SQLite index and note syntax were not confirmed on the fetched page — [Basic Memory docs](https://docs.basicmemory.com/)
- Graphiti uses hybrid retrieval (semantic embeddings plus BM25 plus graph traversal) with no LLM summarization at query time — [Graphiti repo](https://github.com/getzep/graphiti)

### Inferences
- For a vault under about 10k notes, the sourced evidence supports: short index file always loaded, ISO-dated flat Markdown, grep/ripgrep (optionally SQLite FTS5) for retrieval, and agents following links. The one-person inference is that embeddings add an index to keep in sync, with a security cost for an encrypted vault (Cherny's index-liability point), against little demonstrated gain at this scale. This is reasoning, not measurement.
- Relevant to Ryan's setup: the MEMORY.md-as-index pattern he already uses matches Anthropic's documented design (index loads, topic files read on demand). The 200-line cap and "drop stale entries" prompt are built in.
- Mem0/Zep/Graphiti-style servers address multi-session personalization and fact-change tracking. They need extra infrastructure (graph DB, API keys) and are probably overweight for a solo markdown vault.

### Gaps
- No head-to-head benchmark of FTS vs embeddings vs grep for small personal corpora was found. Not fetched: llms.txt spec, Mem0 docs, Hamel Husain on retrieval/BM25, Simon Willison on embeddings, Hacker News threads.
- Cherny's claim is anecdotal; Zep numbers are vendor-run and use benchmarks (DMR) that Zep authors have themselves positioned against MemGPT. No independent replication was checked.

## Q4. Where things go: journal/log vs decision record vs KB note vs repo docs

### Takeaway
No single published decision rule was found that covers all four categories. Fragments exist: the ADR/Microsoft threshold for decision records, Oxide's RFD triggers, and Claude Code's CLAUDE.md-versus-auto-memory split.

### Cited Findings
- Decision record threshold: only choices that affect structure, key quality attributes, or are hard to reverse; store with the workload's own docs repository — [Microsoft Learn](https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record)
- Oxide: RFD for process, architecture, API changes; after implementation the RFD moves to "committed" and explains how the system works — [Oxide RFD 1](https://rfd.shared.oxide.computer/rfd/0001)
- Claude Code split: CLAUDE.md = instructions and rules written by you; auto memory = learnings and patterns written by Claude; project-scoped, per repository — [Claude Code memory docs](https://code.claude.com/docs/en/memory)
- Anthropic: persisted agent notes (NOTES.md-style) are working memory outside the context window, separate from instructions — [Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Ango: daily notes are link targets only, not for writing; reference material lives in References/Clippings; categories via property, not folders — [Ango](https://stephango.com/vault)

### Inferences
- A workable rule assembled from the above (not a published standard): log = chronological, append-only, what happened (including failures); decision record = numbered, immutable, why we chose X, with status; KB/fact note = mutable, current truth, dated; repo docs/AGENTS.md = instructions and how the system works now, living with the code; agent memory = pointer index plus topic files. Cross-repo or personal knowledge goes in the vault; anything an agent must obey in one repo goes in that repo's AGENTS.md.

### Gaps
- Not fetched: GitLab handbook-first page (fetch returned only navigation), Basecamp, Diataxis, Notion/Logseq conventions, any explicit "where does this go" flowchart.

## Q5. Failure modes: over-organizing, hoarding, unmaintained indexes, docs drift

### Takeaway
Sourced failure modes are: long documents that go stale and unread, unrecorded decisions that get re-litigated, contradictory instruction files, oversized always-loaded files that reduce adherence, and indexes that drift from the source.

### Cited Findings
- Large docs "go out of date, and most readers never open them" — [Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- Unrecorded decisions get forgotten, then re-debated or unknowingly contradicted — [Microsoft Learn](https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record)
- Records that omit rationale lose value, since later readers cannot judge if the decision still applies; also avoid hiding consequences — [Microsoft Learn](https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record)
- Over 200 lines or conflicting rules in CLAUDE.md reduce adherence; Claude "may pick one arbitrarily" between conflicting instructions; stale references to missing files/commands are what `/doctor prompt-audit` looks for — [Claude Code memory docs](https://code.claude.com/docs/en/memory)
- Content past 200 lines or 25KB of MEMORY.md is silently dropped on next load — [Claude Code memory docs](https://code.claude.com/docs/en/memory)
- Embedding indexes drift out of sync with changing content — [Latent Space](https://www.latent.space/p/claude-code); Anthropic cites avoiding "stale indexing" — [Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Matuschak: "It's hard to write notes that are worth developing over time" — [Matuschak](https://notes.andymatuschak.org/Evergreen_notes)
- Ango counters over-organizing with a consistent minimal style and few folders — [Ango](https://stephango.com/vault)

### Inferences
- Common thread: every extra layer (nested taxonomy, vector index, graph DB, long instruction file) adds a thing to keep in sync. Cheap guards: a size cap on index files, a periodic audit command, and `superseded_by` links so stale items are marked rather than silently contradicting live ones.

### Gaps
- No quantified shelfware or abandonment rates for ADRs, wikis, or note systems were found. Note hoarding / collector's fallacy sources (Forte, Matuschak critiques, HN threads) were not fetched.
