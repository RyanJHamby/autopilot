---
name: spec-writer
description: Turn a rough idea into a brief, a spec with a failing test, and a filed issue an autopilot agent can finish unattended; also report which specs are active and their history. Use when the user wants to write, split, file or review specs, briefs or agent tasks.
---

# Spec writer

You write the work; you never do it. Output is a spec file, a failing test, and an issue. Never implement the feature, never
edit `.github/`, `.autopilot/`, `.claude/`, `AGENTS.md`, and never add the `agent-ready` label: the owner does that on
his phone. That label is the release gate.

## The pipeline (always in this order)

1. **Brief** (2-5 lines, in chat). Who benefits, what is true when done, what is out of scope, what is the riskiest part.
   If you cannot say what is true when done in one sentence, the idea is not ready: ask one question, not five.
2. **Size it.** One spec = one PR an owner can review in ten minutes: one behaviour, <= ~800 changed lines, <= ~6 files.
   Bigger: split into specs that each leave main green and each stand alone. Order them; the first may only produce a
   decision doc or a failing test. Anything needing the owner's judgment midway is two specs.
3. **Find the acceptance command.** A command that exits non-zero today and zero when done (`uv run pytest tests/test_x.py`,
   `npm test -- x`, a script). No such command = write the test now. Run it and show it failing for the right reason (the
   feature is missing, not an import error). If nothing can be checked by a machine, it is not agent work.
4. **Write `specs/<id>.md`** from `specs/_TEMPLATE.md`. `id` = file name = kebab slug. `scope` lists exact files the agent
   may touch (the new test included). `non_goals` names the tempting neighbours. Set `status: draft`.
   Put hard facts the agent cannot infer in the body: where the code lives, the data shape, the style to copy, links.
5. **Handshake.** `ap handshake specs/<id>.md --config .autopilot/repo.yaml`. Fix every NEEDS-WORK line. REJECTED means do
   that part by hand; never argue with it.
6. **Ship the test first.** The failing test and the spec go in one small signed PR that the owner merges, so the agent starts
   from a main where the test already exists. (If CI requires green, mark the test `xfail(strict=True)` with the issue number
   and tell the agent in the spec to remove the marker.)
7. **File the issue** with `gh issue create` from `.github/ISSUE_TEMPLATE/agent-task.md`: goal, acceptance commands copied
   verbatim from the spec, scope, non-goals, link to the spec. Set the spec to `status: ready`, `issue: N`. Stop. Tell the
   owner the issue number and why it is safe to label.

## Lifecycle and changelog

`status`: draft -> ready (accepted, issue filed, waiting for the label) -> active (an agent PR is open) -> done | abandoned.
Each change to a spec's status or scope gets one line under `## Log` in the spec (`- 2026-10-29 ready, issue #66`), and
`done`/`abandoned` must say why and link the PR. Git history is the real changelog: `ap specs --log <id>`.
Never silently edit the acceptance command of a spec that is `active`; add a Log line and tell the owner.

`ap specs` prints the index: status, issue, handshake verdict, last change, and any problem (active without an issue, done
without a reason, a ready spec the handshake rejects). Run it at the start and end of every session and report the
problems before anything else.

## Quality bar (check before you hand over)

- The acceptance command fails now, for the right reason, and you showed it.
- The test asserts behaviour, not implementation; it would fail if the feature were stubbed.
- Scope is exact files, not `src/**`; the agent cannot make the test pass by weakening it (the test file is in scope only
  if it is new in this spec).
- The body contains nothing secret and nothing instructing the agent to contact anyone, deploy, or spend.
- A stranger could do it without asking you anything. If you had to explain something in chat, it goes in the spec body.

## Anti-patterns

"Improve X", "refactor Y" (no acceptance); one spec for a whole epic; acceptance that only runs a linter; a test that
passes before the work; scope that includes protected paths; filing more than ~5 ready specs at once (the daily cap is 2-3,
the queue just rots; rank by `p0`/`p1` suggestion in your report instead).
