# Pivot research: three adjacent wedges for a solo grid/energy SaaS

Date: 2026-10-29. Follow-up to `grid-wedge-research-2026-10-29.md`. Raw agent notes are appended as Appendices 1-3.

## 0. Trust caveats (read first)

- No general web-search tool worked in any of the three passes. Research used WebFetch on direct URLs, which returns model summaries rather than raw text, plus a few local PDF/API reads.
- Vendor pricing, demand and "who pays" findings are therefore weak. "None found" means "not found", never "does not exist".
- Labels: VERIFIED = primary source read (a summary of it counts only where stated), SECONDARY = trade press or vendor claim, ESTIMATE = my reasoning.
- Liability findings are largely unsourced in all three passes. Get a lawyer's read before charging money.

## 1. Bottom line

None of the three pivots is supported by evidence strong enough to build on. None is refuted outright either, except that the prevailing-wage pivot leans against.

| Pivot | Pain verified? | Card-priced competitor found? | Evidence anyone pays? | Verdict |
|---|---|---|---|---|
| 1. Supplier certificate issuance/retention | Legal duty yes; practical pain weak | One buyer-side vendor, sales-led | None found | Weak |
| 2. Prevailing-wage evidence for small installers | Rules yes; small-installer exposure mostly no | LCPtracker, Procore (sales-led); no self-serve found | None found | Leans against |
| 3. Interconnection application pre-check | Not shown (no rejection-rate data found) | None found; SolarAPP+ is free but permits only | Outsourcers charge four figures; $20-$200 checker unproven | Cautious, untested |

Pivot 3 is the only one where no direct competitor surfaced and no verified fact argues against it. That is an absence of evidence, not a green light.

All three share one gap: no evidence that a small buyer pays $200-$2,500 by card. A cheap landing-page test answers that better than more desk research.

## 2. Pivot 1: supplier-side certificates (OBBBA PFE/MACR)

**Hypothesis:** IRC 6695B penalizes the supplier who gives the certification, so suppliers need to issue and retain certificates.

- **Penalty (VERIFIED, Cornell text via summary plus Notice 2026-15 s.2.03):** falls on the person who provides the certification. It applies if they knew or should have known it was false, the inaccuracy caused a disallowed credit, and the understatement exceeds the lesser of 5% of tax shown or $100,000. Penalty is the greater of 10% of the underpayment or $5,000. Reasonable-cause exception. Applies to certifications after 12/31/2025. Six-year assessment period.
- **Certification content (VERIFIED, full Notice 2026-15 text read):** direct supplier's EIN and signature under penalties of perjury; statement that the property was not made by a prohibited foreign entity and that the supplier knows of none earlier in the chain; non-PFE direct costs (45Y/48E) or direct material costs (45X). Supplier and buyer keep it six years. The notice gives no model form. The safe harbor is optional for the buyer.
- **Why it's weak:** the penalty needs knowledge plus a large understatement, so a small supplier's realistic exposure is low. The hard part is knowing your own sub-tier chain and costs per buyer, which a template does not solve. taxexecutive.org (2026-08-11, SECONDARY) says suppliers resist signing under perjury and disclosing sub-tier makers, and that a certification is "rarely sufficient." Foley Hoag (2026-02-19, SECONDARY) says suppliers must know their chain well enough to certify.
- **Competitors:** Certainty Software sells a buyer-side attestation workflow with a demo CTA; its general pricing page shows $18/user/month and a $930 trial onboarding fee, no card checkout (SECONDARY). No downloadable template or other vendor surfaced. Free law-firm templates probably cap pricing (ESTIMATE).
- **Supplier count:** not found.
- **Liability:** a form generator is lower risk than a tool that decides PFE status or computes costs under a perjury oath (ESTIMATE). LegalZoom history (Wikipedia, SECONDARY) suggests document automation can survive unauthorized-practice challenges. Needs legal review.
- **Decisive unknown:** do small and mid sub-tier suppliers get per-buyer certification requests in volume, and would they pay $200-$2,500 themselves?
- **Cheapest test:** paid-template pre-sale page, or asynchronous outreach to 10-15 component makers (the user has said cold email failed, so prefer the landing page).

## 3. Pivot 2: prevailing-wage and apprenticeship evidence

**Hypothesis:** small solar/storage EPCs need certified-payroll-style records to avoid the 5x-credit penalties, and incumbents are too heavy.

