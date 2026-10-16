# GitHub App "autopilot-control" (not registered yet)

Registered by the owner, once, via GitHub's app-manifest flow (a browser click; nothing here registers anything).

Permissions and why:
- `actions_variables: write`: push tightening/neutral levers (priority, hold, pause) as repo variables.
- `issues`, `pull_requests: write`: label `agent-ready`, open the PR that a guardrail loosening requires.
- `contents: read`: read `.autopilot/*.yaml` for display. **No contents write**: the app cannot push code.
- `checks`, `actions: read`, `workflow_run` events: build the run ledger.

Deliberately absent: `workflows`, `administration`, `secrets`, `members`. It can never edit CI, rulesets, secrets or access.
Private key custody: deployment encrypted env only; never in a repo. Install per owner (personal account, `ampentra`),
selecting repos explicitly rather than "all repositories". `public: false` keeps it installable only by its owner.
Replace the placeholder URLs after the first deploy.
