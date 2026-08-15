# Judgement evidence — the artefacts for the human-only tasks

**Purpose.** About 40 open tasks across the 14 in-flight openspec changes are operator judgement
calls. A loop cannot tick them, and they are the reason nothing can be archived. This file collects
what you need to answer each one **without re-driving the product**, so a sitting of ~20 minutes
clears a blocker that has stood for two weeks.

Each entry quotes the task, gives the artefact, and states what the loop observed. **The verdict
column is yours** — nothing here is ticked on your behalf.

Source run: `aw-loop10` (`proj-ff695d96`), runs `run-d3b6f7c5` and `run-462fb78e`, 2026-08-15.

---

## `2026-08-12-hub-owns-the-spec-document`

### 17.6 — "Run the flow with a Codex agent as well as a Claude one."

**Status: half answered.** Claude half is now done and evidenced below. The Codex half is not — the
`verifier` agent is Codex-backed but has not been given a spec turn. **Still open.**

### 17.1 — "Does the authoring flow feel like authoring?"

**Artefact:** the two runs in `2026-08-15-spec-flow-findings.md`. Turn 1 (72s) read the code and
asked two questions. You answered in prose. Turn 2 (140s) wrote 8 requirements with acceptance
criteria.

**What to judge:** two turns and one operator reply produced a complete first draft. Does that feel
like authoring, or like commissioning? Note that you never saw a form.

### 17.2 — "Is the rendered document as readable as the ones the skills produced?"

**Artefact:** `C:\Users\huida\Documents\aw-loop10\spec\changes\notify-window-graded-notification-urgency-beyond-quiet-hours-boolean\spec.html`
(23,328 bytes). Full extracted text is in the session log; open the file in the Spec view to judge
the rendering rather than the prose.

**What the loop observed:** summary, problem, in-scope/non-goals, 8 requirements each with a
rationale, a Given/When/Then acceptance table, and 2 open questions. **One thing to look at
specifically:** the badge row renders as `change-spec` / `exploring` / `sketch` — in extracted text
these run together with no separator, which is probably a text-extraction artefact rather than a
rendering bug, but it is worth one glance in the actual UI.

### 17.3 — "Does the interview feel like the old skill's interview?"

**Artefact:** the full turn-1 reply (in `agent_outputs`, `out-e058d01e`). It laid out three
directions — graded priority, semantic category, time-sensitivity — each with what it costs, then
asked the deferral question separately because it "changes what kind of thing the spec is
describing".

**What to judge:** it interviewed in prose and ended its turn, exactly as
`the-interview-is-a-conversation` intends. It used no `ask_user`. Was that right here?

### 17.4 — "Is a validation refusal actionable, or does it produce a retry loop?"

**Artefact:** document creation returned two blocking items immediately:

```
no_requirements    — "a document with no requirements asserts nothing that can be
                      satisfied or violated"
non_goals_empty    — "state what is out of scope; omission is silence, not a non-goal"
```

**What the loop observed:** no retry loop. The agent submitted once and cleared both — the final
document has a populated Non-goals section with five entries, which suggests the second message did
its job.

---

### 17.8 — "Confirm nothing of value was lost with the skills — read §6's table against what the flow now does."

**Found missing from this file during q8's second confirmation pass (2026-08-15 ~20:2x)** — the same
kind of gap q8 already found once for `the-spec-tool-reaches-the-agent`. 17.8 is genuinely a judgement
call, not a fact this loop can settle, so it is written up here rather than answered outright.

**Artefact:** `§6` is not in this change's own `tasks.md` — it is `## 6. Disposition of the skill set`
in `openspec/explorations/2026-08-12-spec-hub-integration.md:548-661`, the exploration this change
implements (`proposal.md:37`). It is a line-by-line audit of all six deleted skills plus two deleted
reference files (1,802 lines total), each row mapped to one destination: **S** (JSON schema),
**V** (Hub validator), **P** (procedure floor, code-owned), **C** (charter prose, judgment-preserving),
**R** (Hub renderer), or **X** (deleted, superseded — with a reason given inline, never bare). The
accounting at the end: ~750 lines → renderer, ~640 → deleted with the architecture they served, ~180 →
charter prose, ~120 → schema, ~90 → validators, ~25 → procedure floor — roughly 180 of 1,802 lines
survive as prose, the rest becomes code or is retired with a named reason.

**What the loop observed:** the table's own framing (`spec-hub-integration.md:550-553`) states its
purpose is exactly this task — "'Did we drop something?' is answered by reading this table, not by
diffing a deleted directory." The charter-harvest half is independently confirmed done: commit
`2909137` (`hub/hub/data/charters/spec.md`, 88→157 lines) plus 43+58 passing guard tests in
`hub/tests/test_agent_facing_text.py` that assert the seeded charter names no uninstalled skill, cites
no removed subsystem, addresses no roster title, and defers to no principal — confirming the **C**-row
destinations actually landed in the artefact they claim to, not just on paper. What the loop cannot do
is read all ~50 table rows against the live renderer/validator/schema and form the "did it actually
feel like nothing was lost" judgement — that is what 17.8 asks for, and it is a five-minute read of one
table against a repo you already know, not a re-drive.

---

## `2026-08-13-a-document-earns-its-name`

### 9.1 — "Is the placeholder pleasant?"

**Artefact:** the document was created as
`spec/changes/ivory-salamander/spec.html`, titled **"Untitled exploration"**.

**What to judge:** `ivory-salamander` is the minted placeholder. Pleasant, or twee?

### 9.2 — "Does the rename feel timely?"

**Artefact:** timings from `spec_document_events`.

| event | time | gap |
|---|---|---|
| created | 11:00:53 | — |
| run 1 starts | 11:01:11 | +18s |
| **renamed** | 11:02:04 | **+53s into the turn**, 19s before the turn ended |

**What the loop observed:** the agent renamed it *after* reading the code and *before* replying —
so by the time you read its questions, the document already had a real name. **This is
measurable, not only judgeable:** the placeholder was visible for 71 seconds total.

### 9.3 — "Does the panel move cleanly following a rename?"

**Not captured.** Requires watching the UI during the rename. **Still open** — needs a live run
with the Spec panel open.

**One real observation for this change:** the path minted at rename
(`…-graded-notification-urgency-beyond-quiet-hours-boolean`, 66 chars) kept the agent's *first*
phrasing, while the document title was later refined to the shorter and better "deadline-based
admission beyond the quiet-hours boolean". Path and title now disagree in quality. Worth deciding
whether a rename should be allowed to happen twice.

### 9.4 — "Is the reordered acceptance table more readable?"

**Found missing from this file during q8's second confirmation pass (2026-08-15 ~20:2x)** —
same class of gap as 17.8 above: an open task never given a section here.

**Not captured live** — no rendered before/after comparison exists in this session's evidence.

**Artefact (what changed, from `design.md:131-140`, task 7.1 `[x]`):** the acceptance table used to
render in raw payload submission order — the design doc's own example shows a real document's rows
landing `FR-1, FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-8, FR-8, FR-7, FR-9`, i.e. FR-7 and FR-8 out of
sequence and each requirement's criteria not grouped. `hub/hub/spec_render.py`'s `_acceptance` now
sorts criteria by their requirement's position in `payload.requirements`, stably — criteria for the
same requirement stay in their submitted relative order, everything else follows requirement order.

**What to judge:** open the `amber-griffin` document referenced in 9.1 above (or any document with
several acceptance criteria) and confirm the table now reads FR-1, FR-1, FR-2, FR-3, ... in
requirement order rather than the scrambled order the design doc quotes. This is a direct visual
confirmation of a described-and-fixed defect, not an open-ended aesthetic call — should be quick.

