# LoopEngine on `:8000` — a read-only review, 2026-09-14

Project `LoopEngine`, `proj-03b9c6a6c37a`, resolved by name. Working directory
`C:\Users\huida\Documents\projects\LoopEngine`. Authority: `DIRECTION.md` `## 2026-09-14` § O,
`day-window.md` `## O`.

**How this was read.** The operator's database `~/.agentweave/hub/data/agentweave.db` was opened
only as `sqlite3.connect("file:…?mode=ro", uri=True)` from `py -3.11`. Every table was filtered on
`project_id`. `:8000` was not called. The Hub was still writing while this was read: the newest
event is `2026-09-14 08:30:00` and the newest agent output is `07:02:24`. The counts below are a
snapshot, and they have roughly doubled since the 2026-09-13 23:15 measurement in `DIRECTION.md`
(134 → 277 runs). **Stored times are UTC**, checked against the provider's own reset times, which
are given in Lisbon time (UTC+1) and match the retries stopping. Times below are UTC.

LoopEngine's text is cited by id and paraphrased, never quoted. Quoted strings are AgentWeave's own
output.

## What happened

### The inventory

| | |
|---|---|
| **Agents** | `Architect`: runner *Claude Code · Opus 5*, the only agent with a charter bound (*Spec Author*), and `can_accept_evidence`. `tester`: Opus 5, no charter, `can_accept_evidence`. `dev` and `dev_2`: Sonnet 5, no charter. `dev_2` was added on 09-13 16:30. All four were created by the operator. No agent overrides the permission mode or timeouts. |
| **Other runners** | *Claude (default)*, *Codex (default)*, and an operator-made *Haiku* runner, which is bound to no agent. The checkpoint worker ran Haiku. |
| **Starter charters** | All 9 were seeded, and 8 of them are unbound. |
| **Project settings** | Hop budget 6, turn-delivery cap 10, agent budget 8, agent jobs allowed, no token budget, `main_branch` `main`, checkpoints `offered`. |
| **Runs** | 277: 205 completed, 72 failed. 245 were autonomous and 32 operator-initiated (31 of them the Architect, the spec conversation). |
| **Queue entries** | 268: 219 delivered, 27 withdrawn or abandoned, **20 still `queued`**. |
| **Tasks** | 50: 32 created from the approved spec and 18 created by agents. Now 10 approved, 12 completed (awaiting review), 1 under review, 3 in progress, 23 pending, 1 rejected. |
| **Transitions and integrations** | 110 transitions. 21 integrations: 13 merged, and 8 skipped. |
| **Evidence** | 79 rows: 38 accepted, 35 rejected, 6 awaiting. There are 73 evidence reviews, and `tester` made 68 of them (34 accepted, 34 rejected). 24 of the 79 footprints are not reachable from `main`. |
| **Divergences** | 112, of which 105 are under the `surface` policy (20 of those on failed runs) and 7 under `review` (3 restaffed). **72 are unresolved.** |
| **Other** | 192 messages, all peer: Architect↔tester dominates, with 7 delegations and 17 reviews. 23 questions in 9 batches. 14 checkpoints: all `task_completion`, 7 `passed` and 7 `failed` probe. 1 job, 1 loop, 43 job runs. No permission requests. |
| **Tokens** | 484.6 M total, of which 470.7 M are cache reads. The API-equivalent cost is **$281.75**. By agent: `dev` (Sonnet) 323 M / $114.21; `Architect` 50.6 M / $81.36; `tester` 81.8 M / $76.05; `dev_2` 29.0 M / $10.13. 67 runs measured 0 tokens (the failed spawns) and 3 are `unavailable`. |

### The lifecycle, as it ran

**Spec, 09-12 20:39 → 09-13 15:46: operator and Architect.**
- The operator created the spec document `spdoc-97d90a3506f5` and worked it with the Architect over
  31 operator-initiated runs in two sittings: 09-12 20:39–01:19 and 09-13 13:50–15:37. The Architect
  wrote it through 20 content revisions.
- The Architect asked 15 questions through `ask_user`, in 5 batches, and all were answered. In three
  of the batches (23:26, 14:38 and 16:50), the answers arrived **after the wait had already expired**:
  the wait ended at 23:30 and the answers came at 23:43–23:44. The agent had moved on without them.
- Along the way, the Architect wrote draft spec JSON to `%TEMP%`. Those writes account for some of
  its 21 `agent_wrote_outside_workspace` warnings.
- At 15:46:22–27 the operator moved the document `exploring → proposed → approved` in five seconds.
  Approval created 32 tasks. 77 requirements are now active and 2 retired.

**Setting up the loop, 09-13 16:30–17:46: the Architect, on the operator's instruction.**
- The Architect gave `dev_2` a spike task (`task-5abfa8390fd6`) and blocked it on three operator
  questions.
- In run `run-113f7e6b75f7` it created job `job-79fdadb95db9` (`dev`, `*/5 * * * *`, new session
  per fire) and loop `loop-103ecb8aeb89`. The loop is bound to the spec, stops when the queue
  empties, and **has no `stop_at`**.
- The operator fired the job by hand three times (16:44, 17:12, 17:46). The schedule has fired it
  ever since.
- The first landing was refused twice before it worked:
  - at 17:20, *"this project has no main branch set — choose one in the project's settings"*;
  - at 17:21 (the operator), *"no accepted evidence names a commit, so there is nothing to merge"*;
  - `tester`'s run merged it at 18:56.
  - The 17:20 worktree release also failed, with one unmerged commit.

**The build, 09-13 17:25 → 09-14 07:02: the agents.**
- **How the work flowed.** The job staffed one step per tick. `dev`/`dev_2` implemented, and
  `tester` reviewed and landed: it made most of the 13 merges and most of the evidence decisions.
  The Architect created 18 follow-up tasks (a DNS-rebinding guard, a route-gate table, Node 24 test
  runs, a Windows spawn fix and others) and reviewed.
