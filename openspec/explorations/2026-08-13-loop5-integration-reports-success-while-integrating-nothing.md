# E2E run — the loop from zero, and integration that reports success while integrating nothing

**Date:** 2026-08-13 · **Project:** `aw-loop5` (`proj-30d900a7`) · **Hub:** `cb39e1c`
**Runners:** Codex (`architect`, `verifier`) and Claude (`builder`)
**Scope, as the operator set it:** a project from zero — spec, tasks, agents working, one simple
feature — checking every friction point, including whether the spec can evolve.

Feature built: a single-file Python habit-streak tracker. 19 requirements, 3 tasks, 38 tests.

Findings are ranked by what each costs, not by where it was found.

---

## G1 — Integration reports success while integrating nothing *(critical, shipped today)*

**`cb39e1c` merged `master` into `master` and recorded `outcome: merged`.** None of the work is in
the product.

Evidence, from the live database and the real repository:

```
evidence_footprints:  ev-0adc23cd  git  6425180…  branch=master  reachable_from_main=1
task_integrations:    tint-db9fba57  commit=6425180…  source=master  target=master  outcome=merged
coverage:             FR-7 -> verified / integrated

$ git log --oneline master          6425180 init
$ git ls-tree -r --name-only master README.md
$ git log --oneline agentweave/builder
    247dedd Auto-snapshot: builder's turn
    80efe7b Auto-snapshot: builder's turn
```

`habits.py` and `test_habits.py` exist only on `agentweave/builder`. Master has never contained a
line of the product.

**Cause.** `requirement_evidence.read_footprint(workspace.root)` reads the **project root's** HEAD.
Agents do not work there — `worktrees.py` gives every agent `.agentweave/worktrees/<agent>` on branch
`agentweave/<agent>`, which is where the code is. The footprint therefore never names the agent's
commit; it names whatever the operator's checkout happens to be sitting on.

Everything downstream inherits it: `reachable_from_main` compares master to itself and returns true,
coverage reports `integrated`, and `integrate()` merges a commit that is already an ancestor.

**Why this is the worst finding rather than merely a bug.** B3 built `verified, not integrated`
specifically so `verified` could not describe code that never ships. This inverts that guarantee
into a false positive: the one state the design existed to make unreachable is now the state it
reports. An operator reading the Spec view is told the requirement is verified and in the product,
and both halves are wrong about the same work.

**Secondary defect in the same path.** `integrate()` has no guard for `source_branch ==
target_branch`. Merging a branch into itself is not a merge and should not be recorded as one — that
guard would have surfaced this immediately instead of producing a green result.

**Not covered by any existing change.** This is new, and it is in code committed today.

---

## G2 — The specification tool surface is write-only *(critical)*

No agent can read an approved specification. The tool surface has `submit_spec_document` and
`rename_spec_document`, and **no read**:

```
$ grep "def .*spec" hub/hub/mcp_server.py
792:def submit_spec_document(
887:def rename_spec_document(path: str, subject: str)
```

Both runners hit it independently. The Claude builder, after trying Bash, Read, ToolSearch,
`ListMcpResourcesTool`, HTTP to `HUB_URL`, and PowerShell:

> *"The specification document isn't reachable from my sandboxed worktree — no filesystem access
> outside it, no network access to the Hub API, and no MCP resource exposing it."*

The Codex architect, on a peer-triggered run, reached the same conclusion in its own words:

> *"The Hub exposes the requirement links but not a read-back endpoint for the rendered spec."*

**What it costs.** The builder blocked, messaged the architect, and the architect **reconstructed the
contract from context and relayed a paraphrase**. The implementation was then built against the
paraphrase, not the approved document. Any drift between them is structurally invisible — nothing
compares what was built against what was approved, because the thing that was approved cannot be
read.

This run got lucky: the streak semantics survived the relay intact (verified by hand, G-held below).
That is not a property of the system, it is a property of this particular paraphrase.

**Distinct from `2026-08-13-the-spec-tool-reaches-the-agent`.** That change fixed
`submit_spec_document` never being *registered* — already shipped, and the architect used it fine
four times. The read gap is a separate hole and nothing plans to close it.

---

## G3 — Requirement links carry no statement *(high)*

B3's own user test guide (`tasks.md` §9, step 2) promises a task shows its requirements "with their
current statements." It does not:

```json
{"identifier": "FR-1", "requirement_id": "spreq-b592d81d",
 "document_id": "spdoc-27e020e8", "state": "active", "anchor": "#FR-1"}
```

Identifier, ids, state, anchor. No text. So an agent receives `FR-1` and an anchor **into a document
it has no tool to read** (G2). B3 made requirements addressable without making them readable, and the
two gaps compound: the pointer is precise and the target is unreachable.

