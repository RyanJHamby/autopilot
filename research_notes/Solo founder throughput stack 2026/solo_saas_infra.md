# Solo-founder SaaS infrastructure and stack defaults (as of November 2026)

Method note: all prices below were fetched from official vendor pages on 2026-11-09 via page-fetch (no web search tool was available in this session, so coverage is limited to pages fetched directly). Vendor pages are vendor claims. Several pages carry no "last updated" date. Anything not listed here was not verified.

## Hosting and compute (Vercel, Cloudflare, Fly, Railway, Render)

### Takeaway
Vercel Pro ($20/mo, includes $20 usage credit) is the lowest-friction default for a Next.js product, but Hobby forbids commercial use and Pro usage is uncapped unless a budget is set. Cloudflare Workers Paid ($5/mo) is the cheapest scalable compute with no egress charge; Railway and Fly are usage-based container options. Fly has no free tier for new orgs. Render was not verified.

### Cited Findings
- Vercel Hobby is $0 and "is for personal, non-commercial use"; Pro is $20/mo and includes a $20 monthly credit; each additional developer seat is $20/mo, viewer seats unlimited (seen 2026-11-09) — [Vercel pricing](https://vercel.com/pricing)
- Vercel Hobby includes 1M CDN requests, 100 GB Fast Data Transfer, 4 hrs Fluid Active CPU, 1M function invocations per month, and "cannot purchase additional usage" — [Vercel pricing](https://vercel.com/pricing)
- Vercel Pro includes 10M CDN requests and 1 TB Fast Data Transfer; overage from $2 per 1M requests, from $0.15/GB transfer, from $0.128/hr Active CPU, from $0.60 per 1M invocations — [Vercel pricing](https://vercel.com/pricing)
- Vercel Pro overage is described as "uncapped"; new teams get a default on-demand budget of $200 (editable), with optional auto-pause at 100% — [Vercel pricing](https://vercel.com/pricing)
- Vercel runtime logs are retained 1 hour on Hobby and 1 day on Pro (30 days needs Observability Plus); Web Analytics is 50K events free then $3 per 100K on Pro; Workflow events $20 per 1M; Queues ops from $0.60 per 1M — [Vercel pricing](https://vercel.com/pricing)
- Cloudflare Workers Free: 100,000 requests/day, 10 ms CPU per invocation, no overage (stops at limit). Paid: $5/mo minimum, 10M requests and 30M CPU-ms included, then $0.30 per extra 1M requests and $0.02 per extra 1M CPU-ms; no egress/bandwidth charge; CPU up to 5 min per invocation — [Cloudflare Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/)
- Railway: Free $1/mo credit; Hobby $5/mo with $5 credit; Pro $20/workspace with $20 credit; memory ~$10/GB-month, CPU ~$20/vCPU-month, volumes ~$0.15/GB-month, egress $0.05/GB (seen 2026-11-09) — [Railway pricing](https://railway.com/pricing)
- Fly.io: new organizations have no free tier or monthly allowance; $1 trial credit lasts 7 days; card required afterward. shared-cpu-1x 256MB is $2.19/mo; volumes $0.15/GB-mo; egress $0.02/GB in NA/EU (higher elsewhere); Managed Postgres starts at $38/mo — [Fly.io pricing](https://docs.fly.io/about/pricing)

### Inferences
- Because Hobby is non-commercial, any revenue-generating product on Vercel needs Pro, so the real floor is $20/mo, partly offset by the $20 credit.
- Vercel's uncapped overage is the main cost-surprise risk; set the budget/auto-pause on day one.
- Fly's $38/mo Managed Postgres floor and no free tier make it a worse fit than Neon/Supabase for a zero-revenue stage.

### Gaps
- Render pricing/limits not fetched, so no claim made.
- Cloudflare Pages/D1/R2/Containers pricing not fetched.
- No credible postmortems or outage/pricing-change announcements collected (no search tool). Community complaints about Vercel bills were not verified.

## Databases, backend, auth, email, queues

### Takeaway
Managed serverless Postgres is the default: Neon (usage-based, scale-to-zero, free tier) or Supabase ($25/mo Pro, bundles auth). Auth free tiers are large (Clerk 50K MRU, Neon Auth 60K MAU free, Supabase 50K MAU), so auth is not a cost problem at small scale. Resend free tier is 3,000 emails/mo but only 100/day.

### Cited Findings
- Neon Free: $0, 100 CU-hours/project, 1 GB storage per project (20 GB per account), scale-to-zero after 5 min (cannot be disabled), 100 projects, 10 branches, 6-hour history, 5 GB egress; exceeding storage blocks writes, exceeding compute/egress suspends compute until next period, data not deleted — [Neon pricing](https://neon.com/pricing)
- Neon Launch: pay-as-you-go with no monthly minimum, $0.106/CU-hour, $0.35/GB-month storage, up to 7-day history, 500 GB egress then $0.10/GB; Scale is $0.222/CU-hour with 30-day history — [Neon pricing](https://neon.com/pricing)
- Neon bundles Auth: up to 60K MAU free per project and 1M on paid — [Neon pricing](https://neon.com/pricing)
- Supabase Free: 500 MB DB, 50K MAU, 5 GB egress, projects paused after 1 week of inactivity, no backups. Pro from $25/mo: 8 GB disk, 100K MAU (then $0.00325/MAU), 250 GB egress, daily backups kept 7 days, no inactivity pausing — [Supabase pricing](https://supabase.com/pricing)
- Clerk bills on Monthly Retained Users: 50,000 free per app on Hobby; Pro $25/mo monthly ($20 annual); $0.02/MRU for 50,001-100,000; B2B Authentication add-on $100/mo; Protect $0.002/check beyond 10K free — [Clerk pricing](https://clerk.com/pricing)
- Resend: Free 3,000 transactional emails/mo with a 100/day cap, 1 webhook endpoint, 30-day retention; Pro $20/mo (50,000 emails) or $35/mo (100,000), overage $0.90 per 1,000 — [Resend pricing](https://resend.com/pricing)
- Vercel offers Workflow (durable execution, $20 per 1M events) and Queues (from $0.60 per 1M ops) as first-party primitives, in the same plan pricing — [Vercel pricing](https://vercel.com/pricing)

### Inferences
- Supabase's free-tier pause and no-backup policy make it unsuitable for a paying product; Pro at $25 is the real entry price. Neon Launch can be cheaper at idle because compute scales to zero, but storage is always billed and free-tier history is only 6 hours.
- Using the database vendor's bundled auth (Supabase Auth, Neon Auth) avoids a separate vendor; Clerk costs nothing until 50K MRU but adds lock-in and a per-MRU bill after.
- Keeping queues/workflows inside the host platform (Vercel Workflow/Queues, Cloudflare Queues) is simpler than adding a separate vendor.

### Gaps
- Not fetched: Turso, PlanetScale, Better Auth, Auth.js, Inngest, Trigger.dev, ORMs (Drizzle/Prisma). No claims made. Better Auth and Auth.js are open-source libraries with no vendor fee, but that was not verified here.
- Neon Auth's relationship to current Neon/Databricks ownership and any pricing changes were not verified.

## Payments and tax (Stripe vs merchant of record)

### Takeaway
Stripe Managed Payments now exists: Stripe acts as merchant of record for digital products, handling sales tax/VAT/GST in 80+ countries for 3.5% on top of normal Stripe Payments fees (~6.4% + 30c on a domestic card before Billing). Polar (4-5% + 40-50c) and Paddle (5% + 50c) are the other MoRs fetched. Lemon Squeezy could not be verified.

### Cited Findings
- Stripe standard card fee: 2.9% + 30c domestic; +1.5% international cards; +1% currency conversion. Billing: 0.7% of Billing volume pay-as-you-go. Stripe Tax Basic: 0.5% per transaction (no-code) or $0.50 per transaction (API) where registered — [Stripe pricing](https://stripe.com/pricing)
- Stripe Managed Payments: 3.5% per successful transaction "in addition to Payments fees" — [Stripe pricing](https://stripe.com/pricing)
- Managed Payments: Stripe is the merchant of record; handles sales tax, VAT, GST in 80+ countries, plus fraud prevention, disputes, transaction-level support; subscriptions work via Billing but only through Checkout or Payment Links — [Stripe Managed Payments docs](https://docs.stripe.com/payments/managed-payments)
- Managed Payments does not support Connect, Elements/advanced integrations, third-party tax integrations, one-off invoices on subscriptions, or subscription creation outside Checkout/Payment Links — [Stripe Managed Payments docs](https://docs.stripe.com/payments/managed-payments)
- Managed Payments eligibility: access depends on an eligibility review; seller must be based in a supported location (US, CA, most of EU/EEA, GB, CH, AU, HK, JP, SG); digital products only (SaaS, software, courses, AIaaS tax codes exist); not physical goods, professional services, or products with human intervention; customers in China, Russia, Iran, Cuba, etc. excluded; requires low dispute rate — [Stripe eligibility](https://docs.stripe.com/payments/managed-payments/eligibility)
- Paddle: 5% + 50c per Checkout transaction, no monthly fees; MoR that collects tax and files returns, handles fraud, chargebacks, buyer support; asks sellers with products under $10 to contact them — [Paddle pricing](https://www.paddle.com/pricing)
- Polar: MoR; Starter 5% + 50c (free); Pro $20/mo 3.8% + 40c; Growth $100/mo 3.6% + 35c; Scale $400/mo 3.4% + 30c; +1.5% international cards; $15 per dispute; payouts via Stripe add 0.25% + $0.25 plus $2/mo; fees apply to the VAT-inclusive total; "Early Member" (orgs created before 2026-05-27) 4% + 40c — [Polar pricing](https://polar.sh/resources/pricing)

### Inferences
- Stripe Managed Payments stacked fee is roughly 2.9% + 3.5% = 6.4% + 30c on domestic cards, before Billing (0.7%); that is a derived sum, not a quoted rate, and above Polar/Paddle headline rates (4-5% + 40-50c). Cross-vendor comparison is only approximate because of international/Billing add-ons.
- A solo founder selling digital SaaS globally avoids VAT/sales-tax registration by using an MoR; using Stripe + Stripe Tax leaves registration and filing with the founder (Stripe Tax calculates, per its pricing page, but filing responsibility was not verified here).
- Managed Payments' Checkout-only constraint means embedded Elements flows would be unavailable.

### Gaps
- Lemon Squeezy: pricing page fetch returned no content; its current status/fees and any Stripe-acquisition-related changes are unverified.
- Stripe Managed Payments general-availability status and rollout date not stated in fetched pages (docs read as live product, but not labelled GA/beta in the text retrieved).
- Stripe Tax filing/registration responsibility, Polar/Paddle payout-country coverage, and tax-registration thresholds not verified.

## Observability, ops, feature flags, cost control, backups

### Takeaway
Sentry's free tier (5K errors, 1 user) covers a solo launch; Team ($26-29/mo) mostly buys users and 50K errors. Vercel provides built-in flags and analytics with small free allowances. Backup coverage is vendor-specific: Supabase Pro daily 7 days; Neon history/snapshots are tiered. PostHog pricing could not be retrieved.

### Cited Findings
- Sentry Developer (free): 1 user, 5k errors, 5M tracing spans, 5 GB logs, 50 session replays, 1 uptime monitor, 30-day lookback. Team: $29/mo monthly or $26 annual, unlimited users, 50k errors, up to 90-day lookback — [Sentry pricing](https://sentry.io/pricing/)
- Vercel Flags: 10K requests/mo free on Hobby, $0.03 per 1K on Pro; Flags SDK supports multiple providers (per skill listing in this environment, not a fetched page) — [Vercel pricing](https://vercel.com/pricing)
- Vercel on-demand budget default $200 with optional auto-pause; AI Gateway budgets can cap team/project/key/user spend — [Vercel pricing](https://vercel.com/pricing); [AI Gateway pricing](https://vercel.com/docs/ai-gateway/pricing)
- Supabase Pro: daily backups retained 7 days; Free: no backups — [Supabase pricing](https://supabase.com/pricing)
- Neon: Launch up to 7-day history window, Scale up to 30 days; instant restore $0.20/GB-mo and scheduled snapshots $0.09/GB-mo on paid plans; Free 6 hours — [Neon pricing](https://neon.com/pricing)

### Inferences
- Sentry free plus platform-native logs/analytics is likely sufficient until real revenue; Pro-only log retention of 1 day on Vercel pushes toward a log drain or Sentry logs sooner than expected (drains are $0.50/GB, Pro-only).
- Independent logical backups (e.g. scheduled pg_dump to object storage) are a sensible cheap addition because provider history windows are short; this is a judgment, not a sourced claim.

### Gaps
- PostHog pricing fetch returned only navigation text; free allowances and unit prices unverified.
- Uptime monitors (Better Stack, UptimeRobot), logging vendors, cloud billing-alert mechanisms not researched.

## AI-feature infrastructure (AI SDK, gateways, evals, cost tracking)

### Takeaway
Vercel AI Gateway charges no markup on tokens (including BYOK) and offers per-team/project/key/user budgets, making it a low-effort cost-control layer. Watch add-on surcharges and the fact that BYOK spend is excluded from gateway budgets.

### Cited Findings
- AI Gateway: no markup and no platform fee on tokens at provider list price, including BYOK; free tier covers a subset of models with lower rate limits; buying credits moves the team to the paid tier and ends the monthly free credit; you pay payment processing fees (doc last updated 2026-09-08) — [AI Gateway pricing](https://vercel.com/docs/ai-gateway/pricing)
- Budgets can cap spend per team, project, API key, or member; BYOK spend is excluded from gateway budgets so provider-side limits are needed too — [AI Gateway pricing](https://vercel.com/docs/ai-gateway/pricing)
- Add-ons: Custom Reporting $0.075 per 1,000 writes and $5 per 1,000 queries; team-wide ZDR $0.10 per 1,000 requests; team-wide provider allowlist $0.10 per 1,000 successful requests; Trace Drains $0.05 per 1,000 traces plus $0.50/GB egress with no Pro allowance — [AI Gateway pricing](https://vercel.com/docs/ai-gateway/pricing)
- Stripe publishes AI-as-a-service tax codes for Managed Payments, so LLM-powered SaaS is an eligible product category — [Stripe eligibility](https://docs.stripe.com/payments/managed-payments/eligibility)

### Inferences
- Gateway plus budgets plus provider-side limits is enough cost control for a solo LLM product; a self-hosted proxy or dedicated eval platform is likely overengineering at this stage.
- Per-user quota enforcement in-app (usage table in Postgres) is probably still needed since gateway budgets are team/key-level aggregates by default; user-level budgets exist per the page but details unverified.

### Gaps
- AI SDK specifics, eval tools (Braintrust, Langfuse, Promptfoo), Helicone/OpenRouter comparison, model prices were not researched or verified.

## Overengineering for a solo founder

### Takeaway
Evidence-backed: most vendors give free or $5-25 entry tiers, so the savings from self-hosting or multi-vendor assembly are small relative to time cost. The items below are judgment calls grounded in the pricing data, not sourced prescriptions.

### Cited Findings
- Auth free tiers are large (Clerk 50K MRU, Supabase 50K MAU, Neon 60K MAU) — [Clerk](https://clerk.com/pricing); [Supabase](https://supabase.com/pricing); [Neon](https://neon.com/pricing)
- Vercel Pro bundles queues, workflows, flags, analytics and a $20 credit, and Cloudflare Paid is $5/mo with no egress — [Vercel](https://vercel.com/pricing); [Cloudflare](https://developers.cloudflare.com/workers/platform/pricing/)
- MoRs remove tax registration entirely for digital goods; Stripe Managed Payments covers 80+ countries — [Stripe docs](https://docs.stripe.com/payments/managed-payments)

### Inferences
- Likely overkill: Kubernetes or multi-region Fly clusters, self-hosted auth/analytics/Sentry, microservices (Vercel even sells microfrontends at $250/extra project), a separate queue/workflow vendor before a real background-job need, running own tax registration before meaningful volume, custom LLM router/eval pipeline before product-market fit.
- Likely right-sized: one host (Vercel or Cloudflare), one managed Postgres, bundled or free-tier auth, a MoR (Polar/Paddle/Stripe Managed Payments), Sentry free, hard budgets/alerts on host and LLM spend.

### Gaps
- No primary sources on solo-founder practice (postmortems, surveys) were gathered; this section is inference from pricing only.
