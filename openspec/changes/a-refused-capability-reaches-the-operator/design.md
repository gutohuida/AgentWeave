# Design — a refused capability reaches the operator

**R1, 2026-09-18.** Every file:line below was read in this round. F376's *diagnosis* is not
re-derived here — DIRECTION.md 2026-09-18 forbids that and the measurements stand
(`scripts/drive/FINDINGS.md`, F376 and the D-1 addendum after F380). What is derived here is the
**repair**.

## Round 1 — the code as it is

- `hub/hub/api/v1/jobs.py:32-51` — `_require_agent_job_allowance`. Order matters and does not
  change: `agent is None and run_id is None` returns (an **operator** call carries neither header,
  so nothing below touches the operator's own path); incomplete attribution → 403; stale attribution
  → 403; then `project.allow_agent_jobs` false → 403 *"Scheduled work from agents requires operator
  approval or an enabled allowance"*. **Only that last branch is in scope.**
- Callers of the gate: `:568`, `:847`, `:1163`, `:1294` — `create_loop`/`create_flow` (POST /jobs),
  `update_job`, `archive_job`, `toggle_job`/`run_job`. One branch repairs all of them.
- `hub/hub/db/models.py:79` — `allow_agent_jobs`, `default=False, server_default="0"`.
- Its **only** writer anywhere in `hub/hub` is `PATCH /queue/settings`
  (`hub/hub/api/v1/inbound_queue.py:98`), operator-authenticated. **No agent-facing route or MCP
  tool can set it** — checked by grepping every `allow_agent_jobs` occurrence outside migrations.
  This is the fact that decides D4.
- `hub/ui/src/components/environment/ProjectSettingsPanel.tsx:146` — the only control.

## D1 — the record is a question of record, not a permission request

**Decision.** The refusal opens a row in `questions` through `ask_question_for_actor`
(`hub/hub/api/v1/questions.py:234`), not a `PermissionRequest`.

`permission_requests` looks like the obvious home — the sentence says *"approval"*, and
`hub/hub/operator_direction.py` already turns a route's refusal into a card, an SSE event and a
409 the caller polls. It is the wrong home, and the reason is in that module's own design notes and
in the sweep code:

| | `permission_requests` | `questions` |
|---|---|---|
| Lifetime | **expires**: the adapter waits `AW_DECISION_TIMEOUT` (120s, `mcp_server.py:927`) then `POST`s `/expire` (`:1512`); the run's end sweeps anything still pending (`permission_requests.py:22`, joined to the run-end transaction) | never expired; `answered` is a boolean nobody sweeps |
| Where the operator sees it | inside one agent's output panel (`AgentOutputPanel.tsx:1026`) | a top-level destination (`App.tsx:382` → `QuestionsPanel`) |
| A late answer | cannot exist — the row is gone | **queued and the agent woken** (`questions.py:121` `deliver_batch_if_complete`, `:179` the wake tail, `turn_scheduler.schedule_agent`) — the whole point of the archived change `a-late-answer-is-delivered` |

F376's harm was *the operator came back to nothing*. A record that cannot outlive the turn cannot
repair that, so the decisive property is lifetime, and only one of the two rows has it.

**Read and confirmed in this round, because the whole design rests on it.** `answer_question`
(`questions.py:433-441`) queues the answer whenever the asker is not still waiting, and
`_asker_still_waiting` (`:48`) is true only for a **blocking** question whose wait has not ended and
whose run still lives. So a **non-blocking** question — which is what this change opens — always
takes the queued-and-woken path; the code says so in as many words: *"A non-blocking question still
needs this, and so does a blocking one nobody is waiting on any more: nothing is there to receive
it."* `deliver_batch_if_complete` itself has no waiting check at all (`:121-169`), and
`announce_queued_answer` (`:173`) ends in `schedule_agent`, whose wake is explicitly documented as
safe for an agent whose run is still live.

**And the delivered entry enters at `hop_depth=0`** (`questions.py:154`). That is not incidental to
F376: the finding measured the whole build running as one chain off the operator's 17:36 message,
hand-driven messages inheriting `+1`, and the chain dying at hop 7 against a budget of 6. An answer
that resumes the agent at depth zero is the same reset a flow firing gets
(`scheduler.py:3111`, `:3443`) and the opposite of what a relayed message would get.

**This is not a criticism of `operator_direction.py`.** Turn-scoped is right for *"may this agent
run this command now"*: an answer that arrives after the turn has nothing to authorise. It is wrong
for *"may agents schedule work in this project"*, which is true or false independently of any turn.

## D2 — the agent does not wait, and that is the design

DIRECTION.md said the answer to *what happens to the agent's turn while it waits* decides whether
raising a request is worth doing at all. The answer here: **there is no wait.**

- The route returns **403** with a typed body — `code: "project_setting_blocks_capability"`, the
  setting's name, its current value, the `question_id`, and one sentence saying the operator has
  been asked and will answer into the agent's queue.
- **403, not 409.** 409 + `operator_direction_required` is the *poll-and-retry* protocol
  (`operator_direction.py`, `mcp_server.py:845`), and it presumes an answer inside the turn. Using
  it here would tell an agent to poll a decision that may arrive after its run has ended, i.e. to
  block until a timeout that changes nothing. The refusal is a genuine refusal *now*.
- The agent is told what to do instead: do other work, or end the turn; the answer arrives as input.
  Nothing requires it to ask its own question about the same setting — and if it does, the operator
  gets two cards, which D5 bounds for the Hub's own copy but cannot prevent for the agent's.
- **No new adapter wait.** `archive_job` wraps its call in `_await_decision`
  (`mcp_server.py:840-861`); nothing analogous is added to the five job tools here. This keeps the
  adapter thin, which is a requirement rather than a preference
  (`openspec/specs/agent-capability-plane/spec.md:107`, *"MUST NOT hold a governance or waiting rule
  that the contract does not itself impose on every caller"*), and it means an HTTP-only agent gets
  the identical behaviour with no protocol of its own.

## D3 — what the operator is actually being asked

`openspec/specs/agent-capability-plane/spec.md:915-926` already states the plane's two-class theory:
scheduled jobs need a standing allowance **because a job invokes a model repeatedly, so an agent
creating one commits spend the operator did not authorise per occurrence**; tasks, messages,
questions and evidence need none.

So per-call approval of a `create_flow` is not a smaller version of the allowance — it is a
*different and larger* grant, and the shipped permission card (`tool_name`, `tool_input`) says
nothing about recurring spend. The question the Hub must put is the one the setting represents:
**may agents schedule work in this project?** That is also the question the operator can answer
without reading the call's arguments, which matters because they were leaving.

## D4 — the answer does not flip the setting, deliberately

`allow_agent_jobs` has exactly one writer and it is operator-authenticated (D1's list). Answering
the question therefore does **not** enable the allowance; the question names where the operator
does that (Environment › Settings, `ProjectSettingsPanel.tsx:146`) and its options are
*"Enabled it — go ahead"* / *"Leave it off"*.

Rejected: making the answer apply the setting. It needs either a new column on `questions` carrying
an effect (a migration, and a general effect-hook on an inbox that deliberately has none) or a new
`capability_requests` table with its own decide route and its own card — a second pending-decision
surface for the operator to learn, which `operator_direction.py` explicitly refused to build for the
same reason. Worse, a toggle inside the card would be **a second control for one setting**, and
`the-controls-that-gate-collaboration-are-visible` (F379, DIRECTION.md's item 2) is the change that
owns that surface. Two controls for one setting is how they diverge.

**Follow-up, recorded not built:** one-click enable belongs in F379's change. This change is what
makes the refusal reach a person; that one is what makes answering it one click.

## D5 — one card per project, and a no is a no

- **Dedupe.** Before opening, look for a question for this project, with this change's stable
  question text, where `answered` is false. If one exists, open nothing and return its id. F376's
  run made 21 runs and 20 fallback messages; without this the inbox gets one card per attempt.
- The text therefore **must not name the requesting agent** (the row's `from_agent` already does) or
  the call's arguments, or the dedupe key varies and the cards multiply.
- **A negative answer stops the asking.** If the most recent such question is answered and its
  `answer_labels` contain the *"Leave it off"* label (or it was declined), open nothing: refuse with
  the honest sentence and no new card. Re-asking after a no is the failure
  `operator_direction.py`'s denied branch already names — *"this is an answer rather than a timeout:
  do not ask again for the same thing."* `answer_labels` is an existing column
  (`db/models.py:950`), so this needs no schema change.
- **Known limit, stated not hidden:** the answer wakes `from_agent`, the agent that was refused
  first. A second agent refused while the card was open is not woken by the answer; its next call
  simply succeeds, because by then the gate passes. Recorded in the spec delta as a scenario so a
  later round cannot mistake it for an oversight.

## D6 — the refusal's own wording

Today: *"Scheduled work from agents requires operator approval or an enabled allowance."* It is
false in both halves — no approval is requested, and *"an enabled allowance"* names nothing the
agent can find. Replaced by a sentence that names the setting, its value, that the operator has been
asked, and that an answer will arrive as a message. `mcp_server._readable_detail`
(`mcp_server.py:124`) surfaces `message` out of a dict detail, so an agent that only ever sees the
sentence still sees the whole protocol — the same reason `operator_direction._direction_required`
carries both the sentence and the id.

## D7 — the rule is the contract's

The record is opened by the **route**, inside the session the gate already holds. The MCP adapter
changes only its prose: the five job tools' docstrings, and each `_Operation`'s `http_note` in
`hub/hub/api/v1/agents.py` (the same place `archive_job`'s protocol is described, `:1276-1289`).
Behaviour is identical on both access paths because only one of them holds any of it.

## D8 — generality, without widening the blast radius

`hub/hub/refused_capability.py` takes what the sentence and the card both need: the setting's name,
its current value, what enabling it would allow, where the operator changes it, and the attribution
(`project_id`, `agent`, `run_id`). F378 — `request_agent` refused because `project_sessions` holds
zero rows on every project on the Hub — is the same shape and is the intended second caller, but
**it is not called from here in this change**; DIRECTION.md defers that repair (and *retire* is a
live option for it). The requirement is written for the shape; the scenarios pin the one caller.

## D9 — two traps a later round must not fall into

1. **Do not reuse the "unasked question" surface.** `openspec/specs/agent-capability-plane/spec.md:281`
   still requires that a turn ending on an unasked question be surfaced to the operator. That
   detector was **dropped in migration `0082` (2026-08-20)** and `CLAUDE.md` forbids reintroducing
   it. The spec text is stale; this change neither uses nor repairs it. Flagged here so a round does
   not propose building on a mechanism that no longer exists.
2. **Do not assume the gate fires for the operator.** It returns early when both headers are absent
   (`jobs.py:39`), which is why D-1's reproduction needed a real bound agent turn rather than a
   plain API call. A test that calls the route without agent attribution proves nothing about this
   change (the F190 shape: green for a month while the behaviour could not fire).

## Rounds

- **R1, 2026-09-18** — this document. Rejected (a) on lifetime and on what the operator would be
  approving; adopted (b)'s honest sentence as half; chose the question of record.
- **R2** — owed. Re-derive independently against `jobs.py`, `questions.py`, `permission_requests.py`
  and `mcp_server.py`. The claims most worth attacking: that no sweep touches `questions`; that a
  403 with a dict detail reaches an MCP agent as a readable sentence; that `blocking=False` is right
  (it is what routes the answer down the queued path — but check what it costs on the operator's
  card, since `blocking` is also what the panel reads for urgency); and whether opening a question
  inside the gate's session is safe at all four call sites (`ask_question_for_actor` **commits**).
  The late-answer delivery claim is already read and quoted in D1 — re-read the code, not the quote.
- **R3** — owed. Independent again. If it changes nothing, it must say so.