- **The heaviest hours were 18:00–21:00** (13, 37 and 22 runs). From 19:20, **21 peer-message
  chains hit the hop budget at depth 7** and were suspended (`queue_chain_suspended`): 10 in the
  19:00 hour, one each at 21:00 and 23:00, and 9 between 04:00 and 06:46. One was released at 06:10.
  The other **20 are still `queued`**, two to thirteen hours later, and every one has an empty
  `waiting_reason`. *(Corrected in O-2. O-1 first put all 21 at 19:20–19:30.)*
- **Staffing stalled 243 times** (`review_unstaffed`):
  - 180 × *"could not staff this step: no agent is free to take it. Every agent on the roster is
    either running a turn, already holding active work, or is the one…"* (F352's shape);
  - 63 × the Architect *"is named on … as its reviewer and is not reviewing it: no turn is running
    on that task and none is queued"* (`task-9e89a55ccc84` and others).
  - Two job ticks were skipped outright, at 21:20 and 05:25.
- **Three provider session limits.** Each time, the Hub kept re-spawning into a quota that could
  not serve it:
  1. **21:00–21:05**: 9 runs failed.
  2. **01:19–02:05**: 43 runs in the hour, about 40 of them failing in 6–10 s each with the
     provider's session-limit notice and `Run failed (exit 1).`
  3. **06:57–07:02**: 12 failed runs, and nothing since.

  The mechanism, traced on `entry-3203bb7ad4e0` at 01:25: a job entry is delivered, the run fails,
  and the entry is re-queued and re-delivered about 10 s later, three deliveries in all. The
  second delivery *resumed* the failed session and the third started a *new* one
  (`run-42cae48b5e1f`, `run-895a732851b8`, `run-9f6ddd243259`). Then the entry is abandoned:
  *"delivery failed 3 times; the Hub stopped retrying"* (25 entries). Five minutes later the next
  tick queues a fresh one, and peer messages go through the same cycle. The notice itself states
  when the quota resets, and the Hub does not read it.
- **Three runs failed on the Hub's own write, not the agent's work.** `run-539bd1d44ea1` (35 min,
  304 outputs), `run-d5f4b2972125` and `run-7695d6f7b4b4` all ended
  `(sqlite3.OperationalError) database is locked` on `INSERT INTO agent_outputs`.
- **The questions went unanswered overnight.** From 00:01 the Architect (7) and `tester` (1) asked
  8 questions, and **none was answered**. Each wait ended about 4 minutes later, and the agents
  carried on.
- **Checkpoints and worktrees.** 7 of the 14 checkpoints failed their probe (Haiku, every one on a
  task completion). 4 task-worktree releases failed after merge on Windows with *"failed to delete
  … Permission denied"*.
- **The workspace guard refused tool calls 262 times** (`permission_denied`). By cause:
  - **85:** an agent reading its own harness's saved tool output under
    `~/.claude/projects/…/tool-results/`;
  - **68:** `/`-rooted relative paths inside Bash (`/src/engine`);
  - **45:** globs (`/*.test.js`);
  - **15:** `/dev/null`;
  - **45:** regex fragments (`'\b'`, `'\n'`) and `$VAR` arguments, which are *"outside your
    workspace"* or refused as unresolvable;
  - **4:** other `~/.claude` paths.

**The operator's own hand, 09-13 22:33, as distinct from the agents.**
- The operator landed `task-611ae46fe0fb` and `task-c8d4a3d70c19` by hand. Each went `completed →
  under_review → approved` and was merged by `operator` in about 0.1 s.
- They rejected `task-5420e60359c1` from `in_progress`. The Architect had already opened a
  replacement, `task-c3d80ccad5e8`, at 19:18.
- **One attribution to check in O-3.** `task_transitions` records **32** transitions with
  `actor_kind = operator`. Only the three at 22:33 and those inside the three manual job fires line
  up with the operator acting. **The other ~26 fall exactly on the job's cron ticks** (17:25:00,
  19:00:00, 19:10:00 … 04:10:00): `pending → assigned` and `completed → under_review`, done by the
  loop's step staffing, recorded as the operator. This is unverified in code.

**How it stands.**
- No agent has produced output since 07:02, the third quota wall.
- The job is still enabled (`next_run` 08:35), and the loop has no stop time.
- 23 tasks are pending and 12 are completed but unreviewed.
- 72 divergences sit surfaced and unresolved.
- 20 suspended messages wait on a release nobody has given.
- About a third of the spec's work has landed: 10 of its 32 tasks are approved, 5 completed, 1
  under review and 16 pending.
- None of the Architect's 18 follow-up tasks is approved yet: 7 completed, 3 in progress, 7 pending
  and 1 rejected.

## What the agents experienced

**How this was read.** Each run's `runs.session_id` is the name of its `claude` transcript. All 29
of the Architect's sessions (96 runs) matched a file under
`~/.claude/projects/C--Users-huida-Documents-projects-LoopEngine*`, so no matching by start time was
needed. The transcripts were parsed read-only by scripts in `%TEMP%\o2`, which count and classify
tool calls, errors and the Hub's own strings, then read at the points those counts flagged. Also
read: the notes the agents saved in the harness's memory directory for the project root
(`…LoopEngine/memory/`, 19 files), paraphrased here. Only AgentWeave's own strings are quoted.

### Architect

**The shape of it.** 96 turns: 31 started by the operator (the spec conversation and three chats),
55 woken by a peer message, and 10 by the job. 745 tool calls, 99 of them errors: 58 workspace-guard
refusals, 24 refusals from AgentWeave's own tools, and 17 ordinary ones (a `Read` over the 25k-token
limit, a bad regex). The waking messages reached hop 6 eight times, mostly Architect↔`tester`
threads. Nine turns made no tool call at all. Two were the quota wall; the other seven only
acknowledged a peer (`32be7c52` 18:50, 19:01 and 19:15, `0682583f` 19:59, `8b72ca10` 20:43,
`d6e79412` 21:18 and `4712e387` 04:00).

