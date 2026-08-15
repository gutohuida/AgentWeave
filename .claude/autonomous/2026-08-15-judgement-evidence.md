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

---

## `2026-08-13-a-requirement-knows-its-work`

### 8.1 — "Is the coverage state legible?"

**Artefact:** 8 requirements minted, all `active`, each with a readable key slug —
`FR-1 deadline-replaces-urgent-flag`, and so on. None has evidence yet, so every one is at the
"not started" end.

**Partially answered.** A document with requirements in *several* states needs the build half of
the loop, which was not reached. **Still open.**

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

**Still open, genuinely.** Checked the whole of `proj-ff695d96` (`aw-loop10`), not just this run:
zero rows in `questions`, and no `agent_outputs` row for any agent (`speccer`, `builder`,
`verifier`) contains an `ask_user` tool call across the project's entire history. This project's
notify-window spec never presented a fork sharp enough to trigger one — consistent with the
standing G5 observation logged elsewhere this session (the operator's own non-goal: "the AI should
answer or not deliberately based on the test"), but it means this specific task needs a *different*
run, one that hits a real either/or, to close. Not answerable from data already on disk.

### 5.4 — "With no charter bound, is the interview still recognisable?"

**Still open — this run doesn't test it.** `agents` confirms `speccer` in `proj-ff695d96` has
`charter_id = 'charter-4495f995'` set — a charter *is* bound, so `run-d3b6f7c5` shows the interview
with a charter in place, not without one. Needs a project with an agent that has no charter bound at
all (cheap to set up: create one, run the exploration turn, compare).

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

## Still entirely uncaptured

These need the build/verify half of the loop, or a fresh run shaped differently from what's on
disk — not just a write-up of an existing run:

- `blocked-and-conversation-binding` 8.10–8.13
- `declining-a-question` 6.8–6.9
- `run-without-a-git-repository` 5.3 — the workspace panel's no-repository note, legible or not, is
  a pure visual read; nothing an API drive can answer. 5.1, 5.2 and 5.5 are now answered above
  (twice over, for 5.1) — what's left of each is the literal act of a person looking at the running
  UI, not an unanswered behaviour.
- `the-interview-is-a-conversation` 5.3 (needs a run with a real either/or fork) and 5.4 (needs an
  agent with no charter bound) — 5.1, 5.2, 5.5 are now answered above.
