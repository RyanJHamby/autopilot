# Gates: what a bet clears before real users and before the first payment

A **gate** is a checklist for a bet, kept as data in `src/autopilot/gates/gates.yaml`. There are three:

- `beta`: real users' data is about to arrive.
- `charge`: ready to take the first payment.
- `scale`: real growth is coming (more users, more money, more at stake if a vendor or a secret fails).

They cover what the capability packs (`STANDARD.md`, "Capability packs") cannot see from code: whether the entity exists, whether the
processor account is in the business's name, whether sales tax was decided. The packs stop the code from shipping without its controls;
the gates keep the rest of the business from being forgotten.

This is a checklist, not legal or tax advice. The legal and tax steps say to confirm with a professional, and a test enforces that.

## The two commands

```
ap gate show BET GATE            # where the bet stands; read-only; exit 0 only when every item is done
ap gate seed BET GATE            # dry run: prints the exact pawl commands, writes nothing
ap gate seed BET GATE --apply    # adds the gate's manual steps to the control repo as draft pawl steps
```

`show` accepts `--json`, `--path CLONE` (the bet's repo, if it is not under `--root`) and `--root` (repeatable; default `~/dev` and
`~/Documents`). Both commands take `--control PATH`; without it they use `$PAWL_ROOT`, then `~/dev/control`.

**Seeding is deliberately cautious.** Every pawl write to a control repo with `[sync]` on commits *and pushes to main*, one push per
step. So `seed` is a dry run unless you pass `--apply`, and it runs pawl with `--no-push`: one signed local commit per step, pushed later by
`pawl sync` or your scheduled tick. `--push` opts in to pawl's normal push-per-write. It passes an explicit id (`g-GATE-ITEM`) to every step,
so running it twice adds nothing and a half-finished run resumes. It never edits, resets or deletes a step. If pawl fails part way it stops
and prints exactly what was written.

## How each item is known

`ap gate show` says, next to every item, how it is known, because a tick is not proof.

| Kind | Checked against | What it can and cannot tell you |
|---|---|---|
| `repo-standard` | the bet's repo, held to the **current** standard as if it were new (the check `ap enable` uses), offline | Real: it is checked against the code. Unknown if the bet names no repo or there is no clone. |
| `bet-field` | the bet's own `bet.toml` | Real, but only that the field is filled in, not that what it says is true. A number of zero counts as not set. |
| `bet-artifact` | another bet's artifacts in pawl (for example `llc`: `filing` and `ein` delivered) | As good as the delivery ref recorded in pawl, which is self-attested. |
| `step` | the draft step in pawl | **Self-attested.** Done when someone marks it done; a dropped step counts as not owed. Not in pawl yet shows as "not seeded". |

An item that cannot be answered (no clone, pawl missing, a bet that does not exist) is `unknown` and is never counted as done.

## Reading and adopting it

- Seed a gate only when a bet nears the stage it guards. Nothing here seeds a real bet for you.
- `ap gate show` is cheap and read-only, so run it whenever; it never writes (a test hashes the whole control tree before and after).
- A bet with no `repo` in its `bet.toml` can still be checked for everything else.

## Optional, owner-only: making pawl refuse to advance (not built, not tested)

pawl's guards are data and immutable, and a new evidence kind needs a hand edit of `pawl.toml`, which the control repo's `AGENTS.md`
forbids for agents. So this is left as commands for you to run by hand if you want it, and it is **bookkeeping, not enforcement**: an
evidence ref is free text, so a person can log anything.

```
# 1. in the control repo's pawl.toml, under [evidence], add:   gate-check = 1
# 2. add a guard at the stage you choose (guards cannot be edited later, only retired):
pawl learn charge-gate-shown --enter scale --evidence gate-check --min 1 \
  --why "A payment was taken without the first-payment checklist being read." \
  --fix "Run ap gate show BET charge, then log the result with pawl log BET gate-check REF."
# 3. when `ap gate show BET charge` says Ready:
pawl log BET gate-check "REPO@SHA ap gate show charge: ready"
```

## Not verified

- A real `ap gate seed --apply` against your actual control repo and its remote. The push behaviour is proven with a local bare repository
  and the real pawl, not with GitHub.
- The optional guard wiring above.