**1. The spec it was told to read never fitted in a tool result.** `read_spec_document` says
*"Use this before writing code against a document"* and warns that the document is *"not in your
working copy, so you almost certainly cannot open it as a file"* (`mcp_server.py:1673-1676`).
- The Architect called it 17 times. **Every one of the project's 57 `read_spec_document` results,
  across all four agents, was too large for the harness.** Each was saved to a `tool-results/` file
  of 80–180 KB, on a single JSON line. `list_tasks` spilled 24 times.
- The tool offers no filter narrower than `requirements` or `full` (`mcp_server.py:1668-1670`).
- 27 of the Architect's 58 guard refusals were a `Bash` or `PowerShell` command naming that spill
  file, which lies outside the workspace (runs `e8a7175b` 00:00, `b402c14e` 14:26, `6b7de822`
  16:25, `49d507bb` 17:46, `32be7c52` 18:35, `ca29c639` 18:59, `1e845986` 19:02, `0682583f` 19:40,
  `712ab8e3` 19:50 …).
- `Read` of the spill mostly went through, but it cannot page a single line. The workaround was
  `Grep` with short captures, each one a separate call. Once (`712ab8e3` 19:50) it spawned a
  general-purpose subagent just to pull three requirements out of the file.
- In the end the agents' shared notes settled on the opposite of what the tool description says:
  read the `spec.html` committed in your own checkout, which carries the structured JSON one field
  per line.
- The tools also disagree on how a document is named. `list_evidence` took `spdoc-97d90a3506f5`.
  `read_spec_document` refused the same id with *"path must begin with 'spec/'"* (`31c766dd` 03:49),
  and the Architect then grepped its own spill files to recover the path.

**2. Guard refusals that were not about the workspace.** Of the other 31 refusals, 2 named the
harness's memory file. The remaining 29 quoted fragments that are not paths outside the workspace:
- regex pieces inside PowerShell `-match` and Python one-liners (`'\\b'`, `'\\s+(auth'`,
  `'/script'` from a `<script` pattern, `'/\\1'` from a back-reference);
- ten relative globs (`'/*.test.js'`, `'/**/*.test.js'`);
- `'/dev/null'`, `'/tmp'`, and a relative path after a `cd` (`'/changes/…/spec.html'`).

Each cost a retry. The standing fix was to write a throwaway script into the checkout, run it and
delete it (`6b7de822` 17:03–17:15). The agents' shared notes hold a long list of these workarounds.
They also hold a wrong model of the rule: the notes say the boundary follows the shell's current
directory, but `_decide` resolves relative words against the workspace root and never sees a `cd`
(`mcp_server.py:1308-1311`).

**3. The review briefing told it to approve, and the Hub refused.** The flow's review turn says
*"End the review with a verdict, using `update_task`. The task is `under_review`: set it to
`approved` if the work is right"*. It says nothing about evidence.
- Five approvals were refused: `49d507bb` 18:00, `0682583f` 19:41, `712ab8e3` 19:52, `37dd5b7a`
  20:11 and `8b72ca10` 20:32. Each got *"This task's work has been recorded and nobody has judged it
  … To land it, accept the evidence, or grant an agent the capability to accept it — both are the
  operator's"*.
- At 18:00 the Architect had already messaged `dev` that the task was approved, and had to send a
  correction.
- The operator then gave `tester` `can_accept_evidence`, and the Architect routed every evidence
  decision through `tester` from then on. That routing is one of its saved notes, and it lengthened
  every Architect↔`tester` thread.
- The same 17:46 briefing said the task was `under_review` while its own queue listing, a few lines
  below, showed it `(completed)`. The step's `completed → under_review` transition was recorded at
  17:46:34.027, with `actor_kind = operator` and no run, after the listing was rendered.

**4. It could not finish or close work, and the way out it was offered named a missing control.**
- **7 refusals of the form *"Cannot move a task from 'completed' to …"*:** 5 to `approved`, 1 to
  `rejected` and 1 to `revision_needed`. Each ends *"From 'completed' the available transitions are:
  under_review."*
- **6 refusals of the next step:** *"it is still assigned to 'dev', the agent recorded as completing
  it … Assign a different reviewer, or clear the assignee to review it yourself"*. `update_task` has
  no assignee field (F353).
- **A superseded task could not be closed by any agent:** three tries on `task-5420e60359c1`, which
  the operator rejected at 22:33. `task-8ae8e1ace072`, which the Architect tried to reject as
  superseded at 23:06, is still `completed`, assigned to `dev`.
- **What it did instead:**
  - it asked the operator through `ask_user` at 16:32, naming the gap itself: its tools cannot set
    an assignee;
  - it looked for an `agentweave`/`aw` CLI route at 22:14;
  - it ended several **autonomous** turns asking the operator, in prose, to reassign or close tasks
    (`e56fa1a8` 23:50 and 00:06; `4712e387` 04:00, 04:12 and 04:23).
- Those endings are stored as ordinary chat output. Nothing surfaced them as waiting on the operator.
- At 00:01 it named a second gap in a question: it cannot relink a requirement onto another task.

**5. Questions: answers that arrived late never reached it.** 22 questions in 9 `ask_user` calls.
- Two batches were answered inside the 240 s wait (22:54, 16:32).
- At 14:38 one of four was answered in time. The result came back with top-level `"answered": false`
  and the one answer inside, and the Architect handled it correctly.
- The 23:26 and 16:50 batches, and the other three from 14:38, were answered after the wait ended.
  **No later prompt carries those question ids, and the Architect never called `get_answer` on
  them.** The operator's answers went into a store nobody read.
- The seven overnight questions (4 calls, 00:01–03:49) were never answered. Each single-question
  call ended with *"1 of 1 question(s) went unanswered within 240s. Continue as best you can and say plainly which decisions
  you made without an answer."*