- **Penalties (VERIFIED, Cornell/eCFR):** $5,000 per underpaid worker plus interest; 3x plus $10,000 for intentional disregard; $50/labor hour apprenticeship shortfall; 180-day cure after a final IRS determination.
- **Correction rule (VERIFIED, 1.45-7(c)(6)):** the per-worker penalty is waived if the correction is paid by the end of the month after the quarter of the failure and either the worker was underpaid in 10% or fewer of pay periods or the shortfall is 5% or less. A deadline-tracking feature could be built around this.
- **Records (VERIFIED, 1.45-12 / T.D. 9998):** payroll per worker including apprentices. Form WH-347 is optional; third parties may hold records; the reg text states no retention period.
- **Who bears it (VERIFIED):** the credit claimant is solely responsible for subcontractor wages, so the buyer is usually the developer or owner, not the installer.
- **Market shrink (VERIFIED, Notice 2025-42 and 48E(e)(4)):** OBBBA did not change the PWA provisions the agent read, but wind and solar placed in service after 2027 lose the credit unless construction began before July 5, 2026. That date has passed. Storage is exempt from the termination. PWA applies at 1 MW AC or more; under 1 MW AC is exempt, which covers most small installers.
- **Market size:** no count of small EPCs or 1 MW+ projects found. Only figure: 280,119 solar workers (IREC 2024, SECONDARY). EIA-860M is free and lists proposed units; not downloaded or counted.
- **Products:** LCPtracker (sales-led, no public pricing, already markets an IRA PWA resource center and a Baker Tilly co-solution), Procore (quote-based). "Elations" resolved to a parked domain; Hammer's page would not load. No self-serve card-pay PWA tool found.
- **Data moat:** DOL says SAM.gov wage determinations are public. An API or bulk download could not be confirmed. Public data is not a moat; value would be mapping a project to the right determination and tracking contract-date lock and 180-day supplementals.
- **Not researched:** who pays (Q4) and liability (Q6).
- **Verdict:** leans against. Most small installers are exempt, the real buyer is a developer with a CPA and an incumbent pitching, solar shrinks after 2027, no self-serve payment evidence. Durable niche: storage at 1 MW AC or more.
- **Decisive unknown:** how many 1 MW AC+ projects (storage, plus solar that began construction by July 4, 2026) are built by firms with no certified-payroll system, and would they pay $200-$2,500 by card.
- **Cheapest test:** count EIA-860M proposed units and owners, then a landing-page price test.

## 4. Pivot 3: interconnection application pre-submittal check

