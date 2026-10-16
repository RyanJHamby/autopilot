# control-plane (P3, read-only scaffold)

Next.js PWA that shows the portfolio: status, priority and pool share per repo. Reads `data/state.json`, written by
`ap export-state` from `policy/portfolio.yaml`. No writes, no auth, no network calls yet.

**Do not deploy this as is.** The snapshot names private repos and there is no sign-in. Before any deployment: GitHub
OAuth restricted to the owner, Supabase RLS, and the snapshot moved from a file to the database (see the v2 plan).

    npm install && npm test && npm run dev
