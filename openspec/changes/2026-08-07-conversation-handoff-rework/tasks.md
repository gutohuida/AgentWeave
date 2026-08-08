# Tasks — conversation checkpoint (formerly handoff rework)

> **Gate status (2026-08-08):** `2026-08-07-conversation-navigation` implemented ✅ · section 1
> exploration complete ✅ (`openspec/explorations/2026-08-08-handoff-behaviour.md`) · `design.md`
> written ✅ · `specs/` **not yet written** ⛔.
>
> **Implementation starts when `specs/` exists (task 1.10), and not before.**
>
> Sections 2–9 were rewritten from the exploration's findings at task 1.9. They replace the
> placeholder sections that stood here, which recorded assumptions rather than evidence.
>
> **Order matters.** Sections 2 and 3 are prerequisites: section 2 makes cross-agent participation
> computable, section 3 makes any threshold keyable. Both were discovered by this exploration and
> both block work later in this change.

## 0. Correct the stale references — unblocked, do with the rename

These are live defects today. They were gated on the exploration (see below) and on `design.md`,
both of which are now done. Fold them into section 9's rename rather than doing them twice.

> **Ordering correction (2026-08-08): 0.1 was NOT independent — 1.1–1.3 came first, and have now
> run.** Task 1.1 asks what the agent does when told to invoke a skill it does not have; rewriting
> `HANDOFF_PROMPT` first would have destroyed the condition 1.1 exists to observe. Findings are in
> `openspec/explorations/2026-08-08-handoff-behaviour.md`.
>
> **What 1.1 established about 0.1's shape:** the destination is not merely absent, it is
> *unreachable*. `.agentweave/shared/checkpoints/` lies outside the agent's allowed working
> directory (its worktree), so a Claude agent is sandbox-blocked from it and a Codex agent
> silently creates a second, nested `.agentweave/shared/` inside its own worktree. Installing
> `aw-checkpoint` therefore cannot fix 0.1 on its own — the path is wrong independently of the
> skill being missing, which also bears directly on 0.4.

- [ ] 0.1 `AgentOutputPanel.tsx:48-52` (`HANDOFF_PROMPT`) — the prompt instructs the agent to invoke an
      `aw-checkpoint` skill that is never installed and write to `.agentweave/shared/checkpoints/`,
      which is never created. Replace with an instruction the agent can actually satisfy, or state
      plainly in the prompt that it must produce the summary inline
- [ ] 0.2 `AgentOutputPanel.tsx:54-60` (`RESUME_HANDOFF_PREFIX`, the path at `:57`) — the resume
      prefix instructs the successor to read
      `.agentweave/shared/context.md`, which nothing writes. Remove or correct
- [ ] 0.3 `src/agentweave/diagnostics.py:477` — the remediation hint tells the operator to run
      `agentweave sync-context`, a command removed in the 56→5 CLI cut. Correct it
- [ ] 0.4 Decide and record whether `src/agentweave/templates/skills/aw-checkpoint.md` should be
      installed, rewritten, or deleted — it is currently packaged, referenced by a live prompt, and
      reachable by nothing
      **Decided (design.md, "It is called a checkpoint"): deleted.** The capability moves into the
      Hub, so there is nothing for the template to install.
- [ ] 0.5 `hub/hub/api/v1/agents.py:1444` and `:1474` — the `compact_request` and
      `new_session_request` inbox messages both instruct the agent to *"Run `/aw-checkpoint`"* and
      to re-read a checkpoint afterwards. Same dead reference as 0.1/0.2; **found during the
      exploration and missing from this section's original list**

## 1. Exploration — REQUIRED BEFORE ANY IMPLEMENTATION

Each task below is answered with evidence, written into `openspec/explorations/`. "I think" is not
an answer; a file path, a captured transcript, or an observed run is.

Findings live in `openspec/explorations/2026-08-08-handoff-behaviour.md`.

**Observe what exists**

- [x] 1.1 Trigger the current Handoff against a live Claude agent and capture the full transcript.
      What does the agent actually do when told to invoke a skill it does not have? Does it
      improvise something useful, refuse, or silently no-op?
      **Answered:** it improvises, well, by silently substituting the operator's own Claude Code
      `/handoff` skill — and ignores three of the prompt's four instructions (skill name, reason,
      destination). Artifact landed at `<worktree>/.handoffs/`, which no Hub record references.
      On a second press with the artifact in context it stops improvising and asks the operator
      for clarification instead, producing nothing. Both runs set "Handoff ready".
