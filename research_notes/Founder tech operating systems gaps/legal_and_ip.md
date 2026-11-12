# Legal and IP hygiene for a solo technical founder (US, employed full-time)

**Informational research only, not legal advice.** Compiled 2026-10-29. Every item is labeled by source type: [STATUTE] statute text as shown by an official or near-official site; [OFFICIAL] agency or vendor primary document; [COMMENTARY] law firm or practitioner. Many pages were fetched through a summarizing tool (it returned paraphrase plus short quotes), so the statute text should be re-read at the official site before anyone relies on it. Several fetches failed (CA legislature 403, Illinois ILGA certificate error, OpenAI 403); those are logged under Gaps. This pass did not reach law-firm commentary, Nolo, Gust, SOC 2 vendors, EFF/SFC, or Thaler docket sources. I deliberately did not fill those from memory.

## Moonlighting and IP: invention-assignment statutes and the "own time / own equipment" test

### Takeaway
CA, DE, WA, MN, and NY each have a statute that voids employer invention-assignment clauses for inventions made entirely on the employee's own time, without employer equipment, supplies, facilities, or trade secrets. The carve-back is the same in every one I read: the clause still reaches inventions that relate to the employer's business (or actual or demonstrably anticipated R&D) or result from work done for the employer. For a founder in PA, NJ, TX, or any state without such a statute, the employment contract and common law decide, so the written agreement matters more.

