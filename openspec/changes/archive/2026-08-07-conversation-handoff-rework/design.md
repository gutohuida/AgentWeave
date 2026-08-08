## Context

The Handoff control does not work, and the exploration established *why* in a way that changes the
solution rather than just confirming the problem. Findings are in
`openspec/explorations/2026-08-08-handoff-behaviour.md`; the short version is that the prompt names
an `aw-checkpoint` skill AgentWeave never installs, pointed at
`.agentweave/shared/checkpoints/` — a path outside the agent's sandbox. Both runtimes only appeared
to work because this operator happens to have a personal handoff skill installed
(`~/.claude/skills/`, `~/.agents/skills/`). The competence was borrowed, not built.

**The reframe that drives this design.** `/handoff` exists in a terminal because `/clear` destroys
the only copy of the transcript; the file on disk is the sole survivor. That assumption does not
hold here. A conversation is 1:1 with a provider session (`agent_trigger.py:289` resumes
`conversation.provider_session_id`; `runner_commands.py:206` is `--resume`), so a new conversation
starts the CLI blind — but the Hub still holds every operator input, tool call, output, and the
agent's own `thinking` entries.

Nothing is lost at a handoff. The artifact is therefore **compression across a provider-session
boundary**, not preservation. That is a different problem, and it is solvable Hub-side.

Recent work supports the split this design makes. Anthropic's context-engineering guidance is to
keep architectural decisions, unresolved bugs and implementation details while discarding redundant
tool output, and to tune a compaction prompt on real traces — recall first, then precision.
Factory.ai's probe evaluation found **artifact tracking is the weakest dimension of every
compression method tested** (2.19–2.45 / 5), that structure forces preservation, and that anchored
iterative summarisation beats regeneration. ARC showed that an append-only observation store with
stable addresses and on-demand recall recovers content losslessly (99.0% vs 79.6% for RAG).

The Hub is unusually well placed for all three: it already auto-commits every turn
(`worktrees.py:243-258`), so the file list Factory's summarisers kept dropping is a *diff*, not a
guess; and `agent_outputs` is already an append-only observation store with stable ids.

## Goals / Non-Goals

**Goals:**

- Replace the file-on-disk handoff with a durable Hub record — a **checkpoint** — generated
  Hub-side, without depending on agent cooperation or on any installed skill.
- Make a checkpoint that disagrees with the database *reportable as failed*, not merely a
  checkpoint that is missing.
- Give the successor addressable recall into the predecessor's exact observations.
- Make peer message delivery deterministic, so cross-agent participation is computable.
- Make context measurement work for Claude agents, so any threshold can key on it.
- Let an operator configure whether checkpoints happen automatically and at what point.

**Non-Goals:**

- The agent configuration **page** rework. This change adds agent-level settings; restructuring
  `AgentInfoTab.tsx` into a page with back-button navigation is its own change, sequenced after, so
  it is built once against a settled settings list.
- Governance and audit **pages** over checkpoint data. Minimal visibility is in scope (below);
  browsing chains, diffing, and probe-verdict review are a later change.
- Cross-agent *memory* beyond the checkpoint chain. `recall` is scoped narrowly here (Decision 7).
- Binding `tasks` to conversations. Tasks stay project-scoped; the imprecision is stated, not fixed.
- Trigger-specific prompt variants. Deliberately deferred — see Decision 12, which is provisional.

## Decisions

### The checkpoint is generated Hub-side by a reusable Worker, not by the agent

The current design asks the agent to write the artifact. Observed twice: first press produced a
good artifact in an unreachable place, second press produced nothing and asked the operator a
question. Both set "Handoff ready", because readiness is the run ending.

Instead the Hub generates it out-of-band. There is already a working precedent in miniature:
`conversation_titles.py` reads conversation content from the DB, builds a one-shot invocation
(`build_title_command:59` — `claude -p …` / `codex exec …`), spawns it blocking with a timeout
(`_run_titler:93`), parses the output, and never raises into its caller.

Generalise that into a **Worker**: an operator-chosen `Runner` and model, a Hub-owned versioned
prompt, an input assembled deterministically from the database, a schema-validated output, and a
durable record. Reusing `Runner` records matters — operators already create and bind them, the
catalog already validates model ids, and it lets a checkpoint run on a cheap model while the work
runs on an expensive one.

The Worker is deliberately not `runner_commands.build_command`, for the same reason
`build_title_command` is not: that builds an *agent turn* — streaming JSON, an MCP server, a
permission posture, a context file — none of which applies to a process that reads one prompt and
returns one structured answer.

