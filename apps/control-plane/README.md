# control-plane (read-only scaffold with owner sign-in)

Next.js PWA: portfolio view (status, priority, pool share), lever planning (`lib/levers.ts`), PR inbox triage
(`lib/inbox.ts`), run-ledger webhook (`app/api/github/webhook`), Supabase schema with RLS (`supabase/migrations`).

Sign-in is GitHub OAuth restricted to numeric user ids in `ALLOWED_GITHUB_IDS`; sessions are HMAC-signed cookies;
`proxy.ts` denies by default and every page re-checks. Unconfigured means closed (503/401), never open.

Env: `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `SESSION_SECRET` (>=32 chars), `ALLOWED_GITHUB_IDS`,
`GITHUB_WEBHOOK_SECRET`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`.

**Still not deployable:** `data/state.json` names private repos and is bundled with the build; move it into the
database first. Nothing here is registered or deployed.

    npm install && npm test && npm run dev
