# Driving the spec flow end to end — aw-loop10

**2026-08-15, 12:00–13:00 BST.** Project `aw-loop10` (`proj-ff695d96`) at
`C:\Users\huida\Documents\aw-loop10`, Hub on `:8010` restarted onto current code first.
Fresh project, deliberately: first-run friction can only be seen once.

Agents: `speccer` (claude, Spec Author charter), `builder` (claude, Developer),
`verifier` (codex, Verifier, `can_accept_evidence=true`) — the loop-9 composition.

Codebase under specification: `notify-window`, a 40-line quiet-hours decision function with
6 passing tests, chosen because it is small enough to read in one turn and genuinely
under-specified.

---

## The headline: the spec flow works, and this is the first time it has been watched working

`2026-08-12-hub-owns-the-spec-document` task 17.6 and
`2026-08-13-the-tool-list-matches-the-tools` task 5.1 both say the same thing — nobody has ever
observed an agent call `submit_spec_document` and write a document. **It has now been observed.**

| | run 1 `run-d3b6f7c5` | run 2 `run-462fb78e` |
|---|---|---|
| duration | 72s | 140s |
| exit | 0 | 0 |
| cost | $0.2703 | $0.4681 |
| tools | Read ×3, Grep, Bash, `read_spec_document`, `rename_spec_document` | ToolSearch, **`submit_spec_document`** |
| outcome | interviewed the operator in its reply, wrote nothing | wrote the document |

`content_digest` moved `e3eba36d…` → `6e8b6b36…`; 8 requirements minted `FR-1`–`FR-8`; the file on
disk is 23,328 bytes.

**Run 1 writing nothing was correct, not a defect.** `SPEC_PHASE_DUTIES["exploring"]` says
*"Interview in your reply, not through a tool… then end your turn and let the operator answer in
the composer."* It did exactly that, and its two questions were the two real forks in the problem:
what replaces the boolean, and whether "can wait" means "later" or "gone". This is
`2026-08-13-the-interview-is-a-conversation` working as designed.

### The document is good

Faithful to the answers given, and it did the thing a specification is for — it found what the
operator did not say. Two open questions it raised unprompted:

- a notification already stale **on arrival** — FR-6 as written ("no notification is discarded")
  would require delivering something already useless, and the operator never ruled on it;
- a deadline falling **exactly** at the window's end, against the existing half-open
  (start-inclusive, end-exclusive) boundary convention the code already uses.

Both are real. The second one it found by reading the existing tests, not by pattern-matching.

Every requirement carries a rationale, and the acceptance criteria are per-requirement
Given/When/Then. This is the evidence `17.2` / `5.2` / `6.1` have been waiting for — see
`2026-08-15-judgement-evidence.md`.

---

## Findings

### 1. The activity log is 65% duplicate `context_warning` rows — real, worth fixing

23 event rows for the whole session. **15 are `context_warning`**, and they repeat identical
measurements consecutively:

```
11:01:18.903  context_warning  context_tokens: 46378, percent: 4.64
11:01:19.997  context_warning  context_tokens: 46378, percent: 4.64
11:01:20.697  context_warning  context_tokens: 46378, percent: 4.64
11:01:22.982  context_warning  context_tokens: 47665, percent: 4.77
11:01:24.163  context_warning  context_tokens: 47665, percent: 4.77
11:01:24.628  context_warning  context_tokens: 47665, percent: 4.77
11:01:24.807  context_warning  context_tokens: 47665, percent: 4.77
```

Four rows for one unchanged number, inside two seconds. The signal — trigger, start, complete — is
buried in a measurement that did not change. Two obvious fixes: only write a row when the value
moves, or drop the severity so it does not read as a warning at 4.6% of a 1M window. The name is
also wrong for what it is: nothing is being warned about.

**Suggested QoL (q6): emit `context_warning` only on change, or above a threshold.**

### 2. `create` refuses an existing directory without naming the alternative — minor

