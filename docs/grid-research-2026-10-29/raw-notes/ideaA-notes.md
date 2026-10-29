# Idea A research notes: clean-energy tax-credit compliance ledger (PFE / MACR etc.)
Research date: 2026-10-29. Labels: VERIFIED = primary source fetched and read; SECONDARY = reputable report / company blog; ESTIMATE = my arithmetic; UNVERIFIED = not found.

TOOLING CAVEAT (affects completeness): no working web-search tool was available. WebSearch absent; DuckDuckGo (captcha), Google (blocked), Brave (429) failed. Bing via WebFetch works only for short natural queries and mostly returns dictionary pages for long queries. So vendor discovery (Q4) and forum/search-demand evidence (Q9) are WEAK. Primary sources (IRS PDFs, Cornell LII, Federal Register API, IRS SOI PDF) worked well. Federal Register site started blocking mid-session.

## Q1. Current status of PFE / MACR guidance

- VERIFIED: IRS Notice 2026-15, "Guidance to Apply Interim Safe Harbors for Purposes of Determining a Taxpayer's Material Assistance from a Prohibited Foreign Entity; Other Prohibited Foreign Entity Guidance". PDF https://www.irs.gov/pub/irs-drop/n-26-15.pdf (PDF creation date Feb 12, 2026; release date Feb 12, 2026 corroborated by Crux blog https://www.crux.com/blog/treasury-releases-initial-foreign-entity-of-concern-rules (dated Feb 12, 2026) and Tax Executive/Crux post "published February 12, 2026").
  - It is INTERIM. Sec 3 describes rules Treasury "intend[s] to include in forthcoming proposed regulations"; Sec 4 gives three interim safe harbors (Identification Safe Harbor using 2023-2025 safe-harbor tables, Cost Percentage Safe Harbor, Certification Safe Harbor); Sec 5 touches foreign-influenced-entity and anti-circumvention; Sec 7 requests comments by March 30, 2026 (regulations.gov docket IRS-2026-15).
  - ~4,570 lines of text (about 96 printed pages) -> very complex; heavy worked examples.
