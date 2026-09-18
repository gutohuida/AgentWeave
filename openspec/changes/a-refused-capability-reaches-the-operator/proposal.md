# Proposal — a refused capability reaches the operator

**Round 1, 2026-09-18; amended by Rounds 2 and 3, 2026-09-18** (day window,
`.claude/autonomous/2026-09-18-day-log.md`). Findings: **F376 (A)**, with **F378 (B)**'s refusal
shape. **The three rounds `CLAUDE.md` requires are done; nothing here is implemented yet.**

R2 re-derived the whole argument against the code and left the decision below standing: the record
is still a question of record, the refusal is still a 403 that does not wait. It changed one detail
that the round existed to find — the record must carry **no run and no conversation**, because
stamping the refused run's conversation on it would make the conversation rail and a drained loop
both report a run as *waiting on the operator* while it carried on working (design **D10**). It also
measured what `blocking=False` costs on the operator's panel (**D11**) and found that
`QuestionCreate` makes `options`, `header` and `multi_select` mandatory, which R1's task list would
have failed on (**D12**).

R3 re-derived it again and the decision still stands — **and two of the tasks under it were wrong in
a way tests would not have caught.** First, the rule that was supposed to stop the Hub re-asking
after a *no* keyed on `answer_labels`, and **that column is empty for every typed answer**: both
surfaces that answer a question send the labels only when the operator typed nothing
(`AnswerForm.tsx:33-38`, `AgentOutputPanel.tsx:934-942`), so an operator who wrote *"no, leave it
off"* would have been asked again. The dedupe no longer reads the answer's polarity at all — a
resolved record stops the asking and the refusal quotes what the operator actually said (design
**D13**). Second, **there is no `update_job` MCP tool**: the tools that reach this gate are
`create_job`, `create_loop`, `create_flow`, `toggle_job`, `run_job` and `archive_job`, and
`create_job` — the plainest of them — was named in neither earlier round (**D7**). R3 also narrowed
D8's claim that F378 can reuse this helper (F378's blocking state is an empty table with *no place
the operator changes it*, so three of the signature's parameters have no truthful value there),
established that the record's id has to be in the refusal's **sentence** because nothing on this
surface reads the structured body (**D6**), and recorded two measured costs rather than repairing
them from inside this change (**D13**, **D14**).

## Why

An agent capability refused because of project-level state the agent cannot change is today a
**dead end that no operator surface ever shows**. Measured, twice:

- **F376.** The operator said *"if it's not ready please create it … I'm leaving for a little bit"*.
  The Architect called `create_flow` at 17:37:45 and got
  `403 Scheduled work from agents requires operator approval or an enabled allowance`. Thirty-seven
  seconds later it fell back to hand-driven `send_message` — 20 of them. `permission_requests` held
  **zero rows** for the project; no card, no event, nothing waiting on the operator's return. The
  run cost $26.81 across 21 runs and **0 of 32 tasks reached `approved`**.
- **D-1, 2026-09-18** (`scripts/drive/FINDINGS.md`, the addendum after F380). Reproduced on the
  trial Hub `:8010`, a fresh project, one real `claude-haiku-4-5-20251001` turn: the refusal's exact
  sentence in the transcript, and `select count(*) from permission_requests where agent = …` = **0**.
  Not specific to `LoopEngine_2` or `:8000`.

Two things are wrong at once and they are separable:

1. **The sentence is false.** *"requires operator approval"* names an approval path that is never
   opened. The agent is told to wait for something nobody was asked for.
2. **The operator is never told.** The refusal exists only inside the agent's own transcript, where
   nothing reads it. The state that blocks the work — `projects.allow_agent_jobs`, `default=False`
   (`hub/hub/db/models.py:79`), so this is what *every new project* gets — is one the operator can
   change in five seconds and was never asked about.

## What changes

When the Hub refuses an agent capability because of project-level state the agent cannot change, it
**opens a question of record** — the durable operator inbox the product already has — naming the
setting, its current value, what enabling it would allow, and where the operator changes it. The
refusal returned to the agent names the same facts and **stops promising an approval**, telling the
agent instead that the operator has been asked and that the answer will arrive as a message.