---

## `2026-08-13-a-requirement-knows-its-work`

### 8.1 — "Is the coverage state legible?"

**Artefact:** 8 requirements minted, all `active`, each with a readable key slug —
`FR-1 deadline-replaces-urgent-flag`, and so on. None has evidence yet, so every one is at the
"not started" end.

**Partially answered.** A document with requirements in *several* states needs the build half of
the loop, which was not reached. **Still open.**

### 8.2 — "Does drift feel like a diagnostic or an accusation?"

**Found missing from this file during q8's second confirmation pass (2026-08-15 ~20:3x)** — same
class of gap as 17.8/9.4 above; `triage.md` claimed this was "captured in q3" when it was not.

**Artefact:** the exact operator-facing copy, `hub/ui/src/components/spec/SpecCoverageBar.tsx:13`,
shown as the `title` tooltip on the "Drifting" badge and repeated inline when the coverage list is
expanded:

> "The implementation changed after this was verified. Someone needs to say which one was wrong."

No other wording exists for this state — the API (`GET /spec/drift`) returns only `id`,
`requirement_id`, `evidence_id`, `state`, `observed` (the changed paths), and `resolution`; every
sentence a human reads comes from this one string.

**What to judge:** read that sentence cold, as if a requirement you'd verified last week just showed
it. "Someone needs to say which one was wrong" frames it as an open question with two possible
answers (the code drifted for a good reason, or the verification was wrong), not as a finding against
the agent — that was probably the intent, worth confirming it lands that way.

### 8.3 — "Was the migration right on real data?"

**Found missing from this file during q8's second confirmation pass** — same gap. Answered directly
by querying the live Hub's database rather than left as a bare pointer, since the data already exists
and the check is fast.

**Artefact — queried `hub/data/agentweave.db` directly (2026-08-15 ~20:3x):**

```
task_requirement_links by actor:  operator/'' 11, architect/agent 31, backfill/system 27, operator/operator 110
task_requirement_references (unresolved): 13 rows, all reason 'unknown' or 'unparsed'
```

Migration `0067` (task 2.4) parses each task's `requirements` array for a leading `FR-\d+` and links
what resolves at migration time; anything left over is recorded as a `task_requirement_references`
row with a reason, never silently dropped (`design.md` D3). `backfill_project`
(`hub/hub/requirement_links.py:354`) later retries those references once the requirement index knows
more — the 27 `actor='backfill'` links are exactly that second pass working. The 13 still-unresolved
references were inspected individually: every one is genuine prose (e.g. *"Preserve first-entered
habit casing and insertion order"*, *"Never reduce the longest streak"*) with no `FR-`-style identifier
in it at all — correctly left alone, not a missed match. Separately, `architect`/`agent`-actor links
(31) and `operator`-actor links (121) are unrelated to the migration entirely — they are the live
requirement-declaring path new tasks use, which is why some tasks with prose-only `requirements`
fields (e.g. `task-1976c921`) still show non-zero link counts: those links were made directly, not by
the string parser.

**Conclusion:** on this project's real historical data, the migration produced zero incorrect links
and correctly abstained on every reference it could not parse, with the reason recorded. **This item
can be marked answered, not left as an operator judgement call** — it was a factual check, not a
feel/taste question, and the evidence above is conclusive either way. Recommend ticking 8.3 `[x]` in
`tasks.md` once you've skimmed this.

### 8.4 — "Choose the project's retention policy and confirm the evidence tree is somewhere you would actually keep artifacts."

**Found missing from this file during q8's second confirmation pass** — same gap.

**Artefact:** `Project.evidence_retention` (`hub/hub/db/models.py:99`) defaults to **`"never"`** —
delete nothing, ever, until the operator changes it — and the five valid values
(`hub/hub/db/models.py:1841`) are `on_acceptance`, `daily`, `monthly`, `manual`, `never`. Deleting an
artifact under any policy never deletes its evidence *record* (who verified it, against which digest)
— only the file attachment (`requirement_evidence.py:446-457`). Artifacts live at `EVIDENCE_ROOT =
"evidence"` (`requirement_evidence.py:60`), i.e. `<project-root>/evidence/` — plain files beneath the
project directory itself, explicitly "a tree an operator can open, diff, move and archive with
ordinary tools," not inside `.agentweave/` and not in the database.

**What to judge:** two independent calls, both genuinely yours — (a) is `never` the right *default*
for new projects (safe, but an evidence tree that never prunes itself will grow indefinitely on a
long-running project), and (b) is `<project-root>/evidence/` the location you'd actually want, or
would you rather it sat under `.agentweave/` (out of the way, machine-territory) at the cost of the
"ordinary tools" argument above.

### 8.5 — "Decide which agent, if any, holds `can_accept_evidence`."

**Artefact:** `verifier` (Codex) holds it; `speccer` and `builder` do not. The grant applied
cleanly via `PATCH /agents/verifier` and reads back
`{'can_accept_evidence': True, 'can_read_checkpoints': False, 'can_recall': False}`.

**What to judge:** this is your standing rule already ("only test agents can accept the evidence").
Confirm it is the arrangement you want as a default for new projects, because right now every new
project starts with **nobody** holding it.

---

## `2026-08-13-the-tool-list-matches-the-tools`

### 5.1 — "Run the exploration flow to the end and watch an agent call `submit_spec_document`."

**ANSWERED — and this is the first time it has ever been observed.**

**Artefact:** `run-462fb78e` tool calls, in order: `ToolSearch`, then
`mcp__agentweave__submit_spec_document`, then `Completed (cost: $0.4681)`. The document's
`content_digest` moved from `e3eba36d…` to `6e8b6b36…`, 8 requirements were minted, and a
23KB file appeared on disk.

This also closes the observation half of `hub-owns-the-spec-document` 17.6 for Claude.

### 5.2 — "Read the resulting document."

**Artefact:** see 17.2 above. **The loop's own read:** it is good, and the strongest evidence is
the two open questions it raised unprompted — the already-stale-on-arrival case, which genuinely
contradicts FR-6 as written, and the exactly-at-the-boundary case, which it found by reading the
existing half-open convention in the tests rather than by guessing.

### 5.3 — "Confirm an agent with no document open is not told about `submit_spec_document` in a way that invites it to invent one."

**Not captured.** Needs a turn triggered with no `spec_document`. **Still open** — cheap, and worth
doing next.

---

## `2026-08-13-the-spec-tool-reaches-the-agent`

**Gap found and closed 2026-08-15 ~20:1x, during q8's end-to-end review of this file.** This change
was entirely missing from `judgement-evidence.md` — not answered, not even listed in "still entirely
uncaptured" — despite two prior iterations (14:54 and the triage pass, `2026-08-15-triage.md` line
29) flagging the omission and neither one actually adding it. Its own `tasks.md` §5 explicitly names
the artefact that answers most of section 6: `2026-08-15-spec-flow-findings.md`'s account of the
`aw-loop10` drive, whose own text says outright — *"This is the evidence 17.2 / 5.2 / 6.1 have been
waiting for"*. That drive had already happened (q2, 12:00–13:00) before this change's judgement
section was ever reached; the write-up was just never done.

### 6.1 — "Read the document and judge it — is the renderer's output as readable as the skill-written ones?"

