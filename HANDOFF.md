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

I'll check where things stand before saying anything: whether the Railway repo is disconnected and whether #753 is merged.

### Claude

Neither step is done yet, so "go" hasn't changed anything I can see.

- **Railway:** both services, `api` and `harvest-ferc-worker`, are still connected to `RyanJHamby/gis-analysis-checker`. The worker is linked too, so it may build on pushes as well.
- **PR #753:** not merged. `main` is still at `69251fd`.

**Do these in order:**
1. In Railway, open project `striking-generosity`. For **each** of the two services, go to Settings, then Source, and disconnect the repo. You can reconnect later, and it deletes nothing.
2. Tell me when it's done. I'll check that both services show no source before you merge anything else.
3. Then merge #753 with `gh pr merge 753 --merge -R RyanJHamby/gis-analysis-checker`. Without the disconnect, it would send you a ninth failed-build email.

I'm leaving the Ra

### User

just run scripts

### Claude

"Run scripts" could mean several things, and the ones I've written need credentials I haven't seen. I'll check whether you've set up the config they read, without opening any file's contents.

### User

[Request interrupted by user]

### User

actually done with disconnects

### Claude

Thanks. I'm verifying the disconnects on Railway's side first.

### Claude

Railway still reports both services as connected to `RyanJHamby/gis-analysis-checker`, so I can't confirm the disconnect. Either it didn't take, or the CLI's view lags behind.

Please check in the Railway dashboard. For each of `api` and `harvest-ferc-worker`, open Settings, then Source. A disconnected service shows a **Connect Repo** button and no repo name. If it still shows the repo, the disconnect didn't save: click Disconnect, confirm any prompt, and reload the page to check.

Tell me when both show "Connect Repo", and I'll re-run the check. If it then reports no source, merge #753 safely. If the CLI still disagrees with a dashboard that clearly shows disconnected, I'll trust the dashboard and say so.

About "just run scripts": nothing I wrote can run yet, because the Zoho and Cloudfl

### User

[Image #6] done

### User

[Image: source: /var/folders/n7/6rffgrz57nz8jmz85gl_0rwh0000gn/T/TemporaryItems/NSIRD_screencaptureui_ns8n6z/Screenshot 2026-11-13 at 5.21.28 PM.png]

### Claude

This explains it, and it's not quite done yet. The screenshot shows Railway's **staged changes** bar: "Apply 4 changes" with a **Deploy** button, and both services marked "Edited" with "2 Changes". The disconnect is staged, not applied. That's why the CLI still shows the repo.

**What to do:**
1. Click **Details** first. It lists the 4 changes. Check that they're only the repo disconnects (two per service), and nothing like a redeploy or a variable change.
2. If they are, apply them. The **Deploy** button applies the changes and may also redeploy the services. With no repo connected there should be nothing to build, but I'm not certain what Railway does with the existing June deployment. Look in the **⋮** menu next to Deploy for an option to apply without deploying. I haven't verified that

### User

deployed

### Claude

The disconnect is applied. Both services now show **no repo source**, and applying the changes didn't trigger a new build. The latest deployments are still the earlier failed ones, so nothing new started. The worker was also failing on every push (the same failed builds, at the same times), so you were likely getting a second email per merge.

You can merge #753 now without another failure email:

```
gh pr merge 753 --merge -R RyanJHamby/gis-analysis-checker
```

Tell me when it's done and I'll confirm with git.

**Still open, all yours:**
1. **Railway running cost.** The June deployment may still be running with a public address and no database. Look at the `api` service's deployments, and stop or remove the active one if you want it off. I haven't touched it.
2. **Blog post.** The draft

### Claude

PR #753 is merged. `origin/main` is at `6530598`, which includes the signed commit `ae83e7a`. `REVIVAL.md` now records the failed Railway builds, and the decision record carries your 2,454 figure.

**The Railway fix worked.** The newest `api` deployment is still the earlier failed one from 22:03, so this merge started no new build. You shouldn't get another "Build failed" email.

**What's left, all yours:**
1. **Railway running cost.** The June deployment of `api` may still be running with a public address and no database. Check the service's deployments, and stop or remove it if you want it off.
2. **Blog post.** The draft is local only (`315bbc9`), because the site repo is public. Before publishing:
   - check the 2,454 count and the one reply against your email tool
   - check the Cal.c

### User

i dont want charges for railway anymore. make the blog post, put it on my dev website first

### Claude

Two things, and the Railway one costs money, so I'm doing it first. First I'm identifying exactly what's running, since removing it stops the service.

### Claude

`sed -i` needs a different form on macOS, so that step didn't run. I'm redoing it in Python.

### Claude

Now the draft: a sanitized NOTES block (nothing about private notes or internal decisions), front matter with a description, the footer pointing at the new runs, and a changelog.

### Claude

My greps probably missed because the HTML is minified, with unquoted attributes. I'm looking at the real output.

### Claude

The rendered page is 1 byte, so it's empty. That could be a problem with my page or with the site build itself. I'm comparing it to the existing FlowState page and checking the theme.