```
POST /projects/create  {"path": "…/aw-loop10"}
→ {"code":"invalid_project_path","message":"create requires a target that does not exist"}
```

Correct, and the code is clear. But the operator's next move is always `POST /projects/open`, and
the message does not say so. One clause — "use open for a directory that already exists" — turns a
correct refusal into an actionable one. The UI may already do this; worth checking before changing
the API text.

### 3. Route path reads `/projects/{id}/project/…` — cosmetic, do not churn it

`spec.py`'s router carries `prefix="/project"` and is mounted under `/projects/{project_id}`, so
every spec route is `/api/v1/projects/{id}/project/spec/...`. Singular inside plural. Harmless, and
renaming it would break every client for a cosmetic gain. **Recorded so the next person does not
think they have found a bug.**

### 4. The minted directory name is very long

The rename produced
`spec/changes/notify-window-graded-notification-urgency-beyond-quiet-hours-boolean/`, 66
characters, from a subject the agent chose. It is descriptive and it is legal, but on Windows it
eats a third of `MAX_PATH` before the project directory is counted. Worth a cap — and note the
document's *title* was later refined to something shorter and better ("deadline-based admission
beyond the quiet-hours boolean") while the **path kept the first, worse phrasing**, because the
path is minted once at rename time.

---

## Four things that looked like defects and were not

Recorded because each cost time, and the next person will hit them the same way.

1. **`GET /agent/{name}/chat/{conv}` returns `entries`, not `messages`.** Parsing for `messages`
   yields an empty list and looks exactly like "the run left no trace". The timeline was complete
   all along — 19 entries, operator input through to `Completed (cost: $0.2703)`.
2. **The agent roster has no `last_run_id` field.** Printing one shows `None` and reads as "the run
   never attached to the agent". `status`, `context_usage` and `session_started_at` are the real
   fields, and all three were correct.
3. **Em dashes in agent output looked like mojibake** in terminal output. Stored correctly as
   U+2014; zero U+FFFD in the row. It was the console codepage.
4. **The spec `requirements` index returns no `statement`.** By design — it is an index of
   identity, state and anchor, with a readable `key` slug. Statements come from
   `read_spec_document`.

The lesson worth keeping: **check the response schema before believing a surface is broken.** Three
of the four "findings" above would have been filed as serious bugs by anyone reading the output
without opening the endpoint.

---

## Not reached in this session

Propose → approve → task derivation → build → `record_evidence` → accept → approve → merge. The
document exists and is in `exploring`; everything downstream of it is still unexercised here.
Loop 9's approve→merge half also remains unexercised, which is now the longest-standing untested
claim in the product.

---

## Continued, next iteration: propose → approve, and a real defect in how they interact

Picking up where the above left off, same `aw-loop10` project, same document. All calls made as the
operator against `http://localhost:8010` with the `aw_live_...` credential from
`operator_credentials` (the Hub has no other way to mint one outside the UI's own session — worth
noting as its own friction below).

### `close-exploration` then `propose`: blocked correctly, but the blocking message points at the
wrong fix

`close-exploration` succeeded immediately (`explore_closed: true`). `propose` came back **still in
`exploring`**, refusing with two classes of finding: `unresolved_question` (the two open questions
from the interview) and `requirement_without_task` for all 8 requirements.

Both are real gates, working as designed — `spec_completeness.check()` (`hub/hub/spec_completeness.py`)
checks that every open question is `resolved: true` and that every requirement key appears in the
document's **own** declared `tasks` list.

Resolved the two open questions by triggering `speccer` again on the same conversation
(`conv-243dd3e2`) with the operator's decisions: a notification already stale on arrival is dropped
silently (not delivered, not digested — a ninth requirement, `stale-on-arrival-is-dropped`/FR-9, was
minted for this), and a deadline exactly at the window's end defers rather than interrupts, for
consistency with the codebase's existing half-open boundary convention. `run-d57f6a1b`, 57s, exit 0.
Both questions now carry `resolved: true` and a recorded `decision` string.