- It complied well. It recorded each open decision as pending in a saved note, and told `tester` not
  to decide the evidence it hinged on. It also polled `get_answer` four times between 03:54 and
  04:39, each time *"pending": true*, each inside a turn woken for something else.

**6. It was never told its messages had stopped.** All 78 `send_message` calls returned only
`{"success":true,"message_id":…}`.
- **8 of the 20 hop-suspended entries still queued were sent by the Architect** (4 to `tester`, 3 to
  `dev`, 1 to `dev_2`), and 4 more are addressed to it.
- No result, and no later briefing, said so.

**7. The quota wall, and a review nobody could staff.**
- Its review of `task-9e89a55ccc84` was delivered three times at 21:00 (`f714a68c`, then
  `8cc97a5c`). The second and third turns contained nothing but the provider's session-limit notice
  and its reset time.
- It was never delivered again. From 21:05 to 08:40 the job recorded 64 times that the Architect
  *"is named on task-9e89a55ccc84 … as its reviewer and is not reviewing it … Ask Architect again,
  review it yourself, or send it back with revision_needed"*.
- Meanwhile the Architect had told the operator twice, in chat (`d6e79412` 21:42, `a9f394ad`
  22:05), what the review was actually waiting for: the operator's decision on a run on the work PC.
  The flow cannot tell a reviewer who never started from a review that is waiting on the operator.

**8. The spec conversation's first turn was told it had no MCP tools, and the habit outlived the
turn.**
- `run-2445bbbe1d6d` (20:39) opened with *"Tool access: no MCP tools this turn — but the AgentWeave
  capability plane is reachable over HTTP"*. The adapter reported online 5 s later.
- This is deliberate: a fresh agent gets the HTTP form until its harness has once been seen honouring
  the server, and the reasoning prices that at *"convenience for one turn"*
  (`launchability.py:285-289`).
- **Measured, it was ten turns.** Without a tool schema, the Architect learned the payload shape from
  two 422s (*"schema_version: payload must declare schema_version (this Hub speaks 1)"*, then an
  `OpenQuestion` shape error). It then read `hub/hub/spec_payload.py` in the AgentWeave checkout, a
  sibling directory the operator had pointed it at for another reason.
- For the rest of that resumed session (10 turns, 20:41–23:45) it submitted every draft with `curl`
  and a payload file, while using the MCP `ask_user` in the same session. It first used `/tmp` via a
  heredoc, then `Write` into `%TEMP%`. Those are 9 of its 21 `agent_wrote_outside_workspace`
  warnings.
- Only 7 of the 31 operator turns carried the *"SPECIFICATION TURN"* notice. Those are the turns
  that lose `Write` (`agent_trigger.py:1111`). The follow-ups between 20:55 and 23:44 did not carry
  it, so `Write` was available there. Unverified why a follow-up in the spec conversation is not a
  spec turn.

**9. What it learned lives outside the product.** The other 12 of its outside-workspace writes went
to the harness's memory directory for the project root. The four agents' 19 notes there are a
private ledger of AgentWeave's behaviour:
- the guard's refusals and their workarounds;
- the spec being too big for its tool;
- that no agent can reassign;
- that a `completed` task cannot be sent back;
- not to complete a task you will review;
- that approval merges the commit behind any accepted evidence even when a sibling requirement's
  evidence was rejected.

The last one was `tester`'s finding, relayed by the Architect at 00:01: approving
`task-f6683280dc12` merged `cbc34fa` with FR-11 rejected. O-3 checks whether that is intended.

Each write raised a workspace warning. `Write`, `Edit` and `Read` on those paths and `Read`/`Grep`
on spill files went through, while `Bash` naming the same paths was refused. This suggests the
harness does not consult the permission tool for its own directories. Unverified.

**What went unread for the Architect.**
- The `agent_outputs` rows, which I did not reconcile against the transcripts.
- Its thinking blocks.
- The text of the operator's 31 turns beyond what AgentWeave added to them, which is the operator's
  and out of bounds.
- The one subagent's sidechain.
- How the step that moved `completed → under_review` ends up recorded as `operator`. That is O-1's
  open attribution, and O-3 checks it.

### dev, tester and dev_2

**How this was read.** As for the Architect: every session matched a transcript by
`runs.session_id` (dev 59, tester 27, dev_2 8, none missing). The same `%TEMP%\o2` scripts counted
tool calls, errors and refusals, and I read the transcripts at the points those counts flagged.
The evidence reviews, footprints and run rows come from the `:8000` database, opened `mode=ro`. For
`dev`'s long sessions I read counts and flagged points, not whole transcripts.

#### dev: Sonnet 5, 99 runs, 59 sessions, $114.21

**The shape of it.** 46 runs completed and 53 failed. **51 of the failures are the quota walls:**
the job's `*/5` ticks name `dev`, so `dev` took most of the re-spawns. All 51 carry the harness's
session-limit notice inside the run, and 48 of them used 0 tokens. The other 2 are
`database is locked`. Across the sessions `dev` made 2,470 tool calls, 204 of them errors: 120
guard refusals, 23 from `submit_checkpoint_notes`, 11 from `update_task` and 9 from
`record_evidence`.

**1. Why `dev` cost the most: a handful of long turns, re-read on every call.**
- **Almost all cache reads.** 316.7 M of `dev`'s 323.2 M tokens are cache reads. Output is 1.7 M.
- **A few long runs carry most of it.** The median run lasts 5.7 minutes, but eight runs of 13–35
  minutes (125–294 API calls each) account for 188.9 M, or 58%.
- **The context grows on every call.** Every fresh session starts at 41–45 k tokens of context:
  the system prompt, the tool list and AgentWeave's briefing. The long sessions reach 290–547 k
  (`078560c0`: 294 calls, peak 547 k). Every call re-reads the whole of it, and no `dev` transcript
  shows a compaction.
