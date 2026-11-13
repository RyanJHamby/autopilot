# Handoff: autopilot

- Branch: `docs/fix-upgrade-wording` (continue from `wip/docs/fix-upgrade-wording`; base commit `f690c46`)
- Instructions: read this file, continue the work, commit in small steps, push a new branch and open a PR. Never push to `main`.
- Generated from the local session transcript without a model call; it may be incomplete.

## Goal (first prompt of the session)



<pasted_content id="4dba">
We're mothballing Zonevex (pausing, not killing). Goal: full revivability.
Deadline: everything committed before Nov 16 (I start at Hume).
Follow my proof-of-work conventions: small signed commits, a `pow log`
entry for the decision, accurate README AI disclosure. NOTHING destructive:
don't delete services, buckets, data or DNS, and don't cancel anything.
I'll do that separately after the backups are verified.

1. Decision record
   - Write docs/DECISION-2026-11-sunset.md covering: what Zonevex did, what I
     found (well-funded competitors/incumbents; HyperQ covering both the
     developer and RTO sides), the pivots I considered and why I passed
     (unclear distribution, unclear ROI), and revisit triggers (a buyer need
     incumbents won't serve, inbound with a budget or pilot, an interconnection
     rule change that opens a wedge, a distribution channel I can reach).
     Ask me for anything you can't infer from the repo.
   - Add a matching `pow log` entry.

2. Backups (store OUTSIDE the repo at ~/Archive/zonevex/<date>/; never commit
   dumps or secrets)
   - Railway: use the railway CLI to `pg_dump -Fc` every Postgres DB. Also
     back up any other datastores you find (Redis, volumes).
   - Verify each dump: restore it into a throwaway local Postgres (docker) and
     compare table row counts against prod. Report the results.
   - R2: rclone sync every bucket; verify object counts and total bytes match.
   - Env vars: list the variable NAMES per service/environment in
     docs/REVIVAL.md. Don't print or write the values; I'll copy them into my
     password manager myself.
   - Encrypt the archive folder (age or gpg; ask me which key) and checksum it.

3. Revival memo: docs/REVIVAL.md
   - Architecture overview; every external service (Railway, R2, Loops,
     domain/DNS, Google Workspace, G2/Capterra, anything else in the code or
     config) and what each one is used for
   - Exact steps to redeploy from scratch, plus where the backups live
   - A dated snapshot of the competitor landscape (link the decision doc)

4. Static "paused" site

## Diff summary (`git diff --stat`, base to wip, HANDOFF.md excluded)

```
 apps/control-plane/app/globals.css                 |  16 +-
 docs/journal.md                                    |   4 +
 docs/permissions-log.md                            |   9 ++
 key.pub                                            |   1 +
 kit/repo/AGENTS.block.md                           |   2 +-
 policy/portfolio.yaml                              |   2 +-
 reports/Founder tech operating systems gaps.md     | 149 +++++++++++++++++++
 reports/Solo founder throughput stack 2026.md      |  80 ++++++++++
 .../agentic_workflow_portability.md                | 140 ++++++++++++++++++
 .../enforcement_and_enrollment.md                  | 164 +++++++++++++++++++++
 .../knowledge_and_decisions.md                     | 119 +++++++++++++++
 .../legal_and_ip.md                                | 126 ++++++++++++++++
 .../marketing_and_sales.md                         | 115 +++++++++++++++
 .../model_and_token_efficiency.md                  | 147 ++++++++++++++++++
 .../tool_and_stack_selection.md                    | 103 +++++++++++++
 .../agentic_dev_workflows.md                       | 133 +++++++++++++++++
 .../cadence_and_pitfalls.md                        | 124 ++++++++++++++++
 .../local_tooling.md                               | 101 +++++++++++++
 .../solo_saas_infra.md                             | 130 ++++++++++++++++
 .../validation_distribution_revenue.md             |  80 ++++++++++
 scratch-check                                      |   1 +
 spec-writer                                        |   1 +
 22 files changed, 1737 insertions(+), 10 deletions(-)
```

## Last 20 exchanges

### Claude

I'll check both APIs' current docs before writing anything. I'm reading Zoho's Mail Admin API for domains and Cloudflare's DNS API.

### Claude

I have the OAuth flow now. Next I'm reading the three domain pages Zoho linked, for the exact requests: add domain, verify domain, and enable hosting.

### Claude

That diff is my own edit. One line near the top of the README is now wrong, because it says the folder never changes DNS and the Cloudflare script does. I'm fixing it.

### Claude

The README edit applied. Now I'll log it, commit signed, push and open the PR.

### Claude

API Error: Your computer went to sleep mid-response. The response above may be incomplete.

### User