- [x] 1.2 Repeat against a live Codex agent. Codex has no project-level skill discovery at all
      (`scripts/sync_skills.py` header), so its behaviour may differ from Claude's
      **Answered, and the premise needs correcting.** Codex has no *project*-level skill
      discovery, but it reads `~/.agents/skills/` — it found and followed the *same* handoff skill
      Claude used. Both runtimes silently substitute the operator's personal handoff skill; neither
      has ever run `aw-checkpoint`. Codex resolves the destination relative to its own worktree,
      creating a nested `worktrees/codex-1/.agentweave/shared/checkpoints/` — confirmed on disk.
      **The rescue is borrowed, not a product property:** a user without those personal skill
      directories gets 1.1's second-run behaviour — no artifact, a question back. Section 0 cannot
      assume the competence observed here.
- [x] 1.3 Send the follow-up message and capture what the successor conversation actually receives.
      Determine whether any current behaviour is worth preserving before it is replaced
      **Answered: nothing is worth preserving.** The successor receives exactly
      `RESUME_HANDOFF_PREFIX + "\n\n" + typed message` in a brand-new conversation — no history, no
      peer messages, no tasks, no overrides, no artifact reference. Both paths the prefix names are
      wrong: `.agentweave/shared/` exists nowhere, and the real context file is
      `.agentweave/context/<agent>.md` (already injected into the prompt, so that half is redundant
      even when corrected). Codex's round-trip closes **by coincidence** — it resolved both the
      write and the read against its own worktree. Claude's does not: six failed lookups, one
      sandbox block, then a bare `Glob("*")` rescued it.

**Determine the content**

- [x] 1.4 Read `src/agentweave/templates/skills/handoff.md` (106 lines) and decide which of its
      sections apply to an AgentWeave conversation and which are specific to a single-agent coding
      session in a terminal
      **Answered:** three groups. **Drop** §1 (the operator already chose by pressing the button),
      §2's git gathering (the Hub auto-commits every turn at `worktrees.py:243-258`, so the tree is
      *always* clean and the log is *always* identical auto-snapshots — observed), §2's upstream
      probe, §2's prior-handoff search, §3's `.handoffs/`+`LATEST.md` chain, §4's "run /resume".
      **Stamp, don't ask:** the whole header block plus Files touched, all Hub-known and all got
      wrong or non-answered by the model. **Keep, model-authored:** Goal, Current state, Key
      decisions, Dead ends, Verification, Next steps, Open questions, Read on resume.
- [x] 1.5 Decide whether the artifact is structured (columns or JSON, machine-checkable) or markdown
      (one blob, model-authored). Verification at task 1.11 depends on this answer
      **Decided: hybrid** — a structured envelope the Hub fills and validates, carrying one
      markdown body the model writes. The boundary is 1.4's, and it is verifiability: Hub-known
      fields are checkable so structuring them lets a bad handoff be *failed*; judgement fields
      cannot be schema-validated, so structuring them adds ceremony and removes no failure.
- [x] 1.6 Determine what a handoff must carry that a single-agent session never had: the peer
      messages in the thread, the tasks the agent owns, outstanding questions, the conversation's
      runtime overrides
      **Answered, and they are not equally carryable.** Questions (`questions.conversation_id`,
      `unasked_questions.conversation_id`) and runtime overrides (`Conversation.runtime_overrides`)
      are conversation-scoped — carry exactly. Peer messages are per-side only (see 1.7).
      **Tasks are not conversation-scoped at all** — `tasks` is project-scoped with an `assignee`
      and has no `conversation_id`, so a handoff can only carry the agent's whole task list,
      identical across its concurrent conversations. Accept and state that, or bind tasks to
      conversations in a separate change. Overrides matter concretely: an inherited
      `{"permission_mode": "manual"}` is what failed `run-9058966b`.

**The multi-agent question — most likely to reshape the slice**

- [x] 1.7 `claude-1` hands off a conversation in which `haiku-1` participated. Does `haiku-1` need
      to be told? Its next message routes by `latest_open_conversation`, which will resolve to the
      successor — establish by test whether that is correct or merely convenient
      **Neither — it is already wrong today, independent of handoffs.** `messages.py:133` routes a
      peer message with no `conversation_id` to `latest_open_conversation(recipient)`: whatever
      thread the recipient touched most recently. Observed live — three messages from `codex-1` to
      `haiku-1`, one exchange by any human reading, delivered into three unrelated `haiku-1`
      threads (`conv-b275cb8d`, `conv-dbaf9847`, `conv-f22fb84f`). `Message.conversation_id` is
      populated with the *sender's* thread and never consulted for delivery. Telling `haiku-1`
      would not help: it has no binding to the predecessor to update.