**Hypothesis (the founder's own):** DG interconnection applications are delayed by fixable errors and installers would pay per application ($20-$200) to catch them.

- **Pain evidence: not found.** No rejection rate or cause breakdown in any reachable source. IREC 2026 grades (2026-05-19) grade state rules, not implementation. DOE i2X has no delay numbers. Aurora's "95% first-time AHJ approval" is vendor marketing about permits, not utility applications (SECONDARY). CPUC Rule 21 requires utilities to track 19 interconnection timelines; likeliest data source, not accessed.
- **Competitors (all via WebFetch summaries):**
  - SolarAPP+ (SolarAPP Foundation): free to local governments, claims 350+ jurisdictions, permitting only.
  - Aurora: $159 or $259 per user per month, card self-serve; plan sets and PE stamps are paid add-ons; no interconnection feature.
  - Solargraf: $2,799-$12,999 per year.
  - Arka360: pricing page contradicts itself ($159-$358 per month).
  - PermitFlow: demo-only, no solar or interconnection mention.
  - PowerClerk: utility-side intake portal, demo-only.
  - Not verified: OpenSolar, Scanifly, Enphase and Sunrun tools (pages errored).
  - No pre-submittal QA product for utility interconnection found.
- **Willingness to pay:** Solar Permit Solutions publishes flat per-job prices (not re-confirmed against raw page): plan sets $1,200 (up to 20 kW), $2,000 (20-30 kW), $3,700+ (30 kW and up), PE stamp included; +$1,500 for the utility interconnection application; +$1,000 for AHJ submission. Installers pay four figures for done-for-you work. Nothing shows they pay $20-$200 for a checker.
- **Standardization:** nearly half of states have used IREC model procedures, which weakens a "wrong form per utility" pitch. 13 states have no statewide rules and each utility runs its own portal, which makes coverage costly for a solo founder. No public interconnection application API found. IEEE 1547, UL 1741, NY SIR and MA SMART not checked.
- **Counts:** no installer count or annual application count obtained. EIA 861M has net-metering installation counts through August 2026 (not downloaded). LBNL and SEIA were blocked.
- **Liability:** unsourced. An advisory checker that does not seal drawings is likely lower risk than stamping (ESTIMATE); check state engineering board rules.
- **Decisive unknown:** the real first-pass deficiency rate and whether installers feel it as costly.
- **Cheapest test:** pull Rule 21 or NY/MA utility timeline data for incomplete-application counts, then a card-checkout landing page.

## 5. Head-to-head and recommendation

- **Pivot 1** has the best-verified legal basis but the weakest buyer story, because the pain falls on a party who rarely faces the penalty and cannot fill the template without knowing their own chain.
- **Pivot 2** has the best-verified rules but the clearest evidence against: exempt small installers, sophisticated buyers, incumbents, a shrinking solar market.
- **Pivot 3** has the least evidence either way and the only open competitive space, but also the least proof of pain and a price point far below what installers currently pay outsourcers.

If you test one, test Pivot 3 first, because its decisive unknown (deficiency rate) can be partly answered from public utility timeline data before any build. Run the same 30-day structure as the earlier report: landing page, card checkout, a pre-agreed kill rule. Thresholds are proposals to adjust, not agreed: stop if fewer than 5 paid purchases from at least 500 unique visitors by day 30.

If Pivot 3's public data shows no meaningful deficiency rate, the next candidate is a storage-focused (1 MW AC+) version of Pivot 2.

## 6. Contradictions

- Pivot 1: Foley Hoag and taxexecutive.org describe supplier exposure as "perjury" or "unresolved," while the statute sets a defined 6695B penalty with a knowledge threshold.
- Pivot 3: Arka360's pricing page shows two different price sets.
- Pivot 3: Aurora's "95% approval" claim concerns permits and does not bear on utility interconnection.
- Pivot 2 vs the original strategy: the earlier report's land-and-expand premise assumed credit claimants as buyers; Pivot 2 verifies that PWA liability sits with the claimant, not the installer.

## 7. Unverified claims

- All vendor pricing (Certainty Software, Aurora, Solargraf, Arka360, LCPtracker, Procore) comes from WebFetch summaries; none was confirmed against raw pages.
- Solar Permit Solutions per-job prices not re-confirmed.
- No supplier count, installer count, 1 MW+ project count or annual application count was obtained.
- Whether SAM.gov wage determinations have an API or bulk download.
- OpenSolar, Scanifly, Enphase, Sunrun, Hammer tooling and pricing.
- All liability and unauthorized-practice conclusions.
- Whether later IRS guidance on supplier certification exists (not found, not ruled out).
- Cornell 6695B text and Notice 2026-15 s.2.03 cited from summaries except where the full notice text was read.

## 8. Before relying on this

1. Get a working search tool, or have someone confirm vendor pricing pages directly.
2. Download EIA-860M and the Rule 21 timeline data; both are free and answer a decisive unknown cheaply.
3. Have a lawyer review any product that touches a perjury-backed certification or interconnection engineering.
4. Journal this with `pow log` if you want it on the record; I did not run it.

## 9. Follow-up data check (2026-10-29)

Both lookups used WebFetch summaries (SECONDARY); a direct `curl` was denied, so no file was downloaded or counted.

- **Rule 21 timelines:** the CPUC page lists four reports (all IOUs, PG&E, SCE, SDG&E) as xlsx files, but the filenames carry "202204", so the versions linked look like April 2022. Utilities reportedly submit quarterly updates to the R.17-07-007 service list; I did not find a newer public copy.
- **Hurts Pivot 3:** D.20-09-035 did not require timeline reporting for net-metered systems under about 30 kW, which the March 2021 evaluation says are the majority of Rule 21 interconnections. That same evaluation says utility data was "incomplete or unavailable" in many cases. The page has no data on incomplete or deficient applications.
- **Possibly useful, not reviewed:** the quarterly IOU interconnection data reports under D.14-04-003 (`/industries-and-topics/electrical-energy/infrastructure/rule-21-interconnection/quarterly-iou-interconnection-data-reports` on cpuc.ca.gov). Contents unknown.
- **EIA-860M:** latest release is September 2026 (published 2026-10-23, next 2026-11-24). Direct file: `https://www.eia.gov/electricity/data/eia860m/xls/september_generator2026.xlsx`. It covers existing, retired and proposed units at plants of 1 MW or more, so it fits Pivot 2's storage question. Status and technology codes were not confirmed; no counts were obtained.

**Effect on the verdict:** the free public data most likely to answer Pivot 3's decisive unknown covers the larger systems, not the small residential applications an installer checker would target. That weakens the "answer it from public data first" plan. Pivot 2's EIA-860M count is still cheap and unblocked, but needs a manual download.

---

# Appendix 1: Pivot 1 raw notes

# Pivot 1 notes: supplier-side certification product (OBBBA PFE / MACR). Accessed 2026-10-29.
Tooling: WebSearch NOT available (ToolSearch returned only WebFetch). Used WebFetch + Bing result pages (noisy; summarizer drops quotes, often returns dictionary junk) + Federal Register API + a local pdftotext of IRS PDF.

## Q1 6695B
- VERIFIED (law.cornell.edu/uscode/text/26/6695B, WebFetch summary) AND VERIFIED (quoted in Notice 2026-15 sec 2.03, read locally via pdftotext): penalty on a PERSON (the certifier/supplier) who (1) provides a 7701(a)(52)(D)(iii)(II)(bb) certification and knows/should know it will be used for a MACR determination; (2) knows or reasonably should have known it is inaccurate/false re PFE status or the total direct (material) costs of non-PFE property; (3) the inaccuracy caused disallowance of an "applicable energy credit" (6662(m)(2)) and an income tax understatement exceeding the LESSER of 5% of tax required on the return or $100,000.
- Amount: greater of 10% of the underpayment (6664(a)) solely attributable to the inaccuracy, or $5,000. 6695B(c): no penalty if reasonable cause and not willful neglect.
- Assessment period 6 years after the return/claim was filed (6696(d)(1) as modified). Applies to certifications provided after 12/31/2025 (OBBBA 70512(l)(3); Pub. L. 119-21 sec 70512(k)).
- Not fetched: congress.gov, irs.gov statute page. Cornell text was a model summary, not raw text; the notice quotes the same elements.
- Implication: it is a knowledge-based, high-threshold penalty. A small supplier acting in good faith is unlikely to hit it. Exposure is for knowingly/recklessly false certs on large credit claims. Also: it is a penalty on the supplier, not a duty to obtain a tool.

## Q2 Notice 2026-15 (VERIFIED, read full text; IRS PDF https://www.irs.gov/pub/irs-drop/n-26-15.pdf; PDF metadata created 2026-02-12; 95+ pages)
- Sec 4.03 "Certification Safe Harbor" is OPTIONAL for the taxpayer (buyer): in lieu of computing direct costs / PFE status itself, the taxpayer may rely on supplier certs unless it knows or has reason to know inaccurate.
- Content (sec 4.03(2)(a), restating 7701(a)(52)(D)(iii)(IV)): supplier EIN (or foreign-government equivalent); signed under penalties of perjury; retained by BOTH supplier and taxpayer not less than six years and provided to IRS on request; from the DIRECT supplier from whom taxpayer purchased; states (AA) property not produced/manufactured by a PFE and supplier does not know/have reason to know any prior supplier in the chain is a PFE; (BB) for 45X: total direct material costs not PFE-produced; (CC) for 45Y/48E: total direct costs of MPs not PFE-produced. 4.03(2)(b): supplier may certify either the non-PFE dollar amount of direct costs OR simply that the item was not PFE-produced.
- Certs must be "prepared in a manner consistent with 1.45X-4(c)(4)(i)", i.e. attached to Form 7211/3468/7207 etc. filed with the return for the first year of claim (as stated by the notice; the "attached" language is the buyer's filing). Sec 8.02: taxpayer must attach a statement identifying the safe harbor used.
- No model/sample certification form found in the notice (grep for model/sample/template: none). Substantiation falls under general 6001 / 1.6001-1 (retain while material).
- Reliance: until 60 days after proposed regs publish (and safe-harbor tables for sec 4). Interim.
- Later guidance: projectfinance.law (2026-02-13, SECONDARY) says IRS expected to issue more FEOC guidance on a rolling basis, no target dates; comments due Mar 30. Federal Register API query for IRS "prohibited foreign entity" docs returned nothing relevant (only unrelated notices) => proposed regs NOT FOUND as of this check; not proof they don't exist. Did not locate any "Notice 2026-xx" after 2026-15; could not verify.

## Q3 Number of suppliers needing to issue certs
- NOT FOUND. No count located. cleaninvestmentmonitor.org (2026-10-29) gives investment dollars ($75B Q2 2026, update 2026-08-11), no facility counts on the page. IRS Form 7207 filer counts: not found.
- Reasoning (ESTIMATE, unsourced): certs are per buyer-supplier pair for direct suppliers of MPs/components of a facility or 45X component; demand is driven by the number of 45X manufacturers/45Y-48E developers (buyers), each collecting many certs. Supplier side is concentrated: module, cell, inverter, battery, tracker makers (many foreign, large) rather than a long tail of small US shops. Tail does include small component/subassembly makers feeding 45X manufacturers.

## Q4 Existing products
- Certainty Software (certaintysoftware.com/feoc-foreign-entity-of-concern/, SECONDARY vendor page, 2026-10-29): supplier compliance platform; "standardises screening questions, collects and verifies supplier attestations, keeps audit-ready evidence trail across tiers". Buyer-side/enterprise framing. Demo CTA. Pricing page (certaintysoftware.com/pricing/): Standard $18/user/month annual, "Contact Us"; Enterprise unpublished; Proof of Concept 30-day $930 onboarding fee via form. No card checkout shown. CAVEAT: pricing page appears to be the general product, not a FEOC-specific SKU.
- Law-firm/Big-4 style approach: supplier questionnaires, sourcing maps, working files, AUP reports (taxexecutive.org, SECONDARY).
- No downloadable supplier cert template found via Bing; not found != nonexistent. No other vendor identified. Bing results did not surface supply-chain traceability vendors (did not name any from memory; unverified).
- Insurance "FEOC insurance remains cost-prohibitive and challenging to secure" (taxexecutive.org).

## Q5 Burden / paying for help
- taxexecutive.org/managing-feoc-restrictions-and-irs-notice-2026-15/ (dated 2026-08-11 per Bing snippet; SECONDARY): "Suppliers are being asked to sign under penalties of perjury, retain records for six years, and stand behind portions of their own supply chain"; suppliers push back on scope/granularity; module makers resist disclosing cell manufacturer identities; "A signed certification is necessary but rarely sufficient"; recommends buyers run a "reasonable process". Notes unresolved whether the consequence is recapture/disallowance/supplier penalties. Does not mention 6695B.
- Foley Hoag alert (2026-02-19, SECONDARY, https://foleyhoag.com/news-and-insights/publications/alerts-and-updates/2026/february/new-irs-guidance-clarifies-material-assistance-feoc-requirements/): "MP suppliers will need to know enough about their MPC supply chain to certify under penalty of perjury"; only developers named as facing penalties for relying on certs known inaccurate.
- Direct evidence that small suppliers PAY for cert help: NOT FOUND. Reddit/forums not checked (blocked per brief). Evidence of buyer-side demand for process help: yes, qualitatively; evidence of $200-$2,500 self-serve card willingness: none.

## Q6 Liability / UPL
- Not verified from primary sources. From LegalZoom Wikipedia page (SECONDARY, 2026-10-29): NC court found LegalZoom not UPL (2008-era), other suits settled/dismissed, 2015 NC settlement set registration/consumer-protection conditions. Janson v. LegalZoom (W.D. Mo.) not on that page; I recall an adverse 2011 ruling but did NOT verify (ESTIMATE/memory).
- Practical (my reasoning, not verified): a form generator (user supplies facts, signs own cert) is lower risk than a tool that determines PFE status / computes costs or advises on safe harbor. The product would put a template under a signer's perjury oath: need strong disclaimers, no accuracy warranty, state variance. Tax-advice/Circular 230 issues arise if it advises on credit eligibility. Needs a lawyer review; cost not estimated.

## Contradictions
- Statute/notice: cert must be retained by both supplier and taxpayer; but Certification Safe Harbor is optional for the buyer, so a supplier has no independent duty to issue one. 6695B only bites if a cert is provided.
- taxexecutive.org says supplier penalty exposure exists and is "unresolved" (recapture etc.), while statute text clearly sets 6695B; article doesn't cite 6695B.
- Foley Hoag says no explicit supplier penalty beyond perjury; statute 6695B (effective 2026) does impose one. Different framing, not conflicting law.
- Hypothesis "suppliers need a tool because of 6695B" vs. the high threshold (knowledge + >$100k/5% understatement + reasonable-cause exception).

## Unverified / not checked
- Raw statutory text (WebFetch summaries only for Cornell); congress.gov, irs.gov statute pages, 1.45X-4(c)(4)(i) reg text.
- Whether any post-2026-15 notice or proposed regs exist (Federal Register API query too narrow/unclear).
- Supplier counts; vendor pricing for anything other than Certainty; other vendors; forum/Reddit chatter; any IRS model certificate; UPL case law (primary).
- Bing summaries are lossy; 2 URLs (taxexecutive, projectfinance.law) fetched OK but are secondary commentary.

## Verdict
Hypothesis is TRUE on the narrow legal point (6695B penalizes the certifying supplier; $5k/10%; 6-year retention; signed under perjury; EIN) but WEAK as a business case for the stated buyer. Against: (1) penalty needs knowledge + large understatement, reasonable-cause defense, so small suppliers have low realistic fear; (2) cert content is a few statements but the hard part is knowing your own sub-tier chain and costs per buyer, which a template doesn't solve; (3) buyers (developers/45X manufacturers) drive demand and want per-buyer certs, favoring buyer-side/enterprise tools and law-firm templates (free); (4) the only identified vendor sells via demo/contact; (5) no evidence found that small suppliers pay for help; (6) a fillable form is easy for anyone to copy from law-firm alerts. Plus UPL/liability exposure from tooling that touches a perjury oath.
Weakly for: genuine supplier pushback reported; six-year retention + EIN + chain-of-custody evidence is a real recordkeeping need; the self-serve card-pay slot appears empty (not found).
Most decisive unknown: whether sub-tier small/mid suppliers (not module/battery majors) actually receive per-buyer cert requests in volume and will pay $200-$2,500 themselves rather than have the buyer supply a template or counsel draft it. Cheapest test: interview/post to 10-15 small component makers or 45X manufacturers' procurement leads (not sales calls, asynchronous) or a landing page with a paid template pre-sale.


---

# Appendix 2: Pivot 2 raw notes

# Pivot 2: PWA evidence tool - research notes (accessed 2026-10-29)

Tooling: no WebSearch tool exists in this session (ToolSearch loaded only WebFetch). WebFetch returns model summaries, not raw text. Federal Register redirected to an unblock page; govinfo guessed URL 404; Baker Tilly guess 404; NREL DNS fail; Elations.com is a parked GoDaddy domain (vendor name unverified/likely wrong domain); Hammer fetch failed; sam.gov pages are JS shells. A Bash curl of the SAM API was permission-denied, so not tried.

## Q1. Rules and status after OBBBA
- 5x multiplier, PWA, 1 MW AC exception, begin-construction exception (60 days after guidance), penalties: $5,000 x underpaid workers plus shortfall plus interest; intentional disregard 3x shortfall and $10,000/worker; 180-day cure after final IRS determination; apprenticeship penalty $50/hr, $500/hr intentional; apprenticeship percentage 15% for construction beginning after 12/31/2023. VERIFIED, https://www.law.cornell.edu/uscode/text/26/45 (45(b)(6)-(8)). Cornell shows Pub. L. 119-21 amendments to section 45 did not touch (b)(6)-(8) (model summary of first 100k of 137k chars; remainder unread).
- Interest rate on correction is section 6621 with 6 points substituted for 3 (underpayment rate +6). VERIFIED, eCFR 1.45-7(c) https://www.ecfr.gov/api/renderer/v1/content/enhanced/current/title-26?part=1&section=1.45-7
- Penalty waiver (1.45-7(c)(6)): per-worker $5,000 waived if correction paid by end of first month after the quarter of failure AND (underpaid in <=10% of pay periods OR shortfall <=5% of required). VERIFIED (same URL). This is a concrete automatable rule (a real feature: pay-period/dollar-test calculator and deadline clock).
- Taxpayer (project owner/credit claimant) is solely responsible for wages paid by any contractor/subcontractor (1.45-7(b)(6)). VERIFIED. Implication: buyer is the credit owner/developer, not necessarily the installer; installers need to deliver records upward.
- Wage determination lock: rates at contract execution; supplemental determinations valid 180 days; indefinite alteration/repair contracts re-up annually. VERIFIED (1.45-7).
- Recordkeeping 1.45-12 (T.D. 9998, 89 FR 53252, June 25 2024): "maintain and preserve records sufficient to establish compliance"; minimum = payroll records per laborer/mechanic incl. apprentices, QPLA records; WH-347 and apprentice ratio/good-faith-effort docs listed as optional detail; third-party vendors allowed, with unredacted records available to IRS on request; no retention period stated in the reg text. VERIFIED, https://www.ecfr.gov/api/renderer/v1/content/enhanced/current/title-26?part=1&section=1.45-12 (model summary). Retention period "not present" per that read; general tax records rule (statute of limitations) is ESTIMATE only.
- Section 48(a)(9)-(11): 5x/PWA applies to ITC with 1 MW AC threshold; PWA for 5 years post placed-in-service for alteration/repair; recapture similar to section 50(a). VERIFIED (Cornell 48, first 100k of 216k chars).
- Section 48E (post-2024 tech-neutral): base 6%, 30% if <1 MW AC (also storage <1 MW), or PWA met; solar/wind termination 48E(e)(4): no credit for applicable wind/solar facility placed in service after 12/31/2027 unless construction begins by ~July 4, 2026; storage is NOT subject to that termination. VERIFIED, https://www.law.cornell.edu/uscode/text/26/48E
- Notice 2025-42: wind/solar begin-construction before July 5, 2026 only via Physical Work Test; 5% safe harbor unavailable except low-output solar <= 1.5 MW AC (section 6). VERIFIED (read PDF text locally, https://www.irs.gov/pub/irs-drop/n-25-42.pdf). Today (2026-10-29) the July 4, 2026 begin-construction date has passed.
- IRS PWA page (dated July 2, 2026) lists exceptions (<1 MW; construction began before Jan 29, 2023); does not mention OBBBA; says records must be kept but doesn't describe them. VERIFIED, https://www.irs.gov/credits-deductions/prevailing-wage-and-apprenticeship-requirements
- OBBBA did NOT change PWA rules (as far as read). It changed what projects exist: solar/wind facilities not under construction by 7/4/2026 must be in service by end 2027 or lose credits; also bans leased solar/wind 48E property to third parties (new 48E(i)) and adds prohibited-foreign-entity material assistance rules. So after 2026 PWA-relevant new starts: (a) storage >=1 MW AC (credit runs on, phase-down later; I did not verify the exact phase-out schedule), (b) wind/solar that began construction by 7/4/2026 and are placed in service later (4-year continuity safe harbor, so work through ~2030), (c) other tech (geothermal, nuclear, fuel cell etc.) irrelevant to small solar EPCs. Also, 25D residential credit end is NOT verified here.
- Not verified: 45Y text, exact 48E storage phase-out dates, 45X etc.

## Q2. Market size
- Whole solar workforce: 280,119 workers, 2024 National Solar Jobs Census, https://irecusa.org/programs/solar-jobs-census/ SECONDARY (model summary). No establishment count given.
- EIA-860M (monthly, free xls, latest Sept 2026 released Oct 23 2026) lists existing and proposed generators >=1 MW nameplate, https://www.eia.gov/electricity/data/eia860m/ VERIFIED that it exists; column list and exact threshold semantics (nameplate DC vs AC) not confirmed. This could size the pipeline of >=1 MW projects and planned online dates but I did not download or count.
- Census CBP (NAICS 238210) is the route to count electrical contractors by size; not queried. 
- No number of small EPCs with >=1 MW projects was found. Key structural point (ESTIMATE/reasoning): <1 MW AC projects are exempt, and residential/most small commercial installs fall under 1 MW AC. The PWA buyer is therefore a narrow set: C&I/community solar developers and storage developers with >=1 MW AC projects, usually the taxpayer/developer, mostly more sophisticated than "small installers". The count is unknown.

## Q3. Existing products
- LCPtracker: pricing not public, sales-led (demo form, phone), free accounts only for subs invited by a client who licenses it. VERIFIED, https://www.lcptracker.com/pricing. Has an IRA Resource Center and a joint PW&A solution with Baker Tilly (no price, no product name), products listed include LCPtracker Pro, LCPcertified, Workforce Manager, OnSite, etc. https://www.lcptracker.com/ira-resource-center/ SECONDARY. Blog has "Five Recordkeeping Considerations for IRA Prevailing Wage" (undated). So an incumbent is already marketing IRA PWA to energy companies.
- Procore: pricing not public, quote-based on annual construction volume, sales-led. VERIFIED, https://www.procore.com/pricing. Certified payroll not mentioned on that page.
- "Elations": domain elations.com is a parked/for-sale page; could not verify the vendor exists under that name. Hammer: fetch failed. Unverified, not claimed.
- Not found: any self-serve card-pay PWA-specific tool with public pricing. This means "not found", not "none exist". I could not search.

## Q4. Evidence people pay
- Only evidence: LCPtracker's own marketing and a Baker Tilly co-solution (vendor claims, SECONDARY). No law-firm/CPA articles, forum posts, or willingness-to-pay data found (Baker Tilly URL guess 404; no search engine). Treat as UNVERIFIED.

## Q5. Davis-Bacon data
- SAM.gov hosts DBA wage determinations; DOL says "available to the general public": https://www.dol.gov/agencies/whd/government-contracts/construction VERIFIED (model summary). The SAM.gov page itself rendered only shell text; I could not confirm bulk download or API (GSA open.gsa.gov wage API URL 404). Note the IRS regs 1.45-6/1.45-7 use DOL general wage determinations; I could not confirm which WD pages (construction type: Heavy vs Building vs Highway, solar classification) apply. Moat assessment: data is public, so not a moat; the value is mapping solar to the right WD and county, and tracking lock dates/180-day supplementals (rules above).

## Q6. Liability
- NOT researched with sources (no calls spent). Known from the regs: taxpayer is solely responsible for compliance; third-party vendors may hold records (VERIFIED). A vendor's exposure is ESTIMATE: standard SaaS disclaimers/limit-of-liability to fees paid, "not tax/legal advice" positioning, no calculation-of-penalties guarantee; unauthorized practice and IRS Circular 230 (tax-advice practice) risk if the tool advises on credit eligibility. Needs a lawyer; flag as unverified.

## Contradictions / oddities
- IRS regs page: "construction began before Jan 29, 2023" exception vs statute "60 days after guidance" (consistent: guidance published Nov 30, 2022 -> Jan 29, 2023). Not a conflict.
- Cornell 48 page says solar ITC 6% only for construction beginning before 1/1/2025 (legacy 48), while 48E carries solar forward; ensure the buyer's section is 48E vs 48. Not a conflict, but the model summary of 48(a)(2) as "0% residual" should be double-checked.
- WebFetch summaries conflicted slightly on 1 MW aggregation: 1.45-6 summary said text is silent on aggregation, while 45(b)(6) uses "facility" and the reg defines single project for 48. Not resolved.

## Unverified-claims list
Retention period; storage phase-out dates; number of target firms; vendor prices (all); Hammer/Elations; SAM API/bulk; liability law; willingness to pay; residential 25D status; whether 1 MW is aggregated across a project (48 "single project" suggests aggregation, unverified).

## Verdict (honest)
Legal need is real but the paying segment is thin and shrinking in the wrong direction:
1. <1 MW AC is exempt, so most small installers need nothing. 
2. The taxpayer/developer, not the installer, bears liability, and is usually sophisticated, has a CPA/law firm, and an incumbent (LCPtracker + Baker Tilly) already pitches this. 
3. Solar new starts after 7/4/2026 lose the credit entirely if not in service by end of 2027, so the solar PWA market is a decaying pool through ~2030; storage >=1 MW is the durable part.
4. No evidence found of self-serve willingness to pay; data is public (no moat).
Evidence leans AGAINST as a standalone $30-60K ARR product for small solar installers; a narrower variant (storage/C&I developers, penalty-waiver and wage-lock calculators, WH-347 export) is plausible but unproven.
Most decisive unknown: how many >=1 MW AC (solar-begun-by-7/4/2026 and storage) projects are being built by firms with no existing certified-payroll system, and will they pay $200-$2,500 by card. Cheapest test: count EIA-860M proposed >=1 MW units and their owners, then a landing-page price test.


---

# Appendix 3: Pivot 3 raw notes

# Pivot 3 notes: DG interconnection pre-submittal QA (accessed 2026-10-29)

Tooling: WebSearch NOT available (ToolSearch only surfaced WebFetch). WebFetch returns model summaries, so nothing below is "raw primary text"; labels reflect that. VERIFIED here = vendor/primary page fetched and summary read, not independently re-read raw.
Blocked/failed: emp.lbl.gov (403), nrel.gov (domain no longer resolves; NREL is now National Laboratory of the Rockies, nlr.gov), nlr.gov SolarAPP pages (404), docs.nlr.gov PDF (404), solarapp.org (refused), permitflow /pricing (404), opensolar /pricing (404), scanifly /pricing (404), arka360 detail pages, CPUC rule21 subpages (404), IREC model-procedures full text (gated). No search engine, so no rejection-rate studies found.

## Q1 Rejection/deficiency rates and causes
- NOT FOUND: no quantified DG interconnection rejection/deficiency rate from any source I could reach. (Not found != does not exist.)
- IREC 2026 Interconnection Grades (released 2026-05-19): grades statewide rules only, not implementation; only New Mexico got an A; 9 states B or above; 13 states with no statewide rules got F. Page has no denial/deficiency figures. https://irecusa.org/blog/irec-news/irecs-interconnection-grades-show-improvement-in-several-states/ -- VERIFIED (summary)
- DOE i2X page: no delay/rejection figures. https://www.energy.gov/eere/i2x/interconnection-innovation-e-xchange -- VERIFIED (summary)
- CPUC Rule 21 (D.20-09-035) requires IOUs to track/report 19 interconnection timelines: this is a likely place to find deficiency/timeline data, not checked in depth. https://www.cpuc.ca.gov/rule21 -- VERIFIED (summary)
- Aurora claims "95% first-time AHJ approval rate" for its plan sets (AHJ permits, not utility interconnection; vendor marketing). https://www.aurorasolar.com/plan-sets/ -- VERIFIED as claim only
- Founder's hypothesis (rejection over fixable errors): UNSUPPORTED by anything I read.

## Q2 Existing products
- SolarAPP+: run by independent non-profit SolarAPP Foundation (DOE-funded, originally NREL-managed). Free to local governments; page states no installer fee. Claims 350+ jurisdictions, 150K+ permits, 150K+ staff hours saved. Covers permitting/inspection, not interconnection (no mention). https://www.gosolarapp.org/ and /about -- VERIFIED (summary). Threat is to AHJ permit side only; interconnection adjacency is a gap, not covered.
- Aurora Solar: Basic $159/user/mo ($135 annual), Premium $259/mo ($220 annual), 50 projects/mo; card self-serve for Basic/Premium; Enterprise sales-led. Plan sets and PE stamps are add-ons; AHJ database 25,000+ jurisdictions. No interconnection feature on pricing page. https://www.aurorasolar.com/pricing -- VERIFIED (summary)
- Solargraf: $2,799-$12,999/yr tiers, self-serve "Get started"; permitting listed, interconnection not mentioned. https://www.solargraf.com/pricing -- VERIFIED (summary)
- Arka360: pricing page lists conflicting USD sets ($159-199/mo Basic; $199-358 Premium); SLD export in higher tiers; PE stamp service separate. https://www.arka360.com/pricing -- VERIFIED (summary, internally inconsistent)
- PermitFlow: AI permitting platform for contractors; "Book a Demo" only; no pricing; no solar/interconnection mention on homepage. https://www.permitflow.com -- VERIFIED (summary)
- PowerClerk (Clean Power Research): utility-side interconnection workflow platform with applicant portal; sold to utilities, "Schedule a Demo". Relevant: many utility portals run on it, so applicant forms are portal-bound. https://www.cleanpower.com/products/powerclerk/ -- VERIFIED (summary)
- Solar Permit Solutions: see Q5.
- NOT CHECKED (pages 404/unreachable): OpenSolar, Scanifly pricing, Enphase/Sunrun tools. OpenSolar is widely described as free to use but I did not verify. -- UNVERIFIED
- No product found that specifically does pre-submittal QA of utility interconnection applications. "None found" (limited search).

## Q3 Counts
- 2024 National Solar Jobs Census (IREC): 280,119 solar workers; no company count. https://irecusa.org/programs/solar-jobs-census/ -- SECONDARY/VERIFIED summary
- EIA-861M (data through Aug 2026) has net metering cumulative installation counts and capacity by state/sector (xlsx), so annual net-metered installs can be derived. Not downloaded. https://www.eia.gov/electricity/data/eia861m/ -- VERIFIED existence only
- LBNL Tracking the Sun: blocked (403). Installer count (SEIA/WoodMac/NREL): not obtained. Number of annual DG applications: not obtained. -- NOT FOUND
- Any figures from memory (e.g., ~1M+ residential installs cumulative, thousands of installers) are ESTIMATE/unverified and not asserted here.

## Q4 Standardization / moat or threat
- IREC Model Interconnection Procedures 2023: "nearly half of states" used them. Standardization of rules is a threat to the "wrong form per utility" value, and gives no data moat. https://irecusa.org/resources/irec-model-interconnection-procedures-2023/ -- VERIFIED (summary)
- 13 states lack statewide rules; utility-by-utility variation persists (IREC 2026). Heterogeneity is the only potential moat, but it's costly to maintain.
- Rule 21 has pro forma forms and tracked timelines; each IOU runs its own portal. -- VERIFIED (summary)
- DOE i2X is roadmap/engagement, no application API mentioned. -- VERIFIED (summary)
- IEEE 1547 / UL 1741 / NY SIR / MA SMART: NOT CHECKED.
- No public interconnection application API found.

## Q5 Do installers pay for outsourced design/permit/interconnection help
- Solar Permit Solutions per-job (flat): residential/ADU up to 20 kW $1,200; 20-30 kW $2,000; 30 kW+ from $3,700; add-on utility interconnection application +$1,500; AHJ submission +$1,000; PE stamp included; 2-5 business days. https://www.solarpermitsolutions.com -- VERIFIED (summary; figures look high vs. my expectation, re-confirm raw page)
- Aurora Plan Sets and PE stamp are paid add-ons (price not public); Arka360 has a permit/PE service. -- VERIFIED existence
- Implication: installers pay for done-for-you interconnection submission at $1,000+ scale; unproven they pay $20-200 for a checker.

## Q6 Liability
- NOT researched with sources. Reasoning (ESTIMATE): a checklist tool that doesn't seal drawings isn't practicing engineering; stamps come from licensed PEs (all vendors above bundle PE stamps via partners). Selling "approved/ready" verdicts carries E&O/reliance risk; position as advisory with disclaimers. Need state-board / counsel check.

## Contradictions
- Arka360 pricing page shows two conflicting USD price sets.
- Aurora's 95% approval claim is AHJ-side vendor marketing; no independent corroboration.
- Solargraf Enterprise API "included at no extra cost" vs "Get at $4000".
- NREL domain is gone (renamed NLR); older citations to nrel.gov may break.

## Unverified claims
- Founder's hypothesis (rejection reasons).
- OpenSolar free; Scanifly/Enphase/Sunrun tools; Sunrun not relevant.
- Whether utilities accept third-party pre-checks (not checked; the applicant, not utility, submits so likely no permission needed).
- Installer and application counts.
- IEEE 1547/UL 1741/NY SIR/SMART specifics.

## Verdict
Evidence neither supports nor refutes; it leans cautious. Positives: no free/cheap tool found that does interconnection pre-check; SolarAPP+ is permitting-only and free; installers demonstrably pay $1,000-$1,500 per job to outsourced firms (one vendor). Negatives: zero evidence found of how often applications fail or why; the price point $20-200 is far below what design suites ($135-259/user/mo) and outsourcers charge, so buyer might see it as a feature of Aurora/Arka (SLD export) rather than standalone; utility portals (PowerClerk) and state rules are fragmented, making coverage expensive for a 10-15 hr/wk founder; liability is manageable but unresearched. Market is also hit by the residential federal tax-credit changes (not verified here).
Most decisive unknown: the real first-pass deficiency rate for interconnection applications and what share of installers experience it as a costly pain (willingness to pay). Cheapest test: pull CPUC Rule 21 / NY / MA utility timeline data for "incomplete application" counts, plus 10 installer-forum/owner conversations (without calls: forum posts, a landing page with card checkout).