### Finding: a task board task with the right `requirement_ids` does not satisfy `propose` — only the document's own `tasks[]` does, and nothing tells you that

Before understanding the mechanism, I did what a real operator reading `"'X' has no task, so nothing
implements it"` would plausibly do: created two tasks directly via `POST /tasks` with
`requirement_ids` naming all 9 requirements and `spec_document` set to the right path. The response
confirmed proper linkage — `requirement_links` populated, correct identifiers, correct
`document_id`. Re-running `propose` afterward: **identical blocking list, byte-for-byte, all 9
`requirement_without_task` findings still present.**

The reason is in `spec_completeness.check()`: `tasked = {key for task in payload.tasks for key in
task.requirements}` reads `payload.tasks` — a list embedded in the **document's own JSON content**,
written only by `submit_spec_document` — not the real `Task` table the board and `/tasks` API read
and write. A task created on the board, however correctly linked to real `SpecRequirement` rows,
is invisible to this check. `hub/hub/spec_tasks.py`'s own docstring names the failure mode this
produces exactly: *"an operator approved nineteen requirements and got nothing... two
decompositions, no relationship between them, and the one that was reviewed and approved was the
one nobody worked from."* That comment describes the fix for **half** the problem — `materialise()`
now turns the document's declared tasks into real board rows on approval — but the other half is
still open: **nothing stops an operator or agent from also creating real board tasks by hand before
approval, and nothing reconciles the two.**

Confirmed the duplication happens: after triggering `speccer` again to add its own `tasks[]`
declaration (`run-aa971bc3`, exit 0) and re-running `propose` (now unblocked, phase → `proposed`)
and then approving (phase → `approved`), the approval's `tasks_created` returned **3 more tasks**
(`task-1f82d976`, `task-0d3c8cb5`, `task-553c2c37`) covering the identical 9 requirements the 2
hand-made tasks already covered. Five tasks on the board for one decomposition. Rejected the two
hand-made ones (`status: rejected`, operator-only edge, with a note) rather than deleting — there is
no delete route, which is itself consistent with the product's evidence-first design, but confirms
the duplication is not self-healing.

**The fix that would close this**: either (a) have `propose`'s blocking message say explicitly that
it means the document's own declared decomposition, not the task board — the current message
(`"'X' has no task, so nothing implements it"`) reads as a statement about the board, since "task" is
the board's word everywhere else in the product — or (b) have the completeness check also credit a
real board task whose `requirement_ids` cover the requirement, so the two paths converge instead of
silently coexisting. (b) is more work but is the one that actually prevents the duplication rather
than just explaining it. Filed for `q4`.

### Minor: minting an operator API key requires reading the database directly

There is no CLI command or documented HTTP bootstrap to obtain `operator_credentials.id` outside the
Hub UI's own login flow. Ended up reading `hub/data/agentweave.db` directly
(`select id from operator_credentials`) to script the calls above. Fine for this loop's own driving,
but worth a `agentweave doctor`-adjacent surface (`cli.py` "does only what cannot be done from inside
the app" — minting a scriptable operator credential arguably qualifies) if operator scripting against
the Hub API becomes a supported pattern rather than an autonomous-loop workaround.

### State as of this entry

Document `spdoc-1d230e6b` is `approved`. Board carries `task-1f82d976` (admission decision: FR-1,
FR-2, FR-3, FR-4, FR-7, FR-9), `task-0d3c8cb5` (digest delivery: FR-5, FR-8), `task-553c2c37`
(no-notification-lost: FR-6), all assigned to `builder`. `builder` has been triggered on
`task-1f82d976` (`run-84f3535c`) with `task_id` bound so the run's completion moves the task off
`pending`. Outcome not yet known at the time of writing — continued below once the run lands.
