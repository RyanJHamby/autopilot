# Two candidate wedges for a solo grid/energy software business: research report

Date: 2026-10-29. Prepared from two parallel research passes (Idea A: tax-credit compliance ledger; Idea B: calibrated interconnection-outcome forecasts). Full per-question notes with URLs are in Appendix 1 (A) and Appendix 2 (B).

## 0. Read this first: how much to trust this report

The brief asked for real web search. **Neither research pass had a working general web-search tool.** Both fell back on direct page fetches of known URLs, which succeeded for IRS PDFs, Cornell LII statute text, the Federal Register API, OSTI/NBER abstracts, and some vendor pages. They failed on Google, DuckDuckGo, Brave, Reddit, SEIA, emp.lbl.gov, ferc.gov, enverus.com, gridstatus.io and web.archive.org (blocked, CAPTCHA, 403 or 429).

Consequences:

- **Strong:** statutory and IRS facts for Idea A (Notice 2026-15, Code sections, penalties). LBNL license and headline stats for Idea B.
- **Weak:** vendor landscape, pricing, funding, customer counts, search demand, practitioner fees, willingness to pay, E&O norms. "None found" in those areas means "not found by a limited tool", not "does not exist".
- Every fetched page for Idea B came back as a model summary, not raw text. Recheck any number against its source before quoting it publicly (your repo rule: no public number without a captured run or a verified primary source).
- The LBNL data file and PDFs exceeded the fetch size limit, so nobody has seen the codebook yet. That is step 0 of any backtest.

Label key: VERIFIED = primary source fetched. SECONDARY = reputable or interested-party report. ESTIMATE = reasoning, arithmetic shown. UNVERIFIED = not found.

## 1. Bottom line

| | Idea A (tax-credit compliance) | Idea B (interconnection forecasts) |
|---|---|---|
| Verdict | **Needs more evidence, leaning no-go as framed** | **No-go as framed**; a narrow variant is only a lead magnet |
| Most decisive unknown | Will transferees, tax-equity, and the signing CPA/counsel accept a software-generated MACR file plus supplier-certificate ledger in place of a counsel opinion plus accounting-firm AUP on small deals, and do small claimants who pay $200-$2,500 exist? | Does a model on public as-of features beat a free ISO x technology x age base-rate table out of time (AUC about 0.75+, calibration slope 0.9-1.1, 3x decile spread)? |
| Cheapest next step | Wait for Treasury's tables (statutory deadline Dec 31, 2026), meanwhile test a supplier-certificate template | Two-weekend backtest, starting with the codebook |

**The founder's strategy hypothesis (sell per-event outcomes to the professional who signs) is not supported by the evidence found, for either idea.** In A, the people who sign are counsel and national accounting firms whose deliverables (opinions, agreed-upon-procedures reports) buyers require by contract, and a CPA under Circular 230 still has to review any third-party output. In B, there is no evidence that lenders, tax equity or consultants buy per-project forecasts by card; adjacent vendors sell annual subscriptions or demos. The hypothesis is not refuted either (weak search), but nothing found supports it.

## 2. Idea A: tax-credit compliance ledger

### 2.1 Factual brief