- [x] 1.8 Determine whether a handoff should carry the peer relationships forward at all, or whether
      a successor starting peer-blank is the right default
      **The question dissolves — there are no peer relationships in the data model to carry.**
      Every conversation is already peer-blank; peer messages arrive by recency. Carry-forward is
      not implementable on top of recency routing. **Recommendation: narrow this change to the
      single-agent case** (artifact, verification, lineage, delivery) and raise the routing defect
      as its own proposal — it is a live bug affecting every peer message and is not caused by
      handoffs.

**Then, and only then**

- [x] 1.9 Write `design.md` from 1.1–1.8. Replace sections 2+ of this file with a real task list
      **Done.** `design.md` records 13 decisions; sections 2–9 below replace the placeholders.
      Note 1.8's recommendation was **overturned by the operator**: cross-agent reading is in v1, so
      the routing fix is folded in as section 2 rather than raised as a separate proposal.
- [x] 1.10 Write `specs/` — at minimum the `agent-conversation-handoff` deltas, which are a rewrite
      rather than an addition. Also needs a delta on `agent-conversation-workspace` defining the
      **queue-routing contract**, a term that spec references but never defines
      **Done — four deltas**, and `openspec validate --changes --strict` now passes:
      `conversation-checkpoint` (ADDED, the new capability), `agent-conversation-handoff`
      (MODIFIED ×3), `agent-conversation-workspace` (ADDED, the queue-routing contract),
      `agent-context-usage` (ADDED). The context delta turned out smaller than expected: the
      existing resolution order is already correct — provider, then catalog, then unknown — and the
      real gap is that nothing required a sample to identify its model, so the catalog step was
      unreachable for every Claude sample that carried tokens.
- [x] 1.11 Confirm the verification rule is testable against whatever 1.5 decided: a handoff that
      produced no artifact must be reportable as failed, which the current run-ended check cannot do
      **Confirmed, and strengthened.** Hub-side generation makes absence nearly impossible, so the
      rule becomes: a checkpoint whose probe answers disagree with database ground truth is
      **failed**. Deterministic on the dimension Factory.ai benchmarked worst. See design.md,
      "A checkpoint that disagrees with the database is failed, not ready".

## 2. PREREQUISITE — Deterministic peer delivery

Unblocks the cross-agent participation graph (section 7). Exactly one routing site: both the
operator route and the agent route funnel into `create_message_for_actor`.

- [x] 2.1 Add the binding column to `Conversation` (migration guarded for a missing table, as
      `0033`/`0034` do) and bump the head assertions in `hub/tests/test_migrations.py` **and**
      `hub/tests/test_project_persistence.py`

      **Two columns, not one.** `bound_sender_conversation_id` (indexed — every peer send looks it
      up) and `bound_sender_agent`. A single key column would put a conversation id and an agent
      name in one namespace, and the two answer different questions; keeping them apart means the
      senderless lookup can require the conversation column to be NULL rather than hoping the two
      never collide. Migration `0041`
- [x] 2.2 Replace `latest_open_conversation(recipient)` at `messages.py` with find-or-create keyed
      on `(sender_conversation_id, recipient_agent)` — `conversations.peer_bound_conversation`,
      called from the one site both the operator and agent routes funnel through
- [x] 2.3 Key senderless traffic (Hub, scheduler — no source conversation) on the sender *identity*,
      giving one stable thread per (system sender, recipient). **Recency routing must not survive
      anywhere in the peer path** — it does not; `latest_open_conversation` is gone from
      `messages.py` entirely. It remains in `questions.py`, `unasked_questions.py` and
      `output_recording.py`, which attach a question or an output to the agent's *current* thread.
      That is not the peer path and not a routing decision between correspondents
- [x] 2.4 Archive handling: an explicitly-named archived `conversation_id` keeps today's
      409-with-content-returned; a *binding* resolving to an operator-archived thread creates a
      successor bound to the same sender conversation with `origin: peer`.

      Falls out of the lookup filtering on `open`: an archived bound thread simply is not found,
      and the not-found branch creates the successor carrying the same binding. The split is real
      and tested — the refusal is for a sender that *chose* the conversation, and a binding the
      operator archived is not the sender's choice to be punished for