- **Rework resumes the author's growing session.** 206.5 M tokens are in sessions that span more
  than one run. `task-d8d4b03d722b` alone took 86.6 M ($23.80) over 7 runs, its session carried
  through three review rounds to 428 k.
- **The spec spill adds to it.** Each read of the spec came back as 64 k characters. `dev` read it
  whole into context in 11 sessions: 10 from a spill file, 1 from a scratch copy.
- **Nothing budgets it.** The project has no token budget (O-1).

**2. `submit_checkpoint_notes` failed 23 of its 36 calls.**
- **Two failure shapes.** 9 are pydantic's *"Input should be a valid list"*, where `dev` passed a
  string for `suspicions` or `warnings`. 14 are the Hub's 422 *"suspicions: each entry must be at
  most 400 characters"* (or `warnings`).
- **The caps are not in the description.** The Hub caps each entry at 400 characters, the lists at
  8 entries and `intent` at 1,500 (`agent_actions.py:337-346`). The tool's description says *"a few
  hundred words in total is right"* and states none of the caps (`mcp_server.py:511-535`).
- **The 422 does not help either.** It names neither the entry nor the overshoot.
- **What it cost.** It happened in 11 sessions, each taking two to five calls to get one note
  through. At 02:44 (`317bc32c`), after four refusals, `dev` wrote a Python script into the task
  worktree to count characters.

**3. Evidence names the commit the turn started from, and three things followed from that.**
- **How it works.** The briefing says *"You do not need to `git commit` your own changes. The Hub
  commits your worktree's uncommitted changes automatically at the end of this turn … Call
  `record_evidence` when you are done"* (`launchability.py:423-428`). `record_evidence` footprints
  `HEAD` as it stands, and the Hub re-points the run's rows to the snapshot commit only after the
  process exits (`requirement_evidence.py:905-930`, `agent_trigger.py:2304-2315`).
- **The tool presents the provisional commit as final.** Its description says the returned
  footprint is *"the branch and commit your evidence has been attached to. Read it."*
  (`mcp_server.py:1727-1731`). The authors read it and passed it on to reviewers as the commit to
  check. At 00:00 `tester` noted that one row's footprint was in fact `cbc34fa`, not the commit its
  author had named.
- **Re-recording after a fix was refused, and the remedy contradicts the briefing.** Three times
  `dev` re-recorded evidence after revising the work in the same turn (`87affad0` 17:57 ×2,
  `6761a8a7` 19:48). Each was refused: *"… already records evidence for FR-6 on this task at this
  commit, and is awaiting … if the work has moved on, commit it first so the new evidence names the
  commit it demonstrates."* That is the opposite of the briefing. `dev` committed by hand each time.
- **A reviewer woken mid-turn reads the pre-turn commit.**
  - `dev`'s run `run-13096fbb3cc8` ran from 05:35:45 to 05:53:05. During it, `dev` messaged
    `tester` to re-check its rework.
  - That message woke `tester` at 05:51:59 (`run-7695d6f7b4b4`, which died on the database lock,
    then `run-9f7ae8cfe645`).
  - Between 05:52:18 and 05:52:40 `tester` read the new rows' footprint and the branch head. Both
    were `d4f5eda`.
  - At 05:53:05 the Hub re-pointed the three rows to `880f47c`.
  - At 05:53:11–17 `tester` rejected all three (`ev-c7b3dce37a88`, `ev-be17d387cd74`,
    `ev-b3a0392cf76a`) as unverifiable on footprint `d4f5eda`. The stored footprints now say
    `880f47c`, so the recorded reasons contradict the rows they sit on.
  - `dev` re-recorded at 06:14 and `tester` re-reviewed at 06:55: one whole round lost.
  - **No evidence decision was made while its recording run was live.** I checked this across
    every review of agent-recorded evidence. What happens is that the decision is formed before the
    re-point and lands after it.
- **A run that fails on the Hub's own error is never re-pointed.**
  - `run-d5f4b2972125` recorded `ev-85be48ba74a2`, then failed at 04:03:24 on `database is locked`.
  - The failure path marks the run failed and does neither the snapshot nor the re-point
    (`agent_trigger.py:2461-2491`, against `:2248-2315` for a normal end).
  - The work was committed at 04:05:58 as `d97aef5` by the next run in the same session
    (`run-8e0ed327cfc8`). Its re-point covers only its own rows.
  - `ev-85be48ba74a2` still names `c78d35d`. `tester`'s 04:23 rejection gives, among its reasons,
    that the evidence commit does not contain the code.

**4. One task per run, but messages ask for more.**
- **The refusal, twice.** *"This run cannot claim task task-0c07b268b9e5: it is already working
  task task-9b60162f5804. A run finishes the task it took, and takes at most one."* (`5defd7fe`
  19:19, `05a22a80` 19:25).
- **The work had already landed on the wrong branch.** A peer turn bound to one task asked `dev` to
  fix something on another task. `dev` did the work in the first task's workspace and then could not
  move the second task. `tester` rejected both evidence rows as on the wrong branch
  (`ev-91fc82a39196`, `ev-e3407121b5d8`).
- **Three more turns ended stuck the same way.** Each said the work belonged to another task's
  session and could not be reached from this workspace (`4a419275` 21:22, `9935088b` 23:48,
  `be4ae6db` 00:01).

**5. Smaller misfires.**
- **The transition model.** Three `in_progress → under_review` attempts (`dev`'s idea of handing
  work in), one `pending → completed` and one `pending → under_review`. Each cost one retry.
- **Evidence for a task with no requirement.** Once, for a task with no requirement, `dev` passed
  the task id as the identifier and got *"this project has no requirement FR-8ae8e1ace072"*.
- **A wrong argument name.** `send_message` refused `to` for `to_agent` twice.

**6. The guard refused `dev` 120 times.**

