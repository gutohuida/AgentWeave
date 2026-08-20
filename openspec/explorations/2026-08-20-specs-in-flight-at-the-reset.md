# What was being specified when the trial was reset — 2026-08-20

The operator's first real run at using AgentWeave to spec AgentWeave ended with the Hub database
destroyed (finding 18 in `2026-08-20-dogfooding-findings.md`) and a decision to start clean. The
three documents under `spec/changes/` were deleted with the reset. **Their full text is in git** —
`git show bb663e1:spec/changes/<dir>/spec.html`, or the commit that added each one.

This file exists so the *thinking* is not lost with them. Everything below was authored through the
app, most of it by an Architect agent working from live probes rather than from memory, and the
grounding sections are the expensive part: they were measured on this machine, on 2026-08-20,
against Claude Code 2.1.221 and real Codex rollout transcripts. If any of this work resumes, start
from the measurements, not from a fresh investigation.

---

## 1. Project usage on the control page, and a Budgets page of its own

`spec/changes/project-usage-by-provider-agent-and-model-on-the-control-page-and-subagent-visibility/`
— **`change-spec`, reached `approved`**, 17 requirements, 21 acceptance criteria, 10 tasks. This was
the furthest along: the operator had approved it and put Developer on it with Tester reviewing. Ten
tasks were open at the reset; the ledger showed none complete.

**The shape.** The control page (project Overview) loses the per-agent context meter and the
duplicated budgets panel. It gains one small usage summary — money as the headline, equivalent
tokens beneath, defaulting to today, switchable to 7 or 30 days — that links to **Budgets, promoted
to a project tab of its own**, where usage breaks down by provider with models nested inside, by
agent, and separately for AgentWeave's own worker calls.

**Why the context meter goes.** `ContextUsageIndicator` reports what fraction of a context window an
agent's most recent run consumed. That answered a real question when an agent had one long-lived
session. With many conversations per agent it reports one arbitrary recent thread and answers
nothing. The operator's ruling: it only makes sense *inside* a conversation, and leaves the control
page.

**The grounding that cost the most to establish:**

- `TurnUsage` already carries `agent`, `runner`, `model`, input/output/total tokens, cache read and
  write, reasoning tokens, `api_equivalent_usd_micros`, a provider `allowance` blob and
  `observed_at` — one immutable row per Hub-owned run. Every rollup this change wants is a group-by
  over columns that already exist, and applies **retroactively to history already recorded**.
  `accounting_snapshot` today aggregates only a project total and a per-agent breakdown.
- `WorkerInvocation` records the Hub's own out-of-band model calls (checkpoint generation, probes)
  with their own cli, model, tokens and cost — and is **absent from the accounting snapshot
  entirely**. Separating "spend on work" from "spend AgentWeave incurs driving itself" is a question
  the operator specifically wants answerable, and worker calls will only grow.
- **A real inconsistency, measured.** For a Claude run that spawns a subagent, the final `result`
  event's `usage` covers the **main chain only** (measured: input 18, cache-read 57,940, cache-write
  544 — an exact match), while `modelUsage` covered cache-read 84,169 / cache-write 14,355, the
  difference being the subagent, and `total_cost_usd` (0.03333765) equalled `modelUsage.costUSD`
  exactly. `runner_parsing` reads `result.usage` first and passes `total_cost_usd` through either
  way — **so the Hub stores a dollar figure that includes the subagent beside a token count that
  excludes it.** Precisely the two numbers this change stacks on top of each other. No Hub-spawned
  run in the project had actually spawned a subagent yet (0 of 28 sessions), so no recorded row was
  known to carry it. The fix was scoped forward-only; backfill was an explicit non-goal.
- **Codex reports no cost at all.** Its `turn.completed` accounting is built with no `cost_usd`
  argument and the model catalog has no price table; six recent rollout transcripts under
  `~/.codex/sessions/**/*.jsonl` contain no cost field of any kind. Its usage payload is
  `{input_tokens, cached_input_tokens, cache_write_input_tokens, output_tokens,
  reasoning_output_tokens, total_tokens}` with `total_tokens = input + output`, so `input_tokens`
  already includes cache reads — matching the `cache_is_separate_input=False` path the Hub already
  takes for Codex against `True` for Claude. Model ids look like `gpt-5.6-sol`.
- **Real `rate_limit_info`** is `{status, resetsAt, rateLimitType: "five_hour", overageStatus,
  overageDisabledReason, isUsingOverage}`. It says which window is in force and when it resets, and
  carries **no remaining-allowance figure**; no weekly window appeared in the sample. Note that this
  repository's own test fixture uses a different, invented shape
  (`{"five_hour": {"remaining_percent": 64}}`) — the parser stores the blob verbatim so nothing
  breaks, but no live payload observed here carries a percentage. The spec deliberately required
  showing the reset and stating no remaining figure.