1. **Law.** OBBBA (P.L. 119-21, July 4, 2025) bars 45X/45Y/48E credits where "material assistance" from a prohibited foreign entity (PFE) exceeds thresholds. Facility MACR thresholds step 40% (construction beginning 2026), 45%, 50%, 55%, 60% after 2029; storage 55% to 75%; 45X solar components 50% in 2026 to 85% after 2029. VERIFIED (26 USC 7701(a)(52), https://www.law.cornell.edu/uscode/text/26/7701).
2. **Guidance.** IRS Notice 2026-15 (Feb 12, 2026) is **interim**. Three safe harbors: identification tables, cost-percentage, supplier certification. Comments closed Mar 30, 2026. VERIFIED (https://www.irs.gov/pub/irs-drop/n-26-15.pdf).
3. **Safe-harbor statement.** Claimants attach a statement to Form 7211, 3468 or 7207 for the first year a credit is claimed. VERIFIED (Notice secs 4.03, 8.02).
4. **Tables deadline.** The statute requires Treasury to issue safe-harbor tables "and other guidance" by Dec 31, 2026. VERIFIED (statute as quoted in Notice sec 2.02). **The earlier pass said "final" tables; the statute does not say final.** Whether Treasury meets the date and how granular the tables are: unknown.
5. **No proposed regulation** found in the Federal Register through 2026-10-21; IRS OBBBA page (reviewed 22-Oct-2026) lists only Notice 2026-15 for PFE. VERIFIED, with the caveat that later Notices would not appear in the Federal Register.
6. **Penalties, with nuances the earlier pass omitted.** IRC 6695B (greater of 10% of underpayment or $5,000, certifications after Dec 31, 2025) falls on the **supplier who gives the certification**, not on the claimant, and only if they knew or should have known it was false, the error caused disallowance, the understatement exceeds the lesser of 5% of tax or $100,000, and no reasonable-cause exception applies. VERIFIED (https://www.law.cornell.edu/uscode/text/26/6695B). Claimants face a separate exposure: the substantial-understatement threshold drops to 1% (or $5,000) for overstated MACR (6662(m)) and a six-year assessment period (6501(o)). VERIFIED (Notice sec 2.03).
7. **Scope shrinkage.** The wind/solar begin-construction cliff passed July 4, 2026 (construction beginning after that must be placed in service by end of 2027; physical-work test; 5% safe harbor removed except solar up to 1.5 MW AC). VERIFIED (Notice 2025-42). 25D (residential) ended for expenditures after Dec 31, 2025. VERIFIED (IRS OBBBA page). MACR work remains for storage, geothermal, nuclear, hydro, 2026 wind/solar starts, and 45X manufacturers.

### 2.2 Buyer count: not found

- No IRS SOI count of Form 7207/7211/8933 filers exists in anything fetched. VERIFIED absence on the SOI clean-energy page (updated Dec 4, 2025), which covers only residential credits.
- IRS SOI Pub 5108, tax year 2022: about 25,008 C-corporation returns claimed any general business credit ($48.0B). VERIFIED, but pre-IRA and excludes partnerships/LLCs, where most small developers sit. Not usable as a 2026 claimant count.
- Crux (marketplace; interested party): transfer market about $42B in 2025, about $21B in H1 2026; 98 Fortune 1000 buyers in H1 2026. SECONDARY. Buyers are large corporates; small-cap participation 4.2%.
- **"Thousands of small developers must prove MACR" is not supported by any count found.**

### 2.3 Who does the work and what it costs

Today's stack: in-house tax, outside counsel "should"-level opinion, a national accounting firm's agreed-upon-procedures review (Novogradac named), supplier certifications; AUPs are often a closing deliverable naming the transferee. SECONDARY (Tax Executive, Aug 11, 2026; Crux). No-fault indemnities appear in 94% of transfer deals (Crux, SECONDARY); tax-credit insurance generally excludes PFE risk. **Published fees for MACR analysis or per-certificate collection: not found.** Every price point in the brief is an assumption.

### 2.4 Competitors

| Player | Category | Price | Sales model | Label |
|---|---|---|---|---|
| Crux | Marketplace, advisory, free PFE content | Unpublished | Contact/sales-led | SECONDARY (self-reported) |
| Certainty Software | Generic supplier-compliance SaaS with a FEOC marketing page | $18/user/month annual; $930 proof-of-concept onboarding | Demo/contact, not self-serve | VERIFIED |
| Source Intelligence | Enterprise supply-chain compliance | Unpublished | Demo-led | VERIFIED (homepage) |
| Law firms (Bracewell etc.) | Opinions | Unpublished | Engagement | VERIFIED existence |
| Accounting firms (Novogradac, Baker Tilly) | AUP / MACR calc | Unpublished | Engagement | SECONDARY |
| Self-serve priced MACR or certificate tool | **None found** | n/a | n/a | UNVERIFIED (weak search) |

### 2.5 Half-life

If Treasury publishes component-level tables, the MACR arithmetic becomes a lookup. Notice 2025-08 tables lack 45X percentages and nuclear/geothermal/fuel cells, so actual-cost calculations remain for those (SECONDARY). Durable work the tables do not remove: supplier certifications (EIN, penalties-of-perjury statement, six-year retention by both parties), annual PFE-status monitoring, effective-control contract review, 48E recapture, transferee diligence packages. Much of that is judgment or advice-adjacent. Tax Executive lists open issues (who bears loss on a false supplier cert, taint through corporate groups, recapture mechanics), so rules could shift again after a product is built.

### 2.6 Liability

- Circular 230 sec 10.37 (VERIFIED): practitioners must verify facts and not unreasonably rely on others' work. A CPA must review any third-party MACR output. That is a reason to want a checkable ledger and a reason not to sign off on a black box.
- 26 CFR 301.7701-15 (VERIFIED): a person who renders tax advice on a position directly relevant to an entry can be treated as a preparer; "mechanical assistance" is excluded. A tool that issues the credit-eligibility determination could be argued to cross that line. This is legal reasoning, not legal advice; get counsel before launch.
- UPL by state, E&O cost, how tax-software vendors disclaim, vendor-liability precedent: **not found**.

### 2.7 Bottom-up market model (all ESTIMATE; no verified account universe)

ARR = serviceable accounts (SA) x adoption x events/account/year x price/event.

| Scenario | SA | Adoption | Events/yr | Price | Accounts | ARR |
|---|---|---|---|---|---|---|
| Pessimistic | 800 | 2% | 3 | $300 | 16 | 16 x 3 x 300 = $14,400 |
| Base | 2,000 | 5% | 6 | $400 | 100 | 100 x 6 x 400 = $240,000 |
| Optimistic | 5,000 | 8% | 8 | $500 | 400 | 400 x 8 x 500 = $1,600,000 |

Accounts needed for $300K ARR: pessimistic per-account revenue ($900) = 333; base ($2,400) = 125; optimistic ($4,000) = 75; $10K annual zero-touch = 30; or 3,000 certificates/year at $100. The SA anchors (Crux's 850+ network developers, self-reported; a 50-company survey) are not a count of claimants. The base case needs about 6% of a guessed 2,000-account universe to convert with zero outbound.

### 2.8 Adjacent gates

- **Prevailing wage and apprenticeship.** Underpaid wages cure = shortfall + interest + $5,000 per worker; intentional disregard = 3x + $10,000 per worker; apprenticeship shortfall $50 per labor hour. VERIFIED (26 USC 45(b)(7),(8)). Pain sits with contractors/EPCs (certified payroll). No tools found. Demand unverified.
- **Domestic content.** Reuses the same bill-of-materials data as MACR (strongest overlap, best second product by data reuse). OBBBA threshold changes not verified.
- **Begin-construction documentation.** Notice 2026-15 sec 7(4) itself asks what substantiation is needed. Paying buyer unknown.
- **Energy community.** Not researched.

### 2.9 Distribution

Search demand and forums were not obtainable. Observed: Crux publishes about 2 PFE posts a month and runs webinars; law-firm alerts and Tax Executive own long-tail and in-house tax readers. Every discoverable channel is held by a sales-led incumbent. Solo-founder hypotheses with no evidence: a free MACR worksheet, a CC-licensed supplier-certification template (statutory contents are public), a Notice 2026-15 comment-style explainer.

## 3. Idea B: calibrated interconnection-outcome forecasts

### 3.1 Data inventory and license verdicts

| Dataset | Fields (known) | History | License / terms | Point-in-time? | Verdict |
|---|---|---|---|---|---|
| LBNL Queued Up 2026 data file (end-2025) | Project-level; exact columns UNVERIFIED; codebook + 36 tabs | 2000-2025 requests; annual | **CC BY 4.0, attribute LBNL and GridTracker** (VERIFIED, https://eta-publications.lbl.gov/publications/queued-2026-edition-characteristics; 2025 page did not state a license, so confirm in the file) | Final-state only; six annual editions exist, older file availability unverified | Commercial use OK with attribution |
| LBNL cost datasets (MISO, SPP, PJM, non-ISO) | Project-level cost, status | 2000-2024 by region | Not read | Final estimates, not stage history | Check terms |
| interconnection.fyi public site | Filters by region, state, year, type, status | 1995-2026, about 44,281 requests | "All rights reserved" | Replay only in paid GridTracker, daily since Apr 2024 | Do not scrape or redistribute |
| ERCOT GIS report (monthly) | Milestones, trends | Since 2017-02 | Classified "Public" | Possibly about 7 years of monthly files (inferred, unverified) | Best point-in-time candidate |
| ISO-NE queue | QP, type, MW, dates incl. withdrawn date, study status | Daily; retention not stated | Not stated | No archive stated | Check |
| CAISO, MISO, SPP, PJM, NYISO | Not verified | Unknown | Unknown; NYISO has CEII gate | Unknown | Read each ISO's terms |
| EIA-860/860M | Not fetched | Monthly | Public domain presumed (UNVERIFIED) | Monthly | Use for COD checks |

Headline stats (VERIFIED, LBNL 2026 ed.): of capacity requested 2000-2020, about 13% reached COD, about 75% withdrawn, about 10% still active; median request-to-COD above 5 years for projects built in 2025.

**Main finding against a data moat:** the core outcome labels are free, CC BY, and already used by hobbyist competing-risks pipelines. The only comprehensive point-in-time archive found belongs to GridTracker (daily snapshots since April 2024, API, MCP connector, per-report purchase behind "book a demo"), LBNL's own data partner.

### 3.2 Prior art on predictability

No peer-reviewed project-level model with out-of-sample accuracy was found (limited search; absence is weak evidence). Closest:

- Johnston, Liu, Yang, NBER WP 31946 (Dec 2023), PJM 2008-2020 (VERIFIED, https://www.nber.org/papers/w31946): interconnection cost after each study strongly predicts withdrawal (above $0.1M/MW second-study cost, 33% of generators, means 49% more likely to withdraw before the third study); queue position matters; similar generators have widely different costs (second-study median $0.05M/MW, P90 $0.41M/MW). Structural model, no forecast-accuracy metric.
- Features the evidence supports: study-stage cost (strong, but needs stage data not in free files), queue position, hybrid solar+storage (SECONDARY), cohort-level withdrawal bursts (arXiv 2609.10455, VERIFIED abstract, no accuracy metric).
- Whether entry-time public features alone discriminate well: **no study found**. That is the decisive empirical unknown.

### 3.3 Competitors

| Vendor | Offering | Probability/cost/timeline output | Price | Self-serve? |
|---|---|---|---|---|
| GridTracker / interconnection.fyi | Queue data, replay, docket full-text, API, MCP | No probability product seen | Subscription unpublished; reports "book a demo" | Free public view; paid needs sales |
| Cleanview | Project trackers, Excel, API | Share with signed IAs; no probability | $9,000/yr (5 users); +$5,000/yr API; $4,900 one-time dataset | Public price, "Contact sales" |
| Paces | Site discovery and risk reports | "Grid risk"; no probability described | Not listed | Demo |
| LevelTen | PPA price index | Not interconnection | Subscription only | Demo |
| Grid Status | Open-source `gridstatus` library, hosted API | Data only | Not verified (403) | API self-serve |
| Enverus, GridCARE, Pearl | Not verified | UNVERIFIED | UNVERIFIED | UNVERIFIED |

No reachable vendor publishes a calibrated completion probability or a public track record. That is consistent with white space and equally with "no one has found a buyer".

### 3.4 Willingness to pay

No evidence found that lenders, tax equity, acquirers, brokers or small consultancies pay $100-$1,000 per project by card. Costs of diligence reports and consulting: not found. Arithmetic (ESTIMATE): $300K ARR = 600 reports at $500 (50 a month), 200 at $1,500, or about 33 accounts at $9K. With 10-15 hours a week the binding constraint is demand.

### 3.5 Defensibility and liability

- A public-data baseline is replicable in weeks by a funded competitor or an agent. Verified ingredients: CC BY labels, hobbyist pipelines, GridTracker's MCP server.
- Plausible moats (my analysis, not sourced): time-stamped public prediction log (cannot be backdated), customer-submitted outcomes, proprietary labels. Median 5+ years to COD means a track record matures slowly; withdrawals resolve faster. Only verified analogy: LevelTen's index is built from offers on its own marketplace (206 offers, Q3 2026), not public data.
- Liability: Advisers Act publisher exclusion text verified (15 USC 80b-2(a)(11)); a project-level forecast is likely not security-specific advice (ESTIMATE, not legal advice). Insurance norms: not found. If the buyer who signs relies on the report, risk flows back to the vendor, which conflicts with a cheap per-report model.

### 3.6 Standardization and regime risk

The 2000-2020 serial-queue history that makes backtesting possible is the regime that is ending. Order 2023 cluster studies (all regions implementing; AEU June 2026: no evidence yet of faster processing), PJM's reopened cycle (800+ projects, 220 GW; Utility Dive 2026-04-29), and FERC's June 18, 2026 large-load show-cause orders (readiness requirements; questions on upgrade-cost transparency) mean old base rates may not transfer. It also creates new decisions to forecast, but with no history to calibrate on. Net: weakens the backtest-to-future link; the track record has to start fresh.

### 3.7 Two-weekend backtest design

- **Step 0 (30 minutes, decides everything):** download the LBNL xlsx locally and read the Codebook tab. Confirm entry, withdrawal, COD and IA dates are populated for CAISO, MISO, PJM, SPP, ISO-NE. If withdrawal dates are mostly missing, as-of-T status cannot be reconstructed and the design fails.
- **Target:** P(withdraw by T+3y) and P(COD by T+3y) for projects active at T (competing risks); time to COD secondary.
- **Split:** as-of T1 = end-2018 (train), T2 = end-2021 (test, outcomes through 2025). No final-state fields as features.
- **Features:** ISO, state, technology, MW, entry cohort, age in queue, hybrid flag, IA signed by T if dated.
- **Baselines to beat:** (1) ISO x technology rate from training cohort; (2) age-conditional base rate; (3) constant overall rate.
- **Success criterion (my proposal, not evidence-based):** out-of-time AUC at least 0.75, Brier skill at least 15% over baseline 1, calibration slope 0.9-1.1, top-vs-bottom-decile COD rate ratio at least 3x, in at least 3 of 5 ISOs. Anything less is a base-rate table LBNL gives away.
- **Failure modes:** ERCOT/NYISO date gaps (SECONDARY), re-entered projects, survivorship, post-2023 regime, label latency.
- Capture runs with `pow run` into `results/`, name the hardware, and `pow log` the outcome before quoting any number.

## 4. Head-to-head

| Criterion | A: tax-credit ledger | B: interconnection forecasts |
|---|---|---|
| Buyer count | Unknown. Large buyers about 98-243 Fortune 1000 (Crux, contradictory); small claimants not found | Unknown; no count of diligence buyers found |
| Price per event | Assumed $200-$800 per project, $50-$150 per certificate; no fee evidence | Assumed $100-$1,500 per report; adjacent vendors sell $4.9K-$9K datasets or subscriptions |
| Accounts for $300K ARR | 125 (base $2,400/account), 333 (pessimistic), 30 at $10K annual (ESTIMATE) | About 33 at $9K annual, 200 reports at $1,500, 600 at $500 (ESTIMATE) |
| Time to first dollar at 10-15 hrs/wk | Weeks for a template or certificate pack; tables due Dec 31, 2026 | Two weekends to know if a model works; months more to a sellable product plus an immature track record |
| Liability exposure | Medium-high: preparer/advice line, 1% understatement threshold raises customer stakes | Medium: forecast disclaimers workable, but the signer's reliance flows back |
| Moat vs LLM agents | Weak for the math (commoditizes with tables); moderate for a retained evidence record | Weak for public-feature models; archive/log moat exists but incumbent is ahead |
| Zero-touch sales likelihood | Low-moderate: buyers require opinions/AUPs, content lane held by incumbents | Low: no card-checkout precedent found; subscriptions and demos dominate |
| Time sensitivity | High: tables, deadline Dec 31, 2026 | Low, but regime change erodes backtest value |

## 5. Recommendation

**Test A first, narrowly, and do not build a MACR calculator.** Reasons: it has a dated catalyst (Dec 31, 2026), a statute-defined document obligation, and a test that costs days rather than weeks. B's cheapest test (the backtest) is useful but its best-case outcome is a model with no evidenced buyer, and its data moat belongs to the incumbent. If A fails its kill rule, run B's backtest as a lead-magnet experiment, not a business.

### 30-day test for A (the kill thresholds are my proposals; adjust before starting)

1. **Days 1-3.** Re-read Notice 2026-15 secs 4 and 8 and the statute text for certificate contents. Build a **supplier certification template plus six-year retention checklist** and a **one-page MACR worksheet** that depend only on public statute text, not on the pending tables. Get a lawyer's read on the preparer/advice line before charging, and keep the product framed as a document and record template, not a credit determination.
2. **Days 4-10.** One landing page with a card checkout (a $99-$299 pack). No calls, no demos. Publish the worksheet and an explainer where the buyers already read (tax-advisor and project-finance communities). Do not rely on cold email.
3. **Days 10-30.** Add a short "does this satisfy your closing checklist?" form for practitioners and transfer buyers. If Treasury publishes tables before day 30, add a table explorer and re-announce.
4. **Kill rule.** Stop if by day 30 either (a) fewer than 5 paid purchases from at least 500 unique visitors, or (b) fewer than 3 of 10 practitioner responses say a software-produced file would be accepted for small deals. Continue only if both pass; then test the $50-$150 per-certificate price and one annual account at about $10K.
5. **Repo hygiene.** No `docs/journal.md` was checked here; per your defaults, run `pow init` if the project gets its own repo, `pow log` the decision and result, quote only numbers from `pow run` captures, and update the README AI-disclosure.

### Ranked open questions

1. Will transferees and CPAs accept a software-assembled evidence file on small deals? (A, decisive)
2. How many small claimants (45X manufacturers, 48E/45Y owners, storage developers) exist, and what do they pay now? (A)
3. What do Treasury's tables look like on or after Dec 31, 2026: granularity, 45X coverage, timing? (A)
4. Do public as-of features beat a free base-rate table out of time? (B, decisive; run the backtest only if A fails)
5. What are published fees for MACR analysis, AUP, per-certificate work, and interconnection diligence? (both)
6. UPL and preparer exposure for each product shape; E&O availability and cost. (both)
7. Terms of use for each ISO queue file and LBNL cost datasets. (B)
8. Does anyone sell a self-serve priced MACR or certificate tool that this tooling missed? Search Google, Product Hunt, G2, LinkedIn. (A)

## 6. Ideas we may have missed (hypotheses; demand not verified)

| Idea | Evidence for need | Evidence of demand |
|---|---|---|
| Supplier-side certificate issuance and retention for small component makers/distributors | Penalty falls on the supplier (6695B); certificates need EIN, perjury statement, six-year retention by both parties (VERIFIED); manufacturers need something to hand customers (Crux webinar, SECONDARY) | None; **best of the four** because the buyer is distinct from the incumbent-served transferee |
| Prevailing-wage cure calculator for small EPCs/installers | $5,000 per worker + interest arithmetic (VERIFIED statute); no tool found | None |
| Begin-construction and continuity binder | IRS asked commenters what substantiation is needed (Notice 2026-15 sec 7(4)); four-year continuity safe harbor | Paying buyer unknown |
| Annual PFE-status refresh / effective-control clause checklist | Status tested each year | Advice/UPL risk |
| Large-load (data-center) queue risk and cost exposure | Texas queue headlines of 438-474 GW (Utility Dive, headlines only); FERC June 18, 2026 orders; academic Monte Carlo (SSRN 7303000) | No card-buying evidence; almost no calibration data |
| Per-POI cost screen from LBNL cost datasets | Cost drives withdrawal (VERIFIED) | No price evidence; data is free |
| Per-document parser for ISO study PDFs | Space occupied by GridTracker | None |
| PJM Cycle 1 tracker with public prediction log | Size of event (VERIFIED) | Unknown |

## 7. Contradictions between sources

1. **"Final" tables (A).** Earlier pass: Treasury will issue final tables by Dec 31, 2026. Statute: tables "and other guidance" by that date, not "final". Tax Executive and Crux call Notice 2026-15 interim.
2. **Proposed-reg timing (A).** Crux (Aug 12, 2026) lists "Later in 2026: proposed regulations expected"; projectfinance.law (Feb 13, 2026) says comprehensive proposed regs not expected soon. None found in the Federal Register through Oct 21, 2026.
3. **Crux buyer counts (A).** About 243 Fortune 1000 active investors through Q3 2025 (Mar 19, 2026 post) vs nearly 200 in all of 2025 (Oct 13, 2026 post); participation by size also differs between periods.
4. **Crux market sizes (A).** $47.5-49.0B transferable market in 2026 vs $70B total monetization vs $21B H1 transfers (different scopes); homepage cites both $85B+ and $55B datasets; two different start dates for the 45U/45Z foreign-influenced-entity rule in one post.
5. **48E recapture (A).** Tax Executive: tax years beginning more than two years after enactment (about 2028); Bracewell: 10-year recapture for effective-control payments. Possibly different provisions; unresolved.
6. **Active queue size (B).** LBNL 2026: about 8,200 projects (1,312 GW generation + 749 GW storage); LBNL 2025: about 10,300; GridTracker: 9,781 projects, 1,860 GW; Potter (Feb 2025): about 11,000+. Date and scope differences; never mix sources in one claim.
7. **Withdrawal rates (B).** LBNL 2025: 77% for 2000-2019; LBNL 2026: about 75% for 2000-2020; Potter: roughly constant 72% for 1999-2018. A hobbyist repo's 13/75/19 sums to 107%.
8. **Licensing (B).** interconnection.fyi is "All rights reserved"; LBNL's file built with the same data is CC BY 4.0 (different works); the 2025 edition page did not mention CC BY.
9. **Record counts (B).** 38,201 vs 37,527 from "LBNL 2026" in two hobbyist repos; 44,281 on interconnection.fyi (different scope).

## 8. Claims not verified

**Idea A**
- Any count of small developers, installers, contractors or manufacturers claiming 45X/45Y/48E/48; Form 7207/7211/8933/3468 filing counts for TY2024/2025.
- Transfer-market buyer/seller/deal counts and sub-$10M share.
- Any published fee for MACR/PFE analysis, AUP or per-certificate work.
- Vendor funding or customer counts; whether a self-serve priced product exists.
- SEMA Coalition "PFE Due Diligence Framework" (existence, content).
- Crux self-reported figures (225+ transactions, 850+ developers, 94% no-fault indemnities, $4B PFE-exposed).
- How software vendors disclaim tax advice, E&O cost, UPL by state, vendor-liability precedent.
- OBBBA changes to domestic content thresholds; energy-community rules; 45X wind/inverter/battery thresholds.
- Search demand, forum activity, conference calendars.
- Whether Treasury publishes tables on time and at what granularity.

**Idea B**
- LBNL data file column names, status coding, populated dates by ISO.
- License terms of LBNL cost datasets and of every ISO's queue file; whether older LBNL files and ISO archives remain downloadable; ERCOT archive depth.
- PJM, MISO, CAISO, SPP field lists and inclusion of withdrawn projects.
- Enverus, Grid Status, GridCARE, Pearl offerings and prices; funding and customers for GridTracker, Cleanview, Paces.
- Cost of diligence reports and interconnection consulting; willingness of lenders, tax equity, acquirers and brokers to pay per project; how buyers verify forecasts; E&O norms.
- Content of the Joule 2024 paper, Brattle and Grid Strategies reports; Lowe v. SEC; EIA-860M terms.
- Bodies of Utility Dive articles known only by headline (PJM fast-track, MISO accelerated queue, Texas queue and pause).

## 9. What to do before relying on this

1. Re-run the unverified items with a working search tool (or manually), starting with: vendors for self-serve MACR/certificate tools, practitioner fees, and ISO terms of use.
2. Download the LBNL xlsx and read the Codebook.
3. Verify every number you plan to quote against a raw primary source; Idea B figures were summarized by the fetch tool.
4. Do not use any figure from this report in a README, resume or post until it is backed by a primary source or a captured `pow run`.

---

# Appendices: raw research notes (unedited)

Appendix 1 is the Idea A notes; Appendix 2 is the Idea B notes. They contain the full URL trail and per-question detail.


## Appendix 1: Idea A notes

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

## Appendix 2: Idea B notes

# Idea B: Calibrated interconnection-outcome forecasts. Research notes

Date of research: 2026-10-29. Author: research agent (Claude).

## 0. How to read this / tool limits (important)

Labels: VERIFIED = I fetched the primary page (or paper) this session. SECONDARY = reputable report or third-party page. ESTIMATE = my arithmetic or inference, shown. UNVERIFIED = could not confirm.

Caveats on method, stated plainly:
- No general web search worked. WebSearch was not available. DuckDuckGo and Bing returned CAPTCHAs or junk, Brave returned 429, Yahoo 500, Mojeek 403. What worked: Crossref, OpenAlex, arXiv, GitHub, Federal Register and Hacker News Algolia APIs, plus Utility Dive's on-site search. Direct fetches of known URLs worked on some sites.
- Blocked (HTTP 403) or unusable: emp.lbl.gov (LBNL main site), ferc.gov, enverus.com, gridstatus.io, docs.gridstatus.io, justia.com, web.archive.org (the tool refuses it), PJM pages (404s or stubs). Bash had no network permission.
- I could NOT open the LBNL data file (xlsx) or the LBNL PDFs: both exceeded the fetch tool's 10 MB limit. So the LBNL codebook (exact column names, which dates are populated) is UNVERIFIED. This is the first thing the parent should do (download the xlsx locally and read the Codebook tab).
- Every WebFetch result is a small-model summary of the page, not raw text. "VERIFIED" therefore means "primary page fetched and summarized", not "I read the raw bytes". Numbers I plan to quote publicly should be re-checked against the raw source.
- Coverage by question: Q1, Q2, Q5, Q8 reasonably covered. Q3 partial. Q4 (willingness to pay) and Q7 (liability/insurance) are thin: little hard evidence found.

---

## 1. Data availability for backtesting (Q1)

### 1a. LBNL "Queued Up" (the anchor dataset)

- Current edition: "Queued Up: 2026 Edition ... As of the End of 2025", published May 2026 (OSTI slide record dated June 30, 2026). VERIFIED. https://eta-publications.lbl.gov/publications/queued-2026-edition-characteristics ; https://www.osti.gov/biblio/3376147
- Authors Rand, Cheyette, Talley, Zhang, Gorman, Wiser, Seel, Jeong, Kahrl. Coverage: requests through end of 2025, 7 ISO/RTOs plus about 50 non-ISO balancing areas, about 98% of installed US capacity. VERIFIED (same URL).
- Data file: `lbnl_ix_queue_data_file_thru2025.xlsx`, containing project-level data, a codebook, and 36 summary tabs. VERIFIED (listing only; file itself not opened). https://eta-publications.lbl.gov/sites/default/files/2026-05/lbnl_ix_queue_data_file_thru2025.xlsx
- LICENSE: the ETA page says the data file is CC BY 4.0, attribution to Lawrence Berkeley National Laboratory and GridTracker. Verdict: redistribution and commercial use allowed with attribution. VERIFIED (ETA page, 2026 edition). The 2025 edition's page did not state a license (I checked). So the CC BY statement is edition-specific; confirm in the xlsx itself. The slide-deck license is not stated.
- Scope limits: transmission-connected only, not distribution or behind-the-meter. VERIFIED (2025 edition page).
- Headline stats (2026 ed.): about 8,200 active projects = 1,312 GW generation + about 749 GW storage; of capacity requested 2000-2020, 13% reached COD by end-2025, about 75% withdrawn, about 10% still active; median request-to-COD time above 5 years for projects built in 2025 and rising; 549 GW has a draft or executed IA but is not yet online. VERIFIED (ETA page).
- Prior edition (2025, end-2024): 13% COD, 77% withdrawn, 10% active for 2000-2019 requests; time to COD rose from under 2 years (2000-2007 requests) to over 4 years (2018-2024 requests). VERIFIED. https://eta-publications.lbl.gov/publications/queued-2025-edition-characteristics
- Point-in-time snapshots: LBNL publishes one annual vintage (editions for end-2020 through end-2025 exist on OSTI: DOIs 10.2172/1784303, 1864543, 1969977, 2335720, 3376147, plus the 2025 edition). VERIFIED that the editions exist. Whether older data files remain downloadable and are comparable year to year: UNVERIFIED. If they are, the six annual vintages are the only free "as-of" snapshots at annual resolution.
- Likely fields (from hobbyist repos, SECONDARY/UNVERIFIED): region, technology, MW, entry year, outcome status, COD date. A hobbyist repo says timing statistics are only possible for CAISO, MISO, PJM, SPP because ERCOT has no queue-entry dates for completed projects. https://github.com/bakulbadwal/interconnection-queue-lab (SECONDARY). Brian Potter says NYISO completed projects lack completion dates and ERCOT completed projects lack entry dates (SECONDARY, Feb 2025). https://www.construction-physics.com/p/inside-the-interconnection-queue
- Hobbyist estimates from the LBNL data (SECONDARY, one GitHub repo, MIT-licensed, uncaptured): PJM 2010-2020 entrants, naive completed share 16%, Aalen-Johansen competing-risks 10-year COD probability 21%; for CAISO/MISO/PJM/SPP 2010+ entrants the median request-to-COD rose from 3.2 years (built 2015-2019) to 5.7 years (built 2021-2025), P90 6.1 to 8.6.
- Record counts differ between two hobbyist repos: 38,201 vs 37,527 (see Contradictions).

### 1b. interconnection.fyi / GridTracker (data partner of LBNL, and the main commercial incumbent)

- Public site: about 44,281 queue requests, 1995-2026, compiled daily from ISO/RTO and utility queues, plus EIA-860 planned/operating plants, data centers. VERIFIED. https://www.interconnection.fyi/ (page dated as fetched 2026-10-29)
- Developer names, contacts, documents only in paid GridTracker. Full dataset via monthly CSV or daily Snowflake share. Copyright notice "All rights reserved", no redistribution terms stated. VERIFIED.
- GridTracker's own site: "Daily snapshots of every US interconnection queue since April 2024", full-text search of FERC, PUC dockets and ISO studies, an MCP connector for AI assistants, "queue history replay" including COD date changes over time, an API, "Individual reports can be purchased. For pricing, book a demo". No customers named. States the GridTracker team leads data collection for LBNL Queued Up. VERIFIED. https://www.gridtracker.io/
- Implication: the only comprehensive point-in-time archive of queues that I found is owned by the incumbent, begins April 2024, and cannot be backfilled by a newcomer except via partial ISO archives.

### 1c. ISO-by-ISO public files (state as of fetch; many pages were thin)

| ISO | What I verified | History / point-in-time | License / restriction |
|---|---|---|---|
| ISO-NE | Public queue in xlsx/PDF with fields QP, Type, Fuel, Net MW, Summer/Winter MW, County/ST, Op Date, Sync Date, W/D Date, POI, Serv, SIS/FAC/IA phase status, "Dev" (timeline deviation), Zone. Post-June 13, 2024 requests are in GIC-T behind login. VERIFIED https://www.iso-ne.com/system-planning/interconnection-service/interconnection-request-queue/ | Withdrawal date present; how long withdrawn rows are retained: not stated. Updated "day to day"; new public file after each cluster window | No terms stated on page |
| ERCOT | GIS Report (EMIL pg7-200-er), xlsx, public, monthly, first run 2017-02-01, "Display Duration 2555" (units unstated; 2555 days = 7 years, ESTIMATE that about 7 years of monthly reports stay posted). VERIFIED https://www.ercot.com/mp/data-products/data-product-details?id=pg7-200-er | Potentially 80+ monthly snapshots (ESTIMATE, needs checking: confirm the archive is actually downloadable) | Classification "Public". ERCOT terms of use not checked |
| CAISO | Public Queue Report posted as XLSX (375 KB) and PDF, last posted 10/29/2026 per page. VERIFIED https://www.caiso.com/library/public-queue-report . Fields, withdrawn history: not stated on page | Unknown | Unknown |
| MISO | Web tools: Active Projects Map, Project Status Tool, Power BI dashboards (active queue, COD dashboard). No downloadable queue file described on the page I fetched. VERIFIED (absence on that page only) https://www.misoenergy.org/planning/resource-utilization/GI_Queue/ | Unknown | "All rights reserved" copyright notice only |
| NYISO | Excel file "NYISO-Interconnection-Queue-09302026.xlsx" linked (suggests dated snapshots; date unstated on page). CEII request form and MyNYISO login for secure documents. VERIFIED https://www.nyiso.com/interconnections | Possibly dated files (filename pattern). Unverified | CEII gate for project detail |
| PJM | Pages I could reach were stubs or moved. "Serial Service Request Status" says column definitions are in a linked Excel file; the AE1-AG1 projects (616) were sorted into Transition Cycles; projects beyond AH1 are "no longer valid" with study reports "kept for record". VERIFIED (stub-level) https://www.pjm.com/planning/service-requests/serial-service-request-status | Unknown | Unknown |
| SPP | Page links to an OpsPortal GI queue, GI Queue and COD dashboard, weekly cluster status, study results postings. Whether withdrawn/completed files or costs appear: not stated. VERIFIED (thin) https://www.spp.org/engineering/generation-interconnection/ | Unknown | Unknown |

Not verified at all: exact public field lists for PJM, MISO, CAISO, SPP files; ISO website terms of use on reuse. I did not check them. Treat all ISO "license verdicts" as UNKNOWN pending a manual read of each ISO's terms of use.

### 1d. Cost data (study results)

LBNL publishes project-level interconnection cost datasets by region (VERIFIED, OSTI abstracts; hub page emp.lbl.gov/interconnection_costs is 403 to me):
- MISO: DOI 10.2172/1891311 (2022); "nearly 50% of all projects requesting interconnection from 2010 to 2020".
- SPP: DOI 10.2172/1971633 (2023); 845 projects, studies 2002-2023.
- PJM: DOI 10.2172/1922201 (2023); about 86% of new unique generators requesting 2000-2022.
- Non-ISO BAs (PacifiCorp, BPA, three Duke BAs): DOI 10.2172/3020547 (2026); 2,104 studies, 2000-2024; average cost of "complete" projects $194/kW for 2018-2024 (VERIFIED, abstract page https://www.osti.gov/biblio/3020547).
- LBNL also lists ISO-NE and NYISO short papers (stated on the SPP OSTI page).
- Findings: projects that complete studies have lower costs than withdrawn or still-active ones; network upgrades drive increases; per-kW costs fall with size (VERIFIED, OSTI pages).
- License on these cost files: not read. UNVERIFIED (likely the same LBNL CC BY pattern, do not assume).
- Key limitation for forecasting: these are "most refined" final estimates per project, not the time series of estimates at each study stage. UNVERIFIED how many stages are retained.

### 1e. EIA-860 / 860M, FERC filings
Not fetched this session. EIA-860M is a monthly public-domain US-government release (not verified here, from background knowledge: UNVERIFIED). It can confirm "operating" status and actual COD for a project, which is how a hobbyist repo cross-validates LBNL (SECONDARY: https://github.com/tmedinaa-ops/iso-eia-merged). FERC eLibrary holds executed IAs and complaints; no automated access tested.

### 1f. Summary: is the underlying data replicable by a competitor?
Yes. The core outcome labels (withdrawn / COD / active, entry date, size, tech, region) are in a CC BY 4.0 file that anyone, including GridTracker's competitors and LLM agents, can download free. VERIFIED (license statement). That is the main finding against a data-moat thesis.

---

## 2. Prior art on predictability (Q2)

- Johnston, Liu, Yang, "An Empirical Analysis of the Interconnection Queue", NBER WP 31946, Dec 2023. VERIFIED (PDF read). Hand-collected PJM data: 4,085 requests and 7,117 studies, 2008-2020. Findings: a 10% increase in higher-queued generators cuts probability of receiving the final study by 5% on average; second-study interconnection cost median $0.05M/MW, 90th percentile $0.41M/MW; "observably similar generators can have very different interconnection costs"; a generator with second-study cost above $0.1M/MW (33% of generators) is 49% more likely to withdraw before the third study; "less than a quarter of wind and solar generators that start the process complete it". Structural economic model, not an out-of-sample forecasting benchmark; no accuracy metric. https://www.nber.org/papers/w31946
- Rand et al. (LBNL), Joule 2024, "Grid connection barriers to renewable energy deployment in the United States" (OpenAlex, 78 citations). Content not fetched (publisher redirect failed). UNVERIFIED beyond title.
- arXiv 2609.10455 (Sept 2026), "Cascading Vulnerability Analysis..." uses LBNL data through 2025; tests temporal clustering of withdrawals (39 monthly withdrawal bursts) and simulates cost-reallocation cascades; reports NO predictive accuracy metrics. VERIFIED (abstract). So withdrawal clustering exists, which is a possible feature (cohort-level shocks), but it is not a forecasting result.
- SSRN 7303000 (2026), "Probabilistic Assessment of Interconnection Cost Exposure for ERCOT Data Centers under SB6": Monte Carlo, median exposure about $19.1M (1.4% of capex) for 75-200 MW, about $48.9M (3.6%) on the most congested nodes. VERIFIED (Crossref abstract). Shows probabilistic cost products are being produced academically for large-load, not sold.
- Searches (Crossref, OpenAlex, arXiv) for "predict / forecast / machine learning / survival" + interconnection queue completion or withdrawal found no peer-reviewed project-level predictive model with reported accuracy. This is an absence-of-evidence result from limited search tools, not proof. One hobbyist work uses competing-risks estimators (Aalen-Johansen) on LBNL data (SECONDARY, GitHub, MIT).
- Baselines by year/ISO: the aggregate completion rate is about 13% of capacity (2000-2020 entry), withdrawals about 75% (VERIFIED, LBNL). Potter finds a roughly constant 72% withdrawal for 1999-2018 entries (SECONDARY). Regional per-year baselines I could not extract (LBNL xlsx unreadable to me).
- Which features matter: evidence supports (i) interconnection cost estimate after each study (strongly, Johnston et al.), (ii) queue position / amount of capacity ahead (Johnston et al.), (iii) hybrid solar+storage projects have lower withdrawal (Potter, SECONDARY), (iv) cohort-level withdrawal bursts (arXiv 2609.10455). Features available at entry only (size, fuel, state, ISO, year) are the ones in the public snapshot. I found no study showing that those alone achieve strong discrimination. That is the key empirical unknown.
- Important regime-change warning: ISO processes are being rewritten (cluster studies under Order 2023, PJM's reopened Cycle 1 with 800+ projects / 220 GW per Utility Dive 2026-04-29, MISO/SPP/PJM fast-track lanes). Historic serial-queue outcomes may not predict cluster-process outcomes. AEU report (June 2026) finds "no evidence yet" that requests are processed faster (VERIFIED via Utility Dive https://www.utilitydive.com/news/generator-interconnection-reform-ferc-spp-miso-pjm/823613/). LBNL says full Order 2023 effects "not yet measurable" (VERIFIED, 2025 edition page).

---

## 3. Who sells predictions or adjacent products (Q3)

(c) Competitor and price table. Only what I could verify.

| Vendor | What they sell | Probability / cost / timeline outputs? | Price | Self-serve? | Evidence |
|---|---|---|---|---|---|
| GridTracker / interconnection.fyi (CS Technology Ventures, LLC) | Daily queue snapshots since Apr 2024, queue history replay, dockets/FERC/study full-text, MCP for AI, API, per-report purchase, free public site | No completion-probability product seen. History replay of COD changes | Flat subscription, unpublished. Reports: "book a demo" | Free public view; paid needs sales | VERIFIED https://www.gridtracker.io/ ; https://www.interconnection.fyi/ . Funding, customers: not found |
| Cleanview | Trackers for data centers, BTM power, and clean energy/storage projects from queues (3,491 planned solar, 2,465 battery, 618 wind projects; 410 developers), web, Excel, API | Shows share with signed IAs; no probability product seen | $9,000/yr per subscription (up to 5 users), +$5,000/yr API, $4,900 one-time dataset | Pricing public; page says "Contact sales", no checkout seen | VERIFIED https://www.cleanview.co/ and /pricing |
| Paces | Site discovery, grid/environmental/permitting risk reports and modeling, AI agent | Claims "grid risk" and reports; no probability or cost output described | Not listed | Demo/contact | VERIFIED https://www.paces.com/ . Funding not found |
| LevelTen | PPA Price Index (subscription only), marketplace | Not interconnection | Not listed; no single-report sales | Subscribe link, demo | VERIFIED https://www.leveltenenergy.com/ppa |
| Heatmap Pro | County opposition risk scores, local laws, "time to power" in county profiles | Not interconnection | Not listed | Demo only | VERIFIED https://heatmap.news/pro |
| Grid Status | Open-source `gridstatus` Python library (BSD-3) covering queues for several ISOs, hosted API with free and paid plans | Data only | Not verified (pricing page 403) | Self-serve API | SECONDARY https://github.com/gridstatus/gridstatus |
| Enverus | Not verified (site 403) | UNVERIFIED | UNVERIFIED | UNVERIFIED | Searched: enverus.com, /solutions/interconnection/ (403) |
| Pearl / GridCARE / others named in brief | Not checked beyond this | UNVERIFIED | UNVERIFIED | UNVERIFIED | Not found |

Takeaways:
1. The two vendors with the broadest queue data (GridTracker, Cleanview) sell by subscription or demo, not per-report card checkout (as far as visible). Price anchor for a data subscription: $9K/yr (Cleanview). VERIFIED.
2. No vendor I could reach publishes a calibrated completion probability or a public track record. That supports "white space" but is also consistent with "no one has found a buyer who pays for it". Cannot distinguish with evidence in hand.
3. Funding and customers: not found for any of them.

---

## 4. Buyer and willingness to pay (Q4)

Findings are thin. Honest summary: I found NO direct evidence that lenders, tax equity, acquirers, brokers or small consultancies pay $100-$1,000 per project by card for interconnection-outcome probabilities.

What I did find:
- Pricing of adjacent data products is annual subscription ($9K/yr Cleanview, VERIFIED) with sales contact; LevelTen sells subscription only and refuses single reports (VERIFIED). Both lean away from per-event card purchase.
- GridTracker advertises per-report purchase but behind "book a demo" (VERIFIED).
- Large buyers use studies done by consultants/independent engineers; I found no priced examples (searches blocked). UNVERIFIED: cost of diligence reports and interconnection consulting. I did not find a source.
- How buyers trust forecasts: no direct evidence. Plausible mechanisms (published calibration record, point-in-time archive, reference customers) are my inference, not sourced.

Revenue arithmetic (ESTIMATE, my assumptions): $300K ARR at $500 per report = 600 reports/yr = 50/month; at $1,500 = 200/yr (about 17/month); at $9K annual accounts = about 33 accounts. With 10-15 hrs/wk and no sales calls, the binding constraint is demand, not model-building.

Most decisive unknown for Q4: whether a buyer will pay for a probability that is better than the pivot table they can build from the free LBNL file. See Section (b).

---

## 5. Interconnection cost estimation ($/kW by POI) (Q5)

- Public datasets exist from LBNL by ISO (Section 1d). Per-POI granularity (POI names) is partly public in ISO studies; CEII limits apply at NYISO (VERIFIED: CEII request form) and likely elsewhere (UNVERIFIED).
- Cost is hard to predict and strongly tied to withdrawal: Johnston et al. show same-looking generators have very different costs, median $0.05M/MW vs P90 $0.41M/MW at the second study (VERIFIED). So demand for cost forecasts is plausible on its face: developers and acquirers care about cost surprises.
- Who serves it: unknown from my evidence. LBNL gives retrospective benchmarks free. Paces/others claim "grid risk" modeling (VERIFIED claim, content unclear). Large-load: academic Monte Carlo exists (SSRN 7303000). Price evidence: none found.
- Caution: PJM-style cluster cost sharing (Order 2023) changes cost allocation, so legacy $/kW data may not transfer (VERIFIED by Johnston et al. on PJM's planned reforms, and by FERC orders in general).

---

## 6. Defensibility (Q6)

- Could a funded competitor or LLM agent replicate a public-data model in weeks? Based on evidence: yes for the baseline. LBNL data is CC BY 4.0 (VERIFIED), several hobbyists already built competing-risks and cleaning pipelines on it (SECONDARY GitHub repos, all MIT/Apache), and GridTracker already ships an MCP server so AI agents can query its full record (VERIFIED). A model on public features is not a moat.
- What can create a moat (my analysis, not sourced): (1) point-in-time archives. GridTracker has daily snapshots since April 2024 (VERIFIED), so a newcomer starts behind; partial offset: ERCOT monthly reports since 2017 (VERIFIED existence of report; archive depth unverified). (2) Proprietary or customer-submitted outcome labels. (3) A time-stamped, public prediction log, which is a track record nobody can backdate. The log is cheap to start and cannot be bought later, but it takes years to mature because median request-to-COD is over 5 years (VERIFIED, LBNL), though withdrawals resolve faster and are a usable earlier label.
- Analogy with verified evidence: LevelTen's PPA Price Index is built from offers on its own marketplace (206 offers from 166 projects in North America in Q3 2026, subscription-only). VERIFIED. https://www.leveltenenergy.com/ppa . The moat there is a transacting platform that generates contributed data, not public data. I did not verify any other index analogy (e.g., real-estate or credit indices), so none is claimed.
- Honest verdict: the durable asset is the ground-truth archive plus track record, and the party best positioned is GridTracker (already compiles LBNL's data, owns snapshots, has a customer base). A part-time solo founder cannot out-collect them.

---

## 7. Liability and positioning (Q7)

- Securities angle: 15 U.S.C. 80b-2(a)(11) excludes "the publisher of any bona fide newspaper, news magazine or business or financial publication of general and regular circulation" from "investment adviser", and the SEC and courts treat that exclusion narrowly (statute text VERIFIED via Cornell LII https://www.law.cornell.edu/uscode/text/15/80b-2 ; Lowe v. SEC 1985 not fetched, UNVERIFIED here). A project-level interconnection forecast is not advice about a specific security, which makes the Advisers Act risk low in my judgment (ESTIMATE, not legal advice; not verified with counsel). A statistical rating organization exclusion also exists in the same statute; I did not research credit-rating regulation.
- Contractual: a probability is a statement of belief, not a guarantee. Standard approach (my inference, no source): disclaimers, no reliance clause, limit liability to fee paid, clickwrap terms. Whether E&O/tech insurance is needed or obtainable cheaply: UNVERIFIED, nothing found.
- Practical liability: the buyer who "signs" (lender, consultancy) transfers risk back to the vendor if the report is used as the basis of a sign-off. That conflicts with a cheap per-report model unless positioned as one input. No evidence found on how existing vendors word this.

---

## 8. Standardization and regime risk (Q8)

Does forecasting become more or less valuable in 2-5 years? Evidence points both ways:

Reasons it matters less or changes:
- FERC Order 2023 (final rule 2023-09-06, rehearing order 2024-04-16; both Federal Register, VERIFIED) moves to cluster, first-ready first-served, with penalties and deposits. AEU (June 2026): all regions implementing, SPP and CAISO "promising", PJM/ISO-NE/NYISO "expected progress", MISO "incomplete progress" (VERIFIED via Utility Dive). Higher entry costs should reduce speculative requests and change base rates. Old base rates may not carry over.
- On June 18, 2026 FERC issued show-cause orders to CAISO, ISO-NE, MISO, NYISO, PJM, SPP on large-load interconnection, with "escalating readiness requirements" at each study phase, and questioned transparency of network upgrade costs (VERIFIED, Utility Dive 2026-06-22 https://www.utilitydive.com/news/ferc-doe-data-center-interconnection/823360/). If cost transparency improves, a cost-estimation product loses edge; if not, demand rises.
- Fast tracks: PJM "shovel-ready" fast-track approved by FERC (2026-06-10 headline), MISO accelerated queue (2026-10-06 headline) (VERIFIED headlines only, articles not read).

Reasons it matters more:
- PJM's reopened queue: more than 800 projects, 220 GW (106 GW gas), review expected to take 1-2 years, using Google Tapestry AI (VERIFIED, Utility Dive 2026-04-29). This creates a one-off wave of new decisions to forecast, but the process is new, so no history applies.
- Large-load queues are huge and speculative: Texas 438 GW (2026-06-22) and 474 GW (2026-08-05) per Utility Dive headlines; "Texas hits pause on data centers"; "The Missing Half of the Queue: Why FERC Should Require Load-Side Interconnection Queue Disclosure" (SSRN 2026). Data on load-side outcomes is scarce, so a calibrated forecast may be valuable there, but there is no history to calibrate on. (headlines VERIFIED; contents not read)

Net for Idea B: the 2000-2020 serial-queue history that makes backtesting possible is the regime that is ending. This both undermines the backtest-to-future transfer and means the track record has to start fresh on the new processes.

---

## (a) Data inventory with license verdicts

| Dataset | Fields (known) | History depth | Update | License / terms | Point-in-time? | Verdict |
|---|---|---|---|---|---|---|
| LBNL Queued Up 2026 data file (thru 2025) | project-level incl. status, region, tech, MW, dates (exact columns UNVERIFIED); 36 summary tabs + codebook | 2000-2025 requests | Annual (May) | CC BY 4.0, attribute LBNL + GridTracker (VERIFIED) | Final-state snapshot only; older annual editions give yearly vintages (availability unverified) | Usable commercially with attribution |
| LBNL interconnection cost datasets (MISO, SPP, PJM, non-ISO; ISO-NE, NYISO short papers) | project-level cost summaries, status | 2000-2024 depending on region | Irregular | Not read; do not assume | Final estimates, not stage history | Verify terms before using |
| interconnection.fyi public site | filters by region, state, year, type, status | 1995-2026 | Daily | All rights reserved, no data terms | Replay only in paid GridTracker, snapshots since Apr 2024 | Do not scrape/redistribute without a license |
| GridTracker paid CSV/Snowflake | adds developer names, documents | 1995+; daily snapshots since Apr 2024 | Daily/monthly | Commercial subscription | Yes (from Apr 2024) | Competitor; license terms for derived products unknown |
| ISO-NE public queue | see 1c | queue file | daily | not stated | withdrawn dates, no archive stated | check terms |
| ERCOT GIS report | milestones/trends | monthly since 2017-02 | monthly | Public | monthly archive likely (about 7 yrs, unverified) | Best candidate for point-in-time labels |
| CAISO public queue report | not stated | not stated | file posted 2026-10-29 | not stated | unknown | check |
| MISO / SPP / PJM / NYISO | see 1c | unknown | unknown | unknown / CEII at NYISO | unknown | check |
| EIA-860/860M | not fetched | - | monthly | US gov (UNVERIFIED here) | monthly | use for label checks |
| NBER W31946 PJM hand data | 4,085 requests 2008-2020 | - | static | authors' dataset; availability unknown | - | not reusable by default |

---

## (b) Feasibility of a two-weekend backtest

Honest framing: this tests whether public features give useful lift over a base-rate table. I have not run it; I could not open the data.

Datasets (all free): LBNL 2026 xlsx (CC BY 4.0); LBNL cost files for PJM/MISO/SPP (to add a cost feature on the subset with costs); older LBNL editions if downloadable (annual as-of checks); ERCOT monthly GIS reports and ISO-NE file for cross-checking dates; EIA-860M for COD confirmation.

Step 0 (30 minutes, decides everything): open the Codebook tab. Confirm that queue-entry date, withdrawal date, COD date, IA date, and status are populated for CAISO, MISO, PJM, SPP, ISO-NE. If withdrawal dates are missing for a large share, status "as of T" cannot be reconstructed and the design below fails.

Target variables (two):
1. P(withdraw before T+3y), P(COD before T+3y) for projects active at as-of date T (competing risks, not Kaplan-Meier).
2. Time to COD for built projects (secondary).

Design: temporal split. Choose T1 = end-2018, T2 = end-2021. Reconstruct each project's status as of T from entry/withdraw/COD dates. Train on outcomes known by T1 for the cohort active at T1; test on projects active at T2 for outcomes observed through 2025. Never use final-state fields as features.

Features available at as-of time: ISO, state, technology, MW, entry cohort, age in queue, hybrid flag, whether IA signed by T (if IA date exists), proposed COD slippage if recorded (probably not in LBNL; GridTracker has it only since 2024). Optional: cost estimate where LBNL cost files exist (note: only final estimates, so this leaks).

Baselines (must beat all three):
1. ISO x technology completion rate from training cohort.
2. Age-conditional base rate ("landmark": P(outcome | queued N years)).
3. Constant overall rate.

Success criterion (my proposal, ESTIMATE, not evidence-based): out-of-time AUC at least 0.75 AND Brier skill at least 15% over baseline 1 AND calibration slope between 0.9 and 1.1 AND top-decile vs bottom-decile realized COD rate ratio of at least 3x, holding in at least 3 of 5 ISOs. Anything less means the product is a base-rate table that LBNL already gives away free. Also report results separately for post-2023 entrants (cluster regime) if sample allows; I expect almost no resolved outcomes there.

Time: weekend 1 data cleaning and status reconstruction; weekend 2 models plus calibration plot. Per the user's rules, results must be captured with `pow run` into results/ with hardware named before any number is quoted publicly.

Likely failure modes: ERCOT/NYISO date gaps (SECONDARY), survivorship in entry-date records, projects that re-enter the queue under new numbers, regime change after 2023, label latency (median over 5 years to COD).

---

## (d) Verdict

NO-GO as the primary business as framed (per-report calibrated forecasts built on public queue history). NEEDS-MORE-EVIDENCE only for a narrow variant: a free, public, time-stamped prediction log for one narrow slice (for example PJM Cycle 1 or ERCOT large-load), used as a lead magnet, not as the revenue product.

Why:
1. The labels are free and licensed for commercial reuse (CC BY 4.0); the data partner/incumbent (GridTracker) already holds the only daily point-in-time archive, MCP/API distribution, and report sales. A solo part-timer cannot out-collect them.
2. No evidence found of buyers paying per project by card; adjacent vendors sell annual subscriptions or demos ($9K/yr benchmark).
3. Regime change: the history that supports a backtest is the pre-cluster, pre-Order-2023 regime, and FERC/ISO rewrites (PJM Cycle 1, large-load orders) are replacing it.
4. Label latency is long (median over 5 years to COD), so a public track record takes years to mature; withdrawals resolve faster but are not what lenders ask about.
5. Liability fit is poor for the buyers who sign.

Single most decisive unknown: does a model on public as-of features achieve out-of-time lift (AUC about 0.75+, calibration slope near 1, 3x decile spread) over a free ISO x technology x age base-rate table? If no, stop. If yes, the next unknown is whether anyone will pay for it, which only a fake-door or priced landing page can test.

---

## Contradictions and discrepancies found

1. LBNL 2025 ed.: 77% withdrawn / 13% COD / 10% active for 2000-2019 requests; 2026 ed.: about 75% / 13% / 10% for 2000-2020. Different cohorts; sums fine. A hobbyist repo's "13/75/19" headline sums to 107%, so its 19% is mislabeled or from another cut (SECONDARY).
2. Active queue: LBNL 2026 says about 8,200 projects (1,312 GW gen + 749 GW storage); LBNL 2025 says about 10,300 (1,400 GW + 890 GW); GridTracker homepage shows 9,781 active projects, 1,860 GW; Potter (Feb 2025) cites about 11,000+ projects, 1,900 GW. Differences likely due to date, scope (distribution, data center, storage double counting). Never mix sources in a claim.
3. Coverage: LBNL 2025 edition page says about 97% of US capacity and 49 non-ISO BAs; 2026 page says about 98% and 50. Minor, edition-specific.
4. Record counts: 38,201 (one hobbyist repo) vs 37,527 (another) from "LBNL Queued Up 2026"; vs interconnection.fyi 44,281 (different scope).
5. Licensing: interconnection.fyi page says "All rights reserved"; LBNL's file built with the same data is CC BY 4.0 (attribute LBNL and GridTracker). They are different works; the CC BY covers only LBNL's published file. The 2025 edition page I read did not mention CC BY.
6. Median time to COD: LBNL says median above 5 years for 2025-built projects (all regions "where data is available"); hobbyist repo says 5.7 years median for 2021-2025 in four ISOs. Consistent, not identical scope.
7. Potter's constant 72% withdrawal for 1999-2018 entrants vs the LBNL cohort rate of 75-77% for 2000-2019/20. Different cohort and unit (count vs capacity?). Not reconciled.

---

## Unverified claims (do not use without checking)

- LBNL data file column names, status coding, and which dates are populated by ISO (file unreadable via my tools).
- License terms of LBNL cost datasets; ISO website terms of use for queue files (all ISOs).
- Whether older LBNL data files and ISO monthly archives are still downloadable; ERCOT monthly archive depth (2555-day display duration inferred, units unstated).
- PJM, MISO, CAISO, SPP public queue field lists and whether they include withdrawn projects.
- Enverus, Grid Status, Pearl, GridCARE offerings and prices (sites blocked or not checked).
- Funding and customers for GridTracker, Cleanview, Paces (not found).
- Cost of diligence reports and interconnection consulting; willingness of lenders, tax equity, acquirers, brokers to pay per project; how buyers verify forecasts; insurance (E&O) norms. No sources found.
- Content of the Joule 2024 paper (Rand et al.) and of the Brattle and Grid Strategies reports (not fetched).
- Lowe v. SEC and current SEC guidance on publisher exclusion; any state-law angle.
- EIA-860M terms (public domain assumed from background knowledge).
- Bodies of Utility Dive articles listed only as headlines (PJM fast-track, MISO accelerated queue, Texas 438/474 GW queue and pause).
- Whether PJM Cycle 1 attrition will be high (no forecast in the article).

## Searches that failed or returned nothing useful

DuckDuckGo html/lite (CAPTCHA), Bing (irrelevant results), Brave (429), Yahoo (500), Mojeek and Ecosia (403), Semantic Scholar (429), web.archive.org (tool refuses), emp.lbl.gov (403), ferc.gov (403), enverus.com (403), gridstatus.io (403), pjm.com pages (404/stubs), caiso.com queue-reports page (404), nyiso page lacks field detail. Crossref/OpenAlex/arXiv queries for "predict" + "interconnection queue" returned no project-level forecasting papers.

---

## Ideas we may have missed (only with some evidence; all weak)

1. Large-load (data center) queue risk and cost exposure. Evidence: Texas queue of 438-474 GW and a data center pause (Utility Dive headlines, Jun-Aug 2026); FERC's June 18, 2026 show-cause orders push "escalating readiness requirements" and cost transparency (VERIFIED); academic Monte Carlo of ERCOT SB6 interconnection cost exposure for 75-200 MW sites (VERIFIED, SSRN 7303000); "Missing Half of the Queue" disclosure paper. Buyers: data center developers, land brokers, utilities. Card-buying behavior: no evidence. Calibration data: almost none yet.
2. Cost benchmarking from LBNL's per-region cost datasets, packaged as a per-POI or per-utility $/kW "should I worry" screen. Evidence of demand: only that cost drives withdrawal (VERIFIED, Johnston et al.). Price evidence: none; the data is free (LBNL), so value would be in POI-level detail from study PDFs (CEII limits unverified).
3. A document-parsing utility (extract network upgrade cost tables and milestones from ISO study PDFs into structured rows) sold per document. Evidence: GridTracker already sells "millions of pages" of searchable study documents with AI insights (VERIFIED), so this space is occupied; the open piece might be a per-document CLI/API, but no demand evidence.
4. Time-limited event service: PJM Cycle 1 (800+ projects, 220 GW) tracking, with a public prediction log. Evidence: size of event (VERIFIED, Utility Dive 2026-04-29). Whether anyone pays: unknown.

None of these has direct evidence of card-buying professionals who sign.