| Cause | Refusals |
|---|---|
| the spill file | 42 |
| globs | 25 |
| `/`-rooted fragments | 18 |
| `/dev/null` and `/tmp` | 16 |
| regex fragments | 15 |
| `$VAR` | 2 |
| network | 2 |

- **Why the globs are refused.** The glob word was `test/*.test.js`, and the refusal names
  `'/*.test.js'`. The plain-relative rule does not admit `*` (`mcp_server.py:966`). On Windows the
  backstop then opens an absolute-path candidate at any bare `/` inside the word (`:957-960`), so
  it reads the tail of a relative path as an absolute path.
- **`2>/dev/null`.** Refused even after a `cd`.
- **The two network refusals.** Both were `dev` calling the project's own server on `127.0.0.1`,
  the thing under test. `tester` hit one too.

**7. Two turns ended waiting for a notification that never came.** `79131de2` (20:58) and `6623a907`
(05:04) each ended by saying `dev` would wait for a background test run's completion notice. The
turn ending is the process ending, and neither session was resumed with the result. In `078560c0`
the notice did arrive, but in the *next* run (`run-d479bd1e1710`, 00:45:27), after
`run-539bd1d44ea1` had died on the database lock. The briefing does not say that background work
ends with the turn. Whether the harness kills those processes is unverified.

#### tester: Opus 5, 63 runs, 27 sessions, $76.05

**The shape of it.** 47 runs completed and 16 failed: 15 on the quota walls and 1 on the database
lock. 1,196 tool calls, 85 of them errors, 54 of those guard refusals (12 the spill file, 11 regex
fragments, 10 `/`-rooted, 7 globs, 5 `$VAR`, 4 `/dev/null`, 4 other harness directories, 1
network).

**1. The 68 evidence reviews were not rubber stamps.**
- **The numbers.** 34 accepted and 34 rejected. The median reason is about 1,160 characters and the
  shortest is 160.
- **What a review contains.** They name the commit checked, whether it descends from `main`, the
  suite count, and the probes or mutants tried.
- **Real defects caught.** Several found defects the authors' tests missed:
  - a claim about DNS-rebinding that did not hold (18:56);
  - a failure classifier that treated any bare `429` or `503` in the output as the provider being
    unavailable (04:23);
  - tests that passed without the feature (04:23).
- **Its own evidence.** It never judged its own. The Architect decided its 5 rows (4 accepted, 1
  rejected). So the rule that excludes an agent's own evidence was never exercised by `tester`.
- **Timing.** The median time from evidence being recorded to `tester`'s decision was 15 minutes
  (range 1.7 to 174).

**10 of its 34 rejections were not judgements of the work:**
- **5 retired a superseded or duplicate row.** Their reasons say the content is fine, and that
  the rejection only stops the row being counted twice. An agent has no way to withdraw its own
  `awaiting` row. The duplicate refusal offers only *"say so on that piece"*.
- **2 named the wrong branch** (item 4 under `dev`).
- **3 were the footprint race** (item 3 under `dev`).

**2. A reviewer who helps the work along becomes its author.**
- At 20:45 (`55b5d597`) `tester` went to approve `task-bb06b8c3c708` and found it still
  `in_progress`, because `dev`'s turn had ended without completing it.
- `tester` moved it to `completed` itself. Approval was then refused: *"agent 'tester' recorded the
  task's move to 'completed', and approving, rejecting or requesting revision of work requires a
  different actor … Starting a new run does not make you a different actor."*
- It sent the approval to the Architect and saved a note never to complete a task it reviews.

**3. The author-assignee refusal, twice, and each time it was preceded by a `completed →` refusal.**
- **When.** At 23:07 on `task-49b0567ce119` and at 03:59 on `task-0ff93faef4ba`.
- **The refusal.** *"it is still assigned to 'dev', the agent recorded as completing it … Assign a
  different reviewer, or clear the assignee to review it yourself. Left as is, the task is claimable
  by nobody and 'dev' counts as busy for every other review in this project."*
- **Its response.**
  - it put the verdict in messages to the Architect and `dev`;
  - it sent the Architect a correction when its first message had said the task was moved;
  - it updated its saved note on reassignment.
- **The effect.** Its judgement landed through evidence decisions, which it can make. The task
  status stayed `completed`.

**4. It could not see the answer its decision waited on.**
- At 03:51 it called `get_answer` on `q-dc3b14272b96`, the Architect's question whose answer
  decided the evidence it held.
- It got *"Question not found"*. The route answers 404 for any question another agent asked
  (`agent_actions.py:722-727`), which is deliberate scoping.
- The effect is that a reviewer told to wait on an answer cannot tell when that answer arrives.

**5. The spec, again.**
- Two `read_spec_document` calls with the document id were refused with *"path must begin with
  'spec/'"* (19:08, 19:19).
- 12 guard refusals named the spill file.
- It ended up copying the spec into a `.tmp` directory inside its own worktree to search it.

#### dev_2: Sonnet 5, 19 runs, 8 sessions, $10.13

**The shape of it.** All 19 runs completed. **It has not run since 09-13 23:50 UTC**, over nine
hours when this was read.
- **The four tasks it holds are ones nothing will start.** All four are pending, created by the
  Architect, with no `loop_id`: `task-62b60f9dba50`, `task-88eff732b7f5`, `task-7673e4f80905` and
  `task-a7c2a75726a2`.
- **Two messages to it are still suspended:** `entry-c60e30d4d2b5` (Architect, 19:20) and
  `entry-d1fe571a90e4` (`tester`, 19:30), both at hop 7.
- **How this compares with F352.** F352 measured "five pending, three duplicates" at 22:30. One of
  the five, `task-3fe4f652e5c2`, was since worked and completed. Going by titles, two of the four
  remaining (`task-62b60f9dba50` and `task-a7c2a75726a2`) describe the same change to how the runner
  is spawned.
- **Duplicates across agents.** `task-3fe4f652e5c2` itself duplicated `dev`'s `task-8ae8e1ace072`.
  `dev_2` found `dev`'s claimed fix had never merged and did it again. `task-8ae8e1ace072` is still
  `completed` and assigned to `dev`.