- VERIFIED (statute, quoted in Notice sec 2.02 and read from the notice): IRC 7701(a)(52)(D)(iii)(I) requires Treasury to issue safe-harbor tables (+ other rules) NO LATER THAN DECEMBER 31, 2026. (D)(iii)(II): until the tables issue, and for construction beginning on or before 60 days after the tables issue, a taxpayer may use the Notice 2025-08 tables and rely on a supplier certification. So the Dec 31, 2026 date is statutory (confirmed), but it is a deadline for Treasury, not a promise of simple tables.
- VERIFIED: No proposed regulation on PFE/MACR exists as of 2026-10-21. Federal Register API query for all IRS "Proposed Rule" documents published 2026-01-01..2026-10-21 returned 49 docs; none on 45X/45Y/48E/PFE/7701/begin-construction (only 45Z proposed rule Feb 4, 2026 and hearing notices). Query URL: https://www.federalregister.gov/api/v1/documents.json?conditions[agencies][]=internal-revenue-service&conditions[type][]=PRORULE&conditions[publication_date][gte]=2026-01-01 . Also term search "45Y OR 48E OR 45X" in IRS FR docs since 2026-01-01 returned 0. Caveat: Notices are not published in the FR, so a later Notice would not show here.
- VERIFIED: IRS OBBBA provisions page (last reviewed 22-Oct-2026) lists only Notice 2026-15 for sec 70512 PFE. https://www.irs.gov/newsroom/one-big-beautiful-bill-provisions
- SECONDARY: Tax Executive (Aug 11, 2026): still interim; open issues = effective-control licensing definition, 48E recapture mechanics, who bears loss on a false supplier cert, taint through corporate groups; "no timeline". https://www.taxexecutive.org/managing-feoc-restrictions-and-irs-notice-2026-15/
- SECONDARY: projectfinance.law (Feb 13, 2026): further FEOC notices "on a rolling basis", no target dates; comprehensive proposed regs not expected soon. https://www.projectfinance.law/publications/new-feoc-guidance-notice-2026-15
- SECONDARY: Crux (Sep 3, 2026) quoting practitioner: notice "signals new safe harbor tables will be published by year-end"; "No proposed regulations ... issued yet". https://www.crux.com/blog/feoc-pfe-state-of-play-2q-2026
- Next dated milestone: Dec 31, 2026 statutory deadline for safe-harbor tables (VERIFIED statute). Whether Treasury meets it: UNKNOWN. No later date found. Prior art: Notice 2025-08 tables came Jan 2025.
- CLAIM RE-CHECK of earlier pass:
  - "Notice 2026-15 implements MACR test": TRUE-ish. It is interim guidance + statement of intent on MACR, not final.
  - "Treasury to issue final safe-harbor tables by Dec 31, 2026": PARTLY. Statute says "safe harbor tables (and such other guidance)" by that date; nothing says "final". Tables could be partial.
  - "claimants using safe harbors attach statements to Forms 7211, 3468 or 7207": VERIFIED (Notice sec 8.02 and 4.03(2)(a)); statement identifying safe harbor and application attached to the return for the FIRST year the taxpayer claims a credit for that facility/EST/component; certifications likewise attached (consistent with Reg 1.45X-4(c)(4)(i)). Also "any other applicable form".
  - "IRC 6695B penalty greater of 10% of underpayment or $5,000, for certifications after Dec 31, 2025": VERIFIED (statute at https://www.law.cornell.edu/uscode/text/26/6695B ; Notice sec 2.03). Nuances the earlier pass omitted: (a) penalty is on the SUPPLIER who gives the certification, not the claimant; (b) only if supplier knew or reasonably should have known the cert was false/inaccurate; (c) only if the error caused disallowance + understatement exceeding the lesser of 5% of tax or $100,000; (d) reasonable-cause exception; (e) 6-year assessment period.
- Thresholds (VERIFIED, Cornell LII 7701(a)(52)(B)): qualified facility (45Y/48E) construction beginning 2026=40%, 2027=45%, 2028=50%, 2029=55%, after 2029=60%; energy storage 55/60/65/70/75%. Eligible components (45X) solar component sold 2026=50%, 60/70/80%, 85% after 2029 (other components truncated; not read). URL https://www.law.cornell.edu/uscode/text/26/7701 . Tax Executive piece (secondary) agrees: facility 40->60, storage 55->75.
- Scope limits VERIFIED/SECONDARY: PFE material-assistance rules apply to facilities where construction begins after Dec 31, 2025 and to 45X components sold in tax years beginning after July 4, 2025 (Notice sec 8.01). Projects that began construction by end 2025 need no MACR (projectfinance.law, Feb 13, 2026). Notice 2025-42 (Aug 15, 2025, VERIFIED PDF) separately governs begin-construction for wind/solar termination: wind/solar construction beginning after July 4, 2026 must be placed in service by end of 2027; physical work test; 5% safe harbor removed except solar <=1.5 MW AC; continuity safe harbor 4 calendar years; effective for construction not begun before Sept 2, 2025. https://www.irs.gov/pub/irs-drop/n-25-42.pdf . IMPLICATION: the wind/solar begin-construction cliff passed on July 4, 2026, so the volume of NEW MACR-governed wind/solar projects is now smaller; MACR work remains for storage, geothermal, nuclear, hydro, and wind/solar that began construction in 2026 and 45X manufacturers.

## Q2. Buyer / claimant counts

- VERIFIED (IRS SOI Pub 5108, Corporation Line Item Estimates, TAX YEAR 2022, rev. 9-2025; C-corp 1120-series only; EXCLUDES S corps, REITs, RICs, and ALL partnerships/LLC-pass-throughs and individuals): Form 3800 line 1 (general business credit current year) = about 25,008 corporate returns, $48.0 billion (amounts in $ thousands in the table: 48,031,205). Form 3800 line 6 (incl. carryforwards) about 41,089 returns. Form 3468 line 14 (investment credit total) about 1,156 returns, $8.94B. Source: https://www.irs.gov/pub/irs-pdf/p5108.pdf (pages 156-163). Caveats: tax year 2022 is mostly PRE-IRA effects; 45X/45Y/48E forms (7207/7211) did not exist; line 14 count semantic uncertain (I read "14 = 1,156" count column, amount 8,942,276). Not usable as a direct count of 2026 claimants.
- NOT FOUND: any IRS SOI count of filers of Forms 7207, 7211, 8933, or of 45X/45Y/48E claimants. The SOI Clean Energy page (https://www.irs.gov/statistics/soi-tax-stats-clean-energy-tax-credit-statistics, updated Dec 4, 2025) covers only Form 5695 residential credits, 48(e) LIC bonus allocations, and 30D, tax year 2023. SOI corp source book ends 2014. PRA notice (FR 2026-08-10, doc 2026-16262) lists Forms 3468/3800/7207/7211 by title only; no per-form respondent counts (only aggregate 13.64M respondents for the whole OMB 1545-0123 collection). Federal Register 'Form 3468' PRA 2021-10-28 not read.
- SECONDARY (Crux, interested party, marketplace vendor): transferable credit market ~$42B in 2025 (up from $28B 2024); Q2 2026 record $14.9B; H1 2026 transfer volume $21B; 2026 total monetization forecast ~$70B (up 11% from $63B 2025); PFE-exposed credits ~$4B closed in H1 2026 (~20% of market). https://www.crux.com/blog/tax-credit-investors-need-to-know-in-h2-2026 ; https://www.crux.com/blog/tax-credit-buyer-benchmarking-2025 (Oct 13, 2026); https://www.crux.com/blog/developers-and-manufacturer-takeaways-from-2025-market-intelligence-report (Mar 5, 2026).
- SECONDARY (Crux): BUYER COUNTS are only large corporates. H1 2026: 98 Fortune 1000 companies bought credits (11% of 898 buyer-universe companies); nearly 200 all of 2025 (Oct 13, 2026 post). Participation by size: large-cap 13.8%, mid 9.2%, small-cap 4.2%. 
- CONTRADICTION: Crux Mar 19, 2026 post says ~243 F1000 companies were active investors through Q3 2025 ("nearly a quarter of the index") vs Oct 13, 2026 post "nearly 200 participated in all of 2025". Different denominators/definitions are possible; unresolved. https://www.crux.com/blog/cruxs-2025-market-intelligence-report-what-tax-credit-buyers-need-to-know
- Deal size: Crux says $25-100M deals most active segment in H2 2025 (SECONDARY). Deal counts, number of sellers, number of sub-$10M deals: NOT PUBLISHED in free material (full report is gated).
- Number of small developers, installers, contractors, manufacturers claiming credits: NOT FOUND. Crux survey of "about 50 developers and US manufacturers" Oct 2025 (SECONDARY) -- sample only.
- Intermediaries: Crux is the main named marketplace. Others (Basis, Reunion, brokers) not verified; no direct fetch succeeded.
- Quality of hypothesis premise "thousands of small developers must prove MACR": NOT SUPPORTED by any count I could fetch. Residential 25D ended for expenditures after Dec 31, 2025 (VERIFIED, IRS OBBBA page); 25D is Form 5695 individuals and has no MACR gate. Residential solar leased/PPA under 48E is where small installers/financiers sit, but I did not find a count.

## Q3. Who does the work today; fees

- SECONDARY (Tax Executive, Aug 11, 2026): in-house tax function owns the process; OUTSIDE TAX COUNSEL gives a written "should"-level opinion and drafts reps/indemnities; a NATIONAL ACCOUNTING FIRM performs an agreed-upon-procedures (AUP) review of the MACR calculation (not an audit/opinion), often a closing deliverable naming the buyer; suppliers/sponsors give certifications; transferees/lenders/tax-equity do their own diligence. https://www.taxexecutive.org/managing-feoc-restrictions-and-irs-notice-2026-15/
- SECONDARY (Crux survey of ~50 developers/manufacturers, Oct 2025): some hire accounting/tax firms, some use legal teams, some do nothing; developers lean on manufacturer attestations. https://www.crux.com/blog/feoc-compliance-how-clean-energy-developers-and-manufacturers-are-preparing
- SECONDARY (Crux webinar, Feb 25, 2026): Novogradac is using AUP reports that manufacturers can hand to customers; pain points = getting sensitive ownership data from manufacturers, applying "reason to know" consistently, advisor capacity. https://www.crux.com/blog/highlights-from-cruxs-webinar-on-interim-feoc-guidance
- SECONDARY (Crux, Aug 21, 2026): law firms issuing PFE opinions on a documented risk-based process; no-fault indemnities in 94% of transfer deals; change-in-law provisions 12% of transfer agreements H1 2024 -> 55% H1 2026; tax-credit insurance generally excludes PFE risk. https://www.crux.com/blog/tax-credit-investors-need-to-know-in-h2-2026
- Published fees for MACR/PFE analysis or per-supplier-cert collection: NOT FOUND. Searched: Bing queries for fee/cost/AUP; Bracewell, Baker Tilly, Tax Executive, projectfinance.law, Crux pages (none mention fees). No survey of practitioner fees found. All $ price points in the brief are therefore assumptions.

## Q4. Existing products (WEAK: search tooling failed; treat "none found" as "not found", not "none exist")

| Vendor | What | Price / model | Evidence |
|---|---|---|---|
| Crux (crux.com) | Capital-markets marketplace + advisory + data for transfers/tax equity/debt; blog hub with PFE explainers (free content) | No fees published; CTA "Connect with our team" (sales-led). Self-reported: 225+ transactions closed, 850+ "qualified developers" in network, $85B+ dataset (page also says $55B) | https://www.crux.com/ (fetched 2026-10-29) SECONDARY (self-reported) |
| Certainty Software | Generic audit/supplier-compliance SaaS; a FEOC guidance/marketing page (Jul 29, 2026) pitching supplier attestation workflows; no dedicated PFE module named | PUBLISHED: Standard $18/user/month billed annually; Proof of Concept 30 days with $930 onboarding fee; Enterprise unpriced. Still "Contact us"/"Book demo" (not self-serve) | https://www.certaintysoftware.com/feoc-foreign-entity-of-concern/ ; https://www.certaintysoftware.com/pricing/ VERIFIED (vendor pages) |
| Source Intelligence | Enterprise supply-chain compliance SaaS (PFAS etc.) | Unpriced, demo-led; no FEOC/PFE tax-credit offering on homepage | https://www.sourceintelligence.com/ VERIFIED (homepage only) |
| Altana | Trade network | Page content unreadable | not verified |
| Law firms / accounting firms (Bracewell, Baker Tilly, Novogradac) | Advisory, opinions, AUPs | No fees published | articles above |
| SEMA Coalition "PFE Due Diligence Framework" | Named by Crux as free resource | Could not find it (Bing returned unrelated SEMA car show) | UNVERIFIED existence/contents |

- No standalone, self-serve, published-price MACR calculator or supplier-certificate tool found for PFE/MACR, prevailing wage, or domestic content. Searches that failed to surface any: "FEOC compliance software ...", "MACR calculator", "prevailing wage apprenticeship tax credit software", "domestic content bonus credit software", "PFE compliance platform" (Bing returned dictionary pages / Pfizer ticker). Because Bing mangled queries, absence of evidence is weak. Needs a proper search (Google, Product Hunt, G2, LinkedIn) before concluding the lane is empty.
- Funding / customer counts for any vendor: NOT FOUND (only Crux self-reported counts).

## Q5. Does the workload sit with small buyers?

- Evidence for LARGE-sponsor skew: practitioner stack above (counsel opinion + national-firm AUP + in-house tax) is built for transactions priced in $M; Crux deal commentary centres on $25-100M deals and F1000 corporate buyers (SECONDARY). Transferee demand is for opinions, AUPs, uncapped indemnities (Tax Executive; Crux H2 note: 71% of capped deals set cap above 100% of purchase price).
- Evidence for a small-taxpayer tail: statute is per-taxpayer, per-facility and per-component; every claimant including a small 45X manufacturer or 48E/45Y owner of a 2026 storage project must produce the MACR file and attach the safe-harbor statement (Notice 2026-15 sec 8.02, VERIFIED). Penalty exposure is non-trivial for small filers: 6662(m) lowers the substantial-understatement threshold from 10% to 1% (or $5,000) for MACR overstatements; 6501(o) six-year assessment (Notice sec 2.03, VERIFIED).
- Whether small buyers will pay $200-$800/project: NO EVIDENCE either way. No surveys, forum threads, or practitioner commentary on small-developer spend found (Reddit blocked, SEIA 403, search tool failed). Crux survey says "only 10% reported effective control issues; 80%+ no FEOC ownership", i.e. for most developers the hard part is supply-chain MACR, which Crux says they handle via supplier attestations (SECONDARY).
- Tax-credit insurance (Aon's Gary Blitz via Crux, Sep 3, 2026): PFE risk excluded -> buyers want contractual/indemnity comfort, not software.

## Q6. Half-life if Treasury publishes tables

- VERIFIED: statute 7701(a)(52)(D)(iii)(I) requires tables "and ... all rules necessary" by Dec 31, 2026; interim reliance on Notice 2025-08 tables + supplier certs continues until 60 days after the tables issue for projects beginning construction before then.
- SECONDARY (Crux survey article): Notice 2025-08 tables "do not, for instance, include percentages for 45X"; nuclear, geothermal, fuel cells lack tables (Crux webinar) -> actual-cost calculations remain for those.
- ESTIMATE/reasoning: If Treasury publishes component-level tables, the arithmetic (MACR = 1 - PFE-attributed direct cost / total direct cost) is trivially a spreadsheet; the product would compress to a lookup. Durable work that tables do NOT remove: supplier certifications (EIN, penalties-of-perjury statement, 6-year retention by both parties, "no reason to know" corroboration), annual PFE-status monitoring (status tested each tax year), ownership/effective-control analysis (13 contract-clause categories; Tax Executive/projectfinance.law), IP-licence tracking, 48E recapture (10 years per Bracewell, SECONDARY), and transferee diligence packages. These are judgement/document-collection work that buyers have so far placed with counsel/AUP.
- Tax Executive lists as open: who bears loss when a supplier cert is false; taint through groups; 48E recapture mechanics -> rules could shift again; product built now risks rework.

## Q7. Liability / regulation

- VERIFIED (31 CFR 10.37, Cornell LII): practitioners (CPAs, attorneys, EAs under Circular 230) giving written advice on federal tax matters must base it on reasonable assumptions, verify facts, avoid unreasonable reliance on others' representations; reliance on another's advice only if reasonable/good faith. For a CPA buyer, a third-party MACR output is reliance on another person's work -> they must still review it; reason to buy a checkable ledger, but also reason they won't sign off on a black box. (Page did not define "practitioner" 10.2; not verified.) https://www.law.cornell.edu/cfr/text/31/10.37
- VERIFIED (26 CFR 301.7701-15, Cornell LII): "tax return preparer" includes one who prepares "a substantial portion" of a return, and a person who "renders tax advice on a position that is directly relevant to the determination of the existence ... of an entry" is treated as having prepared that entry; a single entry can be a substantial portion; exclusions include "typing, reproduction, or other mechanical assistance" (text fetched does not mention software). IMPLICATION (ESTIMATE/legal reasoning, not legal advice): a tool that issues a MACR determination used as the credit-eligibility position could be argued to cross from mechanical assistance to advice; preparer penalty exposure (6694) and Circular 230 are therefore real design constraints. How tax-software vendors disclaim: NOT FOUND in this pass.
- UPL (unauthorized practice of law): not researched to primary source (state-by-state); UNVERIFIED.
- E&O norms/cost for tax-software or advisory vendors: NOT FOUND (search returned TurboTax pages).
- Precedent of vendors held liable: NOT FOUND.
- Statutory exposure is placed on suppliers (6695B) and claimants (6662(m), 6501(o)); not on software vendors. No statute found that makes a calculator vendor liable.

## Q8. Adjacent gates sharing the buyer

- Prevailing wage & apprenticeship (PWA), VERIFIED (26 USC 45(b)(7),(8), Cornell LII): underpaid wages cure = pay shortfall + interest (rate +6 pts) + $5,000 penalty per underpaid worker; intentional disregard = 3x shortfall + $10,000 per worker. Apprenticeship shortfall penalty $50 per labor hour; intentional disregard $500; good-faith safe harbor if registered program request denied/no response in 5 business days. Facilities with max net output <1 MW AC are exempt from PWA to get the 5x credit; facilities that began construction before Jan 29, 2023 are exempt (IRS page, last updated Jul 2, 2026). Final regs published June 18, 2024. Sources: https://www.law.cornell.edu/uscode/text/26/45 ; https://www.irs.gov/credits-deductions/prevailing-wage-and-apprenticeship-requirements . Existing tools: none found (DOL page lists no tools). The PWA pain sits with contractors/EPCs (certified payroll), not the credit claimant; per-project penalty arithmetic ($5,000/worker) makes a per-project evidence ledger plausible but UNVERIFIED demand.
- Domestic content bonus: safe harbor tables Notice 2023-38 / 2024-41 / 2025-08 (VERIFIED, referenced in Notice 2026-15 sec 2.04). Reuses the same bill-of-materials data as MACR (strongest data overlap = "second product" candidate). OBBBA threshold changes: NOT VERIFIED in this pass.
- Begin-construction documentation: Notice 2025-42 VERIFIED (above): physical work test, 4-year continuity safe harbor, 5% safe harbor removed except solar <= 1.5 MW AC. Notice 2026-15 sec 7(4) asks commenters what substantiation is needed to prove begin-construction for PFE anti-circumvention -> a documentation-ledger need is acknowledged but unspecified. July 4, 2026 cliff has passed; remaining value is in proving 2026 H1 starts and continuity through 2030 (placed-in-service by Dec 31, 2030 if not placed in service within 4 years? NOT VERIFIED beyond the notice's four-calendar-year continuity text).
- Energy community: not researched (UNVERIFIED).
- 25D: terminated for expenditures after Dec 31, 2025 (VERIFIED, IRS OBBBA page). Eliminates the largest small-buyer cohort for ESTIMATES of installers' customers; no MACR for 25D anyway.
- Best second product (judgement): domestic content (shared BOM/supplier data) then PWA evidence. No evidence of demand for either at card price points.

## Q9. Distribution (WEAK)

- Search-demand evidence (keyword volumes, forum threads): NOT OBTAINED (no SEO tools; Reddit blocked; SEIA 403; search tool unreliable).
- Observed content channels: Crux publishes ~2 PFE posts/month and runs webinars (Feb 2026) -> incumbent owns the "PFE explainer" SEO lane; law-firm alerts (Bracewell, Baker Tilly, projectfinance.law) own long-tail; Tax Executive (TEI) addresses in-house tax directors (SECONDARY). These are channels where buyers are, but all are held by sales-led incumbents.
- Channels a solo founder could try without outbound (HYPOTHESES, no evidence): free MACR worksheet + safe-harbor-table explorer indexed on Notice 2026-15; being the open-source/CC-licensed supplier-certification template (statutory contents are public: EIN, penalties-of-perjury, 6-year retention); Notice 2026-15 comment letter; LinkedIn tax-credit practitioner community; trade association member directories. All UNVERIFIED.

## (a) One-page factual brief

1. Law: OBBBA (P.L. 119-21, July 4, 2025) bars 45X/45Y/48E credits for items with "material assistance" from a prohibited foreign entity; MACR thresholds step up through 2030 (facility 40%->60%; storage 55%->75%; solar component 50%->85%). VERIFIED.
2. Guidance: only Notice 2026-15 (Feb 12, 2026), interim: three safe harbors; statement/certifications attached to Form 7211/3468/7207; comments closed Mar 30, 2026. No proposed regs through at least Oct 21, 2026 (FR check). Statute requires Treasury tables by Dec 31, 2026. VERIFIED.
3. Penalties: suppliers 6695B (greater of 10% of underpayment or $5,000; certifications after 12/31/2025; reasonable-cause exception; trigger = disallowance + understatement > lesser of 5% of tax or $100,000); claimants face 20% accuracy penalty with 1% substantial-understatement threshold (6662(m)) and 6-year SOL (6501(o)). VERIFIED.
4. Market: transfer market ~$42B (2025), ~$21B H1 2026; PFE-exposed ~ $4B (~20%) in H1 2026 (Crux, SECONDARY). Buyers are F1000 tax departments (98 in H1 2026). Work today: in-house tax + counsel opinion + accounting-firm AUP. Fees unpublished.
5. Counts of small claimants: NOT FOUND. IRS SOI TY2022 (pre-IRA) shows ~25,008 C-corp returns claiming any general business credit ($48.0B), excludes pass-throughs where most small developers sit.
6. Competitors: none found with published per-event pricing; generic supplier-compliance SaaS (Certainty, $18/user/mo, demo-led) and sales-led advisory/marketplace (Crux).
7. Risks: guidance unsettled; table publication could commoditize math; transferees demand opinions/AUPs not software; tool may drift into preparer/advice territory (301.7701-15(b)(3)); wind/solar construction cliff passed July 4, 2026; 25D gone.

## (b) Competitor table (price / sales model)

| Player | Category | Price | Sales model |
|---|---|---|---|
| Crux | marketplace + advisory + free content | unpublished | contact/sales-led |
| Certainty Software | supplier-compliance SaaS with FEOC page | $18/user/mo annual (Standard); $930 PoC onboarding | demo/contact; not self-serve |
| Source Intelligence | enterprise supply chain compliance | unpublished | demo-led |
| Law firms (Bracewell etc.) | opinions | unpublished | engagement |
| Accounting firms (Novogradac, Baker Tilly) | AUP / MACR calc | unpublished | engagement |
| Tax insurers (Aon cited) | PFE risk | excluded for now | broker |
| Self-serve priced MACR / cert tool | none found (weak search) | n/a | n/a |

## (c) Bottom-up market model (ALL ESTIMATE; account universe has NO verified count)

Anchors: Crux says 850+ developers in its network (self-reported); Crux survey sample ~50; IRS SOI TY2022 ~25,008 corporate GBC filers (any credit, pre-IRA). I treat "serviceable accounts" (SA) = small taxpayers who must do MACR work for 2026+ starts and would plausibly use a card-priced tool; this is a guess.

Formula: ARR = SA x adoption% x events/yr x price/event.

| Scenario | SA | Adoption | Events/acct/yr | Price | Accounts | ARR |
|---|---|---|---|---|---|---|
| Pessimistic | 800 | 2% | 3 | $300 | 16 | 16 x 3 x 300 = $14,400 |
| Base | 2,000 | 5% | 6 | $400 | 100 | 100 x 6 x 400 = $240,000 |
| Optimistic | 5,000 | 8% | 8 | $500 | 400 | 400 x 8 x 500 = $1,600,000 |

Accounts needed for $300K ARR (no adoption assumption): at pessimistic per-account revenue (3 x $300 = $900) -> 300,000/900 = 333 paying accounts; base (6 x $400 = $2,400) -> 125; optimistic (8 x $500 = $4,000) -> 75; at $10K zero-touch annual -> 30; at $100 per supplier cert -> 3,000 certs/yr.
Reading: $300K needs ~125 accounts at base price = ~6% of a 2,000-account SA with zero-touch acquisition. Base case lands near but below target; target is reachable only if SA >= ~2,500 or price/events rise. Every input is unverified. Timing risk: events cluster around return filing (first-year statement) and construction starts; guidance rewrite on/after Dec 31, 2026 could reset the work.

## (d) Verdict: NEEDS-MORE-EVIDENCE, leaning NO-GO for the hypothesis as stated

Why not GO: (1) no evidence of a large population of small claimants; (2) practitioner/transferee norm is counsel opinion + AUP, which software does not replace and which buyers contractually require; (3) the core math may commoditize after Treasury's tables (statutory deadline Dec 31, 2026, 2 months away); (4) liability posture is unsettled (preparer/advice line; 1% understatement threshold raises customer stakes and makes professionals reluctant to rely on a black box); (5) incumbents (Crux, law/accounting firms) own the content/SEO lane; (6) no price-point evidence at $200-$800.
Why not flat NO-GO: statute creates a real, recurring, per-facility/per-component document obligation (statements, certifications, 6-year retention) with real penalties; no priced self-serve product found (with weak search); suppliers have a distinct penalty exposure (6695B) and small suppliers/distributors may need a cert-issuing/retention tool.
SINGLE MOST DECISIVE UNKNOWN: will transferees/tax-equity/lenders and the signing CPA/counsel accept a software-generated MACR file + supplier-cert ledger as the diligence deliverable (replacing or shrinking the law-firm opinion + AUP) for small deals, and is there a population of small claimants who currently pay for ad hoc help at $200-$2,500? Cheapest test: wait for Treasury's tables (due Dec 31, 2026), then ask 10 practitioners/transfer buyers by inbound content (no calls) whether a ledger would satisfy their closing checklist; or pre-sell a $99-$299 template.

## Contradictions and discrepancies

1. "Final" tables: earlier pass said Treasury will issue final safe-harbor tables by Dec 31, 2026; the statute (quoted in Notice 2026-15) says "safe harbor tables (and ... other guidance)" by that date; not "final". Tax Executive (Aug 2026) and Crux call the notice interim.
2. Proposed-reg timing: Crux Aug 12, 2026 post lists "Later in 2026: Proposed regulations expected"; projectfinance.law (Feb 13, 2026) says comprehensive proposed regs not expected soon and no target dates. Neither confirmed by Treasury; no proposed reg found in FR through Oct 21, 2026.
3. Crux buyer counts: ~243 F1000 active investors through Q3 2025 (Mar 19, 2026 post) vs "nearly 200 in all of 2025" (Oct 13, 2026 post); and 2025 participation by size 30%/24%/15% (large/mid/small) vs H1 2026 13.8%/9.2%/4.2% (different periods/denominators).
4. Crux homepage: "$85B+" and "$55B" transaction datasets on the same page.
5. Crux Aug 12, 2026 post gives two different start dates for FIE prohibition on 45U/45Z (Jan 1, 2028 text vs July 4, 2027 table); I did not resolve against statute.
6. Crux H2 post: transferable market "$47.5-49.0B" in 2026 vs "$70B total monetization" vs "$21B H1 transfers": different scopes (transfers vs transfers+tax equity+preferred). Not a real conflict but easy to misquote.
7. IRS 5108 p. 156-163: Form 3468 line 14 count 1,156 vs 12b count 468 etc.; low counts for TY2022 reflect C-corps only and pre-IRA; not comparable to current claimants.
8. Tax Executive: 48E recapture for tax years beginning >2 years after enactment (~2028) vs Bracewell: 10-year recapture for 48E effective-control payments after placed-in-service; probably different provisions; unresolved.

## Unverified claims (list)

- Number of small developers/installers/contractors/manufacturers claiming 45X/45Y/48E/48 (any count).
- Forms 7207/7211/8933/3468 filing counts for TY2024/2025; any IRS SOI count for 45X.
- Number of transfer-market buyers/sellers/deals; sub-$10M deal share; registered transfer-election counts (IRS page gives none).
- Any published fee for MACR/PFE analysis, AUP, or per-supplier certificate.
- Any vendor funding/customer counts; existence of self-serve products (search limited).
- SEMA Coalition PFE Due Diligence Framework (existence, content).
- Crux claims: 225+ transactions, 850+ developers, 94% no-fault indemnity, $4B PFE-exposed (all Crux self-reported).
- How software vendors disclaim tax advice; E&O cost; UPL rules by state; vendor-liability precedent.
- OBBBA changes to domestic content thresholds; energy-community rules; 45X wind/inverter/battery thresholds (page truncated).
- Search demand, forum activity, conference calendars.
- Whether Treasury will publish tables on time and in what granularity.
- Notice 2026-15 PDF creation date Feb 12, 2026 used with Crux/Tax Executive for release date; IRS newsroom release not fetched (404).

## Ideas possibly missed (hypotheses; evidence = statute/commentary only, no demand evidence)

1. Supplier-side certification issuance/retention for small component makers and distributors: 6695B penalizes the supplier; certification must carry EIN, penalties-of-perjury, retained 6 years by supplier AND taxpayer (Notice sec 4.03(2)(a), VERIFIED). Novogradac AUP "handouts" show manufacturers need something to give customers (Crux webinar, SECONDARY). Buyer = small manufacturer/distributor, card-priced per certificate. Demand UNVERIFIED.
2. Annual PFE-status refresh / effective-control contract-clause checklist (status tested each year; 13 clause categories). Risk: UPL/advice line.
3. Begin-construction/continuity binder (Notice 2025-42 four-year continuity safe harbor; Notice 2026-15 sec 7(4) asks what substantiation is needed). Evidence of need = IRS itself asking; paying buyer unknown.
4. PWA cure calculator: $5,000/worker + interest(+6 pts) arithmetic (VERIFIED statute) for small EPCs/installers; no existing tools found; demand UNVERIFIED.
