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
- **It audits GitHub, not your disk.** Every repo is audited from a fresh shallow clone of its default branch, in a throwaway directory. Your local clones are never read or written, so a stale one cannot give stale gaps or close an issue wrongly. `--root` is accepted and ignored. A repo's age (which decides whether a dated rule binds it at full strength) comes from GitHub's created date, because a shallow clone has no history to read.
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

Install it from a **dedicated clean clone that nothing else touches**, not from the checkout you work in. Your working checkout is on
a feature branch or has uncommitted changes most of the time, and the job refuses to run from such a checkout (see below), so it
would silently never run:

```
git clone https://github.com/RyanJHamby/autopilot.git ~/.autopilot/converge-checkout
(cd ~/.autopilot/converge-checkout && uv sync --quiet)
sed "s|REPO_DIR|$HOME/.autopilot/converge-checkout|" ~/.autopilot/converge-checkout/deploy/launchd/com.autopilot.standard.converge.plist > ~/Library/LaunchAgents/com.autopilot.standard.converge.plist
launchctl load ~/Library/LaunchAgents/com.autopilot.standard.converge.plist
```
It runs Mondays at 19:00 local time (on wake if the Mac was asleep). Installing it files nothing; the first run is the next Monday.

**Work-hours freeze.** `--apply` edits issues on personal repos, so it never runs Mon-Fri 08:30-18:30 ET (`policy/time.yaml`, read
through `autopilot.freeze`). The 19:00 schedule is outside that window, and `tests/test_converge_freeze.py` checks the plist against the
policy so the two cannot drift. A Mac that was asleep wakes into a missed run, possibly inside the window: `--apply` then refuses
before reading anything (fail closed on any resolver or clock error, no override), exits 0, and writes `last.json` with a `skipped`
reason, so the work waits for the next Monday. A dry run (no `--apply`) only reads and is not held.

The job runs whatever code `REPO_DIR` has checked out, so it guards itself: it runs only if that checkout is on `main` with no
uncommitted changes to tracked files (untracked files are ignored), and it pulls `main` first. Otherwise it prints why to the log
and exits without running, so `last.json` goes stale. A dedicated clone that you only ever pull never trips that guard. To see
that it ran, check `~/.autopilot/converge/last.json` (`ok`, and its timestamp) after the first Monday: a stale file means it did not.

## Did it work?
`~/.autopilot/converge/last.json` records the last `--apply` run: `ok`, `exit`, counts of issues created, updated and closed, and
any errors. `"ok": false`, or a stale `time`, means it needs a look. The log is `/tmp/standard-converge.log`.

## Not verified
- That launchd fires on schedule and catches up after sleep (observable only after a week).
- That `gh` and `git` are found under launchd. The first manual start (`launchctl start`) failed with exit 127, `uv: command not found`: launchd's login shell skips `.zshrc`, so `~/.local/bin` was missing. The plist now sets `PATH` itself (`~/.local/bin`, `/opt/homebrew/bin`, `/usr/local/bin`); re-run `launchctl start` and check the log.
- That rulesets bind on private repos (depends on your GitHub plan).