**1. Two agents fixed the same thing in parallel.**
- `tester`'s 18:56 rejection of the FR-60 claim reached `dev_2` as the reviewer of
  `task-b8e8b7f3beca` (`entry-d50ca4b24a74`). Meanwhile the Architect opened `task-9b60162f5804`
  for `dev`.
- Both wrote the fix. `dev`'s merged. `dev_2`'s went onto the already-approved `task-b8e8b7f3beca`,
  where the Hub refused the status move (*"an agent run has no transitions available from
  'approved'"*) but accepted the new evidence.
- `tester` rejected both of `dev_2`'s rows as superseded or duplicate (`ev-90bc84ab8ddb`,
  `ev-13c55e550139`).
- `dev_2`'s 19:13 turn concluded, on its own, that it should check `list_tasks` before fixing
  anything.

**2. A message about another agent's task wakes you in that task's workspace.**
- The Architect's `entry-b71caee8b603` carried `task-9b60162f5804` and woke `dev_2` in
  `.agentweave/tasks/task-9b60162f5804`, which is `dev`'s task. Its next two turns, delivering
  `tester` messages at 19:21 and 19:23, ran there too.
- `dev_2` declined to touch it.
- The eleven runs in that workspace between 18:58 and 19:23 (dev, Architect, tester, dev_2) did not
  overlap.

**3. Reviewing without the capability to decide.**
- **Staffed without it.** At 17:23, in a turn the operator started after the job had staffed
  `dev_2` to review `task-b8e8b7f3beca`, `dev_2` tried to accept three evidence rows. All three got
  *"accepting evidence is the operator's, or an agent the operator has granted it."*
- **Approval refused, as it was for the Architect.** At 19:50 and 19:55 the evidence gate refused
  its approval of `task-715470b41119`.
- **It misread the refusal.** Straight after the 19:50 refusal it messaged `dev` that the task was
  approved. It ended the turn believing the write would succeed once the running turn ended. The
  refusal was the evidence gate, not the live-turn check.

**4. Guard refusals.** 29 (7 regex fragments, 7 `/`-rooted, 5 the spill file, 3 `$VAR`, 3
`/dev/null`, 3 globs, 1 harness directory).

**All three first turns were told there were no MCP tools.** `dev_2` at 16:35, `dev` at 16:45 and
`tester` at 18:50 each opened with *"Tool access: no MCP tools this turn"*, as the Architect's did
(item 8 above).

**What went unread for these three.**
- **Transcripts.** Their `agent_outputs` rows, their thinking blocks and any sidechains. `dev`'s
  three longest sessions (`078560c0`, `c90697b9`, `9894e1e1`) end to end.
- **Whether `tester`'s probes were right.** I did not check them against LoopEngine's code.
- **Background processes.** Whether a background process outlives the turn that started it.
- **The duplicate count.** Whether the four pending `dev_2` tasks duplicate each other beyond their
  titles.

## The sort (O-3)

Written at 10:15–10:30 by the day window's fifth firing. Every observation above lands in exactly
one list below, apart from the four under *Not sorted*, whose mechanism was not confirmed.
- **Fixes:** each mechanism was confirmed in this checkout, at `f28bc31`'s tree, with the `file:line`
  given in its `scripts/drive/FINDINGS.md` entry.
- **Improvements:** each gets a brief, `openspec/explorations/2026-09-14-<slug>.md`, in I-1.

**The two open checks, resolved.**
- **(i) The ~26 transitions recorded as the operator's on cron ticks** are the flow's staging, and
  they are F47. `scheduler.py:828` and `:830` pass `operator()` for `completed → under_review` and
  `pending → assigned`, because `ACTOR_KINDS` has only `run` and `operator`
  (`task_transitions.py:34-36`). F47 is open (C), and has a dated note.
- **(ii) Approving `task-f6683280dc12` merged `cbc34fa` while FR-11's evidence was rejected, and
  that is intended.** The document is `sketch` rigor, read from `:8000`. At `sketch`,
  `_enforced_requirements` filters out every requirement (`requirement_gate.py:339-360`), so a
  rejection is a signal on the task, not a gate. `_check_unaccepted` blocks only when evidence is
  `awaiting` and nothing accepted names a commit, and it allows the mixed case by design
  (`:493-506`). Under `gate` rigor the rejected requirement would refuse the approval. The rigor is
  the operator's setting, so this item is under *Not AgentWeave's*.

## Fixes

Severity first. Within a severity, ordered by what the fault cost on this project.

1. **F352 + F353 (A)**: a flow counts an agent busy for any live task in the project, and its
   unstaffed sentence names nobody and no way out. 180 stalls here. One change, because both
   repairs rewrite the same sentence.
2. **F355 (B)**: a provider session-limit failure is re-delivered twice into the exhausted
   allowance, then its input is given up. There were 25 withdrawn entries, a review among them.
3. **F356 (B)**: an answer given after `ask_user`'s wait, while the run still lives, reaches nobody.
   Three answered batches were lost.
4. **F357 (B)**: a review turn is told to approve, with no word about the evidence gate. Seven
   approvals were refused, and peers were told "approved" anyway.
5. **F358 (B)**: evidence can be decided while its recording run is live, and the duplicate
   refusal's remedy contradicts the briefing. 3 rejections came from the race and 5 from
   retirements.
6. **F359 (B)**: a run the Hub's own write kills is not snapshotted and its evidence is not
   re-pointed. `ev-85be48ba74a2` still names a commit that holds none of the work.
7. **F360 (B)**: the checkpoint probe's "assigned to this agent" rule fails loop checkpoints on a
   coin toss. 7 of 14 were marked failed.
8. **F361 (B)**: a hop-suspended peer message has no reason on its entry, and the sender is told it
   was sent. 20 entries sat 2–13 h.