Beyond this change the same abstraction serves the blind-resume probe (Decision 5), and later spec
compliance and run review. Titling should migrate onto it rather than staying bespoke.

### Deterministic fields are computed, generated fields are written

The split is a *verifiability* boundary, not a stylistic one, and it is the direct answer to
Factory's finding that summarisers silently drop file paths.

| Computed by the Hub | Written by the Worker |
|---|---|
| conversation, agent, runner, model, timestamps | objective — what this conversation is for |
| `trigger`, lineage (`previous_checkpoint_id`, `lineage_id`) | state — where it got to |
| files changed, from the conversation's auto-snapshot diffs | decisions, with rejected alternatives |
| tasks (`assignee`), open questions, permission decisions | dead ends and their symptoms |
| runtime overrides in force | next actions — step 1 executable with no hidden decision |
| observation citations (Decision 6) | risks — what not to repeat |

Never ask the model for something the Hub knows. The observed failure is concrete: the agent wrote
`**Date:** 2026-08-08T00:00Z` — invented, because `Get-Date` was approval-blocked and it chose to
guess rather than block. It also reported "no pending work" from a worktree that is *always* clean,
because `worktrees.py:243-258` commits everything at end of turn.

This resolves exploration task 1.5: the artifact is a **hybrid** — a structured envelope the Hub
fills and validates, carrying one markdown body. Fully-structured buys nothing for judgement
fields, and one markdown blob is unverifiable.

### Each checkpoint is anchored on its predecessor, not regenerated from the whole transcript

Checkpoint N+1 reads checkpoint N plus only the turns since. Factory found anchored iterative
summarisation beats regenerate-from-scratch, which suffers gradual information loss; it is also
cheaper, since the Worker pays full price for whatever it reads.

This makes the chain a first-class object rather than a by-product, which is what lets checkpoints
serve tracking and governance rather than only resumption.

### The agent contributes notes; the Hub remains authoritative