- [x] 2.5 No backfill — bind lazily on next message. Historical traffic stays where it landed.
      Pinned by a test: a pre-existing conversation carries no binding, so nothing resolves onto
      it, even when its id happens to match the sender's
- [x] 2.6 Tests: a sender's separate conversations reach separate recipient threads; a second
      message on the same sender conversation reaches the *same* recipient thread; senderless
      traffic is stable; the archive split behaves per 2.4 — all in
      `hub/tests/test_agent_message_routing.py`.

      **One existing test asserted the behaviour being removed** —
      `test_no_conversation_id_lands_in_the_recipients_newest_open_one`. Rewritten rather than
      deleted, so the file records that the rule inverted and why
- [x] 2.7 Regression test reproducing the observed defect — three messages from one sender landing
      in three unrelated recipient threads — asserted to now land in one.
      `test_three_messages_on_one_line_of_work_land_in_one_thread`, which touches a newer recipient
      thread between each send so it fails against recency routing rather than passing by accident

      **Also verified live against `:8010`, through `send_message` rather than the API.** Migration
      `0041` applied to the real database (38 existing conversations, none backfilled, index
      created). A real `haiku-1` turn called the tool and the Hub created `conv-05a0bbb4` for
      `codex-1`, `origin: peer`, bound to the sender's `conv-0bdd26ba`. A `codex-1` turn on an
      unrelated thread then made `conv-8b300c8e` its most recently touched open conversation — the
      one recency routing would have chosen — and a second `haiku-1` send from the same sender
      conversation landed back in `conv-05a0bbb4`. Both pings, one thread, with the decoy newer

> **Deferred by the operator (2026-08-08): peer-thread presentation is a follow-up, not part of
> this section.** Binding per sender-conversation creates more recipient threads than recency
> routing did. `origin: peer` already exists (`messages.py:138`) so the navigation tree *can*
> group or label them, but doing so is not in scope here. Expect the tree to get busier when
> section 2 lands, and raise the grouping work separately.

## 3. PREREQUISITE — Context usage measurement

Any threshold in section 8 keys on `percent`, which is **always null for Claude agents today**:
329 samples, zero usable. Unimplementable until fixed.

- [x] 3.1 Resolve `limit_tokens` from the model catalog rather than depending on two incomplete
      events colliding, and compute `percent` server-side

      `output_recording.resolve_usage_limit`, applied in `record_context_usage` — the one funnel
      every write path already goes through, so the HTTP self-report endpoint and the Hub's own
      spawn loop get it once rather than twice. It fills gaps and never overwrites: a sample that
      already carries a limit (Codex reports its own) is returned untouched, and a model the
      catalog does not declare leaves the fields alone rather than substituting a guess.

      **The enabling change was upstream.** `_claude_usage_sample` recorded no model, so there was
      nothing to look the window up *by* — Claude names the model on the `assistant` message and
      the window on the `result` message, and the sampler was reading only the former's usage
      block. It now carries `message.model`, which is what makes the reading complete on its own
- [x] 3.2 Fill in `context_window` for `claude-opus-5` and `claude-fable-5`, both `None`. Both 1M,
      from Anthropic's published model reference — a weaker source than the live `result`-event
      observation behind Sonnet 5 and Haiku 4.5, and `test_model_catalog.py` now says so rather
      than asserting the old blank state. Also added `context_window_for_model`, which searches
      every provider by exact id, then alias, then longest declared prefix: a sample carries the
      model the run used, not the provider, and providers report dated snapshots the catalog may
      hold undated
- [x] 3.3 Fix the read path at `agents.py`, which `setdefault`s the newest single row and so
      returns whichever incomplete half arrived last.

      `_usable_context_reading`. The newest row still wins when it carries a percentage; otherwise
      the newest row **from the same provider session** that does. Scoped to the session
      deliberately: a compaction or a fresh session resets usage, and reporting a pre-reset
      percentage as current would be worse than reporting none, because it is the number the
      operator would act on. Pinned by a test
- [x] 3.4 Test with the real observed shapes: a `claude` sample with tokens and no limit, one with
      limit and no tokens, and a complete `codex_appserver` sample —
      `hub/tests/test_context_usage_measurement.py`, 10 tests, shapes taken from the 400 stored
      samples rather than invented
