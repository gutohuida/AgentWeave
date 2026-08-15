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

## Still entirely uncaptured

These need the build/verify half of the loop, or a fresh run shaped differently from what's on
disk — not just a write-up of an existing run:

- `a-gate-that-only-evidence-opens` 5.1–5.4 (refusals, demotion, `contract`, gating at `approved`)
- `answers-arrive-together` 5.1–5.5 (needs a batch of questions and a run that ends mid-batch)
- `the-hubs-procedure-outranks-an-installed-one` 5.3–5.5
- `blocked-and-conversation-binding` 8.10–8.13
- `declining-a-question` 6.8–6.9
- `run-without-a-git-repository` 5.3 — the workspace panel's no-repository note, legible or not, is
  a pure visual read; nothing an API drive can answer. 5.1, 5.2 and 5.5 are now answered above
  (twice over, for 5.1) — what's left of each is the literal act of a person looking at the running
  UI, not an unanswered behaviour.
- `the-interview-is-a-conversation` 5.3 (needs a run with a real either/or fork) and 5.4 (needs an
  agent with no charter bound) — 5.1, 5.2, 5.5 are now answered above.
