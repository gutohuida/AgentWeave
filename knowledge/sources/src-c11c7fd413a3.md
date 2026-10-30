# Findings index

**A snapshot, not the ledger.** New findings and status changes still go in scripts/drive/FINDINGS.md until the cutover: the backlog page, classify_findings.py and the skills read that file, and editing a vault source re-distils all of it. Regenerate with scripts/drive/findings_to_vault.py.

Generated from scripts/drive/FINDINGS.md: 1164 sections. closed 817, open 221, note 92, not a defect 13, partly 9, addendum 8, deferred 4.

`stale?` means a commit subject on master names the finding as fixed while its own status does not. It is a hint, not a verdict.

| Finding | Sev | State | Hint | Title | File |
|---|---|---|---|---|---|
| F1 | A | closed |  | F1 (A) — One cron string, three different answers; the one on screen is wrong | findings-02-closed-1.md |
| F2 | B | closed |  | F2 (B) — "Server time" is a UTC clock wearing a local label | findings-02-closed-1.md |
| F3 | C | closed |  | F3 (C) — `contact_mode` still defaults to `"watchdog-spawn"` | findings-02-closed-1.md |
| F4 | C | closed |  | F4 (C) — A fresh project does not adopt the main branch it can already see | findings-02-closed-1.md |
| F5 | A | closed |  | F5 (A) — The hop budget is defeated by any operator message, and the counter resets | findings-02-closed-1.md |
| F6 | B | closed |  | F6 (B) — A task being actively worked shows no assignee and an idle assignee-status | findings-02-closed-1.md |
| F7 | C | closed |  | F7 (C) — Duplicate evidence for one requirement is accepted without comment | findings-02-closed-1.md |
| F8 | C | closed |  | F8 (C) — Two refusals, two standards of helpfulness | findings-02-closed-1.md |
| F9 | A- | not a defect |  | F9 (A-) — Approval merges to master, and that is worth stating loudly | findings-02-closed-1.md |
| F10 | A | closed |  | F10 (A) — A reviewer agent cannot see the work it is reviewing | findings-02-closed-1.md |
| F11 | B | closed |  | F11 (B) — `run_count` counts firings that did nothing | findings-02-closed-1.md |
| F12 | A | closed |  | F12 (A) — `stop_when_queue_empties` waits for a human, and burns a firing a minute meanwhile | findings-02-closed-1.md |
| F13 | B | closed |  | F13 (B) — Re-enabling a finished loop is accepted, useless, and leaves a contradictory state | findings-02-closed-1.md |
| F14 | B | closed |  | F14 (B) — A task waiting on the operator still reads `in_progress` | findings-02-closed-1.md |
| F15 | C | open |  | F15 (C) — Stopping an agent does not stop the work | findings-01-open.md |
| F16 | C | closed |  | F16 (C) — `loop_id` is accepted on task creation but never echoed back | findings-02-closed-1.md |
| F17 | B | closed |  | F17 (B) — Every Hub-run agent says "No activity yet", forever | findings-02-closed-1.md |
| F18 | B | closed |  | F18 (B) — Refinement of F6: the loop records an assignee, a direct trigger does not | findings-02-closed-1.md |
| F19 | C | closed |  | F19 (C) — A gated task is indistinguishable from an ordinary pending one | findings-02-closed-1.md |
| F20 | C | closed |  | F20 (C) — Deep links use query parameters, and nothing says so | findings-02-closed-1.md |
| F21 | B | closed |  | F21 (B) — A Haiku agent cannot reach `record_evidence`, and burns a whole turn trying | findings-02-closed-1.md |
| F22 | B | closed |  | F22 (B) — Shared dependencies are not symlinked on this machine, and nothing says so | findings-02-closed-1.md |
| F23 | A | closed |  | F23 (A) — A flow at full width reads as stalled with nothing to do | findings-02-closed-1.md |
| F24 | C | closed |  | F24 (C) — a refused firing's status label says `scheduled`, contradicting the reason beside it | findings-02-closed-1.md |
| F25 | C | closed |  | F25 (C) — a stalled job card reads `0 runs` with a run visible underneath | findings-02-closed-1.md |
| F26 | C | closed |  | F26 (C) — the board names a different agent than the task's assignee | findings-02-closed-1.md |
| F27 | A | closed |  | F27 (A) — a run can complete tasks it was never given and never did | findings-02-closed-1.md |
| F28 | B | closed |  | F28 (B) — a flow created after its document is approved has a permanently empty queue | findings-02-closed-1.md |
| F29 | B | closed |  | F29 (B) — an approved document tampered with on disk is served to everyone, silently | findings-02-closed-1.md |
| F30 | B | closed |  | F30 (B) — a self-registered agent bound to a runner reports a CLI named after itself | findings-02-closed-1.md |
| F31 | B | closed |  | F31 (B) — `_SECRET_VALUE_RE` redacts any 32-character identifier, including the Hub's own | findings-02-closed-1.md |
| F32 | B | closed |  | F32 (B) — an agent is told what it may do, never what it may not | findings-02-closed-1.md |
| F33 | B | closed |  | F33 (B) — a job for an agent that does not exist is created, enabled, and scheduled | findings-02-closed-1.md |
| F34 | B | closed |  | F34 (B) — `agentweave --port N status` is silently ignored; `status --port N` works | findings-02-closed-1.md |
| F35 | C | closed |  | F35 (C) — `submit_spec_document` answers a malformed call with raw Pydantic errors | findings-02-closed-1.md |
| F36 | C | closed |  | F36 (C) — dependencies can only be declared by an agent, inside a spec document | findings-02-closed-1.md |
| F37 | C | closed |  | F37 (C) — a document created by mistake is permanent, and becomes a standing warning | findings-02-closed-1.md |
| F38 | B | closed |  | F38 (B) — an agent that needs an answer ends its turn instead of asking | findings-02-closed-1.md |
| F39 | B | closed |  | F39 (B) — two of the three operator grants are announced in neither direction | findings-02-closed-1.md |
| F40 | B | closed |  | F40 (B) — `test_relocate_repairs_and_redrains_queued_work` is flaky, and has been all along | findings-02-closed-1.md |
| F41 | A | closed |  | F41 (A) — F38's fix cannot fire: every document has a `content_digest` from birth | findings-02-closed-1.md |
| F42 | C | closed |  | F42 (C) — F27 bounds the blast radius but a run can still claim work it will not do | findings-02-closed-1.md |
| F43 | A | closed |  | F43 (A) — the flow tells every agent to brief its reviewer, and no flow path delivers it | findings-02-closed-1.md |
| F44 | B | closed |  | F44 (B) — the reviewer is briefed by the loop's newest checkpoint, not the author's | findings-02-closed-1.md |
| F45 | A | closed |  | F45 (A) — a review that ends without moving the task is re-staffed on every tick, forever | findings-02-closed-1.md |
| F46 | B | closed |  | F46 (B) — the review turn named a transition the task could not make | findings-02-closed-1.md |
| F47 | C | closed |  | F47 (C) — the flow's own routing is recorded as the operator's | findings-02-closed-1.md |
| F48 | B | closed |  | F48 (B) — pressing Run on a healthy flow reported "Failed to fire job" | findings-02-closed-1.md |
| F49 | A | closed |  | F49 (A) — `agent_role` could never say `working` | findings-02-closed-1.md |
| F50 | B | closed |  | F50 (B) — a checkpoint that failed its own probe is briefed to the reviewer as though it passed | findings-02-closed-1.md |
| F51 | A | closed |  | F51 (A) — "start exploration" orphans its own document; the agent writes a second one | findings-02-closed-1.md |
| F52 | A | closed |  | F52 (A) — the "workspace" permission posture never sees a git command; every commit is refused, silently, with no operator visibility | findings-02-closed-1.md |
| F53 | B | closed |  | F53 (B) — archiving a loop that never fired still permanently, irrevocably claims its spec document; the tasks it "adopted" have no recovery path | findings-02-closed-1.md |
| F54 | A | closed |  | F54 (A) — a job-creation request that 409s on a document conflict has already committed an enabled, spendable job; the error response is not the rollb | findings-02-closed-1.md |
| F55 | B | closed |  | F55 (B) — an unprovoked, intermittent test failure, and a real "which checkpoint is newest" tie-break bug behind it (Windows clock resolution) | findings-02-closed-1.md |
| F56 | A | closed |  | F56 (A) — one review target with no evidence permanently wedges an agent's entire inbound queue, silently | findings-02-closed-1.md |
| F57 | A | closed |  | F57 (A) — a rejection has no way to say why: `update_task` drops `notes` entirely | findings-02-closed-1.md |
| F58 | A | closed |  | F58 (A) — approving one task's evidence merges its agent's *entire branch history*, including other unapproved tasks' work and scratch debris, not "th | findings-02-closed-1.md |
| F59 | B | closed |  | F59 (B) — the same clock-tick tie-break bug as F55, in a second table: an evidence review's "latest" can pick the older decision | findings-02-closed-1.md |
| F60 | A | closed |  | F60 (A) — An unanswered `ask_user` question that resolves itself mid-turn leaves the task reading `completed`, and the operator can still "answer" it  | findings-02-closed-1.md |
| F61 | B | closed |  | F61 (B) — every flow conversation has the same title, and no API says which turn is a review | findings-02-closed-1.md |
| F62 | C | closed |  | F62 (C) — a mixed-CLI flow reports its tokens in full and its money in part | findings-02-closed-1.md |
| F63 | B | closed |  | F63 (B) — the board says an agent is mid-turn on work nothing is running; two meanings of "in flight" collided | findings-02-closed-1.md |
| F64 | B | closed |  | F64 (B) — one unstaffable queue, two surfaces, two different causes, opposite remedies | findings-02-closed-1.md |
| F65 | C | closed |  | F65 (C) — a review briefing refused for having no evidence stays queued, and blocks archiving its agent | findings-02-closed-1.md |
| F66 | B | closed |  | F66 (B) — A batched turn's workspace and its run binding are decided by two different rules, and they can name different tasks | findings-02-closed-1.md |
| F67 | A | closed |  | F67 (A) — A divergence response is queued into a conversation that does not exist, so it can never be delivered | findings-02-closed-1.md |
| F68 | B | closed |  | F68 (B) — two spellings of one severity, and the louder event is the one that renders as routine | findings-02-closed-1.md |
| F69 |  | not a defect |  | F69 — `every-run-knows-its-task` groups 1-5 driven live, all five behaviours held (not a defect — the record the group asked for) | findings-02-closed-1.md |
| F70 | A | closed |  | F70 (A) — an operator can move a task to `under_review` without staffing a reviewer, and the flow reads that forever as a healthy review in progress — | findings-02-closed-1.md |
| F71 | A | closed |  | F71 (A) — operator-recorded evidence footprints the operator's own checkout, not the commit the operator named, and a downstream review silently gets  | findings-02-closed-1.md |
| F72 |  | closed |  | F72 — every checkpoint ever produced reported no changed files (severity A, fixed 2026-08-27) | findings-02-closed-1.md |
| F73 |  | closed |  | F73 — `ui_stale` is a false positive on any Windows checkout, and no rebuild can clear it | findings-02-closed-1.md |
| F74 |  | closed |  | F74 — evidence from a task-bound run does not carry the task, so its own review turn refuses it | findings-02-closed-1.md |
| F75 |  | closed |  | F75 — a reviewer's independent confirmation is refused as a duplicate of the author's claim | findings-02-closed-1.md |
| F76 |  | closed |  | F76 — a review turn dispatched by hand dead-ends: the reviewer cannot record its verdict anywhere | findings-02-closed-1.md |
| F77 |  | open | stale? 1338b02 | F77 — an agent has no way to address the operator | findings-01-open.md |
| F78 |  | closed |  | F78 — the operator cannot clear a task's assignee, and the API reports that they did | findings-02-closed-1.md |
| F79 |  | closed |  | F79 — a task the operator has decided about still takes new runs | findings-02-closed-1.md |
| F80 |  | closed |  | F80 — `asker_waiting` is computed on one question route and hardcoded on the other four | findings-02-closed-1.md |
| F81 |  | closed |  | F81 — the operator's own refusal is written to the timeline twice | findings-02-closed-1.md |
| F82 |  | closed |  | F82 — creating a loop with initial tasks replies that its queue is empty | findings-02-closed-1.md |
| F83 |  | closed |  | F83 — a loop created enabled with `initial_tasks` never reaches the scheduler | findings-02-closed-1.md |
| F84 |  | closed |  | F84 — an operator who stops a loop stops nothing; it fires for another seventeen minutes | findings-02-closed-1.md |
| F85 |  | closed |  | F85 — a loop stages a review it cannot start, wedges the task, and fails on it forever | findings-02-closed-1.md |
| F86 |  | closed |  | F86 — an unattended loop inherits "ask me first" from a conversation the operator had hours ago | findings-02-closed-1.md |
| F87 | A | closed |  | F87 (A) — a message the Hub gives up on disappears, and the record of it says nothing | findings-02-closed-1.md |
| F88 | A | closed |  | F88 (A) — two grants the operator can confer, and neither has ever done anything | findings-02-closed-1.md |
| F89 | A | closed |  | F89 (A) — turning on automatic checkpointing kills the turn that triggers it | findings-02-closed-1.md |
| F90 | A | closed |  | F90 (A) — a turn held back by another agent's turn is never let go again | findings-02-closed-1.md |
| F91 | A | closed |  | F91 (A) — restarting the Hub spends the operator's message, for a condition that had already passed | findings-02-closed-1.md |
| F92 | B | closed |  | F92 (B) — a run the Hub reconciles is billed to nobody, beside a total that says it is complete | findings-02-closed-1.md |
| F93 | A | closed |  | F93 (A) — a runner binary that is present but broken wedges its agent until the Hub is restarted | findings-02-closed-1.md |
| F94 | B | closed |  | F94 (B) — kill an agent and the product tells you `exit 4294967295`, again | findings-02-closed-1.md |
| F95 | A | closed |  | F95 (A) — a project can be moved exactly until its first turn, and never again | findings-02-closed-1.md |
| F96 | A | closed |  | F96 (A) — the product names the remedy, the operator performs it, and nothing happens | findings-02-closed-1.md |
| F97 | B | closed |  | F97 (B) — the reason a turn is waiting exists, is correct, and never reaches the operator | findings-02-closed-1.md |
| F98 | A | closed |  | F98 (A) — "Full access" is the *least* permissive posture a Codex agent can be given | findings-02-closed-1.md |
| F99 | B | closed |  | F99 (B) — the Effort control does nothing on the transport Codex agents actually use | findings-02-closed-1.md |
| F100 | A | closed |  | F100 (A) — a Codex turn that fails at the provider is recorded as a completed run with no output | findings-02-closed-1.md |
| F101 | A | closed |  | F101 (A) — the Hub's own MCP server can fail to start and the turn says nothing | findings-02-closed-1.md |
| F102 | B | closed |  | F102 (B) — the agent's plan is invisible on the transport every Codex agent uses | findings-02-closed-1.md |
| F103 | B | closed |  | F103 (B) — every context reading in the timeline rendered as the words `context_warning` | findings-02-closed-1.md |
| F104 |  | not a defect |  | F104 (—) — ThreadItem's eleven unhandled variants: swept live, none of them occur | findings-02-closed-1.md |
| F105 | B | closed |  | F105 (B) — the failure family: ten persisted event kinds render as their own bare name | findings-02-closed-1.md |
| F106 |  | not a defect |  | F106 (—) — `ask_user` on Codex: drives clean end to end, blocking and resumption both real | findings-02-closed-1.md |
| F107 | B | closed |  | F107 (B) — the Codex file-change approval card names a *category*, never the action: the operator approves "a file change" without seeing which file | findings-02-closed-1.md |
| F108 | B | closed |  | F108 (B) — a permanently refused request answers `200 {"success": true}` | findings-02-closed-1.md |
| F109 | B | closed |  | F109 (B) — the hub suite runs every session on one database connection, and the retry chain stalls because of it | findings-02-closed-1.md |
| F110 | B | closed |  | F110 (B) — `AW_CHECK_UI_BUNDLE=1` passes on a stale bundle if you skip the build | findings-02-closed-1.md |
| F111 | B | closed |  | F111 (B) — a self-registered agent with no runner is told to install a binary named after itself | findings-02-closed-1.md |
| F112 | B | closed |  | F112 (B) — creating a document with an unrecognised `kind` answers `500 Internal Server Error` | findings-02-closed-1.md |
| F113 | B | closed |  | F113 (B) — `propose` promises "every check that refuses it" and omits one of them | findings-02-closed-1.md |
| F114 | A | closed |  | F114 (A) — sending three messages to an agent that cannot launch destroys the first one | findings-02-closed-1.md |
| F115 | B | closed |  | F115 (B?) — RETIRED 2026-09-04 — the agent worktree is a working directory, not a boundary: an absolute path writes straight into the operator's check | findings-02-closed-1.md |
| F116 | B | closed |  | F116 (B) — the same API forbids an unknown field on one route and silently drops a safety-relevant one on another | findings-02-closed-1.md |
| F117 | B | closed |  | F117 (B) — `PATCH /agents/{name}` takes an untyped body: a misspelled setting answers 200 and changes nothing | findings-02-closed-1.md |
| F118 | B | closed |  | F118 (B) — every task id in every recorded transcript reads `ta<redacted>`, because `task-` ends in `sk-` | findings-02-closed-1.md |
| F119 | B | closed |  | F119 (B) — F31's repair landed in one of three copies of the same regex | findings-02-closed-1.md |
| F120 | C | closed |  | F120 (C) — a flow's claim of a task is recorded as an operator's transition, by nobody | findings-02-closed-1.md |
| F121 | C | closed |  | F121 (C) — one firing of a flow, two `JobRun` rows, and the badge says "2 runs" | findings-02-closed-1.md |
| F122 | B | closed |  | F122 (B) — a flow drives a task to `approved` by itself, and the work never reaches the branch — FIXED, NOT YET DRIVEN | findings-02-closed-1.md |
| F123 | C | open |  | F123 (C, open) — a crashed firing reads `failed` forever, including after the Hub itself retried it and the work succeeded | findings-01-open.md |
| F124 | B | closed |  | F124 (B) — a loop's work can never reach the main branch, and the card offers a retry that cannot succeed | findings-02-closed-1.md |
| F121 |  | addendum |  | F121, strengthened — the same word under-counts on a loop and over-counts on a flow | findings-02-closed-1.md |
| F125 | C | closed |  | F125 (C) — a task's title cannot be changed by anybody, and F116's fix is what made that visible | findings-02-closed-1.md |
| F126 | B | closed |  | F126 (B) — a spent checkpoint can be cut over again, and the second press mints a second successor that does the work a second time | findings-02-closed-1.md |
| F127 | B | closed |  | F127 (B) — pressing Run on a healthy loop whose agent is busy answers 500 "Failed to fire job" | findings-02-closed-1.md |
| F128 | B | closed |  | F128 (B) — a loop runs on an agent its job does not name, whenever its own agent is busy | findings-02-closed-1.md |
| F129 | B | closed |  | F129 (B) — requirement drift works, and the app cannot reach any of it | findings-02-closed-1.md |
| F130 | B | closed |  | F130 (B) — a checkpoint over an empty span makes the NEXT checkpoint re-summarise the whole conversation | findings-02-closed-1.md |
| F131 | A | closed |  | F131 (A) — Continue on one conversation starts a different conversation's work, and reports success against the one you pressed | findings-02-closed-1.md |
| F132 | C | closed |  | F132 (C) — drift has no agent-side half either, and the gate's remedy names an action no surface offers | findings-02-closed-1.md |
| F133 | B | closed |  | F133 (B) — the operator's own message erases the reason their agent is stalled | findings-02-closed-1.md |
| F134 | B | open |  | F134 (B) — a charter with no content is injected as a bare heading, and the agent is reported fully configured | findings-01-open.md |
| F135 | C | closed |  | F135 (C) — the sweep harness reported its own wrong turn as a product defect, for the second time | findings-02-closed-1.md |
| F115 |  | closed |  | F115, reproduced independently — RETIRED IN PART 2026-09-04 — two identical triggers, one inside the boundary and one outside | findings-02-closed-1.md |
| F135 |  | addendum |  | F135, continued — three more of the sweep's own wrong turns, all in the live-turn harnesses | findings-02-closed-1.md |
| F136 | B | closed |  | F136 (B) — the fix that stopped the Hub naming a binary after your agent does not cover the agents that most need it | findings-02-closed-1.md |
| F137 | C | not a defect |  | F137 (C) — the harness that promised to spend no provider tokens had been spending them, and was measuring a different queue | findings-02-closed-1.md |
| F138 | B | closed |  | F138 (B) — three drive harnesses are hard-wired to a forbidden project, and one of them writes | findings-02-closed-1.md |
| F139 | B | open |  | F139 (B) — the agent reached for the host's `SendMessage`, and reported AgentWeave's own roster as unreachable | findings-01-open.md |
| F140 | A | closed |  | F140 (A) — a flow's briefing tells the agent to "finish the task and stop", and never tells it, or the Hub, what finishing means | findings-02-closed-1.md |
| F141 | C | closed |  | F141 (C) — the approval gate probes git, refuses, names the conflicting file, and then forgets it ever happened | findings-02-closed-1.md |
| F142 | A | closed |  | F142 (A) — a task the operator marks finished can never be reviewed by its flow, and the stall blames the queue instead | findings-02-closed-1.md |
| F143 | B | closed |  | F143 (B) — the reviewer is told to build the thing it is reviewing, and said so itself | findings-02-closed-1.md |
| F144 | C | not a defect |  | F144 (C) — row 13's other half holds, and the one red check was the harness looking for the note on a surface that cannot carry one | findings-02-closed-1.md |
| F145 |  | not a defect |  | F145 — row 19 driven at last: a hard Hub kill loses nothing, and the harness had been asking about the wrong process | findings-02-closed-1.md |
| F146 | B | closed |  | F146 (B) — the operator's own question route accepts `blocking`, tells the panel an agent is waiting, and throws the answer away | findings-02-closed-1.md |
| F147 | B | open |  | F147 (B) — the startup pass that re-queues a crashed job firing writes that firing off as failed one line later, and nothing ever corrects it | findings-01-open.md |
| F148 |  | not a defect |  | F148 — the last two row-19 crosses drive clean: an expired card, and an input the Hub gives up on | findings-02-closed-1.md |
| F149 | C | closed |  | F149 (C) — `job_fired` publishes a JobRun id under the key `run_id`, next to real run ids on the same stream | findings-02-closed-1.md |
| F150 |  | not a defect |  | F150 — the crash-ordering seam drives clean: a dead-window follow-up is delayed by exactly one turn, not stranded | findings-02-closed-1.md |
| F151 |  | closed |  | F151 — running migrations at startup silences the Hub's logging, and uvicorn's, for the life of the process — FIXED | findings-02-closed-1.md |
| F152 | B | closed |  | F152 (B) — every gate refusal reaches an agent as a Python dict repr, and the fix is three lines — FIXED | findings-02-closed-1.md |
| F153 |  | not a defect |  | F153 — **the flow lands its work.** Driven end to end, and it does | findings-02-closed-1.md |
| F152 |  | addendum |  | F152 driven — the refusal reaches the agent as a sentence | findings-02-closed-1.md |
| F154 | A | closed |  | F154 (A) — a review that ends without a verdict wedges the task forever, and the flow answers "nothing is wrong" | findings-02-closed-1.md |
| F155 | A | closed |  | F155 (A) — "Resolve the conflict on the branch, then approve" cannot be followed, by anybody | findings-02-closed-1.md |
| F156 | B | closed |  | F156 (B) — `integration-preview` says `will_merge: true` for a task approval refuses outright | findings-02-closed-1.md |
| F157 | C | closed |  | F157 (C) — a loop field on `POST /jobs` is silently dropped; the same field on `PATCH` is refused | findings-02-closed-1.md |
| F158 | B | closed |  | F158 (B) — a task branch cut before its prerequisite was approved never gets that prerequisite's work | findings-02-closed-1.md |
| F159 | B | closed |  | F159 (B) — design D12's `approved` filter, applied to both merge routes, would have stopped prerequisite work that reaches successors today | findings-02-closed-1.md |
| F160 | C | closed |  | F160 (C) — the tool-surface parity tests cannot see an *optional* argument the inventory omits | findings-02-closed-1.md |
| F161 | D | closed |  | F161 (D) — a loop that declares its work needs no evidence still stalls asking for evidence | findings-02-closed-1.md |
| F162 | D | closed |  | F162 (D) — a task reads `completed` before its work is committed, and the tip in that window is the base commit | findings-02-closed-1.md |
| F163 | D | closed |  | F163 (D) — landing a loop's work costs the operator three hand transitions, and two of them are refusals | findings-02-closed-1.md |
| F164 | D | closed |  | F164 (D) — the flow still lands its work after groups 4 and 5, and F154's cause fired again on the way | findings-02-closed-1.md |
| F154 |  | addendum |  | F154 reproduced deterministically, with no agent turn at all — and the reproduction is `scripts/drive/t_f154_wedged_review.py` | findings-02-closed-1.md |
| F167 | B | closed |  | F167 (B) — the F70/F142 recovery cannot see an author whose history is entirely the operator's | findings-02-closed-1.md |
| F156 |  | addendum |  | F156 reproduced deterministically — and the contrast lane is what turns it from a rough edge into a defect | findings-02-closed-1.md |
| F167 |  | closed |  | F167's bound is now measured — the recovery DOES fire when one edge names an agent | findings-02-closed-1.md |
| F165 |  | closed |  | F165 addendum, measured 2026-08-31 (iteration 16) — the unknown branch has **two** spellings, and the merge path knows neither | findings-02-closed-1.md |
| F154 |  | addendum |  | F154 — Status: **FIXED** (`001a07d`, driven 2026-08-31), and the finding was wrong in one place | findings-02-closed-1.md |
| F169 | C | closed |  | F169 (C) — the approval advisory is produced for the operator and reaches no surface, then is unrecoverable | findings-02-closed-1.md |
| F170 | C | closed |  | F170 (C) — the Hub's own project marker is the one working file it leaves untracked | findings-02-closed-1.md |
| F171 | B | closed |  | F171 (B) — the identity-conflict screen offers the right remedy under the wrong explanation | findings-02-closed-1.md |
| F172 | B | closed |  | F172 (B) — relocating onto a path another project still claims answers a bare 500 | findings-02-closed-1.md |
| F173 | A | closed |  | F173 (A) — RETIRED 2026-09-02 — runner management is free-typed text that swallows its own refusal, and the spec says otherwise | findings-02-closed-1.md |
| F174 | B | closed |  | F174 (B) — the Codex catalog has drifted from the file it says it is copied from, and the drift includes the default | findings-02-closed-1.md |
| F175 | C | closed |  | F175 (C) — the model refusal is the one gate in the catalog that names nothing that would work | findings-02-closed-1.md |
| F176 | C | closed |  | F176 (C) — the API creates a nameless runner the dialog refuses to create | findings-02-closed-1.md |
| F177 | C | closed |  | F177 (C) — the runner list's "order by creation" silently becomes "order by name" about half the time | findings-02-closed-1.md |
| F178 | B | closed |  | F178 (B) — the collaboration-readiness report the Hub computes on every call reaches no screen, and has not since 2026-08-08 | findings-02-closed-1.md |
| F179 | B | closed |  | F179 (B) — an agent that cannot run at all is presented as a neutral dropdown value | findings-02-closed-1.md |
| F180 | C | closed |  | F180 (C) — the archive refusal offers only the destructive remedy, and drops the reason the non-destructive one exists | findings-02-closed-1.md |
| F181 | C | closed |  | F181 (C) — `GET /agents/launchability` does not apply the lifecycle filter, and its docstring says it feeds a selector | findings-02-closed-1.md |
| F182 | C | closed |  | F182 (C) — F175's refusal, restated at a second site, still naming nothing that would work | findings-02-closed-1.md |
| F183 | C | open |  | F183 (C) — charter names have no uniqueness rule anywhere, and the one place a charter is chosen shows nothing else | findings-01-open.md |
| F184 | C | closed |  | F184 (C) — a whitespace-only charter name is accepted by the API and renders as a blank row | findings-02-closed-1.md |
| F185 | B | closed |  | F185 (B) — a charter held only by an ARCHIVED agent cannot be deleted, and the refusal names an agent the roster does not show | findings-02-closed-1.md |
| F186 | B | closed |  | F186 (B) — the charter screen destroys authored text on one click, with no confirmation and no undo | findings-02-closed-1.md |
| F187 | B | closed |  | F187 (B) — the charter form swallows its own refusal: the operator clicks Save and is told nothing | findings-02-closed-1.md |
| F188 | A | closed |  | F188 (A) — RETIRED 2026-09-04 — a repairable workspace fault destroys the operator's message after three schedules, and the identical fault one line a | findings-02-closed-1.md |
| F189 | B | closed |  | F189 (B) — the Workspace section shows a path that does not exist, and calls it where the work happened | findings-02-closed-1.md |
| F190 | A | closed |  | F190 (A) — RETIRED 2026-09-03 — no turn can ever say it was stopped, failed or interrupted, because the status map is built backwards from a payload s | findings-02-closed-1.md |
| F191 | C | closed |  | F191 (C) — `Conversation is unavailable` is one sentence for three different causes and names no repair | findings-02-closed-1.md |
| F192 | C | closed |  | F192 (C) — stop reports an agent that does not exist as merely idle | findings-02-closed-1.md |
| F193 | B | closed |  | F193 (B) — an open conversation whose agent is archived vanishes from one rail view, survives in the other, and opens on the words "Agent unavailable. | findings-02-closed-1.md |
| F194 | C | closed |  | F194 (C) — the conversation and chat routes answer 200 for an agent that does not exist | findings-02-closed-1.md |
| F195 | C | closed |  | F195 (C) — the conversation titler does not run in the project's directory, and the parameter that would make it is dead | findings-02-closed-1.md |
| F196 | B | closed |  | F196 (B) — one route writes a value another route's response model cannot serialise, and the project settings page is then unreachable in both directi | findings-02-closed-1.md |
| F197 | B | closed |  | F197 (B) — the settings page has no error state, so a failing settings query renders a loading skeleton forever | findings-02-closed-1.md |
| F198 | C | closed |  | F198 (C) — `PATCH /queue/settings` silently resets the two fields a body omits | findings-02-closed-1.md |
| F199 | C | closed |  | F199 (C) — `GET /queue/{agent}` and `/queue/{agent}/status` answer 200 for an agent that does not exist | findings-02-closed-1.md |
| F200 | C | closed |  | F200 (C) — one refusal string for four distinguishable states, and it asserts a delivery that never happened | findings-02-closed-1.md |
| F201 | C | closed |  | F201 (C) — an illegal move to `blocked` is refused as **malformed** rather than as illegal, and the sentence tells the caller to send more | findings-02-closed-1.md |
| F202 | B | closed |  | F202 (B) — the Overview says "100 tasks" about a project with 241, and the board silently drops the newest work | findings-02-closed-1.md |
| F203 | C | closed |  | F203 (C) — nothing can read a task's transition history | findings-02-closed-1.md |
| F204 | C | closed |  | F204 (C) — the phase route is the one door in the machine that refuses a call with no body, and it refuses it as *malformed* | findings-02-closed-1.md |
| F205 | C | closed |  | F205 (C) — the two phase edges added for F37 are offered by no screen, and the documents they were added for are exactly the ones the UI will not arch | findings-02-closed-1.md |
| F206 | B | closed |  | F206 (B) — five of the spec flow's operator-only routes have no operator surface | findings-02-closed-1.md |
| F207 | C | closed |  | F207 (C) — two doors into `proposed`, and the second one skips the first one's checks | findings-02-closed-1.md |
| F208 | D | closed |  | F208 (D) — the arrange refusal names neither the cause nor the remedy | findings-02-closed-1.md |
| F209 | C | closed |  | F209 (C) — the accept route takes the operator's reason and throws it away | findings-02-closed-1.md |
| F210 | C | closed |  | F210 (C) — F204's shape, twice more: both proposal decisions refuse a bodyless call | findings-02-closed-1.md |
| F211 | C | closed |  | F211 (C) — F206's shape, three more routes with no operator surface | findings-02-closed-1.md |
| F212 | C | closed |  | F212 (C) — coverage reports `unserved` as bare identifiers, which are not unique in a project | findings-02-closed-1.md |
| F213 | D | closed |  | F213 (D) — a resubmitted edit stacks a duplicate proposal, and the twin can never be resolved | findings-02-closed-1.md |
| F214 | D | closed |  | F214 (D) — a retired requirement is reported `unserved`, which is the one thing it is not | findings-02-closed-1.md |
| F215 | B | closed |  | F215 (B) — the operator's screen tells them evidence is waiting for them and gives them nothing to press | findings-02-closed-1.md |
| F216 | C | closed |  | F216 (C) — the drift candidate names nothing its reader has ever seen | findings-02-closed-1.md |
| F217 | C | closed |  | F217 (C) — an agent's accepted evidence is never drift-checked in practice, and an operator's for the same requirement is | findings-02-closed-1.md |
| F218 | D | closed |  | F218 (D) — the create response omits the review it wrote one line earlier | findings-02-closed-1.md |
| F219 | C | closed |  | F219 (C) — RETIRED 2026-09-02 — a runner's model cannot be cleared, and the attempt is answered `200` | findings-02-closed-1.md |
| F220 | C | closed |  | F220 (C) — RETIRED 2026-09-02 — a runner whose model the catalog does not declare cannot be saved at all | findings-02-closed-1.md |
| F221 | D | closed |  | F221 (D) — the Hub refuses a model alias its own catalog declares | findings-02-closed-1.md |
| F222 | B | closed |  | F222 (B) — an archived job can be switched back on, and an archived loop then works a real task | findings-02-closed-1.md |
| F223 | C | closed |  | F223 (C) — `GET /jobs/{id}` reports a `source` the job does not have | findings-02-closed-1.md |
| F224 | C | closed |  | F224 (C) — a loop archived through its job is told "this loop is still running", forever | findings-02-closed-1.md |
| F225 | C | closed |  | F225 (C) — a loop's two operator-only actions have no operator surface | findings-02-closed-1.md |
| F226 | D | closed |  | F226 (D) — the job detail view's embedded history drops the two fields a failure is read by | findings-02-closed-1.md |
| F227 | B | closed |  | F227 (B) — the operator declines a question, then answers it, and a real turn is spent on it | findings-02-closed-1.md |
| F228 | C | closed |  | F228 (C) — a declined question never leaves the list the operator reads as "Unanswered" | findings-02-closed-1.md |
| F229 | D | closed |  | F229 (D) — the page named after questions is the one page that cannot decline one | findings-02-closed-1.md |
| F230 | C | closed |  | F230 (C) — Allow crosses the workspace boundary the product enforces everywhere else, and the card cannot say so | findings-02-closed-1.md |
| F231 | C | closed |  | F231 (C) — an approval leaves no record any screen can retrieve | findings-02-closed-1.md |
| F232 | D | closed |  | F232 (D) — `dismiss` accepts a card the operator answered, though its contract says only an expired one | findings-02-closed-1.md |
| F233 | D | closed |  | F233 (D) — a checkpoint warning can be dismissed before it is shown, and that silences it for good | findings-02-closed-1.md |
| F234 | D | closed |  | F234 (D) — taking the checkpoint answers a `due` warning and a `final` one, but not a dismissal | findings-02-closed-1.md |
| F235 | C | closed |  | F235 (C) — "Still bounded by each checkpoint's own visibility" is a bound that cannot exist | findings-02-closed-1.md |
| F236 | D | closed |  | F236 (D) — a stranded note is handed to a later checkpoint as though it were fresh | findings-02-closed-1.md |
| F237 | B | closed |  | F237 (B) — two controls set the project's token budget; the one in Settings leaves every surface that displays it stale | findings-02-closed-1.md |
| F238 | C | closed |  | F238 (C) — half of all budget changes are missing from the project's own activity history | findings-02-closed-2.md |
| F239 | C | closed |  | F239 (C) — the per-conversation usage rollup answers "0 tokens" for a conversation that does not exist | findings-02-closed-2.md |
| F240 | B | closed |  | F240 (B) — with the budget exhausted and "spending is paused" on screen, the Hub spent $0.042 that reaches no total and no budget | findings-02-closed-2.md |
| F241 | B | closed |  | F241 (B) — the conflict report is computed, correct, and read by nothing | findings-02-closed-2.md |
| F242 | B | closed |  | F242 (B) — one PATCH moves an agent off isolation mid-task, and its next task-bound turn writes uncommitted into the operator's checkout | findings-02-closed-2.md |
| F243 | C | closed |  | F243 (C) — a stored agent config cannot be cleared through the route that set it | findings-02-closed-2.md |
| F244 | C | closed |  | F244 (C) — the roster listing carries no `config`, so the setting that decides where an agent works is invisible on it | findings-02-closed-2.md |
| F245 | B | closed |  | F245 (B) — the conflict check never compares a task branch against the branch it will merge into | findings-02-closed-2.md |
| F246 | C | closed |  | F246 (C) — finishing a task takes its conflict off the report while the divergence remains | findings-02-closed-2.md |
| F247 | C | closed |  | F247 (C) — `GET /worktrees/{agent}` invents a workspace for an agent that does not exist | findings-02-closed-2.md |
| F248 | C | closed |  | F248 (C) — an agent legally named `conflicts` can never have its workspace read | findings-02-closed-2.md |
| F249 | D | closed |  | F249 (D) — the worktrees list cannot say "this project is not a repository" | findings-02-closed-2.md |
| F250 | D | closed |  | F250 (D) — nothing invalidates the worktrees query, so the panel does not notice a checkout being created | findings-02-closed-2.md |
| F251 | B | open | stale? 48eede3 48eede3 | F251 (B) — the Hub broadcasts 17 event names the client discards before any listener, 9 of them into handling code written for them | findings-01-open.md |
| F252 | B | closed |  | F252 (B) — the Logs screen renders the oldest 500 events a project ever recorded, and can never show a newer one | findings-02-closed-2.md |
| F253 | B | closed |  | F253 (B) — a subscriber that falls behind loses events silently: 1,426 of 3,000, twice, with no gap on the wire and no disconnect | findings-02-closed-2.md |
| F254 | C | closed |  | F254 (C) — an SSE ticket outlives the project it names, and opens a stream for a project that no longer exists | findings-02-closed-2.md |
| F255 | C | closed |  | F255 (C) — a malformed `since` is silently ignored, and the route answers as though no filter was asked for | findings-02-closed-2.md |
| F256 | D | closed |  | F256 (D) — the Logs screen's agent filter offers names that are on no roster | findings-02-closed-2.md |
| F257 | D | closed |  | F257 (D) — filtering by a severity that cannot exist answers 200 with an empty list | findings-02-closed-2.md |
| F258 | B | closed |  | F258 (B) — every message the operator sends through `POST /messages` is born one hop past the budget, and waits there until somebody releases it by ha | findings-02-closed-2.md |
| F259 | B | closed |  | F259 (B) — nothing in the product ever marks a message read, so the StatusBar's `N msgs` chip only ever counts up | findings-02-closed-2.md |
| F260 | C | closed |  | F260 (C) — row 17's whole operator surface is unreachable: three routes, three hooks, three components, none of them in the shipped app | findings-02-closed-2.md |
| F261 | C | closed |  | F261 (C) — the recipient is checked against the roster and the sender is not, so a name nobody registered becomes a listed agent | findings-02-closed-2.md |
| F262 | C | closed |  | F262 (C) — `GET /messages?conversation=` means an agent pair, and a real conversation id is silently ignored | findings-02-closed-2.md |
| F263 | D | closed |  | F263 (D) — `sort` accepts any string and quietly means ascending, and the default page is the oldest 100 messages | findings-02-closed-2.md |
| F264 | B | closed |  | F264 (B) — the query that decides what a loop is waiting on has no project filter, and the flag it depends on is never set | findings-02-closed-2.md |
| F265 | B | closed |  | F265 (B) — an agent's `create_loop` with `initial_tasks` is refused 403 *after* the loop and job it refused have been committed and left enabled | findings-02-closed-2.md |
| F266 | C | closed |  | F266 (C, was B) — a post-commit `db.refresh` can fail a run that already succeeded, and the queue then runs the agent's turn a second time | findings-02-closed-2.md |
| F267 | B | closed |  | F267 (B) — the model catalog is a compile-time literal behind a closed door, and it is already 28 days stale | findings-02-closed-2.md |
| F268 | B | closed |  | F268 (B) — the runner-binding select renders `name (cli)`, so the spec's own "second runner with a different model" is unpickable | findings-02-closed-2.md |
| F269 | C | closed |  | F269 (C) — RETIRED 2026-09-03 — a turn whose only agent output is a `status` row loses its "Worked for Xs" line, because the line renders inside the b | findings-02-closed-2.md |
| F270 | C | closed |  | F270 (C) — signal 1 has never fired for a Codex run, so a *cleanly completed* Codex turn still shows the 2026-08-18 lingering counter | findings-02-closed-2.md |
| F271 | A | closed |  | F271 (A) — a failed instructions load renders an empty editor with Save enabled, and one click destroys the project's instructions | findings-02-closed-2.md |
| F272 | C | closed |  | F272 (C, was B) — the terminal status row phase 2 exists to persist is silently lost ~10% of the time, because `record_agent_output` cannot re-read th | findings-02-closed-2.md |
| F273 | B | closed |  | F273 (B) — the one write whose purpose is to outlive the process is the one whose failure nothing surfaces | findings-02-closed-2.md |
| F274 | A | closed |  | F274 (A) - a turn's outcome is erased by work in the agent's *other* conversations | findings-02-closed-2.md |
| F275 | C | closed |  | F275 (C) - an abandoned operator message renders after the failures it caused | findings-02-closed-2.md |
| F276 | C | closed |  | F276 (C) - `agent_wide`'s documented example was never marked `agent_wide`, and no site sets both flags | findings-02-closed-2.md |
| F277 | C | closed |  | F277 (C) - `restrict_spec_writes` omits `MultiEdit`, the one write tool that edits a file the same way the three it names do | findings-02-closed-2.md |
| F278 | C | closed |  | F278 (C) - a deep POSIX file path in a recorded transcript reads `<redacted>.py`, because `/` is inside the high-entropy class | findings-02-closed-2.md |
| F279 | C | closed |  | F279 (C) - the two "a stopped run" tests fail about half the time, on an unmodified tree | findings-02-closed-2.md |
| F280 | C | closed |  | F280 (C) - an agent's recording response reports no footprint, so the recorder is the one party who cannot see what their evidence was attached to | findings-02-closed-2.md |
| F281 | B | closed |  | F281 (B) - a shell command's writes are never recorded, in any posture, and the boundary that refuses some of them is the only thing that ever sees on | findings-02-closed-2.md |
| F282 | C | closed |  | F282 (C) - a junction inside the workspace is correctly classified as outside and correctly refused; what is wrong is the path both of them then print | findings-02-closed-2.md |
| F283 | B | closed |  | F283 (B) - the Permissions pill sits on "Edit files" while the run it describes is spawned under "Workspace only" | findings-02-closed-2.md |
| F284 | C | closed |  | F284 (C) - the permission card the operator answers gives them no way to see that the path leaves the run's workspace | findings-02-closed-2.md |
| F285 | B | closed |  | F285 (B) - the hub suite's in-memory engine shares one connection across every session, so any request that finishes rolls back whatever a background  | findings-02-closed-2.md |
| F286 | B | closed |  | F286 (B) - an exception after a run reaches its terminal status leaves the input queued behind it undrained, and nothing is on a timer to notice | findings-02-closed-2.md |
| F287 | C | closed |  | F287 (C) - `record_agent_output` refreshes a row it has already fully populated, one extra SELECT per output line on the Hub's hottest write path | findings-02-closed-2.md |
| F288 | B | closed |  | F288 (B) - a Hub restart ends a run without releasing anything but that run's own agent, so an agent parked on the crashed run's task checkout is stra | findings-02-closed-2.md |
| F289 | C | closed |  | F289 (C) - the queue status route repeats a refusal's own sentence as the current reason long after it stopped being true | findings-02-closed-2.md |
| F290 |  | closed |  | F290 (RETRACTED, was B) - a run interrupted at Hub restart broadcasts its outcome to nobody, and the client refetches anyway | findings-02-closed-2.md |
| F291 | C | closed |  | F291 (C) - a run that fails before its process spawns tells the conversation nothing, and the one path where that is total leaves the turn silent | findings-02-closed-2.md |
| F292 | B | closed |  | F292 (B) - the fix for F285 traded a deterministic rollback for an intermittent lock, and the mitigation written for it did not hold | findings-02-closed-2.md |
| F293 | B | closed |  | F293 (B) — the F126 guard is on the predecessor's lifecycle, so following the refusal's own advice mints the duplicate successor it was built to preve | findings-02-closed-2.md |
| F294 | B | closed |  | F294 (B) — two cutover presses at the same instant both succeed: the guard reads the lifecycle it is about to write, with nothing serialising the two | findings-02-closed-2.md |
| F295 | A | closed |  | F295 (A) - a cancelled or superseded run's background task can leave a permanently dead worker thread, and any later reuse of its connection hangs for | findings-02-closed-2.md |
| F296 | C | closed |  | F296 (C, harness) - a drive assertion that can never be non-zero was reported as evidence about the product | findings-02-closed-2.md |
| F297 | B | closed |  | F297 (B) — `agentweave stop` on Windows force-kills the Hub, so nothing the shutdown sequence does ever runs | findings-02-closed-2.md |
| F298 | C | closed |  | F298 (C) — stopping the Hub normally reports the operator's own stop as an `ERROR ... Unhandled error in run`, with a traceback | findings-02-closed-2.md |
| F299 | A | deferred | stale? d82ae06 | F299 (A) — a `claude` run whose harness has no MCP cannot write a file, and blames the operator's machine for it | findings-01-open.md |
| F300 | A | closed |  | F300 (A) — the Hub's own workspace approver denies every shell command containing a URL, including the one its own notice instructs | findings-02-closed-2.md |
| F301 | A | deferred | stale? d82ae06 | F301 (A) — on the `cli` access path a `claude` run has no tool that can make the request it is told to make | findings-01-open.md |
| F302 | B | closed |  | F302 (B) — an agent's *first* turn is told "no MCP tools this turn" while it is holding them, and one measured turn believed it | findings-02-closed-2.md |
| F303 | B | closed |  | F303 (B) — four drive scripts kept defaulting a Hub key for a day after the sweep that removed it, and the guard could not see them because the litera | findings-02-closed-2.md |
| F304 | C | closed |  | F304 (C) — a run cancelled by shutdown stores an empty string as its reason | findings-02-closed-2.md |
| F305 | B | closed |  | F305 (B, harness) — a decision the operator has answered is re-asked, because the authority file is not what the windows read | findings-02-closed-2.md |
| F306 | A | closed |  | F306 (A) — an agent can be staffed to review, and approve, work it recorded evidence for | findings-02-closed-2.md |
| F307 | B | closed |  | F307 (B) — a confirmation dialog's first Tab leaves the panel, into the editor behind the scrim | findings-02-closed-2.md |
| F308 | B | closed |  | F308 (B) — pinning CI to the resolution buys agreement by spending the drift alarm, and nothing replaced it | findings-02-closed-2.md |
| F309 | A | closed |  | F309 (A) — the blocking-reason input never gets focus, so the operator's reason is typed into the status menu and each space re-opens it | findings-02-closed-2.md |
| F310 | B | closed |  | F310 (B) — one Escape dismisses two things: the ticket closes out from under the control the operator was actually cancelling | findings-02-closed-2.md |
| F311 | C | closed |  | F311 (C, bookkeeping) — `F307`'s table of affected dialogs is missing the call site where the hook actually misbehaves | findings-02-closed-2.md |
| F312 | A | closed |  | F312 (A) — the default posture forbids every network request a shell command can make, and calls it a filesystem escape | findings-02-closed-2.md |
| F313 | C | closed |  | F313 (C, harness) — the table recording a wrong verdict was read as making it, and six of the ledger's eight conflicts were false | findings-02-closed-2.md |
| F314 | B | closed |  | F314 (B) — `test_flow_holds_the_loop_requirements.py` fails about one run in eight under random ordering, on an unmodified tree | findings-02-closed-2.md |
| F315 | C | closed |  | F315 (C) — the button that blocks a ticket says nothing for the two seconds it takes, and a second press writes the move again | findings-02-closed-2.md |
| F316 | A | closed |  | F316 (A) — the reviewer resolved after a *silent* review excludes only the completer, so on operator-completed work it can pick the author | findings-02-closed-2.md |
| F317 | B | closed |  | F317 (B) — the finding classifier reads a domain verb in a section's own title as a status verdict, and prints the open severity-A count one short | findings-02-closed-2.md |
| F318 | B | closed |  | F318 (B) — the cross-section arm strips quotation one line at a time, so a quotation that wraps is read as prose | findings-02-closed-2.md |
| F319 | A | closed |  | F319 (A) — a review refused on the scheduler path leaves the refused reviewer holding the task | findings-02-closed-2.md |
| F320 | B | closed |  | F320 (B) — the scheduling pass that abandons a refused head returns, and the entry queued behind it is never delivered | findings-02-closed-2.md |
| F321 | A | closed |  | F321 (A) — under the default posture, a shell command naming a file in a subdirectory of its own workspace is refused as outside the workspace | findings-02-closed-2.md |
| F322 | B | open | stale? d82ae06 | F322 (B) — on Codex, "Workspace only" decides a command's network access by its working directory, so the same posture will answer a URL oppositely on | findings-01-open.md |
| F323 | A | closed |  | F323 (A) — on Windows, a traversal written in double quotes passes the default posture and writes outside the workspace | findings-02-closed-2.md |
| F324 | C | closed |  | F324 (C) — four form feeds in F304's body shift every line number the classifier prints after it | findings-02-closed-2.md |
| F325 | A | open |  | F325 (A) — on Codex's default transport a run never receives its canonical context, so a bound charter reaches no Codex agent | findings-01-open.md |
| F326 | D | closed |  | F326 (D) — a review turn refused after its checkout is provisioned leaves the checkout registered | findings-02-closed-2.md |
| F327 | B | closed |  | F327 (B) — a review a flow staffed and whose dispatch is then refused leaves the flow's reviewer holding the task, reported as in flight until the inp | findings-02-closed-2.md |
| F328 | D | closed |  | F328 (D) — input the operator withdraws while its turn is being dispatched is counted, given up on, and announced as dropped by the Hub | findings-02-closed-2.md |
| F329 | A | closed |  | F329 (A) — a first `agentweave` start builds a database no conversation can be written to | findings-02-closed-2.md |
| F330 | C | closed |  | F330 (C) — every refused send from the exploring composer leaves an empty specification document behind | findings-02-closed-2.md |
| F331 | A | closed |  | F331 (A) — on POSIX, the default posture allows any scheme URL in a shell command, and `curl -T x file:///…` writes outside the workspace | findings-02-closed-2.md |
| F332 | A | closed |  | F332 (A) — on POSIX, bash's ANSI-C quoting writes a traversal no reader of the command text sees | findings-02-closed-2.md |
| F333 | B | closed |  | F333 (B) — a `continue` whose pass gives up its conversation's input answers that the conversation "had nothing queued" | findings-02-closed-2.md |
| F334 | B | closed |  | F334 (B) — the author guard's refusal of a dispatched review names an assignment the rollback discarded | findings-02-closed-2.md |
| F335 | D | closed |  | F335 (D) — a review refused on dispatch still broadcasts that it resolved the task's open divergence | findings-02-closed-2.md |
| F336 | C | open |  | F336 (C) — no control in the app dispatches a review, so the check that asks the operator to "dispatch a review from the UI" cannot be done | findings-01-open.md |
| F337 | C | closed |  | F337 (C) — a refusal's path or command is recorded and never shown, and its activity line says the agent did the refusing | findings-02-closed-2.md |
| F338 | D | closed |  | F338 (D) — delivery reads an entry as queued and then marks it delivered by key, so a withdrawal that lands in between is answered 200 and delivered a | findings-02-closed-2.md |
| F339 | B | deferred | stale? 09127ba | F339 (B) — `acceptEdits` is path-confined by Claude Code on a headless run, and four places in the repository, one of them a binding verdict's reason, | findings-01-open.md |
| F340 | B | deferred |  | F340 (B) — the Hub's MCP grounds are positive-only and permanent, while the harness reports the server's state on every run and the Hub parses none of | findings-01-open.md |
| F341 | A | closed |  | F341 (A) — every message to a Claude agent opens a Windows Terminal window, and it stays open | findings-02-closed-2.md |
| F342 | B | closed |  | F342 (B) — typing "..." in the composer shows the first dot vanish, while the message sends all three | findings-02-closed-2.md |
| F343 | B | closed |  | F343 (B) — the desktop window has no right-click menu, so a misspelt word can be underlined and never corrected | findings-02-closed-2.md |
| F344 | B | closed |  | F344 (B) — nothing in the desktop window can be selected, so an agent's answer cannot be copied | findings-02-closed-2.md |
| F345 | B | closed |  | F345 (B) — a pending question grows without bound in the composer's column, squeezing the conversation to nothing and pushing the composer off screen | findings-02-closed-2.md |
| F346 | C | closed |  | F346 (C) — the route-reachability instrument lets a sibling route's literal satisfy a `{param}` slot, so it undercounts clientless routes by one | findings-02-closed-2.md |
| F347 | B | closed |  | F347 (B) — a project whose repository has no commit yet refuses every agent turn with git's plumbing error, including the message asking the agent to  | findings-02-closed-2.md |
| F348 | B | closed |  | F348 (B) — following switches itself off during every running turn, so the newest text drifts below the fold (and under the question tray) | findings-02-closed-2.md |
| F349 | B | closed |  | F349 (B) — two agent triggers at the same moment can answer 500 "database is locked" while the message is delivered anyway | findings-02-closed-2.md |
| F350 | C | open |  | F350 (C) — below ~560px of height in a narrow window, the composer's send button is off the panel even with nothing pending | findings-01-open.md |
| F351 | A | closed |  | F351 (A) — the scheduler's job store shares the SQLite file and is driven synchronously on the event loop, so one lock collision loses a new job — or  | findings-02-closed-2.md |
| F352 | A | closed |  | F352 (A) — a flow counts an agent busy for holding any live task anywhere in the project, so backlog outside the flow starves it of reviewers — and th | findings-02-closed-2.md |
| F353 | B | closed |  | F353 (B) — the product tells the operator to "clear the assignee", and nothing in the app can; the one action that would work, "Land it", is never nam | findings-02-closed-2.md |
| F354 | B | closed |  | F354 (B) — the operator's live agents launch the MCP server from the development working tree, so an unattended loop's uncommitted edits reach them mi | findings-02-closed-2.md |
| F355 | B | closed |  | F355 (B) — a run that fails on the provider's session limit is re-delivered into the same exhausted allowance, and then its input is given up | findings-02-closed-2.md |
| F356 | B | closed |  | F356 (B) — an answer given after `ask_user`'s wait ended, while the asking run is still alive, is delivered to nobody | findings-02-closed-2.md |
| F357 | B | closed |  | F357 (B) — a flow's review turn tells its reviewer to approve, and says nothing about the evidence gate that will refuse it | findings-02-closed-2.md |
| F358 | B | closed |  | F358 (B) — evidence can be decided while the run that recorded it is still live, so the reviewer judges a commit the Hub is about to replace | findings-02-closed-2.md |
| F359 | B | closed |  | F359 (B) — a run killed by the Hub's own write is marked failed without the snapshot or re-point a finished run gets | findings-02-closed-2.md |
| F360 | B | closed |  | F360 (B) — the checkpoint probe asks for the tasks "assigned to this agent" while a loop checkpoint lists the loop's whole queue, so half of a flow's  | findings-02-closed-2.md |
| F361 | B | closed |  | F361 (B) — a peer message past the hop budget is suspended with no reason on its entry, and its sender is told it was sent | findings-02-closed-2.md |
| F362 | B | closed |  | F362 (B) — on Windows, the workspace guard reads the tail of any relative word that contains a `/` as an absolute path | findings-02-closed-2.md |
| F363 | B | closed |  | F363 (B) — `read_spec_document` cannot return a real specification in one tool result, and it refuses the document id the other tools take | findings-02-closed-2.md |
| F364 | C | closed |  | F364 (C) — `submit_checkpoint_notes` enforces caps its description never states, and the refusal names neither the entry nor the overshoot | findings-02-closed-2.md |
| F365 | B | closed |  | F365 (B) — a loop with two stuck reviews records both on every firing, because "unchanged" is judged against the loop's newest record rather than the  | findings-02-closed-2.md |
| F366 | C | closed |  | F366 (C) — an agent can set any task's assignee over HTTP, a field its MCP tool does not carry | findings-02-closed-2.md |
| F367 | B | closed |  | F367 (B) — a stall reason longer than 500 characters is stored, and then the job's run history answers 500 | findings-02-closed-2.md |
| F368 | B | closed |  | F368 (B) — a flow re-briefs an assigned, idle agent on every tick while that agent's queued turn cannot start | findings-02-closed-2.md |
| F369 | C | closed |  | F369 (C) — pressing Run stamps the requester onto an earlier firing's record when the firing wrote none | findings-02-closed-2.md |
| F370 | B | closed |  | F370 (B) — a held assignee is re-briefed every firing when input for an agent whose name sorts first also names its task | findings-02-closed-2.md |
| F371 | C | closed |  | F371 (C) — a review nobody is doing reads as attended while any agent has input naming the task, including input nothing will deliver | findings-02-closed-2.md |
| F372 | B | closed |  | F372 (B) — a loop whose agent is mid-turn queues a briefing for it on every firing when its queue is empty and another agent is free | findings-02-closed-2.md |
| F373 | B | closed |  | F373 (B) — pressing Run on a loop whose work is in flight answers with an earlier firing's stall reason | findings-02-closed-2.md |
| F374 | B | closed |  | F374 (B) — a review refused by the evidence gate is re-staffed to a second reviewer, who meets the same gate, and the surfaced reason blames staffing | findings-02-closed-2.md |
| F375 | A | closed |  | F375 (A) — a bare `..` argument has no separator, so rule 4 calls it "not a path" and never checks it | findings-02-closed-2.md |
| F376 | A | closed |  | F376 (A) — `create_flow` is refused for a setting the operator was never asked about, and the refusal promises an approval that is never requested | findings-02-closed-2.md |
| F377 | B | closed |  | F377 (B) — no operator surface creates a flow, and the one loop form cannot name a specification document | findings-02-closed-2.md |
| F378 | B | closed |  | F378 (B) — `request_agent` reads templates from a table no surface writes, and it is empty in every project on this Hub | findings-02-closed-2.md |
| F379 | B | closed |  | F379 (B) — the five settings that decide whether a collaboration can run are indistinguishable from the ones that pick a title style | findings-02-closed-2.md |
| F380 | A | partly |  | F380 (A) — two independent ways the day window silently fails to arm, and neither leaves anything to read | findings-01-open.md |
| F381 | C | closed |  | F381 (C) — a question nobody is waiting on outranks one an agent is blocked on, in that agent's own tray | findings-02-closed-2.md |
| F382 | C | open | stale? 09127ba 77d39f9 d95b5cd | F382 (C) — `pytest hub/tests/ -q` stalled indefinitely overnight with no error, and a same-morning rerun could not reproduce the stall | findings-01-open.md |
| F383 | C | closed |  | F383 (C) — the CI branch's own commits fail on a genuine flaky test, not only on the docs-only commits noted earlier | findings-02-closed-2.md |
| F384 | B | closed |  | F384 (B) — `submit_spec_document`'s validator reports one missing field at a time, not all of them | findings-02-closed-2.md |
| F385 | C | open |  | F385 (C) — closing and reopening the Hub window loses every browser-stored preference, and the theme falls back to light | findings-01-open.md |
| F386 | B | closed |  | F386 (B) — the Overview question card tells the operator an agent "is waiting" for questions nobody is waiting on, and keeps showing declined ones | findings-02-closed-2.md |
| F387 | B | closed |  | F387 (B) — the Overview question card shows one question, oldest first, so a non-urgent question hides a blocking one | findings-02-closed-2.md |
| F389 | C | open |  | F389 (C) — an allowed permission decision is persisted nowhere, so "the agent was never refused" is unfalsifiable | findings-01-open.md |
| F388 | A | closed |  | F388 (A) — a Hub started from source silently opens the operator's live database, and the code comment says it cannot | findings-02-closed-2.md |
| F390 | C | closed |  | F390 (C) -- `DELETE /runners/{id}` refuses with the same unfindable name F185 refuses with | findings-02-closed-2.md |
| F391 | C | closed |  | F391 (C) -- archiving an agent persists no event and broadcasts nothing, so the transition leaves no trace | findings-02-closed-2.md |
| F392 | B | closed |  | F392 (B) -- a change's "what must not move" group ticked a full-suite run whose evidence was never written down, and the regression it would have caug | findings-02-closed-2.md |
| F393 | B | closed |  | F393 (B) -- three runner registries disagree, the two that lie are the ones a reader finds first, and nothing marks them legacy | findings-02-closed-2.md |
| F394 | A | closed |  | F394 (A) -- `hub-test` does not error on `master`, it HANGS: three runs stopped dead at 13% and were killed by GitHub's 6-hour job timeout | findings-02-closed-2.md |
| F395 | B | closed |  | F395 (B) -- `POST /messages` treats every operator-sent message as if it were the deepest possible agent hop, and mislabels its origin | findings-02-closed-2.md |
| F396 | B | closed |  | F396 (B) -- the MISREPORT ratchet is keyed by file:line, was already decayed on the day its ceiling was measured, and its own warning tells the next r | findings-02-closed-2.md |
| F397 | D | closed |  | F397 (D) -- archiving an already-archived agent is a 200 that re-stamps `archived_at` and writes a second `agent_archived` event | findings-02-closed-2.md |
| F398 | C | closed |  | F398 (C) -- `dismiss-checkpoint-warning` accepts a conversation that was never warned, and the pre-emptive dismissal silences its first warning for go | findings-02-closed-2.md |
| F399 | D | closed |  | F399 (D) -- taking a checkpoint does not clear a `dismissed` warning, so the conversation is never offered another | findings-02-closed-2.md |
| F400 | B | closed |  | F400 (B) -- Run on a documentless loop whose agent is busy answers "no other agent is free" while another agent is free | findings-02-closed-2.md |
| F401 | B | closed |  | F401 (B) -- a bare variable or command substitution names a directory the shell judge never checks | findings-02-closed-2.md |
| F402 | B | closed |  | F402 (B) -- a PowerShell drive-qualified word (`Z:`) reaches the judge with its colon trimmed | findings-02-closed-2.md |
| F403 | B | closed |  | F403 (B) -- bash brace expansion assembles `..` that no rule sees | findings-02-closed-2.md |
| F404 | C | closed |  | F404 (C) -- `from agentweave.templates import *` raises: `__all__` names a constant nothing defines | findings-02-closed-2.md |
| F405 | C | closed |  | F405 (C) -- both `examples/*.py` raise `ImportError` on their first line, and no CI job runs them | findings-02-closed-2.md |
| F406 | D | closed |  | F406 (D) -- an auto-loaded agent rule guarantees every save passes through `validator.py`, which nothing imports | findings-02-closed-2.md |
| F407 | D | closed |  | F407 (D) -- a review-dispatch refusal on an `under_review` task starts a sentence in lowercase | findings-02-closed-2.md |
| F408 | C | closed |  | F408 (C) -- a CLI thread-race test reads a slow runner as a lock that lost its loser | findings-02-closed-2.md |
| F409 | A | closed |  | F409 (A) -- another agent's text can make a Claude turn read any file, before any tool call, past every posture | findings-02-closed-2.md |
| F410 | C | closed |  | F410 (C) -- a checkpoint or divergence delivery reaches the agent labelled `Agent "None"` | findings-02-closed-2.md |
| F411 | B | closed |  | F411 (B) -- the Jobs page's Run button discards the Hub's answer, so a declined Run shows the operator nothing | findings-02-closed-2.md |
| F412 | B | closed |  | F412 (B) -- pressing Run answers `200 {"success": true}` when no turn began | findings-02-closed-2.md |
| F413 | B | closed |  | F413 (B) -- a firing that fails with no row left behind is invisible, and Run calls it "nothing is wrong" | findings-02-closed-2.md |
| F414 | B | closed |  | F414 (B) — `create_loop` with `initial_tasks` still commits the loop and job before a task can be refused | findings-02-closed-2.md |
| F415 | C | closed |  | F415 (C) — `operator` is not a reserved agent name, and Round 3a gave it a meaning | findings-02-closed-2.md |
| F416 | C | closed |  | F416 (C) — `list_evidence` ignores `document` when no `identifier` is given | findings-02-closed-2.md |
| F417 | B | open | stale? 5876bb2 | F417 (B) — the Compact and New-session requests are saved but never reach the agent | findings-01-open.md |
| F418 | C | closed |  | F418 (C) — the loop tab fetches the loop's event history and shows none of it | findings-02-closed-2.md |
| F419 | B | closed |  | F419 (B) — the Overview tab's activity strip shows every project's events, and its warning dot never fires for the Hub's warnings | findings-02-closed-2.md |
| F420 | B | closed |  | F420 (B) — the checkpoint and probe worker runs `claude -p` with every default tool enabled, on untrusted transcript text | findings-02-closed-2.md |
| F421 | B | closed |  | F421 (B) — an `unwritten` checkpoint becomes the next checkpoint's anchor | findings-02-closed-2.md |
| F422 | C | closed |  | F422 (C) — the titler pays again for the same title after every turn | findings-02-closed-2.md |
| F423 | C | closed |  | F423 (C) — a declined handover's note never reaches that task's reviewer | findings-02-closed-2.md |
| F424 | B | closed |  | F424 (B) — when the approval gate's git calls raise, every approval surface answers a bare 500 | findings-02-closed-2.md |
| F425 | B | closed |  | F425 (B) — a read-only agent assigned a writing task writes into the operator's checkout | findings-02-closed-2.md |
| F426 | B | closed |  | F426 (B) — an evidence decision whose merge then fails answers a bare 500 after the decision is saved | findings-02-closed-2.md |
| F427 | B | closed |  | F427 (B) — a footprint watches the whole tree, so one commit raises a drift candidate for every piece of evidence | findings-02-closed-2.md |
| F428 | C | closed |  | F428 (C) — rejecting a proposal in the app leaves it on screen | findings-02-closed-2.md |
| F429 | C | closed |  | F429 (C) — the app records every rigor change with an empty reason | findings-02-closed-2.md |
| F430 | B | closed |  | F430 (B) — a drift candidate can be answered twice, and the second answer overwrites the first | findings-02-closed-2.md |
| F431 | C | closed |  | F431 (C) — an accept refused as stale commits `stale` and leaves the row on screen | findings-02-closed-2.md |
| F432 | C | closed |  | F432 (C) — evidence with no footprint row is never scanned and never reported | findings-02-closed-2.md |
| F433 | C | open |  | F433 (C) — only one unit of a multi-unit proposal can be accepted before its siblings go stale | findings-01-open.md |
| F434 | B | closed |  | F434 (B) — reindex and arrange write files before the database commit, so an `OSError` leaves files written and digests rolled back | findings-02-closed-2.md |
| F435 | C | closed |  | F435 (C) — a drift candidate is never superseded when its requirement is reworded, although the model says it is | findings-02-closed-2.md |
| F436 | B | closed |  | F436 (B) — any drift answer silences that exact change forever, whether or not the answer was true | findings-02-closed-2.md |
| F437 | B | closed |  | F437 (B) — an operator's review request queued for a busy reviewer leaves a flow's completed task in the pool, so a second review can be staffed | findings-02-closed-2.md |
| F438 | C | closed |  | F438 (C) — the holder check's "Let the review in flight finish" is false for a silent holder whose review ended without a verdict | findings-02-closed-2.md |
| F439 | C | closed |  | F439 (C) — input in a closed conversation counts as queued, so after the attended change such a task reads as in flight | findings-02-closed-2.md |
| F440 | B | closed |  | F440 (B) — a decided task's queued review entry is never released; it is refused up to three times, then withdrawn | findings-02-closed-2.md |
| F441 | C | closed |  | F441 (C) — after the attended change, Run can say "already being worked" for an idle assignee whose queued turn cannot start | findings-02-closed-2.md |
| F442 | C | open |  | F442 (C) — a flow review refused at a deferred dispatch (the run-end re-drain) does not finalize the firing's JobRun | findings-01-open.md |
| F443 | C | partly | stale? 1338b02 | F443 (C) — an agent can still set a task's holder, priority and description when it creates the task | findings-01-open.md |
| F444 | B | closed |  | F444 (B) — a worktree's shared dependency links make ordinary reads through them refused | findings-02-closed-2.md |
| F445 | C | open |  | F445 (C) — a link inside the workspace that points outside lists the outside file as a workspace file | findings-01-open.md |
| F446 | C | closed |  | F446 (C) — a plain path word with a colon in a later component is refused on Windows | findings-02-closed-2.md |
| F447 | B | closed |  | F447 (B) — `--tools ""` leaves the account's claude.ai connector tools on the worker and titler | findings-02-closed-2.md |
| F448 | C | closed |  | F448 (C) — the operator's `GET /spec/evidence` ignores `document` when no `identifier` is given | findings-02-closed-2.md |
| F449 | C | closed |  | F449 (C) — the tool-server pin's startup line is never printed: `hub.*` INFO is below the root level | findings-02-closed-2.md |
| F450 | B | closed |  | F450 (B) — an agent can claim and finish a task assigned to a different agent; `assignee` is not an authorization boundary | findings-02-closed-2.md |
| F451 | B | closed |  | F451 (B) — `spec_document_id` on a loop or flow takes a document's path or its id, unvalidated: the path form orphans the flow and slips past the one- | findings-02-closed-2.md |
| F452 | B | closed |  | F452 (B) — `read_spec_document` returns acceptance criteria nested per requirement, `submit_spec_document` takes them flat: an agent's read-then-resub | findings-02-closed-2.md |
| F453 | C | closed |  | F453 (C) — under `manual` posture, commands Claude Code pre-approves as trivial never reach the operator, and nothing says so | findings-02-closed-2.md |
| F454 | B | closed |  | F454 (B) — a Hub-launched agent can load the operator's personal Claude Code skills; a loop firing ran `e2e-loop` and started new loops and commits no | findings-02-closed-2.md |
| F455 | C | closed |  | F455 (C) — `agentweave doctor --port N` without `--profile` checks the default profile's database and reports it accessible | findings-02-closed-2.md |
| F456 | D | closed |  | F456 (D) — a budget-exhausted project runs an operator's trigger without saying the budget was passed over | findings-02-closed-2.md |
| F457 | C | closed |  | F457 (C) — a firing that loaded its loop before an edit was staged clears that edit's marker, and the edit is stranded | findings-02-closed-2.md |
| F21 |  | addendum |  | F21 addendum, 2026-09-25 sweep — the looping agent faked a success, and the workaround stamps the wrong commit | findings-02-closed-2.md |
| F458 | B | closed |  | F458 (B) — the surfaced reason for an operator-held review says "still running the turn ... this clears itself" after the turn has ended | findings-02-closed-2.md |
| F409 |  | addendum |  | F409 drive, 2026-09-27 (live Hub :8041, profile drive0927, Haiku, `claude` 2.1.280) -- tasks 4.1-4.2c of an-at-mention-an-agent-wrote-reads-no-file | findings-02-closed-2.md |
| F459 | B | closed |  | F459 (B) — `a-runner-choice-names-its-model`'s `RunnerPicker` wiring added a second, unhandled `useModelCatalog()` call site | findings-02-closed-2.md |
| F460 | B | closed |  | F460 (B) — `a-model-alias-is-a-model-choice`'s two agent-creation tests never mocked `shutil.which`, so they only ever passed with a real `claude` on  | findings-02-closed-2.md |
| F461 | B | closed |  | F461 (B) — a Codex agent's configured question wait never reaches `ask_user`; above 240 s the wait ends early and its report is refused | findings-02-closed-2.md |
| F462 | B | closed |  | F462 (B) — a specification turn on Codex app-server keeps its write tools | findings-02-closed-2.md |
| F463 | C | closed |  | F463 (C) — the provider quota hold picks the "newest" usage reading by wall clock, so a clock step back picks an old reading | findings-02-closed-2.md |
| F464 | C | closed |  | F464 (C) — `_where` resolves a UNC path over the network before deciding, stalling the deciding process ~21 s per path word | findings-02-closed-2.md |
| F465 | C | closed |  | F465 (C) — archived agents keep counting against the agent budget, so a project at its budget can only raise it | findings-02-closed-2.md |
| F466 | C | open |  | F466 (C) — a Copilot run's Workspace only judges only the commands Copilot asks about | findings-01-open.md |
| F467 | D | open |  | F467 (D) — facts about Copilot CLI that the exploration's appendix recorded wrongly | findings-01-open.md |
| F468 | C | closed |  | F468 (C) — an agent can message itself, and the message starts a new autonomous turn | findings-02-closed-2.md |
| F469 | C | open | stale? 80f2e50 | F469 (C) — the app neither shows nor edits a runner's flags | findings-01-open.md |
| F470 | D | closed |  | F470 (D) — `each-runner-cli-is-one-adapter`'s design.md predates a same-named function `a-copilot-agent-runs-over-acp` already added | findings-02-closed-3.md |
| F471 | D | closed |  | F471 (D) — `each-runner-cli-is-one-adapter`'s D2 assumed `RUNNER_CLIS`/`CATALOG` stay 2-wide; migration 0112 already widened both | findings-02-closed-3.md |
| F472 | D | open |  | F472 (D) — `each-runner-cli-is-one-adapter` task 2.3's own bullet says to delete `codex_appserver.uses_app_server`; its two real callers live in files | findings-01-open.md |
| F473 | C | closed |  | F473 (C) — `each-runner-cli-is-one-adapter` task 3.1/D5's literal 501-gate and `catalog_provider_for_runner` replacements would 501 every Copilot run, | findings-02-closed-3.md |
| F474 | C | closed |  | F474 (C) — `each-runner-cli-is-one-adapter` task 3.2's `resolve_access_path` deletion has three production callers its own text does not name | findings-02-closed-3.md |
| F475 | D | closed |  | F475 (D) — `each-runner-cli-is-one-adapter` task 3.6's "`runners.py:116-118` iterates `ADAPTERS`" bullet would drop Copilot from `GET /runners/launcha | findings-02-closed-3.md |
| F476 | C | open |  | F476 (C) — three Copilot-name branches remain outside the runner adapters, against the requirement the adapter change adds | findings-01-open.md |
| F477 | B | closed |  | F477 (B) — the shim notice invited a compound shell command the approver cannot give standing to, so "Ask me" carded every Copilot call | findings-02-closed-3.md |
| F478 | B | partly | stale? 0a0efa5 83b53b6 | F478 (B) — the workspace judge reads `key:value/path` inside a shell string as a URL whose path is outside the workspace | findings-01-open.md |
| F479 | D | closed |  | F479 (D) — slice 2's spec-turn exclusion list names a tool Copilot 1.0.88 does not have | findings-02-closed-3.md |
| F480 | C | open |  | F480 (C) — a hard-linked file inside the calls directory passes the calls-root rule | findings-01-open.md |
| F481 | C | open |  | F481 (C) — a Copilot conversation cannot be compacted on demand: `/compact` is sent as chat and charged | findings-01-open.md |
| F482 | C | open |  | F482 (C) — D8's quota recognition rests on the schema, not on a captured refusal | findings-01-open.md |
| F483 | A | closed |  | F483 (A) — A Copilot runner is "not signed in" on a machine where `copilot login` is current | findings-02-closed-3.md |
| F484 | B | closed |  | F484 (B) — a Copilot reviewer's `update_task` claims a subagent review that never ran | findings-02-closed-3.md |
| F485 | D | closed |  | F485 (D) — the GitHub MCP toggle's ask-me card never fires: Copilot's own session never sends `session/request_permission` for a built-in `github-mcp- | findings-02-closed-3.md |
| F486 | C | open |  | F486 (C) — a cross-change obligation lives only in the archived change: `worker-spend-counts-against-the-budget` never mentions the worker credit sums | findings-01-open.md |
| F487 | B | closed |  | F487 (B) — task 1.7c's own test rows ask for a cross-platform fix that regresses an already-shipped guarantee | findings-02-closed-3.md |
| F488 | B | closed |  | F488 (B) — a run's registered secret survives the scrub when Copilot's output splits it across two events | findings-02-closed-3.md |
| F489 | C | closed |  | F489 (C) — the Hub retries a Copilot turn three times on an authentication failure that cannot succeed on retry | findings-02-closed-3.md |
| F490 | B | closed |  | F490 (B) — a run's registered secret is not scrubbed from what the agent writes through its Hub tools | findings-02-closed-3.md |
| F491 | B | closed |  | F491 (B) — a Copilot review of this repository cannot finish: the review context asks for the test suite and the turn limit is 600 s | findings-02-closed-3.md |
| F492 | C | closed |  | F492 (C) — a full commit SHA in a tool's input is stored as `<redacted>` | findings-02-closed-3.md |
| F493 | B | closed |  | F493 (B) — the Hub test suite, run inside an agent's run, writes fake refusals into the live Hub | findings-02-closed-3.md |
| F494 | C | open |  | F494 (C) — a Copilot provider runner has never completed a turn with a valid key | findings-01-open.md |
| F495 | B | closed |  | F495 (B) — a task sent back for revision is reworked by its reviewer, not its author | findings-02-closed-3.md |
| F496 | C | closed |  | F496 (C) — "draft the next slice" fires at the slice's approval, before anything was built from it | findings-02-closed-3.md |
| F497 | C | closed |  | F497 (C) — a reviewer is not told that a rejected requirement will refuse its `approved` | findings-02-closed-3.md |
| F498 | C | open |  | F498 (C) — a real live Copilot checkpoint call recorded no credits: the single capture's | findings-01-open.md |
| F499 | A | closed |  | F499 (A) — approving a task whose requirements another task also serves merges the other task's commit, and the approved task's own work never lands | findings-02-closed-3.md |
| F500 | A | closed |  | F500 (A) — a reviewer records its own evidence during the review, which lifts C1b's rejected-requirement block, then approves over the operator's reje | findings-02-closed-3.md |
| F501 | B | closed |  | F501 (B) — the next slice is drafted from task statuses alone: the agent skipped `list_evidence`, missed two rejections and unmerged work, and called  | findings-02-closed-3.md |
| F502 | C | closed |  | F502 (C) — an agent learns the spec payload schema by trial and error: seven rejected submits in two turns, and a misplaced field is accepted silently | findings-02-closed-3.md |
| F503 | D | not a defect |  | F503 (D) — what held in the first real slice drive | findings-02-closed-3.md |
| F504 | B | closed |  | F504 (B) — a task sent back as `revision_needed` reaches its author with no reason, so a merge conflict loops | findings-02-closed-3.md |
| F505 | C | closed |  | F505 (C) — an agent that co-authored a task's fix and recorded evidence for it can approve it | findings-02-closed-3.md |
| F506 | D | not a defect |  | F506 (D) — what the acceptance drive measured | findings-02-closed-3.md |
| F507 | C | closed |  | F507 (C) — the Claude model catalog does not know Sonnet 5.5; a runner on `claude-sonnet-5-5` is refused | findings-02-closed-3.md |
| F508 | B | closed |  | F508 (B) — the planner promised a reviewer the document never declared; the flow staffed a leftover stub agent | findings-02-closed-3.md |
| F509 | A | closed |  | F509 (A) — slice 1 of "same-file tasks build in order" cannot fire for an `aw-tool` agent: it never sees the text that teaches it | findings-02-closed-3.md |
| F510 | B | closed |  | F510 (B) — a task on a loop whose work merges its branch tip can never be given a review turn | findings-02-closed-3.md |
| F511 | D | not a defect |  | F511 (D) — what the checks-gate acceptance drive measured | findings-02-closed-3.md |
| F512 | B | closed |  | F512 (B) — a test-first task can never pass a whole-suite check: red-by-design work is refused at approval | findings-02-closed-3.md |
| F513 | C | closed |  | F513 (C) — `record_evidence` refuses FR-N as ambiguous although the call names the task that fixes the document | findings-02-closed-3.md |
| F514 | D | closed |  | F514 (D) — `ask_user` refuses `multiSelect`; agents trained on Claude Code's own tool send it | findings-02-closed-3.md |
| F515 | B | closed |  | F515 (B) — approving a document writes its phase into the tracked file, and that write then blocks the document's own task merges | findings-02-closed-3.md |
| F516 | B | closed |  | F516 (B) — a check run's checkout is held to the 60s plumbing timeout, and its `error` is never retried | findings-02-closed-3.md |
| F517 | C | closed |  | F517 (C) — a reviewer run failed at spawn with `database is locked` | findings-02-closed-3.md |
| F518 | B | closed |  | F518 (B) — a check run checks work already on the main branch, and blames its failures on the task | findings-02-closed-3.md |
| F519 | B | closed |  | F519 (B) — a reviewer judges a dependent task's diff without its dependency's work, and sends correct work back | findings-02-closed-3.md |
| F520 | A | closed |  | F520 (A) — accepting one task's evidence merges it into main through another approved task that serves the same requirement | findings-02-closed-3.md |
| F521 | B | closed |  | F521 (B) — a half-made check worktree stays `locked` and refuses every later run | findings-02-closed-3.md |
| F522 | C | closed |  | F522 (C) — the integration preview counts commits already on the main branch as "will merge" | findings-02-closed-3.md |
| F523 | B | closed |  | F523 (B) — `list_tasks` returns every task in one result, and a real board spills it to `tool-results/` | findings-02-closed-3.md |
| F524 | C | closed |  | F524 (C) — on Windows the Hub wrote every specification document and the index with CRLF line endings | findings-02-closed-3.md |
| F525 | B | closed |  | F525 (B) — the first Scan for drift after the legacy backfill raises a candidate for most old evidence at once | findings-02-closed-3.md |
| F526 | B | closed |  | F526 (B) -- an `agentweave-mcp` started with no `HUB_URL` silently targets the operator's real Hub on `:8000` | findings-02-closed-3.md |
| F527 | C | closed |  | F527 (C) -- a change document names no capability, so reconciling an archived change into the corpus is a hand-written script | findings-02-closed-3.md |
| F528 | C | closed |  | F528 (C) -- `close-exploration` and `propose` answer 200 for a document whose content was refused | findings-02-closed-3.md |
| F529 | C | closed |  | F529 (C) -- operator evidence always pins the HEAD it was recorded at, never the commit that did the work | findings-02-closed-3.md |
| F530 | B | closed |  | F530 (B) -- under xdist a leaked `shutil.which` patch makes `pty_runner` spawn `/usr/bin/claude`, and CI's hub-test goes red by order | findings-02-closed-3.md |
| F531 | B | closed |  | F531 (B) -- a Hub Claude run loads the operator's own claude.ai connectors (Gmail, Drive, Calendar, Docs) | findings-02-closed-3.md |
| F532 | C | closed |  | F532 (C) -- the Hub cannot delete a specification document, a task or an agent | findings-02-closed-3.md |
| F533 | C | closed |  | F533 (C) -- a fold cannot amend or retire what a capability already says | findings-02-closed-3.md |
| F534 | C | closed |  | F534 (C) -- a merge into a capability answers with change-spec completeness findings | findings-02-closed-3.md |
| F535 | C | closed |  | F535 (C) -- re-approving an amended document leaves its tasks as the first approval made them | findings-02-closed-3.md |
| F536 | C | closed |  | F536 (C) -- a capability can be neither deleted nor retired, so the corpus cannot lose one | findings-02-closed-3.md |
| F537 | C | closed |  | F537 (C) -- the openspec corpus importer dropped every wrapped line of a scenario clause | findings-02-closed-3.md |
| F538 | C | closed |  | F538 (C) -- a checkpoint can fire on a context window that was never measured | findings-02-closed-3.md |
| F539 | C | closed |  | F539 (C) -- the checkpoint a successor receives drops the wait-ended mark on open questions | findings-02-closed-3.md |
| F540 | C | closed |  | F540 (C) -- a failed automatic checkpoint is invisible to the operator | findings-02-closed-3.md |
| F541 | C | closed |  | F541 (C) -- checkpoint token thresholds are checked against the wrong window, or not at all | findings-02-closed-3.md |
| F542 | C | closed |  | F542 (C) -- a spent checkpoint is still offered for cutover on the archived predecessor | findings-02-closed-3.md |
| F543 | C | closed |  | F543 (C) -- an agent's loop and flow rules exist only in the MCP adapter | findings-02-closed-3.md |
| F544 | C | closed |  | F544 (C) -- an explicit "Workspace only" Claude run without the tool server denies every prompted call | findings-02-closed-3.md |
| F545 | C | closed |  | F545 (C) -- an exploring spec turn is told two contradictory ways to ask its questions | findings-02-closed-3.md |
| F546 | C | closed |  | F546 (C) -- a declared task title is cut to 80 characters mid-word | findings-02-closed-3.md |
| F547 | C | closed |  | F547 (C) -- the fold draft is served for a change that is not approved | findings-02-closed-3.md |
| F548 | C | closed |  | F548 (C) -- a divergence recorded for a run whose task someone else decides never closes | findings-02-closed-3.md |
| F549 | C | closed |  | F549 (C) -- a multi-line prompt through a .cmd shim that adds its own arguments is cut, yet marked delivered | findings-02-closed-3.md |
| F550 | C | closed |  | F550 (C) -- an ordinary save strips corpus navigation and the map from a document's file | findings-02-closed-3.md |
| F551 | C | partly | stale? 6a0eaad | F551 (C) -- three small requirement-traceability defects | findings-01-open.md |
| F552 | C | closed |  | F552 (C) -- operator- and agent-facing text that describes things that no longer exist | findings-02-closed-3.md |
| F553 | C | partly | stale? 270c0ad | F553 (C) -- dead UI and parser code, and a built-in command that does nothing | findings-01-open.md |
| F554 | C | closed |  | F554 (C) -- the project header draws the rules two requirements say it must not, and the tests cannot see it | findings-02-closed-3.md |
| F555 | C | closed |  | F555 (C) -- the app-server path writes a run's closing status row outside `_record_observation`, untested | findings-02-closed-3.md |
| F556 | C | closed |  | F556 (C) -- "creator" names two different agents, so an operator-created loop never reports an outstanding message | findings-02-closed-3.md |
| F557 | C | open |  | F557 (C) -- agent budget is labelled a concurrency limit, and the Hub enforces it only when an agent staffs an agent | findings-01-open.md |
| F558 | C | closed |  | F558 (C) -- evidence retention is a stored policy nothing applies | findings-02-closed-3.md |
| F559 | C | closed |  | F559 (C) -- the project-page settings change shipped seven query reads that show a failure as a value | findings-02-closed-3.md |
| F560 | C | open |  | F560 (C) -- the close-exploration route outlived the gate it served | findings-01-open.md |
| F561 | C | closed |  | F561 (C) -- the project's `spec/journey.json` was discovered as a specification document | findings-02-closed-3.md |
| F562 | C | closed |  | F562 (C) -- the approval-warnings change's `drive-first` criterion names a shape its own rule cannot detect | findings-02-closed-3.md |
| F563 | B | closed |  | F563 (B) -- a flow reviewer whose verdict the evidence gate refuses waits on ask_user until it times out | findings-02-closed-3.md |
| F564 | C | closed |  | F564 (C) -- deleting a task deletes its divergence records, which the model says are never deleted | findings-02-closed-3.md |
| F565 | C | closed |  | F565 (C) -- the Hub's half of the single-segment project-name rule is untested | findings-02-closed-3.md |
| F566 | C | closed |  | F566 (C) -- the rule that a refusal fits every surface that records it was dropped with no test | findings-02-closed-3.md |
| F567 | C | closed |  | F567 (C) -- a failed link of a shared dependency directory into an agent's checkout is only logged | findings-02-closed-3.md |
| F568 | C | closed |  | F568 (C) -- two context routes have no caller | findings-02-closed-3.md |
| F569 | C | closed |  | F569 (C) -- `checkpoint_access.participants()` is called only from tests | findings-02-closed-3.md |
| F570 | C | closed |  | F570 (C) -- a loop's history does not record its creation or what was added to its queue | findings-02-closed-3.md |
| F571 | C | closed |  | F571 (C) -- a hand-made task's dependencies can be declared only through a REST route | findings-02-closed-3.md |
| F572 | C | closed |  | F572 (C) -- the conversation has no collapsing thinking section and no way to hide diagnostics | findings-02-closed-3.md |
| F573 | C | closed |  | F573 (C) -- a roadmap cannot leave a question for a later slice: every open question blocks proposing it | findings-02-closed-3.md |
| F574 | C | closed |  | F574 (C) -- a document written whole through the content route always warns "steps skipped" on approval | findings-02-closed-3.md |
| F575 | C | closed |  | F575 (C) -- the Claude runner's model catalog does not offer Sonnet 5.5 | findings-02-closed-3.md |
| F576 | C | closed |  | F576 (C) -- `test_the_slice_adds_no_migration` fails on any branch that carries a migration | findings-02-closed-3.md |
| F577 | C | closed |  | F577 (C) -- the task drawer's prerequisite picker read a failed task list as "no other tasks" | findings-02-closed-3.md |
| F578 | C | closed |  | F578 (C) -- a Claude conversation never shows thinking: the CLI sends thinking blocks with empty text | findings-02-closed-3.md |
| F579 | C | closed |  | F579 (C) -- a roadmap cannot show which of its slices are closed | findings-02-closed-3.md |
| F580 | C | closed |  | F580 (C) -- `approve_anyway` sent as a query parameter is silently ignored | findings-02-closed-3.md |
| F581 | C | closed |  | F581 (C) -- a worker's model answer is not kept, so a wrong judgement cannot be read after the fact | findings-02-closed-3.md |
| F582 | C | closed |  | F582 (C) -- an unknown API route answers 405 Method Not Allowed, not 404, to anything but GET | findings-02-closed-3.md |
| F583 | C | closed |  | F583 (C) -- `test_each_piece_is_one_spawn_and_one_firing` fails on this machine whatever the tree | findings-02-closed-3.md |
| F584 | C | closed |  | F584 (C) -- `spec_reconcile.latest` picks a random reconcile result when two are recorded within one clock tick | findings-02-closed-3.md |
| F585 | C | closed |  | F585 (C) -- `tests/test_skill_sync.py` fails on a clean tree: two skill mirrors are stale | findings-02-closed-3.md |
| F586 | B | closed |  | F586 (B) -- re-distilling a source re-opens a contradiction the operator resolved, and presumes the fact they overruled | findings-02-closed-3.md |
| F587 | B | closed |  | F587 (B) -- re-distilling a source replaces every fact with a new id, orphaning the decision and the requirements that cite them | findings-02-closed-3.md |
| F588 | C | closed |  | F588 (C) -- a spec-vault-check conflict against a fact the operator has since overruled stays on the spec page | findings-02-closed-3.md |
| F589 | B | closed |  | F589 (B) -- deleting a runner a manager job uses is allowed, and the job then silently does nothing | findings-02-closed-3.md |
| F590 | C | closed |  | F590 (C) -- the Manager page tells the operator a vault job without a runner uses "the agent's own runner" | findings-02-closed-3.md |
| F591 | C | closed |  | F591 (C) -- a file source whose transcription failed or has not run yet is shown as "Held on another machine" | findings-02-closed-3.md |
| F592 | C | closed |  | F592 (C) -- deleting a project leaves its private vault behind in the Hub's own directory | findings-02-closed-3.md |
| F593 | B | closed |  | F593 (B) -- folding a verified change leaves its requirements "unserved" in the capability, while the archived change keeps counting as verified | findings-02-closed-3.md |
| F594 | B | closed |  | F594 (B) -- an answered question can be answered again; the second answer overwrites the first, and after delivery it spends a new turn | findings-02-closed-3.md |
| F595 | B | closed |  | F595 (B) -- deleting the runner that project settings name leaves a dangling id; every later settings save is refused, and checkpoints say no runner i | findings-02-closed-3.md |
| F596 | B | closed |  | F596 (B) -- a job fired at an agent with no runner answers 500 and records the firing `failed`, but its message stays queued and runs as soon as a run | findings-02-closed-3.md |
| F597 | C | closed |  | F597 (C) -- the "May agents schedule work?" question stays open after the operator enables `allow_agent_jobs` in settings | findings-02-closed-3.md |
| F598 | A | closed |  | F598 (A) -- with `checkpoint_auto_continue` off, automatic checkpoints in a two-agent project feed each other through the project-wide redrain into a  | findings-02-closed-3.md |
| F599 | B | closed |  | F599 (B) -- a runner's `flags` silently override its model and the permission posture; a `--dangerously-skip-permissions` runner wrote outside the wor | findings-02-closed-3.md |
| F600 | B | closed |  | F600 (B) -- the Add-agent dialog binds whichever runner with the same cli and model the database returns first, a flagged one included | findings-02-closed-3.md |
| F601 | B | closed |  | F601 (B) -- Workspace-only allows writes to PowerShell provider drives (`HKCU:`, `Env:`, `Function:`) written without a separator, and says they are " | findings-02-closed-3.md |
| F602 | B | closed |  | F602 (B) -- an `aw_live_` key in an agent's reply text is stored and broadcast unredacted, while the same value in tool input and output is redacted | findings-02-closed-3.md |
| F603 | B | closed |  | F603 (B) -- a reviewer reviews pre-fix code: work from a mail turn that claimed its task mid-turn sits on the agent's branch, and the task's checkout  | findings-02-closed-3.md |
| F604 | B | closed |  | F604 (B) -- an automatic checkpoint summarises the turn as it stood at its first context reading, mid-turn, so every successor is told to redo work th | findings-02-closed-3.md |
| F605 | B | closed |  | F605 (B) -- the checks gate charges a task with failures already on main; the reviewer is told to send correct work back, and the override has no cont | findings-02-closed-3.md |
| F606 | B | closed |  | F606 (B) -- a reviewer turn can undo its own send-back and complete the author's task, after which the flow refuses to review it | findings-02-closed-3.md |
| F607 | B | closed |  | F607 (B) -- a reconcile pass (and every untasked turn) reads the agent's own worktree, which is never brought up to main; it recorded three false "mis | findings-02-closed-3.md |
| F608 | B | closed |  | F608 (B) -- a job fired on a spent token budget answers 500 and records the firing `failed`, but its entry stays queued and runs once the budget is ra | findings-02-closed-3.md |
| F609 | B | closed |  | F609 (B) -- deleting a project and reopening its folder resurrects the same project id and its "permanently" deleted private vault content | findings-02-closed-3.md |
| F610 | B | closed |  | F610 (B) -- the private vault location may be set inside another registered project or any git work tree, and saving it creates the directory | findings-02-closed-3.md |
| F611 | B | closed |  | F611 (B) -- at contract/gate rigor the operator's own edit becomes a pending proposal that approval neither lists nor blocks; it then goes stale and d | findings-02-closed-3.md |
| F612 | B | closed |  | F612 (B) -- adopting a hand-placed `spec.json` indexes none of its requirements, and nothing but an agent's read says so | findings-02-closed-3.md |
| F613 | B | closed |  | F613 (B) -- the gate says "checks are still running… retry when they finish" while every check run is `error` | findings-02-closed-3.md |
| F614 | B | closed |  | F614 (B) -- `agent_wrote_outside_workspace` records a write that was refused and never happened | findings-02-closed-3.md |
| F615 | B | closed |  | F615 (B) -- a vault report that brings new outside information can only end "answered", so the operator never hears it | findings-02-closed-3.md |
| F616 | B | closed |  | F616 (B) -- Distil is disabled on exactly the file sources that need it: a PDF or image uploaded while distillation was off never gets its facts from  | findings-02-closed-3.md |
| F617 | B | closed |  | F617 (B) -- after a re-distil, a resolved contradiction calls the standing fact "A private fact, held on another machine", and an approved spec says i | findings-02-closed-3.md |
| F618 | B | closed |  | F618 (B) -- agent-keyed routes (heartbeat, compact, new-session, output, sessions) accept any name, and the writes mint phantom agents that the roster | findings-02-closed-3.md |
| F619 | C | closed |  | F619 (C) -- an operator turn bound to a gated task runs the whole job; every status move is refused, and its peer mail starts a seven-turn chain | findings-02-closed-3.md |
| F620 | C | closed |  | F620 (C) -- `POST /agent/trigger` with `"message": ""` starts a paid run | findings-02-closed-3.md |
| F621 | C | closed |  | F621 (C) -- accepting the evidence a reviewer's verdict waited on does not re-dispatch the review, and the only way to ask again is the API | findings-02-closed-3.md |
| F622 | C | closed |  | F622 (C) -- a hand-authored task without requirements is approved and Landed, and its work never reaches main | findings-02-closed-3.md |
| F623 | C | closed |  | F623 (C) -- a message to an agent with no runner answers plain success, and the Team block calls that agent "runner=native" | findings-02-closed-3.md |
| F624 | C | closed |  | F624 (C) -- a loop's outstanding-request check ignores an operator turn queued from the composer; F556 names only `/messages` mail | findings-02-closed-3.md |
| F625 | C | closed |  | F625 (C) -- a waiting firing whose queued entry is withdrawn stays `in_progress` forever, even after its job is archived | findings-02-closed-3.md |
| F626 | C | closed |  | F626 (C) -- with a vault job enabled and no runner, an upload or proposal records nothing at all; only Distil refuses | findings-02-closed-3.md |
| F627 | C | closed |  | F627 (C) -- when another process holds the database, every route answers a bare `500 Internal Server Error` after about 42 s | findings-02-closed-3.md |
| F628 | C | closed |  | F628 (C) -- under `acceptEdits`, a write outside the workspace is refused silently: no card, and the agent tells the operator to approve it in a dialo | findings-02-closed-3.md |
| F629 | C | closed |  | F629 (C) -- Land is the approval control on a completed task, but the merge-verdict note renders only under review | findings-02-closed-3.md |
| F630 | C | closed |  | F630 (C) -- a manager job accepts a model its runner's CLI does not declare; it fails only at the firing | findings-02-closed-3.md |
| F631 | C | closed |  | F631 (C) -- setting a document's size leaves its step outside the new journey | findings-02-closed-3.md |
| F632 | C | closed |  | F632 (C) -- the payload schema tells agents an unresolved question blocks proposing; it only warns | findings-02-closed-3.md |
| F633 | C | closed |  | F633 (C) -- "1 waiting — hop budget exhausted" shows in a conversation that has nothing waiting, with no Continue and no pointer | findings-02-closed-3.md |
| F634 | C | closed |  | F634 (C) -- in a narrow window the panel toggle flips to "Hide panel" but opens nothing; a separate "Panel" button opens the drawer | findings-02-closed-3.md |
| F635 | C | closed |  | F635 (C) -- the Ctrl+K palette drops focus to `<body>` on Escape and after choosing an item | findings-02-closed-3.md |
| F636 | C | closed |  | F636 (C) -- the "Permission decisions" history is reachable only while a question is open, and its rows do not say what was decided | findings-02-closed-3.md |
| F637 | C | closed |  | F637 (C) -- the Jobs page says "No jobs yet / Create First Job" after six jobs have fired, because archived jobs and loops have no view | findings-02-closed-3.md |
| F638 | C | closed |  | F638 (C) -- an agent cannot create a disabled job | findings-02-closed-3.md |
| F639 | C | closed |  | F639 (C) -- the settings copy for `allow_agent_jobs` names only flows and loops, but the setting refuses `create_job` too | findings-02-closed-3.md |
| F640 | C | closed |  | F640 (C) -- a resolved contradiction keeps marking the overruled fact "presumed" | findings-02-closed-3.md |
| F641 | C | closed |  | F641 (C) -- the Manager page reads "empty" for a firing that answered a report, and the upload 413 does not name the limit | findings-02-closed-3.md |
| F642 | C | closed |  | F642 (C) -- a task's assignee accepts an agent that does not exist | findings-02-closed-3.md |
| F643 | C | closed |  | F643 (C) -- refusals and diagnostics that give a code instead of a sentence (drift resolve, arrange, the manifest-drift strip) | findings-02-closed-3.md |
| F644 | C | closed |  | F644 (C) -- a capability created from the app lands under `spec/changes/<random-name>/` | findings-02-closed-3.md |
| F645 | C | closed |  | F645 (C) -- a refused trigger for an unknown agent leaves an open conversation (and a withdrawn queue entry) that the rail files under "Archived agent | findings-02-closed-3.md |
| F646 | C | closed |  | F646 (C) -- a directory inside another project's directory opens as a separate project | findings-02-closed-3.md |
| F647 | C | closed |  | F647 (C) -- `PUT /project/instructions {}` clears the instructions without a word | findings-02-closed-3.md |
| F648 | C | closed |  | F648 (C) -- the agent-budget refusal names no remedy | findings-02-closed-3.md |
| F649 | C | closed |  | F649 (C) -- `agentweave status` ignores `--profile`, and the CLI's hints drop profile and port | findings-02-closed-3.md |
| F650 | C | closed |  | F650 (C) -- `agentweave stop --profile X --port N` against a native Hub it did not start falls through to Docker and prints a Docker-daemon error | findings-02-closed-3.md |
| F651 | D | closed |  | F651 (D) -- an answer that arrives after the timeout is both read in-run by `get_answer` and delivered as a new paid turn | findings-02-closed-3.md |
| F652 | D | closed |  | F652 (D) -- Explore in an existing conversation creates its document on the press; a refused or never-made send leaves an empty `exploring` document | findings-02-closed-3.md |
| F653 | D | closed |  | F653 (D) -- one hop-held entry gets three Continue controls and two explanations | findings-02-closed-3.md |
| F654 | D | closed |  | F654 (D) -- the review-dispatch refusal omits the remedy that works | findings-02-closed-3.md |
| F655 | D | closed |  | F655 (D) -- a loop past its `stop_at` still shows as enabled with a next run until the next tick records the stop | findings-02-closed-3.md |
| F656 | D | partly |  | F656 (D) -- legibility of permission refusal reasons: doubled backslashes, path fragments, an event with no agent, and a stop refusal that hides an un | findings-01-open.md |
| F657 | D | partly | stale? 081b790 | F657 (D) -- small echoes and asymmetries in the spec and evidence routes | findings-01-open.md |
| F658 | D | closed |  | F658 (D) -- Check now is unreachable for a document with no vault warnings | findings-02-closed-3.md |
| F659 | D | closed |  | F659 (D) -- a stale "Decided without you" card stays on a task after its cause is gone | findings-02-closed-3.md |
| F660 | A | closed |  | F660 (A) -- on Copilot, any Hub-refused tool call ends the turn silently: the run records `completed`, exit 0, no reply, and a task turn leaves its ta | findings-02-closed-3.md |
| F661 | B | closed |  | F661 (B) -- the Workspace judge reads regex and script-block text as paths: a read-only `-notmatch '\\.git\\'` is refused as a UNC root, and `$` insid | findings-02-closed-3.md |
| F662 | B | closed |  | F662 (B) -- the Copilot model catalog has drifted from the CLI: `claude-haiku-5.5` and `grok-4.7` are refused (400) though the CLI runs them, and four | findings-02-closed-3.md |
| F663 | C | closed |  | F663 (C) -- a stale `.agentweave/calls/*.json` collides with the shim prompt's example name `1.json`; the second shim turn's create failed twice and t | findings-02-closed-3.md |
| F664 | C | closed |  | F664 (C) -- a Copilot shim spec turn is told to write its args file with the file-writing tool, which spec turns exclude | findings-02-closed-3.md |
| F665 | C | closed |  | F665 (C) -- Copilot worker credits are outside project accounting: accounting showed 19 premium requests / 154.00 AIU against true 21 / 155.92, and `p | findings-02-closed-3.md |
| F666 | C | closed |  | F666 (C) -- after a Stop, the interrupted shell `tool_use` never gets a `tool_result`, so its timeline card stays "awaiting result" forever | findings-02-closed-3.md |
| F667 | C | open |  | F667 (C) -- read-only agents share the project directory as their workspace, so two of them racing on `.agentweave/calls/` (or any file) collide | findings-01-open.md |
| F668 | B | closed |  | F668 (B) -- two different agents bound to one task both start in the same task checkout; D8 serialises one agent's turns, not different agents' | findings-02-closed-3.md |
| F669 | C | closed |  | F669 (C) -- an explicit `work_dir` can point into another agent's isolated workspace | findings-02-closed-3.md |
| F670 | C | closed |  | F670 (C) -- `PATCH /budget` commits before reading totals, so an overflow answers 500 and skips rescheduling | findings-02-closed-3.md |
| F671 | B | closed |  | F671 (B) -- a Copilot worker call fails outright on a model the plan does not offer, while the same runner's turns run on Auto | findings-02-closed-3.md |
| F672 | B | closed |  | F672 (B) -- evidence waiting on the operator stalls a loop, and nothing tells the operator; the controls sit behind a collapsed one-line bar | findings-02-closed-3.md |
| F673 | B | closed |  | F673 (B) -- an evidence piece gives the operator nothing to judge it by | findings-02-closed-3.md |
| F674 | C | closed |  | F674 (C) -- a roadmap slice's change document can be written, approved, built and archived without ever naming its slice | findings-02-closed-3.md |
| F675 | A | closed |  | F675 (A) -- under "Workspace only" an agent can write its runner's allow rules, and its next turn runs past the approver | findings-02-closed-3.md |
| F676 | A | closed |  | F676 (A) -- a pipe can carry a path the shell judge never reads | findings-02-closed-3.md |
| F677 | B | closed |  | F677 (B) -- a Claude run waits for its background command and then takes an unprompted second turn | findings-02-closed-3.md |
| F678 | A | closed |  | F678 (A) -- a resumed Claude turn records its session's running total as its own cost, and drops subagent tokens | findings-02-closed-3.md |
| F679 | B | closed |  | F679 (B) -- a Claude subagent's tool call reaches the operator as the agent's own | findings-02-closed-3.md |
| F680 | A | closed |  | F680 (A) -- with project checks configured, a reviewer can never approve a task whose merge depends on its evidence: "checks are still running" while  | findings-02-closed-3.md |
| F681 | B | closed |  | F681 (B) -- Land approves a task on evidence another, task-less run recorded at main's tip, then skips the merge: the task's own commit never reaches  | findings-02-closed-3.md |
| F682 | B | closed |  | F682 (B) -- a vault source piece longer than ~32k characters fails distillation on Windows: the 50,000-character piece is passed on the command line | findings-02-closed-3.md |
| F683 | B | closed |  | F683 (B) -- two projects can share one private vault location, and each then reads the other's private entries | findings-02-closed-3.md |
| F684 | B | closed |  | F684 (B) -- re-distilling the winning side of a resolved contradiction mints a new fact id, so the fact the resolution says "stands" is gone | findings-02-closed-3.md |
| F685 | B | closed |  | F685 (B) -- opening a folder that contains existing projects is accepted, and every later project under it is then refused as nested | findings-02-closed-3.md |
| F686 | B | closed |  | F686 (B) -- project instructions take any size and are prepended to every agent turn | findings-02-closed-3.md |
| F687 | B | closed |  | F687 (B) -- an operator trigger binds an agent to another agent's task, and that run then completes the task while it stays assigned to the other agen | findings-02-closed-3.md |
| F688 | B | closed |  | F688 (B) -- the Ask-me card's verdict says "Outside this agent's workspace" for refusals that are not about the workspace | findings-02-closed-3.md |
| F689 | B | closed |  | F689 (B) -- an adopted spec.json whose payload fails validation is accepted (201), indexes nothing, and its page loads forever | findings-02-closed-3.md |
| F690 | B | closed |  | F690 (B) -- after a fold, drift on the folded requirement's evidence shows only on the archived change, while the capability reads verified with nothi | findings-02-closed-3.md |
| F691 | B | closed |  | F691 (B) -- evidence for a reworded requirement still reads "accepted" in the requirement story and the evidence browser | findings-02-closed-3.md |
| F692 | B | closed |  | F692 (B) -- a decided piece of evidence has no control to reverse it, and a granted agent overturns a rejection silently | findings-02-closed-3.md |
| F693 | B | closed |  | F693 (B) -- an agent that approves a task from inside its checkout leaves an empty directory that refuses the task's next turn | findings-02-closed-3.md |
| F694 | B | closed |  | F694 (B) -- the planner's same-file warning never reaches the operator, so same-file tasks run in parallel and collide | findings-02-closed-3.md |
| F695 | B | closed |  | F695 (B) -- a conflicting prerequisite refuses the author's turns, so only the operator, in a terminal, can resolve it | findings-02-closed-3.md |
| F696 | C | closed |  | F696 (C) -- "Workspace only" refuses ordinary read-only commands: sed/awk scripts read as paths, every `\| while read` loop, `echo $PWD` | findings-02-closed-3.md |
| F697 | C | closed |  | F697 (C) -- a stopped Claude turn's spend is recorded nowhere | findings-02-closed-3.md |
| F698 | C | closed |  | F698 (C) -- Copilot conversation rows show `Edit {` / `Shell {` instead of the path or command, and an F675 refusal's reason is not on the card | findings-02-closed-3.md |
| F699 | C | closed |  | F699 (C) -- a tester's `add_criterion` amendment never reaches the task it was written for | findings-02-closed-3.md |
| F700 | C | closed |  | F700 (C) -- after `report_cannot_satisfy`, the operator's only response is "mark reviewed", which changes nothing | findings-02-closed-3.md |
| F701 | C | closed |  | F701 (C) -- the gate refusal at sketch rigor offers "lower the document's rigor", which cannot work | findings-02-closed-3.md |
| F702 | C | closed |  | F702 (C) -- the corpus strip still promises fixes that cannot happen and prints codes (F643 remainder) | findings-02-closed-3.md |
| F703 | C | closed |  | F703 (C) -- a document write calls warn-only gaps `blocking` | findings-02-closed-3.md |
| F704 | C | closed |  | F704 (C) -- once an approved roadmap has an unclaimed slice, every unrelated change needs "Approve anyway" | findings-02-closed-3.md |
| F705 | C | closed |  | F705 (C) -- a slice link can be backfilled to an unapproved roadmap, and it then blocks re-proposing the change | findings-02-closed-3.md |
| F706 | C | closed |  | F706 (C) -- evidence that says `covers: partial` alone makes a requirement Verified | findings-02-closed-3.md |
| F707 | C | closed |  | F707 (C) -- a metadata-only proposal is labelled as a Summary/problem/scope change and shows no diff | findings-02-closed-3.md |
| F708 | C | closed |  | F708 (C) -- sending back an operator-completed task leaves the reviewer holding it | findings-02-closed-3.md |
| F709 | C | closed |  | F709 (C) -- an agent can overwrite the notes of another agent's task, and notes become evidence verdict text | findings-02-closed-3.md |
| F710 | C | closed |  | F710 (C) -- `POST /tasks` accepts an empty title that rename refuses | findings-02-closed-3.md |
| F711 | C | closed |  | F711 (C) -- the task story leaves out refused turns, a failed checkout release and an operator's manual merge | findings-02-closed-3.md |
| F712 | C | closed |  | F712 (C) -- a flow firing whose staged review is withdrawn stays `in_progress` forever | findings-02-closed-3.md |
| F713 | C | closed |  | F713 (C) -- a loop stops on a blank reason, and a real reason is then refused | findings-02-closed-3.md |
| F714 | C | closed |  | F714 (C) -- an ended loop's collapsed job card reads "Paused" and offers Resume | findings-02-closed-3.md |
| F715 | C | closed |  | F715 (C) -- the integration preview says "merges cleanly" when approval will skip the merge for a dirty checkout | findings-02-closed-3.md |
| F716 | C | closed |  | F716 (C) -- Checkpoint now on an already-handed-over conversation still makes a paid checkpoint | findings-02-closed-3.md |
| F717 | C | closed |  | F717 (C) -- a private vault location on a missing drive is accepted, then every private add is a bare 500 | findings-02-closed-3.md |
| F718 | C | closed |  | F718 (C) -- clicking the Activity tab always opens the "Activity" view; the Ledger never leads | findings-02-closed-3.md |
| F719 | C | closed |  | F719 (C) -- Manager firing rows never say what they fired on | findings-02-closed-3.md |
| F720 | C | closed |  | F720 (C) -- the vault entry detail tells the operator to enable a job that is already enabled | findings-02-closed-3.md |
| F721 | C | closed |  | F721 (C) -- at a spent budget a conversation-title job leaves no firing, while vault jobs record a failed one | findings-02-closed-3.md |
| F722 | C | closed |  | F722 (C) -- the Overview budget card omits the Hub's workers, so its lines do not sum to its total | findings-02-closed-3.md |
| F723 | C | closed |  | F723 (C) -- `agentweave doctor --profile X` without `--port` is not refused and examines :8000 | findings-02-closed-3.md |
| F724 | C | closed |  | F724 (C) -- `agentweave stop` leaves the desktop window that start opened | findings-02-closed-3.md |
| F725 | D | closed |  | F725 (D) -- a Copilot provider runner gets three different model labels | findings-02-closed-3.md |
| F726 | D | closed |  | F726 (D) -- relocating onto a folder another project claims gives a misleading refusal | findings-02-closed-3.md |
| F727 | D | closed |  | F727 (D) -- the capability question's "Enabled it -- go ahead" reads as a grant but grants nothing | findings-02-closed-3.md |
| F728 | D | closed |  | F728 (D) -- small agent/project items from the 2026-10-18 sweep | findings-02-closed-3.md |
| F729 | D | closed |  | F729 (D) -- after a project delete the app refetches the deleted project | findings-02-closed-3.md |
| F730 | D | closed |  | F730 (D) -- small spec/evidence echoes from the 2026-10-18 sweep | findings-02-closed-3.md |
| F731 | D | closed |  | F731 (D) -- small task/flow/loop items from the 2026-10-18 sweep | findings-02-closed-3.md |
| F732 | D | closed |  | F732 (D) -- the `reset` hint is a command that is refused | findings-02-closed-3.md |
| F733 | D | closed |  | F733 (D) -- every Claude turn logs a second, empty context reading, and the Ledger counts routine readings as warnings | findings-02-closed-3.md |
| F734 | D | closed |  | F734 (D) -- a client sending a body over the limit gets a connection abort instead of the 413 sentence | findings-02-closed-3.md |
| F735 | D | closed |  | F735 (D) -- two silent vault dead ends: "check now" with no requirements, and decision-type uploads | findings-02-closed-3.md |
| F736 | D | closed |  | F736 (D) -- starting the Hub from a folder registers that folder as a project and rewrites its binding | findings-02-closed-3.md |
| F737 | B | closed |  | F737 (B) -- the workspace judge still reads commands as text: four shapes reach the runner's configuration or feed arguments without F675's or F676's  | findings-02-closed-3.md |
| F738 | B | closed |  | F738 (B) -- `agentweave reset --profile X` cannot find X's running Hub, so it deletes the data folder from under it | findings-02-closed-3.md |
| F739 | C | closed |  | F739 (C) -- a request body sent without a Content-Length is not size-limited | findings-02-closed-3.md |
| F740 | D | closed |  | F740 (D) -- a failed conversation-title firing does not say why | findings-02-closed-3.md |
| F741 | D | closed |  | F741 (D) -- a vault report on an unread file still gets the fixed "enable the job" note | findings-02-closed-3.md |
| F742 | C | closed |  | F742 (C) -- renaming a spec document changes its index title but not the file's, which then reads as a metadata conflict | findings-02-closed-3.md |
| F743 | C | closed |  | F743 (C) -- an operator PATCH to revision_needed that names an assignee silently ignores it | findings-02-closed-3.md |
| F744 | D | open |  | F744 (D) -- small items from the 2026-10-18 fix pass | findings-01-open.md |
| F745 | C | closed |  | F745 (C) -- a command substitution's output is never judged: `cp x $(dirname $(pwd))` copies outside the workspace | findings-02-closed-3.md |
| F746 | D | closed |  | F746 (D) -- releasing a task checkout throws away a half-resolved prerequisite merge | findings-02-closed-3.md |
| F747 | C | closed |  | F747 (C) -- a delete/modify merge conflict has no markers, so the snapshot commits it as the files stand | findings-02-closed-3.md |
| F748 | D | open |  | F748 (D) -- a runner that re-reads its settings mid-turn sees a write made earlier in the same turn | findings-01-open.md |
| F749 | C | closed |  | F749 (C) -- `e2e.py hub-up` from a worktree serves the main checkout's code | findings-02-closed-3.md |
| F750 | D | closed |  | F750 (D) -- two processes pinning the same new tool-server digest race, and one fails with Access denied on Windows | findings-02-closed-3.md |
| F751 | D | closed |  | F751 (D) -- a reviewer's verdict still accepts a task's own awaiting evidence recorded for an earlier wording | findings-02-closed-3.md |
| F752 | C | closed |  | F752 (C) -- recording already-built work as a spec change cannot be approved without "Approve anyway" | findings-02-closed-3.md |
| F753 | C | closed |  | F753 (C) -- a fold can change requirements but not an algorithm or a criterion's text | findings-02-closed-3.md |
| F754 | D | closed |  | F754 (D) -- every fold into some capabilities reports the capability's old gaps as if they were the change's | findings-02-closed-3.md |
| F755 | C | closed |  | F755 (C) -- Tier 0 judge fixes leave the spec corpus behind: the shell judge's rules are not specified | findings-02-closed-3.md |
| F756 | C | closed |  | F756 (C) -- a glob in the last component after `..` through a link out is allowed | findings-02-closed-3.md |
| F757 | D | closed |  | F757 (D) -- a fold renames a change's requirements, and the change's own text still names the old keys | findings-02-closed-3.md |
| F758 | D | open |  | F758 (D) -- the approval gate's remedy for an awaiting piece recorded for an earlier wording is one the Hub refuses | findings-01-open.md |
| F759 | B | closed |  | F759 (B) -- an open drift candidate on evidence the operator overturned to rejected hides the rejection from the approval gate | findings-02-closed-3.md |
| F760 | B | closed |  | F760 (B) -- the evidence diff reads git output as cp1252: a 500 on some non-ASCII content, mojibake on the rest, and non-ASCII paths quoted with no pa | findings-02-closed-3.md |
| F761 | B | closed |  | F761 (B) -- a piece that names no commit shows, as its work, whatever commit HEAD happened to be | findings-02-closed-3.md |
| F762 | C | open |  | F762 (C) -- the coverage bar offers Accept, and "Accept instead", on a piece recorded for an earlier wording, which the Hub always refuses | findings-01-open.md |
| F763 | B | open |  | F763 (B) -- after the operator rejects a cannot-satisfy report, the task stays blocked and only the operator can move it, while the reporter is told t | findings-01-open.md |
| F764 | C | open |  | F764 (C) -- a cannot-satisfy report is not tied to its task's criteria, repeats are not recognised, and answering any one report on a task unblocks it | findings-01-open.md |
| F765 | C | open |  | F765 (C) -- a fold archives a change with unanswered cannot-satisfy reports without a word, and reports keep landing on the archived change | findings-01-open.md |
| F766 | D | open |  | F766 (D) -- a change's roadmap slice can be named after the fact only through the API: no screen or tool calls `PUT .../roadmap` | findings-01-open.md |
| F767 | B | closed |  | F767 (B) -- a flow hands fresh work to its own named reviewer, and the task that reviewer builds can then never be reviewed: one event, and nothing on | findings-02-closed-3.md |
| F768 | C | closed |  | F768 (C) -- a task's story leaves out the flow's refusal to staff its review, so an unreviewable task's story ends at "completed" and says nothing mor | findings-02-closed-3.md |
| F769 | B | closed |  | F769 (B) -- the integration note hides a merge behind a later "already in master" skip and keeps a resolved "no main branch" line, so merged work read | findings-02-closed-3.md |
| F770 | C | closed |  | F770 (C) -- the checks row never says a failure also fails on main: the drawer shows a red "Checks failed" with the output, and only the Land refusal  | findings-02-closed-3.md |
| F771 | C | closed |  | F771 (C) -- a review turn is not told which of the document's requirements are someone else's, and a Haiku reviewer sent correct work back twice for t | findings-02-closed-3.md |
| F772 | C | closed |  | F772 (C) -- Land on a task with awaiting evidence also says its commit is "on neither master nor inside any commit the accepted evidence names" and as | findings-02-closed-3.md |
| F773 | C | closed |  | F773 (C) -- a flow task's checks never run while it waits for review: the reviewer judges without them, and its approval is first refused "checks are  | findings-02-closed-3.md |
| F774 | B | closed |  | F774 (B) -- `POST /session/sync` deletes an agent that holds an in-progress task and a live run, answers 200, and a payload with no `agents` key delet | findings-02-closed-3.md |
| F775 | B | closed |  | F775 (B) -- a checkpoint says "No files recorded as changed" when the agent committed its own work, because `files_changed` reads only the Hub's auto- | findings-02-closed-3.md |
| F776 | C | closed |  | F776 (C) -- a turn bound to a task already `completed` (waiting for its reviewer) records an open divergence, "builder ended completed with Fix add()  | findings-02-closed-3.md |
| F777 | B | closed |  | F777 (B) -- a non-ASCII file name reaches the `@` picker git-quoted (`"notes caf\303\251.md"`), and neither that string nor the real name can be read | findings-02-closed-3.md |
| F778 | D | open |  | F778 (D) -- a UTF-16 text file (what PowerShell 5.1's `>` writes) is reported `binary` by `/workspace/file`, so the files tab cannot show it | findings-01-open.md |
| F779 | D | open |  | F779 (D) -- `send_message` from a task-bound run does not record the task, so the Ledger's "Between agents" lane has no task link for a message sent m | findings-01-open.md |
| F780 | B | closed |  | F780 (B) -- Copilot's long context tier cannot be chosen: over ACP neither `--context long_context` nor a persisted `contextTier` changes the window | findings-02-closed-3.md |
| F781 | A | closed |  | F781 (A) -- the Workspace judge reads `Select-String`'s pattern as a path: `-Pattern '- \[ \]'` is refused as "'\' is outside your workspace", and the | findings-02-closed-3.md |
| F782 | A | partly |  | F782 (A) -- a Copilot turn that reaches the fixed 600 s deadline is re-delivered unchanged twice: work that needs more than ten minutes runs three tim | findings-01-open.md |
| F783 | A | closed |  | F783 (A) -- the 600 s turn clock keeps running while `ask_user` waits for the operator: the turn fails with its question still open, the retry asks th | findings-02-closed-3.md |
| F784 | B | closed |  | F784 (B) -- under Ask me, a card nobody answers ends a Copilot turn `completed` with no reply after 4 minutes: the expiry is told to the agent as "the | findings-02-closed-3.md |
| F785 | B | closed |  | F785 (B) -- the refusal continuation says "continue another way", and Haiku's other way is the same path through another tool: the judge refuses it ag | findings-02-closed-3.md |
| F786 | C | closed |  | F786 (C) -- a Copilot turn that hits the 600 s deadline (or is cut by a Hub restart) records no premium request, though its prompt was sent and billed | findings-02-closed-3.md |
| F787 | B | open |  | F787 (B) -- the first trigger of a new agent held the database write lock for over 30 s; every other Hub writer waited and the trace writer's insert f | findings-01-open.md |
| F788 | B | open |  | F788 (B) -- a run's permission wait polls its request about once a second, and every poll is recorded as an `aw.request` span: 60 spans per permission | findings-01-open.md |
| F789 | B | closed |  | F789 (B) -- a Copilot run whose ACP startup request times out fails with an empty error: the run, its `run_failed` event and the conversation say noth | findings-02-closed-3.md |
| F790 | B | closed |  | F790 (B) -- a run's `aw.permission_wait` span stores the tool call's arguments unredacted, while the same call's `execute_tool` span redacts them; the | findings-02-closed-3.md |
| F791 | C | closed |  | F791 (C) -- every run's trace shows two routine `git rev-parse --verify --quiet MERGE_HEAD` probes as red error spans | findings-02-closed-3.md |
| F792 | C | closed |  | F792 (C) -- a stopped run's trace reads `ok`, and its stop is recorded as an `aw.status.completed` event; the trace list and drawer cannot tell a stop | findings-02-closed-3.md |
| F793 | C | closed |  | F793 (C) -- after the OTLP collector was down, a fixed endpoint receives nothing for up to 300 s while Settings -> Traces shows no error and "Never" | findings-02-closed-3.md |
| F794 | C | closed |  | F794 (C) -- a shell or write call on a path inside a root granted for reading only is refused as "is outside your workspace", the same words as an ung | findings-02-closed-3.md |
| F795 | C | closed |  | F795 (C) -- an agent's granted-reach save the Hub refuses shows only "Could not save the granted reach."; the route's own detail is pydantic's raw dum | findings-02-closed-3.md |
| F796 | C | closed |  | F796 (C) -- a host typed into Granted host but not added with Enter or "Add host" is silently dropped when the settings are saved, and stays in the fi | findings-02-closed-3.md |
| F797 | D | open |  | F797 (D) -- the granted root's access select is too narrow for its own label: "Read and write" reads "Read and wr" | findings-01-open.md |
| F798 | B | closed |  | F798 (B) -- adding a folder by path that holds one unreadable subfolder answers a bare 500, adds nothing, and the agent's `vault_add` reads only "Inte | findings-02-closed-3.md |
| F799 | C | closed |  | F799 (C) -- the folder walk follows junctions and directory links (a loop adds each file 64 times to the batch), and the 200-file cap is checked only  | findings-02-closed-3.md |
| F800 | B | closed |  | F800 (B) -- `agentweave reset --profile <name> --all` deletes the shared `~/.agentweave/hub/.env` (the default profile's bootstrap key and ticket secr | findings-02-closed-3.md |
| F801 | C | closed |  | F801 (C) -- a vault report filed while the reports job has no runner stays `pending` forever: choosing a runner never looks into it, and the operator  | findings-02-closed-3.md |
| F802 | C | closed |  | F802 (C) -- `agentweave doctor --profile <name> --port N` tells the operator to start `agentweave --port N`, which starts the default profile's databa | findings-02-closed-3.md |
| F803 | D | open |  | F803 (D) -- small legibility slips on the vault-by-path doors: doubled backslashes in the CLI's refusals, a UTF-8 BOM kept in a source's text, and a r | findings-01-open.md |
| F804 | B | closed |  | F804 (B) -- a question nobody waits on, asked in one conversation, takes over the composer of every other conversation with that agent (archived ones  | findings-02-closed-3.md |
| F805 | D | open |  | F805 (D) -- the files tab's refusals are less legible than its neighbours: an oversized file reads "file is 11200000 bytes, exceeding the 1048576 byte | findings-01-open.md |
| F806 | B | closed |  | F806 (B) -- one folder-browser listing, project open or relocate of a path on an unreachable network host freezes the whole Hub for about 21 s: the fi | findings-02-closed-3.md |
| F807 | B | closed |  | F807 (B) -- switching the checkpoint runner to a Copilot or Codex runner keeps a Claude checkpoint model the screen no longer shows, and Save is refus | findings-02-closed-3.md |
| F808 | C | closed |  | F808 (C) -- every project with no agents tells the operator to run `agentweave start`, a command the CLI refuses | findings-02-closed-3.md |
| F809 | D | open |  | F809 (D) -- small slips around the Add-project dialog and the Runners page: "Workingâ€¦" mojibake, a Hide control under its own popup, doubled backsla | findings-01-open.md |
| F810 | B | closed |  | F810 (B) -- `POST /session/sync` deletes an agent whose messages are still queued, which archive refuses to do: the entries and the conversation are o | findings-02-closed-3.md |
| F811 | B | closed |  | F811 (B) -- two agents whose names differ only in case are both accepted; on Windows and macOS the second shares the first's worktree folder and can n | findings-02-closed-3.md |
| F812 | C | closed |  | F812 (C) -- `POST /session/sync` answers 500 to an `agents` that is not an object, never says which agents it deleted, and leaves every agent it named | findings-02-closed-3.md |
| F813 | D | open |  | F813 (D) -- `request_agent` and Add agent refuse an archived agent's name as merely "already exists", without saying it is archived or that names are  | findings-01-open.md |
| F814 | B | closed |  | F814 (B) -- with the token budget spent, the operator's own message waits "Queued — token budget exhausted" behind an agent's budget-held message, so  | findings-02-closed-3.md |
| F815 | C | closed |  | F815 (C) -- an agent's `send_message` while the token budget is spent answers plain success, so the sender waits for a reply that cannot come | findings-02-closed-3.md |
| F816 | C | closed |  | F816 (C) -- unarchiving a conversation that was cut over reopens it as a live line of work: no notice, a working composer on the old session, while th | findings-02-closed-3.md |
| F817 | C | closed |  | F817 (C) -- a failed Checkpoint now clears the conversation's checkpoint warning: after a reload the offer and the failure are both gone | findings-02-closed-3.md |
| F818 | D | open |  | F818 (D) -- the dismiss refusal tells a conversation far past its threshold that it "has not reached its threshold" | findings-01-open.md |
| F819 | C | closed |  | F819 (C) -- a loop whose agent cannot run gives up on the delivery, but the loop does not say so: its task stays `in_progress` with that agent, the ca | findings-02-closed-3.md |
| F820 | B | closed |  | F820 (B) -- Land during a passing git failure approves the task and records the permanent skip "this project is not a git repository": its commit is n | findings-02-closed-3.md |
| F821 | D | open |  | F821 (D) -- Run on a loop that has ended answers 400 "Job is disabled", whose remedy, enabling it, is refused 409 "loop_ended" | findings-01-open.md |
| F822 | D | open |  | F822 (D) -- a job firing's id and an agent run's id share the `run-` prefix, so a firing id pasted into a run route reads "This run has no trace" | findings-01-open.md |
| F823 | C | closed |  | F823 (C) -- a failed merge's Retry ("Try again") exists only on the board card: the task drawer, where the failure is read, offers none, and a retry t | findings-02-closed-3.md |
| F824 | C | closed |  | F824 (C) -- deleting a task from its drawer makes the page request the deleted task's story ~110 times in five seconds, and the card stays on the boar | findings-02-closed-3.md |
| F825 | C | closed |  | F825 (C) -- deleting a prerequisite answers 204 and silently releases every task that waited on it; the confirm says only "Its dependencies ... go wit | findings-02-closed-3.md |
| F826 | D | open |  | F826 (D) -- once approved, a task's card credits the reviewer (B: "@gamma") or nobody (Land: "Unassigned"); the author appears only in the story | findings-01-open.md |
| F827 | D | open |  | F827 (D) -- a hand-made task whose prerequisite was rejected is told to "edit the document that declared this dependency": there is no document | findings-01-open.md |
| F828 | C | closed |  | F828 (C) -- deleting a document (or a task) leaves the deleted task's checkout and branch, with the agent's unmerged commit, listed under a task id th | findings-02-closed-3.md |
| F829 | C | closed |  | F829 (C) -- after Delete document in the app, the page stays on the deleted document: its old title and phase, three load failures, and 404s, with no  | findings-02-closed-3.md |
| F830 | D | open |  | F830 (D) -- the `steps_skipped` approval gap tells the operator, on screen, to make raw HTTP calls, and the recipe it gives leaves out re-proposing | findings-01-open.md |
| F831 | D | open |  | F831 (D) -- the note answering a cannot-satisfy report runs the operator's reason into the next sentence with no full stop | findings-01-open.md |
| F832 | B | closed |  | F832 (B) -- a refused Land tells the operator to "send the task back (revision_needed)", a move the Hub never offers the operator from `completed`; th | findings-02-closed-3.md |
| F833 | C | closed |  | F833 (C) -- a criterion-only amendment is recorded and shown as "reworded it" with the same wording twice, and the stale-evidence refusal says the req | findings-02-closed-3.md |
| F834 | D | open |  | F834 (D) -- a drift candidate re-raised after "Code corrected" or "Spec updated" looks like new drift: nothing on the row says it was answered, or whe | findings-01-open.md |
| F835 | C | closed |  | F835 (C) -- a dependent's turn refused because its prerequisite's merge could not be brought in is never tried again when the prerequisite lands: it s | findings-02-closed-3.md |
| F836 | C | closed |  | F836 (C) -- when deleting a task keeps its work (unmerged commits), nothing on screen says so: the drawer just closes, Activity shows a bare `task_che | findings-02-closed-3.md |
| F837 | D | open |  | F837 (D) -- every `task_created` row in the Activity feed reads "assigned to unassigned", even for a task created with an assignee | findings-01-open.md |
| F838 | C | closed |  | F838 (C) -- deleting a document whose task kept work says only "Deleted “T” and its 2 tasks.": the 200's `kept_work` (branch, unmerged commit) never r | findings-02-closed-3.md |
| F839 | D | open |  | F839 (D) -- the F829 fix still refetches the deleted document: the delete's own `spec_updated` broadcast re-invalidates every spec query family, so se | findings-01-open.md |
| F840 | D | open |  | F840 (D) -- deleting the last document shows "No specification yet" with no word of what was deleted: `SpecDeletedNote` lives inside the document pane | findings-01-open.md |
| F841 | C | closed |  | F841 (C) -- "Look into it" can be pressed again while the first review runs: each press spawns a paid review of the same report, and the second record | findings-02-closed-3.md |
| F842 | C | closed |  | F842 (C) -- after "Look into it", the Reports list never re-reads: the card promises "The answer appears here when it finishes" and stays `pending` un | findings-02-closed-3.md |
| F843 | D | open |  | F843 (D) -- the vault reports doors refuse without naming the way out: "The vault reports job is disabled." / "... has no runner." on the card, and an | findings-01-open.md |
| F844 | B | closed |  | F844 (B) -- a conversation whose agent is busy in another conversation reads as its own live turn: "asker is responding…", a `running` chip and **Stop | findings-02-closed-3.md |
| F845 | C | open |  | F845 (C) -- in its own conversation, a question nobody waits on still says "Pick one, or write your own answer below." with the composer placeholder " | findings-01-open.md |
| F846 | C | open |  | F846 (C) -- a conversation cut over by a checkpoint opens from the rail with a live composer and no word of its successor; Send is refused "Unarchive  | findings-01-open.md |
| F847 | D | open |  | F847 (D) -- after a failed Checkpoint now and a reload, the banner says "Nothing has been written yet" and nothing on the conversation says the attemp | findings-01-open.md |
| F848 | D | open |  | F848 (D) -- under `automatic` checkpointing with the token budget spent, the threshold banner reads exactly as `offered` does: nothing says the automa | findings-01-open.md |
| F849 | C | closed |  | F849 (C) -- an agent a session sync deletes leaves its conversations open; the rail files them under "agent archived", and an agent later created with | findings-02-closed-3.md |
| F850 | D | closed |  | F850 (D) -- a session sync that deletes an agent leaves it in the rail until a reload: `session_synced` never refreshes the projects summary the rail  | findings-02-closed-3.md |
| F851 | C | open |  | F851 (C) -- `request_agent`'s required `task` is the new agent's whole first message, but neither the MCP tool nor the `aw-tool` listing says so; a re | findings-01-open.md |
| F900 | C | closed |  | F900 (C) -- two files added to the vault by path, each named `README.md`, are both listed as "README.md" | findings-02-closed-3.md |
| F901 | C | closed |  | F901 (C) -- the Vault reader's "Used by" can say how often an entry was read, never by which agent | findings-02-closed-3.md |
| F902 | C | closed |  | F902 (C) -- the compact task card shows one fact at a time: a task both waiting and stalled shows only "waiting" | findings-02-closed-3.md |
| F903 | C | closed |  | F903 (C) -- a requirement awaiting review lost its own tone on the task card and in the drawer | findings-02-closed-3.md |
| F904 | C | closed |  | F904 (C) -- the Overview's "Needs you" lost two question behaviours: blocking questions first, and no "waiting" claim for a non-blocking one | findings-02-closed-3.md |
| F905 | C | closed |  | F905 (C) -- the compact task card offers Retry on every unmerged task, even one a retry can never clear | findings-02-closed-3.md |
| F906 | B | closed |  | F906 (B) -- the clientless-route ratchet measures nothing: `n10_route_reachability.py` reads 0 declared `/api/v1` routes | findings-02-closed-3.md |
| F852 | B | closed |  | F852 (B) -- an agent piece that names no commit, recorded in a task checkout before the task's first commit, still shows master's HEAD commit as its w | findings-02-closed-3.md |
| F853 | D | open |  | F853 (D) -- after a criterion-only change, the piece labels still say "earlier wording" while the story, the decision and the refusal say the criteria | findings-01-open.md |
| F854 | D | open |  | F854 (D) -- the coverage bar shows "<sha> on" with nothing after it when a piece's line of work is unknown | findings-01-open.md |
| F855 | D | open |  | F855 (D) -- the document's health line counts stale, drifting, awaiting-review and changed-unreviewed requirements as "in progress" | findings-01-open.md |
| F856 | C | closed |  | F856 (C) -- a GitHub token (`ghp_...`) in an operator message or an agent reply is stored and exported verbatim in the run's trace, while an `sk-` key | findings-02-closed-3.md |
| F857 | D | open |  | F857 (D) -- a Copilot startup timeout names its request twice: "Copilot did not answer `initialize` within 30 s during initialize" | findings-01-open.md |
| F858 | D | open |  | F858 (D) -- a Copilot launchability probe that fails with a bare exception logs "failed: " with nothing after it, and when no verdict exists yet the e | findings-01-open.md |
| F859 | D | open |  | F859 (D) -- a message whose every delivery attempt failed before any output has no trace button: the conversation says "Last attempt failed" but canno | findings-01-open.md |
| F860 | B | closed |  | F860 (B) -- the conversation never shows a tool's output: an expanded tool row reads only "tool completed" or "tool failed", so a Hub refusal's senten | findings-02-closed-3.md |
| F861 | B | closed |  | F861 (B) -- an agent's `archive_job` puts a card to the operator that does not say which job: "cla wants to use archive_job — no details given — the p | findings-02-closed-3.md |
| F862 | C | open |  | F862 (C) -- with a host granted, a shell command naming an ungranted address is refused saying it "may name only this run's own Hub ($HUB_URL)": the g | findings-01-open.md |
| F863 | C | open |  | F863 (C) -- the Runners page calls the project's checkpoint runner "Unused", and deleting it is then refused: "Runner is bound to the project's checkp | findings-01-open.md |
| F864 | B | closed |  | F864 (B) -- a flow whose own agent is also its named reviewer still hands that agent fresh work while another agent is free, so the task it builds can | findings-02-closed-3.md |
| F865 | B | closed |  | F865 (B) -- with git unreadable for a moment, Land approves a task the preview said approval would refuse for a conflict; once git is back every retry | findings-02-closed-3.md |
| F866 | C | open |  | F866 (C) -- a flow's stall reason for an unstaffed review says "this task names 'alpha' as its reviewer" in the Loops panel and on the loop, where "th | findings-01-open.md |
| F867 | C | open |  | F867 (C) -- a loop's history reads the bare "loop tasks adopted." when it takes over an archived loop's unfinished tasks: no task, no source loop | findings-01-open.md |
| F868 | D | open |  | F868 (D) -- an ended or archived loop reports a `stall_reason` while every agent is busy ("alpha is already running a turn"), and the Loops panel prin | findings-01-open.md |
| F907 | B | closed |  | F907 (B) -- the Activity digest leaves a stopped or failed turn reading "alpha is working" forever, and puts its ending on a separate row by wire name | findings-02-closed-3.md |
| F908 | C | open |  | F908 (C) -- the Activity digest falls back to the event's wire name for every event it has no sentence for, credits the event's `agent` field as its a | findings-01-open.md |
| F909 | B | closed |  | F909 (B) -- a conversation reads "waiting" on the rail and the Overview's agent card says "Waiting for your answer" for a question whose asking run ha | findings-02-closed-3.md |
| F910 | C | open |  | F910 (C) -- the Overview says an agent blocked on the operator's question is "Working on ..." while the same screen says "Nothing running" and Needs y | findings-01-open.md |
| F911 | C | open |  | F911 (C) -- a question's "Open conversation" on the Overview opens the agent's newest conversation, not the one the question was asked in, so the oper | findings-01-open.md |
| F912 | C | open |  | F912 (C) -- `PATCH /questions/{id}` accepts an empty answer, recording the question answered with nothing, and a label that is not one of its options | findings-01-open.md |
| F913 | D | open |  | F913 (D) -- Needs you reads "now ago" for a question asked under 45 seconds ago | findings-01-open.md |
| F914 | C | open |  | F914 (C) -- the Tasks screen's Dependencies view keeps the agent filter and the "Find a task" search on its toolbar and ignores both | findings-01-open.md |
| F915 | D | open |  | F915 (D) -- the Dependencies view says dependencies come only from spec documents, and that a hand-made task's are "set from its task story"; the only | findings-01-open.md |
| F916 | C | open |  | F916 (C) -- deleting a task whose branch holds unmerged work: the confirm promises everything "goes with it", the drawer closes in silence, and the Ac | findings-01-open.md |
| F917 | D | open |  | F917 (D) -- `POST /tasks/{id}/integrations/retry` on a skip the Hub itself marks not retryable answers 200 and records another identical "Not merged"  | findings-01-open.md |
| F918 | B | closed |  | F918 (B) -- the Vault's Add dialog and page drop store any file that is not a PDF or an image as a text "transcript": a Word document goes in as zip b | findings-02-closed-3.md |
| F919 | B | closed |  | F919 (B) -- `agentweave reset --profile <p> --yes` says "Deleted <dir>" and "Hub data destroyed" while the profile's database is still there, held ope | findings-02-closed-3.md |
| F920 | C | open |  | F920 (C) -- the Vault's Add dialog promises folders ("Files or folders", "Drop files or a folder ... Hidden files are skipped"), but its picker refuse | findings-01-open.md |
| F921 | C | open |  | F921 (C) -- `PATCH /manager/jobs/{key}` with only a new `runner_id` keeps a model the new runner's CLI does not declare; the firing then runs on that  | findings-01-open.md |
| F922 | D | open |  | F922 (D) -- Project settings -> Manager tells a vault job with no runner that "with none, the job uses each agent's runner", one row below "This job d | findings-01-open.md |
| F923 | D | open |  | F923 (D) -- small legibility slips on the vault doors: the Hub says "Distil" where the button now reads "Extract facts", a resolution is named with a  | findings-01-open.md |
| F924 | D | open |  | F924 (D) -- an agent's vault report that restates an open contradiction is reviewed without it: the reports job sees only the reported entry, calls th | findings-01-open.md |
| F925 | B | closed |  | F925 (B) -- a job whose agent a session sync deleted (or the operator archived) can still be enabled and fired; the press answers 500 and records the  | findings-02-closed-3.md |
| F926 | C | open |  | F926 (C) -- deleting a charter an agent holds asks the operator to confirm the loss of its text, then the Hub refuses; the refusal says "Unbind before | findings-01-open.md |
| F927 | D | open |  | F927 (D) -- the agent's Charter picker answers a refused binding with "Could not update charter binding." and keeps offering the charter it could not  | findings-01-open.md |
| F928 | B | closed |  | F928 (B) -- a permission card is shown in whichever of the agent's conversations is open, not the one whose run asked: under a finished review's trans | findings-02-closed-3.md |
| F929 | C | open |  | F929 (C) -- the New job form says nothing when the Hub refuses the job: Create is pressed, the dialog stays open, and no sentence appears | findings-01-open.md |
| F930 | D | open |  | F930 (D) -- a job's name may be blank: the route stores "  " on create and "" on rename, and the Jobs list, its menu and the archive confirm then name | findings-01-open.md |
| F931 | C | open |  | F931 (C) -- the Jobs tab's Archive confirm puts focus on the dialog's Close (X), not Cancel, and after Archive focus drops to the page | findings-01-open.md |
| F932 | C | open |  | F932 (C) -- deleting a document whose flow has finished also deletes the flow's job, its loop and every firing record, and nothing says so: not the co | findings-01-open.md |
| F933 | B | closed |  | F933 (B) -- a project or agent default of "Ask me" or "Workspace only" reaches an agent with no tool server as `manual` with nobody to answer: every w | findings-02-closed-3.md |
| F934 | C | open |  | F934 (C) -- the `allow_agent_jobs` refusal, its question and its answer send the operator to "Environment › Settings" and "their Questions destination | findings-01-open.md |
| F935 | C | open |  | F935 (C) -- the Granted reach row promises "writes outside are still recorded on the run", but a shell write into a granted folder, the very case the  | findings-01-open.md |
| F936 | D | open |  | F936 (D) -- Escape on a reach grant's host or folder field discards the entry but keeps the text, so the next "A host…" or "A folder…" opens prefilled | findings-01-open.md |
| F937 | D | open |  | F937 (D) -- the turn context's one-line vault index tells a call-mode (`aw-tool`) run to use `vault_map()` and `vault_read(entry_id)`, a call shape th | findings-01-open.md |
| F938 | B | open |  | F938 (B) -- the Overview's Collaboration block is gone: `CollaborationSummary` has rendered nowhere since the ui-finesse rewire, while its 14 tests st | findings-01-open.md |
| F939 | B | open |  | F939 (B) -- Project settings -> Quality can never show anything but "No quality governance configured", and it tells the operator to add a `quality:`  | findings-01-open.md |
| F940 | C | open |  | F940 (C) -- deleting a runner is one click on a hover icon, with no confirmation and no undo, unlike a charter; a provider runner's base URL and key-v | findings-01-open.md |
| F941 | D | open |  | F941 (D) -- after a confirmed action removes or disables the control that opened it, keyboard focus falls to `<body>`: a runner deleted, instructions  | findings-01-open.md |
| F942 | C | open |  | F942 (C) -- a Copilot provider runner whose key variable starts with `AW_` is refused as "one of the Hub's own credentials", even for a name that is n | findings-01-open.md |
| F943 | D | open |  | F943 (D) -- a Project settings link with an unknown or retired `section` (or none) lands on Quality, not General: the default is still the first entry | findings-01-open.md |
| F944 | B | closed |  | F944 (B) -- an agent's `read_spec_document include=full` never returns `delivery`, so a read, edit and resubmit silently erases the document's flow, a | findings-02-closed-3.md |
| F945 | B | closed |  | F945 (B) -- the Spec header's requirements fact counts every requirement not verified or rejected as "in progress", including ones not started and one | findings-02-closed-3.md |
| F946 | B | closed |  | F946 (B) -- the Spec header says "Vault agrees" on a project whose spec-vault check is off and has never run, and pressing "Check against the vault ag | findings-02-closed-3.md |
| F947 | C | open |  | F947 (C) -- the requirements popover says a merged requirement is "on master" on a project whose main branch is `main` | findings-01-open.md |
| F948 | C | open |  | F948 (C) -- the Spec header's keyboard layers: Archive and Delete confirms do not take focus, Ctrl+Shift+K opens the command palette under the documen | findings-01-open.md |
| F949 | C | open |  | F949 (C) -- every new document, and every phase move the Hub itself makes, lights a warn-toned "index issue" on every document's header until someone  | findings-01-open.md |
| F950 | D | open |  | F950 (D) -- the header's "Approved <date>" is the document's last update, not its approval: a rigor change moves it | findings-01-open.md |
| F951 | D | open |  | F951 (D) -- three small labels in the rebuilt Spec list and header: an untracked change is listed under "Overview", exploring reads "draft" in the lis | findings-01-open.md |
| F952 | B | closed |  | F952 (B) -- the Overview's spend line drops everything the budget card used to say: a turn with no reported cost counts as $0.00 with no caveat, "API- | findings-02-closed-3.md |
| F953 | B | closed |  | F953 (B) -- with the token budget spent, the Overview says only "Autonomous turns are paused; operator messages can still run.": no limit, no way to r | findings-02-closed-3.md |
| F954 | B | open |  | F954 (B) -- Jobs -> Run now toasts "fired — beta starts a turn now." when the Hub answered that the firing waits (`waiting_reason: "token budget exhau | findings-01-open.md |
| F955 | B | open |  | F955 (B) -- Checkpoint now is two browser requests: a reload while it says "Writing checkpoint…" leaves a paid, ready checkpoint nothing will ever cut | findings-01-open.md |
| F956 | D | open |  | F956 (D) -- five small accounting labels: "1 turns could not be priced", "100% used" at 266%, an empty bordered list under "Nothing has merged yet", " | findings-01-open.md |
| F957 | C | open |  | F957 (C) -- after F852, an unnamed piece at main's tip is still presented as the task's work to merge: the coverage bar says "Accepting may merge comm | findings-01-open.md |
| F958 | C | open |  | F958 (C) -- Scan for drift that cannot read the repository answers "Scanned the project: 0 new — 0 on this document", the same as a clean scan | findings-01-open.md |
| F1033 | B | open |  | F1033 (B) -- Settings → General's "Default permissions" option says "Claude and Codex: Workspace only. Copilot: Ask me.", but Codex runs at Edit files | findings-01-open.md |
| F1034 | C | open |  | F1034 (C) -- a Haiku planner writes a whole change document in one turn, never asks the operator or calls `advance_spec_step`, so the document stays a | findings-01-open.md |
| F1035 | C | open |  | F1035 (C) -- `hub/.env.example` tells the reader the CLI fetches the key "via `agentweave hub start` or `agentweave activate`", two commands that no l | findings-01-open.md |
| F1036 | D | open |  | F1036 (D) -- the agent's own rule files are stale: `.claude/rules/cli.md` says five `cmd_*` and "ALL task modifications use `with lock`", `.claude/ref | findings-01-open.md |
| F1037 | D | open |  | F1037 (D) -- `CHANGELOG.md` has no entry since `[1.1.0] - 2026-08-19` and no `[Unreleased]` section, over 3900 commits later | findings-01-open.md |
| F959 | B | open |  | F959 (B) -- a second `agentweave --profile <p> --port <m>` while the profile's Hub runs on another port starts a second Hub on the same database: ever | findings-01-open.md |
| F960 | B | open |  | F960 (B) -- the vault-reports job is shown only the first 50,000 characters of a fact's source, so a correct fact from further in is referred with "th | findings-01-open.md |
| F961 | B | open |  | F961 (B) -- the Activity tab's Ledger counts a Copilot turn's AI credits and an unpriced turn as $0.00: a Copilot-only project reads "Spent $0.00 · No | findings-01-open.md |
| F962 | C | open |  | F962 (C) -- after Copilot compacts a conversation, its context meter keeps the pre-compaction reading: the header says "104,485 / 128,000 · 81.63%" di | findings-01-open.md |
| F963 | B | open |  | F963 (B) -- an agent with no tool server whose *own* default is "Ask me" (or "Workspace only") shows that posture on its composer pill, its settings r | findings-01-open.md |
| F964 | B | open |  | F964 (B) -- the operator's answer to a cannot-satisfy report is delivered into the reporter's most recently active conversation, not the one that repo | findings-01-open.md |
| F965 | C | open |  | F965 (C) -- an agent asking to move a task out of `blocked` after its own cannot-satisfy report is refused with the sentence for a question wait ("the | findings-01-open.md |
| F966 | C | open |  | F966 (C) -- a flow document that names `delivery.tester` is still warned `reviewer_undeclared` ("the flow will give each review to any free agent"), t | findings-01-open.md |
| F967 | B | open |  | F967 (B) -- an agent's evidence whose locator names its test file watches only that test file, so reverting the implementation on the main line raises | findings-01-open.md |
| F968 | B | open |  | F968 (B) -- a granted agent rejecting an awaiting piece of a *completed* task leaves the task completed and tells its author nothing: the reason the t | findings-01-open.md |
| F969 | C | open |  | F969 (C) -- on the Spec page the coverage panel and the header's requirements fact name the same states in different words, and every drifting row poi | findings-01-open.md |
| F970 | B | open |  | F970 (B) -- a *loop* job whose agent a session sync deleted (or the operator archived) answers Run now with 500 "Failed to fire job", and every firing | findings-01-open.md |
| F971 | C | open |  | F971 (C) -- Run on a loop whose agent has no runner answers, on the second press, "Every task on this loop's queue is already being worked … nothing i | findings-01-open.md |
| F972 | C | open |  | F972 (C) -- a firing queued behind another waiting entry for the same agent answers 200 with no `waiting_reason` | findings-01-open.md |
| F973 | C | open |  | F973 (C) -- an ended or archived loop still accepts definition edits and control changes, and its tab then says the edit "applies at the next firing"  | findings-01-open.md |
| F974 | C | open |  | F974 (C) -- after a press, the Loop tab and the Jobs screen take 4-5 s to show what the Hub applied in 0.3 s; one Delegate press fires about 59 GETs | findings-01-open.md |
| F975 | D | open |  | F975 (D) -- the one-loop-per-document refusal names only ids and gives no way out | findings-01-open.md |
| F976 | B | open |  | F976 (B) -- a tester's own `change_criterion` amendment makes the builder's evidence stale, so the tester's approval is refused, and every remedy offe | findings-01-open.md |
| F977 | D | open |  | F977 (D) -- a drained flow reads "Active · Waiting for its next firing · Next: Jan 1 2027" after its last approval; the stop is recorded only when som | findings-01-open.md |
| F978 | D | open |  | F978 (D) -- two labels in the review machinery: an operator's send-back reaches the author as "The reviewer sent it back", and a withdrawn review's re | findings-01-open.md |
| F979 | B | open |  | F979 (B) -- when a project's own `.git` is unreadable and its folder sits inside another repository, the Hub uses the enclosing repository: it creates | findings-01-open.md |
| F980 | C | open |  | F980 (C) -- `PUT /project/documents/{path}/content` answers a bare 500 when the document's file cannot be written | findings-01-open.md |
| F981 | C | open |  | F981 (C) -- `POST /vault/sources` answers a bare 500 when the tracked vault root `knowledge/` cannot be written (F717's fix covered only the private l | findings-01-open.md |
| F982 | C | open |  | F982 (C) -- the first Claude turn after an interrupted or stopped turn in the same session records no cost, though the CLI reported it | findings-01-open.md |
| F983 | C | open |  | F983 (C) -- a corrupt `.agentweave/project.json` in a registered folder cannot be fixed from the app: open answers 409, and the remedy it offers answe | findings-01-open.md |
| F984 | D | open |  | F984 (D) -- propose, phase and rigor on a document whose file is invalid JSON say it "has not been written by the Hub", which is false | findings-01-open.md |
| F985 | D | open |  | F985 (D) -- `POST /tasks/{id}/checks/run` answers 202 `{"run_id": null, "running": false}` with checks configured and starts nothing, without saying w | findings-01-open.md |
| F986 | B | open |  | F986 (B) -- an answer to a question whose asking run has ended is delivered into the agent's most recently active conversation, not the one the questi | findings-01-open.md |
| F987 | C | open |  | F987 (C) -- Stop on a Claude run blocked in an `aw-tool ask_user` call leaves that call's process tree running until the question's own deadline, hold | findings-01-open.md |
| F988 | C | open |  | F988 (C) -- an archived conversation opened by its URL reads "New conversation" in its header, with no archived notice, "Continuing this conversation" | findings-01-open.md |
| F989 | C | open |  | F989 (C) -- the conversation side panel names a fresh, unindexed document by its minted folder ("silver-fenrir"), not its title, so the panel's "Searc | findings-01-open.md |
| F990 | D | open |  | F990 (D) -- the composer's `$` menu offers a skill's supporting files as skills | findings-01-open.md |
| F991 | D | open |  | F991 (D) -- an operator start naming an unknown `task_id` is refused with the agent-delegation sentence ("A delegation may only name a task in the pro | findings-01-open.md |
| F992 | D | open |  | F992 (D) -- Stop is keyed by agent, not by run, so a Stop arriving after its run ended stops the next turn the queue just started, in another conversa | findings-01-open.md |
| F993 | C | open |  | F993 (C) -- the "events were not delivered" notice has no screen: `ActivityLog`, the only component that renders `stream_gap`, mounts only when `GET / | findings-01-open.md |
| F994 | C | open |  | F994 (C) -- a query bound written with a non-UTC offset is compared as its wall-clock time: `DELETE /traces?until=<an hour ago, +02:00>` deleted trace | findings-01-open.md |
| F995 | B | open |  | F995 (B) -- the run-text redaction joins a Claude turn's separate thinking and text blocks as one string: a value split across two replies is not reda | findings-01-open.md |
| F996 | D | open |  | F996 (D) -- after a killed turn, the Hub's automatic re-delivery reads in the Activity digest as a second operator turn with the same message, and its | findings-01-open.md |
| F997 | C | open |  | F997 (C) -- every check run's trace shows routine git answers as red error spans: `merge-base --is-ancestor` exit 1 and `worktree unlock`/`remove` exi | findings-01-open.md |
| F998 | C | open |  | F998 (C) -- a secret in a project check's command is stored and served verbatim in the `project_settings_updated` event, while the same event's copy o | findings-01-open.md |
| F999 | D | open |  | F999 (D) -- Clear leaves its own `DELETE /traces` request trace behind: the screen reads "0 traces" while the Hub holds 1, and the next clear promises | findings-01-open.md |
| F1000 | D | open |  | F1000 (D) -- the task story reads "0 tokens" for a run whose usage was never reported | findings-01-open.md |
| F1001 | D | open |  | F1001 (D) -- a Claude run that fails at CLI startup is traced as a 3.3 s model call whose assistant output is the CLI's error, and the root says only  | findings-01-open.md |
| F1002 | D | open |  | F1002 (D) -- a retried delivery's trace starts at the input's first arrival: attempt 3 reads "22.1 s" with an 18.6 s delivery bar, for a turn that "Wo | findings-01-open.md |
| F1003 | D | open |  | F1003 (D) -- a trace carrying a Hub warning looks like every other trace in the list and the drawer header; the warning appears only in the root span' | findings-01-open.md |
| F1004 | D | open |  | F1004 (D) -- a mistyped `otlp_headers` body is refused with the header's value echoed in `detail[].input` | findings-01-open.md |
| F1005 | B | open |  | F1005 (B) -- Retry merges whatever the task's branch now points at: a commit pushed after approval lands on main with no check run, no review and no o | findings-01-open.md |
| F1006 | C | open |  | F1006 (C) -- after Try again lands a re-resolved branch, the drawer still reads "Merge failed -- CONFLICT ..." above the merge and keeps offering Try  | findings-01-open.md |
| F1007 | C | open |  | F1007 (C) -- a merge that fails on a conflict is recorded with git's "fix conflicts and then commit the result" after the Hub has already aborted it;  | findings-01-open.md |
| F1008 | D | open |  | F1008 (D) -- a hand-made task with no branch is told "no accepted evidence names a commit" on approve, retry and preview, the evidence sentence F622 r | findings-01-open.md |
| F1009 | C | open |  | F1009 (C) -- after a send-back, merging a task's own branch shows an amber warning that "1 earlier commit on the same branch also landed with this mer | findings-01-open.md |
| F1010 | C | open |  | F1010 (C) -- the drawer says "Approving will not merge anything: no accepted evidence names a commit, so there is nothing to merge" beside a task whos | findings-01-open.md |
| F1011 | C | open |  | F1011 (C) -- an agent's illegal-move refusal names moves the same route then refuses that agent: "available: assigned, blocked, completed" (blocked is | findings-01-open.md |
| F1012 | D | open |  | F1012 (D) -- the task story records the operator's send-back and block with no reason: "You moved it to sent back" and "You moved it to waiting on you | findings-01-open.md |
| F1013 | C | open |  | F1013 (C) -- the same-file warning compares declared paths as raw strings: `./lib.py`, `pkg//lib.py`, `pkg/../pkg/lib.py`, `.` and a case variant all  | findings-01-open.md |
| F1014 | C | open |  | F1014 (C) -- a document's tasks with no `files` are named only to the agent that saves it: propose, the approval 409 and the approval report never men | findings-01-open.md |
| F1015 | C | open |  | F1015 (C) -- the approval gap list shows one same-file pair however many there are: "unordered_file_overlap ×2 -- tasks 't1' and 't2' both declare 'li | findings-01-open.md |
| F1016 | B | closed |  | F1016 (B) -- an operator's "nothing merges" (Main branch cleared) is silently undone the next time the folder is opened: the Hub re-adopts `master`, r | findings-02-closed-3.md |
| F1017 | C | open |  | F1017 (C) -- a second Browse while the native folder dialog is open says only "The folder dialog could not be opened.": the Hub's 409 "A folder dialog | findings-01-open.md |
| F1018 | C | open |  | F1018 (C) -- deleting a project while a run is active is refused with "project cannot be deleted while a run is active": no run, no agent, no way out  | findings-01-open.md |
| F1019 | C | open |  | F1019 (C) -- the Instructions editor saves over instructions written since it loaded: a stale tab silently replaces a newer save, with no conflict che | findings-01-open.md |
| F1020 | D | open |  | F1020 (D) -- naming a main branch on a project that is not a git repository is refused as "This project has no branch named 'main' ... it has to exist | findings-01-open.md |
| F1021 | D | open |  | F1021 (D) -- F729 is back: deleting a project fires six GETs of the deleted project (all 404), and the app lands on another project's Overview with no | findings-01-open.md |
| F1022 | D | open |  | F1022 (D) -- small Projects items from the 2026-10-23 sweep: `/favicon.ico` is index.html, identical compact-rail tiles, a typed UNC path ignored by t | findings-01-open.md |
| F1023 | C | closed |  | F1023 (C) -- rebinding an agent to a runner of another CLI resumes the conversation's old provider session on the new CLI: Copilot starts over with a  | findings-02-closed-3.md |
| F1024 | C | closed |  | F1024 (C) -- a conversation's per-run model survives the agent's rebind to another CLI and is handed to it as is: Copilot was launched with `--model h | findings-02-closed-3.md |
| F1025 | C | open |  | F1025 (C) -- the Manager screen's model menu lists no aliases, so a job's model stored as `sonnet` (accepted by the API and stored as written) reads " | findings-01-open.md |
| F1026 | D | open |  | F1026 (D) -- unarchiving an agent whose runner was deleted while it was archived answers "An agent with no charter still runs" while it has no runner  | findings-01-open.md |
| F1027 | C | closed |  | F1027 (C) -- one Escape on the Add-agent dialog's open Provider list closes the whole dialog and throws away the typed name; the list takes no arrow k | findings-02-closed-3.md |
| F1028 | C | closed |  | F1028 (C) -- Ctrl+K over an open dialog or the task drawer: the palette opens on top, but the first Tab moves focus into the dialog behind it, and typ | findings-02-closed-3.md |
| F1029 | C | closed |  | F1029 (C) -- the Vault's Add and Vault storage dialogs drop keyboard focus to `<body>` on every close: Escape, Cancel and the X alike | findings-02-closed-3.md |
| F1030 | C | closed |  | F1030 (C) -- in the task drawer, Escape on the inline "Delete this task?" confirm closes the whole drawer, not just the confirm | findings-02-closed-3.md |
| F1031 | C | closed |  | F1031 (C) -- a task can be renamed only with a mouse: the drawer's title is a click-only heading, and after Enter or Escape in the title field focus f | findings-02-closed-3.md |
| F1032 | C | closed |  | F1032 (C) -- the pane resizers are tab stops with no visible focus: the line meant to light up on focus is pinned to its resting colour by an inline s | findings-02-closed-3.md |
| F1038 | B | closed |  | F1038 (B) -- removing a task worktree that holds a `node_modules` junction empties the main checkout's `node_modules`: `git worktree remove --force` f | findings-02-closed-3.md |
| F1039 | C | closed |  | F1039 (C) -- the operator stream opened twice when its last subscriber unmounted mid-connect, so every event reached every listener twice | findings-02-closed-3.md |
| F1040 | C | open |  | F1040 (C) -- a spec-only change whose one task is the fold can never show Fold, and nothing says why | findings-01-open.md |
| F1041 | C | open |  | F1041 (C) -- the fold dialog's retire list is collapsed, so two folds in a row retired nothing they were meant to | findings-01-open.md |
| F1042 | B | closed |  | F1042 (B) -- the first chapters run on a real project is refused: the prompt says new knots may be left out, the Hub requires all of them on a first v | findings-02-closed-3.md |
| F1043 | B | closed |  | F1043 (B) -- every run longer than 10 minutes is reported dead: the stall sweep reads a heartbeat column nothing writes | findings-02-closed-3.md |
| F1044 | C | open |  | F1044 (C) -- the specs need an ordering | findings-01-open.md |
| F1045 | C | closed |  | F1045 (C) -- Overview shows notifications that cannot be dismissed and offer nothing to do | findings-02-closed-3.md |
| F1047 | A | closed |  | F1047 (A) -- input queued into an archived conversation wedges the agent's whole queue | findings-02-closed-3.md |
| F1048 | A | closed |  | F1048 (A) -- a stall the mender gave up on is raised again on the next firing, and the mender is woken again: 30 turns overnight on one unchanged situ | findings-02-closed-3.md |
| F1049 | B | closed |  | F1049 (B) -- `loop_stalled` fires in the seconds between a task finishing and the flow handing it on | findings-02-closed-3.md |
| F1050 | C | closed |  | F1050 (C) -- a `stuck_task` stall for a task that no longer exists stays open forever | findings-02-closed-3.md |
| F1051 | B | closed |  | F1051 (B) -- the newest integration row is chosen by timestamp alone, and one approval writes several rows with the same timestamp | findings-02-closed-3.md |
| F1052 | C | open |  | F1052 (C) -- approval drops a declared task whose requirements a hand-made task already serves, even when it is different work | findings-01-open.md |
| F1053 | C | closed |  | F1053 (C) -- every press of Check starts the vault's spec check, a model run, even for unchanged or blocked content | findings-02-closed-3.md |
| F1054 | C | closed |  | F1054 (C) -- a flake the task itself introduces lands with the Hub's automatic override | findings-02-closed-3.md |
| F1055 | C | open |  | F1055 (C) -- the Hub's acceptance-drive rule and its test-only-task rule cannot both be met: `no_acceptance_drive` asks for a first task every other t | findings-01-open.md |
| F1056 | B | open |  | F1056 (B) -- a build can land only on `main` or `nowhere`, and on a project whose checkout the Hub runs from, landing anywhere but `master` means swit | findings-01-open.md |
| F1057 | C | open |  | F1057 (C) -- the build record and the project view lack the figures a measured comparison needs: no base commit, no landing branch, no runs or models  | findings-01-open.md |
| F1058 | C | open |  | F1058 (C) -- a document can be built once: a second build covers only its open tasks, so after one build approves them the next has nothing to build,  | findings-01-open.md |
| F1059 | B | closed |  | F1059 (B) -- inside a flow, a builder's completion is recorded without waiting for the fast checks: two flow tasks completed in ~0.4 s and their first | findings-02-closed-3.md |
| F1060 | B | closed |  | F1060 (B) -- a re-completion of unchanged work is refused with the earlier run's output and never says the work is unchanged or which checkout is chec | findings-02-closed-3.md |
| F1061 | C | open |  | F1061 (C) -- returning a task to its builder after its own check failure neither wakes nor tells the builder | findings-01-open.md |
| F1062 | D | open |  | F1062 (D) -- the checks' return of a task to its builder is recorded as `actor_kind='operator'`; only `origin='checks'` says otherwise | findings-01-open.md |
| F1063 | B | closed |  | F1063 (B) -- at Fast a builder's approval is refused because its evidence is unjudged, so "Fast approves without a reviewer" never fires | findings-02-closed-3.md |
| F1064 | B | closed |  | F1064 (B) -- the Hub's own batched landings raise "main moved" notices, and join an open one, because their integration rows carry no merge sha | findings-02-closed-3.md |
| F1065 | B | closed |  | F1065 (B) -- a "no reviewer free" stall names agents outside the build's reviewer pool as "running a turn" when they are not running | findings-02-closed-3.md |
| F1066 | C | open |  | F1066 (C) -- a resubmission without `roadmap` silently unlinks a document from its roadmap slice | findings-01-open.md |
| F1067 | C | open |  | F1067 (C) -- three small refusal/field defects in slices D and D2: `next-slice/take` with an unknown agent answers code `no_offer`; `builds/{id}/stop` | findings-01-open.md |
| F1068 | C | open |  | F1068 (C) -- on a hand-driven build each amendment decision queues a paid turn for the proposing lead, and those unbound lead runs are not counted in  | findings-01-open.md |
| F1069 | B | closed |  | F1069 (B) -- the composer's "Open an existing specification document" picker overflows its dialog: 697 px of content in a 558 px dialog, "+ New", "Roa | findings-02-closed-3.md |
| F1070 | B | closed |  | F1070 (B) -- the side panel at 360 px clips the spec page's approval-gaps block (scrollWidth 392 vs 360), against `side-panel-parity` | findings-02-closed-3.md |
| F1071 | C | closed |  | F1071 (C) -- Ctrl+Shift+K opens the spec picker on top of the command palette: two layers, two Escapes | findings-02-closed-3.md |
| F1072 | C | open |  | F1072 (C) -- slice F/G/I friction: Ctrl+K's "Spec documents" is a flat list while the real picker lives on Ctrl+Shift+K; a running build's header offe | findings-01-open.md |
| F1073 | B | open |  | F1073 (B) -- the mender offers answers it cannot carry out and misstates the evidence gate: "Approve without the check -- operator approval overrides  | findings-01-open.md |
| F1074 | B | open |  | F1074 (B) -- at Gated, a criterion checked by the operator blocks approval until the operator records full evidence, and nothing says so before it hap | findings-01-open.md |
| F1075 | C | open |  | F1075 (C) -- a build's checks queue two at a time, with no view of queue time, and the side-by-side suites make timing tests fail; Fast spent 70 of it | findings-01-open.md |
| F1076 | C | open |  | F1076 (C) -- the mender woke on a "no progress" stall while a healthy check run was queued, called it possibly hung and recommended killing it | findings-01-open.md |
| F1077 | C | open |  | F1077 (C) -- a build record's `spent_usd`, which the cap reads, leaves out the mender turns its own figures count ($0.87 vs $1.05 at Fast, $2.47 vs $2 | findings-01-open.md |
| F1078 | C | open |  | F1078 (C) -- a check run with failing tests that were approved over as not the task's is recorded as `passed` | findings-01-open.md |
| F1079 | C | open |  | F1079 (C) -- slice H: numbers no view shows: a build's base commit, the per-run model, operator actions, escaped defects, mender wakes with nothing st | findings-01-open.md |
| F1046 | C | open |  | F1046 (C) -- a spec document's task can name its reviewer but not who builds it | findings-01-open.md |
| F1080 | B | closed |  | F1080 (B) -- a flow that stops on an empty queue stays stopped when the landing checks send one of its tasks back | findings-02-closed-3.md |
| F1081 | B | closed |  | F1081 (B) -- re-completing a sent-back task checks the commit its old accepted evidence names, not the fix | findings-02-closed-3.md |
| F1082 | A | open |  | F1082 (A) -- an agent turn's auto-snapshot committed the main checkout's untracked files onto master | findings-01-open.md |
| F1083 | B | partly |  | F1083 (B) -- a hand-driven build's builder sees only the document's recommended delivery, and `create_flow` on that document is not refused | findings-01-open.md |
| F1084 | B | open | stale? 0390653 | F1084 (B) -- a completion outside a turn schedules its check run before it commits, so the run can see the task uncompleted, start nothing, and refuse | findings-01-open.md |
| F1085 | B | open |  | F1085 (B) -- Check and `submit_spec_document` say "ready to approve", then approval refuses with gaps neither reported | findings-01-open.md |
| F1086 | B | open |  | F1086 (B) -- the Hub's own knowledge-vault output dirties the project checkout and blocks its own landing | findings-01-open.md |
| F1088 | C | closed |  | F1088 (C) -- a document whose default checker is named `checker` reads on its spec page as "the document names no reviewer" | findings-02-closed-3.md |
| F1089 | B | closed |  | F1089 (B) -- a spec whose build finished reads `approved`, the same as one never built, so the operator cannot tell which specs are done | findings-02-closed-3.md |
| F1090 | B | open |  | F1090 (B) -- side-finding tasks bound to a finished spec keep it from folding, and a duplicate pending task cannot be rejected | findings-01-open.md |
| F1091 | C | open |  | F1091 (C) -- a landing's send-back that is refused leaves the task approved with its landing recorded sent back | findings-01-open.md |
| F1092 | B | open |  | F1092 (B) -- a build's default builder is not honoured in a flow: any free agent takes a task that names no builder | findings-01-open.md |
| F1093 | C | open |  | F1093 (C) -- Run now on a build past its window answers a bare 500 "Failed to fire job" although the stop worked | findings-01-open.md |
| F1096 | C | open |  | F1096 (C) -- a completion with uncommitted work first spends a full check run on the older commit | findings-01-open.md |
| F1094 | C | open |  | F1094 (C) -- a capability's header reads `Approved` with a change's stepper, though its phase is `current` | findings-01-open.md |
| F1095 | B | open |  | F1095 (B) -- creating a document over a file the Hub has no row for answers 201 and destroys the file | findings-01-open.md |