Closing G3 alone would substantially reduce G2's cost, and is far smaller.

---

## G4 — An approved specification produces no work *(high)*

Approving the document generated nothing:

```
tasks: (no tasks)
coverage totals: {'unserved': 19, ...}
```

19 approved requirements, an empty board, and no step between them. The operator must know to ask an
agent to decompose it. When asked, the architect did it well — three tasks, all 19 requirements
linked, `unserved` went to 0 — but nothing in the product suggests that this is the next move, and
nothing would have noticed if it never happened.

This is the same shape as F4 from the 2026-08-13 run (nothing integrates the work), one phase
earlier: **the lifecycle has no step between "approved" and "someone decided what to build."**

---

## G5 — The interview asks in prose, and only the last question survives *(medium)*

Across two interview rounds the architect asked roughly eighteen substantive questions and called
`ask_user` **zero times**. The unasked-question backstop caught exactly two — the final sentence of
each turn:

```
pending :: Finally, when you travel or change the computer's timezone, should "today" always me…
pending :: What would make you call the first version successful after using it for a week?
```

Everything else — the single/multiple habit fork, streak semantics, history policy, error
philosophy, file location — is recorded nowhere. `questions` is `[]`.

Two distinct problems:

1. **The backstop measures the wrong thing.** It fires on "the final text ends in a question", which
   catches the last question of a turn rather than the questions of an interview. Its presence makes
   the ledger *look* covered while 16 of 18 evaporated.
2. **Answering never closes the row.** I answered "what would make you call the first version
   successful" in prose in the very next turn. Its row is still `pending`. Rows the backstop opens
   accumulate as false-pending because the conversation that answers them cannot resolve them.

This is F6 from the previous run, now quantified. **Held:** see G-held — the agent did not *guess*
at the one question I deliberately left unanswered, twice, and wrote it into the document as
unresolved. The prose channel loses questions; the agent's own discipline is what saved this one.

---

## G6 — The product crashes after mutating state, and no gate noticed *(medium)*

Not an AgentWeave defect — a defect in what AgentWeave built, which every gate passed.

```
$ PYTHONIOENCODING=cp1252 python habits.py add "café ☕"
UnicodeEncodeError: 'charmap' codec can't encode character '☕'
$ echo $?
1
$ cat ~/.habits.json
{"habits": [{"name": "café ☕", "checkins": []}]}
```

**The habit was written, then the program crashed.** State mutated, failure reported, exit 1. An
operator would re-run or assume nothing happened. cp1252 is the Windows console default, and the
operator's stated requirement was "Windows and macOS both matter to me."

All 38 tests pass under `utf-8` *and* `cp1252`, because `unittest` captures stdout without going
through the console encoder. File I/O correctly uses explicit `encoding="utf-8"`; only the terminal
path is wrong.

This is the class the skill's step 6 exists for. Worth recording that the loop shipped it through
implementation, self-review, and an architect review without anyone running the tool the way a user
runs it.

---

## G7 — An agent reported work complete that the ledger refused *(medium)*

The builder's closing summary: *"Updated all three of my assigned tasks to `completed`."* Two of its
`update_task` calls returned `tool failed` mid-turn, and it did not notice or mention it. The board
disagreed with the report at the moment it was written.

The transitions show the architect subsequently reviewed all three and sent every one back:

```
task-8d03e365  completed -> under_review -> revision_needed   (architect)
task-d5066bb7  completed -> under_review -> revision_needed   (architect)
task-1976c921  completed -> under_review -> revision_needed   (architect)
```

The ledger stayed correct throughout — this is a reporting gap, not a state gap. But an operator
reading the chat and not the board would have believed three tasks were done.

---

## G8 — Design notes are reported as unresolved requirements *(low)*

The architect filled the free-text `requirements` field with prose constraints alongside the real
`requirement_ids`. Every task now reports three "unresolved requirements":

```
unresolved: [{'reference': 'Keep the deliverable to one directly runnable .py file.',
              'reason': 'unparsed'}, …]
```

The lenient absorption is behaving exactly as B3 §2.4 specifies — never refuse, preserve verbatim —
and the *surface* reads as breakage. Nothing is wrong, and every task looks like it has three
problems. The field's name invites this: `requirements` reads as "notes about requirements."

---

## G9–G11 — carried and cosmetic *(low)*

- **`.pyc` files committed, no `.gitignore` seeded.** Unchanged from the previous run's F4 note.
  `__pycache__/habits.cpython-311.pyc` is on `agentweave/builder`.
- **`CLAUDE.md` claims 21 starter charters; 9 ship** (`hub/hub/data/charters/` has 9 files, and all 9
  seed correctly). Documentation drift, not a product defect.