Hub-side generation cannot recover what never reached the transcript — what the agent was *about*
to do, what it suspects but did not verify, what it would warn a successor away from. So the agent
is asked, via an MCP tool (a tool, not a prompt-and-parse, so the call is observable and the payload
is schema'd), for a brief structured response capped near the 1–2k tokens Anthropic recommends for
distillation.

It is asked only for what is **not** in the transcript. Never files changed, tasks, decisions, or
timestamps — those are Decision 2's left column.

Critically the notes are an **input, not the artifact**. Timeout, refusal, or garbage, and the
Worker generates the checkpoint anyway. This inverts today's design, where the agent is
authoritative and the Hub hopes.

The notes must be collected before cutover, since the provider session is gone afterwards. They are
therefore requested at a **notes threshold** configured *below* the cutover threshold
(Decision 11) — notes written from an already-degraded context are themselves degraded.

### A checkpoint that disagrees with the database is failed, not ready

Exploration task 1.11 asked that a checkpoint producing no artifact be reportable as failed. Hub-side
generation makes absence nearly impossible, so the useful rule is stronger: after generation, probe
the checkpoint and compare its answers to ground truth the Hub already holds.

Factory needed an LLM judge because they had nothing to compare against. We do — "which files were
modified", "what is assigned", "what is unanswered" are all queries. **The dimension that
benchmarked worst everywhere is the one we can check deterministically.**

The acceptance test is the control-plane literature's **blind resume**: can a fresh reader complete
the task from the checkpoint alone? Slipstream validates compaction by replay and catches
information loss, semantic drift, and context collapse; the probe is the cheap tractable version of
that, and it runs on the Worker (Decision 1).

"Ready" therefore stops meaning *the run stopped* — observed to be true of a run that wrote nothing
and asked a question — and starts meaning *a checkpoint record exists and passed its probes*.

### The successor gets addressable recall, not only prose

`agent_outputs` already stores every tool result verbatim under a stable id (`out-dd37110b`). That
is ARC's append-only observation store, and today it is discarded at a handoff.

The checkpoint carries **citations** — ids with short previews — and the successor gets a
`recall(id)` tool that materialises the exact archived content from the database. Lossy summary
plus a lossless escape hatch: the summary carries the narrative, recall recovers anything the
summary dropped, deterministically and without similarity search.

### Checkpoint reading and observation recall are separate grants, closed by default

AgentWeave's posture is isolation by default — separate worktrees, and the injected context says so
outright. Checkpoint access inherits that.

Two grants, deliberately not one:

- **`read_checkpoint`** — the distilled record: objective, decisions, dead ends, next actions.
  Curated and bounded. Grant liberally.
- **`recall`** — raw tool output verbatim: file contents, command output, possibly secrets from
  another agent's worktree. Grant rarely.

Summary access is not transcript access. A QA agent that should understand how a feature was built,
including its dead ends, should not thereby gain read access to three other agents' working
directories.

Grants live on the **Agent** record, alongside `permission_timeout_seconds`, and are enforced at the
tool layer against the run's minted credential — identity is never taken from a request body or
header (`agent_auth.py`), so this composes rather than inventing an auth path.

**Not on the charter.** Charters are editable markdown behaviour contracts; making a prose document
security-relevant means an operator edits a paragraph and silently widens access.

A `visibility` on the checkpoint itself (`private` / `project` / `granted`) gives the other half:
effective access is agent capability ∩ checkpoint visibility.

### Lineage and participation are different graphs and are modelled differently

**Lineage** is linear and belongs to one agent: checkpoint → checkpoint. Stored, as
`previous_checkpoint_id` for order plus `lineage_id` for cheap grouping, because walking the chain
to answer "show me this thread" is otherwise O(n).

**Participation** is cross-agent and belongs to a work unit. **Derived, not stored** — every
mutation carries a run id and every run carries an agent and a conversation, so
`Task.created_by_run_id → Run → (agent, conversation)` answers "who touched this work" as a join,
with no new bookkeeping. `Task` is the natural spine: it is the only project-scoped record multiple
agents mutate, and it already carries `assignee` and `assigner`.

Conflating the two produces a `lineage_id` that means two things.

### Peer delivery binds to the sender's conversation — prerequisite

Today, a peer message with no `conversation_id` is delivered to
`latest_open_conversation(recipient)` (`messages.py:133`) — whatever thread the recipient touched
most recently. Omitting the id is the *normal* path, since a sender does not know the recipient's
thread ids. Observed live: three `codex-1 → haiku-1` messages, one exchange by any human reading,
delivered into three unrelated `haiku-1` threads.

This is not specified behaviour being overturned. The spec promises *"the recipient conversation
selected by the queue-routing contract"*, and that term is **defined nowhere in `openspec/`**. This
change writes the missing definition.

Delivery is keyed on `(sender_conversation_id, recipient_agent)`, find-or-create. `Message` already
records the sender's conversation and the delivery path already ignores it. Both the operator and
agent routes funnel into `create_message_for_actor`, so there is exactly one routing site to change.

Three consequences, decided:

- **Senderless messages** — Hub- and scheduler-originated traffic has no source conversation, so it
  keys on the sender *identity* instead, giving one stable thread per (system sender, recipient).
  Recency routing then disappears from the codebase entirely rather than surviving in a corner.
- **Archive** — split by who chose. A sender that named an archived `conversation_id` explicitly
  keeps today's 409-with-content-returned. A *binding* that resolves to a thread the operator
  archived creates a successor bound to the same sender conversation with `origin: peer`; the sender
  did not choose it and should not be punished for the operator's action.
- **Backfill** — lazy. Historical peer traffic is already scattered across unrelated threads;
  backfilling would mean guessing which of three conversations an `ack` "really" belonged to.

Rejected: a durable A↔B *pair* thread (collapses a sender's separate work into one recipient
thread, losing the conversation-level precision the participation graph needs); requiring
`conversation_id` on peer sends (correct but pushes bookkeeping onto the agent); routing by task
(right unit, but only works for task-bearing messages).

### Context usage is measured from the catalog, not from two colliding events — prerequisite

Claude agents have **never** produced a usable context percentage. Across the last 400 samples,
`codex_appserver` produced 71 complete samples and `claude` produced 329 with **zero** usable
percent: 299 carry `context_tokens` with no `limit_tokens`, and 30 carry `limit_tokens` with no
`context_tokens`.

`record_context_usage` (`output_recording.py:118`) writes each sample whole, merging nothing and
guarding only against out-of-order arrival; the read path then `setdefault`s the newest single row
(`agents.py:418-420`). So whichever incomplete half arrived last wins.

`limit_tokens` is resolved from the model catalog, which is authoritative, and `percent` is computed
server-side. Two catalog gaps are filled at the same time: `claude-opus-5` and `claude-fable-5` are
declared `context_window=None` (`model_catalog.py:125,139`), so even a correct merge would leave
them blank.

This is a prerequisite rather than a side quest: an automatic checkpoint threshold keys on this
value, so the feature is unimplementable for Claude agents until it is fixed.

### Automatic checkpoints are configured as a threshold in percent *or* absolute tokens

Settings: whether automatic checkpointing is off / offered / automatic, a **cutover threshold**, a
**notes threshold** (Decision 4), and the Worker's runner and model.

A threshold is `threshold_mode` (`percent` | `tokens`) plus `threshold_value` — not two nullable
columns — because exactly one interpretation must ever apply. Token values are entered in thousands
(`150` means 150 000), since context windows differ enough between models that "compact at 150k" is
a more meaningful instruction than "compact at 50%".

Absolute tokens has a property worth stating: it does **not require the context window at all**.
`context_tokens >= 150_000` is answerable where `percent` is not, which routes around both the
measurement defect above and any model the catalog declares with `context_window=None`.

**Resolution is agent value ?? project value ?? built-in default, and the override replaces the
whole threshold — mode and value together.** A project percent-mode combined field-by-field with an
agent token-value resolves to nonsense.

Where the window is known the UI shows both readings ("150k — 75% of Haiku 4.5's 200k") and refuses
a token threshold at or above the window, which would never fire.

### One prompt for every trigger in v1 — provisional, and marked as such

At least five triggers produce a checkpoint and they hand the successor different problems: context
pressure (seconds, same agent, mid-task), operator ending a session (days, cold), **delegation (a
different agent, sharing no assumptions)**, run failure (what was in flight), and task completion
(an audit record nobody resumes).

v1 records `trigger` as a field and generates uniformly. Anthropic's guidance is to tune a
compaction prompt on real agent traces, and there are none yet; authoring five variants now would
encode five guesses — the failure this change's own gates exist to prevent.

**This is a deferral, not a conclusion.** It must be revisited once per-trigger probe results exist,
and **delegation is the most likely first candidate** for its own variant, since cross-agent reading
is in scope. Recorded outside this change as well
(`project_checkpoint_trigger_prompts_provisional`), because a design decision that expires is
exactly the kind that gets lost when a change is archived.

### It is called a checkpoint

"Handoff" arrived from the terminal skill along with the file-on-disk assumption that turned out not
to apply. "Checkpoint" is the vocabulary the product already uses — `aw-checkpoint.md`,
`/aw-checkpoint` in two inbox messages (`agents.py:1444,1474`), `checkpoints/` in both prompts, and
a test literally named *"checkpoints the old session"*.

So: **Checkpoint** is the Hub record. Handoff, if it survives, is one button that produces one.

This answers exploration task 0.4 — `src/agentweave/templates/skills/aw-checkpoint.md` is deleted
rather than installed or rewritten, because the capability moves into the Hub.

### Minimal visibility ships with the record; governance pages do not

A checkpoint the operator cannot see rebuilds the exact defect this change exists to remove: a
signal that looks like it works because nothing inspects it. So the checkpoint renders in the
conversation timeline and is readable over the API.

Browsing chains, diffing predecessor against successor, and reviewing probe verdicts are a real
surface whose every element depends on a record shape that does not exist yet. They are a later
change, and cheaper for waiting.

## Risks

- **The CLI compacts on its own.** Claude Code auto-compacts near 95%. If it fires first, the
  provider session survives but its context is now the CLI's summary — ours never happened, and the
  conversation continues on a compaction we did not author and cannot inspect. The signals to notice
  already exist (`context_usage.percent/warning/threshold_warning`, `context_warning` events, the
  `compact_request` endpoint). This design does not yet state whether we race, pre-empt, or defer.
- **Worker cost.** Hub-side generation pays full price for what it reads. Anchoring (Decision 3) and
  an operator-chosen cheap model are the mitigations; neither is measured yet.
- **Thread proliferation.** Keying delivery per sender-conversation creates more recipient threads
  than pair-threading would. `origin: peer` exists (`messages.py:138`) so the tree can group them,
  but the presentation work is real.
- **Notes from a degraded context.** The notes threshold exists to mitigate this and its correct
  value is unknown; the probes should measure it.
- **Probe cost and flakiness.** Self-validation adds a Worker call per checkpoint. Deterministic
  comparisons are cheap; anything needing generation is not.

## Open questions

- Does the CLI-compaction interaction above need resolving in this change or the next?
- Should titling migrate onto the Worker in this change, or later? It is the obvious second caller
  and would prove the abstraction, but it is not required by anything here.
- Does the proactive offer become silent-by-default — checkpoint quietly, surface only in the
  timeline, and reserve the card for when the operator would otherwise lose something?
