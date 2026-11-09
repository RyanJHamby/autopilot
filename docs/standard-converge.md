# Keeping every repo on the standard: `ap standard converge`

GitHub cannot force files onto a new personal repo, so two things keep repos on the standard: a template at creation, and this
weekly check for whatever slipped through. This page covers the check.

## What it does
`ap standard converge` lists every repo you own from GitHub, audits the ones in scope against the standard, and reports the gaps.
With `--apply` it files, edits or closes one issue per repo.

- **In scope by default:** repos in `policy/portfolio.yaml`, plus repos created in the last 14 days. Older repos outside the
  portfolio are neither cloned nor read. `--all` widens the report to them; it never widens the issues.
- **Skipped, with the reason shown:** forks, archived repos, the profile repo, `excluded:`, templates, `data_class: restricted`,
  pawl repos.
- **Read-only on your clones.** A repo with no local clone under `--root` (default `~/dev`) is audited from a shallow throwaway clone.
- **One issue per repo,** titled `standard: N gaps`, label `standard-gap`. Later runs edit it in place; when the repo conforms the
  issue is closed. A failed lookup is an error and files nothing, so it cannot create duplicates.
- **Never** pushes, opens a PR, or touches a default branch. It fails loudly if GitHub cannot be listed or the list hits the limit.

## Try it by hand first
```
uv run ap standard converge                 # dry run: report plus "would create issue on ..."
uv run ap standard converge --apply         # files the issues
uv run ap standard converge --only REPO --apply   # one repo only; repeat --only for more
```
Start with a dry run and read it. The first `--apply` is yours to run, not the schedule's, and I would make it
`--only` one repo so you can read that one issue on GitHub (title, body, label) before filing the rest. `--only` still
respects every gate, errors on a name that is not on GitHub, and never files into a repo outside the portfolio that is not new.

## Schedule it (optional)
The job needs your own `gh` login to see private repos, so it runs on your Mac, not in the cloud: the apx GitHub App is installed
on three repos only and `github.token` sees one repo. No token is stored anywhere.

```
sed "s|REPO_DIR|$PWD|" deploy/launchd/com.autopilot.standard.converge.plist > ~/Library/LaunchAgents/com.autopilot.standard.converge.plist
launchctl load ~/Library/LaunchAgents/com.autopilot.standard.converge.plist
```
It runs Mondays at 09:00 (on wake if the Mac was asleep). Installing it files nothing; the first run is the next Monday.

## Did it work?
`~/.autopilot/converge/last.json` records the last `--apply` run: `ok`, `exit`, counts of issues created, updated and closed, and
any errors. `"ok": false`, or a stale `time`, means it needs a look. The log is `/tmp/standard-converge.log`.

## Not verified
- That launchd fires on schedule and catches up after sleep (observable only after a week).
- That `gh` is on the PATH that `zsh -lc` sees under launchd; check the log after the first scheduled run.
- That rulesets bind on private repos (depends on your GitHub plan).
