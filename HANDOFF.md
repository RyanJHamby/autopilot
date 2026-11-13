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

The DNS is simple, and your answer helps. Here's what's live for `zonevex.com`, read from public DNS on 2026-11-13.

| Record | Value | Meaning |
|---|---|---|
| Nameservers | `ruth` and `alan.ns.cloudflare.com` | **DNS is at Cloudflare** |
| MX | the 5 standard Google hosts (`aspmx.l.google.com` and `alt1` to `alt4`) | mail goes to Google today |
| SPF (TXT) | `v=spf1 include:_spf.google.com ~all` | Google only |
| TXT | 3 × `google-site-verification=…` | Search Console or Workspace verification |
| DMARC, Google DKIM | none found | no DMARC; Google DKIM not enabled, or on another selector |
| Apex, `www`, `app` | point at Vercel | the paused page and the web app |
| `api` | no record | |

I found no Resend or other mail-sender records. I checked six common selectors, which isn't exhausti

### User

go

### Claude

I'm doing that now. I'll record the snapshot without the verification token values, mark the registrar as still unknown (nameservers only tell me who hosts DNS), and update the two table rows.

### Claude

PR #750 is open: https://github.com/RyanJHamby/gis-analysis-checker/pull/750. It adds a DNS snapshot as section 10 of `REVIVAL.md`. I read it from public DNS and changed nothing. It also updates the Domain and Google Workspace table rows, so two of your `TODO (Ryan)` items are closed.

Merge it with `gh pr merge 750 --merge -R RyanJHamby/gis-analysis-checker`.

**Still unknown:** the domain registrar. Nameservers only show who hosts DNS (Cloudflare). Check Cloudflare under Domain Registration, or your registrar emails, and tell me if you want it recorded.

**Open items, all yours:**
1. **Email route.** Forwarding through Cloudflare Email Routing, a paid Zoho plan plus the script, or Zoho's own migration tool. Before cancelling Workspace, run a full Google export. Your notes suggest a Sheet

### User

[Request interrupted by user]

### User

gh pr merge 750 --merge -R RyanJHamby/gis-analysis-checker

### Claude

The first attempt had a trailing period after the repo name, so GitHub couldn't resolve it. The second one is the correct command. I'm checking whether it went through.

### Claude

PR #750 is not merged yet. The corrected command hasn't run, or hasn't finished. `main` is still at `949307e`. The only command that ran was the first one, with the trailing period, and it failed.

Run this exact line, with no period at the end:

```
gh pr merge 750 --merge -R RyanJHamby/gis-analysis-checker
```

Then tell me, and I'll confirm that `main` has it.

### Claude

That one still has the trailing period after `gis-analysis-checker`, so GitHub looked for a repo with a period in its name. It may be coming from the way the line is being copied.

Skip the `-R` flag and run it from the repo directory:

```
cd ~/dev/zonevex
gh pr merge 750 --merge
```

`gh` finds the repo from that folder, so there's no name to mistype. Tell me when it's done and I'll confirm with git.

### Claude

PR #750 is merged. `origin/main` is at `b4d5b1d`, which includes the DNS snapshot commit `1494e4c`, signed. `REVIVAL.md` now records that DNS is hosted at Cloudflare and lists the live records.

**Still open, all yours:**
1. **Email route.** Forwarding through Cloudflare Email Routing, a paid Zoho plan plus the script, or Zoho's own migration tool. Run a full Google export before cancelling Workspace.
2. **Zoho setup.** Add `zonevex.com` in Zoho's console and paste me the MX, SPF and DKIM values it shows. I'll then script the Cloudflare cutover as a dry run, using a scoped token you create.
3. **Supabase.** Check for a deletion or pause email, and for a `ryan@zonevex.com` login.
4. **Cal.com.** Disable the `demo` event type.
5. **Registrar.** Check Cloudflare or your registrar emails if yo

### User

zoho migration

### Claude

I couldn't load Zoho's migration guide earlier. I'm trying several likely addresses, so the steps come from Zoho's own page and not from memory.

### Claude

Zoho's own migration tool is the right route here, and it makes my script unnecessary for this mailbox. These facts come from Zoho's migration pages, read just now.

**Why one-click, not the script**
- Zoho says the one-click migration tool is **free and included on all plans**, so the Free plan works. My script needs IMAP on the Zoho side, which new Free accounts don't have.
- You authorize Zoho to read your Google account once, by signing in as the Workspace admin. There's no password file or token to handle.
- It moves mail with folders and read/unread state, plus contacts and calendars.

**What it does not move.** The page lists these, so recreate them by hand:
- filters and rules
- vacation responders
- signatures
- tasks and notes
- third-party add-ons
- Gmail labels that have no Zoh

### User

[Image #4]

### User

[Image: source: /var/folders/n7/6rffgrz57nz8jmz85gl_0rwh0000gn/T/TemporaryItems/NSIRD_screencaptureui_7xInXz/Screenshot 2026-11-13 at 3.33.34 PM.png]

### Claude

This is useful, and it changes the first step. What I can see in the screenshot:

- **You already have a Zoho Mail account.** The "Welcome to Zoho Mail" message is dated Dec 1, 2025. MFA was turned on Jan 24, a test email arrived from your Gmail that day, and there's a "New sign-in to your Zoho account" from today at 3:22 PM (I'm assuming that was you just now).
- **I can't tell what address it is.** The screenshot doesn't show the mailbox name. It could be a personal `@zohomail.com` address, or it could already be a `zonevex.com` organization.
- **It's not migrated.** The inbox holds only Zoho system mail, a few promotions and your test. There's no Zonevex mail in it yet.

**What I need you to check, two quick things:**
1. **The address.** Click the "RH" avatar at the top right. What addr

### User

api calls and script

### Claude

I'll check both APIs' current docs before writing anything. I'm reading Zoho's Mail Admin API for domains and Cloudflare's DNS API.

### Claude

I have the OAuth flow now. Next I'm reading the three domain pages Zoho linked, for the exact requests: add domain, verify domain, and enable hosting.

### Claude

That diff is my own edit. One line near the top of the README is now wrong, because it says the folder never changes DNS and the Cloudflare script does. I'm fixing it.

