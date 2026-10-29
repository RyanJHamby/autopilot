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
