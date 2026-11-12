# Marketing, distribution and sales for technical solo founders (as of 2026-10-29)

Scope note: this pass used only WebFetch (no web search tool was available) with about 14 fetches. Roughly half of the guessed URLs 404'd (YC library, Close founder-led-sales, SaaStr, April Dunford post, Pragmatic Engineer). The compliance and policy sections rest on primary sources. The channel-evidence, AI-outreach, records, and portfolio sections are thin and mostly appear under Gaps. Nothing there is filled in from memory.

## Distribution and marketing channels (build in public, SEO, OSS, Show HN/PH, newsletters, communities, DevRel)

### Takeaway
Primary sources I could fetch agree that early distribution is manual and narrow: pick one to three channels and do unscaled work. Show HN requires a runnable, non-trivial product, not a landing page. I could not retrieve developer-tool-specific channel comparisons or time-to-first-customer data.

### Cited Findings
- Paul Graham (essay, opinion plus anecdote): nearly all startups must recruit early users manually. Stripe's founders set users up on the spot ("give me your laptop"). Airbnb's founders went door to door in New York, and PG says about 30 days of in-person engagement "made the difference between success and failure." Big launches and partnerships usually fail to produce early growth. — [Do Things That Don't Scale](https://paulgraham.com/ds.html)
- PG also recommends tracking weekly growth. His illustration: 10% weekly growth from 100 users is about 14,000 users after a year. This is an arithmetic illustration, not a measurement. — [PG](https://paulgraham.com/ds.html)
- PG advises starting with a narrow market (Facebook at Harvard; Pinterest recruiting at a design-blogger conference) and doing manual work before automating it (Stripe's "instant" accounts were hand-processed). — [PG](https://paulgraham.com/ds.html)
- Show HN rules (primary, HN): the submission must be something people can run or try. It must be non-trivial and made by the poster, who must be around to discuss it. Landing pages, sign-up pages, newsletters and blog posts do not qualify. The rules also say "Don't post quickly-generated one-offs; anybody can do that now." Asking friends to upvote or comment is against the rules. Fewer barriers (sign-ups) get more feedback. — [Show HN guidelines](https://news.ycombinator.com/showhn.html)
- Lenny's Newsletter compilation of how big consumer apps got first users (all figures source-reported by founders or press, unverified, mostly consumer or prosumer products rather than B2B infra). Loom: about 3k users from Product Hunt launch day plus 1-2 days. Superhuman: a 4-day article "bought north of 5,000 signups". Buffer: about 100k users in 9 months from about 150 guest posts, with early posts driving little traffic. Robinhood: early spike mostly from Hacker News. The page says most startups relied on one strategy and none on more than three. — [Lenny's Newsletter](https://www.lennysnewsletter.com/p/how-the-biggest-consumer-apps-got)

### Inferences
- For a one-person evening/weekend effort, "pick one channel, repeat for weeks" is supported by both PG and the Lenny's compilation. The Buffer example suggests early content returns are slow, so budget for volume.
- Show HN fits a B2B data/infra tool only if there is a runnable demo, CLI, or repo, and the founder can be online for the first hours. Evenings and a US-timezone job conflict is a practical constraint to plan around (my inference, not sourced).
- The Lenny's examples are consumer-heavy and survivorship-biased. Do not treat them as B2B infra benchmarks.

### Gaps
- No fetched evidence on channel effectiveness specifically for developer tools or B2B infra (OSS-as-marketing, SEO, newsletters, DevRel, communities). Needs search of Indie Hackers, Starter Story, PostHog/Supabase/Plausible founder write-ups.
- No typical time-to-first-customer data found.
- No evidence on whether "build in public" changed efficacy after 2023 (X/Twitter algorithm changes, Product Hunt changes). Stale-advice flags unverified.

## Sales for technical founders (founder-led sales, ICP, discovery, CRM, outbound, pricing, design partners)

### Takeaway
Fetched sources give only fragments: the Mom Test's stated purpose and Close's cold-email cadence guidance. YC, SaaStr, Dunford, Koomen and CRM-tool comparisons were not retrievable.

### Cited Findings
- The Mom Test (author's own site): the book promises ways to avoid biased feedback, ask questions that produce real data on whether a problem exists, write outreach emails people will answer, and judge whether a prospect will buy. The page does not list the specific rules. — [momtestbook.com](https://www.momtestbook.com/)
- Close.com cold-email guide (vendor content marketing, by a practitioner claiming 20+ years' experience): aim for 50-150 words (unsourced). The article gives two inconsistent follow-up schedules (Day 1/2/4/8 in one section; Day 1/3/7/12 in the FAQ) and says to stop if someone asks not to be contacted. — [Close](https://www.close.com/blog/cold-email-templates)
- Same Close page: it cites an average cold email response rate of about 8.5% (attributed to a Backlinko study) and a 37% multi-channel lift (attributed to Optimove). It also gives an unsourced benchmark table (open 40-60%, reply 5-15%, positive reply 1-5%). All third-party or unsourced; treat as anecdotal. Open-rate figures are unreliable after Apple Mail Privacy Protection (my note, not from the page). — [Close](https://www.close.com/blog/cold-email-templates)
- Close's own 8.5% figure and its unsourced table are not mutually consistent in definition (response vs reply vs positive reply). Treat the ranges as vendor-optimistic. — [Close](https://www.close.com/blog/cold-email-templates)

### Inferences
- Under $100k ARR with limited hours, the supportable pattern from these sources is: manual, personal outreach to a narrow ICP, conversations before building, a short sequence (3-4 touches), and stopping on request.
- Vendor benchmarks (Close) likely overstate results for a cold, unknown solo sender.

### Gaps
- YC guidance (Startup School, library), Lemkin/SaaStr, Steli Efti, Pete Koomen, Lenny on pre-revenue sales, and Dunford's positioning framework: not retrieved (404s or untried). Do not cite these from this brief.
- No data on CRM choices (Notion/Airtable/HubSpot free/Attio), pricing and packaging, pipeline stages, or design-partner program norms.

## Systematization and AI (agents for research, drafting, repurposing, call notes; guardrails; failure modes)

### Takeaway
I found no fetched source documenting founders' AI-agent sales workflows or published failure cases. The only sourced items are the platform constraints that bound what an agent may safely do: Gmail bulk-sender rules, LinkedIn's automation ban, and CAN-SPAM responsibility for tools you hire.

### Cited Findings
- LinkedIn does not permit bots, crawlers, or browser extensions that scrape, modify, or automate activity. The User Agreement (Section 8.2) bars scraping profiles and data. Members who use such tools "risk having their accounts restricted or shut down." — [LinkedIn Help](https://www.linkedin.com/help/linkedin/answer/a1341387)
- Gmail bulk-sender requirements (effective Feb 1, 2024, for senders above 5,000 messages/day): SPF, DKIM and DMARC; one-click unsubscribe for marketing mail; keep spam rate below 0.30% and ideally below 0.10%. — [Google Workspace Admin Help](https://support.google.com/a/answer/81126)
- Under CAN-SPAM you "can't contract away your legal responsibility" when another company (including, by extension, a tool) sends your email. — [FTC](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business)
- Show HN guidelines explicitly discourage "quickly-generated one-offs", a sign communities are pushing back on low-effort AI-assisted posts. — [Show HN guidelines](https://news.ycombinator.com/showhn.html)

### Inferences
- A low-volume solo sender (dozens of emails a week) is far below the 5,000/day threshold, but the 0.1% / 0.3% spam-rate and authentication norms are still sensible targets. Whether Gmail applies them below threshold is not stated on the page; authentication is cheap regardless (my inference).
- Safe agent-assist boundary (inferred from the rules above): agents can research accounts from public/company sources, draft, summarize notes, and prepare CRM updates. A human should approve each send. LinkedIn automation should be avoided entirely.

### Gaps
- No sourced case studies of AI SDR deliverability bans or spammy-AI backlash (need HN threads, Lemlist/Instantly postmortems, founder write-ups).
- No sourced data on AI tooling in use (Clay, Apollo, Attio AI, Granola, Claude-based workflows) or on brand-voice controls.

## Records and learning loops (interview repositories, decision logs, weekly reviews, dashboards)

### Takeaway
Not researched successfully; no relevant source was fetched.

### Cited Findings
- None.

### Inferences
- The repo's own AGENTS.md rules (log decisions/failures with `pow log`, quote numbers only from captured runs) already form a decision-log practice that could extend to customer-interview notes. This is local context, not external evidence.

### Gaps
- No external evidence on interview repositories, positioning decision logs, or weekly review formats (candidates: Teresa Torres, Dovetail, Lenny's templates, Indie Hackers).

## Career/portfolio angle (what makes GitHub work credible)

### Takeaway
No direct evidence retrieved. The Pragmatic Engineer homepage fetch yielded only article titles.

### Cited Findings
- Pragmatic Engineer homepage listing had no content on portfolio credibility; only unrelated titles ("An educational side project", "I replaced a $120/year micro-SaaS in 20 minutes with LLM-generated code"). Nothing usable. — [Pragmatic Engineer](https://blog.pragmaticengineer.com/)
- PG's Wufoo and "do things that don't scale" anecdotes support the general idea that dated, hands-on, personally observable work is persuasive, but he is writing about startups, not hiring. — [PG](https://paulgraham.com/ds.html)

### Inferences
- Show HN's requirement that the poster "worked on [it] personally and is around to discuss" aligns with portfolio credibility norms, but this is analogy only.

### Gaps
- No hiring-manager or respected-engineer statements on dated work, hardware-labeled benchmarks, or writing. Needs targeted search.

## Compliance basics (CAN-SPAM, GDPR/PECR, LinkedIn)

### Takeaway
CAN-SPAM applies to B2B email, with no opt-in requirement but strict content and opt-out rules. UK PECR generally permits B2B cold email to corporate subscribers but not to sole traders/some partnerships without consent or soft opt-in, and UK GDPR still applies to personal business addresses. LinkedIn bans automation.

### Cited Findings
- CAN-SPAM: "The law makes no exception for business-to-business email." Requirements: truthful header info; non-deceptive subject lines; identify the message as an ad; include a valid physical postal address; give a clear opt-out method; honor opt-outs within 10 business days (mechanism must work for at least 30 days after sending); you remain responsible when others send for you. — [FTC CAN-SPAM guide](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business)
- CAN-SPAM penalties: up to $53,088 per violating email. — [FTC](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business)
- PECR (UK): corporate subscribers (bodies with separate legal status) need no consent for marketing email, but you must not conceal identity, must give a valid opt-out address, and should honor opt-outs. — [ICO B2B marketing](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/business-to-business-marketing/)
- PECR: sole traders and some partnerships are treated as individual subscribers: they need specific consent or the soft opt-in (contact details obtained in the course of a sale or negotiation, similar products, opt-out offered at collection and in every message). If unsure, treat as an individual. — [ICO](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/business-to-business-marketing/)
- UK GDPR still applies to addresses identifying a person (for example firstname.surname@company). Legitimate interests is often the appropriate lawful basis, via a three-part test, but "there is no absolute rule." The right to object to direct marketing is absolute. Keep a suppression list. ICO says this guidance is under review because of the Data (Use and Access) Act, so it may have changed since the fetch. — [ICO](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/business-to-business-marketing/)
- LinkedIn: no bots, scrapers, or automation extensions; risk of account restriction. — [LinkedIn Help](https://www.linkedin.com/help/linkedin/answer/a1341387)
- Gmail bulk-sender rules: see Systematization section. — [Google](https://support.google.com/a/answer/81126)

### Inferences
- A US-based sender emailing US businesses needs: a real postal address in every message, a working unsubscribe honored quickly, honest subject and sender, and a suppression list. These are checkable in a pre-send gate (inference).
- If prospects include EU/UK individuals, a documented legitimate-interests assessment and suppression list are prudent. EU member-state rules differ from UK PECR; this was not researched here.

### Gaps
- EU (non-UK) ePrivacy/GDPR treatment of B2B cold email, which varies by country (e.g., Germany is stricter) was not fetched.
- Post-Data (Use and Access) Act changes to PECR penalties/rules were not verified.
- Legal advice caveat: these are regulator summaries, not legal advice.
