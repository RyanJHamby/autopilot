# Grid/energy solo-SaaS research: index and decision (2026-10-29)

## Contents

| File | What it is |
|---|---|
| `01-wedges-report.md` | Original brief: Idea A (tax-credit compliance ledger) and Idea B (interconnection-outcome forecasts). Synthesis plus both raw-notes appendices. |
| `02-pivots-report.md` | Follow-up: three pivots (supplier certificates, prevailing-wage evidence, interconnection application pre-check), plus a data-check addendum (section 9). Includes raw-notes appendices. |
| `raw-notes/` | Unedited agent notes: `ideaA-notes.md`, `ideaB-notes.md`, `pivot1-notes.md`, `pivot2-notes.md`, `pivot3-notes.md`. |

The two reports at `docs/grid-wedge-research-2026-10-29.md` and `docs/grid-pivots-research-2026-10-29.md` are the originals; the copies here are identical at the time of writing. Nothing is committed.

## Trust caveat

No general web-search tool worked in any pass. Research used WebFetch (model summaries, not raw text) plus a few local reads. Vendor pricing, demand, counts and liability findings are weak or unsourced. "None found" means "not found". A direct `curl` was denied (logged in `docs/permissions-log.md`), so no data file was downloaded or counted.

## Verdicts

| Idea | Verdict | Decisive unknown |
|---|---|---|
| A. Tax-credit compliance ledger | Needs more evidence; leaning no-go as framed | Will transferees and signing CPAs/counsel accept a software-generated MACR file plus supplier-certificate ledger on small deals, and do small claimants paying $200-$2,500 exist? |
| B. Interconnection-outcome forecasts | No-go as framed | Does a public as-of-features model beat a free base-rate table out of time? |
| Pivot 1. Supplier certificates | Weak: penalty (IRC 6695B) needs knowledge plus a large understatement; the hard part is knowing your own sub-tier chain | Do small suppliers get per-buyer certification requests in volume and would they pay $200-$2,500? |
| Pivot 2. Prevailing-wage evidence | Leans against: under 1 MW AC exempt, buyers are developers with advisors, solar shrinks after 2027; storage 1 MW+ is the only durable niche | How many 1 MW AC+ projects are built by firms with no certified-payroll system, and would they pay by card? |
| Pivot 3. Interconnection application pre-check | Cautious, untested: no direct competitor found, but no evidence of the pain; public data (Rule 21) mostly excludes systems under ~30 kW | The real first-pass deficiency rate, and whether installers feel it as costly |

## Decision so far

- No idea has shown a small buyer would pay by card. No build time is justified yet.
- The realistic first milestone is $30-60K ARR from one narrow product, not $300K.
- Only cheap demand tests are worth doing: a one-page card-checkout offer with a pre-agreed kill rule (proposed, not agreed: stop if fewer than 5 paid purchases from at least 500 unique visitors by day 30).
- The supplier-certificate template was suggested as the cheapest to build, not the best supported by evidence; its own research was rated weak. Pivot 3 is the alternative test.
- The deciding question for choosing: which buyer (small component suppliers or solar installers) can be reached without cold email.

## Open follow-ups

1. Download EIA-860M (`https://www.eia.gov/electricity/data/eia860m/xls/september_generator2026.xlsx`, September 2026 release, next release 2026-11-24) and count proposed 1 MW+ storage units and owners.
2. Review CPUC quarterly IOU interconnection data reports (path in `02-pivots-report.md` section 9); contents unknown.
3. Confirm vendor pricing pages and any supplier, installer or application counts with a working search tool.
4. Legal review before shipping anything touching perjury-backed certifications or interconnection engineering.
5. Not done: `pow log` entry and commit. Do these only if requested.
