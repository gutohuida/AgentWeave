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

## Still entirely uncaptured

These need the build/verify half of the loop, which was not reached before the session handed over:

- `a-gate-that-only-evidence-opens` 5.1–5.4 (refusals, demotion, `contract`, gating at `approved`)
- `answers-arrive-together` 5.1–5.5 (needs a batch of questions and a run that ends mid-batch)
- `a-posture-that-survives-the-handoff` 4.1–4.4
- `the-hubs-procedure-outranks-an-installed-one` 5.3–5.5
- `blocked-and-conversation-binding` 8.10–8.13
- `declining-a-question` 6.8–6.9
- `run-without-a-git-repository` 5.1–5.5 (needs a non-repository project — cheap to set up)
- `the-interview-is-a-conversation` 5.1–5.5 (**mostly answerable from this run's turn 1** — the
  next iteration should write these up from `out-e058d01e` rather than re-driving)