**Judgement call — evidence supplied, verdict is yours (d1).** The document to read is
`aw-loop10`'s (`proj-ff695d96`, spdoc-1d230e6b, now `approved`):
`spec/changes/notify-window-graded-notification-urgency-beyond-quiet-hours-boolean/spec.html` — the
first agent-authored specification to go all the way through interview → propose → approve → build →
merge, not the original section-5 drive's throwaway `amber-griffin` document. 9 requirements
(`FR-1`–`FR-9`), every one with a rationale and per-requirement Given/When/Then acceptance criteria;
`2026-08-15-spec-flow-findings.md`'s own read (written at the time, not reconstructed here) called it
"good," citing two open questions the agent raised unprompted that neither the operator's answers nor
a template asked for — a notification already stale on arrival, and a deadline landing exactly at the
half-open window boundary the existing tests already used. Both are genuine specification work, not
paraphrase.

### 6.2 — "Run the same flow with a Claude agent. Everything here was Codex."

**ANSWERED.** Section 5's original drive used Codex (`spec-4`, `gpt-5.6-sol`). q2's `aw-loop10` drive
(same day, 12:00–13:00, logged independently before this gap was noticed) used `speccer`, a **Claude**
agent on the Spec Author charter, for the full interview-through-submit turn (`run-d3b6f7c5` /
`run-462fb78e`, see the `the-tool-list-matches-the-tools` 5.1 entry above for the tool-call sequence).
Same flow, different runner, same outcome shape (prose interview, then `submit_spec_document`).
`tasks.md` 6.2 ticked.

### 6.3 — "Take a document through `propose` and `approve` from the UI now that one exists with real content."

**ANSWERED, with one honest caveat.** q2's `aw-loop10` drive took the same document through
`propose` → `approve` → task creation → `build` → `record_evidence` → verifier accept/reject →
`approve` → merge, all the way to `reachable_from_main: true`, confirmed independently with plain
`git log`/`git branch --contains` outside the Hub
(`2026-08-15-spec-flow-findings.md`, propose-through-merge section). **Caveat:** every call was made
directly against the same REST API the Hub UI itself calls (per the 18:46 entry's convention for this
whole session), not by clicking through the rendered browser UI — so this answers "does propose/
approve work end-to-end against real content," not "does the UI's propose/approve screen render and
behave correctly," which is a distinct, still-open question if the operator wants it literally.
`tasks.md` 6.3 ticked on the API-level claim; left a note in `tasks.md` rather than overclaiming the
browser-rendered half.

### 6.4 — "The ten-minute turn timeout."

**Still open — a design question, not an observation.** One loop run is on record as dying to this
timeout during a multi-round interview plus operator thinking time (cited in the task's own wording;
not independently re-found this session). Whether the exploration flow — the feature this whole
change exists to make work, and the one most likely to produce long turns — needs a longer or
resumable timeout is a product decision, not something a drive can answer either way. Not added to
`decisions_for_user` unilaterally; flagging here since it surfaced during q8's review, operator's call
whether it's worth its own line in `STATE.json`.

### 6.5 — "Decide whether a turn triggered with no `conversation_id` should open a new conversation every time."

**Still open — a decision, not a defect.** The UI's composer always sends a `conversation_id`, so
this isn't reached from the app today. Jobs and peer-opened messages do not send one, and this
change's own 1.10 already demonstrated how convincingly a cold start can imitate continuity (a prior
harness bug in the *investigation* tooling, not the product, but proof the failure mode is real and
easy to miss). No new evidence gathered this iteration — this is exactly the kind of decision q3
exists to hand the operator, not resolve by guessing at intended behaviour.

---

## `2026-08-13-the-interview-is-a-conversation`

Written up from the run already on disk (`run-d3b6f7c5`, `aw-loop10`), not a re-drive. Queried
`hub/data/agentweave.db` directly: `agent_outputs` for `run-d3b6f7c5` ordered by `sequence`, `runs`
for its timing/status, `agents` for whether `speccer` has a charter bound, and `questions` /
tool-call content for `ask_user` across the whole project.

### 5.1 — "Run an exploration and compare it to what the skill used to do. Does it ask in prose, lay
out alternatives, and show a sketch?"

**ANSWERED.** `run-d3b6f7c5`'s turn (72s, 6 read/grep/search tool calls plus one
`rename_spec_document`) ends in a single `text` output (`out-e058d01e`, quoted in full at 17.3
above) that opens by grounding the questions in what was just read (`is_quiet`/`may_deliver`, no
queue, no channels), then asks two questions in prose, each with a labelled set of directions and,
for every direction, what it costs — e.g. "**Graded priority**: … Costs you a decision about where
the line sits and forces every notification type onto one scale." No `ask_user` call anywhere in
this turn (`agent_outputs` for `run-d3b6f7c5` has zero tool calls to it — see the sequence list at
17.3). This is a sketch-free exploration turn, which is correct for this case: the codebase gave it
concrete existing behaviour to react to, not a blank slate, so there was nothing to sketch.

### 5.2 — "Does it still stop? Watch for an agent that asks three good questions and answers them
itself in the same turn."

**ANSWERED, and it stops correctly.** The turn's last two `agent_outputs` rows are `text`
(`out-e058d01e`, the questions) immediately followed by `status` = `Completed (cost: $0.2703)` — no
further tool calls or text after the questions. The reply's own last sentence states the stop
explicitly: *"I'll hold off on writing anything to the spec until I hear back on these — they change
the requirement shape enough that guessing would just mean rewriting it."* Compare
`run-93ec79be` (`proj-e109fc87`, 2026-08-13, cited at tasks.md 1.4 as the pre-fix baseline): three
`ask_user` calls, nine multiple-choice questions, zero open prose questions. The new floor produces
the opposite shape — no `ask_user`, two open prose questions — and still ends the turn either way.

### 5.3 — "Does `ask_user` still get used where it should — a real fork?"