- [x] 3.5 Verify live against `:8010` that a Claude agent reports a percentage — the exploration's
      standing rule is that a captured observation, not a passing test, closes a measurement task.

      **Observed.** Before: all four Claude agents in the testbed reported
      `context_tokens: null, percent: null`; both Codex agents were fine. After a real `haiku-1`
      run, `GET /agents` returned `percent: 15.12`, `context_tokens: 30233`,
      `limit_tokens: 200000`. The stored rows show both halves working: the tokens-carrying rows
      were written *with* a limit and percent (the write path), and the newest row for the session
      is still the limit-only end-of-turn report carrying `percent: null` — so the read-path
      fallback is what surfaced 15.12 rather than nothing

## 4. The Worker

A Hub-side, out-of-band, single-purpose model invocation. Generalises
`conversation_titles.py`'s proto-worker.

> **The envelope shapes were captured before the parser was written** (`claude` 2.1.221,
> `codex-cli` 0.146.0), on the exploration's standing rule that an observation beats a passing
> test. It paid for itself three times over — see 4.3 and 4.5.

- [x] 4.1 Worker abstraction: operator-chosen `Runner` + model, Hub-owned versioned prompt,
      deterministically assembled input, schema-validated output, durable record

      `hub/hub/worker.py`. Deliberately **generic**, not checkpoint-shaped: design.md earmarks the
      same abstraction for the blind-resume probe (Decision 5), and later spec compliance and run
      review. `run_worker` takes primitives rather than a `Runner` row so a call that can take
      minutes does not hold a DB session open across it
- [x] 4.2 Reuse `Runner` records and validate the model against the catalog; do **not** use
      `runner_commands.build_command`, which builds an agent turn (streaming JSON, MCP server,
      permission posture, context file) — none of which applies

      `build_worker_command`, with a test asserting `--permission-mode`, `--mcp-config`,
      `--allowedTools` and `stream-json` appear nowhere in it — because the tempting fix for any
      future worker problem is to borrow a flag from `build_command`. `model_is_declared` checks
      **exact ids only**, matching `runners._reject_undeclared_model` rather than the alias
      resolution `context_window_for_model` does: a worker that accepted models the runner
      registry refuses would be the laxer of two gates on the same value
- [x] 4.3 Blocking spawn with timeout that never raises into its caller, following
      `_run_titler:93`

      `_run_worker_process`, classifying its own failure into `timeout` / `spawn_failed` /
      `nonzero_exit`. **Two properties the capture established, both load-bearing and neither
      guessable:** `stdin` must be `DEVNULL` or `codex exec` blocks on "Reading additional input
      from stdin..." indefinitely — observed hanging over six minutes having written zero bytes —
      and **stderr is never a failure signal**, because a successful codex run writes its banner,
      its token count *and* a transparently-retried `ERROR ... 503 Service Unavailable` there
      while exiting 0. Both are pinned by tests
- [x] 4.4 Record every invocation: prompt version, runner, model, tokens, duration, outcome

      `WorkerInvocation` + migration `0042`; head assertions bumped in `test_migrations.py` and
      `test_project_persistence.py`. **Tokens are real, not nullable-in-practice** — both CLIs
      report usage in JSON mode (`claude --output-format json` → `.usage` + `total_cost_usd`;
      `codex exec --json` → `turn.completed.usage`), which is why JSON mode was chosen over
      scraping prose. Cache dimensions are carried separately rather than folded into
      `input_tokens`: the captured claude sample read **2** input tokens against **47091** cache
      reads, so folding them would misreport the call by four orders of magnitude.
      `runner_id` carries **no foreign key** — an audit row a runner deletion could cascade away
      is not an audit row. Eight outcomes rather than a boolean, because a timeout, a missing CLI
      and a model that answered in prose are three different problems; a test asserts the
      vocabulary cannot drift from the check constraint.

      **No `Run` row is created**, and a test pins it: `turn_scheduler.schedule_agent` and
      `trigger_agent_directly` gate on a running `Run` for the agent, so a worker recorded as a
      run would make that agent look busy and stall its queue until it returned. This trap is
      documented in `conversation_titles.py` and is the easiest way to get the Worker wrong
