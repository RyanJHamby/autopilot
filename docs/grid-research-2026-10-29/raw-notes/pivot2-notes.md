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
