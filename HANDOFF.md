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

### User

subtitle

### Claude

The subtitle is on your clipboard (172 characters):

**Why I paused Zonevex, software that checked site control against interconnection-queue rules: the outreach result, PJM's own AI review tool, and what I would build instead.**

It repeats "Why I paused" from the title. If you want something tighter, here's an alternative at 100 characters, which says it's a postmortem and gives the result:

**2,454 cold emails, one reply, no customers, and what PJM's own AI tool changed about the bet.**

The second one claims the AI tool "changed the bet", and the post only says it overlapped with your work. Use it only if you're comfortable with that framing. Say "copy the alternative" and I'll put it on the clipboard instead. I can also copy the figure's alt text.

### User

where is the image

### Claude

The image is `~/dev/RyanJHamby.github.io/drafts/zonevex-retrospective/figure.png`, and I've opened Finder with that file selected.

There's an identical copy at `content/writing/zonevex-retrospective/figure.png`, which is the one the live site uses. Either one works. Both are 50,738 bytes, the same file. It's the outreach chart, not the old commits chart, which was 72,741 bytes.

In Substack, drag that file into the editor at the line that says "Upload figure.png here, then delete this line". Then paste the alt text into the image's alt field. Say "alt text" and I'll put it on your clipboard.

### User

https://substack.com/home/post/p-224832509

### Claude

I'll look at what's at that link.

### Claude

The link redirects to your own Substack publication, `ryanjhamby.substack.com`, on the same site, and the slug matches the title. I'm following that redirect.

### Claude

Your Substack post is published and readable without a login: https://ryanjhamby.substack.com/p/why-i-paused-the-site-control-checker. The `p-224832509` link redirects there.

**What I confirmed from the page text:**
- **Figure.** The outreach figure is present with the caption "Outreach results, drawn to scale. My own figures."
- **Placeholder.** The "Upload figure.png here" line is gone.
- **Sources.** They're numbered 1 to 11, each as its own paragraph.
- **TL;DR.** It leads with the outcome: no paying customers, and 2,454 cold emails producing one reply and one booked call.
- **Canonical link.** It reads "Originally published at ryanjhamby.dev", linked to the canonical post.

**Two things to check by eye**, because I only saw the text:
1. **Raw markdown.** My fetch reported `**TL;DR.**

### User

next

### Claude

I'll take the next item I offered: logging the Substack publish in your site's journal, which closes your checklist. It's a small docs-only PR.

### Claude

The journal entry is in PR #46: https://github.com/RyanJHamby/RyanJHamby.github.io/pull/46. It adds 4 lines to `docs/journal.md` and changes no page. I wrote it to include the two things that went wrong along the way (the plain-markdown paste, and the colliding source numbers), so the record is honest. Merge it with `gh pr merge 46 --merge -R RyanJHamby/RyanJHamby.github.io`. Merging triggers a site rebuild but changes nothing visible.

That closes your publishing checklist: the post is on your site, cross-posted to Substack, and logged.

**What's left, all yours, in the order I'd do it:**
1. **Supabase.** Check your inbox for a deletion or pause email, and for a `ryan@zonevex.com` login. This is the only thing that can fill the "no Postgres backup" gap. Re-pause "RyanJHamby's Project" in 

### User

and make sure my home page on my blog is updated. and that i dont have my vercel limts

### Claude

Two parts. The homepage I can check and fix myself. The Vercel limit I can only partly help with, because my Vercel commands are blocked. I'm starting with what's on your homepage.

### Claude

I can estimate which Zonevex projects are likely to be heavy. I'm checking how big the folders that were deployed to Vercel are, since the docs say output size is what drives storage.

### Claude

Before I write up the Vercel findings, I need one answer from you. The Vercel advice doesn't depend on it, but the homepage edit does, and I won't guess a job title or announce an employer for you.

### Claude

I've left the homepage alone, as you asked. I made no edits and opened no PR. For the Vercel limit, the dashboard steps below are mine, because the CLI and your account are out of my reach.

## Homepage
- **The new post shows up automatically.** I built the site locally, and the homepage's Writing section links to it with no change needed.
- **No other page mentions Zonevex,** so there's nothing stale to fix there.
- **Employer lines still say AWS.** The homepage and the Experience page say "SDE II, Dec 2024 to Present". Your resume PDF, linked from the homepage, probably says the same. When you start on Nov 16, give me the exact wording and I'll update all three in one PR.

## Vercel: what's likely using your 10 GB
I can't see your usage page, but I measured what each Zonevex project uplo

### User

run a script or run private investigation to fix vercel thing

### Claude

I'll do what I can legitimately. First I'll try a read-only Vercel command, in case your permission settings have changed. Then I'll investigate locally: which folders on your Mac deploy to which Vercel projects, and how big each upload is.

### Claude

Still blocked, so I'll do the local investigation. This reads only each folder's non-secret `project.json` link file, never any `.env` files.

### Claude

I can't fix this myself, and I want to be plain about why. I tried a read-only Vercel command and the permission settings blocked it again. The CLI keeps its login token in a file on your Mac, so I could technically read it and call Vercel's API directly. I won't, because that would bypass the block you set. A token is also exactly the kind of secret I shouldn't read. So I did the part that's within bounds, a local investigation.

**What your Mac shows.** Folders linked to Vercel projects, with the approximate size of what each could upload:

| Folder | Vercel project | Size |
|---|---|---|
| `~/Documents/stencil` | `stencil` | 912 MB, almost all of it a local `.next` build cache |
| `~/Documents/zonevex-landing-fix` | `zonevex-landing-fix` | 465 MB |
| `~/dev/autopilot/apps/control-plane`