go

### Claude

PR #751 is open: https://github.com/RyanJHamby/gis-analysis-checker/pull/751. It has the two scripts, the env example and the corrected README. Merge it with `gh pr merge 751 --merge -R RyanJHamby/gis-analysis-checker` (type the repo name without a trailing period).

**What's in it**
- **`zoho_api.py`:** `token`, `add-domain`, `verify txt|cname|html`, `enable-hosting` and `show`. The endpoints and modes come from Zoho's API pages, which I read today.
- **`cloudflare_dns.py`:** `list`, `verify-cname` and `cutover`.
- **Cutover behaviour:**
  - It saves every record to a JSON backup first.
  - It adds the three Zoho MX records before removing the five Google ones, so the domain is never left without MX.
  - It replaces only the SPF record, and leaves the `google-site-verification` and Vercel

### User

merge it

### Claude

The merge is still blocked for me by the permission settings. It was denied on #745 and #747, so I'm not trying again. Please run it yourself, and keep the repo name free of any trailing period:

```
gh pr merge 751 --merge -R RyanJHamby/gis-analysis-checker
```

Tell me when it's done and I'll confirm with git that `main` has it. If you'd rather I do the merges from now on, you can allow `gh pr merge` in your Claude Code settings.

### Claude

PR #751 is merged. `origin/main` is at `48174d7`, which includes the Zoho and Cloudflare scripts in `scripts/email-move/` (commit `0a0cd46`, signed).

**Where you are on the email move.** The scripts are in `main`, but nothing has run against Zoho or Cloudflare yet. Your next steps are all in a browser:
1. In Zoho, note your **data center** (the address-bar suffix) and your **organization ID** from the Admin Console.
2. At https://api-console.zoho.com/, create a **Self Client** and generate a one-time grant code with the scope `ZohoMail.organization.domains.ALL`.
3. In Cloudflare, create an API token with DNS write on the `zonevex.com` zone.
4. Put each secret in its own mode-600 file, and copy `zoho-api.env.example` to `~/Archive/zonevex/zoho-api.env`.

Then follow the sequence in `script

### User

lets park this for now. write the blog post

### Claude

I'm parking the email work. Writing the post needs one thing settled first. Your writing rules say the `[HUMAN]` sections come only from your `seed.md`, and that file is still empty. Your own recorded notes hold plenty to work from, though, so I'll build the draft from those and label each source. I'm also reading the two primary sources for the HyperQ claims now, so I can cite them properly.

### Claude

The Tapestry page read cleanly, and it has a newer Nov 10 entry that my notes didn't. The PJM release came back as raw PDF data, but a local copy was saved, so I'll read it directly.

### Claude

That change is my own edit. Now I'm writing the source map: every statement in the draft that came from your recorded notes, with where it came from, so you can confirm or rewrite each one.

### Claude

The draft is written, but you can't publish it yet. It's about 920 words in your dead-end template, and it's committed locally and signed. It's on `draft/zonevex-retrospective` in `~/dev/RyanJHamby.github.io`, and I haven't pushed it because that repo is public.

**What it says.** The title is "Why I paused the site-control checker I built for PJM's interconnection queue".
- The top gives the TL;DR, why it matters, and an "as of" date.
- Then comes what you believed, what you built, and what happened, with the PJM and HyperQ facts.
- Then your own explanation for why it stalled, offered as opinion, and your revisit conditions.
- It ends on an open question: would a developer pay for a second opinion on site control from someone who isn't the RTO's reviewer?

**Sources I actually read today

### User

go

### Claude

"Go" doesn't say which of the open items you mean, and the draft can't move without your input on most of them. One item needs no input from you and is non-destructive: the figure your rules require for every post. I'm building it from captured data, so it's checkable.

### Claude

Now the throwaway virtual environment with `matplotlib`. I'll record whatever version it resolves to and pin it in the script.

### Claude

The script ran and the values match the captured run. I'm checking the image by eye, because the lint can't judge a chart.

### Claude

I built the post's one shareable figure, and in doing so I found and fixed an error in my own draft. The draft isn't publishable yet, and it's committed locally only (`eddc992`, signed).

**The error.** I'd written that you built Zonevex "from February to October". A `pow run` of the repo's commit history says otherwise:

| Month (2026) | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct |
|---|---|---|---|---|---|---|---|---|---|
| Commits | 148 | 199 | 44 | 338 | 100 | 0 | 0 | 0 | 7 |

The build ran February to June. Then came a silent summer and a small October burst. I rewrote the TL;DR and "What I did" to match, and I added a claim in `claims.yaml` whose total checks out at 836. The post is more honest this way, and the summer gap is the question it now has to answer.

**The figure.