- **A renamed document's title lags until the next save.** After `rename_spec_document` the path was
  `local-command-line-habit-tracker` while the title was still `Habit streak tracker`; it corrected
  on the architect's next submission. Transient, not permanent — a narrower statement than the
  previous run's F9.

---

## What held

Worth recording, because the next session should not re-test these.

- **A document earns its name.** `rename_spec_document` fired unprompted once the subject was clear,
  moving `emerald-griffin` to `local-command-line-habit-tracker`.
- **B3's index works from cold.** 17 requirements auto-indexed on first save, 19 after the update,
  **0 diagnostics**, no operator action.
- **B3's linking works.** `requirement_ids` resolved on every `create_task`; `unserved` went 19 → 0.
- **The agent preserved an unanswered question rather than guessing — twice.** I deliberately never
  answered the malformed-data-file question. It re-asked once, then wrote it into the document as
  explicitly unresolved: *"I'll preserve that explicitly as unresolved rather than silently choosing
  a recovery policy."*
- **Peer messaging triggers real work.** The builder's `send_message` started `run-c24408ac` on the
  architect, which answered and unblocked it. The architect then reviewed all three tasks and moved
  them to `revision_needed` without any operator prompt.
- **Streak semantics are correct.** Recomputed by hand against the rule as I stated it — ten cases
  including the subtle one (*checked in yesterday, not today, streak stays alive*; *miss a full day,
  it dies*). **0 failures.** This survived the G2 paraphrase relay intact.
- **`main-branch-suggestion` suggests without assigning.** Returned
  `{"suggestion":"master","chosen":null,"is_repository":true}`, and nothing merged until the operator
  set it — which is the whole point of `cb39e1c`'s D2.
- **Integration skipped correctly when it should.** Approving a task whose requirements had no
  accepted evidence recorded `skipped` with *"no accepted evidence names a commit, so there is
  nothing to merge"* rather than merging something arbitrary.
- **The settings route refuses a branch the repository does not have**, at the moment the operator
  submits it.

---

## Not reached

The operator's scope included **evolving an approved spec**, which this run did not get to — G1 and
G2 absorbed the time. A second run should reopen the approved document, reword a requirement, and
check that evidence goes `stale` and links survive, which is B3 machinery no run has exercised.

Rigor promotion to `gate` was also not exercised on this project; B4's gate has still never fired
against a real agent's task outside `aw-e2e`.

---

## Resolution — 2026-08-14

Fixed in `openspec/changes/2026-08-14-what-the-product-actually-built`, verified against this same
project (`aw-loop5`), which was deliberately preserved as the reproduction.

**G1, before and after, from one response:**

```
ev-0adc23cd  operator  branch=master              reachable=True   ← the false positive
ev-6590836c  agent     branch=agentweave/builder  reachable=False  ← the truth
```

Then: approval merged `63ec206278bb` into `master`, `habits.py` and `test_habits.py` arrived on the
main branch behind a real merge commit, coverage moved to `verified / integrated`, drift raised
nothing, and a second approval of the same work recorded
*"already in master; there was nothing to merge"* while leaving `master` untouched.

**G2, G3, G4, G8, G9, G10, G11** are all closed by the same change. **G5** was closed as a non-goal
by the operator: *"that's okay because this is an AI test. The AI should answer or not deliberately…
The operator will answer those questions when he's working on it."* **G6** is a defect in what the
agents built, not in AgentWeave.

### Three further defects, found only by driving the fix

Each of these survived a green unit suite and was exposed by running against a real project.

1. **The merge could not commit.** `git merge` failed with *"Committer identity unknown"* in a
   repository with no configured `user.email`. `snapshot_worktree` had always supplied
   `-c user.name/-c user.email` for exactly this reason; the merge did not. So the Hub could create
   an agent's commits and then be unable to integrate them. Every test repository sets an identity
   in setup, so no test could reach it.
2. **The `.gitignore` seeding did nothing for the project it was written for.** `open_existing`
   returns early for an already-registered project, so seeding only ever reached brand-new ones —
   and existing projects are precisely the set whose agents have already been committing.
3. **The UI staleness warning could not be cleared.** It watched all of `hub/ui/src`, including
   `__tests__`, which is never bundled. Editing a UI test marked the artefact stale permanently: an
   identical rebuild commits nothing, so the artefact's commit date never moves. A warning that
   cannot be cleared teaches an operator to ignore the one signal that catches a real stale bundle.

**The pattern worth keeping.** All three, and G1 itself, are cases where the test environment was
shaped like the thing under test rather than like the product. The integration tests used
branch-switching in one repository because that was convenient; AgentWeave gives every agent its own
checkout. The repositories set an identity because that was tidy; real ones often have not. **A
suite that constructs its own world will confirm that world.**
