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
