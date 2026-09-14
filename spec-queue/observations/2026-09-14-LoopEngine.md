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