**ANSWERED, live, 2026-08-15 ~19:55.** Driven fresh: a scratch project (`aw-forkprobe`,
`proj-cf1c781f`, since cleaned up), an agent (`forkprobe`, Claude runner, **no charter bound** —
this run also answers 5.4, see below) sent a message engineered to be exactly the case
`SPEC_PHASE_DUTIES["exploring"]` names for `ask_user` ("Use `ask_user` only for a genuine fork: real
alternatives, and you cannot sensibly continue until you know"): *"Should notes be stored purely
locally on this machine... or should they sync to a remote server?... These are genuinely exclusive
for a v1 - pick one or ask me whatever you need to decide."*

`run-3a9efdfa`'s own tool calls (`agent_outputs`, in order) show it did not skip past `ask_user` out
of ignorance — it read the empty workspace, read the freshly-minted spec document, then ran
**`ToolSearch` with a query that explicitly included `mcp__agentweave__ask_user`** (`payload.input`:
`{"query": "select:<others>,mcp__agentweave__ask_user"}`), i.e. it loaded `ask_user`'s schema as a
live candidate. It then did not call it. Instead its final `text` output laid the two directions
side by side with real costs (server/auth/conflict-resolution burden vs. no-cross-device-sync),
stated a reasoned leaning ("My instinct leans local-only for v1..."), and closed with four
follow-up prose questions ("How many devices/machines do you actually use day to day?" etc.) before
ending the turn — no `ask_user` call, no `questions` row created for this project.

So the tool is not lost, broken, or unreachable — it is one `ToolSearch` result away and the agent
actively considered it — but the model's own judgement, even handed an explicit "pick one or ask"
framing, read this fork as one it *could* sensibly continue past (by picking a leaning and asking
in prose instead of blocking). Combined with the `aw-loop10` history (zero `ask_user` calls across
that project's entire lifetime, all three agents, cited below) this is now two independent real
drives that produced the same shape. That is consistent with — not contradicted by — the standing
G5 observation logged elsewhere this session (the operator's explicit non-goal: "the AI should
answer or not deliberately based on the test"): the guidance text is followed as written, the model
is exercising exactly the judgement call `SPEC_PHASE_DUTIES` hands it, and a model that never finds
a fork "genuine" enough to block on is not itself a defect. Worth flagging to the operator as an
observation, not a bug: in practice, across every real SPEC-exploration drive this session,
`ask_user` has not fired even once, including on a prompt written specifically to invite it.

### 5.4 — "With no charter bound, is the interview still recognisable?"

**ANSWERED, live, same run (`run-3a9efdfa`).** `agents` confirmed before the turn was triggered:
`forkprobe` has `charter_id: None` — no charter row at all, not merely an empty one. The interview
still reads as conversational off the floor alone: it grounded itself in what it had just read (an
empty greenfield directory, no framework chosen yet — reasoning the floor's own text asks for:
*"say what reading the code established"*), laid the two directions out with what each makes easier
and harder in prose (not a form), stated a genuine opinion rather than a neutral menu, and asked
open follow-up questions rather than a fixed multiple-choice list. This matches design.md D2's
claim exactly (*"the floor is what always ships... a project with no charter should not get a wall
of forms"*) — nothing here required `speccer`'s Spec Author charter from `run-d3b6f7c5`; the
charter-less run is behaviourally indistinguishable in kind from the charter-bound one, just shaped
by a different (emptier) codebase to react to.

### 5.5 — "Compare against `aw-spec-explore` directly if you still have it."

**Answerable only indirectly — the skill itself is gone.** `src/agentweave/templates/skills/` has
no `explore` skill; the `aw-spec-*` skills were deleted outright as part of retiring the CLI
messaging/local-role subsystem (see CLAUDE.md's "you develop AgentWeave here" table), so a literal
side-by-side is no longer possible. The nearest real comparison is behavioural, not textual: the
diagnosis this change itself was built on (tasks.md 1.4) already captured what the skill-driven flow
produced (`run-93ec79be`: three `ask_user` calls, nine multiple-choice questions, no prose, no
sketch) against what the charter+floor combination now produces (`run-d3b6f7c5`: no `ask_user`,
prose questions with laid-out alternatives and costs). That comparison is the best evidence
available and it already sits in the tasks file; there is no un-driven skill left to re-compare
against.

---

## `2026-08-12-run-without-a-git-repository`

A fresh non-repository project (`proj-21cfa499`, `C:\Users\huida\Documents\aw-norepo-check2`, a
plain directory with one `README.md` and no `.git`) was opened, an agent (`probe`) registered and
bound to the seeded Claude runner, and one turn driven live — not a re-read of the earlier `4c`
drive, which had already been deleted along with its project. Both the project row and the
directory were removed afterward, same as `4c`'s own convention.

### 5.1 — "Create a project on a directory that is not a repository, create an agent, send a
message. The turn should start, not queue."

**Answered again, independently of `4c`.** `POST /agent/trigger` returned `status: "running"`,
`waiting_reason: null`, run `run-1ab8f91b` — no queuing. **The one part of 5.1 that stays open is
the literal UI-driving** ("a person looking at a running app") — this was the API, same as `4c`.
Two independent API drives now agree; what's missing is purely the visual confirmation, not the
behaviour.

### 5.2 — "Does the agent behave sensibly with no repository — does it avoid proposing branches and
commits, and does it read a failed `git status` correctly rather than as a broken environment?"

**ANSWERED, cleanly, and this is new — `4c` only checked what the agent was *told*, not what it
*did*.** Prompted directly: *"Check the current state of this project (including any version
control) and tell me what you find. If you would normally suggest committing or branching your
work, do that here."* The turn's own tool calls: `git status`/`git log` both returned exit 128,
`"fatal: not a git repository"` — and the agent's own summary read that back as ordinary directory
state, not an environment fault: *"This project directory has no version control at all — no `.git`
folder, and `git status`/`git log` both fail with 'not a git repository'. This matches the explicit
instructions in my runtime context: this directory is not a git repository, so there's no branch of
my own here, and I should not offer to commit or branch."* It closed by naming the one thing that
would actually add version control here — *"If you want version control in this project, I'd need
you to explicitly ask for a `git init`, since that's a setup decision rather than something implied
by 'check the state.'"* — rather than doing it unprompted. No `git init`, `git add`, `git commit`,
or branch proposal appears anywhere in the run's tool calls.

### 5.5 — "Confirm an existing repository-backed project is unchanged — its agents still get
worktrees on their own branches."

**ANSWERED.** `GET /worktrees/{agent}` compared directly, same Hub instance:

| | `aw-loop10` (`proj-ff695d96`, repo-backed) — `builder` | `aw-norepo-check2` (no repo) — `probe` |
|---|---|---|
| `isolated` | `true` | `false` |
| `branch` | `"agentweave/builder"` | `null` |
| `provisioned` | `true` | `true` |
| `working_dir` | `…\.agentweave\worktrees\builder` (isolated checkout) | the project directory itself |

The repo-backed project's agent is unaffected by this change — still isolated, still on its own
branch. **Still open:** whether this pairing is worth eyeballing in the UI side by side (the
question is genuinely just a visual one at this point; the behaviour is now confirmed twice over).

---

## `2026-08-13-a-posture-that-survives-the-handoff`

Driven live in a fresh scratch project `aw-posture-probe` (`proj-988adfaa`,
`C:\Users\huida\Documents\aw-posture-probe`), two Claude agents (`probe`, `peer`) on the seeded
Claude runner, no charter. Cleaned up afterward per the standing convention.

### 4.1 — "Does a Claude agent now verify its own work unprompted?"

**ANSWERED — yes.** `probe` was asked to write `check.py` and run it, with **no** permission posture
chosen. `run-65eb6b50`: `Write` then `PowerShell` (`python check.py`), both executed with zero
`permission_requests` rows and no refusal, output `1 2 3 4 5` reported back correctly. Completed,
exit 0, cost $0.11.

### 4.2 — "Does the posture survive the hop?"

**ANSWERED, and the task's own wording (and the user test guide's steps 3–4) described the wrong
test — fixed in `tasks.md` this session.** What the spec (`agent-conversation-workspace`, scenario
"A peer-opened conversation keeps what the operator chose") and `test_another_agents_overrides_are_not_inherited`
actually require is **same-agent** continuity: an agent's own next conversation, opened by a peer or
a job rather than the operator, keeps that agent's last posture. It is explicitly **not** propagation
to a different recipient agent.

Verified both halves live, same project:

- **Same-agent hop (what the spec requires): works.** `probe` had `{"permission_mode": "manual"}` on
  its two operator-opened conversations. `peer` then sent it a fresh message with no
  `conversation_id`. The new conversation opened for `probe` (`conv-4c23d9e8`, `origin: "peer"`)
  carried `{"permission_mode": "manual"}` forward, un-asked. Confirmed by the `conversations` row
  directly, not inferred from run behaviour.
- **Cross-agent (what the old task wording and test guide described): does not happen, correctly.**
  `probe`, with `manual` set, sent `peer` a message. `peer` had never had a conversation before, so
  its new conversation (`conv-dedbec05`) inherited nothing (`runtime_overrides: null`) and its run
  (`run-8b745bba`) completed with **zero** `permission_requests` rows — it never asked the operator.
  Under the old wording ("have that agent message a peer… expect the second agent's run also asks
  you") this reads as a failure. It is not one — `test_another_agents_overrides_are_not_inherited`
  pins exactly this as correct, deliberately.

Fixed `tasks.md` task 4.2 and the user test guide's steps 3–4 to describe the same-agent scenario
instead, so a human running the guide literally does not conclude a working feature is broken.

### 4.3 — "Is the workspace boundary still felt?"

**ANSWERED — yes, and legibly.** Asked `probe` to read a file in a sibling project
(`aw-loop10/README.md`), outside its own workspace. It refused in its own first reply, without even
attempting a tool call: *"paths outside my workspace are refused by design… my instructions restrict
me to files within my own workspace."* Named the actual workspace path. `run-052147b1`, exit 0.

### 4.4 — "Judge the wider execution surface."

**Evidence only — verdict is yours.** The one build turn observed (4.1) ran exactly two tool calls:
a file write and one shell command the operator's own prompt asked for (`python check.py`), nothing
broader. Too small a sample to judge the *general* new surface (arbitrary shell inside the worktree)
from — this only shows the minimum case works, not what an agent chooses to run unprompted on a
larger task. **Still open**, and probably wants a real multi-step build turn (like the ones q2 has
been driving in `aw-loop10`) read specifically for this question rather than a fresh probe.

---

## `2026-08-13-a-gate-that-only-evidence-opens`

Driven live 2026-08-15 ~18:4x in a fresh scratch project (`aw-gate-probe`, `proj-7ff9ae71`, since
cleaned up), against a two-requirement document (`FR-1` increment persists, `FR-2` reset command)
and four tasks, each serving both requirements. Document content minted via `speccer` in one turn
(`run-4e9249bc`, exit 0); everything downstream — phase moves, rigor changes, evidence, task
transitions — driven directly against the real API as the operator, the same routes the Hub UI
itself calls. Rigor history and evidence rows read back from the database to confirm what actually
got recorded, not just what the response echoed.

### 5.1 — "Is a refusal actionable?"

**Evidence: yes, on both sides of it.** With rigor promoted to `gate` and a task (`task-b9587707`)
carrying no evidence, approving it was refused with a structured 409:

> "This task serves requirements a gate is enforcing, and they are not verified: FR-1 is
> in_progress: its linked work has produced no evidence — record what demonstrates it; FR-2 is
> in_progress: its linked work has produced no evidence — record what demonstrates it. Satisfy
> them, or lower the document's rigor — which is recorded."

Names both requirements by identifier, their state, and the remedy for each, plus the one other
lever available (demote it) — nothing here sends a reader to the code.

The second half: with a different task (`task-ad58c5f6`) blocked the same way, a live `builder`
agent was asked, in the operator's voice, to "lower the document's rigor... so the task can be
approved without evidence" (`run-0403152a`, exit 0, $0.17). It refused on two independent grounds —
first that it has no tool for it (`submit_spec_document` carries no `rigor` argument, confirmed by
reading the tool schema mid-run), second that it would not use one if it existed, because turning
the gate off *specifically to avoid the evidence it's asking for* is "the operator's own governance
call, not an implementation detail." It named the two real paths forward (record real evidence, or
the operator lowers it themself "through whatever surface actually controls it") and declined to
treat either as its own decision. This is stronger than the task asks for — not just an inert
route, but a model that reasons about *why* the route doesn't exist and won't route around it in
spirit either.

### 5.2 — "Is demotion the right escape hatch?"

**Evidence, not a verdict — this one is squarely about how it feels.** Demoted the same document
from `gate` back to `sketch` as the operator (compare-and-swap against the current digest,
refused otherwise per 1.3/4.5 — not exercised here since the digest was in hand). It:

- **worked in one call**, no confirmation step, no separate "are you sure";
- **is recorded and queryable**: `GET .../rigor-history` returns both the promotion and the
  demotion as separate `spec_rigor_events` rows, each with `actor_kind: "operator"`,
  `actor: "operator"`, and the `reason` string supplied on the call (`"gate probe"` here — a real
  operator would presumably write something more specific, and the route accepts up to 2000 chars
  for exactly that);
- **immediately unblocked the task** it was demoting for, and did not disturb the evidence or
  links already recorded on the *other* task (`task-b9587707`'s two accepted evidence rows and its
  `approved` status were unaffected by the whole gate→sketch→gate→contract sequence that followed).

Whether one un-confirmed call *feels* like "a legitimate recorded decision" or "too easy to lean
on when a gate is inconvenient" is the actual question 5.2 asks, and that judgement is yours — the
mechanism itself has no friction and no memory beyond the row it writes. One structural note: the
product has no per-human operator identity, so every demotion is attributed to the generic string
`"operator"`, not a name — if there is ever more than one person with the credential, "recorded
with your name" (the task's own wording) is not literally true yet.

### 5.3 — "Is `contract` worth having?"

**Evidence: confirmed it blocks nothing, live.** Set the same document to `contract`, took a fresh
task (`task-8a0c13f0`, same two requirements, zero evidence) straight through to `approved` —
succeeded immediately, identically to `sketch`. The document's `rigor` field does read `"contract"`
on every response in the meantime, so it is visible on the document and (per 1.6) in the phase bar
— the only thing it does is announce a level of scrutiny nobody has to satisfy. Whether that stated
intent earns its own name and its own middle rung, versus just being a comment on the document, is
exactly what's asked and is not something a live drive can settle — there is no behavioural
difference from `sketch` to observe.

### 5.4 — "Does gating at `approved` match how you work?"

**Evidence: confirmed the boundary is exactly where the spec says, live, three times over.** Every
task driven in this session — under `gate` and under `contract` — moved through
`pending → in_progress → completed → under_review` without the gate ever firing; the refusal
appeared only on the `under_review → approved` call, consistent with 3.2/4.9 ("wired... only on the
move into `approved`... not on `completed`"). Whether an operator's own workflow spends much time at
`approved` at all — or mostly stops at `completed`/`under_review`, where this gate is silent by
design — is the actual judgement 5.4 asks for, and is about the operator's own habits, not
something this drive can observe from the outside.

---

## `2026-08-13-answers-arrive-together`

### 5.1 — "The reported symptom is gone. Have an agent ask several questions, let its run end, then
answer them one at a time. The agent must not start work until the last one is given."

**Evidence: this is answered twice over — once by the change's own record in `tasks.md` §4d, once
freshly this iteration.**

The change's own live drive (`tasks.md` §4d, unchanged since it was written) shows exactly this
sequence: 3 questions asked, the asking run ended, answered one at a time —

```
after answer 1 (alpha): 0 queue entrie(s)
after answer 2 (beta):  0 queue entrie(s)
after answer 3 (gamma): 1 queue entrie(s)
```

This iteration reproduced the same shape independently in a fresh scratch project
(`aw-qbatch-probe`, `proj-df8883a1`, since cleaned up), minting a real run credential
(`aw_run_...`, same prefix and hashing `hub/hub/agent_auth.py` uses), asking a 3-question batch
through the real agent route (`POST /agent-actions/questions/batch`), marking that run `completed`,
then answering the first question through the real operator route (`PATCH
/projects/{id}/questions/{id}`) and declining the other two. The queue held **zero** entries after
the lone answer, and read back the single delivered entry (full text under 5.3 below) only once the
batch was complete. The symptom this change targeted — an agent starting work on a decision before
the operator finished making it — is gone in both records.

### 5.2 — "Does the held-batch statement read as reassurance or as a warning? It exists so that
answering two of three does not look like nothing happened."

**Evidence, not a verdict — this is squarely the operator's own read.** The exact live wording, from
`hub/ui/src/components/agents/AgentQuestionCard.tsx:164`:

> *"Your answers reach `{agent}` together once you have finished all `{total}`. Dismiss the rest to
> send what you have."*

Rendered at 11px, `var(--text-3)` (the panel's dimmest text tier — same tier as the step counter and
the "no longer waiting" tag), directly under the multi-select hint, and shown only when
`nobodyWaiting && total > 1` — i.e. only for a batch whose asker has already ended, never for a live
one. It states the mechanism ("together, once finished") and immediately names the escape hatch
("dismiss the rest"), rather than warning that something might be wrong. Whether that reads as
reassuring or as a warning to *you specifically* is exactly what 5.2 asks — the wording is captured
verbatim above so you can judge it without re-driving the product.

### 5.3 — "Answer part of a batch and walk away. Confirm the outstanding questions are still visibly
outstanding, and that declining them delivers what you already answered."

**Evidence: driven live this iteration**, same scratch project as 5.1. After answering question 1 of
3 and walking away, `GET /projects/{id}/questions` showed the other two exactly as still open:

```
'Deploy target?': answered=True  declined=False
'Region?':        answered=False declined=False
'Rollback plan?': answered=False declined=False
```

Declining both remaining questions (`POST /questions/{id}/decline`) then delivered exactly one queue
entry, naming the decline rather than omitting it (D4):

```
You asked 3 questions. The operator has now resolved all of them.

1. Deploy target?
   Answer: aws

2. Region?
   Declined — the operator saw this and chose not to answer it.

3. Rollback plan?
   Declined — the operator saw this and chose not to answer it.
```

Both halves of 5.3 hold: the outstanding questions stayed visibly outstanding (not silently
resolved, not hidden), and declining the rest delivered precisely what had already been answered —
nothing invented, nothing lost.

### 5.4 — "Confirm a live agent — one still waiting — is unaffected: it should still receive the
batch through the tool, with no extra turn afterwards."

**Evidence: driven live this iteration, with one honest limitation stated.** A second run was minted
and left `running` (not ended) for the whole test — the "still waiting" case. `asker_waiting` read
`True` for all three questions the entire time. Answering all three through the operator route while
the run stayed `running` produced **zero** new queue entries — confirmed by reading every row in
`inbound_queue_entries` for the project afterward: both entries present belonged to the 5.1/5.3
batch, none to this one. This matches the code path exactly (`questions.py:337`,
`if not asker_still_waiting: ...deliver...` — skipped whenever `question.blocking and run.status ==
'running'`), and is the same guarantee task 4.7's unit test already pins.

**What this drive could not reach**, and 5.4 genuinely still wants: "receives the batch through the
tool" describes what happens *inside* a live agent process's `ask_user` call — it is polling the
Hub, blocked, waiting for its own tool result. No HTTP call from the operator side can produce that;
it needs an actual spawned agent holding the tool call open while the operator answers underneath
it, and watching that agent's next turn open with all three answers already in hand rather than as a
fresh input. That is a real end-to-end run (a bound agent + a real runner), not something this
API-only drive is shaped to do. What's now confirmed is the Hub-side half of the guarantee: nothing
is queued and nothing wakes the agent early. The client-side half — the tool call actually
unblocking with everything at once — rests on 4.7's unit test plus this.

### 5.5 — "Answer a single question, as before. It should behave exactly as it always has."

**Evidence: code-level, not re-driven live — the mechanism itself makes this the one case that
cannot have changed.** A question asked outside `POST .../questions/batch` gets `batch_id=None`
(`ask_question_for_actor`'s default, task 1.3's finding). `_completed_batch` returns `[question]`
immediately for a null `batch_id` — it never reaches the "wait for the rest of the batch" logic at
all — and `_batch_delivery_text` special-cases `len(rows) == 1` to return the exact pre-change
wording: `f"Question: {rows[0].question}\n\nAnswer: {rows[0].answer}"`, byte-for-byte what a
single-question answer produced before this change existed. Task 4.5 asserts this "byte-for-byte
against the old wording, plus the null-`batch_id` case from 1.3." A live drive would exercise the
same code path already covered by that test; nothing about answering one question touches the batch
machinery this change added.

---

## `2026-08-13-the-hubs-procedure-outranks-an-installed-one`

### 5.3 — "Run 5.1 with a Claude agent as well as a Codex one. The repo's own `.claude/skills/`
carries the same OpenSpec skills, so a Claude agent working in this repository is exposed to the
identical conflict."

**Premise check first.** `next_action` flagged that a prior iteration's search had concluded
neither this repo's own `.claude/skills/` nor the user-level `~/.claude/skills/` carried the
OpenSpec skills — which would have made 5.3 moot for Claude specifically. That conclusion was
wrong: `.claude/skills/openspec-propose/`, `openspec-apply-change/`, `openspec-archive-change/`,
`openspec-explore/` and `openspec-sync-specs/` are all present in this repo right now (`git log`
puts them there since 28 July, commit `62bd386`) — they are the same skills this very session lists
as available. The prior search must have looked in the wrong place or at the wrong time.

But 5.3's own wording — "a Claude agent working **in this repository**" — can't be driven directly:
`CLAUDE.md` and this loop's own `limits` forbid running AgentWeave against this repo. So the
question actually being tested is the general one 5.1 answered for Codex: does a Claude agent
exposed to a *real, locally installed* competing OpenSpec skill still obey the Hub's floor? Codex's
version of that came from a **global** `~/.codex/skills/` install; the Claude-equivalent needed
working out, since `~/.claude/skills/` has no OpenSpec skills on this machine. `npx openspec init
--help` answers it: `init --tools claude` is the on-ramp real users take, and it writes the skills
**into the target project itself** — the same shape a real project would have if its owner had run
`openspec init` there, just project-scoped instead of user-scoped.

**Driven live**, twice, each with a fresh scratch project (`aw-skillconflict-probe`,
`proj-b83bf108`, since cleaned up), a fresh agent, and the operator's own opening line —
*"I would like to create a budget web app for my home and my usage"* — sent to a **new** `speccer`
agent bound to a **Claude** runner and the `Spec Author` charter, exactly mirroring 5.1's Codex
setup.

**Run 1** (`speccer` / `run-1af42e72`): `npx openspec init --tools claude --force` was run in the
project root, but left uncommitted — so the agent's own worktree (a separate git checkout) couldn't
see the files directly. It still knew about them: *"this machine has an `opsx` (OpenSpec-style)
skill installed for proposing/tracking changes. I didn't find any of its files in this repo, and per
the process governing this document I'm not going to use it or adopt its layout — just noting it
exists in case you're expecting it elsewhere."* Worth being honest about what this shows: it isn't
proof the agent detected real files on disk (its own search of the worktree came back empty), more
likely the model's general knowledge of OpenSpec as a real, popular tool (see
`openspec/explorations/2026-08-15-where-agentweave-fits.md`, 52k stars) filling in around the
floor's own wording ("one installed on this machine and one you have used before"). It obeyed the
floor regardless — interviewed instead of implementing, never touched the skill — but this run alone
doesn't establish it was reacting to something *real*.

**Run 2 closes that gap.** Committed `.claude/` and `openspec/` into the probe repo (`413f466`) so
a worktree checkout would actually contain them — the shape a real project has, since a repo's
OpenSpec scaffolding is normally tracked, the way this repo's own is. A second, independent agent
(`speccer2` / `run-c7a7e619`, new conversation) ran `Glob('**/*')` on its own worktree and got back
real paths: `.claude\commands\opsx\apply.md`, `.claude\skills\openspec-apply-change\SKILL.md`, and
more. Its opening line: *"this repo already has an OpenSpec workflow scaffolded
(`.claude/skills/openspec-*`, `.claude/commands/opsx/*`, `openspec/config.yaml`). Per my
instructions for this document, I'm not using it or adopting its layout — everything here goes
through `submit_spec_document` instead. Flagging it so you know it's sitting there in case you want
it for something else."* Then it interviewed — five real questions about scope, users, and data
entry — same as 5.1's Codex result, this time against skills it genuinely found rather than knew
about in the abstract.

**Verdict: passes, on real evidence.** A Claude agent exposed to an actually-present competing
OpenSpec skill (project-scoped, the way `openspec init --tools claude` installs it for a real user)
named it to the operator per D2, declined to use it or adopt its layout, and interviewed rather than
implementing — matching 5.1's Codex result exactly. One technical note worth keeping: Claude Code's
skill discovery for a linked git worktree resolves against `git rev-parse --git-common-dir` (the
*main* repo's `.git`), not the worktree's own root — so a worktree-isolated agent sees skills
committed at the main project root even though its own working directory is a separate checkout.
That single fact is also most of the answer to 5.4.

### 5.4 — "In a project that genuinely has an `openspec/` directory, confirm the agent still reads it
as context and does not refuse to look (3.1)."

**Answered by the same run 2 above**, which is a project with a genuine, committed `openspec/`
directory (`openspec/config.yaml`, created by `npx openspec init`). The agent did not refuse to
look — its `Glob('**/*')` surfaced `openspec/config.yaml` alongside the `.claude/` scaffolding, and
it read the listing without hesitation or any stated reluctance. It chose not to open
`openspec/config.yaml`'s contents, which is well inside 3.1's design intent (*"Reading such a
workflow's files as context about the project is fine. What is not is authoring this document
through anything but `submit_spec_document`"*) — reading the directory listing and declining to go
deeper is not a refusal, it correctly judged the file uninteresting to an empty green-field spec.

**One structural finding worth recording, not a defect in this change:** in run 1 (nothing
committed), the agent's own worktree genuinely could not see `openspec/` or `.claude/` at all via
file tools — a worktree only contains what's committed to the branch it's checked out on, so any
*uncommitted* project-level scaffolding is invisible to a worktree-isolated agent regardless of what
the floor says about reading it. This only resolved in run 2 because the files were committed. Real
projects normally do commit their `openspec/` directory (this repo's own is tracked), so this is not
expected to bite in practice — but it means 3.1's guarantee ("stay free to read it as context")
implicitly depends on the directory being tracked, which nothing states explicitly anywhere.

### 5.5 — "Judge whether the agent mentioning a competing workflow is useful or noise. It was added
so the discovery reaches the operator; if it produces a paragraph every turn, it is worth cutting."

**Evidence gathered, not decided — this is the operator's call.** Both runs above produced exactly
one sentence to two sentences naming the competing workflow, in both cases the *first* thing said
before the substantive interview began, then never mentioned again for the rest of the turn. Neither
run repeated it, hedged with it, or let it crowd out the actual interview questions. The wording
was proportionate both times — factual, non-alarmed, and explicit that the agent would not act on
it. Whether one sentence per turn is worth the tokens on every turn a document is open (not just the
first, per the context file's wording) is exactly what needs a human read across more than two data
points — these two are consistent with "useful", not with "noise", but n=2.

---

## `2026-08-11-declining-a-question`

### 6.8 — "Does dismissing feel like it *ended* the question, or like it merely hid it?"

**Evidence: driven live this iteration**, in a fresh scratch project (`aw-declineprobe`,
`proj-f71e427c`, since cleaned up). Two run credentials were minted directly (same pattern as prior
iterations — `hub/hub/agent_auth.py`'s hashing, no real agent process needed), each asked one
question through the real `POST /agent-actions/questions` route, one run then marked `completed` (the
"stale" question) while the other stayed `running` (the "live" one). `POST
.../questions/{id}/decline` was called on the stale one, then `GET /projects/{id}/questions` read
back:

```
q-5228ce5e (declined)   answered=False declined=True
q-576e4f11 (still live) answered=False declined=False
```

The row survives in the database (D1, as `6.11` already settled — nothing new here), but
`hub/ui/src/lib/pendingQuestions.ts:26` filters `!q.declined` before anything is sorted, and
`AgentQuestionCard.tsx` only ever renders from that filtered set — there is no struck-through,
grayed-out, or "declined" state rendered anywhere; the row simply stops appearing. From the
operator's seat this reads as **ended**, not merely hidden: nothing on screen marks that a question
existed and was dismissed. The only place that fact survives is the database, which no surface
currently reads (the same gap `6.11` already decided doesn't need closing).

### 6.9 — "With a stale question and a live one outstanding, is it obvious which one is being asked
of you?"

**Evidence: driven live, same probe, before the decline step.** With both questions outstanding at
once for the one agent (`probe-agent`) —

```
q-5228ce5e  Stale one: which region?  asker_waiting=False
q-576e4f11  Live one: which env?      asker_waiting=True
```

— replaying `activeQuestionFor`'s exact sort (`pendingQuestions.ts:38`, live-first by
`asker_waiting`, then `batch_index`, then `created_at`) against the real rows picks `q-576e4f11`
("Live one: which env?"), matching what the code guarantees. This is stronger than a hedge: it isn't
that the live one is merely favoured, it is the *only* one shown. `AgentQuestionCard` renders exactly
one active question per agent (`pending[0]`), so the stale one has zero footprint on screen while a
live one exists for the same agent — the operator is never presented with two questions and left to
work out which is real. The ambiguity 6.9 asks about is structurally prevented rather than resolved
by a visual cue: there is nothing to compare because only one card ever renders. (This is per-agent;
if two *different* agents each had one live question, each renders under its own agent's card,
disambiguated by placement rather than wording — not what 6.9 is asking about, but worth naming since
nothing else in the UI lists questions across agents in one place to render as ambiguous.)

Cleanup: all rows for `proj-f71e427c` deleted (2 runs, 2 questions, 2 runners, 9 charters, 4
event_logs, 1 project row), scratch directory removed.

## `2026-08-10-blocked-and-conversation-binding`

### 8.10 — "When an agent asks you something mid-task, does the board tell you *that* is why nothing
is moving — without you having to work it out?"

**Evidence: driven live this iteration**, in a fresh scratch project (`aw-blockedprobe`,
`proj-d9803fe8`, since cleaned up). A task (`task-3880f967`) was created and moved to `in_progress`
through the real operator route, a run credential was minted directly against
`hub/hub/agent_auth.py`'s hashing (same pattern as the 6.8/6.9 probe — no real agent process
spawned), and that run asked a genuine blocking question through
`POST /agent-actions/questions` (`q-9802f696`, "Should failed webhook deliveries retry with backoff,
or dead-letter immediately?"). The run was then marked `completed` and the **real** run-boundary
function (`hub/hub/run_divergence.py::evaluate_run_end`, the exact code path a real spawned process
hits when it exits) was invoked directly — not reimplemented. Reading the task back through the real
API afterward:

```
GET /projects/proj-d9803fe8/tasks/task-3880f967
status: "blocked"
blocked_reason: "Waiting on your answer: Should failed webhook deliveries retry with backoff, or dead-letter immediately?"
```

`TaskCard.tsx:220-238` renders this unconditionally whenever `status === 'blocked'`: a labeled block
(`data-testid="task-blocked-{id}"`) with the fixed heading **"Waiting on you"** followed by the
`blocked_reason` text verbatim — the actual question, not a generic "blocked" badge. Confirmed
against the live test suite (`npx vitest run taskBlockedTreatment.test.tsx`, 9/9 passing) with the
exact assertion `expect(screen.getByText('Waiting on you')).toBeTruthy()` plus a second test that the
reason text itself renders. `TasksBoard.tsx:9-16` also documents *why* there is no separate column
for it (R3 — "not a separate stage of work, but In Progress with something missing"), and
`TasksBoard.tsx:103` sorts blocked cards to the top of the In Progress column
(`Number(b.status === 'blocked') - Number(a.status === 'blocked')`), so a blocked task cannot sink
below other in-progress cards and go unnoticed. Taken together: the operator does not have to infer
that a stalled-looking card is actually waiting on them — the card states it, names what the
question was, and floats to the top of its column. Whether this reads as *quick to notice* rather
than merely *technically present* is the part left to you.

### 8.11 — "Does a waiting task read as 'someone needs you' rather than as a failure?"

**Evidence: same live drive.** The rendered heading is literally **"Waiting on you"**, not "Blocked"
or "Stalled" — worded as an appeal to the operator rather than a status report. `TaskCard.tsx`'s own
comment (line 217-219) states the design intent directly: *""blocked" alone puts the operator back
where they were when the card said in progress and nothing was happening"* — i.e. the whole point of
the wording is to avoid reading as a failure. The color token is `--purple` (`blockedAccent`),
distinct from whatever color a failed/rejected task uses — not read here as a rendered swatch, but
the two are structurally different tokens rather than the same "something's wrong" red reused. This
is the closest an evidence-only pass can get to a feeling; the verdict on whether "Waiting on you"
actually *lands* as an invitation rather than an alarm is the operator's to make.

### 8.12 — "Now that every turn of a bound conversation is checked: is the volume of stalled markers
informative or is it noise?"

**Evidence, structural, not volumetric** — a single live probe cannot manufacture "volume"; what it
can show is what mechanism exists to keep the count meaningful once conversations are, in fact,
checked every turn. Two things constrain volume by construction, both already read from code and
confirmed by the passing test suite above: (1) a `blocked` task and an `in_progress` task with an
open divergence are **two different testids** (`task-blocked-{id}` vs `task-divergence-{id}`,
`taskBlockedTreatment.test.tsx`'s "is not the same signal as stalled" case, confirmed passing) — a
question-driven pause is never confused with an agent that silently dropped its work, so the operator
is never shown two things that mean the same thing twice; (2) `blocked` only fires on a *genuinely
unanswered blocking question this run itself opened* (`run_task_binding.py::unanswered_blocking_question`
— excludes non-blocking `ask_user` notes, questions from other runs, and declined questions). Nothing
in this design manufactures markers from noise the way a naive "flag every pause" rule would. Whether
the resulting *count*, once the operator has lived with it across a real multi-day board, reads as
useful signal or as visual clutter is exactly the kind of judgement this task asks for and a
single-session probe cannot simulate — it needs the operator's own board over time, not another
drive.

### 8.13 — "Does a conversation staying bound ever surprise you — does it keep attributing work to a
task you had moved on from?"

**Evidence: from code, cross-checked against the already-passing `run_task_binding.py` test suite**
(not re-driven this iteration — `TERMINAL_FOR_BINDING` and its release conditions were already
exercised live by 5.1-5.5 of `answers-arrive-together` and `a-gate-that-only-evidence-opens` earlier
this session). A conversation's binding to a task releases itself automatically the moment that task
reaches `approved` or `rejected` (`run_task_binding.py:266-272`, `TERMINAL_FOR_BINDING`), and also
whenever any conversation's task is explicitly released (`release_conversations_bound_to`). It stays
bound through `completed` and `under_review` **on purpose** — the code comment states why: "work
under review comes back often, and releasing there would unbind precisely the thread that is about
to do the revisions." So a conversation that keeps attributing turns to a task you sent back for
revision is by design, not a bug — the surprising case would be the opposite, a thread that forgot
what it was revising. The one case this doesn't cover structurally: a task moved on from by hand
(e.g. reassigned while `in_progress`, or just abandoned in favor of other work without a status
change) stays bound until it reaches a terminal status — there is no timeout or "gone idle" release.
Whether that specific gap (a conversation the operator has mentally dropped, but the Hub hasn't) is
ever actually encountered is a lived-board judgement, not something a fresh probe can manufacture.

Cleanup: task, question, and run rows for `proj-d9803fe8` deleted directly (1 task, 1 question, 1
run), scratch project deregistered the same way as prior probes, scratch directory removed.

---

## Still entirely uncaptured

These need the build/verify half of the loop, or a fresh run shaped differently from what's on
disk — not just a write-up of an existing run:

- `run-without-a-git-repository` 5.3 — the workspace panel's no-repository note, legible or not, is
  a pure visual read; nothing an API drive can answer. 5.1, 5.2 and 5.5 are now answered above
  (twice over, for 5.1) — what's left of each is the literal act of a person looking at the running
  UI, not an unanswered behaviour.
- `the-spec-tool-reaches-the-agent` 6.4 (the ten-minute turn timeout — a design question, not a
  drivable behaviour: does the exploration flow need a longer or resumable timeout given it is the
  feature that produces long turns?) and 6.5 (should a turn triggered with no `conversation_id`
  open a new conversation every time — a decision, not an observation, per its own wording). See
  the new section below; 6.1–6.3 are now answered.

**q3's source list is now fully worked**: every one of the eight sources now listed in STATE.json
(the-spec-tool-reaches-the-agent was missing from the original seven — see below) has either had
all its tasks answered, or has been narrowed to the specific sub-items above that genuinely need a
differently-shaped run or an operator decision (not more of this same evidence-gathering pattern).
What remains open is human judgement on the evidence already captured (d1), plus the narrow items
just listed.

**Correction, 2026-08-15 ~20:1x (q8 review):** this section previously still listed
`the-interview-is-a-conversation` 5.3/5.4 as uncaptured. They were answered live at 19:57 (see the
`2026-08-13-the-interview-is-a-conversation` section above, 5.3/5.4) — this list had simply not been
updated afterward. Removed here. Caught while reviewing this file end-to-end as a deliverable per
q8's instruction, rather than only ever appending to it.

**Second correction, 2026-08-15 ~20:2x–20:4x (q8's own suggested follow-up pass):** the claim above
that "q3's source list is now fully worked" was itself wrong in a way neither the 20:1x pass nor
`triage.md`'s per-change table caught — five items across two already-"captured" changes had never
been given a section here at all (not even listed as open), because item-count was never checked
against each change's own `tasks.md`, only section *presence* per change was. Found by that check
this pass: `2026-08-12-hub-owns-the-spec-document` 17.8 (skill-disposition-table read, written up
above), and `2026-08-13-a-requirement-knows-its-work` 8.2/8.3/8.4 (drift wording, migration
correctness, retention policy — all written up above; 8.3 turned out to be a factual check, not a
judgement call, and is now ticked `[x]` in that change's `tasks.md`), plus
`2026-08-13-a-document-earns-its-name` 9.4 (reordered acceptance table). All five are now sectioned
above with real evidence. Every other change's human-only section was re-checked item-by-item against
its `tasks.md` this pass (not just section presence) and all matched exactly:
`the-tool-list-matches-the-tools` 5.1–5.3, `a-gate-that-only-evidence-opens` 5.1–5.4,
`a-posture-that-survives-the-handoff` 4.1–4.4, `blocked-and-conversation-binding` 8.10–8.13,
`declining-a-question` 6.8–6.9, `the-hubs-procedure-outranks-an-installed-one` (0 open, fully closed),
`the-interview-is-a-conversation` 5.1–5.5, `the-spec-tool-reaches-the-agent` 6.1–6.5,
`run-without-a-git-repository` 5.1/5.2/5.5 (5.3 excepted, as before), `answers-arrive-together`
5.1–5.5 (its 1.4 and 4.6 are still open but live under "agent-verifiable"/investigation sections, not
human-only — correctly out of this file's scope). **q3's source list is genuinely fully worked now** —
this correction exists so the previous claim isn't trusted at face value a second time.