- [x] 4.5 Tests including a worker whose CLI fails, times out, and returns unparseable output

      `hub/tests/test_worker.py`, 23 tests, envelope samples captured verbatim rather than
      invented. **Capturing first caught a bug that would otherwise have shipped:** the real
      claude envelope nests `usage`, `iterations` and `modelUsage`, and the first
      `extract_json_object` — scanning every `{` and keeping the last that parsed — returned the
      innermost *trailing* object rather than the envelope. A candidate now advances the cursor
      past its own end, so only top-level objects are considered. `unparseable` (prose) and
      `schema_invalid` (valid JSON, wrong shape) are separate outcomes, and usage is retained on
      both — a worker that burned tokens producing garbage still cost money.

      **Correction found in passing, not acted on:** `conversation_titles.title_from_output`
      justifies its last-non-empty-line heuristic with "Codex prints progress and configuration
      ahead of its answer". In 0.146.0 all of that goes to *stderr* and stdout is one clean line.
      The heuristic still works; its stated reason is stale. Titling is not in this change's
      scope — design.md says it should migrate onto the Worker, which is the right time to fix it

      **Live-verified against the real database and real CLI spawns.** The suite fakes
      `subprocess.run` — right for determinism, but it means nothing in it has ever launched a
      process. Migration `0042` applied to `hub/data/agentweave.db` (`0041 → 0042`, table created,
      19 columns). Three real invocations, all recorded:

      | cli / model | outcome | ms | in / out | cache read | cost |
      |---|---|---|---|---|---|
      | `claude` / `claude-haiku-4-5-20251001` | `ok` | 7282 | 10 / 353 | 21569 | 31074 µ$ |
      | `codex` / `gpt-5.6-sol` | `ok` | 9703 | 17599 / 43 | 11008 | — |
      | `claude` / `claude-nonexistent-9` | `unknown_model` | — | — | — | — |

      Both `ok` runs returned a Pydantic-validated object from a genuinely one-shot process.
      Codex reports no cost, which is the nullable-where-unavailable policy working rather than
      failing. The undeclared model was refused **before** any spawn — no duration, no tokens,
      and the reason recorded on the row

## 5. The checkpoint record

- [x] 5.0 **PREREQUISITE discovered while implementing 5.2 — record the per-turn snapshot commit.**

      `worktrees.snapshot_worktree` has always returned the SHA of the commit a turn produced, and
      **both call sites in `agent_trigger.py` (`:1150`, `:1515`) discarded it**. Nothing in the
      schema recorded what a turn changed, so 5.2's "files changed from the conversation's
      auto-snapshot diffs" was not computable.

      The alternatives were worse and were rejected: matching commits to turns by timestamp is
      guesswork, because one worktree — and so one branch — is shared by **all** of an agent's
      concurrent conversations and every auto-snapshot carries the identical message
      `Auto-snapshot: <agent>'s turn`; diffing the agent's branch as a whole answers a different
      question for the same reason.

      `Run.snapshot_commit_sha` + migration `0043`, captured at both sites. **No backfill** — those
      SHAs were never captured and cannot be recovered, so a historical conversation reports no
      changed files rather than a plausible guess, the rule `0041` set for peer bindings
- [x] 5.1 `Checkpoint` model + migration: identity, `trigger`, `previous_checkpoint_id`,
      `lineage_id`, `visibility`, envelope fields, body, probe verdict

      Migration `0044`; head assertions bumped to `0044`. Five triggers, three statuses
      (`ready` / `unwritten` / `failed`), three visibilities. **`status <> 'ready' OR body IS NOT
      NULL` is enforced in the schema, not only in `create_checkpoint`** — the defect this change
      removes is a readiness signal that meant "the run stopped", and making the state
      unrepresentable is what stops a future code path reintroducing it. `failed` is reachable only
      from section 6's probes; section 5 never writes it
- [x] 5.2 Compute the deterministic half — files changed from the conversation's auto-snapshot
      diffs, tasks by `assignee`, open questions, permission decisions, runtime overrides

      `hub/hub/checkpoints.py`. Nothing in the module asks a model for anything.
      `worktrees.files_changed_in` uses `git show --name-only` rather than a `sha^..sha` diff:
      the first commit on a fresh agent branch has no parent and a diff against `sha^` fails
      outright on it — which is exactly the commit a first-ever checkpoint needs. Permission
      *denials* are carried, not just grants: an agent refused a tool call and working around it
      leaves a successor that needs to know why the obvious route is closed. `agent_worktree` uses
      `worktree_path`, never `ensure_worktree`, so computing a checkpoint cannot have the side
      effect of provisioning a workspace for an agent that never ran
- [x] 5.3 Never ask the model for a computed field. Test that the envelope is populated even when
      the Worker returns nothing

      A body-less checkpoint is `unwritten` and still carries every computed field — the computed
      half is the verifiable half and does not depend on a model. A whitespace-only body collapses
      to NULL, so "cleared" and "never written" are one state (the rule `Agent.description`
      follows) and a worker that returned a newline cannot produce a checkpoint claiming to be
      readable