9. **F347 (B)**: a repository with no commit refuses every turn with git's plumbing error. It was
   seen on this project on 09-13 and already has its verdict (option a).
10. **F362 (B)**: on Windows, the guard reads the tail of a relative word containing a `/` as an
    absolute path. That covers the globs, `/`-rooted fragments, regex and `2>/dev/null`: at least
    128 of the 262 refusals. *Not built today: `mcp_server.py`.*
11. **F363 (B)**: `read_spec_document` never fits a tool result, and it refuses the document id.
    All 57 results spilled, and 85 refusals named the spill file. *Not built today:
    `mcp_server.py`.*
12. **F364 (C)**: `submit_checkpoint_notes` enforces caps it never states, with a refusal that
    names nothing. 23 of 36 calls failed.
13. **F47 (C)**: the flow's staging is recorded as the operator's. That is the ~26 on cron ticks.

**Re-observed and not in the list.**
- F349 gets a note: the same lock kills runs, which is F359.
- F354 was not observed breaking anything here.
- F351 is fixed, `022903f`.

## Improvements

Most useful first. Each is briefed in I-1, and none is specced or built.

1. **`rework-in-a-fresh-session`.** `dev`'s $114 is long turns re-read from cache:
   - 98% of it is cache reads;
   - 8 runs account for 58%;
   - context grows from 41–45 k to 290–547 k, with no compaction;
   - rework resumes the author's growing session (206 M tokens across multi-run sessions);
   - no token budget is set by default.
2. **`agents-can-retire-their-own-work`.** No agent can withdraw its own `awaiting` evidence row or
   close a superseded task. 5 of `tester`'s rejections were retirements, and `task-8ae8e1ace072` is
   still `completed`.
3. **`a-review-can-wait-on-the-operator`.** A reviewer waiting on an operator decision looks like
   one that never started: 64 events for `task-9e89a55ccc84`. The Architect ended autonomous turns
   asking in prose. The improvement is a *declared* wait, not detection of prose, which stays
   retired (CLAUDE.md, 2026-08-20).
4. **`requests-that-name-another-task`.** One run takes one task, but messages ask for work on
   another:
   - two *"cannot claim task"* refusals;
   - evidence left on the wrong branch;
   - a message carrying another agent's task id wakes its recipient in that task's workspace;
   - `dev` and `dev_2` fixed FR-60 in parallel.
5. **`the-first-turn-has-its-tools`.** Every agent's first turn was told *"no MCP tools this turn"*.
   For the Architect that became a whole ten-turn session of `curl` and payload files
   (`launchability.py:285-289` prices it at one turn). Related to F340.
6. **`the-transition-model-agents-are-told`.** Agents repeatedly tried edges that do not exist:
   - `in_progress → under_review`, `completed → approved`, and `pending → completed`;
   - a reviewer who moved a task to `completed` then could not approve it (`task-bb06b8c3c708`).
7. **`a-peer-can-see-the-answer`.** `get_answer` answers 404 for a question another agent asked
   (`agent_actions.py:722-727`). `tester` could not see the answer its decision waited on.
8. **`project-notes-inside-the-product`.** The agents kept a 19-note ledger of AgentWeave's
   behaviour in the harness's memory directory, and every write raised an outside-workspace warning.
9. **`peer-threads-that-only-acknowledge`.** 7 of the Architect's turns only acknowledged a peer.
   Such threads spend the hop budget, which was reached 21 times.
10. **`background-work-ends-with-the-turn`.** Two turns ended waiting for a background task's notice
    that never came. The briefing does not say that background work ends with the turn.
11. **`localhost-for-the-thing-under-test`.** The default posture refused the agents' calls to the
    project's own server on `127.0.0.1`: 3 refusals.

## Not AgentWeave's

- **LoopEngine's code.** The defects `tester` caught belong to the project and are not
  AgentWeave's: the DNS-rebinding claim, the 429/503 classifier, and tests that passed without the
  feature.
- **The rigor setting.** The spec document is `sketch` rigor, the operator's setting, so approval
  merging over a rejected sibling requirement is intended (check (ii) above).
- **The loop has no stop time, and the job is still enabled.** It was configured on the operator's
  instruction.
- **Eight questions went unanswered overnight.** The operator was away. The agents recorded the
  open decisions and carried on correctly.
- **The provider's session limits themselves.** The plan's allowance is not AgentWeave's. What the
  Hub does next is F355.
- **The first landing was refused for *"this project has no main branch set"*.** The setting was
  unset, and the refusal named the repair.
- **Agent slips answered by a clear refusal:** `to` for `to_agent`, and a task id passed as a
  requirement identifier.
- **`tester`'s reviews were real, not rubber stamps.** 34 accepted and 34 rejected, with a median
  reason of about 1,160 characters. Nothing to change.

## Not sorted, and why

Each of these has an observation, but no mechanism confirmed in code this firing, so none is filed:
- **4 task-worktree releases failed after merge on Windows** with *"failed to delete … Permission
  denied"*. Which process held the files was not checked.
- **Only 7 of the Architect's 31 operator turns carried the *"SPECIFICATION TURN"* notice.** Why a
  follow-up in the spec conversation is not a spec turn was not traced.
- **Whether the harness bypasses the permission tool for its own directories.** `Read`, `Write` and
  `Grep` on those paths went through, while `Bash` naming them was refused.
- **72 surfaced divergences sit unresolved.** Whether any of them mattered was not read.

## What went unread

O-3 started at 10:15, before 11:00, with both O-2 halves complete. Unread across O-2:
- the `agent_outputs` rows of all four agents, which were not reconciled against the transcripts;
- the thinking blocks, and the one subagent sidechain;
- `dev`'s three longest sessions end to end;
- whether `tester`'s probes were right against LoopEngine's code;
- whether background processes outlive their turn;
- whether `dev_2`'s pending tasks are duplicates beyond their titles.

The operator's own turn text was out of bounds and was not read.
