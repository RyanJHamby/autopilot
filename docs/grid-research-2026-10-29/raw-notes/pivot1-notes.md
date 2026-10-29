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