- [x] 5.4 State the task imprecision explicitly: `tasks` has no `conversation_id`, so the carried
      list is the agent's whole list, identical across its concurrent conversations

      `TASK_SCOPE_NOTE`, carried **in the payload** as `scope: "agent"` plus prose, not only in a
      docstring. A list that looks conversation-specific and is not is the same class of quiet
      wrongness this change exists to remove, so the record says so where a reader will see it
- [x] 5.5 Anchored generation — checkpoint N+1 reads checkpoint N plus only the turns since, not the
      whole transcript

      `covers_from_run_id` / `covers_through_run_id` + `runs_to_cover`. `lineage_id` is the
      founding checkpoint's own id, carried forward rather than regenerated, so "show me this
      thread" is one indexed read. An anchor naming a run the conversation no longer has falls
      back to covering **all** turns and logs it — covering a turn twice is a redundancy, silently
      covering none is a hole

## 6. Generation, agent notes, and self-validation

- [x] 6.1 `submit_checkpoint_notes` MCP tool — schema'd, capped near 1–2k tokens, asking **only**
      for what is not in the transcript: intent in flight, unverified suspicions, warnings

      Tool in `mcp_server.py`, endpoint `POST /agent-actions/checkpoint-notes`, storage in
      `CheckpointNote` (migration `0045`). Caps: intent 1500 chars, 8 entries × 400 chars each.
      Not incidental — an agent allowed to write at length here would be writing the checkpoint
      by the back door, which is the arrangement this change replaces.

      **A table, not a column on `conversations`.** "The agent had nothing to add" and "the agent
      was never asked, or never answered" must stay distinguishable; that is the same reason the
      spec requires a tool call rather than prose parsing. Notes from a run with no conversation
      are refused 409 rather than stored where nothing will read them
- [x] 6.2 Notes are an *input*, never the artifact. Test that timeout, refusal, and garbage all
      still produce a checkpoint

      From the Hub's side, timeout and refusal and silence are one state: no note row. A
      checkpoint generated without notes says so in its body, so the two absences do not read
      identically to a successor. **Notes are marked consumed even when generation produced
      nothing** — otherwise a failed generation leaves stale intent to be picked up by a later
      checkpoint as though it were current, the same staleness as reporting a pre-compaction
      context percentage
- [ ] 6.3 Request notes at the **notes threshold**, below the cutover threshold, so they are not
      written from an already-degraded context
      **BLOCKED on section 8.** The threshold configuration this keys on (8.4/8.5) does not exist
      yet; the input side is complete, so this is the wiring only
- [x] 6.0 **Generation itself** — `hub/hub/checkpoint_generation.py`, the glue sections 4 and 5
      were built for. A Hub-owned versioned prompt (`checkpoint/1`), input assembled from the
      anchor plus only the turns since, `CheckpointBody` as the schema, `render_body` /
      `render_checkpoint` as the artifact a successor receives.

      **Both sides of the exchange are bounded by when the anchor was taken.** Filtering only the
      agent's outputs by covered run id — the obvious implementation — would replay every operator
      message the previous checkpoint already summarised, on every subsequent checkpoint, and
      `InboundQueueEntry` carries no run to filter by in any case. The transcript trims
      newest-first, so a conversation that overflows the cap keeps its *recent* turns rather than
      its opening
- [x] 6.4 Probe the generated checkpoint against database ground truth — files changed, tasks
      assigned, questions unanswered

      A second Worker call (`checkpoint-probe/1`) reading the checkpoint blind, graded by
      `grade_probe` against the envelope. **The probe reads the whole rendered checkpoint, not the
      body alone** — a deliberate choice, and the alternative is not merely weaker but broken: the
      generation prompt is forbidden from asking for computed fields, so the body legitimately
      contains no file list and a probe of the body in isolation would fail every well-formed
      checkpoint. Reading the artifact exactly as a successor receives it catches what is real —
      a body contradicting the envelope, and a render that drops the envelope on the way out.

      Findings separate `missing` from `invented`: a missing path is information the checkpoint
      lost, an invented one is information it made up, and they call for different fixes. Path
      separators and leading `./` are normalised, so a reader echoing a Windows path has not
      "disagreed"
- [x] 6.5 A checkpoint whose probes disagree with the database is **failed**. "Ready" means a
      record exists and passed, never "the run stopped"

      **A probe that cannot run leaves the checkpoint `ready` with `probe_status` NULL.** An
      unrunnable probe is the Hub's failure, not the checkpoint's; failing a checkpoint because
      the grader was unavailable would recreate — in the other direction — exactly what this
      change removes, a status that reports something other than what it names