**Pricing design, read from T3 Code's shipped sourcemaps (`src/usage/`, design reference only).**
Rates come from LiteLLM's public `model_prices_and_context_window.json` — the same table `ccusage`
prices against. Each entry gives USD-per-token for input, output, cache read and cache creation. The
rules worth keeping: a missing cache rate falls back to the **input rate, not to free**; an entry
lacking either input or output is **dropped**, because a half-priced model under-reports silently;
model names are canonicalised by stripping a `provider/` prefix and lowercasing; bare family names
("opus", "sonnet", "haiku") are treated as **unpriceable rather than guessed** at a generation;
rates are read at the base tier only, because the record does not say which tier served a request;
every bucket carries a source of `providerReported`, `modelPriced` or `unpriced`; reasoning tokens
are **never** charged on top of output, being already counted inside it; buckets are
`(day, provider, model)` cells cut on the **operator's local calendar day**, so a turn lands on the
day the operator experienced it.

**One architectural line deliberately not crossed.** T3 derives usage by scanning the provider CLIs'
own on-disk transcripts, so its numbers cover turns never driven through T3 at all. AgentWeave's
`TurnUsage` covers exactly the turns the Hub spawned — and is the only source that knows which
agent, task and project a turn belonged to, which is also the only way the work-versus-overhead
split is answerable. Scanning provider transcripts was an explicit non-goal.

**The 17 requirements, condensed.** Control page shows one usage summary for the window, money
primary and tokens secondary, covering both agent work and AgentWeave's own calls (FR-1); shows only
the summary, no breakdown or budget controls (FR-2); links to Budgets (FR-3). Budgets is a top-level
project tab beside Overview/Tasks/Spec/Jobs/Activity and is *not* also an Environment section
(FR-11). An API-equivalent estimate is marked as such, stating subscription plans are billed
differently (FR-4). Every provider gets a monetary figure — provider-reported where given, rate-table
computed otherwise — and a rate table ships in every release (FR-12). Each figure declares its source
(FR-13). Unpriced work still counts in tokens, contributes nothing to money, and the surface states
how much was excluded (FR-14). Window defaults to today, switchable to 7/30 days, and every figure
follows it (FR-5), with boundaries on the local calendar day (FR-15). For turns recorded after this
ships, money and tokens describe the same work (FR-16, the consistency fix). Budgets breaks down by
provider (FR-6), by agent (FR-7), and by model nested inside its provider rather than as a flat list
(FR-8). AgentWeave's own out-of-band calls are their own category, never summed into any agent
(FR-9). Where a provider reports a rate-limit window, show which one and when it resets, with no
remaining figure (FR-10). The control page shows no context meter for any agent; the meter stays
available inside a conversation (FR-17).

**The 10 tasks** were: ship-and-refresh the rate table with a fallback; price a turn and record where
the price came from; make money and tokens count the same work; window on the local day; move Budgets
to a project tab; build the breakdowns; give AgentWeave's own spend its own category; build the
control-page summary; the estimate caveat and rate-limit reset; remove the context meter.

---

## 2. Tracking and showing the subagents Claude spawns

`spec/changes/tracking-and-showing-the-subagents-claude-spawns/` — **`change-spec`, `exploring`**.
Zero requirements by design: a seeded exploration carrying the problem, the live probing, and six
open questions. The operator had said *"Creating a new explore page. You don't need to do nothing
right now"* and had not been interviewed on it.

**The problem.** A Claude agent can spawn subagents. The Hub records a spawn only as a generic tool
call — no identity, type, model, tokens, duration or outcome. From the operator's chair a subagent is
a tool call named `Task` followed by a blob of result text. Two distinct problems live here and
either is worth solving alone: **attribution** (subagent tokens landing in project totals so the
money and token figures are honest) and **visibility** (a place to see what was delegated, how long
it took, what it returned). The operator asked for this to be developed separately from the usage
change and named a side-panel page as a possible home.

**What live probing established — everything needed is already in the stream the Hub parses, and
none of it is read today:**

- A spawn emits `system` / `subtype: task_started` carrying `task_id`, `tool_use_id`, `description`,
  `subagent_type` (e.g. `Explore`), `task_type` (e.g. `local_agent`) and the full `prompt`. Identity
  and intent arrive **up front, before any work happens**.
- Every subagent turn arrives as an ordinary `assistant` line with `parent_tool_use_id` set to the
  spawning tool call's id, carrying its own `message.model` and `message.usage`. Per-subagent,
  per-model attribution is directly measurable **live**, without waiting for completion.