### Cited Findings
- [STATUTE] California Labor Code 2870: an assignment clause does not apply to an invention developed "entirely on his or her own time" without the employer's "equipment, supplies, facilities, or trade secret information," except inventions that relate at conception or reduction to practice to the employer's business or actual or demonstrably anticipated R&D, or that result from work performed for the employer. Clauses beyond that are "against the public policy of this state and is unenforceable." — [FindLaw mirror of CA Labor Code 2870](https://codes.findlaw.com/ca/labor-code/lab-sect-2870/) (official leginfo page returned 403; mirror is not the official source)
- [STATUTE] New York Labor Law 203-f ("Inventions made by employees"): same structure; assignment provisions cannot require assignment of inventions developed entirely on the employee's own time without employer equipment, supplies, facilities, or trade secret information, unless they relate to the employer's business or actual or demonstrably anticipated R&D or result from work for the employer; non-conforming provisions are "against the public policy of this state and shall be unenforceable." The page did not state an effective date; the site displays "from 2023-09-22" as a revision marker only. — [NY Senate, Labor Law 203-f](https://www.nysenate.gov/legislation/laws/LAB/203-F)
- [STATUTE] Washington RCW 49.44.140: same test; such provisions are "void and unenforceable"; employer cannot require them as a condition of hiring or continued employment; for agreements after Sept 1, 1979 the employer must give written notice at signing that the clause excludes these inventions. — [WA Legislature RCW 49.44.140](https://app.leg.wa.gov/rcw/default.aspx?cite=49.44.140) (paraphrase from fetch tool)
- [STATUTE] Delaware 19 Del. C. 805: same test; provision covering protected inventions is "against the public policy of this State and is unenforceable"; cannot be required as a condition of employment or continued employment. — [Delaware Code Title 19 Ch. 8](https://delcode.delaware.gov/title19/c008/index.html)
- [STATUTE] Minnesota Stat. 181.78: provisions void for inventions made without employer resources and on own time that either don't relate to employer's business/R&D or don't result from work for the employer; cannot be required as a condition of employment; for agreements after Aug 1, 1977 the employer must give written notice at signing. Note the paraphrase phrases the carve-back as "either ... or"; confirm exact wording against the statute. — [MN Revisor 181.78](https://www.revisor.mn.gov/statutes/cite/181.78)
- Summary of the shared test: (1) entirely own time, (2) no employer equipment/supplies/facilities/trade secrets, (3) not related to employer's business or anticipated R&D, (4) not resulting from work for the employer. All four must hold for the statute to protect the invention. — synthesized from the statute sources above.
- Note scope: these statutes are written about "inventions"; the sources I read do not say how courts apply them to software copyright, which is usually governed by work-for-hire doctrine plus contract. Not confirmed here.

### Inferences
- The "relates to employer's business" prong is the widest and least predictable gate; a founder building anything adjacent to the employer's product or customers is exposed even with perfect own-time/own-equipment discipline.
- Statutes with a written-notice rule (WA, MN) suggest the employer's agreement should itself contain a statutory carve-out notice; its absence in a WA/MN agreement is worth asking counsel about.
- The founder's state of residence may not be the state whose law governs the agreement (choice-of-law clause); nothing fetched addresses this.

### Gaps
- Illinois Employee Patent Act (765 ILCS 1060): fetch failed (certificate error). I did not verify its text, so I make no claim beyond the user's prompt naming it.
- Pennsylvania, New Jersey, Texas: I found no statute through this pass and did not run a search to confirm absence. Status is **unverified**: "no statute, relies on contract and common law" is the working assumption from the brief, not a confirmed finding. Also unchecked: NJ and PA case law on assignment clauses, moonlighting/duty-of-loyalty, and any non-compete or restrictive-covenant rules (some states have enacted noncompete limits that interact).
- Employment-lawyer practice guidance (read the agreement, written disclosure/approval, device/account separation, dated work records): no law-firm or bar sources retrieved. This is widely given advice but I have no citation, so treat as unsourced.
- Whether each statute's last amendment date, and NY 203-f's effective date, is as I describe: not verified.

## Entity formation and basics

### Takeaway
Stripe Atlas and YC materials steer venture-track founders to a Delaware C-corp; Atlas treats Delaware LLC as simpler and more flexible but notes professional investors prefer C-corps and YC may require conversion. Nothing retrieved addressed timing of formation relative to first revenue, EIN, or bank account separation.

### Cited Findings
- [COMMENTARY, vendor] Stripe Atlas: forms all LLCs in Delaware; LLC governed by an operating agreement, pass-through taxation, early losses may offset owners' other income; C-corp pays entity-level tax and is more standardized; "professional investors strongly prefer C corporations"; YC and others may require LLC-to-Delaware-C-corp conversion before investing; Delaware LLC to Delaware corporation conversion is straightforward; out-of-state founders may need to register as a foreign entity in the home state; Atlas LLCs do not include vesting; guide says it is not legal or tax advice. — [Stripe Atlas LLC vs C-corp](https://stripe.com/guides/atlas/llc-vs-c-corp)
- [OFFICIAL, vendor] Cooley GO document generator offers Delaware, Nevada, and Delaware PBC incorporation packages, employee confidential information and inventions assignment agreements (US/UK/Singapore), NDAs, advisor/consulting agreements, KISS and NVCA documents, sample cap tables, a VC due diligence request list, and YC SAFE generators. Page does not state pricing. — [Cooley GO documents](https://www.cooleygo.com/documents/)
- [OFFICIAL] YC SAFE page: SAFE created 2013 by Carolynn Levy; post-money SAFE is the YC standard since 2018; board must approve SAFE issuance; Send-a-SAFE supports only US-incorporated companies; the page does not discuss Delaware or C-corp. — [YC documents](https://www.ycombinator.com/documents)

### Inferences
- A founder employed full-time who has no revenue and no outside investors may defer entity formation, but a liability shield and a clean assignment of IP to the entity are both reasons counsel often cite; I have no retrieved source for that, so it is an inference only.

### Gaps
- Not retrieved: Clerky, Clerk, Gust, Nolo, YC startup-school guidance on Delaware vs home state, EIN steps (IRS), business bank account/commingling (veil-piercing) guidance, and any source on forming before first revenue. State-specific foreign-registration and franchise tax costs also unverified.
- Whether forming an entity while employed triggers any employer-agreement issue (e.g., outside-activity disclosure): no source.

## Contracts and templates

### Takeaway
Common Paper publishes a broad free standard set under CC BY 4.0, including items that fit a solo B2B founder (Mutual NDA, Terms of Service, Cloud Service Agreement, DPA, Design Partner, Pilot, Professional Services, SOW, Order Form, Independent Contractor, AI Addendum). Cooley GO covers inventions assignment and advisor agreements.

### Cited Findings
- [OFFICIAL, vendor] Common Paper standard agreements: Mutual NDA, Terms of Service, Design Partner Agreement, Cloud Service Agreement, SLA, Data Processing Agreement, BAA, Professional Services Agreement, AI Addendum, Partnership Agreement, Software License Agreement, Pilot Agreement; plus Letter of Intent, one-way NDA, Term Sheet, Independent Contractor Agreement, Amendment, SOW, Order Form. Released free under CC BY 4.0. AI Addendum described as covering "AI-related data use, IP, and risk." — [Common Paper standards](https://commonpaper.com/standards/)
- [OFFICIAL] YC's SAFE variants (post-money cap, discount, MFN) and pro rata side letter. — [YC documents](https://www.ycombinator.com/documents)

### Inferences
- CC BY 4.0 permits copying and modifying with attribution, so templates can be stored as versioned plain files in git with the attribution kept; the sources do not describe how founders actually store or version them.

### Gaps
- Bonterms (Cloud Terms, NDA), YC-specific NDA/contractor templates, privacy policy generators, and any practitioner source on storing and versioning legal documents: not retrieved.
- Whether template terms suit a given deal (e.g., liability caps, governing law) needs counsel.

## Open source and licensing

### Takeaway
Only DCO and FSL were checked. DCO is a lightweight per-commit certification; FSL is a source-available "Fair Source" license converting to Apache 2.0 or MIT after two years.

### Cited Findings
- [OFFICIAL] Developer Certificate of Origin v1.1 (Linux Foundation, 2004/2006): contributor certifies they wrote it or have the right to submit it under the project's license (a), derivation from properly licensed prior work (b), received from a certifying third party (c), and acknowledges the contribution record is public and kept indefinitely (d). — [developercertificate.org](https://developercertificate.org/)
- [OFFICIAL] Functional Source License: a "Fair Source" license for SaaS companies; two-year restricted period during which you can do anything except undermine the producer; then converts to Apache 2.0 or MIT. Page's links point to Sentry, suggesting Sentry created it (not stated directly). — [fsl.software](https://fsl.software/)

### Inferences
- DCO adds no copyright assignment or relicensing right, whereas a CLA typically does; this distinction is from general knowledge, not from a fetched source, so confirm before use.

### Gaps
- MIT/Apache-2.0/AGPL/BSL comparisons, CLA sources, dependency license scanning tools, SBOM guidance (CISA/NTIA), trademark vs copyright vs patent for small founders, EFF and Software Freedom Conservancy views: not retrieved.

## AI-specific legal

### Takeaway
Anthropic's commercial terms assign output rights to the customer, treat customer content as confidential, say Anthropic may not train on Customer Content from Services, and include an IP indemnity with notable exclusions. Consumer plans (Free/Pro/Max, including Claude Code on those accounts) are different: users choose whether data trains models. The Copyright Office's Part 2 report (Jan 2025) is the main official guidance on copyrightability; I could confirm its existence and structure but not its conclusions from the text.

### Cited Findings
- [OFFICIAL] Anthropic Commercial Terms (page showed effective date June 17, 2025; verify current version): customer owns Outputs and retains Inputs; Anthropic assigns "its right, title and interest (if any)" in Outputs, subject to compliance; Customer Content is Customer's Confidential Information; Anthropic "may not train models on Customer Content from Services"; K.1 IP indemnity against third-party claims that paid use of the Services or Outputs violates IP rights; exclusions include customer modifications, combination with non-Anthropic technology, customer-provided Inputs, knowing infringing use, patented inventions in Outputs, and trademark claims from trade use of Outputs. — [Anthropic Commercial Terms](https://www.anthropic.com/legal/commercial-terms)
- [OFFICIAL] Anthropic consumer terms update (published Aug 28, 2025; deadline Oct 8, 2025): for Free, Pro, Max (including Claude Code from those accounts), users choose whether chats and coding sessions are used for training; opt-in retention five years, otherwise 30 days; Team, Enterprise, API, Bedrock, Vertex AI, Gov and Education are excluded (under Commercial Terms). — [Anthropic: updates to consumer terms](https://www.anthropic.com/news/updates-to-our-consumer-terms)
- [OFFICIAL] US Copyright Office AI initiative: Part 1 Digital Replicas (July 31, 2024); Part 2 Copyrightability (report dated January 2025; page date Jan 29, 2025); Part 3 Generative AI Training, pre-publication version released May 9, 2025, final to follow with no substantive changes expected. Part 2's table of contents covers prompts, expressive inputs, and modifying or arranging AI-generated content, and an arguments-for-legal-change section. — [Copyright Office AI page](https://www.copyright.gov/ai/); [Part 2 PDF](https://www.copyright.gov/ai/Copyright-and-Artificial-Intelligence-Part-2-Copyrightability-Report.pdf)

### Inferences
- If a founder uses a personal consumer Claude account with the training toggle on for employer or customer code, that data could be used for training under the terms described. The employer-confidentiality and customer-NDA exposure follows from that, but no source here addresses employer agreements directly.
- Anthropic's assignment is "if any", so the terms do not themselves resolve whether copyright subsists in the output.

### Gaps
- Part 2's actual conclusions (human authorship requirement, prompts alone insufficient, protection for human-selected arrangement/modification): I only saw the cover and table of contents; do not cite conclusions from this note. Part 3's content and any final version: not read.
- Thaler v. Perlmutter (D.C. Cir. 2025) and any 2025-2026 court or Copyright Office developments, including cert activity: not retrieved. Flagged as fast-moving and unconfirmed.
- OpenAI services agreement and Copyright Shield: fetch returned 403.
- Policies startups publish on AI use, customer-data handling, and employer-policy rules on AI tools: not retrieved.

## Security and privacy compliance for early B2B

### Takeaway
Only CCPA applicability thresholds were confirmed. A solo B2B founder with no consumer data and under the revenue threshold is likely outside CCPA by its own terms, but contract-based obligations (DPAs, security questionnaires) arrive earlier.

### Cited Findings
- [OFFICIAL] CCPA applies to for-profit businesses doing business in California that meet any one: gross annual revenue of $26.625 million or more (figure effective Jan 1, 2025, CPI adjusted); buying, selling, or sharing personal information of 100,000+ California residents or households; or 50%+ of revenue from selling or sharing California residents' personal information. — [CPPA FAQ](https://cppa.ca.gov/faq.html)

### Inferences
- Common Paper's DPA and Cloud Service Agreement exist as free starting points when a customer asks for data terms.

### Gaps
- SOC 2 timing and cost, Vanta/Drata/Secureframe and cheaper alternatives, GDPR triggers (outside US-only scope, but US firms with EU users), state privacy laws beyond CA (including whether CPI adjustments after 2025 apply), and standard security questionnaire practice (CAIQ, SIG, etc.): not retrieved. The CPPA figure may have been CPI-adjusted again; confirm the current number.

## Record-keeping and diligence

### Takeaway
No source retrieved describes how founders organize a legal folder or what diligence counsel wants. The retrievable adjacent facts are that Cooley GO publishes a VC due diligence request list and sample cap tables, and that YC requires board approval to issue SAFEs.

### Cited Findings
- [OFFICIAL, vendor] Cooley GO lists a "VC due diligence request list," sample cap tables, and employee confidential information and inventions assignment agreements among its documents. — [Cooley GO documents](https://www.cooleygo.com/documents/)
- [OFFICIAL] Board approval is required for issuing SAFEs. — [YC documents](https://www.ycombinator.com/documents)

### Inferences
- A sensible minimal structure (unsourced, my suggestion): employment agreement and any outside-activity approval; signed contractor assignments; incorporation, EIN, and bank docs; cap table and board consents; executed customer paperwork with expiry/renewal dates; third-party license inventory; a dated decision log for legal calls. This matches the items the brief lists for diligence but I have no source confirming counsel's expectations.

### Gaps
- Law firm diligence checklists (clean IP chain, signed assignments, cap table), renewal and expiry tracking practices, and decision-log norms: not retrieved. The Cooley GO due diligence list itself was not opened.
- Per the repo's own working agreement, any claim about dates or numbers in public materials should come from captured evidence; none of this research involves benchmarks.