- [ ] 6.6 Blind-resume acceptance test: a reader given only the checkpoint answers the probe
      questions correctly
- [ ] 6.7 Record `trigger` on every checkpoint. **One prompt for all triggers in v1 — provisional,
      see design.md and `project_checkpoint_trigger_prompts_provisional`. Do not let this harden**

## 7. Recall and permissions

- [ ] 7.1 `recall(id)` MCP tool materialising exact archived content from `agent_outputs` by stable
      id, scoped to the predecessor conversation in v1
- [ ] 7.2 Checkpoint carries citations — ids with short previews
- [ ] 7.3 Two independent grants on the `Agent` record: `read_checkpoint` and `recall`. Closed by
      default. Summary access is **not** transcript access
- [ ] 7.4 Enforce at the tool layer against the run's minted credential; identity is never taken
      from a request body or header
- [ ] 7.5 `visibility` on the checkpoint (`private` / `project` / `granted`); effective access is
      agent capability ∩ checkpoint visibility
- [ ] 7.6 Participation query — `Task.created_by_run_id → Run → (agent, conversation)`. Derived, not
      stored; no new bookkeeping
- [ ] 7.7 Test the tester scenario end to end: an agent granted checkpoint reads over three peers
      can read their checkpoints and is **refused** `recall`
- [ ] 7.8 Grants must not live on the charter — add a test asserting charter text cannot widen
      access

## 8. Lifecycle, configuration, and visibility

- [ ] 8.1 Deliver the checkpoint to the successor as an `InboundQueueEntry`, conversation-scoped.
      **Not** through `_render_hub_agent_context`, which is agent-scoped and writes one file per
      agent, so it cannot carry a per-conversation payload
- [ ] 8.2 Archive the predecessor on a successful checkpoint, through `archivable()` — which
      already refuses when an undelivered queue entry would be stranded
- [ ] 8.3 Create the successor with `origin: handoff` and a title derived from its predecessor's;
      make lineage legible in the navigation tree
- [ ] 8.4 Configuration: automatic checkpointing off / offered / automatic, cutover threshold, notes
      threshold, Worker runner + model
- [ ] 8.5 Threshold is `threshold_mode` (`percent` | `tokens`) + `threshold_value`, **not** two
      nullable columns. Token values entered in thousands (`150` = 150 000)
- [ ] 8.6 Resolution is agent ?? project ?? built-in default, and an override replaces the **whole
      threshold** — mode and value together, never field-by-field
- [ ] 8.7 Where the context window is known, show both readings ("150k — 75% of Haiku 4.5's 200k")
      and refuse a token threshold at or above the window, which would never fire
- [ ] 8.8 Token mode must work where `limit_tokens` is unknown — it needs only `context_tokens`
- [ ] 8.9 Minimal visibility: the checkpoint renders in the conversation timeline and is readable
      over the API. **In scope** — an invisible checkpoint rebuilds the defect this change removes
- [ ] 8.10 The proactive offer becomes *"I made one, here it is, cut over?"* rather than *"shall I
      ask the agent?"* — generation no longer depends on the agent

## 9. Rename, and the stale references

- [ ] 9.1 **Checkpoint** is the Hub record; handoff is at most a button that produces one. Rename
      through the UI, API, and specs
- [ ] 9.2 Rewrite `HANDOFF_PROMPT` and `RESUME_HANDOFF_PREFIX` (`AgentOutputPanel.tsx:48-60`), or
      remove them if Hub-side generation makes them unnecessary. Section 0.1/0.2
- [ ] 9.3 Fix `agents.py:1444` and `:1474`. Section 0.5
- [ ] 9.4 Fix `diagnostics.py:477`'s dead `agentweave sync-context` hint. Section 0.3
- [ ] 9.5 Delete `src/agentweave/templates/skills/aw-checkpoint.md`. Section 0.4
- [ ] 9.6 Update `hub/ui/src/__tests__/agentHandoff.test.tsx`, which asserts the prompt contains
      `'aw-checkpoint skill'`
- [ ] 9.7 Full sweep before committing: `pytest hub/tests/`, `npx vitest run`, `npx tsc --noEmit`,
      `npx openspec validate --changes --strict`, `npm run build` + copy to `hub/hub/static/ui`
      confirmed with `diff -rq`