- On completion the parent's tool result carries `agentId`, `agentType`, `resolvedModel`, `status`,
  `totalDurationMs`, `totalToolUseCount`, `toolStats` (read/search/bash/edit counts, lines added and
  removed) and `usage`. An **asynchronous** launch instead returns `{agentId, description, prompt,
  resolvedModel, status, isAsync, outputFile, canReadOutputFile}` — different shape, and a reader
  must handle both.
- Claude Code also writes each subagent's transcript to
  `~/.claude/projects/<slug>/<session>/subagents/agent-<agentId>.jsonl`, entries carrying
  `isSidechain: true`, the parent `sessionId`, the `agentId`, and per-message `usage`, `model` and
  `effort`.

**The trap, and it is a big one.** `totalTokens` on the tool result is **not** the subagent's cost —
it is the final request's footprint. Measured against a real subagent transcript: the tool result
reported `totalTokens` 40,314, while summing that subagent's 18 actual requests gives **530,405**
(36 input, 3,083 output, 394,591 cache read, 132,695 cache write). Pricing a subagent from
`totalTokens` understates it by more than an order of magnitude. The per-turn `usage` on each
`parent_tool_use_id` line is the figure that can be summed.

**The six open questions, none resolved:**

1. Is the goal attribution, visibility, or both — and if only one, which ships first? They share a
   data-collection step and nothing else.
2. Does "subagent" mean only Claude's spawned agents, or also AgentWeave's own `WorkerInvocation`
   calls (arguably the same idea one level up, and already getting its own Budgets category)? Does
   Codex have an equivalent?
3. Where does the surface live — a project tab, a subview of Activity, a panel inside the
   conversation that spawned it, or the agent's own page? A subagent belongs to one turn of one
   conversation, which argues for showing it where that turn is read; a project-wide page instead
   answers "what has been delegated lately, and what did it cost".
4. Store a subagent's prompt and returned text, or only metadata? They are what make the work
   reviewable and are the whole point of a visibility surface — and they are unbounded text arriving
   on every spawn, with the prompt carrying whatever the parent agent chose to paste in.
5. Do asynchronous subagents need following to completion, or is recording the launch enough?
   Following one means watching for a result after the spawning turn has already ended.
6. Should any of it be retroactive? Claude Code's on-disk subagent transcripts hold the history, but
   reading them means AgentWeave deriving facts from another tool's files rather than its own
   records — the same architectural line the usage change deliberately did not cross.

---

## 3. Quiet hours for agent notifications

`spec/changes/quiet-hours-for-agent-notifications/` — **`change-spec`**, 7 requirements, 4 tasks,
authored 2026-08-18. Older than the other two and much thinner; it reads as an exercise of the spec
flow rather than committed product work. Recorded here for completeness.

A per-project quiet window with graded urgency and a morning digest, so an overnight run stops waking
the operator for things that can wait. A deferred notification is deferred, **not dropped** (FR-1); a
blocking question overrides the window and notifies immediately (FR-2); every deferred notice appears
in the next digest (FR-3); the digest groups by agent rather than arrival time (FR-4); the window
defaults to 22:00–08:00 in the project's declared timezone (FR-5); a project may disable quiet hours
(FR-6); the digest may be delivered as a conversation entry rather than a separate surface (FR-7).
Non-goals: per-agent overrides, timezone inference from the host clock, any change to how questions
are routed. Its one open question — whether a second blocking question during quiet hours re-notifies
or folds into the first — was marked resolved without the answer being recorded in the payload.

---

## What survived the reset, and where

- `spec/capabilities/` — **kept**, 34 files: the 32 migrated openspec capabilities plus
  `project-instructions` (deliberately skipped by the importer, because a hand-translated version
  with authored GIVEN clauses already existed) and `quiet-hours`.
- `spec/agentweave.html` — the authored system map, **kept**, still the corpus `home`.
- `spec/index.json` — **still correct.** It lists 33 documents (the 32 migrated capabilities plus the
  system map) and every one of them still exists on disk; the deleted change documents were created
  after the index was written and were never in it. The two capability files it does not list —
  `project-instructions` and `quiet-hours` — are the ones that read `unfiled`, and they were unfiled
  before the reset for the same reason they are now: no Hub can adopt a document that already exists
  on disk.
- `openspec/specs/` — unaffected, still the authoritative corpus for the same capabilities.
- The Hub database rows for all of the above are **gone** and were not restored. The documents on
  disk cannot be given rows again until document adoption exists (finding 17): `POST /documents`
  still renders a placeholder over the file it is handed.
