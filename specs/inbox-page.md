---
id: inbox-page
goal: "The control-plane has an Inbox page listing the owner's open agent PRs ordered by lib/inbox.ts, using a repo-scoped read-only fetch through the GitHub App installation token."
acceptance:
  - npm --prefix apps/control-plane test
  - npm --prefix apps/control-plane run typecheck
scope:
  - apps/control-plane/app/inbox/**
  - apps/control-plane/lib/inbox.ts
  - apps/control-plane/lib/inbox.test.ts
non_goals:
  - no write actions (approve/merge stay in GitHub)
  - no changes to proxy.ts, lib/auth.ts, lib/githubApp.ts or anything under supabase/
risk_tier: 2
max_runs: 3
autonomy: inherit
---
Session check on the page (see app/page.tsx). Token permissions: pull_requests read only. Unit-test the mapping from the GitHub PR JSON to PrItem.
