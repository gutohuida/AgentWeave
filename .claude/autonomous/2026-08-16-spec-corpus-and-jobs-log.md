# Run log — 2026-08-16 night: the spec corpus, and loops as a first-class concept

Newest entry at the **bottom**. Written for someone who was asleep.

**Branch:** `autonomous/2026-08-16-spec-corpus-and-jobs`
**Parent:** `hub-native-experience` @ `b2b0cd5` — that is what this run is a diff against.
**Window:** 2026-08-16T21:35 → 2026-08-17T08:00 (+01:00)
**Driver:** Windows Scheduled Task `AgentWeaveAutonomousSession`, firing `claude -p` every 15
minutes. Each firing is a **fresh process** that reads `STATE.json`, does one iteration, commits,
pushes and exits. Nothing is held in memory between iterations — that is what makes it survive the
interactive session ending, which is what killed the 2026-08-15 attempt at forty minutes.

---

## Entry 0 — the limits, before any work

Recorded first so a later session inherits them even if this one dies mid-thought. Full text lives
in `STATE.json`'s `limits`; this is the short form.

1. **Stay on `autonomous/2026-08-16-spec-corpus-and-jobs`.** No commit, merge or rebase onto
   `hub-native-experience` or `master`. Merging back is the operator's decision, made awake.
2. **Nothing outward-facing.** No publish, release, PR, issue, force-push or history rewrite.
   Pushing *this* branch is required, not optional — it is what makes the work durable.
3. **Nothing destructive.** In particular: do not delete `hub/data/agentweave.db` (the preserved
   pre-migration original), and do not repoint the trial Hub's database.
4. **Install nothing new.** No new dependency in any language. The operator confirmed the spec cap
   but explicitly declined to authorise `pywebview` and declined to restate a general toolchain
   allowance. A package that seems necessary is a `decisions_for_user` entry, not a `pip install`.
5. **Never mark work complete because a plan exists.** Only verified implementation closes a task.
6. **Every claim measured or labelled unverified.** If it could not be run, the log says so.
7. **Decisions that are the operator's get written down, not guessed.**

### The one setting most likely to surprise a reader

`spec_round_protocol.at_cap` is **APPROVE AND EXECUTE**. Changed by the operator this session, in
these words: *"one more change after the 3 round spec cap approve and execute."* On the previous run
that gate shipped an artifact with its objections recorded and stopped, which is exactly why Q6
ended at 0/21. Tonight N2, N2b and N3 are expected to land as **working code**.

This delegates approval to the run for tonight, **in openspec only**. It does not touch the
product's own rule that only an operator may approve a spec document — that rule is code, in
`spec_lifecycle.transition`, and N2 must not weaken it while adding an operator-only archive act.

**N4 is the single exception**: spec only, no implementation, because implementing it needs
`pywebview` and no new dependency is authorised.

### Baseline — any red below is this run's own

Verified interactively at `b2b0cd5`, immediately before starting. Do not re-verify from scratch.

| Gate | Result |
|---|---|
| `pytest hub/tests/ -n 8` | 2068 passed, 11 skipped |
| `pytest tests/ -n 4` | 362 passed, 3 skipped |
| `npm test` | 921/921 |
| `npm run lint` | clean |
| `npx tsc --noEmit` | clean |
| `ruff check` | clean |
| `black --check` | 383 files clean |
| `openspec validate --changes --strict` | 17/17 |

Four of those were **red** at the start of the interactive session and were fixed before seeding:
the UI suite was flaky (a different `userEvent` test timed out on roughly every full run), UI lint
exited 1 on nine warnings, eight Python files had drifted out of `black` format, and Q6's own
`app-lifecycle` delta failed strict validation.

### Preparation already done — do not redo it

`/autonomous-prep` ran with the operator awake; eight `AskUserQuestion` rounds, and the resulting
plan was presented in full and explicitly approved before the run started. There is **no interview
left to do**. Every answer is in `STATE.json` under `limits`, `decisions_for_user` or
`spec_round_protocol`.

Four rulings are binding and must not be re-litigated:

- **Archiving is an operator act**, mirroring the existing rule that an agent cannot approve.
- **The corpus absorbs a finished change by explicit authored merge**, not automatic migration.
- **Capability documents sit outside the phase machine**, and carry a **dedicated phase value with
  no transitions** — not a permanent `approved`, because that row would lie about what it is.
- **The job system composes with AgentWeave's own primitives** and supports **many named loops** at
  different cadences, never a singleton.

One question is deliberately **open**: the task board at scale. The operator said *"Maybe make a
task board by spec? I don't know"* and meant it. N1 answers it with evidence; N2b acts on the
answer, or records why not.

### Two environment traps that cost the most if forgotten

- **Start the Hub from `hub/`, never the repository root.** `python -m uvicorn` puts the working
  directory on `sys.path[0]`, so this repo's own `hub/` directory shadows the installed `hub`
  package. The parent process survives, so migrations run and only the spawned server dies — 60
  seconds later, with its output already sent to `DEVNULL`.
- **`pytest` has no timeout plugin here.** `--timeout=` is an unrecognised argument and fails
  collection outright with exit 4.

Next: install the driver and release the branch to it. First work item is `N1-corpus-at-scale`.