Scoped to one refusal in this change: `_require_agent_job_allowance`'s `allow_agent_jobs` branch
(`hub/hub/api/v1/jobs.py:44-51`). It guards four routes — `create_job`, `update_job`, `archive_job`
and `run_job` (`jobs.py:568`, `:847`, `:1163`, `:1294`) — reached by six MCP tools: `create_job`,
`create_loop`, `create_flow`, `toggle_job`, `run_job` and `archive_job` (**R3**, design D7; there is
no `update_job` tool — that is the PATCH route, reached by `toggle_job`). The helper is written in a
shape F378's repair can reuse, but **R3 narrowed that claim**: F378's blocking state is an empty
table with no writer, so its refusal needs a control to point at before this signature fits. That
repair is **not** in this change (DIRECTION.md 2026-09-18 defers it).

## The decision, and the one that was rejected

DIRECTION.md 2026-09-18 named two repairs and told R1 to argue between them rather than assume.
**Neither survives as written.** The argument is in `design.md` D1–D4; in short:

- **(a) Raise a `permission_requests` row** so the existing sentence becomes true. **Rejected**, on
  two measurements. First, that row is **turn-scoped by design**: the adapter's wait is
  `AW_DECISION_TIMEOUT`, 120s by default, and it then `POST`s `/expire`
  (`hub/hub/mcp_server.py:1512`, `:1564`); the run's end sweeps whatever is still pending
  (`hub/hub/permission_requests.py:22`), joined to the transaction that ends the run. F376's
  refusal was at 17:37:45 and the ledger deadlocked at 17:56 — **18 minutes** in which a
  120-second card had already expired, and the operator's own *"a little bit"* was
  open-ended. A card that dies 120 seconds after the refusal, and again
  when the run ends, reaches them exactly as well as today's nothing — *(a) makes the sentence true
  without repairing the harm the finding measured.* Second, the card is rendered only inside the
  agent's own output panel (`AgentOutputPanel.tsx:1026` → `PermissionRequestCard`), not on any
  top-level destination. And approving one `create_flow` call grants **recurring model spend**,
  which is the very reason this capability is gated by a standing allowance rather than
  per-occurrence approval (`openspec/specs/agent-capability-plane/spec.md:920`) — the shipped card's
  copy does not say that, so the operator would be answering a question other than the one asked.
- **(b) Tell the truth and stop there.** **Adopted in part, rejected as sufficient.** The honest
  sentence is necessary and is half of this change. It is not enough on its own: nothing reaches the
  operator's screen at all, so the only path left is the agent relaying the refusal in prose — and
  F376 is the measurement of an agent not doing that. It sent 20 messages instead.
- **(c) What this change does.** A **question of record** (`questions`, via
  `ask_question_for_actor`, `hub/hub/api/v1/questions.py:234`) instead: never expired, rendered on a
  top-level destination (`App.tsx:382` → `QuestionsPanel`), and already carrying a shipped
  **late-answer delivery** path that queues the answer and wakes the agent *after its run has ended*
  (`questions.py:121`, `:179`; the archived change `a-late-answer-is-delivered`). The decision put to
  the operator is therefore the one the setting actually represents — *may agents schedule work in
  this project* — not one call's arguments.

**What happens to the agent's turn while it waits** — the question DIRECTION.md said decides whether
this is worth doing: **it does not wait.** The call is refused immediately, the turn carries on or
ends, and the operator's answer arrives later as queued input that wakes the agent. No new blocking
call, no new adapter-side wait, and therefore nothing that could make the MCP adapter thicker than
the contract (`openspec/specs/agent-capability-plane/spec.md:107`).

## Capabilities

- `agent-capability-plane` — two ADDED requirements: the durable record, and the refusal's honesty.

## Impact

- `hub/hub/api/v1/jobs.py` — the allowance branch of `_require_agent_job_allowance` only.
- **new** `hub/hub/refused_capability.py` — opens the record, dedupes, composes the refusal.
- `hub/hub/mcp_server.py`, `hub/hub/api/v1/agents.py` — tool and contract descriptions of the
  refusal, for the six tools R3's table names. No behaviour.
- Tests: `hub/tests/test_refused_capability.py` (new), `hub/tests/test_agent_actions_governed.py`.
- **No migration. No schema change. No UI change.** The one-click enable is deliberately left to
  `the-controls-that-gate-collaboration-are-visible` (F379), which owns that surface — see design D4.
- Blast radius shares no file with F379's change (`hub/ui/src/components/`) or F377/F378's.
