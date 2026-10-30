## F299 (A) — a `claude` run whose harness has no MCP cannot write a file, and blames the operator's machine for it

**Status:** open — **DEFERRED by the operator 2026-09-21: triaged, won't build now** (`spec-queue/DECISIONS.md`, `### 2026-09-21 evening`). Neither creatable runner reaches this path (`RUNNER_CLIS = ("claude", "codex")`, both MCP-injectable) and `hub_client` has no UI control; reopen when a runner that cannot take MCP (GHCP) is implemented. **Corrected 2026-09-27 (`ghcp-d6-correct-f299`):** GHCP *can* take MCP (`--additional-mcp-config`, verified on 1.0.88); the real trigger is a run on a machine whose policy blocks MCP servers. It is answered for Copilot by slice 3, `a-run-reaches-the-hub-without-mcp`, of `openspec/explorations/2026-09-27-copilot-as-a-full-runner.md`. Original status follows.
**Ready:** parked

**Original status:** open. Driven 2026-09-09 by the night window, task §4.9 of
`openspec/changes/2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing`. The prediction being
tested was the repository's own, written at `hub/hub/runner_commands.py:245-248` and never driven:
*"naming an approver that will not be there makes every tool call fail, which the model reports as
a broken approval system."* It is **substantially right, and sharper than it says.**

> **2026-09-13, DECIDE session.** The operator answered the spec loop's question with **(b)**. 1b is
> handed back, and `an-absent-approver-is-not-named` is REJECTED and archived unbuilt as
> `openspec/changes/archive/2026-09-13-an-absent-approver-is-not-named/`. F299 stays **open** and
> will be re-decided as one question with F301, F339 and F340 (`spec-queue/DECISIONS.md`, `### 2026-09-13
> afternoon`, the OPEN block).

> **Re-measured 2026-09-13** (day window, `d2-r1`, `claude` **2.1.269**,
> `scripts/drive/t_d2_0913_f299_harness.py`, which uses `build_command`'s own argv and spawns through
> `PtySession` as the Hub does, once with the inherited `CLAUDE*` environment and once without).
> **Condition A no longer starts.** Both F299's reproduction flags and the Hub's full configuration
> with a policy-blocked server **exit 1 before any model call**. The harness prints its own reason:
> `Warning: MCP server blocked by enterprise policy: agentweave` and then `Error: MCP tool
> mcp__agentweave__approve_tool_call (passed via --permission-prompt-tool) not found`. Condition C
> still behaves as recorded below: it completes, `Write` is denied, and the model says *"I need
> permission to write the file"*. The environment made no difference. This finding does not record
> the build it was driven on, so the change is most likely the harness (2.1.238 → 2.1.269), and
> that is unmeasured. Specced as `openspec/changes/an-absent-approver-is-not-named`, whose
> `proposal.md` puts this to the operator before `DECISIONS.md` 1b is built. **Status unchanged:
> open.**
>
> **Corrected the same day** (`d3-r2`, round 2 of that change, `claude` 2.1.269 read at 10:25 and
> 10:38). **"Exit 1 before any model call" is wrong.** Each of `d2-r1`'s own A transcripts, and
> R2's rerun, holds a model call and a `Write` tool_use, and no result line. R1 had read the missing
> result line as a missing model call. What 2.1.269 does with condition A:
> - a turn needing no approval **completes** (measured: exit 0, `ok`);
> - the first approval-needing call gets the `not found` error as its result, and the process dies
>   there, exit 1, with no result line. The Hub therefore records the turn's usage as
>   *unavailable*.
>
> The two harness lines and exit 1 stand as recorded. F299's 2026-09-09 run differed in carrying on
> after each refusal, not in failing to start. Evidence:
> `openspec/changes/an-absent-approver-is-not-named/evidence/r2-harness-results.json`. **Status
> unchanged: open.**
>
> **Round 3 the same day** (`d4-r3`, `claude` 2.1.269). Nothing above changes. One fact bears on
> this finding directly: under the policy, the harness's `init` line **leaves the blocked server
> out** of `mcp_servers`, which is different from how it reports a server that timed out or crashed
> (`failed`). The change now uses that difference to decide which earlier run counts as evidence
> against the harness. Evidence: `…/evidence/r3-harness-results.json`. **Status unchanged: open.**

**The configuration this is about is the ordinary one.** Runner `claude`, `hub_client` unset, a
harness whose company policy blocks MCP servers. The Hub emits `--mcp-config` (which that harness
ignores) and, because a server was configured, `--permission-prompt-tool
mcp__agentweave__approve_tool_call`. Nothing will ever answer that tool.

**What actually happens** — three real `claude -p` runs on Haiku in `testbed/scratch/c2drive`, one
per condition, with `--output-format json` so `permission_denials` is read rather than inferred:

| | flags | Read | Write / mutating Bash |
|---|---|---|---|
| **A** | `--permission-mode manual --permission-prompt-tool mcp__agentweave__approve_tool_call`, **no** `--mcp-config` | **succeeded** | **denied** (`Write`, `PowerShell`, `Bash` all three) |
| **B** | `--permission-mode acceptEdits` (what the `cli` access path produces) | — | **succeeded** |
| **C** | `--permission-mode manual`, **no** approver flag | — | **denied** (`Write`) |

So it is not *every* tool call: a `Read`, and a `Bash` that only echoes, go through. Every call that
needs an approval fails. For an agent asked to do work, that is the same thing.

**The part that is worse than the comment predicted is what the model says about it.** In condition
A it reported:

> I've encountered a workspace establishment issue that's preventing file creation. […] This
> appears to be a system-level permission or workspace configuration issue. You may need to check
> your workspace permissions or contact your system administrator to resolve this.

In condition C — denied for the same reason, but without an approver flag naming an absent tool —
it reported the truth:

> I need permission to write the file. Please approve the write operation.

Same denial, two different explanations, and the one the Hub's own configuration produces is the
misleading one. The operator is told their machine is broken. The agent burned the rest of its turn
retrying the same write through `Write`, then `PowerShell`, then `Bash`, because the error it was
given did not read as "ask someone".

**What this settles for the change.** The mirror deployment is **not a wording defect**. §1–§3
correct what such a run is *told*; this is a run that cannot act. Fixing the wording alone leaves it
broken in exactly the same way — which is what §4.9 was written to find out before a mechanism was
chosen, and it is why the mechanism chosen (§4.1) deliberately does **not** move the injected server
on an inference.

**Why it was not fixed in the same change.** Every available remedy moves containment:

- resolve to `cli` when there are no grounds → `acceptEdits`, which has **no path check at all**
  (`runner_commands.py:66-67`), for every unstated `claude` run on the machine;
- keep `manual` and drop the approver flag → condition C, which denies every mutating call anyway,
  and in a headless run there is nobody to approve;
- leave it as it is → condition A.

There is no non-widening, non-breaking option. `agent-capability-plane`'s *"A truer description does
not silently widen permission"* says the containment a run gets is the operator's to decide, so this
is not the implementing window's call to guess. It is in `STATE-night.json`'s `decisions_for_user`.

**The workaround exists today and is one line.** `hub_client: "cli"` — already documented in
`src/agentweave/config.py:714` as *"uncomment if MCP is blocked by company policy"* — moves the run
to the `cli` path, which removes the approver flag along with the injection, and the run works
(condition B). What the operator is choosing when they do that is `acceptEdits`, and nothing in the
UI says so.

**Corrected 2026-09-09 by F301.** That last sentence is right about editing and wrong about the
plane. Driven through the Hub on exactly this configuration, a run on the `cli` path made **zero**
requests to the capability plane: the harness statically refuses a shell command that interpolates
`$AW_RUN_TOKEN`, and `acceptEdits` with no approver auto-denies the rest. The workaround restores
writes, not access.

**Reproduce**

```bash
cd testbed/scratch/c2drive
claude -p --model haiku --permission-mode manual \
  --permission-prompt-tool mcp__agentweave__approve_tool_call --output-format json \
  "Create a file called written_A.txt containing the single word ok. Use your Write tool." \
  | py -3.11 -c "import json,sys; d=json.load(sys.stdin); print([x['tool_name'] for x in d['permission_denials']]); print(d['result'])"
```

---

**Foot 2026-10-01 (`a-run-reaches-the-hub-without-mcp`).** Answered for Copilot by construction (its approver is the ACP
handler, not an MCP tool) and given a plane by the shim (drives 9.3/9.4). Open for Claude: under condition A file
writes still die with no approver, and the containment choice stays the operator's (`DECISIONS.md` 2026-09-13).

## F301 (A) — on the `cli` access path a `claude` run has no tool that can make the request it is told to make

**Status:** open — **DEFERRED by the operator 2026-09-21: triaged, won't build now** (`spec-queue/DECISIONS.md`, `### 2026-09-21 evening`). Neither creatable runner reaches this path (`RUNNER_CLIS = ("claude", "codex")`, both MCP-injectable) and `hub_client` has no UI control; reopen when a runner that cannot take MCP (GHCP) is implemented. **Corrected 2026-09-27 (`ghcp-d6-correct-f299`):** GHCP *can* take MCP (`--additional-mcp-config`, verified on 1.0.88); the real trigger is a run on a machine whose policy blocks MCP servers. It is answered for Copilot by slice 3, `a-run-reaches-the-hub-without-mcp`, of `openspec/explorations/2026-09-27-copilot-as-a-full-runner.md`. Original status follows.
**Ready:** parked

**Original status:** open. Same session and fixture as F300; agent `httpagent`, `config.hub_client = "cli"`,
so no MCP server is injected and the posture falls to
`DEFAULT_CLAUDE_PERMISSION_MODE_WITHOUT_APPROVER = "acceptEdits"`. Raw run in
`testbed/scratch/c2verify/driveA.json` (uncommitted); `run-dceb35938752`, 2 minutes 14 seconds,
exit 0, **zero requests reached the Hub** — its access log has no `/api/v1/agent-actions` line for
that run.

**The notice was read correctly.** The run's first thought quotes the route and the body schema §2
renders for the HTTP path — *"`POST /api/v1/agent-actions/tasks` (`create_task`) — body `title`*,
`description`, …"* — and it went straight for a shell command. Nothing about the description failed.

**Fifteen attempts, five distinct refusals, and only the last is ours:**

| Attempts | Tool | Refusal |
|---|---|---|
| 1, 3 | PowerShell | `Command contains expandable strings with embedded expressions` |
| 2, 7 | PowerShell | `Command contains subexpressions $()` |
| 4, 9 | PowerShell | `Command invokes .NET methods` |
| 5, 6, 8 | Bash | `Contains simple_expansion` |
| 10, 11 | Bash (heredoc to python) | `Contains brace with quote character (expansion obfuscation)` |
| 12, 13, 15 | PowerShell (`curl.exe`) | `contains multiple operations … requires approval` |
| 14, 15 | Bash / PowerShell | `Permission to use Bash has been denied` |

The first five rows are the harness's own command analyser, not AgentWeave: reading an environment
variable inside a shell command (`$AW_RUN_TOKEN`, `$env:AW_RUN_TOKEN`) is a shape it refuses
outright. The last rows are `acceptEdits` with no approver — a command that needs approval is
auto-denied, because nothing headless can answer.

**So the notice instructs a form of command the harness statically refuses**, and the posture the
`cli` path forces has nobody who can override it. The run ended by telling the operator it had
"formulated the correct HTTP request" and needed permission — the honest report, and still a turn
that did nothing. It also spent four of its fifteen attempts spawning a subagent to try the same
request, which failed the same way.

**This corrects part of F299.** F299 records `hub_client: "cli"` as the one-line workaround, on the
strength of condition B — a raw `claude -p --permission-mode acceptEdits` that wrote a file. That
much stands: the workaround restores the ability to *edit*. It does **not** restore access to the
capability plane, which is the thing a run is switched to that path in order to reach. Driven
through the Hub on that exact configuration, the plane was unreachable.

**Read with F300 this is the whole of it:** on `workspace`, our own approver denies the URL (F300);
on `cli`/`acceptEdits`, the harness refuses the interpolation and then the tool (F301). There is no
posture on this machine on which a `claude` run reaches the HTTP form of the plane under its own
power. The MCP adapter reaches it from the same environment, which is why the plane is correctly
described as reachable — but *reachable* and *reachable by the agent's own tools* are two claims and
only the first is proven.

**Not fixed here.** Every remedy either moves containment or changes what the notice tells an agent
to do — for instance instructing a `python -c` request that reads `os.environ` rather than a shell
interpolation, which the analyser may not refuse (untested). Both belong with the F299 decision
already in `STATE-night.json`'s `decisions_for_user`; they enlarge it rather than replace it.

**Reproduce**

```bash
# trial Hub on 8010 from source, per CLAUDE.md; fixture project with a claude/haiku runner
AW_KEY=$(cat ~/.agentweave/hub/profiles/trial/bootstrap-key.txt) AW_PROJECT=<pid> \
  py -3.11 testbed/scratch/c2verify/drive.py httpagent driveA \
  "Create an AgentWeave task titled 'C2V-HTTP-A' ... reply with the HTTP status code and the task id."
```

---

**Addendum 2026-10-01 (`each-runner-cli-is-one-adapter` task 6.2 (a), R2 open question 3; still parked).**
Two facts, one read from code and one driven:

- *From code:* `GET /agents/launchability` reports `collaboration_ready: True` for a `claude` agent with
  `hub_client: "cli"`, because `ClaudeAdapter.collaboration(flags, yolo=…)` takes no `hub_client`. That
  is the very configuration this finding measured unable to reach the Hub. Driven on the trial Hub
  2026-10-01: `radrive-clihub` reads `runnable: True, collaboration_ready: True, collaboration_reason:
  null`, unchanged from the pre-adapter baseline (`hub/tests/fixtures/runner_adapters/drive_before.json`),
  so the adapter move neither caused nor fixed it.
- *Driven, and it muddies any re-measurement on this machine:* a `hub_client: "cli"` Haiku run of
  `adapterdrive` (`run-2314f869771d`) was given no tool server (axes `none/none/cli`, told the HTTP form)
  and **still set `Run.mcp_adapter_online_at`**. The server came from the operator's own Claude
  configuration: `~/.claude.json` registers `agentweave` → `agentweave-mcp` at local scope for
  `C:/Users/huida/Documents/projects/AgentWeave`, and an agent worktree under
  `.agentweave/worktrees/<name>/` is inside that directory, so Claude loads it. The installed
  `agentweave-mcp` reads the run's `AW_RUN_TOKEN` from the environment it inherits and reports in as
  the run. So on this machine, for `proj-d85a82bf4216`, a "cli" Claude run is not tool-less, and
  `harness_has_honoured_mcp` can be set by a server the Hub never injected. A re-measurement of this
  finding must use a project outside this repository, or remove that registration first.

**Fixed 2026-10-01 for Claude and Copilot (`a-run-reaches-the-hub-without-mcp`, drives 9.3 and 9.8).** A Claude run with
`hub_client: "cli"` -- no MCP server, no approver, in a project outside this repository -- wrote
`.agentweave/calls/create_task.json` with `Write` and ran `aw-tool create_task .agentweave/calls/create_task.json`;
the pre-allowed `Bash(aw-tool:*)` let it through and the task was created by the run (`run-5ffb0bac65e3`). A first
turn with a one-line prompt asked for the missing task fields instead of acting (`run-f0a07b42b88f`), a model choice,
not a refusal. Copilot with MCP blocked reached the plane the same way (9.3, 9.4).

## F380 (A) — two independent ways the day window silently fails to arm, and neither leaves anything to read

**Status:** part (a) fixed in the commit that follows 2026-09-21 night iteration 3 (tracked-only dirty check in `arm-cycle.ps1` and `install-driver.ps1`; refusal now also appends to the gitignored driver log); part (b) was decided 2026-09-18 and is not touched here. Filed 2026-09-18 00:15 by an interactive session, from the live scheduled tasks
and `arm-cycle.ps1` / `install-driver.ps1` on this machine.

**Source:** drive — found by exercising the product and reading what it actually recorded.
**Theme:** Flows & loops

**Three consecutive days produced no FILL window, for three different reasons, and all three look
identical from outside: `STATE-day.json` reads `iteration: 0` and nothing else says anything.**
Task Scheduler records a bare `LastTaskResult` with no message; the day log is not written because
the window that would write it never started.

| date | `AgentWeaveArmDay` result | cause |
|---|---|---|
| 2026-09-16 | 1 | `install-driver.ps1` rolled the start to tomorrow and threw *"no window"*. Fixed by `22822bc`'s 15-minute grace — but see (b), the fix is narrower than the hole. |
| 2026-09-17 | **3** | **(a)** the tree was dirty, so the arm refused. |
| 2026-09-18 | — | would have been **(b)** again, had the `DAY WINDOW` line not been added by hand at 00:15. |

### (a) Any untracked file anywhere in the repo disarms the next window

`arm-cycle.ps1:167` refuses on `git status --short`, which counts **untracked** files, not only
tracked modifications:

```
$dirty = @(& git -C $Repo status --short)
if ($dirty.Count -gt 0) { Say "REFUSING: working tree is dirty. ..."; exit 3 }
```

Its own comment reads *"A dirty tree is the operator's, or a window that died mid-iteration"* — both
of those are **tracked** modifications. An untracked scratch file is neither, and is exactly what a
healthy window produces.

**Measured.** On 2026-09-17 the night window's compose iteration parked a pytest log in
`.claude/autonomous/tmp/`. Nothing in either playbook or any script names that directory — a window
picked the name; `.claude/autonomous/scratch/` is the ignored one that exists for this. One
untracked directory, and the whole next day is gone. Worked around in `.gitignore` for that one
name (`d52f699`), which does not address the class: **any** file a window leaves, or the operator
drops in the tree overnight, has the same effect.

Whether the refusal should read `git status --short -uno`, or list untracked files without
refusing, is the decision. An arm that refuses because a `.log` exists is protecting nothing — it
does `git checkout`, and untracked files survive that.

### (b) The arm fires 75 minutes after the window it arms is due to start

`AgentWeaveArmDay`'s trigger is **10:15**. `arm-cycle.ps1`'s standard day window is **09:00-17:00**.
`AgentWeaveArmNight` fires **22:55** for a **23:00** window — five minutes ahead, which is the
shape that works.

`install-driver.ps1:200-209` gives a start already past a **15-minute** grace; at 10:15 a 09:00
start is 75 minutes past, so the `elseif` rolls it to **tomorrow 09:00**, which is after **today's**
17:00 stop, and it throws *"the run would have no window"*.

The day window therefore only arms when `DIRECTION.md`'s **newest section is dated today and
carries a `DAY WINDOW:` line** that happens to match the trigger. That is how 2026-09-17 was meant
to work, and it is a daily manual step nobody is reminded of: a section written for tomorrow that
omits the line disarms tomorrow, silently, and the omission looks like nothing at all.

**DECIDED by the operator 2026-09-18 00:30: return the day to 09:00.** `install-tasks.ps1` had
declared `AgentWeaveArmDay` at **08:55** for an 09:00-17:00 window all along — the live trigger at
10:15 was undocumented drift from a one-off. Re-running `install-tasks.ps1` restored it; the task
now fires 08:55, five minutes ahead of its window, exactly as `AgentWeaveArmNight` sits five minutes
ahead of 23:00. The `DAY WINDOW` line was removed from `DIRECTION.md ## 2026-09-18` in the same
sitting, and is now what it was meant to be: a way to move a day deliberately, not a prop that
arming depends on. **(b) is closed. (a) and the silence below are still open.**

### What is common to all three, and is the actual severity-A part

**None of the three failures wrote anything a person or a later window would find.** No log entry,
no `DECISIONS.md` row, no non-zero exit anybody reads. `STATE-day.json` keeps the previous cycle's
`iteration` and branch, so it reads as a window that has not started yet rather than one that
cannot. The only reason any of them were caught is that a person went looking days later.

A refusal to arm is a legitimate outcome; a **silent** refusal to arm is not. The arm knows exactly
why it stopped in every one of these paths — it prints the reason to a console nobody is attached
to.

**Related:** F361 (the same shape one level down — a suspension with the reason known and recorded
nowhere the sender can read), F376.

---

## F782 (A) -- a Copilot turn that reaches the fixed 600 s deadline is re-delivered unchanged twice: work that needs more than ten minutes runs three times (30 min, three premium requests) and is then dropped

**Status:** expectation 1 fixed 2026-10-20 (night iteration 10, change `the-turn-clock-counts-work-not-waiting`, spdoc-8cdbaa6d6f9f, folded into `inbound-queue-delivery`): a deadline cut fails with `error_kind turn_timeout`, `retryable False`, and its entry is withdrawn after that attempt with a reason naming the 600 s limit and the background-or-split advice. Driven on scratch :8110 (`c1019_copilot_s3.py`, real Copilot): the turn that reached the deadline was withdrawn at once and `queue_entry_abandoned` carries the reason, with no re-delivery. (It was the entry's third attempt only because two earlier attempts failed at startup under load, F789; the reason text is the turn-limit one, not "delivery failed 3 times".) Expectation 2 (a per-agent turn-limit setting) is still open: it needs a column, so Tier 2. Found 2026-10-19 in the Copilot stall drive (`scripts/drive/c1019_copilot_s3.py`, scratch Hub :8110, Copilot CLI 1.0.91 as the Hub launches it, `claude-haiku-4.5`, real turns).
**Source:** drive
**Theme:** Runs
**Ready:** yes -- repro below; measured 3 of 3 attempts.
**Tier:** 1 (a behaviour change plus, if taken, a setting)

Agent `slow` was asked to run `py -3.11 -c "import time; time.sleep(700); print('slept-done')"` and wait for it. Haiku ran it in Copilot's shell (`mode="sync"`, long `initial_wait`). At 600 s the Hub cancelled the prompt: `run-c2e1184edfe9` `failed`, "Copilot did not finish the turn within 600 s", tool card "shell interrupted". `return_run_entries` put the input back (`queue_entry_queued`) and the Hub re-delivered it 0.4 s later in the same provider session (`run-d1044857d61a`, `session_mode: resume`). The retry prompt carried only "delivery attempt 2; an earlier attempt was cut off before it finished" (`inbound_queue.format_turn_prompt`, `hub/hub/inbound_queue.py:217-222`), so the agent said "I'll run the command and wait for it to complete" and ran the same 700 s command. It failed at 600 s again. The third attempt (`run-23d84ec23d71`) started a fresh session (`RESUME_RETRY_LIMIT = 2`) and did the same. Then the entry was withdrawn: "delivery failed 3 times; the Hub stopped retrying" (`queue_entry_abandoned`, 18:30:33, 30 min 14 s after the send). No reply ever reached the operator. All three runs carry `last_heartbeat_at = NULL`, and nothing on screen says a 600 s limit exists until the first failure.

The limit cannot be changed. `copilot_acp.run_turn(turn_timeout=DEFAULT_TURN_TIMEOUT_SECONDS)` (`hub/hub/copilot_acp.py:2224`, the constant is `hub/hub/codex_appserver.py:664`, 600.0) is never passed a value by `agent_trigger`. A timeout is also not marked unretryable: `_await_prompt` returns `status="failed"` with no `error_kind`, so `return_run_entries(retryable=None)` treats it like a crash. A test suite, a build, a long migration or any honest >10 min step therefore costs three runs, three premium requests (unrecorded, F786) and half an hour before the operator learns it cannot work. F491 (fixed by changing a review context) was this mechanism in one case. Its "timeout-resume direction was not taken" note is the general fix this entry asks for.

Expected: (1) a turn that hit the deadline is not re-delivered unchanged. Either it is withdrawn at once with a reason that names the limit (an `error_kind` such as `turn_timeout`, `retryable=False`, which reaches the "Last attempt failed" text), or it is retried at most once with a retry note that says "the earlier attempt hit the 600 s turn limit; run long commands in the background or split the work". (2) The limit is a per-agent (or per-runner) setting beside the waiting settings, with 600 s as the default. Failing tests: `hub/tests/test_copilot_acp*.py`, a fake ACP session whose prompt never answers, with `turn_timeout=1`, gives a `TurnOutcome` with an `error_kind` naming the timeout and `retryable is False`; and `hub/tests/test_inbound_queue*.py`, `return_run_entries` for that outcome withdraws the entry after one attempt with a reason naming the limit. Seam: Runs (Copilot ACP deadline) x Inbound queue & messages (`return_run_entries`). Codex app-server shares the constant (*not reached*).

## F251 (B) — the Hub broadcasts 17 event names the client discards before any listener, 9 of them into handling code written for them

**Status:** open -- reopened 2026-10-23 (day `sweep-questions-sweep`, scratch Hub :8117, Chromium, `scripts/drive/s1023_cv_rail.py`): 8179c93 built F253's `stream_gap` and never touched the allowlist. `hub/ui/src/hooks/useSSE.ts:21-68` still omits `conversation_updated` (0 occurrences in the file) and `:362` drops any frame not listed; 15 broadcast kinds are still dropped (`conversation_updated`, `conversation_cut_over`, `checkpoint_due`, `checkpoint_ready`, `checkpoint_warning_dismissed`, `agent_requested`, `project_deleted`, `question_declined`, `queue_agent_held`, `queue_agent_paused`, `review_unstaffed`, `run_diverged`, `task_blocked`, `task_unblocked`, `worktree_released`). Live instance: a rename and an archive made from the conversation header (`AgentOutputPanel.tsx:507-533`, relying on the broadcast per `api/agentChat.ts:244-247`) leave the rail on the old title, and the archived conversation listed open with "Show archived (0)", 25 s later; a fresh load is right. A generated title (`conversation_titles.py:385-395`) only `persist_event`s, no broadcast, so the header keeps the first message. The unbuilt openspec leftover `every-event-the-hub-sends-reaches-the-app` covers it: move it across, do not finish it there. Previously: fixed 8179c93 (driven live 2026-09-26, drive Hub :8037, `d0926_stream_gap.py`: a stalled operator-stream subscriber, 3,000 events, one `stream_gap` frame `{dropped: 1362, severity: warn}`, no `project_id`; received 1638 + dropped 1362 = 3000. The UI half, tasks.md 3.2, NOT driven in a browser -- unit tests only). Filed as follows: Filed by the row-16 drive (`00b5dd9`). [classified 2026-09-09, D-2]
**Re-measured 2026-09-13 (day `d1-drive`), and now coupled to F335.** A live Chromium session
received `task_updated` and rendered it. It rendered nothing for the `run_divergence_resolved`
the wire carried in the same instant (captured with `curl -N /api/v1/events`). A static diff of
the Hub's literal `broadcast(…, "<kind>")` calls against `SSE_EVENT_TYPES` still finds 17 kinds
dropped. Six have a feed sentence in `eventSummary.ts`: `queue_agent_paused`, `review_unstaffed`,
`run_diverged`, `run_divergence_resolved`, `task_blocked` and `task_unblocked`. **Do not fix this
without F335.** A refused review broadcasts a false `run_divergence_resolved` at staging time, so
admitting that kind to the allowlist puts F335's false *"1 open divergence on T resolved"* line in
the live feed.

`useSSE.ts:335` is the whole of it:

```ts
if (SSE_EVENT_TYPES.includes(evt.type)) {   // useSSE.ts:335
```

`SSE_EVENT_TYPES` (`useSSE.ts:21`) is a hand-written array of 44 names. A frame whose name is not
on it is read off the socket and dropped — not dispatched, not buffered into `eventBuffer`, not
counted as stream activity by any consumer. **Measured against the bundle the Hub actually serves**
(`hub/hub/static/ui/assets/index-Xrm9NpmM.js`, whose array matches the source member for member),
against every literal name passed to `sse_manager.broadcast` under `hub/hub` (57):

```
broadcast by the Hub, absent from the served allowlist  (17)

  agent_requested        checkpoint_due          checkpoint_ready
  checkpoint_warning_dismissed                   conversation_cut_over
  conversation_updated   job_archived            new_session_request
  project_deleted        question_declined       queue_agent_paused
  review_unstaffed       run_diverged            run_divergence_resolved
  task_blocked           task_unblocked          worktree_released
```

Three were **driven, not inferred** — observed crossing the wire on a live instance stream and then
checked against the served allowlist:

```
LEG 3  names on the instance wire: ['job_created', 'job_updated', 'job_archived', 'project_deleted']
       job_created / job_updated  -> on the allowlist, reach a screen
       job_archived               -> discarded          (jobs.py:1158)
       project_deleted            -> discarded          (projects.py:628)
LEG 7  renaming a conversation:   ['conversation_updated'] -> discarded   (agent_chat.py:395)
```

**Nine of the seventeen have UI code written to handle them**, which is what makes this a defect
rather than an unused vocabulary:

| name | the code that never runs |
|---|---|
| `checkpoint_ready`, `conversation_cut_over` | `api/checkpoints.ts:46` — `useCheckpoints`' subscription |
| `conversation_updated` | `api/agentChat.ts:175` |
| `task_blocked`, `task_unblocked`, `run_diverged`, `run_divergence_resolved`, `queue_agent_paused`, `review_unstaffed` | `lib/eventSummary.ts` — an operator-facing sentence for each |

`useCheckpoints`' own docstring states the consequence in advance, as a thing that was fixed:

> *Refreshed on `checkpoint_ready`, which is what the Hub broadcasts when the threshold fires.
> Without that subscription the offer existed only in the database: the checkpoint was generated,
> probed and stored, and the operator saw nothing until they happened to reload.*

That is the current behaviour. The subscription is there; the dispatcher never calls it.

**This has happened before and was patched name by name.** `useSSE.ts:530`:

> *`loop_queue_exhausted` (design D6) is a loop event's first consumer here — none of the six were
> reaching a listener before this task, because they were absent from `SSE_EVENT_TYPES` above and
> silently dropped.*

`__tests__/useSSE.test.tsx` has two tests of exactly that shape — one for the six loop events, one
for `permission_denied` — each added after someone noticed a specific name missing. **No test
compares the array against the Hub's broadcast vocabulary**, so the next name added on the server
is dropped by default. The allowlist is a duplicate of a server-side fact with no mechanism keeping
it true.

**Reproduction:** `t_sweep_row16_logs_events_sse.py`, legs 2, 3 and 7.

---

## F322 (B) — on Codex, "Workspace only" decides a command's network access by its working directory, so the same posture will answer a URL oppositely on the two runners

**Status:** open. Filed 2026-09-12 by the day window's D-2 (R1 of `a-url-is-not-a-path`). **Read,
not run:** live reproduction is not possible, because Codex is undrivable (the plan was cancelled on
2026-08-29). No proposal.

**The claim.** `a-url-is-not-a-path` proposes that, under "Workspace only", a Claude shell command
naming any network address other than the run's own Hub is refused, and that the refusal gives a
reason about network access. On Codex the same posture decides a command approval by where the
command runs, and by nothing else:

```python
# hub/hub/codex_appserver.py:280-283
if posture == WORKSPACE_PERMISSION_MODE:
    subject = approval_subject(method, params)
    inside = _within(subject.get("cwd") or subject.get("grantRoot"), workspace)
    return {"decision": "accept"} if inside else {"decision": "decline"}
```

F98 measured this acceptance in passing (`FINDINGS.md:6704-6706`, 2026-08-28): *"accepting an
escalated command purely because it ran from inside the workspace"*. It was never filed on its own.

**What the request carries, and the Hub ignores.** This is from the research routine's
2026-09-12 schema read (`spec-queue/research/2026-09-12.md` §2). It is **unverified here**: this
window did not regenerate the schema. `CommandExecutionRequestApprovalParams` in `codex-cli`
0.146.0 carries `networkApprovalContext {host, protocol}` and `proposedNetworkPolicyAmendments`.
`grep -n network hub/hub/codex_appserver.py` returns one line (`:118`), the full-access grant.
Whether Codex 0.146.0 raises a network need as a command approval with that field populated has not
been observed.

**Why it is filed and not fixed alongside.** The F312 verdict names *"the regex-and-`_decide`
path"*, and `DIRECTION.md` measured the change's blast radius on that path alone. Bringing Codex
under the same rule would widen the change past what was decided, for a runner nobody can drive.
The alternative is a proposal that closes F312 on one runner and leaves the other doing the opposite
with nothing recorded, and that is how the ledger gets entries nobody can resolve. So this entry
exists.

---

## F339 (B) — `acceptEdits` is path-confined by Claude Code on a headless run, and four places in the repository, one of them a binding verdict's reason, say it checks nothing

**Status:** open — **DEFERRED by the operator 2026-09-21: triaged, won't build now** (`spec-queue/DECISIONS.md`, `### 2026-09-21 evening`). Neither creatable runner reaches this path (`RUNNER_CLIS = ("claude", "codex")`, both MCP-injectable) and `hub_client` has no UI control; reopen when a runner that cannot take MCP (GHCP) is implemented. **Corrected 2026-09-27 (`ghcp-d6-correct-f299`):** GHCP *can* take MCP (`--additional-mcp-config`, verified on 1.0.88); the real trigger is a run on a machine whose policy blocks MCP servers. It is answered for Copilot by slice 3, `a-run-reaches-the-hub-without-mcp`, of `openspec/explorations/2026-09-27-copilot-as-a-full-runner.md`. Original status follows. **2026-09-24 (B11):** stays parked for the approver-less question; its docs row is split out as a no-spec fix: reword `permission-postures.md:33` ("Not checked") to "checked by Claude Code, not by the Hub", with the version, after one Haiku re-measure with F339's script.
**Ready:** parked

**Original status:** open. Filed 2026-09-13 by the day window's `d7-ledger`, from research 2026-09-13
candidate 2. **Measured twice on `claude` 2.1.269, Haiku, through the Hub's own argv and PTY.** An
operator question goes with it (below), so this is not a repair.

**The claim.** Under `--permission-mode acceptEdits`, headless, with nothing to answer a prompt,
Claude Code writes inside its working directory and refuses a write outside it. The repository
says the opposite in four places:

| where | text today |
|---|---|
| `docs/reference/permission-postures.md:33` (the page `agent-run-sandboxing` requires), and `:39`, `:64` | *"**Edit files** \| `acceptEdits` \| **Not checked.** Edits are accepted with no path comparison at all."*; the no-server fallback *"falls back to **Edit files**, which checks nothing"*; *"Under the postures that check nothing, a shell redirect leaves no trace at all"* |
| `openspec/specs/agent-capability-plane/spec.md:256-259`, a shipped requirement's reasoning | a run's requests are *"checked against its workspace or accepted without a path check"*, and a move *"from a checked posture to an unchecked one"* |
| `hub/hub/runner_commands.py:63-64` | *"narrower than `acceptEdits`, which accepted every edit with no path check at all"* |
| `spec-queue/DECISIONS.md:772-774`, 1b | *"**Rejected: also drop to `acceptEdits` on no grounds.** That restores capability by removing the path check entirely"* |

The ledger repeats it: F299 at `:24342` (*"`acceptEdits`, which has **no path check at all**"*) and
F281 at `:21078`, which lists `acceptEdits` among the postures where an outside write is
*possible*. The research found no drive in the ledger that measured an outside write under
Claude's `acceptEdits`, and neither did this entry's author.

**The measurement.** `scripts/drive/t_d7_0913_accept_edits_confined.py`. argv is
`build_command(runner="claude", mcp_command=None)`, the one case the Hub itself picks `acceptEdits`
(`DEFAULT_CLAUDE_PERMISSION_MODE_WITHOUT_APPROVER`, `runner_commands.py:73`). The script asserts
the flag is present and that no `--mcp-config` or approver is. The spawn is `PtySession`, every
`CLAUDE*` variable is stripped, and the workspace is under `%TEMP%`. `init` reports
`claude_code_version: 2.1.269` and `permissionMode: acceptEdits`. The turn ended `success`, 5
turns, $0.028, rc 0. A second run, after a lint-only edit to the script, gave the same three
denials and the same files ($0.015).

| step | the CLI's `permission_denials` | on disk |
|---|---|---|
| `Write inside.txt` | — | **written** |
| `Write ../outside.txt` | **Write** (`…\d7_0913_accept_edits\outside.txt`) | absent |
| `Bash: echo hi > ../outside_bash.txt` | **Bash** | absent |
| `Write <absolute path outside>` | **Write** (`…\d7_0913_accept_edits\outside_abs.txt`) | absent |

This agrees with the research's pipe-spawned Q1, Q2, Q6 and Q7. Those runs also refused `cp` to
`../`, a shell redirect to an absolute path outside, a `Read` and a `cat` of `../`, and
`python -c`. The model said the writes were outside *"the allowed working directory"*. That is
quoted only as what the model said. The refusals come from `permission_denials`, and the file
outcomes from the disk.

**What is true in the page and what is not.**
- *"Not checked"*, *"no path comparison at all"* and *"checks nothing"*, said of `acceptEdits`,
  are false on 2.1.269.
- What stays true: **the Hub** checks nothing under `acceptEdits`, and it records none of the
  harness's refusals. `grep -rn permission_denials hub/hub` returns nothing today. The shell redirect
  also *"leaves no trace"* in the Hub, although it did not land either.
- `bypassPermissions` (*"Full access"*) was not measured and is not disputed.

**What is not established.**
- n = 2 on one build and one model. The confinement is the harness's, and it is version-bound. The
  Hub pins no build and records none.
- A path a program builds at runtime never passes the harness's text check. Under `acceptEdits`,
  `python -c` is refused (research Q6), which closes that route today only because execution is
  refused outright.
- The operator's own `~/.claude/settings.json` can widen the scope, through an `allow` rule or an
  `additionalDirectories` entry. That is equally true under every posture.

**Why B.** It is a wrong surface: an operator page and a spec's reasoning. It matters beyond the
doc, because it is the stated reason 1b rejected the one option that lets an approver-less run do
work. Measured, the choice on no grounds is not "contained but broken" against "working but
unchecked":

| on no grounds | outside the workspace | inside: edit | inside: run code |
|---|---|---|---|
| 1b as decided (`manual`, no approver) | refused | **refused** | refused |
| the rejected option (`acceptEdits`) | **refused, by the harness** | allowed | refused |

What the rejected option gives up is *who* checks. The Hub neither sees nor records the refusals,
and the rule is Claude Code's, not the Hub's.

**Relation to F299's change.** `openspec/changes/an-absent-approver-is-not-named` neither relies on
this nor reintroduces the rejected option (design D10). Its D11 was already rewritten in round 3 so
that it does not make the disputed claim normative. The operator question below is separate from
that change's own operator question. It asks whether 1b's rejection still stands on its remaining
reason.

**Operator question.** Does 1b's *"Rejected: also drop to `acceptEdits` on no grounds"* stand on its
remaining reason, that `agent-capability-plane` reserves containment to the operator and the Hub
does not substitute a posture that accepts without asking? Its stated reason, *"removing the path
check entirely"*, does not hold on 2.1.269. Either way, the four texts above need rewording. The
page's row would read something like *"Checked by Claude Code, not by the Hub: in a headless run a
path outside the run's working directory is refused (measured on 2.1.269), and the Hub neither sees
nor records the refusal."* The spec's reasoning needs rounds.

**Reproduce:** `py -3.11 scripts/drive/t_d7_0913_accept_edits_confined.py`. It makes one Haiku
turn and writes `%TEMP%\d7_0913_accept_edits\results.json` and `transcript.txt`.

---

## F417 (B) — the Compact and New-session requests are saved but never reach the agent

**Status:** open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B10 rounds
(`spec-queue/tracks/B10.md` Final). `POST /agents/{name}/compact` and `POST /agents/{name}/new-session`
(`hub/hub/api/v1/agents.py:2971-3040`) create a `sender="hub"` `Message` row, broadcast
`message_created` and persist an event, but create **no inbound-queue entry**, and messages reach an
agent only through the inbound queue. The agent never sees the request, and the route answers
`{"status": "ok"}`. The UI hooks (`hub/ui/src/api/context.ts:4-8`) are mounted nowhere, so today it is
reachable only through the API: another dead surface in the sense of D6. Repair shape: decide
build-or-delete as B10 did. Either queue the request as an inbound entry (and give it a mount), or
delete both routes and their hooks. After B10's F259 change they no longer inflate `/status`
`pending`, but the request still goes nowhere.

**Re-verified 2026-09-24 (Round 6), handed on as a spec track, not fixed.** `POST
/agents/{name}/compact` and `/new-session` (`hub/hub/api/v1/agents.py`) add a `sender="hub"`
message but no inbound-queue entry, so nothing delivers them; `hub/ui/src/api/context.ts` has no
importers. The only consumer ever specified was the deleted watchdog, and
`agent-conversation-handoff` retires the Compact/Reset controls for Handoff and start-fresh.
Queuing them would not work either (a headless run cannot `/compact`). Recommendation: a small
change that deletes both routes, `context.ts` and the `compact_request`/`new_session_request`
events; mind `every-event-the-hub-sends-reaches-the-app` and
`an-event-is-announced-only-once-its-write-is-committed`, which name `new_session_request`.

**Re-verified 2026-10-15** (full sweep, G6: Checkpoints; G2: Runs): still bites. `POST /agents/beta/compact` wrote `msg-6f4671798cd6` (`sender='hub'`, unread), no inbound-queue entry, no turn; the text asks a headless agent to "Run `/compact` in your session". `requestCompact`/`requestNewSession` (`hub/ui/src/api/context.ts`) still have no caller, and the composer's only built-in command is `/model`. The same routes (and heartbeat/output) also accept any name and mint phantom agents: filed as F618.

## F478 (B) — the workspace judge reads `key:value/path` inside a shell string as a URL whose path is outside the workspace

**Status:** arguments-file half fixed 2026-10-02 by `an-arguments-file-written-from-powershell-is-the-hubs-own`
(`4f8b8cc`; re-driven: 9.10 met on the trial Hub, `run-71191896f5c6`, Copilot's three `Set-Content` writes allowed
by standing and the submission recorded). The general half (`echo 'a:b/c'`) stays open until
`the-shell-judge-reads-a-word-whole` archives. Found 2026-10-01 by drive 9.10 of `a-run-reaches-the-hub-without-mcp`. **Ready:** R1 proposed
2026-10-02 as `an-arguments-file-written-from-powershell-is-the-hubs-own` (the arguments-file half; R2 done
2026-10-02 -- 9.10's exact command fits its grammar; R3 done 2026-10-02 -- BMP-wide tokenizer sweep, every grammar trap run on 5.1, one safety rule made explicit; adversarial review done 2026-10-02 -- APPROVE WITH FIXES, all nine applied, "nothing joined" generalised to every part, notice now spells the form out; operator approval owed, DECISIONS.md `F478-approve`). R1 measured that the refusal is rule 6's backstop, not the URL rule (rule 1 already needs `://`), so
the general half (`echo 'a:b/c'`) is F362's mechanism, owned by `the-shell-judge-reads-a-word-whole` D2.

`_decide("PowerShell", {"command": "echo 'a:b/c'"}, workspace=W)` refuses *"'/c' is outside your workspace"*; so does
`Set-Content -Path '.agentweave/calls/r.json' -Value '{"path":"spec/x.html"}' -Encoding utf8` (`'/x.html'`), while
the same write with `{"title":"x"}` is allowed. A `word:word/…` token is read as `scheme:authority/path`. It predates
the shim, but the shim's fallback (write the JSON args file from PowerShell) now meets it whenever an argument value
holds a slash -- every spec-document path does. In 9.10 a Copilot specification turn told `aw-tool` tried exactly
that (`run-b30d4295abaf`, to call `read_spec_document`), was refused, and gave up: the spec flow over the shim was
**not** demonstrated on Copilot. A file-tool write is unaffected (it has a declared path), and F477's rewording now
steers runs to it; but a spec turn's only file tool on Copilot is `create`, which that turn did not reach for.
Options for the design: read a single-quoted PowerShell literal (or a bash `'…'`) as data, not as words; or treat a
scheme only when followed by `//`. Either is a judge change with its own round.

## F1083 (B) -- a hand-driven build's builder sees only the document's recommended delivery, and `create_flow` on that document is not refused

**Status:** part (2) fixed 2026-10-29 -- `POST /jobs` refuses a flow or loop on a document with a running build, 409 naming build and driver (`hub/tests/test_one_driver_per_document.py`); part (1), the agent-readable build, fixed 2026-10-29 (task-799357e3e80e: `read_spec_document` returns the running build as the operator's choice, FR-5); the finding is fixed. Found when the operator built `a-checks-send-back-returns-the-task-s-accepted-evidence` (`spdoc-ed413679f369`) by hand.
**Source:** drive
**Theme:** Spec flow x Flows
**Ready:** yes
**Tier:** 1

Repro: the operator pressed Build with driver **hand**, level **fast**, builders `["Architect"]`, landing `main`, which recorded `build-677c20b97b82`, `driver='hand'`, with no loop. They then sent Architect "Build: <title>". Architect's only view of the document, `read_spec_document(include=full)`, shows `delivery` (the recommendation: `mode: flow`, Developer, QA, every five minutes). Nothing in the turn prompt or in any MCP read names the build or its driver, level or builders. Architect took the recommendation as the plan and called `create_flow`. The Hub accepted it: `job-842aed458b2a` / `loop-e4f44cc238ba` was created on a document that already had a running hand build, and both of the build's tasks got `loop_id = loop-e4f44cc238ba`. The job was disabled before its first firing. Archiving a loop is the operator's, so the tasks stay attached to it. **Expected:** (1) an agent can read the document's running build (driver, level, builders, reviewers, lead, landing), for example as part of `read_spec_document` beside `delivery` and labelled as the operator's choice, not the recommendation; (2) `create_flow` / `create_loop` on a document with a running build is refused, naming the build. The build itself is the only way to attach a driver. **Test:** start a hand build on an approved document, then `create_flow` on it as an agent: refused 409 naming the build, and no task's `loop_id` changes.

## F1084 (B) -- a completion outside a turn schedules its check run before it commits, so the run can see the task uncompleted, start nothing, and refuse every other request while it does

**Status:** open 2026-10-29. Found when landing batch `lbat-241d71a02f3e` sent `task-58195abe01a9` back: its own test, `test_fix_is_checked_after_landing`, failed under the Hub's `-n auto` check run (`chk-c6aa0226cb9a`) and passed alone. The test now drains `project_checks` before requesting its run; the product race is unchanged.
**Source:** drive
**Theme:** Checks
**Ready:** yes
**Tier:** 0

Repro: `task_transition_service.py:1259` calls `project_checks.schedule` for a task moved to `completed` with no run, inside the transaction that moves it. The scheduled `request_run` can run before that commit, read the task as `in_progress`, resolve no targets (`check_targets`: `awaiting_review` is false, and a sent-back task's evidence is held), and return `None` with no run recorded. While it is between `_starting.add` and its return, a second `request_run` for the task returns `None` at `project_checks.py:1199`. Both requests end with no run on the fix. Measured with 24 copies of the test under `-n auto`: 18 failed before the test's drain, 0 of 75 in three runs after. In a flow the firing's `checks_waits` backstop requests again; for a hand-driven task nothing does until someone asks for review. Fix direction: schedule after commit, as `landing_queue.release_after_commit` does.

## F382 (C) — `pytest hub/tests/ -q` stalled indefinitely overnight with no error, and a same-morning rerun could not reproduce the stall

**Status:** open — **Decided 2026-09-24 (operator, daily review, bundle B11; `spec-queue/tracks/B11.md` Final):** **watch-only, with two tripwires (no-spec fix round)**: bound `released.wait()` (`timeout=30`, then fail) at `test_agent_trigger.py:1935` and `:2089`, and give the windows' local full-suite run CI's `--timeout=300 --timeout-method=thread`. Close after two clean weeks. **Tripwires built 2026-10-13 (night iteration 27):** both `released.wait()` calls in `hub/tests/test_agent_trigger.py` now go through `_wait_released` (30 s bound, then the read raises an AssertionError naming F382; drove it with a 1 s bound on an unset event), and `.claude/loops/night-window.md` (F392 rule 1) names `--timeout=300 --timeout-method=thread` for the full-suite run; 77 passed in that file. Status stays open for the two clean weeks. Was: open, narrowed to one test but not diagnosed (2026-09-22, see the foot); watch-only proposed in D13. Was: open, undiagnosed; the rerun that motivated it concluded clean (addendum below).
Filed 2026-09-18 by the day window's D-6 unit, from reading a background run's own log rather than
from a drive.

**Source:** drive (a background command, not a product surface) — found by checking a run this
same queue had flagged as unresolved rather than trusting tree-green.
**Theme:** Testing & CI

**The night window (2026-09-17) started `py -3.11 -m pytest hub/tests/ -q`** at compose time,
logging to `.claude/autonomous/tmp/2026-09-17-hubtests-compose.log`, to check tree-green before
closing. That window ended without a verdict — still running past 105 minutes — and queued
checking it as a `D-6` candidate for today rather than blocking on it.

**Measured this morning, before touching anything.** The log file's last line is frozen at
`[ 14%]` with 21 trailing dots and no percentage marker after them — mid-batch, not between
batches. Its mtime is `2026-09-17 23:10`, unchanged for **over ten hours** at the time of this
check (`2026-09-18 09:10 UTC`). No process on the machine has that command line any more
(`Get-CimInstance Win32_Process` over every `python.exe`, cross-checked against PIDs individually)
— it did not finish, did not error into the log, and did not survive to be killed by anything that
left a trace. Nothing else in `hub/tests/` or the environment changed between compose time and this
check (`git diff` over the same window is empty).

**A same-morning rerun passed the exact point that killed the first one.** Started a fresh
`py -3.11 -m pytest hub/tests/ -q` at `09:06 UTC`, logging to
`.claude/autonomous/tmp/2026-09-18-hubtests-d6.log`, and watched it rather than trusting its exit
code alone: it crossed `14%` cleanly at `09:12:19`, no gap longer than the ordinary per-batch delay,
and reached `19%` by `09:15:02` — a rate (~2%/minute) that would finish the suite in well under the
"105 minutes and still at 14%" the night run measured. No `FAILED` or `ERROR` line in either log.

**Why this is the finding, not a thing to fix.** A stall that reproduces would name a test; this one
did not reproduce on the same machine, same suite, same day, at the same completion point, which
rules out a simple ordering or fixture bug as the *only* explanation and points instead at something
environmental — a leaked lock, a port two runs raced for (the trial Hub on `:8010` and the operator's
`:8000` were both live overnight per this window's own logs), or a resource that one run's leftover
state starved the other of. Guessing at which without a second stall to compare against would be
exactly the blind fix this window's own instructions warn against. The fresh run was left running in
the background at the time of filing (`.claude/autonomous/tmp/2026-09-18-hubtests-d6.log`) rather
than killed, so its eventual conclusion is on record for whoever next picks this up.

**Addendum, iteration 12 (2026-09-18 ~09:45 UTC): the rerun concluded, and it is clean.**
`.claude/autonomous/tmp/2026-09-18-hubtests-d6.log`'s final line: `4440 passed, 86 skipped, 262
warnings in 2301.58s (0:38:21)` — zero `FAILED`, zero `ERROR`. The only warning in the tail is a
`PytestUnhandledThreadExceptionWarning` from `aiosqlite`'s connection worker thread hitting a closed
event loop during teardown (`RuntimeError: Event loop is closed`), which is textbook async-fixture
teardown-ordering noise, not a test failure, and not the shape of a 10-hour freeze. The suite finished
in 38 minutes once it ran to completion — well inside the pace iteration 7 projected and nowhere near
the "105 minutes and still at 14%" the frozen overnight run measured. This does not diagnose the
original stall (still no reproduction, still no test name, still no traceback), but it does close the
open question of whether the fresh rerun itself would stall too: it did not. The finding stays open
as an unexplained one-time environmental stall, not as a suspected-still-broken suite.

**Related:** none yet — first time this shape has been filed.

**Narrowed 2026-09-22, and the first attempt at it was wrong.** The stalled log holds 669 results (74 `s`, the rest dots) before it froze at `[ 14%]`. In `hub/tests/` collected at `f4ff939` (the last commit before the 2026-09-17 night run), #669 is `test_agent_trigger.py::test_spawn_failure_broadcasts_run_failed_event`, and pytest writes its `.` only once the call has finished. So the run hung in **#670, `test_stop_endpoint_marks_run_stopped_and_broadcasts_run_stopped`**. An earlier version of this foot mapped the stall to #669 by an off-by-one and closed this entry as F394. The Opus review of this session caught it, and the entry is reopened. #670 ends in `_await_background_run()` after a stop with an entry queued behind the run. Two candidate hangs are left, and neither is shown. (a) F394's spin: a stopped run's redrain starts a follow-on run as its last action, and the old `while set: for t in list(set): await t` loop spins. `f9e6dee`'s shared helper removes that. (b) The fake terminal session in `_stoppable_pty` blocks in `released.wait()` with **no timeout**, so a stop that never reached `terminate` waits forever. `f9e6dee` does not touch that. The morning rerun passed, so it is intermittent. Watch-only again, as `spec-queue/ROUNDS.md` D13 proposed.

## F443 (C) — an agent can still set a task's holder, priority and description when it creates the task

**Status:** still open (2026-10-12, night ledger-sweep-2) The archived `an-agent-updates-a-task-with-what-its-tool-carries` covers update only and names F443 out of scope (design.md:9, proposal.md:45). Nothing to close.

**Earlier status:** open. Filed 2026-09-24 (daily review, operator-accepted), from the Opus review of B3
(`spec-queue/tracks/reviews/B3-2026-09-24.md` §7). B3's `an-agent-updates-a-task-with-what-its-tool-carries`
makes holder, priority and description the operator's fields on *update* (403 for a run actor). But
`POST /agent-actions/tasks` still lets an agent set all three at *creation*
(`test_agent_actions_coordination.py:123` does). That is inconsistent with "the holder is the operator's
statement", unless creation-time delegation is intended. Decide whether an agent creating a task may
name its holder (delegation), then either document the exception in `task-lifecycle-governance` or
refuse those fields at create for run actors.


## F469 (C) — the app neither shows nor edits a runner's flags

**Status:** open, filed 2026-09-30 by R2 of `a-runner-that-cannot-collaborate-says-so-where-it-is-bound` (design D7), found while writing its task 1.5.

`POST` and `PATCH /api/v1/projects/<pid>/runners` accept `flags` (`hub/hub/schemas/runners.py`, `RunnerCreate`/`RunnerUpdate`), and flags change what a run does: `--no-app-server` moves a Codex runner off the app-server transport, and with it off Full access every AgentWeave tool call is refused (`agents.py`, `get_agents_launchability`). The app never renders a runner's `flags` and cannot set them: the UI's `RunnerUpdate` (`hub/ui/src/api/runners.ts`) has only `name` and `model`, and no component reads `flags`. So a flagged runner exists only because something called the API, the operator cannot see why it behaves differently from its twin, and cannot undo it except by deleting it. The cannot-collaborate line now names remedies the app does offer (rebind, or Full access) instead of a flag edit.

Question for the operator: should the Runners page show flags read-only (cheap, removes the invisible state), or edit them (free-form CLI arguments, needs validation per CLI)? Test either way: a runner created with flags through the API shows them on the Runners page.

**Operator answered 2026-09-30 (AskUserQuestion, handoff-0158 resume):** show them read-only. The Runners page renders a runner's `flags`; editing stays with the API (or delete and recreate). Ready to propose.

**Re-verified 2026-10-15** (full sweep, G1: Runners & models): still open; the Runners page and every runner select still show no flags. The sweep showed flags also override the model and the permission posture (a `--dangerously-skip-permissions` runner wrote outside the workspace while the roster said `workspace`): filed as F599, with the Add-agent binding that hands such a runner out as F600.

## F551 (C) -- three small requirement-traceability defects

**Status:** partly fixed 2026-10-12 (Tier 0, night iterations 17 and 21): part 1, the blank rejection reason, is closed -- `requirement_evidence.decide` refuses a rejection with a blank reason (422 `rejection_needs_reason`) on both planes; test `test_a_rejection_of_evidence_carries_its_reason.py` failed first; drive `d1012_f551_rejection_reason.py` 10/10; the app's reject control already disables Reject on a blank reason. Part 3, identifier sort order, is closed too (night iteration 21): the coverage report, the `unserved` list and `requirement_links.for_task` re-sort their rows with the shared `spec_identity.natural_key` (promoted from `spec_tasks._natural`, which `api/v1/tasks.py` had restated); test `test_requirement_identifiers_sort_naturally.py` failed first (3); drive `d1012_f551_sort.py` 9/9. Left as it was on purpose: `GET /spec/requirements`, whose string order a test pins and the app re-sorts (F211). Still open: the `provisional` flag never cleared. Filed 2026-10-08 (spec overhaul audit, reading code; see the audit report for
`requirement-traceability`). The Hub accepts an empty reason when rejecting evidence; the `provisional` flag on evidence
is never cleared; requirement identifiers sort as text (`FR-10` before `FR-2`).

## F553 (C) -- dead UI and parser code, and a built-in command that does nothing

**Status:** partly fixed 2026-10-09 (Tier 0, night iteration 4; decisions overhaul-dead-renderers, overhaul-model-command). Deleted `SharedStreamRenderer.tsx`, `streamModel.ts`, `AgentActivityTab.tsx` and their tests (`streamRenderer.test.tsx`, the AgentActivityTab case in `timelineEnvelopeUnwrap.test.tsx`; two n11 CLASSIFIED rows for the deleted file). Accepting `/model` in the composer now clears the typed command and opens the composer's model picker (`composerModelCommand.test.tsx`, 3 cases, all failed before). **Left alone, undecided:** `parse_opencode_line` and `panelTabsStore.reconcile` -- the operator did not decide them. Not driven in a browser; rendered vitest covers the real Composer and ModelPicker. Filed 2026-10-08 (spec overhaul audit, reading code).
`SharedStreamRenderer.tsx`, `streamModel.ts` and `AgentActivityTab.tsx` are mounted nowhere (only tests import them);
`parse_opencode_line` (`runner_parsing.py:644`) parses for a runner nothing launches; `panelTabsStore.reconcile` has no
production caller, so dangling file and document tabs are never dropped on load; the composer's only built-in command
`/model` (`composerTriggerSources.ts:16`) inserts the text and nothing acts on it. Operator questions in DECISIONS.md.

## F656 (D) -- legibility of permission refusal reasons: doubled backslashes, path fragments, an event with no agent, and a stop refusal that hides an unknown name

**Status:** partly fixed 2026-10-15 (Tier 0). Fixed: a refusal quotes its word as written (`mcp_server._quote`: single quotes, only a non-printing character escaped, no `repr` doubling; 47 judge tests re-spelled, a new test pins the form), and every `permission_denied` event carries `agent` in its data, so the Activity line names who was refused (three emitters; new test). Provider-drive fragments are fixed by F601 (the word is quoted whole). Not fixed here: the `('.'+'.')` and `${HOME` fragments (cosmetic), and `stop` on a never-created name answering "has no run in progress" -- that name was known because an earlier probe minted it as a phantom agent, which is F618's root (S4). Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G7: Permissions & sandbox, Logs; scratch Hub `:8037`).

- On Windows the workspace verdict quotes paths through `repr`, so the operator's card reads `'..\\aw-sweep-1015-g7-outside\\outside.txt' is outside your workspace`, with doubled backslashes the agent never wrote (`_quote`, `mcp_server.py:1426`).
- Provider paths are quoted as fragments: `Get-Content Env:\PATH` gives `'\\PATH' is outside`, `('.'+'.')\x` gives `'\\x'`, and `${HOME}` gives `'${HOME'`.
- The Activity row reads `permission_denied: an agent was refused PowerShell…`; the event payload carries no `agent`, though the run knows it is alpha.
- `POST /agent/ghost/stop` gives `404 "ghost has no run in progress."`, not "ghost is not an agent" (cf. F618).

Seam: Permissions & sandbox (verdict wording) x Logs, events & SSE. Tier guess: 0.

## F657 (D) -- small echoes and asymmetries in the spec and evidence routes

**Status:** partly fixed 2026-10-15 (Tier 0). Taken: an unknown rigor answers 422 (malformed), not 409; the operator's evidence decision answers with the footprint (`_footprints_for`, as every other evidence answer); a no-flow approval of a document with no tasks says "the document declares no tasks" instead of "the tasks are on the board". `test_spec_route_echoes.py` and `test_the_decision_response_reports_the_footprint` failed before. Driven: rigor `bogus` -> 422 on a scratch Hub. **Not taken:** close-exploration on a proposed document is F560's (the route outlived its gate); rejecting a proposal with no reason vs evidence needing one, and the unknown roadmap slice not reported while the roadmap is proposed, are left open here (each needs a choice of which side moves). Opened 2026-10-15. Measured in the 2026-10-15 full sweep (G4: Spec documents, Requirements, evidence & coverage; scratch Hub `:8034`).

- The evidence decision response returns `"footprint": null`; `GET /spec/evidence` shows the footprint (`efp-339be924b892`). Related F280.
- Unknown rigor -> **409** `unknown_rigor` (a malformed value, not a conflict).
- Rejecting a proposal needs no reason (200); rejecting evidence does (422 `rejection_needs_reason`).
- `close-exploration` on an already-`proposed` document answers 200 and records an event (cf. F560).
- An approval report for a document with no tasks says "the tasks are on the board, started by hand".
- An unknown roadmap slice is not reported while the roadmap is only proposed (only `roadmap_not_approved`), although the roadmap's slices are already known.

Seam: Spec documents x Requirements, evidence & coverage (route echoes). Tier guess: 0.

## F77 — an agent has no way to address the operator

**Status:** open — filed, not fixed

**Severity: C**, but it is the reason F76's turn ended in prose rather than a record.

**What happens.** The reviewer, having concluded, tried to tell the person who asked:

```
mcp__agentweave__send_message {"to": "Operator", "content": "## Review Verdict: APPROVED ..."}
  -> 404 "Unknown recipient 'Operator': no agent by that name is registered in this project"
```

`send_message` addresses the roster, and the operator is not on it. `ask_user` exists but is for
*questions* — it takes 1-4 structured questions, blocks the run, and waits for answers. A verdict
is not a question, and an agent that used `ask_user` to deliver one would be misusing the one
blocking primitive the product has.

**The refusal is legible about the wrong thing.** It correctly says no agent is named `Operator`;
it does not say whether addressing the operator is possible at all, so the agent's next move is to
guess another name. Per the standing rule that a refusal must say what *would* work, this one
cannot, because nothing would.

**Whether this should be fixed is genuinely open**, and connects to the retired question-detection
backstop: the product deliberately does not guess when trailing prose is addressed to a human. An
explicit `notify_operator` would not be a guess. Recorded, not decided.

---

## F325 (A) — on Codex's default transport a run never receives its canonical context, so a bound charter reaches no Codex agent

**Status:** open. Filed 2026-09-12 by the day window's `D-7`, from research 2026-09-12 §3, and
verified against the code at `34014e0` by reading. **Read, not run:** live reproduction is not
possible, because Codex is undrivable (the plan was cancelled on 2026-08-29). No proposal.

**The claim.** Every turn renders the canonical context: charter, operating profile, the tool
section for this run's access path, workspace facts, spec-document blocks, and the review block on a
review turn. It is written to `<work_dir>/.agentweave/context/<agent>.md`
(`hub/hub/api/v1/agent_trigger.py:1001-1047`). What happens next depends on the runner:

| runner / transport | how the context is handed over | code |
|---|---|---|
| `claude` | `--append-system-prompt-file <path>` | `hub/hub/runner_commands.py:229-230` |
| `codex`, `exec` (opt-out, `--no-app-server`) | `-c model_instructions_file=<path>` | `runner_commands.py:311-312` |
| `codex`, `app-server` (**the default**) | **nothing**: the file is written and never read | below |

**The app-server row, measured line by line.** `uses_app_server` (`hub/hub/codex_appserver.py:79-87`)
returns true for every `codex` runner without `--no-app-server`. It has done so since `4b9604f`
(2026-08-06 21:55). `build_command` receives `context_file` (`agent_trigger.py:1089-1104`), but
`cmd` *"is unused on the app-server transport"* (`:1269-1272`). What the app-server path gets is
`prompt` (`:1265`), which is `"\n\n".join([*notices, message])` (`:1074`): the access-path notice,
the auto-snapshot notice, the spec-phase notice and the message. `_execute_codex_appserver_run`
(`:2619`) passes it to `codex_run_turn` unchanged (`:2803`). `prompt` appears nowhere else in that
function. `run_turn` has no parameter for context (`codex_appserver.py:904-926`). `thread/start`
and `thread/resume` get `cwd`, `sandbox`, `approvalPolicy`, an optional `model` and an optional
`config` (`:955-990`). `config` is the rendered config-style controls plus the Hub's MCP server.
The catalog's only config-style control is Codex's effort (`hub/hub/model_catalog.py:231`,
`model_reasoning_effort`). `turn/start` gets the thread ID and `prompt` alone (`:998-1001`). Nothing
points the agent at the file: `hub/hub/api/v1/agents.py:1602-1604` removed that pointer on purpose,
because the file's contents are *"already delivered as the system prompt"*. That comment was
committed in `828718b` at 2026-08-07 00:17, 2h22m **after** app-server became the default.
`grep AGENTS.md` over `hub/hub/` returns nothing, so no second route exists.

**Every line number in research §3 held** at `34014e0`. Two statements moved:

- The research dates the comment "the same day" as the default. It was committed after.
- The research counts six app-server tests. There are eight (`hub/tests/test_agent_trigger.py:107`,
  used at `:1285 :1414 :2435 :2477 :2532 :2577 :2628 :2666`), and none asserts anything about
  context. The `exec` flag is pinned, by `hub/tests/test_runner_parsing.py:204-210`, which the
  research did not mention. Any repair changes it.

**What the protocol offers, regenerated here.** `codex app-server generate-json-schema` (CLI
0.146.0, the installed build) was run into `testbed/scratch/d7codex/schema/`, with no model turn.
`ThreadStartParams` has 15 properties, including `baseInstructions` and `developerInstructions`,
both `string | null`. `ThreadResumeParams` carries both. `TurnStartParams` carries neither. The
`Config` definition has a `developer_instructions` key. The schema describes none of them. On
`HEAD`, `git log -S` over `hub/` and `src/` finds **0** commits for `developerInstructions`,
`baseInstructions` or `developer_instructions`. With `--all`, it finds `developerInstructions` only
in `50bd12e`, the research file copied into `spec-queue/`, and in `578afad`, a T3 Code checkpoint
ref.

**What it breaches.** `agent-context-onboarding`, *Canonical per-agent runtime context*: "The Hub
SHALL build canonical runtime context for each configured agent and supply it to every run", with
the scenario *Runtime launch injects generated context*. `agent-charter`, scenario *Agent context
resolves its bound charter*: "WHEN an agent with a bound charter begins a turn, THEN the supplied
context includes that charter's content". On a `codex` runner with default flags, neither holds.
Severity A because the operator acts on what the agent does, believing a charter governs it.

**Where the research overstates.** It says a Codex reviewer "is not told what it is doing". For a
review dispatched by a loop or a flow, it is told. The scheduler prepends the loop briefing to the
queue entry's `content` (`hub/hub/scheduler.py:2826-2833` and `:3180-3187`), which becomes the
prompt, and the briefing says *"**This turn is a review.** Somebody else finished the task below"*
(`:2187`, `:2201`). What a Codex reviewer lacks is the context's review block
(`agents.py:1610-1661`): the commit under review, *detached HEAD is expected*, *"Do not fix what you
find. Report it."*, and *end the review with a verdict through `update_task`*. A review dispatched
straight through `POST /agent/trigger` has only its message. The research's sentence holds for that
path.

**Unverified: the `exec` half.** That `model_instructions_file` **replaces** Codex's built-in
instructions, rather than adding to them, is Codex's behaviour. This repository does not pin it.
`openspec/changes/archive/2026-04-26-add-codex-runner/design.md` D2 chose the flag without saying
which it does. The only probe of the flag is recorded in handoff-0039 (2026-08-13) and the archived
`2026-08-13-the-spec-tool-reaches-the-agent` tasks.md 1.4: a passphrase that existed only in the
file came back. That shows the file reaches the model, not what it displaces. The research quotes
`codex-rs/config/src/config_toml.rs:250-254` at `654b0a7`: *"override the built-in instructions
… STRONGLY DISCOURAGED"*. This window does not browse and did not re-read it.

**Plausible, unverified: a 2026-08-13 conclusion may rest on this.** That probe was a direct
`codex exec` from the shell. Handoff-0039 records the `--skip-git-repo-check` and closed-stdin traps
it hit. The Hub-driven Codex iterations it was run to explain did not follow a precedence statement
that was *"verified present in the delivered context file"*. They ran through the Hub a week after
app-server became the default. Their runner's flags are not recorded, and the harness
(`testbed/scratch/spec_loop.py`) no longer exists. If they ran on app-server, the probe tested a
channel they never used, and the context never reached them. That would also explain why the fix
that worked was moving the directive into the turn prompt, since the prompt is the one channel
app-server delivers.

**Confirming probe, for whoever can drive Codex.** Bind a charter containing a marker word to a
Codex agent with default flags, run one turn, and ask it to *quote* its `## Charter` section. Ask
it to quote rather than obey (`FINDINGS.md:14811-14814`). On the code as read, it will say it has
no charter.

**Related:** F322 (the other Codex-only defect filed today, same basis), F306 (the right agent
reviews; on Codex app-server that agent does not get the review block).

---

## F1082 (A) -- an agent turn's auto-snapshot committed the main checkout's untracked files onto master

**Status:** open 2026-10-29. The gitlinks were cleaned up by hand in `dab496b`.
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** yes
**Tier:** 2

Repro: Architect's review turn on `task-a80259e4ab36`. The turn ran in `.agentweave/tasks/task-a80259e4ab36`, and several of its shell commands were run from the project root (`cd /c/.../AgentWeave; git log ...`). At 10:12:12 the Hub's end-of-turn snapshot committed `b3b0562` "Auto-snapshot: Architect's turn on task-a80259e4ab36" **on master, in the main checkout**. It was 36 files: 32 under `knowledge/`, two `spec/changes/*/spec.json`, and two gitlinks (mode 160000) to the scratch worktrees `tmp-merge-chk` and `tmp_master`. The next landing batch (`lbat-f2b3c8e7899e`) took `b3b0562` as its base and landed on top of it. The snapshot is supposed to commit the agent's own worktree only. **Expected:** the snapshot commits only inside the run's workspace, and refuses (with a recorded reason) to commit to the project's main branch or main checkout. Auto-snapshots should also never stage gitlinks. **Test:** run an agent turn whose workspace is a task worktree; leave untracked files in the main checkout; the turn's snapshot must not create a commit on master. (First written as F1049 on a branch whose ledger was behind master's; renumbered 2026-10-29.)

**Cause (found 2026-10-29 by Architect, not yet confirmed by a test):** the root-level shell commands are not the cause. The review turn approved the task from inside its own checkout. Approval releases (removes) the task worktree, but `.agentweave/tasks/task-a80259e4ab36/` survived as an empty directory, modified at 10:12, with no `.git`. Most likely Windows cannot delete a directory that is a live process's working directory, and the agent's turn ran there. The end-of-turn snapshot then ran in that directory: `snapshot_worktree` (`hub/hub/worktrees.py:1654`, master) runs `git add -A` and `commit` with `cwd=<path>`, and `_run_git` (`:109`) has no top-level guard. Git found no repository there, walked up, and used the enclosing main checkout (`git -C .agentweave/tasks/task-a80259e4ab36 rev-parse --show-toplevel` answers the project root today). `add -A` stages the whole working tree from any subdirectory, so every untracked file in the main checkout was committed on master. That explains the 36 files: Hub-written vault files under `knowledge/`, two Hub-written spec documents, and the scratch worktrees as gitlinks. `task_id_of` read the task id off the path, so the message still named the task. **Fix direction:** before any write, `snapshot_worktree` (and arguably every `_run_git` against a task or agent checkout) checks that `rev-parse --show-toplevel` is the directory itself and that it is not the project's main checkout, and refuses with a recorded reason otherwise. **Test:** create a task worktree, remove it leaving the empty directory, leave an untracked file in the main checkout, and snapshot that path: no commit on main.

## F134 (B) — a charter with no content is injected as a bare heading, and the agent is reported fully configured
**Status:** open (design gap, no chosen fix -- refuse empty charter content at the API, or render a no-charter-equivalent notice, or a third explicit statement)

**Driven 2026-08-30, iteration 11, full-surface sweep. Row 4 into row 3, on the 8011 Hub,
`proj-1964cdedffe2`.**

`POST /projects/{p}/charters` with `{"name": "sweep-empty", "content": ""}` answers **201**. Binding
it to an agent answers **200**. The canonical context that every real turn is built from then ends
like this — this is the literal last line of
`GET /projects/{p}/agents/agent-context?agent=unbound-driver`:

```
## Charter: sweep-empty
```

Nothing under it. The document stops there.

The code has a strictly better sentence for this situation and cannot reach it:

```python
if charter:
    lines.append(f"## Charter: {charter.name}")
    lines.append("")
    lines.append(charter.content)      # ""
    ...
else:
    lines.append("## Charter")
    lines.append("")
    lines.append("No charter is assigned to this agent.")
    ...
    missing.append("charter")
```

`hub/hub/api/v1/agents.py:1502-1513`

`if charter:` tests the *row*, which is always truthy when one is bound, so an empty contract takes
the first branch. Two consequences:

1. **The agent reads a heading that promises a behaviour contract and finds nothing.** An agent
   reasonably reads that as truncation. `_render_hub_agent_context` is not a reporting route — it is
   materialised into the workspace immediately before command construction for *every* turn
   (`agent_trigger.py:897-911`, *"an edited charter is therefore visible on the next run"*), so this
   is what a real run receives.
2. **`missing` stays `[]`.** The response reports the agent as wanting nothing, while its behaviour
   contract is empty. The `else` branch appends `"charter"`; this branch cannot.

### The corpus does not cover it

`openspec/specs/agent-charter/spec.md:56-72` governs the neighbouring case and stops short:

> An agent with no bound charter SHALL remain usable — its context response SHALL state plainly that
> no charter is assigned rather than erroring **or fabricating behavior content**.

A bound-but-empty charter is neither "resolves its bound charter" nor "has no bound charter". The
requirement's own phrase is the right test and no scenario applies it here.

### The asymmetry that produced it

`hub/hub/schemas/charters.py:12-13` — `name: str = Field(min_length=1, max_length=256)` beside
`content: str` with no constraint. The name of a behaviour contract is guarded; its text is not.

### One defect, or a design gap

A gap, with more than one defensible answer, so **filed, not fixed**: refuse empty content at the
API (an operator mid-edit cannot save a blank draft), or render the no-charter notice and count it
in `missing` (an empty charter and no charter become indistinguishable, which may be exactly right),
or emit a third explicit statement. `PATCH` has the same hole — `content: Optional[str] = None`
means an existing charter can be blanked the same way. Severity B rather than A: it degrades what an
agent is told rather than stopping anything, and no seeded charter is empty (all 9 have content).

**Reproduce:**

```
POST  /api/v1/projects/<p>/charters    {"name":"blank","content":""}      -> 201
PATCH /api/v1/projects/<p>/agents/<a>  {"charter_id":"<id>"}              -> 200
GET   /api/v1/projects/<p>/agents/agent-context?agent=<a>
      -> .context ends "## Charter: blank" ; .missing == []
```

### Also driven this row, and held

- `GET /fs/list` on a missing path, and on a *file*, answers 200 with `entries: []` **and a
  `reason`** naming the OS error — it does not turn "I could not look" into "there was nothing
  there". `DirectoryPicker.tsx:158-161` renders it: *"Can't read this directory: {reason}"*. The
  seam this sweep expected to be broken is not.
- Duplicate charter names are accepted (six rows named `sweep-charter` in this project). Not filed
  as a defect: binding is by `charter_id` throughout, and no requirement claims names are unique.
  Recorded so the next sweep does not re-derive it.
- `GET /agents/agent-context` for an agent that does not exist answers 200 with onboarding context,
  by design; an illegal agent name answers 400 `Invalid agent name`.

## F139 (B) — the agent reached for the host's `SendMessage`, and reported AgentWeave's own roster as unreachable

**Status:** open. Non-deterministic and unfixed. The archived change
`2026-09-01-a-flow-briefing-names-its-contract` cites it in `design.md:35` as a reason its own
briefing cannot assume a tool call, and repairs nothing here. [classified 2026-09-09, D-2]

**Driven 2026-08-30, iteration 12, on the 8011 Hub, `proj-1964cdedffe2`, agent `driver` on
Claude/Haiku. Non-deterministic: the identical instruction succeeded on the run nine minutes
earlier and failed on this one, with nothing else changed.**

`driver` was told, in the operator's own words, to *"use the send_message tool exactly once to send
to the agent named 'peer'"*. Its transcript (`conv-fb23a8232711`):

| # | tool called | outcome |
|---|---|---|
| 1 | **`SendMessage`** `{"to_agent": "peer", "subject": "ping", "content": …}` | tool failed |
| 2 | `ToolSearch` `{"query": "select:SendMessage"}` | loaded the **host's** schema |
| 3 | **`SendMessage`** `{"to": "peer", "recipient": "peer", "message": …}` | "tool completed" |
| 4 | `ToolSearch` `{"query": "select:ListAgents"}` | loaded the **host's** roster tool |
| 5 | **`ListAgents`** | listed Claude Code sessions |

and then, as its final visible answer to the operator:

> I cannot complete this task. The agent named 'peer' from the AgentWeave roster is not currently
> reachable. `ListAgents` shows three peer sessions, but none of them is the 'peer' agent specified
> in the instruction.
>
> The send_message call failed with "No agent named 'peer' is reachable."

`peer` was on the roster, open, idle, and bound to a runner throughout. Nothing was ever sent. The
Hub's queue for `peer` records no new entry, `driver`'s run completed `status: "Completed"`, and the
operator is left with a confident, detailed, entirely wrong report that **their own roster is
broken** — sourced from a different product's view of a different kind of agent.

### The collision

The Hub spawns Claude Code, which ships its own agent-messaging tool called **`SendMessage`** and its
own roster tool called **`ListAgents`**. AgentWeave's are `mcp__agentweave__send_message` and the
roster in the injected context. The names differ only by case and separator, and both describe
"message another agent", so an agent told to *"use the send_message tool"* has two plausible
referents and no way to rank them.

The canonical context is already aware of the prefix, and says so once, in a header line
(`GET /agents/agent-context?agent=driver`):

> Names below are as injected; with an MCP surface they are prefixed `mcp__agentweave__`.

— and then lists the tool bare:

> - `send_message(to_agent, subject, content, message_type=message, task_id=None)` …

So the context states the rule in one place and violates it in every call site beneath. A note that
the reader must apply is weaker than a name that is already correct, and this transcript is what the
difference costs. On the successful run nine minutes earlier the same agent's `ToolSearch` query was
`select:send_message` and it landed on `mcp__agentweave__send_message`; here it was
`select:SendMessage`. Nothing in the product decided which.

### Why it is worse than a wrong tool call

The host's `SendMessage` **succeeded** at step 3 — the Hub recorded `tool completed` — while
carrying the message nowhere AgentWeave can see. And the host's `ListAgents` answered with real
data about the wrong population, which is what gave the agent the confidence to write a diagnosis
rather than ask. An agent that had simply failed would have said so; this one investigated, using
tools that all worked, and reached a conclusion about the product that is false.

There is no Hub-side signal at any point. The run is `Completed`, the queue is empty, and only
reading the transcript reveals that the hop never happened.

### The cheap mitigation, and why it is filed rather than applied

Inject the fully-qualified names. `mcp__agentweave__send_message` does not collide with anything,
and the header note becomes unnecessary rather than unheeded. That touches every tool name in the
canonical context — a surface the agent-facing text tests pin (`hub/tests/test_agent_facing_text.py`)
and one that other runners render differently, so "as injected" is genuinely runner-dependent and
picking one spelling is a decision about which runner the text is written for. That is the
operator's call.

Two smaller things fall out of the same transcript, recorded and not filed separately:

- The Hub renders a tool result as **`tool completed`** when the tool returned an error payload
  (step 3 above: `"No agent named 'peer' is reachable"`). The word in the timeline describes whether
  the call returned, not whether it worked, which is the opposite of what an operator scanning a
  transcript will read it as.
- Every AgentWeave tool call on Claude Code costs an extra round trip: the first call fails, the
  agent runs `ToolSearch`, then it calls again. Both runs show it. Harmless, but it is two extra
  provider requests per tool on every turn.

### Reproduction

Trigger any Claude-runner agent with an instruction naming `send_message` in prose and a peer to
send to. Roughly one attempt in two picks the host tool. `scripts/drive/t_row6_hop_chain.py` is the
harness; run it until the hop-1 check reports no new entry, then read the triggering agent's
transcript rather than the queue — the queue shows nothing, which is the whole problem.

## F147 (B) — the startup pass that re-queues a crashed job firing writes that firing off as failed one line later, and nothing ever corrects it

**Status:** open, filed not fixed under D5 — every repair changes when or how a firing is
concluded, which is a design call. Reproduced live by `scripts/drive/t_row19_crash_job.py` on
`proj-1964cdedffe2` / `driver` / Haiku, 8011.

`reconcile_stale_job_runs` had never been driven by anything — its own docstring says so, and its
correlation is a join by convention rather than by constraint, which **F121** already found bending.
Driving it says the reconciliation itself is fine and the *history it leaves the operator* is wrong.

### Measured

A job is created and fired by hand; the Hub is force-killed mid-firing; the Hub restarts.

```
runs      run-a46a031d484f  conv-ea9c3ad574b3  interrupted  ended 09:15:11   <- the crash
runs      run-3d282cf81379  conv-ea9c3ad574b3  completed    09:15:12 -> 09:15:23  exit 0
job_runs  run-e584a6b1bee3  conv-ea9c3ad574b3  failed
          error_summary = "Reconciled on Hub start: no live run behind this firing"
```

Same conversation on all three rows. **The firing's work ran to completion twelve seconds after the
restart, on the firing's own conversation, exit 0 — and the job's history still reports that firing
as failed.** No second `JobRun` is written for the run that succeeded, so `GET /jobs/{id}/history`
shows the operator one entry and it says failure.

### Why nothing corrects it

The two startup passes are adjacent (`main.py:350-351`) and they work against each other:

```python
await reconcile_interrupted_runs()   # run_reconciliation.py:87 -> return_run_entries(db, run.id)
await reconcile_stale_job_runs()     # run_reconciliation.py:221 -> job_run.status = "failed"
```

The first one **re-queues the crashed run's input** — that is what `return_run_entries` is for, and
F145 measured the redelivery working end to end. So by the time the second one declares "no live
run behind this firing", the firing's work is already queued to be retried and will be running
within a second or two. The sentence is true at the instant it is written and false almost
immediately after.

The normal end-of-turn path cannot repair it, because it only looks at firings still in flight
(`scheduler.py:1568-1576`):

```python
select(JobRun)
  .where(JobRun.conversation_id == conversation_id, JobRun.status == "in_progress")
```

Reconciliation has already moved the row to `failed`, so the successful run's
`finalize_job_run_for_conversation` matches nothing and returns silently. The row is `failed`
forever.

### A second, latent defect in the same function

`reconcile_stale_job_runs` correlates with an **unordered** `.first()`:

```python
run_result = await db.execute(select(Run).where(Run.conversation_id == job_run.conversation_id))
run = run_result.scalars().first()
if run is not None and run.status == "running":
    continue
```

At the moment this drive ran there was one `Run` on that conversation. There are now **two**, and
after any redelivery there always will be. A second crash during a retried firing would therefore
consult whichever row SQLite hands back first — quite possibly the older `interrupted` one — and
write off a firing that is running. `finalize_job_run_for_conversation` orders its own version of
this same correlation `fired_at.desc()` and explains why in its docstring; this one does not order
at all.

### The repairs, and why the choice is the operator's

1. **Don't conclude what you just re-queued.** Skip a `JobRun` whose conversation has a queue entry
   that `reconcile_interrupted_runs` just returned. Narrowest, and it needs the first pass to hand
   the second one its returned entry ids — they are already computed (`run_reconciliation.py:87`).
2. **Conclude it as interrupted, not failed,** and let the resumed run finalize it. Needs
   `finalize_job_run_for_conversation` to accept `"interrupted"` as well as `"in_progress"`, and
   needs `interrupted` to be a status the job history renders.
3. **Write a second `JobRun` for the retry.** Truthful about both attempts and the closest to what
   the last-ten-runs view is for, but it changes what "a firing" counts as, and F121 is already a
   finding about one firing producing two rows.

The `.first()` ordering is small and unambiguous enough to fix on its own, but it sits inside the
function all three repairs rewrite, so it is filed with them rather than patched ahead of them.

### The harness read 4/4 while getting this wrong

Its verdicts were *"no JobRun is left in_progress"* and *"the crashed firing is recorded as
failed"* — both true, both passing, and the second one asserts the defect as the expected outcome.
The file now also asserts that the firing's work completed on the firing's own conversation (it
did) and that the history says so (it does not), so the row that is wrong shows as `BAD` until it
is fixed. That is the eighth harness defect of this sweep and the second of the species *"the
assertion agreed with the bug"* (F143 was the first).

**Reproduce:**

```
AW_HUB=http://127.0.0.1:8011 AW_KEY=... AW_TICKET_SECRET=aw0830-ticket-secret \
  AW_PROJECT=proj-1964cdedffe2 AW_AGENT=driver AW_PORT=8011 \
  AW_DB="sqlite+aiosqlite:///C:/Users/huida/AppData/Local/Temp/aw0830/aw0830.db" \
  AW_HUBLOG="C:/Users/huida/AppData/Local/Temp/aw0830/hub_crash.log" \
  PYTHONIOENCODING=utf-8 py -3.11 -u scripts/drive/t_row19_crash_job.py
```

It kills and restarts the Hub on the port you give it. **Do not pipe it through `head`** — SIGPIPE
kills it before the `finally` that disables and archives the job. It now also exits unless the
agent is idle and bound and no job is already enabled.

## F340 (B) — the Hub's MCP grounds are positive-only and permanent, while the harness reports the server's state on every run and the Hub parses none of it

**Status:** open — **DEFERRED by the operator 2026-09-21: triaged, won't build now** (`spec-queue/DECISIONS.md`, `### 2026-09-21 evening`). Neither creatable runner reaches this path (`RUNNER_CLIS = ("claude", "codex")`, both MCP-injectable) and `hub_client` has no UI control; reopen when a runner that cannot take MCP (GHCP) is implemented. **Corrected 2026-09-27 (`ghcp-d6-correct-f299`):** GHCP *can* take MCP (`--additional-mcp-config`, verified on 1.0.88); the real trigger is a run on a machine whose policy blocks MCP servers. It is answered for Copilot by slice 3, `a-run-reaches-the-hub-without-mcp`, of `openspec/explorations/2026-09-27-copilot-as-a-full-runner.md`. Original status follows.
**Ready:** parked

**Original status:** open. Filed 2026-09-13 by the day window's `d7-ledger`, from research 2026-09-13
candidate 3. **The code half was read from the source, and the permanence was measured with a
one-off test. The harness half is measured, from the F299 rounds' and the research's evidence.**
Overlaps `openspec/changes/an-absent-approver-is-not-named` (design D3, D9, D11). That change does
**not** absorb it (see below).

**The claim.**
- **Positive-only and permanent.** `harness_has_honoured_mcp` (`hub/hub/launchability.py:232-260`)
  is true once **any** run of the agent carries an `mcp_adapter_online_at`:
  `select(Run.id) … .limit(1)`, with no ordering, no recency, and no count of later runs.
  - The only writer is the adapter's announce (`hub/hub/api/v1/agent_actions.py:441-442`), which
    only ever sets the column.
  - Its docstring gives the reason (`:246-247`): *"There is no negative form to record: a harness
    that ignores the configuration is silent."*
- **The harness is not silent.** It reports the server's state before any model call, on the first
  stream-json line (`system`/`init`), in `mcp_servers`. `parse_claude_line` has no branch for
  `system` (`hub/hub/runner_parsing.py:244-371`: `assistant`, `user`, `result`, `rate_limit_event`).
  Such a line falls through to `return ParsedLine(session_id=session_id)` at `:371`. The harness's
  stderr sentence *"Warning: MCP server blocked by enterprise policy: agentweave"* reaches the Hub
  through the PTY and becomes a plain text event (`:235-238`). Nothing acts on it or records it.
  `grep -rn mcp_servers hub/hub` finds only Codex config-building code.

**What the harness says, measured on 2.1.269.**

| condition | `init.mcp_servers` entry for `agentweave` | evidence |
|---|---|---|
| server started | `{"status": "connected"}` | R3 `S_0`/`S_8`, `evidence/r3-harness-results.json`; research I1 |
| server exits at start | `{"status": "failed"}`, turn completes rc 0 | R3 `S_crash`; research I2 (binary missing) |
| server never ready within ~30 s | `{"status": "failed"}`, turn completes rc 0 | R3 `S_45` |
| server blocked by `deniedMcpServers` via `--settings` | **absent** from the list | R2 `"init_agentweave": "ABSENT"` (2 runs), `evidence/r2-harness-results.json`, `a-hub-plain-raw-pty.txt`; research I3 |

The `evidence/` paths are under `openspec/changes/an-absent-approver-is-not-named/`.

**Permanence, measured.** A one-off test, run once on `ae5766f` and deleted. It planted one run
of agent `g` with `mcp_adapter_online_at = 2020-01-01`, followed by five later `failed` runs with no
stamp. `harness_has_honoured_mcp(session, "proj-test", "g")` returned `True`: 1 passed. The
existing tests (`hub/tests/test_mcp_adapter_online.py:98-129`) cover the positive case and the
never-stamped case only.

**What it gets wrong today, on this tree.** The grounds decide only what a run is *told*
(`described_access_path`, called at `hub/hub/api/v1/agent_trigger.py:1001-1005`). What the run is
*given* (the server, and with it the approver flag) comes from `resolve_access_path` alone.
- **A policy that arrives after the first success.** The agent is told the MCP form of its tool
  surface on every later turn, while its harness lists no `agentweave` server. The approver is
  named anyway, grounds or not. On 2.1.269 each such run dies at its first approval-needing call,
  which is F299, not this finding.
- **The Hub's own server failing on an agent with grounds.** The harness says `failed`, the Hub
  records nothing, and the run is told the MCP form. The operator's only sign is the harness's own
  text. The research measured Q4c (a missing server binary, with the approver named, over a pipe)
  as an exit 1 with *"MCP tool … not found. Available MCP tools: none"*. That shape under the PTY
  is **not measured**.

**What it would get wrong after F299's change.** That change gates the approver flag on the same
grounds (1b: *"same signal, same grain"*). It reads `init`'s status only to decide what counts as
a *test* of the harness (design D3), never to revoke grounds. D9 says so: *"Grounds are permanent
(research candidate 3) … This change inherits that unchanged."* D11 names the grounded agent whose
harness blocks the server later as the third kind of run its exception covers, and leaves it to
this finding. So once that change ships, a grounded agent keeps its approver after a block, and on
2.1.269 every later run dies at its first write. Deleting run history is the only way out.

**Why B.** It is a misleading surface today, the notice and the harness's report shown as prose,
plus an in-code claim that is false as measured. It would become A on the approver's side once
F299's change ships, and that is why it is filed now.

**What a repair would have to decide, not proposed.** Whether grounds should read the *latest*
test rather than *any* success. F299's change already adds `Run.harness_mcp_status`, which is the
signal a latest-test rule would need. A status string the Hub does not recognise must count as
"no grounds", never as grounds. Whether to recognise the stderr sentence as well, which is a vendor
shape the Hub does not version. And whether the Hub then names `hub_client: "cli"`
(`src/agentweave/config.py:714`) as the way out. That is a new decision: 1b chose *"same signal,
same grain"* (`DECISIONS.md:754`), and design D9 adds that *"a negative signal is a new decision"*. The "absent" row was measured with `--settings`,
not a real managed-settings file, so it needs one run under real managed settings before anything
depends on it.

**Reproduce:**
- Read `launchability.py:251-260` and `runner_parsing.py:242-371`.
- For the harness side, `py -3.11 scripts/drive/t_d4_0913_f299_slow_server.py S_0 S_crash` (each a
  separate invocation) and `py -3.11 scripts/drive/t_d2_0913_f299_harness.py A_hub --env plain`.
  Read `init_agentweave` in each.

**Foot 2026-10-01 (`a-run-reaches-the-hub-without-mcp`, drive group 9).** Fixed for Claude, Copilot and Codex
app-server runs that report their servers: `Run.harness_mcp_status` records each run's own test and the latest tested
run decides what the next is told. Driven on one Copilot agent: `connected` (9.2) -> `absent` under
`--disable-mcp-server agentweave` (9.3) -> `connected` again in the same, resumed conversation (9.5/9.6); and on Claude
with `deniedMcpServers`, whose `init` omits the server: `absent`, told `aw-tool` (9.7). Still open for Codex `exec`
and a Codex app-server run that reports nothing (no negative source; design D1).

## F763 (B) -- after the operator rejects a cannot-satisfy report, the task stays blocked and only the operator can move it, while the reporter is told to "try again" and the operator's page reads "all reviewed"

**Status:** open 2026-10-19. Found in the spec sweep (`scripts/drive/s1019_spec.py`, `s1019_spec_p2.py`, `s1019_spec_ui.py`, scratch Hub :8160; seeded running runs bound to each task stand in for the builder's turn), seen in a browser.
**Source:** drive
**Theme:** Spec documents
**Ready:** yes -- repro below; the fix is a choice between two options, recommendation given.
**Tier:** 1 (the capability specifies "rejecting keeps the task blocked": `spec-document-authority`, criterion `the-operator-answers-a-cannot-satisfy-report-respond-reject`)

A change with one task, approved; the task is assigned to `builder` and in progress. A run bound to it reports that `c-alpha` cannot be satisfied (201, `task_blocked: true`). The operator answers `reject` with "warm the cache in setup" (200, `task_unblocked: false`). The note queued to builder ends "...the task stays blocked. Their reason: warm the cache in setup Try again with that in mind, or report back what still stands in the way." (`spec_amendments._note_to_reporter`; the full stop after the reason is missing too). What the reporter can then do, measured with the same run's credential:
- `PATCH /agent-actions/tasks/{id} {"status":"in_progress"}` -> 403 "A task waiting on a person is released when the wait actually ends -- the operator answers or declines the question, or your own wait for it expires and ask_user reports that." (`hub/hub/api/v1/tasks.py:1719-1724`). That sentence is about `ask_user`, and here it is false: the operator *has* answered.
- `{"status":"completed"}` -> 409 "From 'blocked' the available transitions are: in_progress."
- Recording evidence works (201 awaiting), and so does reporting again (201). The task stays blocked either way.

On the operator's side, the task's `blocked_reason` still reads "cannot satisfy criterion c-alpha: cold cache". The spec page's Amendments panel reads **all reviewed**: "Answered: report rejected by operator ... Answer: warm the cache in setup". Nothing anywhere says the task now waits on the operator, so the work stalls until someone happens to open the task and move it.

**Fix shape (recommended):** a rejection returns the task to `in_progress` (the criterion stands as written, so keep working), and the note says so. **Alternative:** keep the task blocked, but rewrite `blocked_reason` to "report rejected -- waiting on the operator to unblock", show it on the panel as an open item, and make the agent's 403 name the cannot-satisfy wait instead of `ask_user`. Either way, the note and the task's state have to agree. Seam: Spec documents (cannot-satisfy) x Tasks.

## F787 (B) -- the first trigger of a new agent held the database write lock for over 30 s; every other Hub writer waited and the trace writer's insert failed `database is locked`

**Status:** open 2026-10-20. Found by the trace-hub-wide slice 1 drive (scratch Hub :8027). It happened once and was not reproduced.
**Source:** drive
**Theme:** Runs & runtime
**Ready:** no -- needs a repro; the measurements are below.
**Tier:** 0

The request span the new middleware recorded for `POST /api/v1/projects/{project_id}/agent/trigger` ran from 22:27:54.959 to 22:28:38.198 (43 s). That was the first turn of a freshly created Claude agent (`claude-haiku-4-5-20251001`) on a fresh project and profile. The run's root span starts at 22:28:37.943, so 43 s passed between the trigger arriving and the run starting. During that window, the span writer's one-row `INSERT INTO trace_spans` failed with `sqlite3.OperationalError: database is locked`, which only happens after the 30 s busy timeout (`SQLITE_BUSY_TIMEOUT_SECONDS`). So something held the write lock for at least 30 s while the trigger was in flight. The journal mode is `delete` (F627), so readers were blocked too.

Two later triggers of the same agent took 3 s each. A probe that tried `BEGIN IMMEDIATE` (then `ROLLBACK`) once a second throughout the second one found the lock free every time. So the hold is on a first-time path. Candidates, all unverified: tool-server pin or MCP registration on an agent's first run, and runner launchability checks. Any of them, run while a session has an uncommitted write open, would fit.

Expected: no request holds the write lock across a subprocess or a CLI's start. Repro to try: a fresh profile, `e2e.py setup`, `agent <p> a - claude claude-haiku-4-5-20251001`, then `turn` while `testbed`-style `BEGIN IMMEDIATE` probes run at 1 Hz. Any LOCKED sample longer than a second names the window, and a stack dump of the Hub (py-spy) at that moment names the holder. Since slice 1, the trace writer retries a batch the locked database refused (`traces.LOCKED_ATTEMPTS`), so this no longer loses spans. Seam: Runs (trigger) x the database.

## F788 (B) -- a run's permission wait polls its request about once a second, and every poll is recorded as an `aw.request` span: 60 spans per permission prompt, 90% of a project's request traces

**Status:** open 2026-10-20, waiting on the operator's decision `trace-5` (`spec-queue/DECISIONS.md`): the fix contradicts trace-D4's "all agent-credential" as decided, so slice 4 built it, then reverted it. Found by the trace-hub-wide slice 3 drive (scratch Hub :8027, `proj-9c510080c45f`).
**Source:** drive
**Theme:** Traces
**Ready:** no -- needs decision `trace-5`. The counts and the rule are below.
**Tier:** 0

Over four real Haiku turns with `acceptEdits` (8 permission prompts), the project recorded 537 `aw.request` spans. 480 of them are `GET /api/v1/agent-actions/permission-requests/{request_id}` with actor `run`: 60 per prompt. The tool server polls its pending request while it waits for the operator or the judge, and slice 1's rule (D3, `trace_requests._keep`) records **every** request made with a run credential, so each poll is kept forever (trace-D3). The operator's own polling is skipped by default for exactly this reason. The run's polling is the same kind of traffic and is not.

Expected: a run's routine read (a GET that answered 2xx, was fast and emitted no event) is not a span by default, like the operator's; `record_reads` turns both on. The wait itself is already recorded once, as the run's `aw.permission_wait` span. Keep recording a run's mutating, failing and slow requests and any request that emitted an event, as D3 and D5 already do. Test at the seam: `trace_requests._keep(method="GET", run_id="run-x", status=200, stream=False, elapsed=0.01)` must answer False. The existing test `test_a_runs_request_nests_under_its_open_tool_span` uses a POST, so it stays green. Re-drive: `d1020_hub_wide_trace_drive.py <project> work` should leave about 1/10 of today's request spans. Seam: Traces (requests) x the tool server's permission wait. This needs a design amendment: D3's "every request made with a run credential" becomes "every non-routine one".

## F938 (B) -- the Overview's Collaboration block is gone: `CollaborationSummary` has rendered nowhere since the ui-finesse rewire, while its 14 tests stay green and `hub-workspace-shell` still says the Overview MUST show it

**Status:** open 2026-10-22. Found by the day sweep `sweep-projects-sweep` (Chromium against the served bundle, scratch Hub :8119, profile pj1022, project `proj-52da8d2af5a9`; `scripts/drive/s1022_pj_ui.py general`).
**Source:** drive
**Theme:** Projects
**Ready:** yes
**Tier:** 0

Repro: open any project's Overview. The `main` text is "Nothing needs you · Nothing running · 0 tasks · $0.00 so far · 0 tokens · Ledger · Needs you · Running now · Recently finished · Agents ...". It has no "Collaboration", no "Hop budget" and no "Approval merges into" (all three `in main` were False). `grep -rn "<CollaborationSummary" hub/ui/src --include=*.tsx` finds only `__tests__/collaborationSummary.test.tsx`. `git log -S CollaborationSummary` shows that a8ca6e2 (ui-finesse, "every screen") dropped it from the Overview. Only `HOP_HELD_REASON` is still imported from the file (`AgentPostureChips.tsx:7`). Two current requirements in `spec/capabilities/hub-workspace-shell/spec.json` have no screen left: "The Overview MUST show a Collaboration block, above Attention, with the current value of: agents may start flows, hop budget, token budget, the branch approval merges into, the number of checks, the per-turn delivery cap, and agent budget ... each row MUST link to the control that edits it", and `the-overview-switches-agent-flows-in-place`. This is F190's class: the component's tests render it in isolation, so they pass while the operator can never see it. The approved mock (`hub/ui/mock/screens/Overview.tsx`) has no Collaboration block either. If dropping it was the operator's intent, the fix is to retire the two requirements. Nothing records that decision, so the spec stands. **Expected:** `OverviewScreen` renders `<CollaborationSummary onNavigate={onNavigate} />` again, in the place the spec names. **Test:** an `OverviewScreen` render test (not a `CollaborationSummary` one) finds the "Collaboration" heading and the hop-budget row. This fails today. Seam: Projects x Overview (the UI rewire).

## F939 (B) -- Project settings -> Quality can never show anything but "No quality governance configured", and it tells the operator to add a `quality:` section to `agentweave.yml`, a file nothing reads; a failed read shows the same empty state

**Status:** open 2026-10-22. Found by the day sweep `sweep-projects-sweep` (Chromium, scratch Hub :8119; `scripts/drive/s1022_pj_ui.py faults quality worktrees`).
**Source:** drive
**Theme:** Projects
**Ready:** yes
**Tier:** 0

Repro: open Project settings -> Quality. It reads "No quality governance configured. Add a quality: section to agentweave.yml to enable review gates, decision docs, and echo-chamber guard." `QualityHealthPanel.tsx:24-55` reads `quality` only from `GET /projects/{id}/session/sync`'s `data.quality`. Nothing the operator can reach writes that. `src/agentweave/config.py:7` says "DEAD (2026-09-20): the whole module. agentweave.yml is read and written by nothing live". `session.py:433-437` records that the CLI push path is gone and that `POST /session/sync` "keeps test callers". No settings field, route or CLI command sets `review_required`, `docs_threshold` or `echo_chamber_guard`. The only remaining reader is the turn context's "Quality Gates" block (`agents.py:2505`). So the advice is false, and the section is one of the nine on Project settings with no working control. A second problem: with `GET .../session/sync` answering 500 (Playwright `page.route`), the section renders the **same** "No quality governance configured" with no error and no Retry. This is F197's class, which the other seven sections already handle: Runners, Charters, Manager, Instructions, Budgets, Diagnostics and General each showed "... could not be read." with the Hub's reason and a Retry in the same drive. Worktrees, on a failed `GET /worktrees`, shows "Could not read this project's checkouts." (`OtherSettings.tsx:126`) with no reason and no Retry. **Expected (Tier 0):** the empty state stops naming `agentweave.yml` and says plainly that nothing configures quality gates yet. A failed read gets the named failure and Retry the other sections use, and so does Worktrees. Giving quality a real settings door, or removing the section, is a Tier 1 question for the operator, outside this fix. **Test:** `qualityHealthPanel.test.tsx` covers two cases. With a session-sync query in error, it expects "could not be read" and a Retry button. With empty data, it expects no `agentweave.yml` in the text. Both fail today. Seam: Projects x Quality (a configuration path deleted under a screen that still points at it).

## F954 (B) -- Jobs -> Run now toasts "fired — beta starts a turn now." when the Hub answered that the firing waits (`waiting_reason: "token budget exhausted"`)

**Status:** open 2026-10-22. Found by the day sweep `sweep-checkpoints-sweep` (Chromium, :8122; `s1022_ck_ui.py job -spent`, screenshot `testbed/ui-judge/s1022-ck-job/122114/job-run-spent.png`).
**Source:** drive
**Theme:** Jobs & loops
**Ready:** yes
**Tier:** 0

Repro: with the project's token budget spent, job `ping-beta` (agent beta, enabled, far-future cron) on the Jobs tab, Run now. `POST /jobs/job-96e2bab0ca74/run` -> 200 `{"success": true, …, "waiting_reason": "token budget exhausted"}`. The toast reads "**ping-beta fired** — beta starts a turn now." No run started: beta's entry stayed `queued`, "token budget exhausted". It ran (`run-28451b831d1f`) only 1.5 min later, when the limit was raised from Budgets. The job row said "Ran now ago · 1 fired", with nothing about the wait. F596 made the route answer `waiting_reason` for exactly this (no runner, CLI missing, budget), and no screen reads it. The pre-ui-finesse Jobs panel did not read it either.

Seam: `JobsScreen.tsx:81-85` ignores the response body. **Expected:** with `waiting_reason`, the toast says "ping-beta fired — waiting: token budget exhausted", in the composer's "Not started — <reason>" form (`AgentOutputPanel.tsx:1031`). **Test:** `JobsScreen` with a mocked run response carrying `waiting_reason` asserts the toast names it and does not say "starts a turn now".

## F955 (B) -- Checkpoint now is two browser requests: a reload while it says "Writing checkpoint…" leaves a paid, ready checkpoint nothing will ever cut over, and the checkpoint that is finally handed over records "No files recorded as changed"

**Status:** open 2026-10-22. Found by the day sweep `sweep-checkpoints-sweep` (Chromium, :8122; `s1022_ck_ui.py reload_mid`, `press_wait`, `sheet -stranded`).
**Source:** drive
**Theme:** Checkpoints
**Ready:** yes
**Tier:** 1

Repro: alpha's `conv-966fe9cf91e0`, past its 8,000-token threshold, under `offered`. Press the header **Checkpoint** and reload the page 3 s later, while it shows "Writing checkpoint…" (a press takes about 30 s: generation and probe). The Hub finishes: `ckpt-f62ff5fd96d8` is `ready`, probe `passed`, trigger `operator`, and `cut_over_to_conversation_id` is NULL. The conversation stays `open`, and its warning is cleared. The reloaded page offers nothing for the checkpoint, only "Checkpoint" again. The Checkpoints sheet lists it ("ready · operator · Probe: passed") with no Cut over. The same happened to `ckpt-06d65548418e` when the page was closed mid-press. The only way forward is another press, which pays for a third checkpoint (`ckpt-d3f414e72653`, cut over to `conv-da01bb95cfa4`). The two stranded ones cost 31,712 tokens, about $0.069 in Haiku. **And the handover is wrong:** each operator checkpoint chains on the newest (`previous_checkpoint_id`), so the one handed over covers no run (`covers_from_run_id` NULL) and has `files_changed: []`. The successor reads "No files recorded as changed", though alpha changed `src/calc.py` (the first, stranded checkpoint recorded it).

Seam: `checkpointOperationStore.ts:58-70` takes, then cuts over from the browser. `AgentOutputPanel.tsx:717-722` offers only `trigger === 'context_pressure'` checkpoints for cut over. F126 noted both points in passing in 2026-09 ("a reload between the 201 and the cutover"; "a checkpoint the operator generated on purpose is never offered one"), and nothing filed or decided them. **Expected:** an operator press survives a reload. Either the Hub does take-and-cut-over in one request, or the newest `ready` checkpoint with no successor and no later run is offered for Cut over whatever its trigger. A checkpoint's span and `files_changed` run from the last checkpoint that was handed over, not from one that never was. Two seams (UI offer, Hub chaining), so Tier 1. **Acceptance drive:** press, reload mid-write. The page offers Cut over for that checkpoint, and the successor's checkpoint lists `src/calc.py`.

## F1033 (B) -- Settings → General's "Default permissions" option says "Claude and Codex: Workspace only. Copilot: Ask me.", but Codex runs at Edit files and Copilot at Workspace only

**Status:** open 2026-10-22. Found while writing the permission-postures docs page (docs rework, `df23b58`), by comparing the UI label with the runner adapters.
**Source:** code
**Theme:** Permissions & sandbox
**Ready:** yes
**Tier:** 0

The unset option of the Default permissions select is labelled `'Claude and Codex: Workspace only. Copilot: Ask me.'` (`hub/ui/src/components/settings/GeneralSettings.tsx:206`). What a run actually gets with no posture is each adapter's `posture_at_rest`: Claude → `workspace` (`runner_commands.claude_posture_at_rest`), Codex → `acceptEdits`, i.e. Edit files (`hub/hub/runner_adapters/codex.py:279-282`), Copilot → `workspace` (`hub/hub/runner_adapters/copilot.py:289-294`, `copilot_acp.posture_for(None)` returns `workspace`, measured). Two of the three claims are wrong, and the Codex one understates what an agent may do. **Expected:** the label is derived from the adapters (or the permission-modes route returns each runner's at-rest posture) rather than hand-written. **Test:** a UI test that the unset option's text names each runner's at-rest posture as the modes route reports it (fails today on Codex and Copilot).

## F959 (B) -- a second `agentweave --profile <p> --port <m>` while the profile's Hub runs on another port starts a second Hub on the same database: every job fires twice, and the newcomer's startup fails the first Hub's live firing

**Status:** open 2026-10-23. Found by the day sweep `sweep-vault-sweep` (throwaway profile `vs1023`, Hubs started by the CLI itself on :8150 and :8151; the profile was reset after).
**Source:** drive
**Theme:** CLI & lifecycle
**Ready:** yes
**Tier:** 0

Repro: from `testbed/cli1023`, `agentweave --profile vs1023 --port 8150` (Hub A, PID file `hub-vs1023-8150.pid`). Then `agentweave --profile vs1023 --port 8151` -> a second Hub starts, `hub-vs1023-8151.pid`, both answering `/health`, both on `~/.agentweave/hub/profiles/vs1023/agentweave.db` (same `instance_identity.json`). Nothing refuses or warns. Then on A, an agent `idle` with its runner unbound and `POST /projects/{p}/jobs {"name":"twice","agent":"idle","message":"tick","cron":"* * * * *"}`; restart B so its scheduler loads the job. `job_runs` for the job: **08:35:00.016 and 08:35:00.019, 08:36:00.017 and 08:36:00.019** — two firings per tick, each in its own new conversation (5 conversations for `idle` in 3 minutes). B's startup `reconcile_stale_job_runs` also marked A's in-flight 08:34 firing `failed` "Reconciled on Hub start: no live run behind this firing". With a runner bound, each tick would be two paid turns. What held: B's `reconcile_interrupted_runs` left A's live run alone (it checks the PID), a turn for a busy agent through B was queued ("agent is already running") and drained once, and disabling the job on A stopped both Hubs firing (the enabled flag is read at fire time).

The CLI comment at `cli.py:1271` names exactly this trap ("two SQLite writers shared one file") as what profiles were for, but `_hub_native_start` checks only *this port's* health (`:1245`) and *this port's* stale PID (`_hub_pid_running(port, profile)`). `_hub_pid_files_of(profile)` (`:593`) already lists the profile's other PID files. **Expected:** a start whose profile has a live Hub on another port refuses, naming it: "Profile 'vs1023' is already served on port 8150 (PID 7396). Open that one, or stop it first: agentweave --profile vs1023 --port 8150 stop" (exit 1), and does not start a process. **Test:** `tests/test_cli.py`: with a `hub-vs1023-8150.pid` naming a live PID, `cmd_hub_start(--profile vs1023 --port 8151)` returns 1 and never calls `Popen` (fails today: it spawns).

## F960 (B) -- the vault-reports job is shown only the first 50,000 characters of a fact's source, so a correct fact from further in is referred with "the source does not contain" it, and the fact turns disputed

**Status:** open 2026-10-23. Found by the day sweep `sweep-vault-sweep` (scratch Hub :8150, profile `vs1023`, `scripts/drive/s1023_vault.py`, Chromium `s1023_vault_ui.py`, shot `testbed/ui-judge/s1023-vault/094616/01_reports.png`).
**Source:** drive
**Theme:** Knowledge vault
**Ready:** yes
**Tier:** 0

Repro: a 70,041-character `note` source `ops-handbook` whose line 405 (char ~61,000) reads "The on-call pager escalation timeout is 17 minutes, set by Ines Carvalho." Distillation (Haiku) stores `fct-4b28a2236fec` "The on-call pager escalation timeout is 17 minutes.", citing `src-33cefa5f852e` lines 405-405 (F682's fix holds: both pieces distilled). An agent turn files `vault_report(fct-4b28a2236fec, "This fact is incomplete. … set by Ines Carvalho; the fact should name her.")`. The `vault-reports` firing answers **referred**: "The source provided (Operations handbook) does not contain any information about a 17-minute pager escalation timeout, Ines Carvalho, or pager escalation settings. … The entry cites a different source identifier (src-33cefa5f852e, line 405) than the one provided for verification." The fact now reads `disputed: true`, and the Vault → Reports card shows that sentence as "Referred to you". The same report on a short source (`backup-note`) came back **corrected** with a new fact superseding the old one, so the outcome depends only on where in the source the fact sits.

Seam: `vault_reports._review` (`hub/hub/vault_reports.py:282`) passes `text[:SOURCE_CHARS]` whatever the fact's citations say; the archived change `a-working-agent-tells-the-manager-an-entry-is-wrong` states "the text of its first cited source up to 50,000 characters", so the requirement wording is part of the gap. `POST /vault/reports/{id}/review` takes the same path. A referred report cannot be looked into again (409 "is referred, not pending"), so the fix does not repair reports already referred. **Expected:** for a fact, the worker sees a window of at most `SOURCE_CHARS` that contains its cited lines (centred on `line_start..line_end`, the window's first line number stated in the prompt so located quotes still map), and the capability requirement says "the part of its first cited source holding the cited lines, up to 50,000 characters" (amend it through the Hub). **Test:** `hub/tests/test_vault_reports.py`: a source of 70,000 characters with the cited line past 60,000; the faked `run_worker` asserts the prompt contains the cited line (fails today: the prompt holds only the first 50,000 characters).

## F961 (B) -- the Activity tab's Ledger counts a Copilot turn's AI credits and an unpriced turn as $0.00: a Copilot-only project reads "Spent $0.00 · Nothing was spent yet", and the agent and task that spent 5.51 AI credits read "$0.00"

**Status:** open 2026-10-23. Found by the day sweep `sweep-checkpoints-sweep` (scratch Hub :8112, profile `ck1023`, `scripts/drive/s1023_ck_setup.py`, `s1023_ck_ui.py ledger|overview|story`, shots `testbed/ui-judge/s1023-ck-ledger/100304/ledger.png`, `s1023-ck-overview/100250/`).
**Source:** drive
**Theme:** Accounting & allowance
**Ready:** yes
**Tier:** 0

Repro: a project whose only spend is Copilot. Agent `copr` on a real Copilot runner (`cli: copilot`, `model: claude-haiku-4.5`), task `task-3d674922843e` "Fix add() in src/calc.py" assigned to it, one turn with `task_id`. `turn_usage`: 110,288 tokens, `api_equivalent_usd_micros` NULL, `ai_nano_aiu` 5,507,540,000, `premium_requests` 0.33. Plus Copilot provider-runner turns (stub, no cost reported). Every other surface says what was spent. The task drawer reads "Cost 5.51 AI credits · 0.33 req" with the run row "copr worked · claude-haiku-4.5 · 5.51 AI credits". The Overview line (F952's fix) reads "5.51 AI credits so far · 262.3M tokens". Budgets reads "copr 5.51 AI credits · 0.33 premium requests · 110.3K tokens". The **Ledger** (Activity → Ledger, `GET /projects/{p}/ledger`) reads "Spent **$0.00** · 262.3M tokens", "Spend by day: **Nothing was spent yet.**", By agent "copbig $0.00 · copr $0.00 · cop $0.00", and By task "Fix add() in src/calc.py **$0.00**". After two Haiku agents and a checkpoint added $0.29, the line became "Spend by day $0.29" with copr and its task still "$0.00", ranked below the priced agents. So the Ledger contradicts the task story for the same task, and the "dash, not $0.00, for an unpriced agent" rule F952 set holds on Overview and Budgets but not here.

Seam: `project_ledger.py:128-191` sums `api_equivalent_usd_micros or 0` alone, so a NULL cost is 0 and credits are dropped. `spend` carries no `ai_nano_aiu`, `premium_requests` or unpriced count at any level. `ProjectLedger.tsx` renders `money()` of those numbers (`:248`, `:286`, `:299`), and `SpendByDay` returns "Nothing was spent yet." whenever the largest day's `usd` is 0 (`:60-61`), whatever the tokens. F952 noted that the ledger has no credits field, but fixed only the Overview line by reading `/accounting`. **Expected:** the ledger's total, each day, each agent and each task carry credits and premium requests (summed from `turn_usage` / `worker_invocations`), plus an unpriced-turn count beside `usd`. The view shows credits where a row has them, "—" for a row with no priced turn and no credits, and "N turns unpriced" beside a partly priced total. A day with tokens but no dollars is not "Nothing was spent". **Test:** `hub/tests/test_project_ledger.py`: a project with one Copilot turn (`ai_nano_aiu` 5.5e9, cost NULL) on a task, where `by_agent[0]` and `by_task[0]` carry the credits and `unpriced_turns: 1`. This fails today, since the keys are absent. Also a `ProjectLedger` render test fed that payload, in the field order the route returns, that renders "5.51 AI credits" for the agent and does not render "Nothing was spent yet."

## F963 (B) -- an agent with no tool server whose *own* default is "Ask me" (or "Workspace only") shows that posture on its composer pill, its settings row and the Overview, while every run it starts gets "Edit files": an operator who chose Ask me watches it write without asking

**Status:** open 2026-10-23. Found by the day sweep `sweep-reach-sweep` (scratch Hub :8113, profile `rc1023`, project `proj-421826485996`; Chromium against the served bundle, `scripts/drive/s1023_rc_ui.py` and `s1023_rc_ui_send.py`; shots `testbed/ui-judge/s1023-reach/104652/`, `testbed/ui-judge/s1023-reach-send/104754/01_after_send.png`).
**Source:** drive
**Theme:** Permissions & sandbox
**Ready:** yes
**Tier:** 0

Repro: agent beta on a Claude Haiku runner with `config.hub_client: "cli"`, so it has no tool server and no approver. Open beta → settings → Execution → Permissions → **Default permissions for beta** → **Ask me**. `PATCH /agents/beta {"default_permission_mode": "manual"}` → 200. The row now reads "Ask me" with the note "Claude Code still runs commands it treats as read-only (such as echo or git status) without asking; writes and other commands come to you." `GET /agents` says beta `default_permission_mode: "manual"`, `permission_mode_at_rest: "acceptEdits"`, `permission_mode_built_in: "acceptEdits"`. That is F933's fix (89ce56a) working: an inherited default that needs an approver is skipped for a run with none. Open beta's conversation: the composer reads "Permissions: Ask me". From that composer, with the pill untouched, send "Use your Write tool to create the file pill-check.txt containing the word hi …" (`run-253b446d2409`). The file is written in beta's worktree, `GET /permission-requests` has nothing for the run, no card appears, and beta replies "File written successfully to pill-check.txt." The pill still reads "Ask me" afterwards. With `default_permission_mode: "workspace"` the roster is likewise `acceptEdits`, while every screen says Workspace only (roster measured; not sent from the composer). A project default does not show the mismatch, because the agent's own field stays null, and the pill then reads `permission_mode_at_rest`, which is right.

Cause: `postureAtRest` (`hub/ui/src/api/agents.ts:733-736`) reads `agentRow.default_permission_mode ?? agentRow.permission_mode_at_rest`, preferring the agent's own field over the Hub's resolved one. Before F933 the two always agreed whenever the field was set. Since F933, `permission_mode_at_rest` is the only truthful value. The same assumption sits in `AgentPostureChips.tsx:125`, the Overview's agent details (`posture = agent.default_permission_mode ? labelFor(...) : "Built-in default (...)"`), and in `AgentSettingsPage.tsx:267-274`, whose Ask-me note promises "writes and other commands come to you". Nothing on the settings row says the choice does not apply to this agent. **Expected:** the pill and the Overview show `permission_mode_at_rest`. Where the agent's own default differs from it, the settings row says why, e.g. "Ask me needs an approver, and beta has no tool server (Hub client: command line), so its runs get Edit files". The Ask-me note is not shown for such an agent. Offering the choice is fine (the Hub stores it and applies it once the agent has a tool server). **Test:** in `hub/ui/src/__tests__/`, `postureAtRest({default_permission_mode: 'manual', permission_mode_at_rest: 'acceptEdits'})` → `{permission_mode: 'acceptEdits'}`. This fails today. Seam: Permissions & sandbox (composer pill, agent settings, Overview) x the roster's resolved posture.

## F964 (B) -- the operator's answer to a cannot-satisfy report is delivered into the reporter's most recently active conversation, not the one that reported, and unbound to the task: after a reject the reporter cannot report again (403), and after an accept it does the task's work on its own branch instead of the task's checkout

**Status:** open 2026-10-23. Found by the day sweep `sweep-spec-sweep` (scratch Hub :8114, profile `sp1023`, project `proj-5d1a4f5172a6`; seven real Haiku 4.5 turns; `scripts/drive/s1023_sp_setup.py`).
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

Repro. builder (claude-haiku-4-5) has two open conversations. In the first, `conv-7b98d1151605` (operator origin, no task), it ran an unrelated turn on another document. The second, `conv-01652c671291`, is bound to `task-ddc3099981de` of approved change `spec/changes/sp-report/spec.json`. There, `run-f6f10aa6c8bd` called `report_cannot_satisfy` for both criteria, giving `amd-20bce705688a` (c-fast, `task_blocked: true`) and `amd-bbfa905afd09` (c-tiny). The operator then sends one message in the older conversation (`run-421d3ab958bb`, "reply OK"), which makes it the more recently updated one. Next, `POST /projects/{p}/project/documents/spec/changes/sp-report/spec.json/amendments/amd-20bce705688a/respond {"response":"reject","reason":"Measure it on a 1 KB string instead …"}` → 200. The note is queued as `entry-9221d9f18b94` with `conversation_id: conv-7b98d1151605, task_id: null`, and it starts `run-8c0cb4d9ab69` there with `task_id: None`. Following the note ("Try again …, or report back what still stands in the way"), builder calls `report_cannot_satisfy` (c-fast) → **403 "only a run working or testing a task of this document may report a criterion it cannot satisfy"**. Its `update_task` to `in_progress` → 403 (F965), and it ends asking in prose. Then `respond` on `amd-bbfa905afd09 {"response":"accept"}` → 200 `task_unblocked: true`, and the task goes `in_progress`. That note is also queued into `conv-7b98d1151605` (`entry-db196a204021`, `task_id: null`), and `run-a33e299337a9` runs unbound. builder edits `textkit/words.py` in **its agent worktree** (`.agentweave/worktrees/builder`, commit `c12f68c` "Auto-snapshot: builder's turn" on `agentweave/builder`). The task's checkout `.agentweave/tasks/task-ddc3099981de` stays clean at `a03ac52`. It records `ev-0c331fe27de8` with `task_id: task-ddc3099981de`, `run_id: run-a33e299337a9`, and ends without completing the task. 10-20's drive did not show this because the reporter had only one conversation.

Cause: `spec_amendments.queue_note_to_reporter` (`hub/hub/spec_amendments.py:868`) picks `conversations.latest_open_conversation(agent)`, ordered by `updated_at` (`conversations.py:215`), and builds the entry with no `task_id`. The report itself records `run_id` (`amendment.run_id`, here `run-f6f10aa6c8bd`), whose conversation is the bound one. **Expected:** the note goes into the reporting run's conversation (`runs.conversation_id` of the report's `run_id`), falling back to the latest open one only when that conversation is archived, and the entry carries the report's `task_id`. The turn the answer starts is then bound to the task: its checkout, `report_cannot_satisfy`, evidence. **Test** (`hub/tests/`, beside the F700 respond tests): a reporter with two open conversations, the reporting one older and bound to the task. `respond` reject → the queued entry's `conversation_id` is the reporting conversation and its `task_id` the report's task. This fails today. Seam: Spec documents (report answer) x Inbound queue x Worktrees.

## F967 (B) -- an agent's evidence whose locator names its test file watches only that test file, so reverting the implementation on the main line raises no drift: the requirement keeps reading "verified" while its own named test fails

**Status:** open 2026-10-23. Found by the day sweep `sweep-evidence-sweep` (scratch Hub :8115, profile `ev1023`, project `proj-563f2775ab60`; `scripts/drive/s1023_ev_setup.py`).
**Source:** drive
**Theme:** Drift
**Ready:** yes
**Tier:** 1

Repro. builder (claude-haiku-4-5, `run-30bb84be135f`) fixed `textkit/words.py` (`split(' ')` → `split()`) and added tests in one commit, `fad8fee` on `agentweave/task/task-a2cf84a08020`. It recorded `ev-70160b95bae5` for FR-2 ("count_words MUST return 0 for an empty or blank string") with `locator: "tests/test_words.py::test_empty_string and tests/test_words.py::test_blank_string"`. The evidence was accepted, and Land merged the task (`dfff3d4`). Its footprint `efp-7cd33520c87f` has `entries: {"tests/test_words.py": …}` and `watched_from: ["locator"]`, so `textkit/words.py` is not watched. On master, commit a revert of the fix in `textkit/words.py` only. `py -3.11 -m pytest tests -q` → **2 failed** (test_empty_string, test_blank_string). `POST /projects/{p}/project/spec/drift/detect` → `{"raised": [], "rebuilt": 0}`, and `GET /spec/coverage` still reads FR-1 and FR-2 `verified`, `integrated`. Touching `tests/test_words.py` alone (a comment line) raises drift on both. So the scan watches the proof and not the thing proved. Neither the drift panel nor the Evidence view says what a piece watches (`spec-drift-unwatched` lists only pieces watching nothing), so the operator cannot see the gap.

Cause: deliberate. `requirement_evidence.watched_files` (`hub/hub/requirement_evidence.py:938`) takes "the **first** source that names a file … not their union": a locator naming any file wins over the branch's changes. This narrowing came after `drift-watches-the-files-its-evidence-is-about` D1, which specified a union, because on `:8000` a union made 22 of 46 agent rows watch a shared file. The narrowing fixed noise, and the price is this blind spot whenever an agent's locator is its test (the shape the MCP tool's own example invites, `mcp_server.py` `record_evidence`). A design gap, not a slip, hence Tier 1. Options for the change: (a) when every locator path is a test file (`tests/`, `test_*`, `*_test.*`, `*.test.*`), add the branch's non-test changes (rule 3) to it; (b) at least name the watched paths on the evidence card and the drift strip, so a test-only watch is visible. **Acceptance drive:** this repro, where the implementation-only revert on master raises a candidate for FR-2 and the test-only touch still raises one. Seam: Requirements, evidence & coverage (record) x Drift (scan).

## F968 (B) -- a granted agent rejecting an awaiting piece of a *completed* task leaves the task completed and tells its author nothing: the reason the tool says "is what the author reads to fix it" reaches nobody

**Status:** open 2026-10-23. Found by the day sweep `sweep-evidence-sweep` (scratch Hub :8115; `run-1fea7e495c79`, a real Haiku 4.5 turn by `checker`, granted `can_accept_evidence`).
**Source:** drive
**Theme:** Requirements, evidence & coverage
**Ready:** yes
**Tier:** 1

Repro: `task-a2cf84a08020` is `completed` by builder, with awaiting evidence for FR-1 and FR-2. checker, granted with `PATCH /projects/{p}/agents/checker {"can_accept_evidence": true}`, is not dispatched as a reviewer; it is asked to review evidence in an ordinary turn. It calls `list_evidence(review_state="awaiting")`, then `decide_evidence(ev-40cc02c9763c, accepted, …)` → 200 and `decide_evidence(ev-70160b95bae5, rejected, "the criterion also needs a test of a tab-only string; record it again with that test")` → 200. Afterwards: `inbound_queue_entries` holds no entry for builder (only the operator's two prompts); the task stays `completed` (`has_rejected_evidence: true`); nothing starts a builder turn. The only party who learns of it is the operator, from the Spec header ("1 rejected") and later from Land's 409 `gate_unsatisfied`, whose sentence tells *a reviewer* to "move the task to revision_needed with notes naming the rejected requirement". The `decide_evidence` docstring (`hub/hub/mcp_server.py:5514`) promises the reason "is what the author reads to fix it". The author reads it only if somebody moves the task to `revision_needed`: the F504 fix lists rejected pieces with their reasons on that turn. The decide answer does not tell the deciding agent that this step is needed. Cause: neither decide route (`hub/hub/api/v1/agent_actions.py:1679`, operator `spec.py:1777`) does anything for a rejected piece of a task that is not `approved` (`_reopen_an_approved_task` handles approved only). **Expected (the change chooses one):** a rejection of a completed task's awaiting evidence either moves the task to `revision_needed` with the reason as its note (the operator path already reopens an approved task, vis-D1), or queues the reason to the author bound to the task. Either way the decide answer says which happened. **Acceptance drive:** this repro, where after the reject builder gets a turn bound to the task carrying the reason, or the task reads `revision_needed`. Seam: Requirements, evidence & coverage (agent decision) x Tasks x Inbound queue.

## F970 (B) -- a *loop* job whose agent a session sync deleted (or the operator archived) answers Run now with 500 "Failed to fire job", and every firing emits a `job_run_failed` event naming a job_run_id that has no row

**Status:** open 2026-10-23. F925's fix (0f2771e) holds for plain jobs only. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8111, profile `la1023`, project `proj-655cbdd8ca29`; `scripts/drive/s1023_la_f925.py`, `s1023_la_loops.py`).
**Source:** drive
**Theme:** Jobs & loops
**Ready:** yes
**Tier:** 0

Repro: two enabled loop jobs (`initial_tasks` with one task, far-future cron), `gone1 loop` for agent gone1 and `arch1 loop` for arch1. `POST /session/sync {"data":{"agents":{"alpha":{},"arch1":{}}}}` → gone1 removed; `POST /agents/arch1/archive` → 200. `POST /jobs/job-2cc35804fe0a/run` → **500 `{"detail":"Failed to fire job"}`**, the same on a second press and for arch1's loop. `GET /jobs/{id}/history` → `[]`; `job_runs` has no row for either loop, but `event_logs` has `job_run_failed` events naming `run-008137496f71`, `run-9f475933ba06`, … that do not exist. On cron `* * * * *` a new event with a new id was written at 11:00, 11:01 and 11:02, still with no row; the plain job beside it counted into one row (`tick_count` 5). Queue and conversations stayed clean. The 500 sentence reaches the Jobs screen and an agent's `run_job` alike ("(500): Failed to fire job", run-17fa via MCP). Plain jobs on the same agents: enable → 400 with the create's sentence, Run now → 409 with the trigger's sentence, one `failed` row + `job_run_failed`, nothing queued (F925 holds there).

Cause: in the loop branch the SELECT inside `agent_unfirable_reason` (`hub/hub/scheduler.py:4041-4049`) autoflushes the `JobRun` built above it; `_discard_unused_run` (`scheduler.py:1116`) then `session.delete(run)`s it. The `except` at `scheduler.py:4274` (`run if "run" in locals() and run in session`) still finds the deleted object, stamps it `failed`, persists the event naming it, and the commit deletes the row. `run_job` sees no new row, `_loop_flow_busy_refusal` / `_loop_in_flight_decision` return None, and it answers 500 at `hub/hub/api/v1/jobs.py:1908`. **Expected:** as for a plain job: one `failed` row whose id the event names, cron ticks counting into it, and the press answering 409 with "gone1 is not an agent in this project…" / "arch1 is archived…". Optional (F925's design note, still not done): the sync and archive answers name the jobs left naming the agent; the Jobs rows still read "Active · Next: Jan 1 2027". **Test:** `hub/tests/test_a_job_for_a_vanished_agent_does_not_fire.py` fires plain jobs only: add a job with `initial_tasks` → press 409 with the sentence, `JobRun` count 1 with the event's `job_run_id`, a second tick increments `tick_count`. Seam: Agents (sync/archive) x Jobs & loops (loop firing).

## F976 (B) -- a tester's own `change_criterion` amendment makes the builder's evidence stale, so the tester's approval is refused, and every remedy offered to the tester and the operator is one the Hub then refuses

**Status:** open 2026-10-23. Extends F758 (the gate's remedy for a stale piece is refused) at the seam where it fires on every tester criterion fix. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8112, profile `lb1023`, project `proj-ea9d9171917e`, real Haiku 4.5; `scripts/drive/s1023_lb_flow.py`, `s1023_lb_hold.py`).
**Source:** drive
**Theme:** Flows & review
**Ready:** yes
**Tier:** 1

Repro: flow document `delivery {"mode":"flow","agent":"alpha","tester":"tester"}`; task `t-slug`; criterion `c-slug` deliberately wrong (`slugify('  Hello,  World! ') == 'hello--world'`). beta's rework records `ev-83ff5ed0fcae` at `9877b026`. Review turn `run-573d56ff11e9` is briefed "**Your verdict decides this task's evidence** (`ev-83ff5ed0fcae` for `FR-2` at `9877b026baa9`). Approving accepts it and merges the work". The tester runs the `how_to_check`, gets `'hello-world'`, and calls `amend_spec_document op=change_criterion` (`amd-a3ad1918556b`) → revision `sprev-f470d3396bfc` (`reworded`, actor tester); FR-2's digest changes. Then `update_task approved` → 409 `gate_unsatisfied` three times ("This task's work has been recorded and nobody has judged it: FR-2 at 9877b026baa9 … accept the evidence, or grant an agent the capability to accept it — both are the operator's"); `record_evidence` → 409 ("a reviewer judges the evidence the task's author recorded"); `decide_evidence` → 403; `ask_user` `q-b0951e26759f` times out. The operator is told (divergence `div-67fb88d5aa14`) the review "ended without recording a verdict … naming a different reviewer, reviewing it yourself, or asking this one again is the way forward", and the loop's stall reason says "Ask tester again, review it yourself, or send it back". Following it: `PATCH /tasks/task-a1499b2857e6 {"status":"approved"}` → the same 409 ("accept the evidence"); `POST /project/spec/evidence/ev-83ff5ed0fcae/decision {"decision":"accepted"}` → 409 `evidence_stale`. Only send-back → builder re-records (`run-93aa17ce491b`) → a fresh tester review (`run-12f4e4dd6d53`) landed it: two extra paid turns. On screen the drawer story ends "tester's turn ended with the task still under review · surfaced" with no reason (`run_divergences` has no reason column); the piece reads plain "awaiting", not stale.

Cause: `requirement_evidence.decide_with_verdict` skips a stale piece when accepting (`hub/hub/requirement_evidence.py` ~1415-1418, the F751 fix); `requirement_gate._operator_only_remedy` (`hub/hub/requirement_gate.py:1286-1289`) treats the task's own pieces as never the operator's hold, so `approval_held_for_operator` returns None and the divergence says "ended without recording a verdict" instead of the gate's sentence; `review_turn.verdict_evidence_sentence` (`hub/hub/review_turn.py:339`) promises "Approving accepts it" whether or not the piece is stale. **Expected:** once a review run's own amendment makes the reviewed piece stale, its approve refusal (and the amendment's tool answer) names the piece as stale and gives `revision_needed` as the remedy so the author re-records; the divergence and stall reason carry the gate's sentence; the drawer marks the piece stale. **Acceptance drive:** this repro, where the tester's approve is answered with the stale sentence and `revision_needed` lands without the operator. **Test:** `hub/tests/test_the_reviewers_verdict_decides_the_tasks_evidence.py`: a review run amends the criterion, then approves → refusal naming staleness with `revision_needed` as the remedy; `run_diverged` reason carries the gate's sentence. Seam: Flows & review (tester turn) x Requirements, evidence & coverage (stale).

## F979 (B) -- when a project's own `.git` is unreadable and its folder sits inside another repository, the Hub uses the enclosing repository: it creates the agent's worktree and branch there and commits to it

**Status:** open 2026-10-23. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8113, profile `lc1023`, projects `proj-486861916a9d`, `proj-e35fc30d0076`; `scripts/drive/s1023_lc_fault.py`).
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** yes
**Tier:** 1

Repro: an outer repo `~/Documents/lc1023outer` (branch `main`, holding `OUTER.md`) containing a project repo `inner/`. Open `inner` as a project, create agent gamma (Haiku), write `garbage` into `inner/.git/HEAD`. `GET /worktrees` → 200 `{"repository": true, "unavailable_reason": null}`. `POST /agent/trigger` gamma → 200, `run-8ca5ab556815` completed with `workspace_dir=inner\.agentweave\worktrees\gamma`. Effect: `git -C lc1023outer worktree list` shows `inner/.agentweave/worktrees/gamma [agentweave/gamma]`; the agent's checkout holds `OUTER.md` (the wrong code), and the outer repo's branch has `e3dd480 AgentWeave "Auto-snapshot: gamma's turn"` adding `.agentweave/context/gamma.md`. Moving `inner/.git` aside entirely does the same, and `/worktrees` lists the outer repo's worktree as this project's. After HEAD is restored the next trigger is held with a legible reason ("refusing existing path … not the registered git worktree … `rm -r …`"), but following it, or deleting the project (204), leaves the outer repo's worktree registration, branch and commit behind. A project under `testbed/` inside this repository is exposed the same way (the subagent's first try resolved the AgentWeave repo; nothing was written there, checked with `git status` and the branch list).

Cause: `is_git_repo` (`hub/hub/worktrees.py:126-145`) runs `git rev-parse --is-inside-work-tree` with `cwd=project`, which answers true inside any enclosing repository; callers include `hub/hub/api/v1/agent_trigger.py:1290`, `hub/hub/api/v1/worktrees.py:161` and the same probe in `hub/hub/task_integration.py:170` (`repository_fault`). Workspace-isolation D2 notes git "answers about the enclosing repository", but only for checkouts. **Expected:** a project root counts as a repository only when `git rev-parse --show-toplevel` resolves to that root; otherwise it reads "not a git repository" with git's own error, a writing agent fails closed, and nothing is ever written to another repository. **Acceptance drive:** this repro → trigger held or refused naming the project's `.git`, outer repo unchanged (`worktree list`, branches). **Test:** `hub/tests/test_worktrees.py`: tmp outer repo, inner dir with garbage `.git/HEAD` → `is_git_repo(inner)` False and agent-worktree provisioning refuses. Seam: Projects x Worktrees x Resilience.

## F986 (B) -- an answer to a question whose asking run has ended is delivered into the agent's most recently active conversation, not the one the question was asked in

**Status:** open 2026-10-23. Found by the day sweep `sweep-questions-sweep` (scratch Hub :8116, profile qa1023, `proj-4f66170b9633`, `scripts/drive/s1023_qa_drive.py`).
**Source:** drive
**Theme:** Questions
**Ready:** yes
**Tier:** 0

`gamma` (Haiku 4.5) asked `q-c89789c5f0a3` in `conv-0f96dd45a214`; that run (`run-c826abe6cd14`) was stopped. gamma then ran in a newer conversation `conv-2599b9f224f8`. `PATCH /projects/{p}/questions/q-c89789c5f0a3 {"answer":"maybe next week","labels":["maybe"]}` -> 200; `inbound_queue_entries` row `entry-b772aa7b17cf` has `conversation_id` = `conv-2599b9f224f8` ("Question: Rename the module to utils?\n\nAnswer: maybe next week") and was delivered in `run-7aeb3da3fcbd` there. The question's own `conversation_id` is `conv-0f96dd45a214`. Since F804 the ask card shows only in the asking conversation, so the operator answers there and the turn runs somewhere else.

Cause (verified): `deliver_batch_if_complete` (`hub/hub/api/v1/questions.py:164`) picks `latest_open_conversation(...)`, ordered by `updated_at` (`hub/hub/conversations.py:203-217`), ignoring `question.conversation_id`; answer, decline and the expiry report all go through it. Same pattern as F964 (cannot-satisfy replies) -- fix with one helper if it fits.

**Expected:** deliver into `question.conversation_id` while it is open; fall back to the latest open conversation only when it is archived or null. **Test:** beside `hub/tests/test_a_question_names_its_conversation.py`: an agent with two open conversations, the question asked in the older one, its asking run ended; answering queues an entry whose `conversation_id` is the question's. Fails today. Seam: Questions x Inbound queue x Conversations.

## F995 (B) -- the run-text redaction joins a Claude turn's separate thinking and text blocks as one string: a value split across two replies is not redacted when the model thinks between them, and the ordinary word opening the next block after an `aw_live_`-shaped token is replaced by `<redacted>`

**Status:** open 2026-10-23. Found by the day sweep `sweep-traces-sweep` (Logs row; scratch Hub :8119, profile ev1023, `scripts/drive/s1023_ev_sse_secret.py`).
**Source:** drive
**Theme:** Logs, events & SSE
**Ready:** yes
**Tier:** 2 -- secrets (CLAUDE.md's table). Hazard: the redaction floor itself; no migration, rows already stored keep what they hold.

A Haiku turn (`run-f44cb8dee387`) was asked to say `Channel prefix aw_live_`, run `echo one`, say `Q7xP2mK4R9sT is the channel. Notes are in C:\Users\...\README.md`, run `echo two`, say `Second channel aw_live_N4bV6`, run `echo three`, say `Finished cleanly.` (whole fake keys were refused by Haiku). `agent_outputs`:

```
 2 text      "Channel prefix aw_live_"
 5 thinking  "<redacted>, echo one completed. Now I need to say the text for step 3."
 6 text      "Q7xP2mK4R9sT is the channel. Notes are in C:\Users\huida\Documents\aw-ev1023\README.md"
 9 thinking  "Good, echo two completed. Now step 5: say the text."
10 text      "Second channel <redacted>"
13 thinking  "<redacted> the tool calls are done. Now the final step: say \"Finished cleanly.\""
```

Seq 2 + seq 6 read `aw_live_` + `Q7xP2mK4R9sT` verbatim, the F488/F602 split guarantee broken; ordinary words opening seq 5 ("Good") and seq 13 were redacted instead. Paths were correctly kept.

Cause (verified): `scrub_stream` (`hub/hub/run_secrets.py:137-195`) carries one tail per run across both `STREAM_KINDS` (`:37`, text and thinking), strips whitespace at the boundary (`:153`, `:168`) and joins, so the dangling half of a text block is consumed by the next *thinking* block and joined with its first word, which is redacted; the next text block starts from a tail no longer ending in `aw_live_` (`:188`). Claude almost always thinks after a tool result, so for Claude text the split guarantee rarely holds. The boundary join was designed for Copilot's mid-token deltas, where a boundary is not a word break; Claude's blocks are whole blocks.

**Expected:** a tail per stream kind, so a value split between two text blocks is redacted with thinking between them; a word opening a new Claude block is not pulled into a token that ended the previous block. **Test:** `hub/tests/test_run_secrets_stream.py`: for one registered run, text `"Channel prefix aw_live_"`, thinking `"Good, done."`, text `"Q7xP2mK4R9sT is it"` -> the thinking comes back unchanged and the second text starts with `<redacted>`. Both fail today. Seam: Runs (Claude executor) x redaction (F488/F602).

## F1005 (B) -- Retry merges whatever the task's branch now points at: a commit pushed after approval lands on main with no check run, no review and no override, past a check that would have refused it

**Status:** open 2026-10-23. Found by the day sweep `sweep-tasks-sweep` (Worktrees row; scratch Hub :8160, profile wt1023, proj-1fff2af61236, `scripts/drive/s1023_wt_drive.py bypass`).
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** yes
**Tier:** 1

A hand-made task (no loop, no requirement link) merges its own branch tip (F622's `review_alone_gates` route). T1 was worked by a Haiku turn, its checks passed on `fd2dc80`, it was Landed, and `fd2dc80` merged. Then:

```
PUT /settings  checks: tests + nobad = py -3.11 -c "import os, sys; sys.exit(4 if os.path.exists('bad.txt') else 0)"
operator commits bad.txt on agentweave/task/<T1>          -> b3b2f87
GET  /tasks/<T1>/integration-preview -> "approval will merge one commit into master; it merges cleanly as of now"
POST /tasks/<T1>/integrations/retry  -> 200  [merged fd2dc80, merged b3b2f87]
git show master:bad.txt              -> "this file fails the nobad check"
GET  /tasks/<T1>/checks              -> one run, passed, target_shas [fd2dc80]   (b3b2f87 never checked)
task_transitions for T1              -> no new row, override_reason null
```

The same door, on the path the gate itself prescribes: T2's merge failed on a conflict, the operator resolved it on T2's branch (`f45b763`, "Resolve the conflict on the branch"), pressed **Try again** in the drawer, and `f45b763` merged; T2's checks list still holds only the run on `8dcf6c7`. Contrast Land on T4, whose `nohowdy` check failed: 409 `gate_unsatisfied` naming the check, a blank `override_checks_reason` refused, and only a stated reason landed it (recorded on the transition).

Cause (verified): `retry_integration` (`hub/hub/task_transition_service.py:1068-1091`) goes straight to `integrate_task`, which resolves targets afresh with `merge_targets` (`:1193`); for a branch-tip task that is `task_branch_tip` (`hub/hub/task_integration.py:552`), i.e. whatever the branch holds now, not what approval judged. Neither `evaluate_approval` (checks, conflict) nor `project_checks.request_run` is asked, and the route (`hub/hub/api/v1/tasks.py:1414`) accepts it on an already-merged task whose newest row is `retryable: false`.

**Expected:** a retry merges only what approval judged; where the branch has moved past it, the retry runs the approval gate on the new tip (checks, conflict) and refuses with the gate's sentence, or asks for the same override reason Land does. **Acceptance drive:** this repro -> retry refused naming `nobad`, `master` unchanged. **Test:** `hub/tests/test_task_integration_retry.py`: an approved, merged branch-tip task, a commit added to its branch that fails a configured check, `POST /integrations/retry` -> master does not contain the commit and the answer names the check. Fails today. Seam: Worktrees & integration (retry) x project checks x approval gate.

## F1056 (B) -- a build can land only on `main` or `nowhere`, and on a project whose checkout the Hub runs from, landing anywhere but `master` means switching that checkout's branch

**Status:** open 2026-10-28. Found preparing slice H (`the-measured-re-run`, FR-4 `lands-off-master`) on :8000.
**Source:** code
**Theme:** Worktrees & integration
**Ready:** no -- design gap between slice D (D8: "A named branch is not offered") and slice H (FR-4)
**Tier:** 1

Slice H requires each build to land its approved work on its own branch cut from the base commit. `builds.LANDINGS` is `("main", "nowhere")` (`hub/hub/builds.py:47-49`), and integration merges into the project's own checkout and refuses unless that checkout is on the target branch (`task_integration.py:75-79`, `checkout_obstacle` :760). So the only way to land a build off `master` is to point the project's main branch elsewhere and switch the checkout -- which for this repository is the checkout :8000 serves its code and UI bundle from. H therefore runs with `landing: nowhere` and assembles each build's branch afterwards from the task branches, which skips slice E's merge queue. **Expected:** a build may name a landing branch, created from its base commit and merged into in a worktree of its own, never in the project's checkout. Seam: Worktrees & integration x builds.

## F1073 (B) -- the mender offers answers it cannot carry out and misstates the evidence gate: "Approve without the check -- operator approval overrides the partial-evidence gate", which neither it nor the operator can do

**Status:** open 2026-10-28. Found by slice H's Gated build on :8000 (`build-cee80c298887`), question `q-96041fe49960`.
**Source:** drive
**Theme:** Questions
**Ready:** yes
**Tier:** 1

At 13:53 the mender asked about `task-a2437846eb7f` (reviewed, approval refused on FR-3's partial evidence) and offered "Approve without the check". The operator chose it. The mender's next turn (`run-f8b79cd509be`) replied "I can't act on that answer. Approving the task isn't one of my powers", and the operator's own `PATCH status=approved` was refused 409 `gate_unsatisfied`: there is no override for an evidence gate, only for checks (`override_checks_reason`). So the option was false twice: the mender cannot approve, and nobody can approve over the gate. A mender option should be an action the Hub will take on that answer, or say plainly that the operator must act and how. At 14:27 it asked the same question again (`q-527c404bf04f`), 21 s before the operator approved. Area: Questions x Flows & review.

## F1074 (B) -- at Gated, a criterion checked by the operator blocks approval until the operator records full evidence, and nothing says so before it happens or names the screen to do it on

**Status:** open 2026-10-28. Found by slice H's Gated build (:8000).
**Source:** drive
**Theme:** Requirements, evidence & coverage
**Ready:** no -- decide whether Gated should ask for operator checks up front (at Build) or offer them on the task when review ends
**Tier:** 1

FR-3 of the candidate had a `checked_by: operator` criterion. At Gated, QA's evidence covered it partially, and approval was refused: "record evidence that demonstrates all of it, with covers: full, and have it accepted ... or build the task at a level that does not gate them". The refusal names no screen; the route that works is the operator's `POST /project/spec/evidence` (`ev-f59cdc2a15c5` here). Starting the build said nothing about the operator check it would need. Fast approved the same task over the criterion with no question. The drive did the real check in a browser on a scratch Hub served from the build's branches. Area: Requirements, evidence & coverage x Flows & review.

## F1085 (B) -- Check and `submit_spec_document` say "ready to approve", then approval refuses with gaps neither reported

**Status:** open 2026-10-29. Found when the operator approved `the-build-plan-lives-in-the-spec-and-every-task-goes-to-its-people` (`spdoc-a7d41f10be14`).
**Source:** drive
**Theme:** Spec flow
**Ready:** yes
**Tier:** 0

Repro: Architect submitted the document; the answer was `blocking: []`, `ready_to_approve: true`, `warnings: []`, and the operator's Check agreed. The operator pressed Approve and got three gaps: `criterion_without_check` x16 (no `checked_by`), `no_acceptance_drive` (the first task was not depended on by every other task) and `steps_skipped` (document still at step `intake`). The first two come from `spec_completeness.approval_gaps` (`spec_completeness.py:360`, `:385`), which the submit answer and Check do not run. An agent filling a document in one pass cannot see them until the operator is already trying to approve, which costs the operator an extra round trip each time. **Expected:** `submit_spec_document`'s `blocking` (or a separate `approval_gaps` list) and Check report everything approval would, so `ready_to_approve: true` means approval goes through, or at most warns. **Test:** submit a change-spec with criteria lacking `checked_by` and no acceptance-drive task: the submit answer names `criterion_without_check` and `no_acceptance_drive`, and `ready_to_approve` is false.

**Also (2026-10-29, Architect):** an unresolved open question only warns. `submit_spec_document` answered `blocking: []` and `ready_to_approve: true` for `a-task-s-checks-and-merges-use-its-own-work-and-a-live-run-is-never-reset`, while three open questions were `resolved: false` and only raised `unresolved_question` warnings. The tool's own description says "An unresolved one blocks the document".

## F1086 (B) -- the Hub's own knowledge-vault output dirties the project checkout and blocks its own landing

**Status:** open 2026-10-29. Found by reading the ledger of `spdoc-a7d41f10be14` (Architect).
**Source:** ledger
**Theme:** Worktrees & integration
**Ready:** yes
**Tier:** 0

Repro: `task-94d59bc7214d` was approved at 17:02. Its integration was `skipped` twice (17:03, 17:04) with "the project's checkout has uncommitted changes to tracked files". Stall `stall-92f8a073661c` was raised, and the mender gave up: "uncommitted changes under knowledge/ (vault output)". The task landed only at 17:38, after the operator-approved commit `6e3689b` "Commit knowledge vault output (operator-approved to unblock integration)" and a 30-minute check rerun. `hub/hub/vault.py` writes sources and facts under the project's `knowledge/` directory, which is tracked, so every distillation can block every approval until somebody commits by hand. F715 made the preview *say* the checkout is dirty; nothing stops the Hub from being the one dirtying it. **Expected:** the Hub's own writes to tracked paths in the project checkout never block its own integration: it commits them itself, or integration does not count them. **Test:** with an uncommitted vault write under `knowledge/` and nothing else changed, approving a task integrates it, `merged`.

## F1090 (B) -- side-finding tasks bound to a finished spec keep it from folding, and a duplicate pending task cannot be rejected

**Status:** open 2026-10-29. Found when the operator tried to fold `spdoc-a7d41f10be14` after its build finished.
**Source:** operator
**Theme:** Builds
**Ready:** yes
**Tier:** 0

Repro: after the build finished, two tasks outside the build's plan stayed bound to the document. One was `task-0e655f8ddc47`, filed by QA during review for F1088, with no assignee. The other was `task-5f4335f3826b`, Architect's replacement for it, assigned to Developer and pending. Folding refuses `fold_tasks_open` (`spec_service.py:881`) while any task is open. Neither task is in the build (`build_id: null`), so nothing starts it and the spec stays unfoldable until someone notices. Rejecting the duplicate also fails: `PATCH /tasks/task-0e655f8ddc47 {status: rejected}` answers 409 "From 'pending' the available transitions are: assigned, in_progress". **Expected:** a pending task can be withdrawn as a duplicate. The fold refusal and the finished-build notice name each open task and whether a build will ever start it. **Test:** reject a pending task -> 200, and the document's open-task list no longer names it.

**Also (2026-10-29, operator: "the agents are stopping because there is no flow"):** hand-driven work does not move on by itself. `task-5f4335f3826b` was completed again at 22:51 after a send-back, and sat with no check until Architect messaged QA. When it was sent back at 22:48, Developer did not start until messaged. A sent-back task can only move to `in_progress`, so nobody but its holder can put it back in the queue. When it was approved, its dependent `task-5776b7d94b0c` stayed `pending` until moved by hand. Each step of a two-task fix needed the Architect to relay it. **Expected (to be decided):** a hand-placed task with a named checker goes to that checker when completed, and a dependent pending task with an assignee is assigned once its prerequisites are approved. Or the operator is told plainly which task waits on them, and for what.
## F1092 (B) -- a build's default builder is not honoured in a flow: any free agent takes a task that names no builder

**Area:** Flows & review. Driven 2026-10-30 on :8010 at 4dba06e (`scripts/drive/d1030_own_work_replay.py`). A flow built with `builder: Builder`, `checker: Checker`, no per-task people and an idle agent `Other` on the roster: `Other` built "Add the report" while Builder was busy. This is what the real build-7450d5263aed did (default DeveloperOpus; Developer and Architect each took a task). The Build dialog shows a default builder, so the operator reads it as a choice that will be kept.
**Cause, read:** the flow's pool narrows only by `build.builders` (`hub/hub/scheduler.py:1836`); the default builder is stored apart from that list and the pool never reads it. A task naming a builder is held for that builder (slice 1's drive passes 24/24), and a task added mid-build is assigned to the default, so the plan's own unnamed tasks are the ones left open to anybody.
**Default checker held:** every review in the drive went to Checker.
**Status:** open 2026-10-30.

## F1095 (B) -- creating a document over a file the Hub has no row for answers 201 and destroys the file
**Status:** Open. Found driving New capability (task-bf5ebb75161c) on 2026-10-30; its fix was taken out of that task as a contract change that needs its own look.
**Source:** found by driving
**Theme:** Spec documents
**Ready:** yes
**Tier:** 1

Repro: write `{"title": "KEEP ME"}` to `spec/capabilities/handmade/spec.json` with no document row, then `POST /project/documents` with that path, title `Handmade`, kind `capability`. It answers 201 and the file now holds the empty scaffold; `KEEP ME` is gone (run against a test client on 2026-10-30). The content really is lost: `create_document` (`hub/hub/spec_lifecycle.py:238`) checks only for an existing row, the Hub keeps no copy of a file it never read, and only git can bring it back, if the file was ever committed. New capability reaches this from the UI, because its path comes from the title: a title that folds to a loose capability's folder overwrites it with no warning. **Expected:** a create over a file the Hub has no record of is refused and the file is untouched, with adopting (`hub/hub/spec_adoption.py:297`) named as the way to take it in. **Mind when fixing:** today's behaviour has callers. `TestReindexRoute` and its neighbours in `hub/tests/test_spec_index_writer.py` write a file and POST over it expecting 201 (`:311` onward), and `scripts/migrate_openspec_corpus.py:335` POSTs then PUTs and treats any 409 as "already imported", so a refusal there must not read as success. A refusal needs its own code, distinct from `document_exists`. **Test:** the repro above must answer 409 and leave the file byte-identical.
## F15 (C) — Stopping an agent does not stop the work

**Status:** open (no fix commit; recorded as an operator decision in a2424d9 — there is no pause-this-agent lever, only a per-run stop)

`POST /agent/builder/stop` behaved correctly: the run went to `stopped` (not `failed`), `ended_at`
was set, and the already-delivered queue entry was not spuriously returned.

But `critic` had meanwhile messaged `builder`, so a *new* builder run (`run-448817a1`) started
moments after the stop. The stop endpoint stops **one run**, and the queue immediately starts
another. There is no "pause this agent" — the only lever is per-run, and a peer conversation
outlives it.

## F123 (C, open) — a crashed firing reads `failed` forever, including after the Hub itself retried it and the work succeeded
**Status:** open (decision needed jointly with F121 on what a JobRun row represents; three shapes proposed, none chosen)

Same specimen, sixteen seconds later:

```
job_runs   run-5d31c6858841  conv-eb547b1f68eb  status "failed"
runs       run-5fe90fc12c65  conv-eb547b1f68eb  status "interrupted"   (the crash)
           run-bf3961c3ee7d  conv-eb547b1f68eb  status "completed"     (the retry, 17:07:10)
queue      entry-7f110f6fcc1c  origin_type "job"  state "delivered"  attempts 1
```

The Hub's own crash recovery put the job's message back, delivered it to a new run **on the same
conversation**, and that run did the work and completed. The job's history does not say so. It
says `failed`, and there is no second row for the retry — so the operator's only view of whether
this job's work happened reports the opposite of what happened.

**Mechanism, and it is one line.** `scheduler.finalize_job_run_for_conversation` selects
`JobRun.conversation_id == … AND JobRun.status == "in_progress"` (`scheduler.py:1569-1574`).
Reconciliation has already moved this row to `failed`, so the completing retry matches nothing and
finalisation is a no-op. Every part is individually defensible: the firing *did* fail, and a
terminal row should not be silently rewritten by a later run.

**Not fixed, because the fix is a decision about what a `JobRun` is**, and the same table already
has **F121** open against it (one firing, two `JobRun` rows; the badge counts turns not firings).
The three shapes, costed:

1. *Let the retry finalise the failed row* — smallest diff (drop the `in_progress` filter, or
   widen it to `("in_progress", "failed")`), but it makes a terminal status mutable and erases the
   fact that a crash happened at all.
2. *Append a `JobRun` for the retry* — the history reads firing → failed → retried → completed,
   which is what happened. But the retry is not a firing: `run_count`, `last_run` and the badge all
   count these rows, so this inflates every one of them, which is precisely F121's complaint.
3. *Leave the row and mark the job* — a `continuity_warning`-style field saying "the last firing
   was interrupted; its work was retried and completed". `JobResponse` already carries
   `continuity_warning`, so the surface exists.

My reading is (3), because it is the only one that keeps the firing's record honest *and* tells the
operator the work happened — but F121 and this should be decided together rather than one at a
time, since both are about the same confusion between a firing, a turn, and the work.

Severity **C**: no work is lost, and the operator can find the truth in the agent's conversation.
It is the *job* view that is wrong, and that is the view a job exists to be read from.

---

## F183 (C) — charter names have no uniqueness rule anywhere, and the one place a charter is chosen shows nothing else

**Status:** open. Re-verified 2026-10-21 (`sweep-agents-sweep`, :8154): `POST /charters {"name": "Developer"}` beside the seeded Developer -> 201. Verified 2026-09-09: `hub/hub/api/v1/charters.py` still carries no
duplicate-name refusal on either the create or the rename door, and `Charter.name` has no unique
constraint. Named in no change. [classified 2026-09-09, D-3]

**Severity:** C. Nothing in the Hub resolves a charter by name, so no run misbehaves. What breaks
is the operator's ability to pick the right one.

**Where.** `hub/hub/api/v1/charters.py:19-34` (create) and `:62-80` (update) both write
`body.name` straight onto the row. `hub/hub/schemas/charters.py:11-12` constrains only length.
There is no unique constraint on `Charter.name` in `hub/hub/db/models.py`. So a project can hold
any number of charters called `Developer`.

The contrast is one file away: `hub/hub/api/v1/agents.py:612-617` refuses a duplicate **agent**
name with a 409 that names it — *"Agent name 'x' already exists in this project"* — which row 3
drove on screen (`row3-04-duplicate-refused.png`). Agents refuse it; charters do not.

**Why it matters at the picker.** `hub/ui/src/components/agents/AgentSettingsControls.tsx:283`
renders each option as `<option key={charter.id} value={charter.id}>{charter.name}</option>` — the
id is the value, the name is everything the operator can read. Two charters under one name are
indistinguishable at the only place the binding decision is made. Measured on screen: the picker
listed **four** options reading exactly `Code Reviewer` (`row4-08-picker.png`).

The seeded set is what makes this reachable rather than theoretical. An operator who wants their
own take on the `Developer` starter has no reason to think the name is taken by something they
must not collide with, and no refusal tells them.

**Reproduction (API).**

    POST  /projects/{pid}/charters {"name": "Code Reviewer", "content": "..."}  -> 201
    GET   /projects/{pid}/charters                                             -> two rows, one name
    PATCH /projects/{pid}/charters/{other} {"name": "Code Reviewer"}            -> 200, now three

Three assertions in `t_sweep_row4_charters.py` hold this open; both the create door and the rename
door are probed, because closing one leaves the other.

**Re-verified 2026-10-15** (full sweep, G1: Charters): still open; duplicate charter names are accepted, visible as "Tester, Tester" in the Add-agent charter select.

**Re-verified 2026-10-20** (day sweep `sweep-agents-sweep`, scratch :8149): still open. `POST /charters {"name": "Developer"}` -> 201 beside the seeded Developer, and Environment -> Charters lists "Developer" twice.

## F336 (C) — no control in the app dispatches a review, so the check that asks the operator to "dispatch a review from the UI" cannot be done

**Status:** open. Filed 2026-09-13 by the day window's `d1-drive`, priority 2. **Measured by search
and in Chromium against the served bundle at `4521625`. What pressing the nearest control does
was read, not driven.**

**The claim.** A turn is a review only when the trigger carries `review_task_id`
(`hub/hub/api/v1/agent_trigger.py:769-772`, and `:1442` on the route). No code in `hub/ui/src`, and
none in the served `hub/hub/static/ui`, sends that field. A search for
`review_task|reviewTask|review-task` gives 0 matches in each. The only control that dispatches an
agent from a task is the card's **Start work** menu (`TaskCard.tsx:259-280`). Its items read
`Start <agent> on this`, and it posts `task_id` (`api/tasks.ts:397-410`). In the drive, the menu on a
completed task offered exactly `['Start au094433 on this', 'Start rv094433 on this', 'Start
wk094433 on this']`.

**Why it matters.** Two operator-facing documents tell a human to do this.
`openspec/changes/archive/2026-09-13-a-refused-review-leaves-nothing-behind/test-guide.md` check 1
says *"From the task's card, dispatch a review naming `critic`"*. Its `tasks.md` 6.1, human-only,
says *"Dispatch a review from the UI … what the UI's own dispatch control shows for the `409`"*.
F319's *"What the operator sees"* asks the same question. Those words can only be followed through
the API. The nearest control does something else. By reading `bind_run_to_task`
(`run_task_binding.py:441-443`, *"a task already `completed` binds and moves nowhere"*),
**Start rv on this** on a completed task starts an ordinary work turn, *"Work on task …"*, bound to
that task. It does not start a review. There is no commit check and no `409`. The operator is not
told what they pressed was not a review.

**The 409 itself is fine where it can be reached.** Over the API it reads *"commit <sha> is not
present in this repository, so there is nothing to check out for review"*, and the board stays
untouched. So 6.1's real answer is that **no UI surface shows it**: the operator cannot dispatch
the thing that would produce it. The only UI-reachable path to a refused review is a flow
(F327), which reports through the queue, not a `409`.

**A possible repair, not proposed.** Either give the card a review item that posts `review_task_id`
and renders the refusal in `task-status-refusal-<id>`, as start-work does, or reword the test
guide and 6.1 to name the API. Choosing between them is a product decision: whether an operator
should hand-dispatch reviews in the app at all. It is not a wording fix.

**Reproduce:** `scripts/drive/t_d1_0913_render.py D`, the board leg, which prints the menu items.
Screenshot: `%TEMP%\d1_0913\render\shots\d-094433-5-start-work-menu.png`.

**Related:** F319, F327, F335 (the route's `409` never stages, above).

**Re-verified 2026-10-15** (full sweep, G3: Flows & review, scratch Hub `:8033`): still open. After the operator accepted the evidence a tester's verdict waited on, the flow skipped every tick with *"Ask tester again, review it yourself, or send it back"*; asking again needs `POST /agent/trigger` with `review_task_id`, and `grep review_task_id hub/ui/src` returns nothing. The stall is filed as F621.

## F350 (C) — below ~560px of height in a narrow window, the composer's send button is off the panel even with nothing pending

**Status:** open. Found 2026-09-13 while measuring F345's narrow fallback; it predates it.

**Measured** (headless Chromium, trial Hub, no question pending): at 500×560 and 420×560 the send
button sits at y 567–599 in a 560px viewport; at 560×800 it is on screen. Below 768px wide the
project rail stacks *above* the conversation panel instead of beside or over it — 290px of 560, 368px
of 800 — so header plus composer alone exceed what is left, and the panel's `overflow-hidden` gives
no way to scroll to it. F345's inline question adds at most its 72px floor on top of that. The
repair is in the narrow layout, not the tray: the rail collapsing to a drawer or header control
below the breakpoint would return that height to the conversation.

## F385 (C) — closing and reopening the Hub window loses every browser-stored preference, and the theme falls back to light

**Status:** open. Filed 2026-09-19 by the operator, from their own use of the `:8000` app.
**Source:** operator
**Theme:** Operator surfaces

**What happened.** In the operator's words: *"whenever I close the hub and open again the theme
changes from dark to light (minor bug)."* Reproducible on every close/reopen cycle of the windowed
app, with no other action in between.

**Where.** Two halves, and the second is why the drift only ever runs dark to light.

1. **The store is never persisted across window sessions.** `src/agentweave/cli.py:950-952` opens
   the window with `webview.create_window("AgentWeave", url, text_select=True)` and
   `webview.start(icon=_app_icon_path())`. Neither call passes `private_mode=False` or a
   `storage_path`, and pywebview's `start()` defaults `private_mode` to `True` — an in-memory
   profile whose cookies, `localStorage` and `sessionStorage` are discarded when the window closes.
   So every `window.localStorage` write the dashboard makes is gone on the next launch.
2. **The fallback is hardcoded light, not the OS preference.** `hub/ui/src/store/configStore.ts:49`
   reads `mode: prefs.mode ?? 'light'`, where `prefs` comes from
   `readJSON<StoredPrefs>(window.localStorage, PREFS_STORAGE_KEY)` (`:41-44`). The round trip
   itself is correct — `setMode` writes through `writePrefs` to the same key (`:116-126, :144-147`)
   — so this is not a read/write mismatch. But when the read returns `{}`, the `??` resolves to
   `'light'` unconditionally. Nothing consults `prefers-color-scheme` anywhere in `hub/ui/src`
   (the only `matchMedia` calls are `lib/motion.ts:7-8` for reduced motion). An operator who has
   never touched the toggle and one who set dark and lost it are therefore indistinguishable, and
   both get light.

**The theme is the visible half; it is probably not the expensive half.** The same discarded
`localStorage` holds `SELECTED_PROJECT_STORAGE_KEY` (`configStore.ts:53-60, :105-110`), so the open
project does not survive a close either. That is masked rather than absent: `bootstrap()`
auto-selects a project when none is persisted (`:176`), so with three projects registered the app
reopens on whichever one that picks rather than on an empty state — the operator lands somewhere
plausible instead of somewhere chosen. **Unverified** — asserted from reading the two code paths,
not reproduced against a running window, because confirming it means driving the operator's own
`:8000` app.

**Fix shape (not decided).** The two halves are independently repairable and the second is a
one-line change with a different meaning:

- Pass `private_mode=False` (with an explicit `storage_path` under `~/.agentweave/`, so the profile
  is somewhere the product owns and a reset can find) to `webview.start()`. This restores every
  preference at once, and is the fix that matches what the operator expects from a desktop app.
  It also makes the WebView2 profile a thing that exists on disk, which `R4`'s reset button would
  then have to know about.
- Separately, decide whether an *unset* preference should follow `prefers-color-scheme` instead of
  defaulting to light. That is a real product decision, not a repair, and it stays wrong for a
  first-launch operator even after the persistence fix lands.

**Related:** `R4` (a reset button, from the same conversation — the persistence profile is state it
would have to clear). `hub/ui/src/store/configStore.ts:17-19` already records that an older
persisted `theme` key from the removed 5-theme picker is deliberately ignored; that is a different
key and not the cause here.


## F389 (C) — an allowed permission decision is persisted nowhere, so "the agent was never refused" is unfalsifiable

**Status:** open. Filed 2026-09-19 by an interactive session at the operator's instruction, as the
residual F52's own RETIRED note records and explicitly says was *"not filed"*. It has been carried
as an unnumbered sentence inside another finding's status line across nine handoffs.
**Source:** read from the code
**Theme:** Operator surfaces

**What is missing.** `record_permission_decision`
(`hub/hub/api/v1/agent_actions.py:932`) persists an event only on the refusal branch:

> Only refusals are persisted. An allowed call is the unremarkable case and would bury the
> interesting one under a row per tool call (`:940-942`).

The reasoning is sound for the timeline — a row per allowed tool call would bury the refusals, and
the refusal is the thing an operator can act on. **The consequence is about evidence, not about the
timeline**: because an allowed call writes nothing, "this run was never refused" and "this run never
asked" produce byte-identical state. There is no record that distinguishes them.

**Why this is worth a number.** It is the exact property that made F52 cost three weeks. F52 claimed
every git commit was silently refused under the `workspace` posture. Disproving it needed
`0cda570` to attack the inference and `57eb92b` to drive a full live turn that committed — because
**no stored record could answer the question directly.** F52 is now RETIRED and its central
inference disproved, but the unfalsifiability that let a wrong inference stand for three weeks is
untouched: **a recurrence would be as unfalsifiable as the original was.**

**Where.** `hub/hub/api/v1/agent_actions.py:932-975`. The refusal branch calls `persist_event` with
`event_type="permission_denied"`; there is no allowed branch. Note that F52's own status line cites
this as `agent_actions.py:940` — the file is at `hub/hub/api/v1/`, and the bare path does not exist
at the repository root. Verified 2026-09-19: the comment is at `:940-942` and the shape is
unchanged.

**Severity C, deliberately.** Nothing is broken and no operator is misled today. It is a gap in what
can later be proven, which is why it sat unfiled for nine sessions — it never reproduces, because
there is nothing to reproduce. That is also why it needs a number rather than a sentence inside a
RETIRED finding's status line, where no index can see it.

**Not proposed, and the cheap remedy is not obviously right.** A counter per run, or a single
`permission_allowed` aggregate written at turn end, would answer "was anything refused" without a
row per call — but that is a design question with a migration behind it, and nobody has asked for
it. **Do not read this finding as a decision that it should be built.**

## F433 (C) — only one unit of a multi-unit proposal can be accepted before its siblings go stale

**Status:** open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B6 rounds (`spec-queue/tracks/B6.md` Final, candidate 5). The spec calls the units individually acceptable, but accepting one makes the rest stale. Not carried by any change: it is an operator design question (should siblings rebase, or be accepted together?).


## F442 (C) — a flow review refused at a deferred dispatch (the run-end re-drain) does not finalize the firing's JobRun

**Status:** open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B1 rounds (`spec-queue/tracks/B1.md` Final); found by R3. Pre-existing; pinned by S13's test 1.5b. The firing's `JobRun` stays open after its review was refused at the deferred dispatch.

## F445 (C) — a link inside the workspace that points outside lists the outside file as a workspace file

**Status:** open. Filed 2026-09-24 (operator decision `F409-approve`), measured by the second
pre-approval review of `an-at-mention-an-agent-wrote-reads-no-file`
(`spec-queue/tracks/reviews/F409-2026-09-24-second.md`). With a junction inside the workspace pointing
outside (no admin needed on Windows), git lists `docs/secret.txt` through it, so the composer's file
picker offers it, and a Haiku `claude -p` turn given `@docs/secret.txt` attached the outside file. The
Hub's own file reader already refuses such a path, so the listing and the reader disagree. Not a
bypass on its own: creating the link needs a shell call the posture judges. Repair shape open: filter
the picker's listing by the same resolution the reader uses. Sibling of F444.

## F466 (C) — a Copilot run's Workspace only judges only the commands Copilot asks about

**Status:** open, filed 2026-09-30 from `a-copilot-agent-runs-over-acp` (review 2026-09-28, finding 1; task 10.1). Partly measured: task 1.1's capture (`hub/tests/fixtures/copilot_acp/turn_write_shell_mcp.jsonl`, Copilot 1.0.88).

Under Claude, `_decide` reads every Bash command word by word. Under Copilot, the Hub judges only what Copilot raises as `session/request_permission`. Copilot's own `manual` mode auto-approves requests it classes read-only (DOCUMENTED: *"read-only requests are auto-approved"*), and the exploration's capture (`acp4…log:34-39`) shows an `echo` running with no request at all. So a Copilot run under Workspace only judges fewer commands than a Claude run, and which ones is decided in Copilot's native runtime. Task 1.1 narrowed the gap rather than confirming it: `Get-ChildItem` **did** raise a request (three times, `readOnly:false`), so the read-only class is smaller than the design assumed. And `curl.exe` raised an ordinary `execute` request, never the `url` request the design anticipated. Parity is therefore measured command by command, not assumed.

What would close it: a deciding `preToolUse` hook, which slice 5 declines. Test to write when it matters: a drive that runs a known read-only command under Workspace only and records whether a request arrived.

## F476 (C) — three Copilot-name branches remain outside the runner adapters, against the requirement the adapter change adds

**Status:** open, filed 2026-10-01 while closing `each-runner-cli-is-one-adapter` (task 4.4). Derived from code, not driven.
**Ready:** needs design (each branch needs an adapter member that has not been designed)

The change adds *Each supported runner CLI is served by exactly one runner adapter* to `runner-registry`,
which says code outside the adapters SHALL NOT branch on the name of a supported runner CLI, one that has an
adapter. Task 3.7 gave Copilot an adapter (`CopilotAdapter`, `ADAPTERS["copilot"]`), so Copilot is now
such a CLI. Task 4.4's scan (`hub/tests/test_no_runner_literals.py`) checks only `"claude"`/`"codex"`, as
its text says, and passes. A scan for `"copilot"` finds three branches it does not cover:

- `hub/hub/api/v1/agent_trigger.py:1222` — `if runner == "copilot":` dispatches to `_prepare_copilot_turn`
  (home, diagnostics, every refusal before the `Run` row). Task 3.7 kept this deliberately.
- `hub/hub/api/v1/agents.py:1681` — `runner.cli != "copilot"` guards the Copilot home ensured at agent
  creation (`ensure_copilot_home`).
- `hub/hub/conversation_titles.py:280` — `if runner.cli == "copilot":` parses the JSONL title envelope; the
  Claude and Codex title commands print plain text, read raw.

(`copilot_probe.py:129` matches the pattern but compares a directory name, not a runner.)

Each needs a member the slice-1 design never named: a per-turn preparation hook on the RPC transport,
a hook run when an agent is bound or created, and a title-text extractor beside `parse_one_shot`.
Adding them while closing the change would be design without a round. **Fix:** design those three
members (Copilot slice 3, `a-copilot-agent-uses-hooks-and-its-own-agents`, already touches the
trigger's Copilot preparation), move the branches onto them, and widen `test_no_runner_literals.py`
to every key of `ADAPTERS`, so the scan covers whatever runners exist rather than a hard-coded two.

## F480 (C) — a hard-linked file inside the calls directory passes the calls-root rule

**Status:** open, found 2026-10-02 by the adversarial review of `an-arguments-file-written-from-powershell-is-the-hubs-own`
(`spec-queue/tracks/reviews/F478-2026-10-02.md`, finding 7); measured by the reviewer, not yet re-measured by a
drive. **Ready:** no change owns it. It belongs to slice 3's (`a-run-reaches-the-hub-without-mcp`) calls-root rule.

`_inside_hub_calls_root` (`hub/hub/mcp_server.py:1680-1693`) resolves a name with `os.path.realpath`, which follows
symbolic links and junctions but cannot see a hard link. So `.agentweave/calls/hl.json`, hard-linked to a file
outside the workspace, counts as inside, and a case-3 file-tool write (or a case-4 PowerShell write, once that
change is built) to it has standing and writes the outside file. Creating the link,
`New-Item -ItemType HardLink -Path .agentweave/calls/r.json -Target (Join-Path $HOME x.txt)`, is allowed by `_decide`
under "Workspace only" (measured), where a plain relative write is already allowed, so nothing is added there. Under
"Ask me" the link is a card, so this is the persistent-state residual: one approved command makes every later
"own" write to that name a write elsewhere, unasked. The cheap close the reviewer proposes: an existing target with
`st_nlink > 1` is not inside. It needs a design round (the requirement text says "taken as named and not by
following links", which a hard link sidesteps) and a decision on whether the Hub's turn-start reset of the calls
directory should also remove multiply-linked files.

## F481 (C) — a Copilot conversation cannot be compacted on demand: `/compact` is sent as chat and charged

**Status:** open, found 2026-10-02 by drive task 7.5 of `a-copilot-run-shows-its-credits` (design.md Round
log, "Drive, group 7"; `run-7ae7fb81a043` on the trial Hub). **Ready:** no change owns it.

An operator who types `/compact` to a Copilot agent gets a normal model turn. In the drive that was one call,
22876 tokens and 0.17 AI credits, with no `session.compaction_complete` and no compaction. The cause is
deliberate and correct: slice 2 begins every `session/prompt` with `COPILOT_TURN_CONTEXT_HEAD`
(`hub/hub/copilot_acp.py`), so that no relayed text runs as a slash command (`/allow-all`, `/permissions`).
Copilot does advertise `compact` in its `available_commands_update`. Two things are left. First, the
operator has no in-app way to compact a Copilot conversation, and nothing tells them that `/compact` will be
spent as chat. The old `POST /agents/{name}/compact` route only sends a message telling the agent to "Run
`/compact` in your session", which no agent can do. Second, design D3's compaction de-duplication
(`compactionTokensUsed` against an `assistant.usage` with the same `requestId`) stays unmeasured until a
natural auto-compaction at about 80% of the window is captured. A fix would be a Hub-issued compaction
that bypasses the guard for that one command, or refusing a leading `/compact` with a sentence.

## F482 (C) — D8's quota recognition rests on the schema, not on a captured refusal

**Status:** open, filed 2026-10-02 by task 8.2 of `a-copilot-run-shows-its-credits`. **Ready:** waits on evidence,
not on a change. A Copilot quota refusal is recognised only by a `session.error` (or a `session/prompt` JSON-RPC
error's `data`) carrying `errorType "quota"` and `errorCode "quota_exceeded"` (design D8, `copilot_usage.py`). Those
names come from Copilot's published `ErrorData` schema; no real refusal has ever been observed. Drive task 7.7
replayed the schema's shape through `acptee`, so it proves the Hub's handling, not the recognition. Task 5.2 logs
every armed `session.error` whole at warning level (`Copilot session.error errorType=… payload=…` in the Hub's
log). **Wanted:** the first real quota refusal's line from that log, copied here. It either confirms D8 or
corrects the field names. If a refusal ever arrives without a hold, look for that line first.

## F486 (C) — a cross-change obligation lives only in the archived change: `worker-spend-counts-against-the-budget` never mentions the worker credit sums it owns

**Status:** open, found 2026-10-03 by R1 of `a-copilot-one-shot-records-its-credits` (its design D5 and
Open question 1). **Ready:** yes, as a note in that change's next round. No code is involved.

`a-copilot-run-shows-its-credits` (archived 2026-10-02) decided in D12 that *"whichever lands second
adds `ai_nano_aiu` / `premium_requests` sums to each `workers` line"*. Its task 6.4 recorded that
`worker-spend-counts-against-the-budget` had not landed, so *"that change owns them now"*. Nothing in
`openspec/changes/worker-spend-counts-against-the-budget/` says so: `grep -i "credit\|nano\|copilot"`
over its `proposal.md`, `design.md`, `tasks.md`, `test-guide.md` and spec delta finds nothing. An IMPL
of that change built from its own files would ship `workers` lines without credits, and the Copilot
worker credits that `a-copilot-one-shot-records-its-credits` starts recording would reach no screen.

The same archived note also assumes that *"a Copilot one-shot's `total_tokens` comes from slice 2's
envelope parser"*. The real one-shot capture (`hub/tests/fixtures/copilot_acp/oneshot_ok.jsonl`) has no
token count on any line, so every Copilot worker row's `total_tokens` will be NULL. That change's
round should know this before it designs a Copilot line.

**Fix candidate:** the sibling's next round adds a task, a test and a delta sentence for the credit
sums, and records the token-less Copilot stream. The spec-flow lesson is that an obligation handed to
an unarchived change has to be written into that change's own files at the time it is handed over.

## F494 (C) — a Copilot provider runner has never completed a turn with a valid key

**Status:** open, filed 2026-10-05 when task 7.6 of `a-copilot-agent-uses-hooks-and-its-own-agents`
(slice 5, group C) was moved out so that the change could archive (operator, 2026-10-05).
**Ready:** waits on the operator: it spends real money, and the operator supplies the key when they
choose. No key is asked for until then.

Group C is built and tested (tasks 1.7–1.9, 3.1–3.5), and driven up to the provider: task 7.3 sent a
real run to `https://api.anthropic.com` with the runner's key variable and got Anthropic's 401, and
task 7.5 drove the refusals. No turn has yet **completed** on a valid key, so two things are not
measured: that a provider turn finishes and reports its usage in tokens, and that the key's value
appears nowhere in the trial database afterwards (the scrub's end-to-end check; F488's hole in it is
fixed by `1d2f72a`).

**The drive (task 7.6 verbatim in intent):** with a dedicated Anthropic workspace key carrying a hard
monthly limit of a few dollars, set only in the trial Hub's launch shell (never user-wide, so `:8000`
cannot see it), run one turn on `claude-haiku-4-5-20251001` through a provider runner: `Reply with
the single word ok.` It completes, and its usage is in tokens. Then grep the trial database
(`mode=ro`) for the key's value: no match. Add one turn asking a Copilot agent to use the `explore`
agent and record the `model` its `subagent_completed`/`subagent_failed` report (slice 5 finding 13).
Revoke the key afterwards and record that it was. A failure here is a fix against the archived
slice 5 code (`hub/hub/runner_provider.py`, `hub/hub/run_secrets.py`).

## F498 (C) — a real live Copilot checkpoint call recorded no credits: the single capture's
`session.usage_checkpoint` is not guaranteed on every one-shot

**Status:** open
Found 2026-10-06 night by `a-copilot-one-shot-records-its-credits` task 3.1's drive, on the real
trial Hub (`:8010`, `proj-d85a82bf4216`), spending both calls of the 2-call budget. Driven, not
just read.

Set the project's `checkpoint_runner_id` to `runner-72c07eca7e75` (`copilot-s5drive`, a real
GitHub Copilot CLI runner — `provider_config: null`, `model: null`, so Free-plan Auto), then
`POST /conversations/conv-15d28aac6465/checkpoint` for agent `cp5` (`cp5` already carried 51K
tokens of real conversation history). The route returned `201` with `status: "ready"`,
`probe_status: "passed"` — the checkpoint body itself is real and well-formed. `mode=ro` read of
`worker_invocations` afterward:

```
wrk-02f48c6671b4  checkpoint        copilot  ok  error=None  ai_nano_aiu=None  premium_requests=None
wrk-bdea16321100  checkpoint_probe  copilot  ok  error=None  ai_nano_aiu=None  premium_requests=None
```

Both fields are `NULL` on both rows, where task 3.1 expected non-`NULL` the way the single
2026-09-29 capture (`oneshot_ok.jsonl`) and 2.1/2.2's fix predict. `outcome="ok"` and `error=None`
rule out a spawn/envelope failure — `parse_copilot_envelope` ran to completion and simply found no
`session.usage_checkpoint` line in this stdout, which is exactly D4's already-named "no checkpoint"
row (`empty usage (unchanged)`), not a bug in 2.1/2.2's code. The Hub process serving `:8010` was
confirmed started at `2026-10-06T02:49:44` (PID 23496, listening on 8010), after `b79c11b`'s fix
landed — so this was not stale code. `GET /accounting` showed neither figure for either row (its
`recent_turns` list does not reach past 2026-10-05T12:42, confirming D5 as designed: no route reads
`worker_invocations` credits).

So the single capture this change's design is built on is not representative of every real
one-shot: whether a given Copilot one-shot emits `session.usage_checkpoint` at all is UNVERIFIED
beyond that one capture, and this round measured a real, well-formed, successful call that did
not. The budget is spent (2/2 calls), so this is not re-driven tonight. Task 3.2: no independent
non-interactive reading of Copilot's own usage report was found (matching
`a-copilot-agent-uses-hooks-and-its-own-agents` task 7.1's finding for `/usage`) — recorded as "not
compared: no independent reading".

**Direction (not decided):** a second, deliberately provoked capture (a longer or BYOK one-shot,
or several real calls across a day) would show whether the checkpoint event is conditional (on
session length, model, or something else) or just rare. Until then, 2.1/2.2's fix is confirmed
correct for the shape it was built from, but the rate at which real checkpoints actually carry a
`session.usage_checkpoint` line is open.

## F557 (C) -- agent budget is labelled a concurrency limit, and the Hub enforces it only when an agent staffs an agent

**Status:** open. Filed 2026-10-08 (interactive, reading code while inventorying the project's settings for R2/F379).

Settings says agent budget is "The maximum number of agents this project may run at the same time"
(`ProjectSettingsPanel.tsx:148`); the 2026-09-17 Buried Controls audit repeated it. The Hub reads `agent_budget` in one
place that refuses: `request_agent` (`api/v1/agents.py:2556`), which counts the project's agents and refuses a new one
at the budget. Operator agent creation does not check it, and nothing limits concurrent runs by it. The label is
corrected by `the-settings-that-gate-collaboration-are-on-the-project-page` (FR-8); what the budget *should* cap is
an operator question, left open.

## F560 (C) -- the close-exploration route outlived the gate it served

**Status:** open 2026-10-08. Found while building step-journey (`a-spec-is-written-one-step-at-a-time`, FR-11).

Proposing no longer needs exploration closed, and the app no longer offers the control, but
`POST /project/documents/close-exploration` and `spec_lifecycle.close_exploration` still exist: about 70 Hub test files
call the route as setup before proposing. It decides nothing now and has no client. Remove the route, the function and
the `explore_closed` view field together with those calls (a mechanical sweep), or keep it as a no-op deliberately.
`explore_closed_at` stays either way, for rollback.

## F667 (C) -- read-only agents share the project directory as their workspace, so two of them racing on `.agentweave/calls/` (or any file) collide

**Status:** open 2026-10-15. Measured in the work-PC Copilot drive of 2026-10-12 (Copilot CLI 1.0.94-3, source Hub, `proj-d73f8848ee60`; handoff `.claude/work-pc/handoff-0162-2026-10-12-copilot-drive.md`), filed at home 2026-10-15. Raised as `wpc4-c` by the F663 change's R2 round; not driven live. Seam: Worktrees & integration x Runs. Tier guess: 1 (design gap).

## F762 (C) -- the coverage bar offers Accept, and "Accept instead", on a piece recorded for an earlier wording, which the Hub always refuses

**Status:** open 2026-10-19. Found in the evidence sweep (scratch Hub :8150, real browser, `scripts/drive/s1019_evidence_ui.py` and an inline Playwright check).
**Source:** drive
**Theme:** Requirements & evidence
**Ready:** yes -- repro below.
**Tier:** 0

FR-1 was reworded after its pieces were recorded. On the document's coverage bar, **Evidence (3)** lists the awaiting earlier-wording piece with an **Accept** button and a merge note. Pressing it shows the Hub's 409 `evidence_stale` sentence, which is legible. A rejected earlier-wording piece offers **Overturn… -> Accept instead**, which is refused the same way. `EvidencePieces` (`hub/ui/src/components/spec/EvidencePieces.tsx:52-54`) never reads `for_current_wording`, though the Evidence view marks the same pieces "earlier wording" and the API carries it. Expected: no accept control on an earlier-wording piece, an "earlier wording" mark as in the Evidence view, and Reject left available. The UI twin of F758, which is the gate's remedy text for the same piece.

## F764 (C) -- a cannot-satisfy report is not tied to its task's criteria, repeats are not recognised, and answering any one report on a task unblocks it

**Status:** open 2026-10-19. Found in the spec sweep (`scripts/drive/s1019_spec.py`, scratch Hub :8160).
**Source:** drive
**Theme:** Spec documents
**Ready:** yes -- repro below.
**Tier:** 0

The setup is one approved change with tasks t-alpha..t-delta, each with one requirement and one criterion, and a run bound to t-alpha:
- The run reports `c-beta`, which is t-beta's criterion: 201, and **t-alpha** is blocked with "cannot satisfy criterion c-beta: not my task's". `spec_amendments.report_cannot_satisfy` checks only that the run's task belongs to the document, never that the criterion serves the task's requirements.
- It then reports its own `c-alpha`: 201 with `task_blocked: false`, since the task was already blocked. `blocked_reason` still names c-beta.
- It reports `c-alpha` a second time while the first is unanswered: 201, a new report. Proposals answer the same kind of repeat with `already_pending`; reports have nothing like it.
- The operator rejects the `c-alpha` report ("task stays blocked"), then accepts the cross report. t-alpha goes to `in_progress`, which undoes the rejection, while two `c-alpha` reports are still on the task (one rejected, one unanswered).

The spec page's **Defects by step** then counts the change as "build 7". That count includes the repeat, the cross report and the rejected report, because `spec_defects.py:126-135` counts every `cannot_satisfy` event, whatever its answer.

Expected: refuse (or at least flag) a criterion that serves none of the run's task's requirements; answer a repeat on the same criterion with the pending report's id; unblock a task only when none of its reports is still unanswered or rejected. Seam: Spec documents (cannot-satisfy) x Tasks.

## F765 (C) -- a fold archives a change with unanswered cannot-satisfy reports without a word, and reports keep landing on the archived change

**Status:** open 2026-10-19. Found in the spec sweep (`scripts/drive/s1019_spec.py`, `s1019_spec_ui.py`, scratch Hub :8160), seen in a browser.
**Source:** drive
**Theme:** Corpus & folding
**Ready:** yes -- repro below.
**Tier:** 0

The change in F764 had two unanswered reports on `c-alpha` ("cannot finish under 1ms"), so its FR-1 read `amendment_unreviewed`. With all four tasks approved, `GET .../fold-draft?into=<capability>` answered `warnings: []`, and `POST .../fold` answered 200 (`merged: 1`, archived, `warnings: []`). The capability now carries `c-alpha` "alpha finishes under 1ms" verbatim. A builder had said twice that this cannot be met, and nobody was asked. After the archive:
- The run still bound to t-delta reports `c-delta` on the **archived** change: 201. The archived change's FR-4 coverage turns `amendment_unreviewed`.
- The Amendments panel offers **Amend criterion...** on the archived change, which the Hub refuses legibly: "... is archived; only an approved document is amended". It also offers **Accept and unblock** (200, `task_unblocked: false`), and says "FR-1 cannot be verified until you review this." on a document that is closed.

Expected (warn, not gate): the fold draft and the fold each list every unanswered cannot-satisfy report as a warning naming its criterion. `report_cannot_satisfy` refuses a document that is no longer approved, saying it is archived and naming the capability where the behaviour now lives. The panel shows Amend only on an approved document. Seam: Spec documents (cannot-satisfy) x Corpus & folding.

## F845 (C) -- in its own conversation, a question nobody waits on still says "Pick one, or write your own answer below." with the composer placeholder "Answer asker…", but typed text is now sent as a plain message and the question stays open

**Status:** open 2026-10-21. Found by the day sweep `sweep-questions-sweep` (scratch Hub :8152, Chromium against the served bundle, `scripts/drive/s1021_q_ui.py stale`). The residue F804's own fix note named ("still renders as the composer's placeholder owner").
**Source:** drive
**Theme:** Questions
**Ready:** yes
**Tier:** 0

A fresh Haiku turn in C (`conv-0d3fea18114c`) asked `q-59bfc787766e` ("Which colour for the footer?", wait 30 s); nobody answered; the run ended ("No answer came within the timeout."); the route lists it `asker_waiting: false`. In C the card shows the "no longer waiting" chip **and** "Pick one, or write your own answer below.", and the placeholder reads "Answer asker…" (screenshot `testbed/ui-judge/s1021-q-stale/101335/C_own_stale_after.png`). Typing "Reply with the single word gamma." and Send started `run-eb20350b5343` in C with that bare text (entry `entry-d54f17a114d3`) and left the question `answered 0`. That is F804's intended behaviour (`AgentOutputPanel.tsx:1049`: typed text answers only while `asker_waiting !== false`), but the screen still promises the opposite: an operator who types "green" as a late answer sends the agent a bare "green" with no question attached, and the question stays in the Questions list as unanswered. Sources: placeholder `AgentOutputPanel.tsx:1416` (`pendingQuestion ? 'Answer …'`), hint `AgentQuestionCard.tsx:187-188`, though the card already computes `nobodyWaiting` (`AgentQuestionCard.tsx:78`).

**Expected:** when `asker_waiting === false`, the hint reads "Pick one to answer it; anything you type below is sent as a new message." and the placeholder is the ordinary "Message asker…". **Test:** `hub/ui/src/__tests__/questionTrayConversation.test.tsx`: a stale question in the conversation on screen renders neither "write your own answer below" nor an "Answer" placeholder; fails today. Seam: Questions x Conversations & composer.

## F846 (C) -- a conversation cut over by a checkpoint opens from the rail with a live composer and no word of its successor; Send is refused "Unarchive it to continue it", the one door F816 now shuts

**Status:** open 2026-10-21. Found by the day sweep `sweep-checkpoints-sweep` (scratch Hub :8153, profile c1021, Chromium against the served bundle, `scripts/drive/s1021_c_ui.py unarch|predsend|sheet`). The residue of F816's fix: the refusal moved to unarchive, but the routes and screens that point there were not changed. Re-verified 2026-10-22 (sweep-checkpoints-sweep, :8122, Chromium): the predecessor `conv-966fe9cf91e0`, cut over to `conv-da01bb95cfa4` by Checkpoint now, opens with a live composer (`textarea` enabled) and no "archived" or "cut over" word on the page; the only pointer is the queue line "1 waiting in another conversation — waiting for Continue: conversation conv-da01bb95cfa4 was handed a checkpoint…".
**Source:** drive
**Theme:** Checkpoints
**Ready:** yes
**Tier:** 0

alpha's `conv-29d1e4cd542c` was checkpointed (`ckpt-dcf21c885f7d`, ready, probe passed) and cut over to `conv-0198f7d71d7c` (`POST /checkpoints/{id}/cutover` 200). In the rail, Show archived -> the predecessor's row menu -> **Unarchive** -> 409, and the row shows "Conversation conv-29d1e4cd542c was cut over to conv-0198f7d71d7c (checkpoint ckpt-dcf21c885f7d), which holds its work; continue there. This one stays archived and readable." (F816 holds.) Opening that archived row, though: no notice that it is archived or cut over, "Continuing this conversation" above an enabled composer, placeholder "Message alpha…" (`testbed/ui-judge/s1021-c-unarch/102850/unarch-pred-open.png`). Typing "Reply with the single word PRED." and Send -> `POST /agent/trigger` 409 `{"detail":"Conversation conv-29d1e4cd542c is archived. Unarchive it to continue it, or omit conversation_id to start a new conversation with alpha."}`, shown under the composer. The way out it names is the one F816 refuses, and it does not name the successor that holds the work. The Checkpoints sheet on the predecessor still reads "Probe: passed · carried into a new conversation" with no name or link (`CheckpointsPanel.tsx:47`; F816's own note: "not done").

Cause: `conversation_unavailable_reason` (`hub/hub/conversations.py:200`) has one sentence for every archived conversation; `checkpoint_cutover.handover_of` (`hub/hub/checkpoint_cutover.py:61`) already answers the successor.

**Expected:** for a handed-over conversation the trigger refusal names the successor ("conv-… was cut over to conv-… (checkpoint ckpt-…); continue there, or omit conversation_id to start a new conversation with alpha."); the opened predecessor says it was cut over and links the successor; the sheet's "carried into a new conversation" links `cut_over_to_conversation_id`. **Test:** beside the F816 test in `hub/tests/test_checkpoint_cutover.py`: cut over, then `POST /agent/trigger` with the predecessor's `conversation_id` -> 409 whose detail names the successor and does not say "Unarchive"; fails today. Seam: Checkpoints x Conversations & composer.

## F851 (C) -- `request_agent`'s required `task` is the new agent's whole first message, but neither the MCP tool nor the `aw-tool` listing says so; a real agent passed a task id

**Status:** open 2026-10-21. Found by the day sweep `sweep-agents-sweep` (scratch Hub :8154, a real Haiku turn `run-6bc545f5458f`, `aw-tool` call mode).
**Source:** drive
**Theme:** Agents
**Ready:** yes
**Tier:** 0

Asked to "call request_agent with name 'Beta' and template 'beta'", alpha's first call failed for a missing argument. Its thinking: "`request_agent` requires three arguments: name, template, and task ... no details on what task should be. Let me try with ... a simple task identifier". It listed the project's tasks and called again with `task: "task-e32b0b7a5aec"`. That call was refused for F811's case twin, which is the only reason no new agent was created whose entire brief was a bare task id. The route treats `task` as free text: it becomes the delegation `Message.content` and the queue entry's `content` (`hub/hub/api/v1/agents.py:2799`, `:2813`; `AgentRequest.task`, up to 100,000 characters, `:100`). The MCP docstring (`hub/hub/mcp_server.py:802-808`) never mentions `task`. The `aw-tool` listing (`agents.py:1515-1526`) gives `args="name, template, task"` with text about the budget and the template only.

**Expected:** both descriptions say what `task` is: "`task`: the new agent's first message, the work you are handing it, in prose; it is delivered to it as a message from you, and it is not a task id". If the field is meant to accept a task id too, the route resolves one. **Test:** `hub/tests/test_mcp_tool_docs*.py` (or beside the aw-tool listing tests): `request_agent`'s docstring and its `_Operation.text` both mention `task` and "first message"; fails today. Seam: Agents x Capability plane (agent tool descriptions).

_F900-F906 were filed as F835-F841 on 2026-10-20 on `ui/finesse-mocks`, and renumbered on 2026-10-21 when the day window filed its own F835-F837 on the cycle branch the same morning._

## F862 (C) -- with a host granted, a shell command naming an ungranted address is refused saying it "may name only this run's own Hub ($HUB_URL)": the granted hosts it may also name go unmentioned

**Status:** open 2026-10-21. Found by the day sweep `sweep-reach-sweep` (scratch Hub :8157, a live Haiku turn).
**Source:** drive
**Theme:** Permissions & sandbox
**Ready:** yes
**Tier:** 0

`PUT /projects/{p}/settings {"default_permission_mode": "workspace", "reach_grants": {"roots": [], "hosts": ["github.com"]}}`. A Claude turn (Haiku) ran `git ls-remote https://github.com/gutohuida/AgentWeave HEAD`, which was allowed (the grant works), and then `git ls-remote https://gitlab.com/gitlab-org/gitlab HEAD`, which was refused with `permission_denied` reason `'https://gitlab.com/gitlab-org/gitlab' is a network address. Under this posture a shell command may name only this run's own Hub ($HUB_URL); if the task needs another address, ask the operator with ask_user`. The decision is right. The sentence is not: this run may also name github.com, the operator granted it, and the refusal is the one place that says what is allowed. This is F794's species for hosts (F794 fixed the same sentence for read roots).

Cause: `_NETWORK` (`hub/hub/mcp_server.py:1473-1476`) is one fixed sentence, used at `:2533`, `:2543`, `:2631` and `:2637` whatever `_REACH.get().hosts` holds.

**Expected:** when the run has granted hosts, the refusal names them, e.g. `... may name only this run's own Hub ($HUB_URL) and the hosts the operator granted (github.com); for another address, ask the operator with ask_user`. With none granted it reads as today. **Test:** in `hub/tests/test_an_operator_sets_how_far_an_agent_reaches.py`, `_decide` for `Bash` `curl https://other.example` with `AW_REACH_GRANTS` naming host `github.com` denies with a reason containing `github.com`; with no hosts granted, the reason is unchanged. Seam: Permissions & sandbox (shell judge) x reach grants (hosts).

## F863 (C) -- the Runners page calls the project's checkpoint runner "Unused", and deleting it is then refused: "Runner is bound to the project's checkpoint runner setting. Unbind before deleting."

**Status:** open 2026-10-21. Found by the day sweep `sweep-projects-sweep` (scratch Hub :8158, Chromium against the served bundle).
**Source:** drive
**Theme:** Runners & models
**Ready:** yes
**Tier:** 0

Repro (`py -3.11 scripts/drive/s1021_p_ui.py extra`): `PUT /projects/{p}/settings {"checkpoint_runner_id": <r-sonnet>}`, with no agent and no manager job on r-sonnet. On Environment -> Runners the row reads "r-sonnet Claude Code · sonnet (latest) **Unused**". Pressing Delete r-sonnet: `DELETE /projects/{p}/runners/{id}` -> 409, and the page shows "The runner was not deleted. Runner is bound to the project's checkpoint runner setting. Unbind before deleting." (screenshot `testbed/ui-judge/s1021-p-extra/122340/50_checkpoint_runner_delete.png`). The refusal is right and the count is wrong: the page told the operator nothing used it. Cause: `usedBy` (`hub/ui/src/components/settings/sections/RunnersSection.tsx:51-54`) counts agents and manager jobs only, while the Hub's holder list (`hub/hub/api/v1/runners.py:270-288`) also counts the checkpoint setting. A runner held by an agent and a manager job read "2 using it", which matched the 409 (held, same drive).

Side, same sentence: "Unbind before deleting" names no place to do it, and "background job(s)" is a word the app does not use (the screen calls them Manager jobs). With the checkpoint setting the operator must know that Settings -> Checkpointing -> Checkpoint runner is where it is "unbound".

**Expected:** the checkpoint setting counts as a use, e.g. "Checkpoints" or "1 using it" with the title naming it, so a runner that cannot be deleted never reads Unused; ideally the 409 names where each holder is released ("... the project's checkpoint runner (Settings -> Checkpointing)"; "Manager job(s): conversation-titles"). **Test:** in `hub/ui/src/__tests__/runnersUi.test.tsx`, render the Runners section with project settings whose `checkpoint_runner_id` is a runner no agent or manager job holds, and assert its row does not read "Unused". Seam: Runners & models (Runners page) x Projects (settings, Checkpointing).

## F866 (C) -- a flow's stall reason for an unstaffed review says "this task names 'alpha' as its reviewer" in the Loops panel and on the loop, where "this task" names no task

**Status:** open 2026-10-21. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8159, Chromium against the served bundle).
**Source:** drive
**Theme:** Flows & review
**Ready:** yes
**Tier:** 0

Repro: F864's flow after its second firing. `GET /loops/{id}` -> `stall_reason`: "this task names 'alpha' as its reviewer, and that agent is the one that completed this task. Naming a different reviewer, or reviewing it yourself, ...". In Chromium, the conversation's side panel -> Loops shows the flow `stalled` with that line under it (screenshot `testbed/ui-judge/s1021-l/123619/loops-index.png`). The queue holds two tasks, and nothing on the line says which one waits. The sentence is written for the task's own story (where F768's fix also shows it, correctly) and is promoted verbatim to the loop's `stall_reason` (`hub/hub/scheduler.py:1627`, the ladder's reason, which `decide_firing` lifts). By contrast F819's stall reason names its task: "task-bd411ade853a ('Write E.txt') is still assigned to delta".

Expected: a loop-level stall reason names the task, e.g. "Add coefficient_of_variation() names 'alpha' as its reviewer, and alpha completed it. ...". **Test:** in the `decide_firing` tests for rung 1b, the stalled decision's `stall_reason` contains the task's title or id. Seam: Flows & review (review ladder) x Jobs & loops (stall reason).

## F867 (C) -- a loop's history reads the bare "loop tasks adopted." when it takes over an archived loop's unfinished tasks: no task, no source loop

**Status:** open 2026-10-21. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8159, Chromium against the served bundle).
**Source:** drive
**Theme:** Jobs & loops
**Ready:** yes
**Tier:** 0

Repro (`scripts/drive/s1021_l_loops.py adopt`): an approved two-task document with no delivery; loop A created on it (`enabled: false`) adopts both tasks; one task is rejected; `POST /jobs/{A}/archive`; loop B created on the same document -> the pending task moves to B (held: F53), and `event_logs` gets the `loop_tasks_adopted` pair, `{"from_loop": A, "to_loop": B, "task_ids": ["task-95df0452d781"]}`. In Chromium, loop B's Loop tab -> History reads "loop stopped. / **loop tasks adopted.** / The operator created this loop from the jobs page, ..." (screenshot `testbed/ui-judge/s1021-l/124329/looptab-loop-3d285888fed7.png`). `loopEventSentence` (`hub/ui/src/lib/loopHistory.ts:30-46`) knows `loop_created` and `loop_tasks_added`, and anything else falls to `event_type.replace(/_/g, ' ')`. The archived loop's history gets the same line, so neither side says what moved where. "loop stopped." is the same fallback and does not carry the stop reason either.

Side, same tab: Settings reads "Document: spdoc-e0968b6104bc", an id, where the rest of the app names the document by title or path.

Expected: "Took over 1 unfinished task from "loop A on the document" (archived): "Write M2.txt"." on B, and "Gave 1 unfinished task to "loop B adopts": ..." on A. The event carries ids only, so the sentence needs the titles (add them to the event as `loop_tasks_added` does, or resolve them in the history route). **Test:** `hub/ui/src/__tests__/loopHistory.test.ts`, a `loop_tasks_adopted` event renders a sentence naming its tasks and the other loop. Seam: Jobs & loops (history) x Spec documents (a document's tasks across loops).

## F908 (C) -- the Activity digest falls back to the event's wire name for every event it has no sentence for, credits the event's `agent` field as its actor, and drops the subject: "alpha task created", "alpha agent created", "question answered"

**Status:** open 2026-10-22. Found by the day sweep `sweep-traces-sweep` (same Hub and drive as F907; `scripts/drive/s1022_tr_ui.py digest|live`).
**Source:** drive
**Theme:** Logs, events & SSE
**Ready:** yes
**Tier:** 0

The operator created a task through `POST /projects/{p}/tasks` (`{"title": "Digest probe task", "assignee": "alpha"}`, 201) and later answered alpha's `ask_user` through `PATCH /projects/{p}/questions/q-1f71e74a46aa` (200). The digest, in Chromium:

```
alpha worked | Reply with the single word OK. | 2m 17s ...
question answered                       <- no who, no question
alpha question asked                    <- no question text ("Which colour for the border?")
alpha task created                      <- the operator created it; alpha is the assignee; no task title
alpha agent created
```

`task_created` is persisted with `agent=alpha` (the assignee) and data `{"id", "title"}`; the digest's `default:` branch (`hub/ui/src/lib/activityDigest.ts`) renders `lead: e.agent` + `e.event_type.replace(/_/g, ' ')`, and its `taskId` only reads `d.task_id` or `task_updated`'s `d.id`, so the title it holds never reaches the row. The file's own header says the digest replaces "every event by its wire name"; these are the commonest events of a project's first hour (agent created, task created, question asked/answered).

**Expected:** a sentence for `task_created` ("Task created", detail the title, no agent lead unless the event names an actor), `question_asked` ("alpha asked you", detail the question), `question_answered` ("You answered alpha", detail the question) -- neither event carries the question text (`question_asked` data is `{id, from_agent, blocking}`, `question_answered` is `{id, answer}` with `agent` null), so the digest looks it up by id the way it already looks up task titles (a `questionText` in `DigestContext`, from the questions query), `agent_created` ("alpha was added"); the default branch never leads with `e.agent` for an event whose actor it does not know. **Test:** in the `activityDigest.test.ts` F907 adds: a `task_created` event with `agent: 'alpha'` and `data: {id, title}` yields a row whose text is not "task created" and whose detail is the title; same for `question_asked` with its question. Seam: Logs, events & SSE x Tasks / Questions.

**Extended 2026-10-22** (day sweep `sweep-agents-sweep`, Chromium, `scripts/drive/s1022_ag_ui.py views`): `agent_removed` falls to the same fallback: the digest reads "gamma agent removed" / "delta agent removed" while the Logs view, on the same tab, reads "gamma was removed from the roster by a session sync" (F850's `eventSummary` sentence, which `buildDigest` does not use). A failed job firing reads "delta job fired · Runs as delta" (F925).

## F910 (C) -- the Overview says an agent blocked on the operator's question is "Working on ..." while the same screen says "Nothing running" and Needs you says it "is waiting"

**Status:** open 2026-10-22. Found by the day sweep `sweep-questions-sweep` (same Hub and drive as F909; `scripts/drive/s1022_qs_drive.py ask`, `s1022_qs_ui.py needs|keys`).
**Source:** drive
**Theme:** Questions
**Ready:** yes
**Tier:** 0

`alpha` asked "Which colour for the border?" (red/blue, blocking) in `conv-457c97270f66` and waited (`run-d62ae7299b06` `running`, question `asker_waiting` true, conversation `attention` "waiting"). The Overview, in Chromium (`testbed/ui-judge/s1022-questions/094012/needs_you.png`): summary "2 things need you · Nothing running", Running now "No agent is working right now", Needs you "alpha is waiting", and alpha's Agents card **"Working on “Reply with the single word OK.”"**. The conversation's own header read "working · 3m 13s" with Stop while the ask card stood below it.

Cause: the strip in `hub/ui/src/components/overview/OverviewScreen.tsx` (~l.136) ranks `a.status === 'running' || live` before `waiting`, the reverse of the Hub's rule ("Waiting outranks running: a run blocked on a question is still a running process, but what the operator needs to see is that it stopped for them", `hub/hub/conversations.py` `conversation_attention` docstring), which Running now and Needs you already follow.

**Expected:** an agent with a conversation whose `attention` is `waiting` reads "Waiting for your answer" on its card even while its status is `running`. **Test:** the OverviewScreen test: agent `status: 'running'`, its one conversation `attention: 'waiting'` -> the card's text is "Waiting for your answer", not "Working on". Fails today. (The header's "working" clock is the same disagreement in `ConversationBar`; fold it in if the same rule is reused, else leave it.) Seam: Questions x Overview.

## F911 (C) -- a question's "Open conversation" on the Overview opens the agent's newest conversation, not the one the question was asked in, so the operator lands where the ask card is not shown

**Status:** open 2026-10-22. Found by the day sweep `sweep-questions-sweep` (same Hub; `scripts/drive/s1022_qs_ui.py f804` then `needs`).
**Source:** drive
**Theme:** Questions
**Ready:** yes
**Tier:** 0

`alpha` waited on "Which colour for the border?" asked in conversation A (`conv-457c97270f66`); the operator then sent a message in alpha's other conversation B (`conv-16eaf2f51006`), so B was the newer. On the Overview, the question's row -> **Open conversation** navigated to `?agent=alpha&conversation=conv-16eaf2f51006` (B): no ask card (F804 scopes it to A, rightly), composer "alpha is busy in another conversation — a message here will queue", header "waiting on your answer in <A>" -- one more click to the question. With A the newer one, the same button landed on A (first `needs` run), so it depends on which conversation was touched last.

Cause: `OverviewScreen.tsx:90` builds the question row's primary action as ``onNavigate(`agent:${q.from_agent}`)`` (agent destination with `conversationId` null), although the question carries `conversation_id` and the screen already has `openConversation(agent, conversationId)` (l.67) that the Running rows use.

**Expected:** a question with a `conversation_id` opens that conversation; one without keeps the agent destination. **Test:** the OverviewScreen test: a question `{from_agent: 'alpha', conversation_id: 'conv-A'}` -> clicking Open conversation calls `onOpenConversation('alpha', 'conv-A')`. Fails today. Seam: Questions x Conversations.

## F912 (C) -- `PATCH /questions/{id}` accepts an empty answer, recording the question answered with nothing, and a label that is not one of its options

**Status:** open 2026-10-22. Found by the day sweep `sweep-questions-sweep` (same Hub; `scripts/drive/s1022_qs_drive.py probes`).
**Source:** drive
**Theme:** Questions
**Ready:** yes
**Tier:** 0

1. `alpha` waited on `q-469b2ee00e69` (options red/blue). `PATCH /projects/{p}/questions/q-469b2ee00e69` `{"answer": ""}` -> **200**, `answered: true, answer: "", answer_labels: []`. Alpha's tool returned it; the transcript: *"the answer returned as an empty string ... It appears the response was not captured correctly. Could you please provide your choice again?"* -- the turn ended asking in prose, and the question is closed (a real answer is now 409 `_REANSWER_DETAIL`).
2. `q-f499ff0210f2` (options yes/no): `{"answer": "maybe next week", "labels": ["maybe"]}` -> **200**, `answer_labels: ["maybe"]`, delivered to beta as new input.

The app's own forms refuse a blank answer (`AnswerForm.tsx:99`), so this is an API-only hole, but it is the state `2026-08-11-declining-a-question` D1 rejected by name ("a reader that finds `answered=True` with nothing in `answer` has to guess which case it is in"), and `labels` exists to carry *which options were chosen*. `QuestionAnswer` (`hub/hub/schemas/questions.py:45`) has no `min_length`, and `answer_question` (`hub/hub/api/v1/questions.py:498`) checks labels only for refused-capability questions.

**Expected:** a blank answer with no labels -> 400 "An answer cannot be empty; to close it without answering, decline it" (naming `POST /questions/{id}/decline`); a label not among the question's options -> 400 naming the options. **Test:** `hub/tests/` beside the F594 re-answer test: both bodies refused, the question still unanswered. Fails today. Seam: Questions (operator answer route).

## F914 (C) -- the Tasks screen's Dependencies view keeps the agent filter and the "Find a task" search on its toolbar and ignores both

**Status:** open 2026-10-22. Found by the day sweep `sweep-tasks-sweep` (scratch Hub :8114, profile tk1022, Chromium against the served bundle, `scripts/drive/s1022_tk_ui.py deps`).
**Source:** drive
**Theme:** Dependencies
**Ready:** yes
**Tier:** 0

Nine tasks (three from an approved change document, six made by hand; two assigned to `beta`). On the Board, the `beta` chip leaves two cards (`t-label`, `S`), as it should. Switch to **Dependencies**: the same toolbar is still there, chips and search box live, and:

```
Dependencies view, chip "beta" active + "Find a task" = "Add"  -> 8 rows (every task), not the 1-2 that match
Board view, chip "beta"                                        -> 2 cards
```

`BoardView.tsx:95` filters `visible` by `agentFilter` and `query`, but the Dependencies branch (`BoardView.tsx:155`) renders `children`, a `DependencyListView` that `TasksScreen.tsx:320` hands the unfiltered `tasks`. (The spec's requirement filter does apply there: `TasksScreen` applies it before both.) **Expected:** either the list honours the chip and the search (filter rows, keeping a matching row's chain context) or the toolbar hides them on that view; never controls that look active and do nothing. **Test:** a `BoardView`/`TasksScreen` vitest: `view="dependencies"`, chip `beta` selected -> only beta's rows (or no chips rendered). Fails today. Seam: Tasks (board toolbar) x Dependencies.

## F916 (C) -- deleting a task whose branch holds unmerged work: the confirm promises everything "goes with it", the drawer closes in silence, and the Activity tab's default view reads only "task checkout kept"

**Status:** open 2026-10-22. Found by the day sweep `sweep-tasks-sweep` re-driving F836 in Chromium (scratch Hub :8114, `scripts/drive/s1022_tk_ui.py delete t-label`). The residual F836 recorded as "not done", plus a part its fix cannot reach.
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** yes
**Tier:** 0

`t-label` worked by a real Haiku turn: commit `a11c5d6` on `agentweave/task/task-f5d5eb6aa258`, task `completed`, not merged. In Chromium:

```
drawer -> Details -> Delete -> confirm: "Delete this task? Its own prerequisites, links, transitions and evidence go with it. This cannot be undone."
Delete task -> drawer closes; page text has no "kept", "branch" or "unmerged"
Activity tab, default "Activity" view (the digest): "10:02 (warning) task checkout kept"  /  "10:02 task deleted"     (no branch, count or title)
Activity tab, "Logs" view : "task_checkout_kept  Kept agentweave/task/task-f5d5eb6aa258 (1 unmerged commit) from deleted task "Add discounted_label()""   <- F836's sentence
Project settings -> Worktrees: "Task deleted -- its work is kept on this branch."                                                                      <- held
```

F836's sentence lives in `eventSummary`, which only `EventRow` and `LogLine` use; the Activity view is `ActivityDigest`, whose default branch (`lib/activityDigest.ts:165`) prints the wire name (the general case is F908). So the one warning that work survived a delete is unreadable where the operator lands. **Expected:** (1) when the task's checkout holds unmerged commits, the confirm says the branch and its commits will be kept (the drawer can read it from `GET /worktrees`' row for the task's checkout); (2) the digest's default branch falls back to `eventSummary(e)` before the wire name, which gives this row and `task_deleted` ("Deleted "Add discounted_label()"") their sentences and narrows F908. **Tests:** `activityDigest.test.ts`: a `task_checkout_kept` event with `{branch, unmerged_commits: 1, title}` yields text containing the branch and the title; a drawer test: a task whose checkout row has unmerged commits gets a confirm naming the branch. Both fail today. Seam: Tasks (delete) x Worktrees x Activity digest.

## F920 (C) -- the Vault's Add dialog promises folders ("Files or folders", "Drop files or a folder ... Hidden files are skipped"), but its picker refuses a folder and a dropped hidden file vanishes without a word

**Status:** open 2026-10-22. Found by the day sweep `sweep-vault-sweep` in Chromium (scratch Hub :8115, `scripts/drive/s1022_vt_ui.py add,drop`) plus the code it points at.
**Source:** drive
**Theme:** Knowledge vault
**Ready:** yes
**Tier:** 0

```
Vault -> Add: segmented "Files or folders", drop zone "Drop files or a folder or browse", hint "Text, Markdown, PDF and images. Hidden files are skipped."
set_input_files(<folder>) on the drop zone's input  -> "Error: File input does not support directories, pass individual files instead"
page drop of one file named ".env"                  -> the dialog opens with an empty list and "Choose or drop at least one file."; nothing says .env was skipped
grep -rn "webkitdirectory\|webkitGetAsEntry" hub/ui/src  -> nothing
```

The input in `DropZone` (`hub/ui/src/components/ui/dropzone.tsx`) has no `webkitdirectory`, and neither `DropZone.onDrop` nor `usePageDrop` walks `DataTransferItem.webkitGetAsEntry()`, so a folder can be neither browsed nor dropped; `visibleFiles` (`VaultAddDialog.tsx`) and the folder-path naming in `VaultScreen.add` read `webkitRelativePath`, which nothing ever sets. (A real OS folder drop arrives in `dataTransfer.files` as one zero-byte entry whose `File.text()` rejects, so it would come back "it could not be read as text" -- inferred from the code, not driven: Playwright cannot drop a real folder.) The only way to add a folder is the path door (`POST /vault/paths`, `vault_add`, the CLI). **Expected:** either the dialog adds folders (a folder input with `webkitdirectory`, and drops walked through `webkitGetAsEntry`, hidden names skipped as the path door does), or it stops promising them ("Files", "Drop files"); and a skipped hidden file is listed as skipped ("1 hidden file skipped: .env") instead of disappearing. **Test:** `VaultAddDialog` test: a drop of `[File(".env")]` renders a line naming `.env` as skipped; and, if folders are kept, a folder input exists with `webkitdirectory`. Fail today. Seam: Vault Add dialog x `DropZone` / `usePageDrop`.

## F921 (C) -- `PATCH /manager/jobs/{key}` with only a new `runner_id` keeps a model the new runner's CLI does not declare; the firing then runs on that CLI and records the undeclared model

**Status:** open 2026-10-22. Found by the day sweep `sweep-vault-sweep` (scratch Hub :8115, `scripts/drive/s1022_vt_drive.py manager` and a one-off firing).
**Source:** drive
**Theme:** Manager jobs
**Ready:** yes
**Tier:** 0

```
PATCH .../manager/jobs/vault-distillation {"runner_id": <claude runner>, "model": "claude-haiku-4-5-20251001"} -> 200
PATCH .../manager/jobs/vault-distillation {"runner_id": <copilot runner>}                                      -> 200, model still "claude-haiku-4-5-20251001"
the same pair in one call: {"runner_id": <copilot runner>, "model": "claude-haiku-4-5-20251001"}
  -> 400 "'claude-haiku-4-5-20251001' is not a model 'copilot' declares; expected one of: auto, ..., claude-haiku-4.5, ..."
enable + upload a note -> firing: cli "copilot", model "claude-haiku-4-5-20251001", outcome "empty", usage {"premium_requests": 1.0}
PATCH ... {"runner_id": ""} -> 200, runner_id stored as "" (not null)
```

The route (`hub/hub/api/v1/manager.py`, `update_manager_job`) judges the model only when the request sets one (F630's fix), so a runner change carries the old CLI's model across. The Manager screen guards it (`ManagerSettings.tsx` `chooseRunner` clears the model when the CLI changes), so only an API caller reaches it today; the firing record then names a model the CLI never ran (Copilot used its own), and the screen shows that model under a Copilot runner. **Expected:** when `runner_id` changes and the stored model is not one the new runner's CLI declares, either clear it (as the screen does, and say so in the answer) or answer 400 with the sentence the one-call PATCH gives; an empty `runner_id` is 400 or treated as null, never stored as "". **Test:** `hub/tests/test_manager*.py`: set a claude runner + haiku model, PATCH a copilot runner alone -> the job's model is null (or 400); PATCH `{"runner_id": ""}` -> `runner_id` null or 400. Fail today. Seam: Manager jobs (API) x runner/model catalog.

## F926 (C) -- deleting a charter an agent holds asks the operator to confirm the loss of its text, then the Hub refuses; the refusal says "Unbind before deleting" without saying where, and focus drops to the page

**Status:** open 2026-10-22. Found by the day sweep `sweep-agents-sweep` (scratch Hub :8116, Chromium against the served bundle, `scripts/drive/s1022_ag_ui.py charters`; `testbed/ui-judge/s1022-ag-charters/103927/ch-3-bound-delete.png`).
**Source:** drive
**Theme:** Charters
**Ready:** yes
**Tier:** 0

Project settings -> Charters lists Developer with "alpha" beside it (bound). Its **Delete Developer** button opens `DeleteCharterDialog`: "Delete the charter "Developer"? Its 87 lines of authored text will be lost. AgentWeave keeps no copy -- there is no archive and no undo, so the only way back is to write it again." The operator confirms the irreversible loss; `DELETE /charters/{id}` -> 409 "Charter is bound to agent(s): alpha. Unbind before deleting."; the page shows "The charter was not deleted." with that sentence, and `document.activeElement` is `BODY` (the dialog closed, focus not returned to the Delete button). Nothing says that unbinding is done in alpha's settings -> Charter. The screen already knows the binding (`ChartersSection.tsx` passes `boundTo` to the row), so the confirm warns of a loss that cannot happen. Unbound delete holds: confirm names the line count, Cancel takes focus, Escape closes and focus returns to the Delete button, the row goes.

**Expected:** for a bound charter the Delete control does not open the loss confirm: it says the charter is held by alpha and that it is released in alpha's settings -> Charter (a link), or the Hub's sentence names that place; focus returns to the opener after a refusal. **Test:** `hub/ui/src/__tests__/` (ChartersSection): a charter whose `boundTo` is `["alpha"]` -> pressing Delete shows no "will be lost" text and names alpha; fails today. Seam: Charters (settings) x Agents (binding).

## F929 (C) -- the New job form says nothing when the Hub refuses the job: Create is pressed, the dialog stays open, and no sentence appears

**Status:** open 2026-10-22. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8117, profile lp1022, project `proj-042da656a1f4`, Chromium, `scripts/drive/s1022_lp_ui.py jobs` and `jobs2`; `testbed/ui-judge/s1022-lp/105956/06_past_stop_refused.png`, `.../105843/02_form_refused.png`).
**Source:** drive
**Theme:** Jobs & loops
**Ready:** yes
**Tier:** 0

Repro: Jobs -> **New job**, name "past loop", agent alpha, a message, **Make this a loop**, purpose "Drain the queue", Stop at `2020-01-01 00:00` -> **Create Job**. `POST /jobs` -> 422 `"stop_at 2020-01-01T00:00:00+00:00 has already passed, so the loop would stop at once; choose a later time. Nothing was changed"`. The dialog stays open with every field as typed, no `role=alert`, and no error line: the form's text ends "... Require accepted evidence before merging ... Cancel Create Job". The console logs a 422. No job was created. The same holds for cron `0 4 13 * 5` -> 400 (both day fields): the press adds nothing to the pre-submit ambiguity line, so the operator cannot tell that the press was refused. Any other Hub refusal of a create would be equally silent (an agent archived meanwhile, a roster typo after an API rename).

Cause: `JobsScreen.tsx:96` calls `createJob.mutate(job, { onSuccess: () => setShowForm(false) })` with no `onError`, `useCreateJob` (`api/jobs.ts:219`) has none either, and `JobForm`'s `error` state (`JobForm.tsx:39`) is local, with no prop for a server answer. This predates ui-finesse: the old `JobsPage.handleCreate` was the same. **Expected:** the Hub's sentence appears in the form's error line. That means `errorDetail` for a string `detail`, and the first `msg` of a 422 list without pydantic's "Value error, " prefix. The dialog stays open with the fields kept. **Test:** a JobsScreen test where the create mutation rejects with the 422 body above -> the dialog shows "has already passed". This fails today. Seam: Jobs & loops (form) x the jobs route's refusals.

## F931 (C) -- the Jobs tab's Archive confirm puts focus on the dialog's Close (X), not Cancel, and after Archive focus drops to the page

**Status:** open 2026-10-22. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8117, profile lp1022, project `proj-042da656a1f4`, Chromium, `scripts/drive/s1022_lp_ui.py jobs2`).
**Source:** drive
**Theme:** Keyboard & dialogs
**Ready:** yes
**Tier:** 0

Repro: Jobs -> a job's **More for ui probe** -> **Archive**. The confirm "Archive ui probe? It stops firing. Nothing is deleted ..." opens with `document.activeElement` = the header's `BUTTON aria-label="Close"`, not **Cancel**. Pressing **Archive** closes it, the row goes, and focus is `BODY` (measured for two jobs). The checklist's dialog rule is that a confirm takes focus on Cancel and that focus returns to something sensible after. Cause: `DialogContent` (`hub/ui/src/components/ui/dialog.tsx:14-45`) renders the Radix `Close` first and sets no initial focus, so Radix focuses the first focusable element. `JobsView.tsx:376-400` uses it as is. The older D5 dialogs mark their initial control with `data-dialog-initial-focus` (`useDialogFocus`). Other `DialogContent` users (`AgentSettingsSections.tsx`, `GeneralSettings.tsx`, `VaultAddDialog.tsx`, `VaultStorageDialog.tsx`) were not measured here. **Expected:** the archive confirm focuses Cancel (`onOpenAutoFocus` on `DialogContent`, or an `initialFocus` prop), and after Archive focus moves to the Jobs list or **New job**. **Test:** a JobsView test: open the archive confirm -> the active element is Cancel. This fails today. Seam: Keyboard & dialogs x Jobs & loops.

**Widened 2026-10-23** (day sweep `sweep-projects-sweep`, Keyboard & dialogs row, :8118, profile kb1023): **F931 still reproduces (initial focus), widened:** the agent's **Archive…** confirm (`AgentSettingsSections.tsx:143-166`, settings → Identity) opens with focus on the header's Close (X), not **Keep alpha** (`s1023_kb_dialogs.py archive-agent`). Escape then returns focus to Archive… (held, it has a `DialogTrigger`). The Vault Add and Vault storage dialogs also open on the X. They are forms, so this matters less there. F931's "after Archive focus drops to the page" half has the same cause as F1029 (no `DialogTrigger`).

## F932 (C) -- deleting a document whose flow has finished also deletes the flow's job, its loop and every firing record, and nothing says so: not the confirm, not the answer, not the event

**Status:** open 2026-10-22. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8117, profile lp1022, project `proj-042da656a1f4`; `scripts/drive/s1022_lp_drive.py`, then the delete by API).
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

Repro: an approved change with `delivery: {mode: flow}`. Its flow (job-7d424efaf227, loop-e98571ee8723) built and reviewed both tasks, which were merged, and ended `completed` with 5 firing rows. `DELETE /projects/{p}/project/documents/spec/changes/ivory-kirin/spec.json` -> 200 `{"path": ..., "deleted": true, "tasks": [2 ids], "requirements": 2, "kept_work": [], "diagnostics": []}`. The `spec_document_deleted` event carries `{path, tasks}`. Afterwards `GET /jobs?include_archived=true` no longer lists the flow, `GET /jobs/{id}/history` and `GET /loops/{id}` are 404, and `job_runs` for it count 0. The Spec page's confirm (`useSpecPhaseControls.tsx:761-762`) says "Its file, its requirements and their evidence, and every task it put on the board go with it." It says nothing about the flow. Elsewhere the product promises that a job's history outlives it: the Jobs tab's archive confirm says "Nothing is deleted: its history stays, listed under Archived", and the skill and docs say jobs cannot be deleted, only archived. The cascade itself is deliberate (`hub/hub/deletion.py` docstring: "its stopped flows"; `:267-303`). What is missing is saying so. `DeletedDocument` (`deletion.py:135`) has no field for it. **Expected:** the confirm names the document's flow, if it has one ("and its flow <name>, with its N firings"), and the answer and the event list the job and loop ids deleted. The alternative is a design call for the operator: the flow's job is archived instead of deleted, so its history stays. **Test:** `hub/tests/test_deletion*.py`: delete a document whose stopped flow has firings -> the response names the job (`flows: [{job_id, loop_id, firings}]`). This fails today. Seam: Spec documents (delete) x Jobs & loops.

## F934 (C) -- the `allow_agent_jobs` refusal, its question and its answer send the operator to "Environment › Settings" and "their Questions destination", and neither exists any more

**Status:** open 2026-10-22. Found by the day sweep `sweep-reach-sweep` (scratch Hub :8118, profile rc1022, project `proj-9c9bf6db138b`; `scripts/drive/s1022_rc_drive.py job`).
**Source:** drive
**Theme:** Operator surfaces
**Ready:** yes
**Tier:** 0

Repro: with `allow_agent_jobs` off, agent beta (call mode) ran `aw-tool create_job .agentweave/calls/3.json` (`run-1dc6ef5d6306`). The answer was 403 `project_setting_blocks_capability`, with the sentence: "The operator has been asked whether to enable it — question `q-cac95431869c`, on their Questions destination; the setting itself is at Environment › Settings." The question `q-cac95431869c` says "You change it yourself at Environment › Settings", and both options repeat it. After `PUT /settings {"allow_agent_jobs": true}`, the recorded answer reads "Enabled it — go ahead (the operator turned allow_agent_jobs on in Environment › Settings)". Since ui-finesse there is no "Environment" anywhere in the app. The setting is Project settings -> General -> Collaboration -> "Agents may start jobs, flows and loops" (`GeneralSettings.tsx:115`), and also the Overview's Collaboration toggle (`CollaborationSummary.tsx:64`). The Questions takeover is gone too (F904): the question is a row in the Overview's **Needs you**. Source: `hub/hub/refused_capability.py:83` (`where_changed`), `:89`, `:97`, `:293`, `:392`. The tool descriptions agents read repeat "Questions destination" (`mcp_server.py:831, 889, 981, 1112, 1124`; the call-mode list carries the same text). What held: the refusal is otherwise legible, the question was raised, and the grant answered it and reached beta, whose next turn created the job (`job-2d78515a2604`, disabled). **Expected:** "Project settings › General" (or the Overview's Collaboration block), and "in Needs you on the Overview". **Test:** `hub/tests/test_refused_capability*.py`: the refusal detail, the question and the auto-answer contain neither "Environment" nor "Questions destination". This fails today. Seam: Capability plane x Questions.

## F935 (C) -- the Granted reach row promises "writes outside are still recorded on the run", but a shell write into a granted folder, the very case the row says needs read and write, is never recorded

**Status:** open 2026-10-22. Found by the day sweep `sweep-reach-sweep` (scratch Hub :8118, profile rc1022, project `proj-9c9bf6db138b`; `scripts/drive/s1022_rc_drive.py outside`).
**Source:** drive
**Theme:** Permissions & sandbox
**Ready:** yes
**Tier:** 0

Repro: project `reach_grants: {roots: [{path: <testbed>\reach1022-outside, access: readwrite}]}`. alpha under Workspace only (`run-d3e8e90f56ef`) ran `Set-Content -Path '<...>/reach1022-outside/written.txt'`, which was allowed, and the file exists. It then ran `Set-Content` to an ungranted `testbed/not-granted.txt`, which was refused: "Denied: '...not-granted.txt' is outside your workspace." The run row reads `outside_workspace_writes = '[]'`, and no `agent_wrote_outside_workspace` event was written. The Granted reach row (`GeneralSettings.tsx:212`) says: "folders and hosts an agent may use beyond its workspace (a shell command needs read and write). A guardrail against mistakes, not a sandbox; writes outside are still recorded on the run." The recorder sees only file-tool paths (`workspace_writes.py:42-63`). Shell writes are out of its scope by the operator's design (F281, closed B11). So the promise is false for exactly the shell write the grant enables. **Expected:** the copy says what is recorded, for example "a file tool's writes outside are recorded on the run; a shell command's are not". It must not imply a record that F281 decided not to keep. **Test:** a `GeneralSettings` test: the Granted reach description does not claim shell writes are recorded. Seam: Permissions & sandbox (reach copy) x Runs (outside-write record).

## F940 (C) -- deleting a runner is one click on a hover icon, with no confirmation and no undo, unlike a charter; a provider runner's base URL and key-variable name go with it

**Status:** open 2026-10-22. Found by the day sweep `sweep-projects-sweep` (Chromium, scratch Hub :8119; `scripts/drive/s1022_pj_ui.py runners`).
**Source:** drive
**Theme:** Runners & models
**Ready:** yes
**Tier:** 0

Repro: Project settings -> Runners, then focus or hover the row `kb-haiku` (unused) and press its **Delete kb-haiku** icon. No dialog opens (`dialog` count 0). The toast says "kb-haiku deleted", and `GET /runners` no longer has it. The toast has no Undo, although `toast()` supports an action. `RunnersSection.tsx:81-88` calls `deleteRunner.mutate` straight from the row button (`RunnersSettings.tsx:92`). Charters, one section below, open `DeleteCharterDialog` first, because "a charter delete is a hard delete" (F186, `ChartersSection.tsx:12`). A runner delete is just as hard, and it carries the runner's model, flags, and for a Copilot provider runner the `base_url` and `api_key_var` the operator typed. The Edit icon sits beside Delete, 1 icon-width apart (`aw-list-actions`), so one mis-click loses the runner. A held runner is refused safely (409 "Runner is bound to agent(s): alpha. Unbind before deleting." shown under the heading: held). **Expected:** Delete asks first ("Delete the runner kb-haiku? Agents and jobs cannot use it afterwards."), with Cancel focused, as charters do. An Undo toast is an acceptable alternative. **Test:** `runnersUi.test.tsx`: clicking Delete on a row opens a dialog and sends no DELETE until it is confirmed. This fails today. Seam: Runners & models x Keyboard & dialogs.

## F942 (C) -- a Copilot provider runner whose key variable starts with `AW_` is refused as "one of the Hub's own credentials", even for a name that is no credential at all; the refusal never says `AW_` names are reserved

**Status:** open 2026-10-22. Found by the day sweep `sweep-projects-sweep` (Chromium, scratch Hub :8119, the runner dialog; `scripts/drive/s1022_pj_ui.py extra`).
**Source:** drive
**Theme:** Runners & models
**Ready:** yes
**Tier:** 0

Repro: New runner -> CLI copilot -> "Send runs to a model provider with your own API key" -> Key variable name `AW_DRIVE_NOT_SET_1022`, model Fable 5, then Save. The dialog's alert says "api_key_var names one of the Hub's own credentials (AW_DRIVE_NOT_SET_1022), and a runner with a model provider sends that variable's value to its base_url. Name a variable that holds the provider's API key." The variable is set nowhere and is no Hub credential. `runner_provider.py:158` refuses `api_key_var in _HUB_CREDENTIAL_NAMES or api_key_var.startswith("AW_")` with one sentence for both. An operator who reads it as "that name is taken" will try `AW_ANTHROPIC_KEY` and be refused again with no clue why. The same body over `POST /runners` gives the same 400. Held: a non-`AW_` name that is unset (`MY_DRIVE_UNSET_KEY`) is stored (201), and `GET /runners/launchability` names the fix: "... $MY_DRIVE_UNSET_KEY, is not set in the Hub's environment. Set it and restart the Hub." **Expected:** two sentences. A name in `_HUB_CREDENTIAL_NAMES` keeps today's wording. An `AW_` prefix says "Names starting AW_ are reserved for the Hub's own settings; use another name, such as ANTHROPIC_API_KEY." **Test:** `provider_config_problem({"type": "anthropic", "api_key_var": "AW_X"}, "copilot")` mentions "AW_" and "reserved". This fails today. Seam: Runners & models (refusal legibility).

## F947 (C) -- the requirements popover says a merged requirement is "on master" on a project whose main branch is `main`

**Status:** open 2026-10-22. Found by the day sweep `sweep-spec-sweep` (Chromium, scratch Hub :8121).
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

Repro: project `sp-main`, a git repo initialised with `-b main`; `GET /projects/{p}/settings` shows `main_branch: "main"`. A real Haiku turn worked FR-1, the operator accepted the evidence, and **Land** merged the work (`43e2e3c Integrate approved work db865390ffa9` on `main`; coverage `FR-1 verified integrated`). The header's requirements popover then reads "FR-1 Verified on master". There is no `master` branch in that repository. `SpecHealthLine.tsx:116` hard-codes the word: `r.integration === 'integrated' ? 'on master' : ...`, and `grep -rn "on master" hub/ui/src` finds no other place. The operator of a `main` (or `trunk`) project is told the work is on a branch that does not exist. **Expected:** "on main", "on the main line", or the project's `main_branch` passed in. **Test:** `SpecHealthLine.test.tsx`: an `integrated` row renders no "master" when the main branch passed is `main`. This fails today. Seam: Spec documents (header) x Worktrees & integration.

## F948 (C) -- the Spec header's keyboard layers: Archive and Delete confirms do not take focus, Ctrl+Shift+K opens the command palette under the document search, and a refused Approve drops focus to `<body>`

**Status:** open 2026-10-22. Found by the day sweep `sweep-spec-sweep` (Chromium, scratch Hub :8121; `scripts/drive/s1022_sp_focus.py`, `s1022_sp_keys.py`, `s1022_sp_actions.py`).
**Source:** drive
**Theme:** Keyboard & dialogs
**Ready:** yes
**Tier:** 0

Three repros on `spec/changes/hdr-explore/spec.json` and `hdr-proposed`.

(1) More actions → Delete document… (or Archive). The dialog opens, but 200 ms and 1500 ms later `document.activeElement` is still `spec-more-actions` behind the modal (`closest('[role=dialog]')` is false). The keyboard rule says a confirm takes focus on Cancel. One Tab moves focus to Cancel. Escape then closes the dialog and focus falls to `<body>`, not to More actions. The items are `MenuItem onSelect={onDelete}` / `onArchive` (`SpecDocumentHeader.tsx:169-174`). Radix's DropdownMenu returns focus to its trigger after `onSelect`, and that wins over the dialog's own initial focus. On 2026-10-20 the same dialogs took focus when they opened from the phase bar (F829's drive, before a8ca6e2 moved them into the menu), so this is a regression of the move.

(2) Ctrl+Shift+K, the shortcut the breadcrumb's tooltip advertises ("choose another document (Ctrl+Shift+K)"), opens two dialogs: `['Command palette', 'Search documents']`. The first Escape closes only the document search and leaves the palette open with focus in its input. It takes a second Escape. `CommandPalette.tsx:76-77` checks `ctrlKey` and `k` but not `!shiftKey`, so both handlers fire (`SpecPage.tsx:122`).

(3) Pressing the primary **Approve** on a proposed document with gaps: the 409 renders "Not approved: the Hub found these gaps… Approve anyway", and focus is on `<body>`, although the Approve button is still on screen (`useSpecPhaseControls`; the button is disabled while busy, so it loses focus). The keyboard user has to Tab from the top of the page to reach "Approve anyway". This is the same class as F941.

**Expected:** (1) the confirm takes focus on Cancel and gives it back to More actions. Open the dialog after the menu has closed, or use `onCloseAutoFocus={e => e.preventDefault()}` when an item opens a dialog. (2) the palette ignores Shift+K. (3) focus moves to Approve anyway, or stays on Approve. **Tests:** `specDocumentHeader.test.tsx`: Delete from the menu, then the active element is inside the dialog. `CommandPalette.test.tsx`: Ctrl+Shift+K does not open it. All fail today. Seam: Keyboard & dialogs x Spec documents.

**Widened 2026-10-23** (day sweep `sweep-projects-sweep`, Keyboard & dialogs row, :8118, profile kb1023): **F948 (1) still reproduces, and is wider than the Spec header's Archive/Delete.** Measured again 2026-10-23 (`scripts/drive/s1023_kb_spec.py`, `s1023_kb_conv.py sheets`; shots `testbed/ui-judge/s1023-kb/spec_menu_*.png`, `conv_checkpoints_sheet.png`). Every dialog opened from a Radix menu item behaves the same way. At +200 ms and +1500 ms, focus is still on the menu trigger behind the scrim. Escape closes the dialog and focus is `BODY`. Instances: Spec header **More actions → Start a flow…** (`useSpecPhaseControls.tsx:461`), **Archive…**, **Delete document…** (`SpecDocumentHeader.tsx:169-174`), **Retire capability…** on a capability (`useSpecPhaseControls.tsx:475-479`), and the conversation bar's **More conversation actions → Checkpoints** (`ConversationBar.tsx:197` → `CheckpointsPanel.tsx:104`). The same dialogs opened from a plain button hold. **Fold into capability…** (primary button) opens on Cancel and returns focus to the button. One shared fix in the `MenuItem`-opens-a-dialog path covers all five.

**Widened 2026-10-23** (day sweep `sweep-projects-sweep`, Keyboard & dialogs row, :8118, profile kb1023): **F948 (2) still reproduces in a second place:** in a conversation, Ctrl+Shift+K (`ConversationView.tsx:142-150`) opens `['Command palette', 'Search documents']`, and it takes two Escapes (`s1023_kb_conv.py shiftk`). The cause is the same: `CommandPalette.tsx:76-77` does not check `!shiftKey`.

## F949 (C) -- every new document, and every phase move the Hub itself makes, lights a warn-toned "index issue" on every document's header until someone presses Rebuild, and the index details say "Choose it." / "Adopt it first." with no control or pointer to where that is done

**Status:** open 2026-10-22. Found by the day sweep `sweep-spec-sweep` (API and Chromium, scratch Hub :8121).
**Source:** drive
**Theme:** Corpus & folding
**Ready:** yes
**Tier:** 1

Repro, `GET /project/specs` diagnostics after each step on a project whose index had just been rebuilt with a home (`manifest.state: valid`): `POST /project/documents` (new `hdr-new2`) adds `unfiled_document`. Approving `hdr-proposed` through the app adds `intrinsic_metadata_conflict` ("the index records status 'proposed', but the document says 'approved'. Rebuilding the index takes the document's value."). The header of **every** document (not just the one concerned) shows an amber "1 index issue", then "2", then "3". Before any home is chosen, the second document created already lights "1 index issue" on all of them. Show details then reads "The index was not written: more than one document could be the corpus's home (…). Choose it." The detail panel (`SpecDocumentPanel.tsx`, `detail === 'index'`) has no Rebuild, home select or Adopt. Those live in the document search (breadcrumb → `SpecCorpusStrip`), and nothing points there. Held: the corpus strip in the search dialog does work. Rebuild asked "Which document is the corpus's home?", and "Rebuild with this home" wrote the index ("Index: home is Road · Indexed 5 documents"). Adopt is offered for the untracked file. F643 (fixed) noted the same churn: "Every newly created document shows as `unfiled_document` until someone presses Rebuild." Only its wording was fixed. **Expected:** the Hub keeps the index current on its own writes (create, phase move; rename already does since F730), so the header's index fact means a real divergence: a hand-edited file or an untracked document. The detail names its fix in place: a Rebuild/Adopt button, or "Open the document search (Ctrl+Shift+K) to choose the home". **Test:** a Hub test: create a second document and approve a first on a valid index, then `/specs` diagnostics is `[]`. This fails today. Tier 1, because it changes when `spec/index.json` is written. Seam: Corpus & folding x Spec documents (header).

## F957 (C) -- after F852, an unnamed piece at main's tip is still presented as the task's work to merge: the coverage bar says "Accepting may merge commit 8d3c6cebc6b3 into main", and Land's refusal says "This task's work has been recorded … FR-3 at 8d3c6cebc6b3 … merge none of it"

**Status:** open 2026-10-22. Found by the day sweep `sweep-evidence-sweep` (scratch Hub :8124, a real Haiku `builder` turn, Chromium on the served bundle: `scripts/drive/s1022_ev_drive.py nowork`, `s1022_ev_ui.py`, shot `testbed/ui-judge/s1022-evidence/124119/05_bar_FR-3.png`).
**Source:** drive
**Theme:** Requirements & evidence
**Ready:** yes
**Tier:** 0

Repro: master's HEAD is `8d3c6ce` "sort names (made for FR-1)". builder, on t-total (FR-3) in a fresh task checkout, edits nothing and records FR-3 with no commit and no locator -> `ev-aca5b49fff70` awaiting, footprint `8d3c6ceb… on agentweave/task/task-e3d11413a518`, `commit_named 0`, `reachable_from_main 1`. F852's fix holds: `GET /spec/evidence/ev-aca5b49fff70/diff` -> `files: []` and "this piece names no commit; … already on the main line, which is not work of its own, so there is no work to diff". Two other surfaces still present that commit as the piece's work. (1) The coverage bar, Show details -> Evidence (1) for FR-3: "total() printed 6 — builder · 8d3c6cebc6b3 on agentweave/task/task-e3d11413a518 · task-e3d11413a518 · awaiting [Accept] **Accepting may merge commit 8d3c6cebc6b3 into main** for an approved task that serves this requirement and is waiting on it." The commit is main's tip, so nothing can merge. `EvidencePieces.tsx:94-98` shows the note for any awaiting piece with a commit; it reads neither `reachable_from_main` nor whether the piece named a commit. The same row names the task by raw id (`EvidencePieces.tsx:71`), where the Evidence view names it "Check total()". (2) `PATCH` t-total -> completed, then `POST /tasks/task-e3d11413a518/land` -> 409 `gate_unsatisfied`, message "This task's work has been recorded and nobody has judged it: FR-3 at 8d3c6cebc6b3. Approving now would record that the work is good and merge none of it…" (`requirement_gate.py:405-417`). After accepting, Land answered 200 with no merge, as it should: there was no work. **Expected:** the merge note shows only when the piece's commit is not already on the main line (`footprint.reachable_from_main` false); an unnamed piece at main's tip says "names no work of its own" there instead. The gate sentence names such a piece as "FR-3 (no work of its own; recorded at main's 8d3c6cebc6b3)", not as work to merge. The bar names the task by its title. **Test:** `EvidencePieces.test.tsx`: an awaiting piece with `reachable_from_main: true` renders no `evidence-merge-note-*`; `test_requirement_gate`: an unaccepted entry for an unnamed footprint on main's first-parent chain does not say "merge none of it".

## F958 (C) -- Scan for drift that cannot read the repository answers "Scanned the project: 0 new — 0 on this document", the same as a clean scan

**Status:** open 2026-10-22. Found by the day sweep `sweep-evidence-sweep` (scratch Hub :8124, `scripts/drive/s1022_ev_drift.py`, Chromium `s1022_ev_ui2.py`, shot `testbed/ui-judge/s1022-evidence-drift/124305/02_scan_no_repo.png`).
**Source:** drive
**Theme:** Drift
**Ready:** yes
**Tier:** 0

Repro: FR-2's accepted piece `ev-fb9afe324ba9` watches `todo/items.py` and is merged to master (`reachable_from_main` 1). A watched commit, then `POST /spec/drift/detect` -> 200 `{"raised": ["drift-dadfd49e8675"]}`: scanning works. Move the project's `.git` aside, and `POST /spec/drift/detect` -> **200 `{"raised": [], "rebuilt": 0}`**. On the Spec page, the drift strip's **Scan for drift** reads "Scanned the project: 0 new — 0 on this document". (The diff route, by contrast, says "commit a864355a45e6 is not in this repository".) `requirement_evidence.detect_drift` skips a footprint silently when `main_ref` is None (`:1956`) or `tree_entries` cannot read the ref (`:1966-1971`). So an unreadable repository, a renamed main branch, or a footprint's line of work whose branch was deleted (a task delete discards its branch, F828) each produce a scan that reports nothing and looks clean (only the unreadable repository was driven; the other two are read from the code). Accepted evidence then goes unwatched with no word. **Expected:** the detect response lists what it could not scan (`unscanned: [{evidence_id, identifier, reason}]`, or one `reason` when the repository is unreadable), and the strip says it ("Scanned the project: 0 new — 1 piece could not be checked: …"). **Test:** `test_drift_*`: detect with a footprint whose branch was deleted answers it under `unscanned` with a reason (fails today: `raised: []` and nothing else).

## F1034 (C) -- a Haiku planner writes a whole change document in one turn, never asks the operator or calls `advance_spec_step`, so the document stays at `intake` and approval always warns `steps_skipped`

**Status:** open 2026-10-22. Found by the docs-rework drive (throwaway Hub :8012, demo project "Northwind Invoicing", planner on claude-haiku-4-5), spec `invoice-csv-totals-row-and-half-up-tax-rounding`.
**Source:** drive
**Theme:** Spec documents
**Ready:** no
**Tier:** 1

Asked in a conversation to plan a change, the planner filled every section (4 requirements, 6 acceptance criteria, tasks, delivery) in one turn and proposed it. It never called `ask_user` at a step boundary nor `advance_spec_step` (`hub/hub/mcp_server.py:5207`), although the journey's instructions say to (`hub/hub/spec_journey.py:427`, `:550`). The document was left at step `intake`, so approval answered `steps_skipped` (the F830 recipe) and the operator had to use Approve anyway. It also created the document's two tasks itself with `create_task` instead of letting approval or the document's tasks section produce them. F574 is the operator-written variant (fixed by naming the journey call); this is the agent-written one, where the step protocol is simply not followed. **Open question for the fix (why Ready: no):** whether an agent writing later steps' content should move the step itself (the content-based option F574 declined), or the planner's instructions should make the step calls unmissable. **Test:** an e2e drive where a Haiku planner plans a small change and the document reaches its last journey step, or approval does not warn `steps_skipped` (fails today).

## F1035 (C) -- `hub/.env.example` tells the reader the CLI fetches the key "via `agentweave hub start` or `agentweave activate`", two commands that no longer exist

**Status:** open 2026-10-22. Found while rewriting the docs (env-variables reference).
**Source:** code
**Theme:** CLI & lifecycle
**Ready:** yes
**Tier:** 0

`hub/.env.example:17`. The CLI's subcommands are `doctor`, `status`, `stop`, `reset`, `vault` (`src/agentweave/cli.py:1834-1909`); the Hub is started by bare `agentweave` (`cmd_hub_start`, `cli.py:1403`). There is no `activate`. **Expected:** the comment names bare `agentweave` (or drops the sentence: the key is auto-generated and the app needs no copy of it). **Test:** extend the docs/command consistency check, if one covers example files, to `hub/.env.example`; otherwise a text edit with no test.

## F962 (C) -- after Copilot compacts a conversation, its context meter keeps the pre-compaction reading: the header says "104,485 / 128,000 · 81.63%" directly above the card "Copilot compacted this conversation automatically (104,485 → 32,455 tokens of 128,000)"

**Status:** open 2026-10-23. Found by the day sweep `sweep-checkpoints-sweep` (scratch Hub :8112, profile `ck1023`, zero spend: the Copilot stub `scripts/drive/s1018_A_copilot_stub.py`; `scripts/drive/s1023_ck_fill.py`, Chromium `s1023_ck_ui.py conv`, shot `testbed/ui-judge/s1023-ck-conv/100832/convcop.png`).
**Source:** drive
**Theme:** Checkpoints
**Ready:** yes
**Tier:** 0

Repro: agent `cop` on a Copilot provider runner aimed at the stub. Ten operator messages of 9,990 characters each into one conversation, `s1023_ck_fill.py cop 30`. Copilot's `usage_update` readings climb 42,395 → 97,588 (76.24%) → 104,485 (81.63%). On that turn Copilot compacts on its own: a `status` output "Copilot compacted this conversation automatically (104,485 → 32,455 tokens of 128,000)" at 09:07:52.256. The turn's last reading is the `context_warning` at 09:07:52.020, before the compaction. After the run, `GET /conversations?agent=cop` gives `context_usage` 104,485 / 81.63%, and the conversation header shows "104,485 / 128,000 · 81.63%", "Context window Used 104,485 tok", with the compaction card right under it. Nothing records the post-compaction size until the next turn's `usage_update`. (On the next turn, Copilot reported 111,450 and compacted again to 32,522. Under a stub summariser that is Copilot's own count, not the Hub's, and it is not part of this finding.) What held: the compaction is relayed with both sizes; it counts as the threshold (`consider_from_compaction`), and the offered banner with Checkpoint now is shown; "final" is correctly not raised for an undismissed conversation (`checkpoint_trigger.py:268`).

Seam: Copilot readings come only from ACP `usage_update` (`copilot_acp.usage_sample`, `hub/hub/copilot_acp.py:1711`). `_compaction` (`:1390-1452`) has `postCompactionTokens` and `tokenLimit` in hand and emits only the `compacted` status. **Expected:** a successful compaction with a post count and a limit also records a context reading (`context_tokens = post`, `limit_tokens = tokenLimit`, `source: copilot_acp`), so the meter agrees with the card at once. A compaction with no post count changes nothing. **Test:** in `hub/tests/test_copilot_acp*.py`, feeding a `session.compaction_complete` with `preCompactionTokens: 104485, postCompactionTokens: 32455, tokenLimit: 128000` yields a usage sample of 32,455 / 128,000 after the `compacted` event. This fails today, since only the status is emitted.

## F965 (C) -- an agent asking to move a task out of `blocked` after its own cannot-satisfy report is refused with the sentence for a question wait ("the operator answers or declines the question, or your own wait for it expires and ask_user reports that"), though no question exists

**Status:** open 2026-10-23. Found by the day sweep `sweep-spec-sweep` (scratch Hub :8114; `run-8c0cb4d9ab69`, real Haiku 4.5 turn).
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

Repro: `task-ddc3099981de` is `blocked` with `blocked_reason` "cannot satisfy criterion c-fast: …" (set by `report_cannot_satisfy`, `spec_amendments.py:512`), and the operator rejected that report. The reporter calls `update_task {"task_id": "task-ddc3099981de", "status": "in_progress"}` → 403 "A task waiting on a person is released when the wait actually ends — the operator answers or declines the question, or your own wait for it expires and ask_user reports that. An agent cannot move it out of 'blocked' by asking to." (`hub/hub/api/v1/tasks.py:1753`). The comment above it lists the "three real releases" as the question answer, the decline and an expired wait, so it predates F700's report answers. The agent reads it and cannot tell what releases the task: the operator's **amend** or **accept** on the report in the document's Amendments panel (a reject keeps it blocked, `spec_amendments.py:681`). **Expected:** when the block came from a cannot-satisfy report (an open or rejected `cannot_satisfy` amendment naming this task), the refusal says so and names the way out. For example: "task-ddc… is blocked by your report that criterion c-fast cannot be satisfied (amd-20bce…); the operator rejected it: <reason>. It is released when the operator amends the criterion or accepts a report; report again if something still stands in the way." The question sentence stays for question waits. **Test:** `hub/tests/` — block a task through `report_cannot_satisfy`, then the agent's PATCH `in_progress` → 403 whose detail names the report and not "question". This fails today. Context, not a separate defect: after that reject, accepting the *other* report on the same task (`amd-bbfa905afd09`) unblocked it (`_unblock` runs on any accept). Seam: Tasks (agent transitions) x Spec documents (cannot-satisfy).

## F966 (C) -- a flow document that names `delivery.tester` is still warned `reviewer_undeclared` ("the flow will give each review to any free agent"), though every review goes to the named tester

**Status:** open 2026-10-23. Found by the day sweep `sweep-spec-sweep` (scratch Hub :8114; the flow's review turn `run-6d5559ec7825` went to `tester`).
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

Repro: `PUT /projects/{p}/project/documents/spec/changes/sp-flow/spec.json/content` with `delivery {"mode": "flow", "agent": "builder", "tester": "tester", "stop_when_queue_empties": true}` and no task `reviewer` → 200 with `warnings: [{"code": "reviewer_undeclared", "where": "tasks", "message": "neither `delivery.reviewer` nor any task's `reviewer` is set, so the flow will give each review to any free agent; if a particular agent should review, set `delivery.reviewer` …"}]`. After approval and builder's completed turn, the flow staged the review for **tester** (`run-6d5559ec7825`, test duty included), as `review_turn.py:226-230` says: a named tester reviews every task naming no reviewer, ahead of `delivery.reviewer`. The warning tells the operator the opposite. Cause: `spec_completeness.reviewer_undeclared_warnings` (`hub/hub/spec_completeness.py:558`) returns early only on `delivery.reviewer`. **Expected:** no warning when `delivery.tester` is a name (the warning stays when it is `false` or unset). **Test:** `hub/tests/test_spec_reviewer_undeclared_warning.py` — a flow delivery with `tester: "tester"` and no reviewer → no `reviewer_undeclared`. This fails today. Seam: Spec documents (submission warnings) x Flows & review.

## F969 (C) -- on the Spec page the coverage panel and the header's requirements fact name the same states in different words, and every drifting row points at "Drifting, below", which is not on screen

**Status:** open 2026-10-23. Found by the day sweep `sweep-evidence-sweep` (scratch Hub :8115; Chromium against the served bundle, `scripts/drive/s1023_ev_ui.py health|drift`).
**Source:** drive
**Theme:** Requirements, evidence & coverage
**Ready:** yes
**Tier:** 0

Repro, on `spec/changes/ev-main/spec.json` (five requirements, one with no task): (1) The header fact reads "2/5 verified · 1 rejected · 1 not started · **1 with no task** · 1 not merged", and its popover reads FR-5 "**No task**". Show details opens the coverage panel under the header, which reads "**1 no work linked**" and "FR-5 — **No work linked**". The same state gets three names on one screen. The same split exists for `amendment_unreviewed`: "**changed, unreviewed**" in the header (`SpecHealthLine.tsx:254`) and "**Amendment not reviewed**" in the panel (`SpecCoverageBar.tsx:20`); that state was not reached on screen in this drive. (2) After a scan raised three drift candidates, the header fact reads "0/5 verified · 3 drifting · …" with the warn tone (F945 holds). Its Show details panel then explains each drifting row as "The implementation changed after this was verified. Say which one was wrong — **answer it under Drifting, below.**" (`SpecCoverageBar.tsx:16`). Nothing named Drifting is below. The answers live in the **drift** fact's own detail, and the page shows one detail at a time (`SpecDocumentPanel.tsx:149`, `detail` is a single key), so opening the requirements detail is exactly what hides them. Screenshot `testbed/ui-judge/s1023-evidence/113810/b1_coverage.png`. **Expected:** one word per state across the header, its popover and the panel (the coverage panel's `STATES` labels and `SpecHealthLine`'s `OPEN_STATES`/`STATE_LABEL` from one table), and a drifting row's sentence that names where to answer it, e.g. "answer it from the drift fact above ('N drifted')", or, better, a link that opens that detail. **Test:** `hub/ui/src/__tests__/specHealthLine.test.tsx` — render the header and the coverage bar for an `unserved` row and assert that the same label is used; and that a `drifting` row's `why` does not say "below". Both fail today. Seam: Requirements, evidence & coverage (header) x Drift (strip).

## F971 (C) -- Run on a loop whose agent has no runner answers, on the second press, "Every task on this loop's queue is already being worked … nothing is wrong" while nothing is worked

**Status:** open 2026-10-23. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8111; `scripts/drive/s1023_la_loops.py`).
**Source:** drive
**Theme:** Jobs & loops
**Ready:** yes
**Tier:** 0

Repro: `PATCH /agents/norun {"runner_id": null}`; a loop job for norun. First `POST /jobs/job-1f2782f2a3bc/run` → 200 with `waiting_reason` "No runner is bound…" (the entry stays queued with that reason). Second press → **409 "Every task on this loop's queue is already being worked. Nothing was started, and nothing is wrong — the next firing picks up whatever finishes."** Nothing will finish: no runner. Cause: `_held_in_flight_reasons` (`hub/hub/api/v1/jobs.py:1685`) names the provider hold and the spent token budget (F441) but not the agent-wide environment refusals (no runner bound, runner CLI missing). **Expected:** 409 naming the hold, e.g. "norun has no runner bound, so its queued turn cannot start. Bind one in the Hub UI." **Test:** beside `hub/tests/test_run_names_a_spent_token_budget.py`: a runnerless loop agent, two presses; the second's detail names the runner and does not contain "nothing is wrong". Seam: Jobs & loops x Runners.

## F972 (C) -- a firing queued behind another waiting entry for the same agent answers 200 with no `waiting_reason`

**Status:** open 2026-10-23. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8111).
**Source:** drive
**Theme:** Jobs & loops
**Ready:** yes
**Tier:** 0

Repro: runnerless agent norun with two jobs. `POST /jobs/{norun plain}/run` → 200 with `waiting_reason` "No runner is bound…". Then `POST /jobs/{norun loop}/run` → 200 `{"success":true,"job_run_id":"run-9aa91e126e3e",…}` with **no** `waiting_reason`; `inbound_queue_entries` row `entry-f08bfc095cda` is `queued` with `waiting_reason` NULL, while `GET /queue/norun/status` says "No runner is bound…". Cause: `hub/hub/api/v1/jobs.py:1949-1963` reads only this firing's own entry's `waiting_reason`, and the queue stamps the reason on the head entry only. **Expected:** the press carries the agent's waiting reason whenever its entry is queued behind a hold (read the queue status, not the entry). **Test:** `hub/tests/test_a_job_for_an_agent_with_no_runner_waits.py`: two jobs for the same runnerless agent; the second press has `waiting_reason`. Seam: Jobs & loops x Inbound queue.

## F973 (C) -- an ended or archived loop still accepts definition edits and control changes, and its tab then says the edit "applies at the next firing" of a loop that never fires again

**Status:** open 2026-10-23. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8111; Chromium against the served bundle, `scripts/drive/s1023_la_ui.py`).
**Source:** drive
**Theme:** Jobs & loops
**Ready:** yes
**Tier:** 0

Repro: loop B stopped with a reason (`ending_state: stopped`). `PATCH /jobs/job-cb4be9d8fac9 {"purpose":"edit an ended loop"}` → 200, writes `loop_edit_staged`, `pending_purpose` set. `POST /loops/loop-7871385dea5f/control {"control":"creator"}` on archived loop A → 200, `control: creator`, `loop_control_changed` written; the same on ended loop B. The neighbours refuse correctly: `stop_reason` → 409 `loop_already_ended`, `enabled` → 409 `loop_ended`, archive → 400. Loop B's tab (Chromium) reads "Stopped early: operator: not needed after all … Edit staged — it applies at the next firing … Until then the loop runs on the definition below marked 'In force now'". Spec `agent-loops` ac99 says an ended loop's settings are read-only. Cause: the staging branch of `update_job` (`hub/hub/api/v1/jobs.py` ~1297-1320) never checks `loop.ending_state`; `set_loop_control` (`hub/hub/api/v1/loops.py:203-237`) checks neither `archived_at` nor `ending_state`. **Expected:** 409 saying the loop has ended and to create a new loop (as `loop_ended` already does); nothing staged, no event. **Test:** `hub/tests/test_jobs*.py` / the loops tests: a stopped loop, then a PATCH of `purpose` and a POST to `control` → each 409, no `pending_*` set, no event. Seam: Jobs & loops (Settings, Delegate) x loop ending.

## F974 (C) -- after a press, the Loop tab and the Jobs screen take 4-5 s to show what the Hub applied in 0.3 s; one Delegate press fires about 59 GETs

**Status:** open 2026-10-23. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8111; Chromium, `scripts/drive/s1023_la_ui.py storm|latency loop-c4e818c86b61`).
**Source:** drive
**Theme:** Jobs & loops
**Ready:** yes
**Tier:** 1

Repro (Chromium, request log): idle 10 s → no loop GETs. Press "Let norun decide" → 39 × `GET /loops/{id}` + 20 × `GET /loops` in about 5 s, then quiet; the POST's 200 arrived at 0.32 s but the controller text changed only at 4.8 s (4.2 s on a second try). On flow C a Delegate press took ~13 s to show, and Stop's ending was still not on screen 3 s later. Jobs screen: Pause fires 14 × `GET /jobs` within 0.13 s and its toast appears at 3.5 s; Run now's 200 at 0.29 s, toast at 4.1 s. Cause (partial): the mutation's `onSettled` (`hub/ui/src/api/loops.ts:66-68`) and the SSE `loop_*` case (`hub/ui/src/hooks/useSSE.ts:605-612`) each invalidate twice; that does not account for ~59 requests, and the rest was not found, hence Tier 1. **Expected:** a few refetches, and the tab or toast updates when the response lands. **Test:** a vitest under `hub/ui/src/__tests__` with mocked fetch: press "Let X decide" → at most 3 loop GETs and the controller text updates once the POST resolves. Seam: Jobs & loops UI x SSE invalidation.

## F980 (C) -- `PUT /project/documents/{path}/content` answers a bare 500 when the document's file cannot be written

**Status:** open 2026-10-23. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8113; `scripts/drive/s1023_lc_fault.py`).
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

Repro: `attrib +R spec/changes/cobalt-selkie/spec.json`, then a content PUT with a valid payload → **500 "Internal Server Error"**; the Hub log shows `PermissionError: [Errno 13] … spec.json`. A directory in place of the file → the same 500. The `spec_documents` row (digest, `updated_at`) is unchanged: no partial state. Cause: `write_document` (`hub/hub/spec_documents.py:317-323`) lets the OSError escape via `_apply_and_write` (`hub/hub/spec_service.py:325`); the route (`hub/hub/api/v1/spec.py:829`) catches only `SaveRefusedError`. The agent amend path goes through the same `save_document` (not driven). **Expected:** 409 naming the file and the OS reason ("spec.json is read-only or locked; close what holds it and save again"). **Test:** route test for the content PUT with `Path.write_text` monkeypatched to raise `PermissionError` → 409. Seam: Spec documents x Resilience.

## F981 (C) -- `POST /vault/sources` answers a bare 500 when the tracked vault root `knowledge/` cannot be written (F717's fix covered only the private location)

**Status:** open 2026-10-23. Extends F717. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8113).
**Source:** drive
**Theme:** Knowledge vault
**Ready:** yes
**Tier:** 0

Repro: make `knowledge` a file in the project root; `POST /vault/sources {"name":"Fault note","type":"note","content":"…"}` → **500**; log `FileExistsError: [WinError 183] … lcproj\knowledge`. In the same state map, settings, contradictions and reports answer 200. Cause: `Storage.write` (`hub/hub/vault.py:150`) `mkdir`s, reached from `vault.py:936`/`:978`; `hub/hub/api/v1/vault.py:183` catches only `VaultError`. **Expected:** 409 naming `knowledge/` and why it cannot be written. **Test:** `hub/tests/test_vault*.py`: a tracked add with `knowledge` as a file → 409. Seam: Knowledge vault x Resilience.

## F982 (C) -- the first Claude turn after an interrupted or stopped turn in the same session records no cost, though the CLI reported it

**Status:** open 2026-10-23. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8113; kill/restart and Stop drives, `scripts/drive/s1023_lc_kill.py`).
**Source:** drive
**Theme:** Accounting & allowance
**Ready:** yes
**Tier:** 1

Repro: an interrupted (Hub killed) or stopped turn leaves a `turn_usage` row `status=unavailable, session_totals=null`. The next measured turn in that session has `session_totals` but `api_equivalent_usd_micros = NULL`: `run-d01f4744bd6a` (session `f5ece8dc`, 74,901 tokens, totals 10,425 µ$), `run-d391a64a639c` (`e708aaff`, 118,661, 17,704 µ$), `run-4d578d7ce374` (`f483dd06`, 73,357, 43,891 µ$). The turn after is priced (`run-86708a79d7a3` 5,863 µ$). `GET /accounting` for the project: `api_equivalent_usd_micros: 5863, unpriced_turns: 7` (~$0.006) against ~$0.078 the CLI reported. Cause: `hub/hub/usage_accounting.py:168-172`: "earlier rows but none with recorded totals → no cost" (meant for legacy pre-0132 rows) also fires when the only earlier rows are `unavailable` rows from a process that died. It decides where the cut turn's spend is counted, hence Tier 1. **Expected:** when every earlier row in the session is `unavailable`, use a zero baseline so the session's reported spend is counted. **Test:** `hub/tests/test_a_claude_turn_records_its_own_cost.py`: an `unavailable` row with null totals followed by a measured row with totals → priced. Seam: Runs (interrupt/stop) x Accounting.

## F983 (C) -- a corrupt `.agentweave/project.json` in a registered folder cannot be fixed from the app: open answers 409, and the remedy it offers answers 409 too

**Status:** open 2026-10-23. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8113; API only, not browsed).
**Source:** drive
**Theme:** Projects
**Ready:** yes
**Tier:** 0

Repro: write `{not json` into the project's marker. `POST /projects/open {"path": <dir>}` → 409 `project_identity_conflict` "project marker is unreadable or invalid"; the same with `"register_copy_as_new": true` → the identical 409. Meanwhile `GET /projects` reports `directory_state: "available"`, and settings, agents and documents answer 200. Cause: `hub/hub/project_lifecycle.py:85-86` sends a registered path to `_require_marker` before reading `register_copy_as_new`; `_read_marker` (`:535`) raises without naming the file or a fix. By code reading only (unverified), a *missing* marker hits the same wall (`:548-549`). **Expected:** for a path this database has registered, rewrite the marker from the registered id, or refuse naming `.agentweave/project.json` and how to repair it. **Test:** `hub/tests/test_project_lifecycle*.py`: a registered project with a corrupt marker, opened again → marker rewritten or a refusal naming the file. Seam: Projects x Resilience.

## F987 (C) -- Stop on a Claude run blocked in an `aw-tool ask_user` call leaves that call's process tree running until the question's own deadline, holding the agent's worktree open

**Status:** open 2026-10-23. Found by the day sweep `sweep-questions-sweep` (scratch Hub :8116, profile qa1023).
**Source:** drive
**Theme:** Runs
**Ready:** yes
**Tier:** 0

`gamma` (`question_timeout_seconds` 600, aw-tool call mode) called `aw-tool ask_user .agentweave/calls/ask_rename.json`. `POST /agent/gamma/stop` -> 200 "stopping"; the run went `stopped` at 11:25:42 UTC. At 11:33 UTC these were still alive: bash.exe 14272/28492 (`eval 'aw-tool ask_user .agentweave/calls/ask_rename.json'`), sh.exe 15556 (`aw-tool`), python.exe 15256 (`.../tool-server/e20febd905ba97dc/mcp_server.py --call ask_user`), their parent 24716 gone. They exited ~12:35:35 local, exactly 600 s after the question was created. Meanwhile `DELETE` project (204) could not remove its folder: `[WinError 32] ... .agentweave\worktrees\gamma`. Unverified: that 24716 was the run's own `claude.exe` (the project delete removed the runs row).

Cause (verified): `stop_agent_run` calls `pty.terminate(force=True)` (`hub/hub/api/v1/agent_trigger.py:2587-2591`); Claude runs are `spawn_kind = "pty"` (`hub/hub/runner_adapters/claude.py:64`), so this is `PtySession.terminate` -> `self._proc.terminate(force)` (`hub/hub/pty_runner.py:345-346`), the direct child only, as `terminate_process_tree`'s docstring says (`pty_runner.py:228-231`). Hub shutdown uses `terminate_process_tree` (`agent_trigger.py:2636`); Stop does not. The older "Stop kills the process" result (~l.15645) measured children not blocked in a tool call.

**Widened 2026-10-23 (`sweep-traces-sweep`, Runs row, :8118, `scripts/drive/s1023_rn_stop_tree.py`):** the cause is general, not ask_user-specific. A run blocked in a plain shell call (`py -3.11 -c ... range(300)`): tree claude.exe 16780 -> cmd.exe 16348 -> powershell.exe 22628 -> py.exe 22256 -> python.exe 23760 (+ tool server, conhosts). `POST /agent/alpha/stop` -> 200, run `stopped` in 4.1 s; 8 s later powershell 22628, py 22256, python 23760 and conhost 26816 still alive, and renaming `.agentweave/worktrees/alpha` failed `[WinError 32]`. Reproduced twice. The failure-path kill (F359, `agent_trigger.py:3857-3860`) is also `pty.terminate(force=True)`; the fix should cover it too.

**Expected:** Stop takes the run's whole tree (`terminate_process_tree(pty.pid)` for a PtySession). **Test:** in the stop tests (`hub/tests/`): stopping an active PtySession-backed run calls `terminate_process_tree` with its pid (monkeypatched). Fails today. Seam: Runs (Stop) x Questions.

## F988 (C) -- an archived conversation opened by its URL reads "New conversation" in its header, with no archived notice, "Continuing this conversation" and a live composer

**Status:** open 2026-10-23. Found by the day sweep `sweep-questions-sweep` (Conversations row; scratch Hub :8117, profile cv1023, `proj-8cd25053c03e`, Chromium on the served bundle, `scripts/drive/s1023_cv_rail.py`).
**Source:** drive
**Theme:** Conversations & composer
**Ready:** yes
**Tier:** 0

`POST .../agent/alpha/conversations/conv-9c177acf95dd/archive`, then load `/?project=...&agent=alpha&conversation=conv-9c177acf95dd`: header "alpha / New conversation" above the old transcript, no archived notice, live composer; the More menu has no Archive/rename (`conversation` is null). Screenshot `testbed/ui-judge/s1023-conversations/123844/rail_00_archived_open.png`.

Cause: the header looks the conversation up only in `useAgentConversations` (`hub/ui/src/components/agents/AgentOutputPanel.tsx:413`), which lists open conversations (`agent_chat.py:515-533`, `lifecycle` defaults to `open`); undefined -> the 'New conversation' fallback (`:1246`). F846 is the cut-over-predecessor case of the same gap; this is the general archived one plus the lost title.

**Expected:** the header names the archived conversation, and the page says it is archived, with Unarchive. **Test:** `hub/ui/src/__tests__/` beside the conversation-bar tests: an archived conversation id absent from the open list gets its real title and an archived notice. Fails today ("New conversation"). Seam: Conversations (lifecycle) x `ConversationBar`.

## F989 (C) -- the conversation side panel names a fresh, unindexed document by its minted folder ("silver-fenrir"), not its title, so the panel's "Search by title" cannot find it

**Status:** open 2026-10-23. Found by the day sweep `sweep-questions-sweep` (Conversations row; :8117, `scripts/drive/s1023_cv_spec.py`).
**Source:** drive
**Theme:** Conversations & composer
**Ready:** yes
**Tier:** 0

Fresh project, `POST /project/documents {"title":"Composer drive change","kind":"change-spec"}`; `GET /project/specs` returns the entry with path, state `unindexed`, phase, document_id and **no `title`**. The side panel's specs tab shows "silver-fenrir / spec.json"; the Spec tab's own list and the Ctrl+K palette show "Composer drive change".

Cause: `spec_documents.py:715-729` sets `title` only from the manifest; `api/v1/spec.py:142-151` merges the tracked row's `phase` and `id` but not its `title`; `specNavigation.ts:135` falls back to `deriveTitle(path)`. Related: F949 (new documents read as index issues).

**Expected:** an entry with a tracked row carries the row's title. **Test:** `hub/tests/`: `GET /project/specs` right after a create, no index rebuild -> the entry's `title` is the document's. Fails today. Seam: Side panel specs tab x Corpus index.

## F993 (C) -- the "events were not delivered" notice has no screen: `ActivityLog`, the only component that renders `stream_gap`, mounts only when `GET /ledger` answers 404

**Status:** open 2026-10-23. Found by the day sweep `sweep-traces-sweep` (Logs row; scratch Hub :8119, profile ev1023, `proj-c01bff86cc78`, Chromium on the served bundle, `scripts/drive/s1023_ev_sse_gap.py`).
**Source:** drive
**Theme:** Logs, events & SSE
**Ready:** yes
**Tier:** 0

Wire: `s1023_ev_sse_gap.py wire 400 60` (a raw socket on `/api/v1/events` that reads the headers then stops reading, while 400 x 60 KB `POST /projects/{p}/logs` go in) read 264 `log_event` frames and one `event: stream_gap data: {"dropped":136,"severity":"warn"}` (264 + 136 = 400): the Hub half works, first time reached. Browser: three attempts with the app on Activity never showed "fell behind" (main thread blocked 25 s under 400 x 60 KB and 300 x 200 KB; CDP throttling at 200 KB/s for 200 s). Even if a gap arrived, no mounted view renders it.

Cause (verified): the sentence lives in `hub/ui/src/lib/eventSummary.ts:22` and is rendered only by `ActivityLog` (`hub/ui/src/components/activity/ActivityLog.tsx:140-148`), whose only mount is `ProjectLedger`'s 404 branch (`ProjectLedger.tsx:186-198`, "This Hub predates the ledger"). `ActivityScreen.tsx:60-63` renders `ProjectLedger`, `LiveDigest` (`buildDigest` over `/logs`, which never carries a gap) or `LogsView`; none handles `stream_gap`. `useSSE.ts:349-360` dispatches it and runs the catch-up, so the data heals silently. The current spec still requires the notice: `spec/capabilities/agent-stream-events` ac67, "Activity shows that events were not delivered whichever project is selected".

**Expected:** on a Hub with the ledger, a gap is said on screen (digest or Activity tab header), whichever project is selected. **Test:** `hub/ui/src/__tests__/` beside the ActivityScreen/digest tests: dispatch a `stream_gap` `{dropped: 136}` with the Activity tab on the Activity (or Ledger) view and a ledger answering 200; "events were not delivered" is rendered. Fails today. Seam: SSE stream x Activity tab (ledger rebuild).

## F994 (C) -- a query bound written with a non-UTC offset is compared as its wall-clock time: `DELETE /traces?until=<an hour ago, +02:00>` deleted traces from the last minute, and `GET /logs?since=<11:00Z as +02:00>` answers 0 of 32

**Status:** open 2026-10-23. Found by the day sweep `sweep-traces-sweep` twice, independently (Traces row, scratch Hub :8120, profile tc1023, `scripts/drive/s1023_tc_probes.py`; Logs row, :8119, profile ev1023, `scripts/drive/s1023_ev_sse_probe.py`).
**Source:** drive
**Theme:** Traces
**Ready:** yes
**Tier:** 0

Traces (four traces, all started 12:17 UTC or later): `GET /traces/export?since=2026-10-23T12:00:00+00:00` -> 158 spans, `...T12:00:00Z` -> 158, `...T14:00:00+02:00` (same instant) -> **0**, `...T09:00:00-03:00` -> 268 (all). `DELETE /traces?until=2026-10-23T13:17:48+02:00` (11:17:48 UTC, before every trace) -> `{"deleted_spans": 4, "deleted_traces": 4}`, counts 4 -> 0. The list cursor too: `before=2026-10-23T14:07:50.327755+02:00|b75e3daf0001c60b` (the same instant as the route's own `+00:00` cursor) returns 61 traces instead of 30.

Logs (32 events, 11:52:18Z..12:05:07Z): `GET /projects/{p}/logs?limit=500&since=2026-10-23T11:00:00Z` -> 32; `since=2026-10-23T13:00:00%2B02:00` (11:00Z) -> **0**; `since=2026-10-23T06:00:00-05:00` -> 32 (right only because 06:00 wall clock is also earlier). The route's own refusal for a bad `since` tells callers how to send an offset ("a + must be sent as %2B"); F255's check compared only `+00:00` with `Z`.

Cause (verified): `traces.parse_bound` returns the aware datetime with its offset kept (`hub/hub/traces.py:1801-1804`), `list_traces` the same for `before` (`:1676`), and `list_logs` passes `datetime.fromisoformat(since)` straight into the filter (`hub/hub/api/v1/logs.py:86,95`). `UTCDateTime` (`hub/hub/db/models.py:30-51`) has `process_result_value` only, no `process_bind_param`, and SQLite's `DATETIME` bind drops tzinfo (`'2026-10-23T13:00:00+02:00'` binds as `'2026-10-23 13:00:00.000000'`), so an aware non-UTC value is compared against naive-UTC storage as its wall time. Any route binding a caller's aware datetime against a `UTCDateTime` column shares it.

**Expected:** `UTCDateTime.process_bind_param` converts an aware value to UTC (`astimezone(timezone.utc)`) for every column, or at least `parse_bound`, the trace cursor and `list_logs` do. **Test:** `hub/tests/`: a trace started 12:30 UTC — `export?since=...T14:00:00+02:00` includes it and `DELETE ?until=...T13:00:00+02:00` deletes nothing; events after 11:52Z — `logs?since=...T13:00:00%2B02:00` returns them all (beside `test_the_logs_page_is_the_newest_and_pages_back` in `hub/tests/test_a_request_means_what_it_says.py`). All fail today. Seam: Traces (export/clear) and Logs x the database's datetime binding.

## F997 (C) -- every check run's trace shows routine git answers as red error spans: `merge-base --is-ancestor` exit 1 and `worktree unlock`/`remove` exit 128 on a checkout that is not there

**Status:** open 2026-10-23. Found by the day sweep `sweep-traces-sweep` (Traces row; scratch Hub :8120, profile tc1023, `POST /tasks/{id}/checks/run`, check run chk-d23dfb3a61f7).
**Source:** drive
**Theme:** Traces
**Ready:** yes
**Tier:** 0

The `check_run` work trace has 20 `aw.command` children, 9 of them `error`. Only 2 are real (the `fails` check, exit 3, on the merged work and on main). The other 7 are routine: `git merge-base --is-ancestor <target> <main>` "exit code 1" (not an ancestor, an answer); `git worktree unlock .agentweave/checks/<task>` exit 128 four times; `git worktree remove --force --force` exit 128 twice with no checkout to remove. All draw red in the waterfall ("An error is red whatever the operation: it is the one thing to find").

Cause (verified): `project_checks._git` calls `traces.run` without `ok_codes` (`hub/hub/project_checks.py:84-101`); the ancestor probe is at `:121`, and `_remove_checkout` unlocks and removes unconditionally (`:155-169`). F791 fixed only the two `MERGE_HEAD` probes in `worktrees.py`; `worktrees.py:480` and `:703` use the same `--is-ancestor` with `check=False` and no `ok_codes` (not seen in this drive).

**Expected:** `--is-ancestor` passes `ok_codes=(0, 1)`; `_remove_checkout` unlocks/removes only a checkout that exists or is registered (or records those exits as answers). **Test:** beside `hub/tests/test_a_merge_head_probe_is_not_a_failed_command.py`: a check run whose checks all pass, on a fresh task, leaves no `aw.command` span with `status == "error"`. Fails today. Seam: Traces x Worktrees & integration (project checks).

**Widened 2026-10-23** (day sweep `sweep-tasks-sweep`, Worktrees row, :8160, `scripts/drive/s1023_wt_drive.py`): each of four passing check runs had 12 `aw.command` spans, 4 `error` (`merge-base --is-ancestor` exit 1, `worktree unlock` 128 twice, `worktree remove` 128). Every `task_integration` trace, successful merges included, also carries a red `git merge-base --is-ancestor <commit> master` exit 1 (`requirement_evidence.is_reachable_from`, `hub/hub/requirement_evidence.py:1103`, called from `task_integration.integrate`), and a branchless task's integration a red `git rev-parse --verify refs/heads/agentweave/task/<id>` exit 128 (`task_branch_tip`, `hub/hub/task_integration.py:430`). The fix should cover these probes too.

## F998 (C) -- a secret in a project check's command is stored and served verbatim in the `project_settings_updated` event, while the same event's copy on the trace reads `<redacted>`

**Status:** open 2026-10-23. Found by the day sweep `sweep-traces-sweep` (Traces row; scratch Hub :8120, profile tc1023).
**Source:** drive
**Theme:** Logs, events & SSE
**Ready:** yes
**Tier:** 2 -- secrets (CLAUDE.md's table); the diff is one redaction call, no migration (rows already stored keep their value).

`PUT /projects/{p}/settings` with `checks: [{"name":"prints-key","command":"py -3.11 -c \"print('token sk-ant-api03-TRACEfake0123456789abcdefghijKLMNOPqrstuv')\""}]`. The `event_logs` row evt-32da84378834 (`project_settings_updated`) holds the key verbatim, twice (`changed.checks.now`, `settings.checks`), and `GET /events/history` returns it unchanged. No `trace_spans` row holds it: the event recorded on the PUT's request span, and the check's `aw.command` span (`print('token <redacted>')`), are both redacted. Related (noted by the Logs drive, not separately filed): `POST /logs` also stores an `aw_live_` value verbatim — the same unredacted `persist_event`.

Cause (verified): `persist_event` stores `data` as given (`hub/hub/utils.py:71-78`) and `sse_manager.broadcast` sends it unchanged (`hub/hub/api/v1/projects.py:725-732`); only the trace copy goes through `redact` (`traces._event_record`, `hub/hub/traces.py:1137`).

**Expected:** the event history and the trace agree: `persist_event` stores `data` through the same `redact_text_secrets` floor the trace uses. **Test:** `hub/tests/`: a settings PUT whose check command carries an `sk-ant-` key leaves `/events/history` without the key. Fails today. Seam: Traces (event copy) x Logs, events & SSE.

## F1006 (C) -- after Try again lands a re-resolved branch, the drawer still reads "Merge failed -- CONFLICT ..." above the merge and keeps offering Try again, while the card says nothing is wrong

**Status:** open 2026-10-23. Found by the day sweep `sweep-tasks-sweep` (Worktrees row; scratch Hub :8160, profile wt1023, proj-1fff2af61236, `scripts/drive/s1023_wt_ui.py tryagain T2` / `drawer T2`, Chromium, served bundle fresh).
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** yes
**Tier:** 0

T2's rows, in the route's order: skipped `8dcf6c74` (dirty checkout), failed `8dcf6c74` (CONFLICT), failed `8dcf6c74`, then merged `f45b7632` (the branch after the operator merged master into it), `rode_along_commits: [8dcf6c74]`. A fresh page, drawer of T2:

```
Merge failed -- Auto-merging greet.py CONFLICT (content): Merge conflict in greet.py Automatic merge failed; fix conflicts and then commit the result. (tried 01:34 PM)
Merged f45b7632 into master
1 earlier commit on the same branch also landed with this merge, not just the reviewed one.
Try again                                   <- task-integration-retry-<T2>: 1
board card T2: no status line, no Retry     <- latest_integration merged
```

The "earlier commit ... not just the reviewed one" is `8dcf6c74`, which is the commit that was reviewed; the one nobody reviewed is `f45b7632` (F1005). The rode-along wording itself, for a task's own earlier commits, is F1009.

Cause (verified): `newestPerTarget` keys rows by `commit_sha@target_branch` (`hub/ui/src/components/tasks/TaskIntegrationNote.tsx:16-37`); a merge suppresses only rows with its own key or a null commit, so a failure on the branch's earlier tip survives a merge of its later tip, and `canRetry` (`:71`) is true while any surviving row is retryable. F769 fixed the same-commit and null-commit cases only.

**Expected:** once a row for the task's branch (`source_branch`) has merged, earlier unmerged rows from that branch are not shown and Try again is not offered; the drawer agrees with the card. **Test:** `hub/ui/src/__tests__/taskIntegrationRetry.test.tsx`, rows in the route's order above -> no "Merge failed" text and no `task-integration-retry-<id>`. Fails today. Seam: Worktrees & integration x Tasks (drawer vs card).

## F1007 (C) -- a merge that fails on a conflict is recorded with git's "fix conflicts and then commit the result" after the Hub has already aborted it; the remedy that works ("resolve the conflict on the branch") never reaches the drawer

**Status:** open 2026-10-23. Found by the day sweep `sweep-tasks-sweep` (Worktrees row; scratch Hub :8160, profile wt1023, proj-1fff2af61236, `scripts/drive/s1023_wt_drive.py retry`, `s1023_wt_ui.py tryagain T2`).
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** yes
**Tier:** 0

T2 approved over a dirty checkout (skipped, retryable), then T1 merged the same line of `greet.py`. `GET /tasks/<T2>/integration-preview` already said `conflicts: [{"paths": ["greet.py"]}]`. `POST /tasks/<T2>/integrations/retry` -> 200, a `failed` row whose whole reason is `Auto-merging greet.py\nCONFLICT (content): Merge conflict in greet.py\nAutomatic merge failed; fix conflicts and then commit the result.`; `git status` in the project is clean afterwards (nothing to fix or commit there). The drawer shows exactly that sentence beside Try again; pressed again in Chromium it records a third identical row. The gate's sentence for the same state, seen when approving T3 from the drawer, is legible: "This task's work does not merge cleanly into master: greet.py. Resolve the conflict on the branch, then approve ...". The pre-approval note above Approve reads only "The Hub: approval will be refused: greet.py in commit 62412ed99266 conflict with master" with no remedy either.

Cause (verified): `integrate` runs `git merge --no-ff` on the operator's checkout without asking `would_conflict` first, then `merge --abort` and stores git's stderr as the reason (`hub/hub/task_integration.py:713-731`); the gate's wording lives only in `requirement_gate._tip_merge_detail` (`hub/hub/requirement_gate.py:317-330`).

**Expected:** integration asks `would_conflict` before merging (the plumbing the gate and preview already use) and records a reason naming the paths and the gate's remedy ("resolve it on agentweave/task/<id>, then Try again"); the operator's checkout never enters a merge that is known to conflict. **Test:** `hub/tests/test_task_integration.py`: `integrate()` on a target that conflicts with main -> outcome failed, reason names `greet.py` and does not contain "commit the result". Fails today. Seam: Worktrees & integration (retry) x legibility.

## F1009 (C) -- after a send-back, merging a task's own branch shows an amber warning that "1 earlier commit on the same branch also landed with this merge, not just the reviewed one": the task's own first-round commit reads as unreviewed work riding along

**Status:** open 2026-10-23. Found by the day sweep `sweep-tasks-sweep` (Tasks row; scratch Hub :8162, profile tk1023, proj-d51843e66b2a, `scripts/drive/s1023_tk_drive.py workw/revise/workw2/approve`, `scripts/drive/s1023_tk_ui.py drawer W`).
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** yes
**Tier:** 0

Task W (`task-0ac0709e7e50`), per-task checkout `agentweave/task/task-0ac0709e7e50`. Real Haiku turns:

```
run-356cfd288e13 (alpha): commit ad95ad6 "add mul", W -> completed
PATCH /tasks/W {"status":"revision_needed","notes":"Add a test for mul() ..."}  -> 200
run-73f28d2e43bc (alpha): commit 0b165fb "add test_mul" on the same branch, W -> completed
POST /tasks/W/land {} -> 200 approved, merged 0b165fb
GET /tasks/W/integrations -> {"commit_sha":"0b165fb...","rode_along_commits":["ad95ad63efe0..."], ...}
Chromium, drawer (Story and Details): "Merged 0b165fb0 into master  [amber warning] 1 earlier commit on the same branch also landed with this merge, not just the reviewed one."
```

Both commits are W's own work, made by W's own runs on W's own branch, and W has no evidence: the operator reviewed the task, not one commit. The warning was F58's (one per-agent branch carrying other tasks' work). Since per-task checkouts (2026-08-27) the branch is the task's own, so the amber warning fires on every task that took more than one commit (every send-back cycle) and tells the operator unreviewed work reached master when none did.

Cause (verified): `commits_riding_along` is `git rev-list <main>..<commit_sha>` minus the tip (`hub/hub/task_integration.py:598-611`), computed for every merge (`:706`, stored `:736`/`:758`). Recording the task's own groundwork is deliberate (`hub/tests/test_task_integration.py:340-380`, `test_later_commits_on_the_branch_are_not_merged`: "an earlier commit on the same task's own branch is groundwork ... it has to land with it ... the record still says which commit was reviewed"), and `test_another_tasks_commits_do_not_ride_along` (`:383-423`) shows another task's work no longer can. The defect is the presentation: the drawer renders any non-empty list as a warning, worded as unreviewed work (`hub/ui/src/components/tasks/TaskIntegrationNote.tsx:130-144`), without telling this task's own commits from anything else.

**Expected:** this task's own earlier commits read neutrally ("with 1 earlier commit of this task: ad95ad6 add mul"), and the amber warning is reserved for commits that did not come from this task's runs (a prerequisite merged in, foreign work), naming whose they are. **Test:** in `hub/ui/src/__tests__/taskIntegrationRetry.test.tsx` (the file that already asserts the rode-along line): a merged integration whose `rode_along_commits` are the task's own renders no `warning` icon and no "not just the reviewed one". Fails today. Seam: Tasks (send-back) x Worktrees & integration.

## F1010 (C) -- the drawer says "Approving will not merge anything: no accepted evidence names a commit, so there is nothing to merge" beside a task whose evidence names commit f13fe58 and awaits review; Land is then refused saying the opposite

**Status:** open 2026-10-23. Found by the day sweep `sweep-tasks-sweep` (Tasks row; scratch Hub :8162, profile tk1023, proj-d51843e66b2a, `scripts/drive/s1023_tk_drive.py spec/workr`, `scripts/drive/s1023_tk_ui.py land R`).
**Source:** drive
**Theme:** Requirements, evidence & coverage
**Ready:** yes
**Tier:** 0

Task R (`task-8cd706681ed0`, `t-div` of an approved change document, serves FR-1). Real Haiku turn `run-4358a089b744`: commit `f13fe58` on `agentweave/task/task-8cd706681ed0`, `record_evidence` -> `ev-865460461102` (`review_state: awaiting`, locator "calc/ops.py (commit f13fe58)"), task `completed`.

```
GET /tasks/R/integration-preview -> 200 {"targets": [], "will_attempt_merge": false,
    "reason": "no accepted evidence names a commit, so there is nothing to merge"}
POST /tasks/R/land {} -> 409 gate_unsatisfied, unaccepted[0].kind "awaiting_evidence", unlanded commits ["f13fe588..."],
    message "This task's work has been recorded and nobody has judged it: FR-1 at f13fe5883a44. Approving now would record that the work is good and merge none of it ... accept the evidence ..."
Chromium, drawer Details, both on screen at once:
    (info) "Approving will not merge anything: no accepted evidence names a commit, so there is nothing to merge."
    (refusal, after Land it) "This task's work has been recorded and nobody has judged it: FR-1 at f13fe5883a44 ..."
```

Before pressing Land, the operator is told there is nothing to merge and that approving is harmless; there is a recorded commit waiting on their decision, and approving is refused. The preview's sentence is true only of *accepted* evidence and is read as a statement about the work.

Cause (verified): the preview's empty answer is `NOTHING_TO_MERGE` whenever evidence governs and no *accepted* target exists (`hub/hub/api/v1/tasks.py:1192-1194`, `:1280-1283`; sentence `hub/hub/task_integration.py:69`); it never asks about awaiting evidence, which the gate does (`unaccepted` / `unlanded` in the 409). The drawer prints it verbatim (`hub/ui/src/components/tasks/TaskDetailDrawer.tsx:87`).

**Expected:** where evidence awaits review, the preview says so in the gate's terms ("FR-1's evidence at f13fe58 awaits your review: accept it and approving merges it; approving now is refused"), and links to the Evidence view; "nothing to merge" only where no evidence names a commit at all. **Test:** in the integration-preview tests: a task with one awaiting evidence piece naming a commit -> the preview's `reason` does not contain "nothing to merge" and names the piece. Fails today. Seam: Tasks (drawer) x Requirements, evidence & coverage (gate). Same sentence, other case: F1008 (a task with no branch).

## F1011 (C) -- an agent's illegal-move refusal names moves the same route then refuses that agent: "available: assigned, blocked, completed" (blocked is always 403 for an agent) and "available: under_review" (403 for the task's author)

**Status:** open 2026-10-23. Found by the day sweep `sweep-tasks-sweep` (Tasks row; scratch Hub :8162, profile tk1023, proj-d51843e66b2a, `scripts/drive/s1023_tk_drive.py probe`: a real Haiku turn `run-ff6278552103` running `tools/agent_probe.py` with its own run credential against `/agent-actions/tasks/*`).
**Source:** drive
**Theme:** Tasks
**Ready:** yes
**Tier:** 0

beta's own task `Bown` (`task-0d47510b8fa7`, in_progress, assignee beta), in order:

```
PATCH /agent-actions/tasks/Bown {"status":"approved"}     -> 409 "Cannot move a task from 'in_progress' to 'approved'. From 'in_progress' the available transitions are: assigned, blocked, completed."
PATCH /agent-actions/tasks/Bown {"status":"blocked"}      -> 403 "A task is recorded as waiting on a person because AgentWeave saw the run end with an unanswered blocking question, not because an agent said so. Use ask_user ..."
PATCH /agent-actions/tasks/Bown {"status":"completed"}    -> 200
PATCH /agent-actions/tasks/Bown {"status":"approved"}     -> 409 "Cannot move a task from 'completed' to 'approved'. From 'completed' the available transitions are: under_review."
PATCH /agent-actions/tasks/Bown {"status":"under_review"} -> 403 "Cannot move task ... to 'under_review' with 'beta' as its holder: it is the agent recorded as completing this task ... the operator can move it on."
```

Each refusal on its own is right; the first of each pair sends the agent to a move that is always refused to it, so an agent following the refusal's advice spends a call on a second refusal (Haiku "wanders" exactly this way). From `completed` the author has no move at all, and the map's sentence says it has one.

Cause (verified): `refusal_detail` lists `allowed_targets(from_status, actor_kind)` (`hub/hub/task_transitions.py:385-403`), the map for the actor *kind*. `blocked` is in the run's map (`:115`, `_BOTH`, because the runtime takes that edge on the run's behalf) and refused to the agent by `update_task_for_actor` (`hub/hub/api/v1/tasks.py:1703-1716`); `completed -> under_review` is `_BOTH` (`task_transitions.py:138`) and refused to the author by `_guard_reviewer_is_not_the_author` (`hub/hub/task_transition_service.py:452`).

**Expected:** an agent's map refusal lists only moves that agent can make on this task (no `blocked`; no `under_review` for the task's author), and where none remain says so ("nothing more is yours to do on this task; the operator or a reviewer moves it on"). **Test:** `hub/tests/test_task_transitions_api.py`: a run-actor PATCH `in_progress -> approved` -> detail does not contain "blocked"; the completing run's `completed -> approved` -> detail does not offer `under_review`. Both fail today. Seam: Tasks (agent plane) x Capability plane.

## F1013 (C) -- the same-file warning compares declared paths as raw strings: `./lib.py`, `pkg//lib.py`, `pkg/../pkg/lib.py`, `.` and a case variant all overlap `lib.py`-style paths with no warning, and `../outside.py` is accepted as repo-relative

**Status:** open 2026-10-23. Found by the day sweep `sweep-tasks-sweep` (Dependencies row; scratch Hub :8161, profile dp1023, proj-f68af439d5d3, `scripts/drive/s1023_dp_overlap_paths.py` and `s1023_dp_planner.py`).
**Source:** drive
**Theme:** Dependencies
**Ready:** yes
**Tier:** 0

One exploring change document, two tasks with no `depends_on`, rewritten per case through `PUT /projects/{p}/project/documents/{path}/content`; the warning codes each save answered with:

```
['lib.py']      vs ['lib.py']              -> ['unordered_file_overlap']
['pkg/lib.py']  vs ['pkg\\lib.py']         -> ['unordered_file_overlap']
['pkg']         vs ['pkg/lib.py']          -> ['unordered_file_overlap']
['lib.py']      vs ['./lib.py']            -> []
['Lib.py']      vs ['lib.py']              -> []     (one file on this Windows checkout)
['pkg/lib.py']  vs ['pkg/../pkg/lib.py']   -> []
['pkg/lib.py']  vs ['pkg//lib.py']         -> []
['.']           vs ['lib.py']              -> []     ("a directory covers what is beneath it")
['../outside.py']                          -> 200, stored; absolute and empty paths are refused 422
```

The `./lib.py` case went end to end in `s1023_dp_planner.py`: `t1` files `["lib.py"]`, `t2` files `["./lib.py"]`, no order. Save, propose and the approval 409 carried no `unordered_file_overlap`; Approve anyway created both tasks with no prerequisite, so they would be built in parallel. Every other warning the drive saw was correct.

Cause (verified): `_normalise_path` (`hub/hub/spec_completeness.py:418-419`) only swaps backslashes and strips leading/trailing `/`; `paths_overlap` (`:422-429`) then compares strings exactly or by `prefix + "/"`. A `./` or `..` segment, a doubled slash, `.` and case are never folded. The payload validator (`hub/hub/spec_payload.py:564-576`) refuses empty and absolute paths but not one that climbs out with `..`.

**Expected:** declared paths are normalised before comparison (`posixpath.normpath`, `.` as the repo root that covers every path, case-folded where the checkout's filesystem is case-insensitive), so every spelling of one path draws the warning; a path that normalises outside the repo (`../x`) is refused like an absolute one, naming the task and the path. **Test:** beside `hub/tests/test_spec_task_files.py`: `paths_overlap("lib.py", "./lib.py")`, `("pkg/lib.py", "pkg//lib.py")`, `(".", "lib.py")` each return the shared path, and a payload with `files: ["../x.py"]` is `payload_invalid`. Fail today. Seam: Dependencies x Spec documents (the planner's same-file warning).

## F1014 (C) -- a document's tasks with no `files` are named only to the agent that saves it: propose, the approval 409 and the approval report never mention them, so the operator approves tasks the Hub cannot order

**Status:** open 2026-10-23. Found by the day sweep `sweep-tasks-sweep` (Dependencies row; scratch Hub :8161, profile dp1023, proj-f68af439d5d3, `scripts/drive/s1023_dp_planner.py`, Chromium `s1023_dp_ui.py`).
**Source:** drive
**Theme:** Dependencies
**Ready:** yes
**Tier:** 0

Document `spec/changes/amber-roc` with four tasks, `t3` and `t4` declaring no `files`:

```
PUT .../documents/{path}/content  -> 200 warnings: [undeclared_task_files "tasks 't3', 't4' declare no `files`, so the Hub cannot tell whether they edit the same path; ..."]
POST .../documents/propose        -> 200 warnings: criterion_without_check x4, no_acceptance_drive, steps_skipped   (no undeclared_task_files)
POST .../documents/phase?to=approved -> 409 approval_warnings: the same three codes                  (no undeclared_task_files)
approve anyway                     -> 4 tasks created; the Spec page's "Approved over these gaps" lists the same three
```

The app never calls `PUT .../content` (no `/content` caller in `hub/ui/src`), so the only reader of that warning is the agent whose save it answered; the operator who decides at propose and approve is never told. F694 fixed exactly this for `unordered_file_overlap` ("the save result's advisory alone never reached the operator, so proposal and approval say it too") and left its sibling behind.

Cause (verified): `phase_findings` (`hub/hub/spec_service.py:1959-1965`) adds `spec_completeness.overlap_warnings(payload)` but not `undeclared_files_warnings`, which only the save result carries (`spec_service.py:420-421`).

**Expected:** propose and approval report `undeclared_task_files` too -- as a note (`NOTE_CODES`, `spec_service.py:1798`) if it must not make every file-less multi-task document need Approve anyway, but on the operator's screen either way. **Test:** beside `hub/tests/test_approval_warnings_routes.py`: propose a two-task document whose tasks declare no `files`; the propose answer and the approval 409 (or its notes) carry `undeclared_task_files`. Fails today. Seam: Dependencies x Spec documents (approval).

## F1015 (C) -- the approval gap list shows one same-file pair however many there are: "unordered_file_overlap ×2 -- tasks 't1' and 't2' both declare 'lib.py' ... (tasks, tasks)"; the second pair is never named

**Status:** open 2026-10-23. Found by the day sweep `sweep-tasks-sweep` (Dependencies row; scratch Hub :8161, profile dp1023, proj-f68af439d5d3, Chromium against the served bundle, `scripts/drive/s1023_dp_ui.py overlap`, shot `testbed/ui-judge/s1023-dp/134147/overlap_approve.png`).
**Source:** drive
**Theme:** Dependencies
**Ready:** yes
**Tier:** 0

Document "Two same-file pairs": `t1`/`t2` both declare `lib.py`, `t3`/`t4` both declare `util.py`, no `depends_on`. Propose answers both warnings correctly:

```
"tasks 't1' and 't2' both declare 'lib.py' and neither depends_on the other, ...; chain them with depends_on"
"tasks 't3' and 't4' both declare 'util.py' and neither depends_on the other, ...; chain them with depends_on"
```

Press **Approve** on the Spec page; the gap list (`approval-warning-unordered_file_overlap`) reads, in full:

```
unordered_file_overlap ×2 — tasks 't1' and 't2' both declare 'lib.py' and neither depends_on the other, so they would be built in parallel; chain them with depends_on (tasks, tasks)
```

The operator cannot learn from the screen that `t3` and `t4` collide on `util.py`; the "places" add nothing, because every overlap finding's `where` is `"tasks"`. The same rendering is used for "Approved over these gaps" afterwards.

Cause (verified): `GapLines` (`hub/ui/src/components/spec/SpecPhaseParts.tsx:20-48`) groups gaps by code and prints only `group[0].message` plus up to three `where`s; `overlap_warnings` gives every pair `where="tasks"` (`hub/hub/spec_completeness.py:466-474`). Grouping suits a code whose places differ (`criterion_without_check` × 4 lists `acceptance_criteria[0..]`) and loses everything for a code whose difference is in the message.

**Expected:** each pair is named on screen -- either `GapLines` lists every distinct message when the places do not distinguish them, or `overlap_warnings` sets `where` to the pair (`tasks[0], tasks[1]` / the keys) so the place list names them. **Test:** `hub/ui/src/__tests__/specApprovalWarnings.test.tsx`: two `unordered_file_overlap` gaps with different messages and `where: "tasks"` render both task pairs. Fails today. Seam: Dependencies x Spec documents (approval report on screen).

## F1017 (C) -- a second Browse while the native folder dialog is open says only "The folder dialog could not be opened.": the Hub's 409 "A folder dialog is already open" never reaches the screen, and nothing says where the open one is

**Status:** open 2026-10-23. Found by the day sweep `sweep-projects-sweep` (Projects row; scratch Hub :8116, profile pj1023, proj-19b3a5f0a902, Chromium against the served bundle, `scripts/drive/s1023_pj_native.py`, shots `testbed/ui-judge/s1023-pj/135501/10_native_pending.png`, `11_native_second_tab.png`, `12_native_reopened.png`).
**Source:** drive
**Theme:** Projects
**Ready:** yes
**Tier:** 0

Add project -> Browse... (native dialog available). Tab 1's button reads "Waiting..." (disabled) while the Hub's Tk dialog is up on the Hub's desktop. Then:

- Tab 2, Add project -> Browse... -> `POST /fs/native-dialog/open` 409 `{"detail": "A folder dialog is already open"}`; the modal shows **"The folder dialog could not be opened."**
- Tab 2, Escape, reopen Add project: Browse... is enabled again; pressing it -> the same 409 and the same sentence.
- The same happens in one tab: close the modal while the dialog waits, reopen, press Browse.

The operator is told the dialog failed when one is in fact open (possibly behind the browser window) and waiting for them for up to 120 s; nothing says to look for it or that the button frees when it closes.

Cause (verified): `openNativeFolderDialog`'s `onError` (`hub/ui/src/components/projects/ProjectManagerModal.tsx:69`) replaces every error with a fixed sentence instead of `readableApiError(error, ...)`; the Hub's reason is raised at `hub/hub/native_dialog.py:142` and passed through as the 409 detail (`hub/hub/api/v1/native_dialog.py`).

**Expected:** a 409 reads like "A folder dialog is already open on this computer -- finish or cancel it there (it may be behind this window); it closes by itself after 2 minutes." Other errors keep the Hub's reason. **Test:** `hub/ui/src/__tests__/projectManagerDirectoryPicker.test.tsx`: the open mutation rejects with a 409 carrying that detail -> the status text contains "already open" (fails today). Seam: Projects (Add-project dialog) x the Hub's native dialog.

## F1018 (C) -- deleting a project while a run is active is refused with "project cannot be deleted while a run is active": no run, no agent, no way out named, and the dialog shows exactly that line

**Status:** open 2026-10-23. Found by the day sweep `sweep-projects-sweep` (Projects row; scratch Hub :8116, profile pj1023, proj-c29934c5b878, `scripts/drive/s1023_pj_busy_delete.py`, one Haiku turn, shot `testbed/ui-judge/s1023-pj/140344/55_delete_during_run.png`).
**Source:** drive
**Theme:** Projects
**Ready:** yes
**Tier:** 0

Agent `beta` (claude, Haiku) runs a turn holding a 100 s shell sleep (`run-7b777daa282e`, `running`). Then:

```
DELETE /projects/proj-c29934c5b878?remove_private=true
  -> 409 {"detail": {"code": "project_has_active_run", "message": "project cannot be deleted while a run is active"}}
Settings -> Delete project... -> type the name -> Delete project
  -> role=alert in the dialog: "project cannot be deleted while a run is active"
```

The refusal is correct; it does not say which agent is running, that stopping it (the agent's Stop) is the way through, or that the delete can then be retried. Relocate has the same sentence shape ("project cannot be relocated while a run is active", `hub/hub/project_lifecycle.py:397`).

Cause (verified): `ProjectLifecycleService.delete` raises the bare message (`hub/hub/project_lifecycle.py:245-249`) after counting `Run.status == 'running'` without keeping which.

**Expected:** "aw-pj1023-b can't be deleted while beta is running (run run-7b777daa282e). Stop beta, then delete again." (each running agent named), and the same for relocate. **Test:** `hub/tests/test_project_lifecycle*.py` / the delete-route test: with one `running` run, the 409 message names the agent and the stop remedy (fails today). Seam: Projects (delete) x Runs.

## F1019 (C) -- the Instructions editor saves over instructions written since it loaded: a stale tab silently replaces a newer save, with no conflict check

**Status:** open 2026-10-23. Found by the day sweep `sweep-projects-sweep` (Projects row; scratch Hub :8116, profile pj1023, proj-19b3a5f0a902, Chromium against the served bundle, `scripts/drive/s1023_pj_ui.py instr`, shot `testbed/ui-judge/s1023-pj/140258/40_instr_stale_save.png`).
**Source:** drive
**Theme:** Projects
**Ready:** yes
**Tier:** 1

```
PUT /project/instructions {"content": "v1: use tabs."}
open Settings -> Instructions               editor shows 'v1: use tabs.'
PUT /project/instructions {"content": "v2: written elsewhere, keep this."}   (another tab / window)
in the open editor: type 'v1: use tabs.\nv1b: added here.' -> Save (no refusal, no notice)
GET /project/instructions -> 'v1: use tabs.\nv1b: added here.'      (v2 is gone; no notice)
```

The operator's own pywebview window and a browser tab are an ordinary pair. Instructions ride every agent turn and the clear dialog itself warns "AgentWeave keeps no copy -- there is no history and no undo", so a silently lost write is unrecoverable.

Cause (verified): the query never re-reads on its own (`refetchOnWindowFocus: false`, `hub/ui/src/main.tsx:17`; no SSE event for instructions), and `put_instructions` (`hub/hub/api/v1/instructions.py:53-61`) overwrites with no version or `If-Match`. When the query *does* refetch with a different value (an SSE reconnect invalidates everything), `useEffect(() => setDraft(content), [content])` (`hub/ui/src/components/settings/OtherSettings.tsx:32`) replaces an unsaved draft instead.

**Expected:** the PUT carries the version (or content hash) the editor read, and a mismatch answers 409 "these instructions changed since you opened them" with the current text, which the editor shows beside the draft; a refetch never overwrites a dirty draft. **Test:** `hub/tests/test_instructions.py`: PUT with a stale version -> 409, content unchanged (fails today, no version exists); a UI test that a changed `content` prop leaves a dirty draft alone. Seam: Projects (instructions) x multiple windows.

## F1025 (C) -- the Manager screen's model menu lists no aliases, so a job's model stored as `sonnet` (accepted by the API and stored as written) reads "sonnet -- Not in the model catalog"

**Status:** open 2026-10-23. Found by the day sweep `sweep-projects-sweep` (Runners & models row; scratch Hub :8117, profile rm1023, proj-8717fc708877, `scripts/drive/s1023_rm_holders.py`, Chromium against the served bundle `scripts/drive/s1023_rm_ui2.py`, shots `testbed/ui-judge/s1023-rm/140238/11_manager_runner_menu.png`, `12_manager_model_menu.png`).
**Source:** drive
**Theme:** Runners & models
**Ready:** yes
**Tier:** 0

```
PATCH /projects/{p}/manager/jobs/vault-distillation {"runner_id": <claude runner ch>, "model": "sonnet"}  -> 200 {"model": "sonnet"}
manager_jobs row: model 'sonnet'
```

Project settings -> Manager -> Vault distillation -> Model: the closed menu reads `sonnet`; opened, it lists the eight Claude ids and, last, `sonnet` with the detail **"Not in the model catalog"**. `sonnet` is a declared Claude alias (`GET /model-catalog`: `claude-sonnet-5-5` aliases `["sonnet"]`); the same API answers an undeclared model with 400, so the label tells the operator the Hub holds something it would have refused. Nor can an alias be chosen on this screen, though the Add-agent dialog ("Latest: sonnet -- latest (now Sonnet 5.5)") and the checkpoint model menu both offer them.

Cause (verified): `ManagerSettings.tsx:130` calls `catalogModelOptions(..., { stored: job.model, aliases: false })`; with aliases off, `settingsOptions.tsx:111` appends any stored value not in the list as "Not in the model catalog". `GeneralSection.tsx:136` (checkpoint model) leaves aliases on.

**Expected:** the Manager model menu offers the aliases as the other menus do ("sonnet, the latest -- Now Sonnet 5.5"), so a stored alias reads as that choice; "Not in the model catalog" is kept for a value the catalog really lacks. **Test:** `hub/ui/src/__tests__/managerSection.test.tsx`: a job with `runner_id` of a Claude runner and `model: "sonnet"` renders no "Not in the model catalog". Fails today. Seam: Runners & models (catalog aliases) x Manager jobs (screen).

## F1040 (C) -- a spec-only change whose one task is the fold can never show Fold, and nothing says why

**Status:** open 2026-10-24. Found by the Architect authoring `project-checks-says-what-a-run-does` (size fix, no code); the operator reported "it's not showing the fold into capability".
**Source:** drive
**Theme:** Spec flow
**Ready:** yes
**Tier:** 0

A change document must have a task for every requirement, so a correction with no code gets a task whose work is the fold itself. Approving the document creates that task (`pending`, unassigned). `_fold_state` (`hub/hub/api/v1/spec.py:528`) answers `tasks_open` while any declared task is neither approved nor rejected, and `useSpecPhaseControls.tsx:403` shows Fold only for `ready`, so the task's own work is hidden behind the task. An agent cannot close it either (`pending -> rejected` is operator-only, `task_transitions.py:105`); the operator has to reject a task that was never wrong for the button to appear. Two candidate fixes, not chosen: let a document task be marked as the fold (closed by the fold), or allow a size-`fix` document with no tasks. Also check what the document header says in `tasks_open`: the operator saw no Fold and no reason.

## F1041 (C) -- the fold dialog's retire list is collapsed, so two folds in a row retired nothing they were meant to

**Status:** open 2026-10-24. Found by the Architect checking the operator's two project-checks folds (`spmrg-947e84fcc1eb`, `spmrg-61cd21e89bc4`): both were instructed to retire requirements, and neither merge's content event shows a retirement.
**Source:** drive
**Theme:** Spec flow
**Ready:** yes
**Tier:** 0

`FoldIntoCapabilityDialog.tsx` puts retirement behind a closed "Also retire from the capability" toggle (`retireOpen` defaults to false), below the requirement rows, and confirming with nothing retired raises no question. Retiring is how a change that supersedes a capability requirement keeps the capability from contradicting itself, so skipping it silently leaves two active statements of the same rule. A missed retirement can't be repaired: an archived change refuses a second fold into the same capability (`fold_already_folded`, `spec_service.py:1062`), and capabilities take no direct edits, so the only route is a new change that carries something real to fold. The fold route also accepts `replaces` (replace a capability requirement in place, `spec_service.py` `fold_draft`), which the dialog never sends. A third fold (`project-checks-path-pattern-syntax-and-retirements`) retired two of its three; **`n2` is still active** beside its replacement `project-checks-says-what-a-run-records-its-state-and-each-check` (same statement plus `superseded` and skipped checks): retire it with the next change that folds into project-checks. Candidate fixes, not chosen: open the retire list by default when the change's statements resemble existing ones, show "retiring nothing" next to Confirm, offer "replaces" per row.

## F1044 (C) -- the specs need an ordering

**Status:** open 2026-10-25. Operator request, noted at their ask for later ("We need to create ordering for the spec"); not explored.
**Source:** operator
**Theme:** Spec flow
**Ready:** no
**Tier:** ?

Recorded in the operator's words only. Before any work, ask what is to be ordered and by what: the documents in the Spec tab's list (by phase, by date, by hand), the slices or changes in build order, or the requirements and tasks inside one document.

## F1052 (C) -- approval drops a declared task whose requirements a hand-made task already serves, even when it is different work

**Status:** open 2026-10-27. Found approving slice F (`the-spec-page-redesigned`) on `:8000`.
**Source:** drive
**Theme:** Spec flow
**Ready:** yes
**Tier:** 0

`spec_tasks.materialise` (`hub/hub/spec_tasks.py:398-405`) skips a declared task when every requirement it names is already served by a hand-made task, and approval reports it as `already_served`. Slice F declares two tasks, `mock` and `wire`, over the same twelve requirements; the mock was done on 2026-10-26 as hand-made task-dadec899cc91 linked to all twelve, so approving F on 2026-10-27 created nothing (`approval_report`: `created: []`, `already_served: [mock, wire]`). The wiring work is not on the board, and nothing but the report says so. The rule is right for the task a hand-made task *is* (the mock), wrong for a different declared task that happens to serve the same requirements. **Expected:** a declared task is treated as served only when a hand-made task is matched to it (the same key, or a link the operator made), not when the requirement sets merely overlap; the report says which hand-made task served which entry. **Test:** a document with two declared tasks over the same requirements and one hand-made task linked to all of them: approval creates the second.

## F1055 (C) -- the Hub's acceptance-drive rule and its test-only-task rule cannot both be met: `no_acceptance_drive` asks for a first task every other task waits on, and `test_only_task` says that task fails the project's checks at its own approval

**Status:** open 2026-10-28. Found authoring slice H's candidate (`every-same-file-overlap-reaches-the-operator`, spdoc-19cff1fe73b3) on :8000.
**Source:** drive
**Theme:** Spec documents
**Ready:** no -- needs a decision on which shape the Hub recommends
**Tier:** 1

A first task holding only the three repro tests, with the two fix tasks depending on it, saved with `test_only_task` ("edits only tests and ... depends on it, so it is red until they land and fails the project's checks at approval; put the failing test and the fix that turns it green in one task", `spec_completeness.py:520-546`). Folding each test into its fix task, as that warning asks, then drew `no_acceptance_drive` at approval ("the first task ... is not an acceptance drive every other task waits on", `spec_completeness.py:~395-415`). Every Tier 1/2 document written to CLAUDE.md's "acceptance drive first" rule hits one or the other, and with slice L's checks-before-review the first shape is sent back by the checks. **Options:** count a task whose description and files put its test first as the drive (drop `no_acceptance_drive` when every task carries a test path), or exempt a drive task from the approval checks until its dependents land. Seam: Spec documents x Worktrees & integration (checks at approval).

## F1057 (C) -- the build record and the project view lack the figures a measured comparison needs: no base commit, no landing branch, no runs or models per build, no list of runs in a window, no per-task wall time

**Status:** open 2026-10-28. Found writing slice H's acceptance drive (`scripts/drive/measured_rerun_check.py`) against :8000.
**Source:** code
**Theme:** Accounting & allowance
**Ready:** yes
**Tier:** 1

H's FR-2/FR-3/FR-10 read from the app's views. What no route answers today (the drive falls back to approximations, marked "from a query"): (1) a build's base commit -- `builds.view` has no field; (2) its landing branch and tip (only `main`/`nowhere`, F1056); (3) the runs and their models per build -- no route ties a run or turn to a build, and `/accounting` `recent_turns` is a capped project-wide list; (4) the runs in a time window (no list-runs route); (5) real defects, escaped defects and operator actions per build; (6) FR-7's approval hours held by a failure not the task's, the mender's model, mender wakes with no stalled work and expired mender questions; (7) a "judged again" flag on held evidence; (8) wall time and cost per task (`spend.by_task` is cost only). Also: for flows that predate builds the project view's `wall` is 0 in every part (both H baselines, `GET /stats` groups.spec rows for loop-df5f74816122 and loop-cee87801ae6a), so the baselines' wall-time split comes only from queries. Seam: Accounting x builds x the spec page's build panel.

## F1058 (C) -- a document can be built once: a second build covers only its open tasks, so after one build approves them the next has nothing to build, and a re-run needs a copy of the document

**Status:** open 2026-10-28. Found preparing slice H, whose FR-2 builds one candidate document twice (Fast, then Gated).
**Source:** code
**Theme:** Spec documents
**Ready:** no -- design gap: H assumes a re-build; D defines a build over the document's open tasks
**Tier:** 1

`POST /documents/build` covers the document's tasks whose status is not terminal (`hub/hub/api/v1/spec.py:3479-3494`, then `builds.cover_tasks`); a build whose every task is approved or rejected has finished (`builds.finish_if_done`). After the Fast build approves the candidate's three tasks, a Gated build of the same document would cover none. H's Gated build therefore runs on a twin document with the same payload (`spec/changes/every-same-file-overlap-reaches-the-operator-at-gated`, spdoc on :8000), and `measured_rerun_check.py --gated-document` reads its builds beside the Fast one's. **Expected (if re-building is wanted):** a build may re-run a document from its base commit with fresh tasks, its earlier tasks kept as the earlier build's record. Seam: Spec documents x builds.

## F1061 (C) -- returning a task to its builder after its own check failure neither wakes nor tells the builder

**Status:** open 2026-10-28. Found by the scoped drive of slices L/M/J (:8031, aw-drive-lmj).
**Source:** drive
**Theme:** Checks
**Ready:** yes
**Tier:** 1

Task-222e went to `revision_needed` (origin `checks`, note "the project's checks failed on check run chk-f3ef5307ba17" with the output) at 09:26:57; no builder turn and no queue entry followed. It was picked up only because the tester fired the flow at 09:27:58 and the builder's empty-queue firing found it. Outside a flow nothing would pick it up. Slice L does not promise a wake; the send-back is otherwise silent. Area: Worktrees & integration x Inbound queue.

## F1066 (C) -- a resubmission without `roadmap` silently unlinks a document from its roadmap slice

**Status:** open 2026-10-28. Found by the scoped drive of slices D/D2/E (:8032).
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

The lead's first `submit_spec_document` carried the roadmap link; its third and fourth resubmissions dropped it and the stored document ended with no `roadmap`, with no warning. With D2's next-slice offer, an unlinked slice reads as unclaimed and can be offered again. Expected: a save that drops the link of a document that had one warns (or keeps it). Area: Spec documents.

## F1067 (C) -- three small refusal/field defects in slices D and D2: `next-slice/take` with an unknown agent answers code `no_offer`; `builds/{id}/stop` ignores a `reason` body; `amendments[].task_id` stays null after an accepted add_task

**Status:** open 2026-10-28. Found by the scoped drive of slices D/D2/E (:8032).
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

`POST .../next-slice/take` naming `ghost` -> 422 `code: "no_offer"`, message "ghost is not an open agent" (wrong code for the refusal). `POST .../builds/{id}/stop {"reason": ...}` -> stored reason always "stopped by the operator". PATCH of cap and window on a `finished` build is accepted as a no-op. After an accepted add_task, the response's `task_created` names the task but `amendments[].task_id` stays null. Area: Spec documents x builds.

## F1068 (C) -- on a hand-driven build each amendment decision queues a paid turn for the proposing lead, and those unbound lead runs are not counted in the build's spend

**Status:** open 2026-10-28. Found by the scoped drive of slices D/D2/E (:8032). Possibly by design for the decision input; the uncounted spend is not.
**Source:** drive
**Theme:** Accounting & allowance
**Ready:** no -- decide whether a hand build's lead is told by a turn
**Tier:** 1

Hand "starts no turn at all", but each amendment decision queued input for the lead; `run-3895d6d08359` ran ($0.006) and two more entries were queued. Runs not bound to a build task are not in the build's `spent_usd` or figures (`cost.lead` 0.0), so a cap cannot see them. Also (D): lowering a hand build's cap below its spend ($0.01 vs $0.92) changes nothing and says nothing. Area: Inbound queue x Accounting.

Drive record D/D2/E (what held, 20 Haiku turns, $2.26): D -- build recorded with every setting, a second Build 409 naming the running one, legible refusals (unknown agent, inverted window, bad level), level on tasks and transitions, declared builders applied and `ghost` reported unresolved, the flow staffed only builders and reviewers, the build finished and its job disabled, `spent_usd` equal to turn_usage. D2 -- a lead's add_task proposal left the board unchanged and accepted joined the running build at its level and builder; `proposal_decided`, `amendment_stale`, decline-needs-reason, non-author 403, `draft_next_slice_retired` all legible; the next-slice offer raised and taken once; a hand commit raised a notice in ~14 s and a `reset --hard` as a rewrite in ~15 s; rigor retired. E -- four approvals answered ~1 s each, one ~60 s gather, a conflicting task removed before the check naming the file and the other task, the breaker found by one narrowed run and sent back alone with output, the rest landed, sent-back work cannot land or be re-approved, landing state on the checks route with position and seconds, a restart mid-gather lost and repeated nothing. Not reached: every UI criterion, the lead driver, Gated, budget-cap stop on a flow, lands-nowhere, M's override inside a batch, dependent-waits-for-prerequisite.

## F1072 (C) -- slice F/G/I friction: Ctrl+K's "Spec documents" is a flat list while the real picker lives on Ctrl+Shift+K; a running build's header offers "Close 1 open task as already built"; agent/model groupings put wall time under synthetic rows; Check's warnings vanish after a refused Approve; palette "settings" ranks a conversation first

**Status:** open 2026-10-28. Found by the scoped browser drive of slices F/G/I (:8033); shots `run1_full.png`, `activity_Agent.png`, `activity_Model.png`, `check_after.png`, `approve_click.png`, `palette_settings.png`.
**Source:** drive
**Theme:** Spec documents
**Ready:** no -- each needs a small decision
**Tier:** 1

(1) `picker-everywhere` names "the Ctrl/Cmd+K picker", but Ctrl+K's Spec documents section has no filters, order or shortcuts; the picker is Ctrl+Shift+K. (2) A running build's header shows the close-as-built strip for the task the build is working. (3) In G's by-agent and by-model groupings, wall time and checks sit under rows named "checks and wall time" and "no model recorded"; totals are right, labels mislead. (4) After Approve is refused (steps_skipped) the inline Check marks and the "N warnings" chip disappear. (5) Palette "settings" puts a conversation titled "Reply with exactly the word OK..." first; Enter opens it. Also seen, pre-existing: Add-agent and Vault Add dialogs open with focus on Close (F931 family); Overview "Running now" says no agent works while a run is parked on ask_user; the approval report quotes a raw `POST /api/v1/.../journey?path=...` to the operator (F574 family). The drive also saw F1064 independently: the Hub's own "Integrate approved work 63e3bd59605b" raised "master moved outside the Hub" on Overview (event 09:47:58).

Drive record F/G/I (what held, 8 Haiku turns): F -- the header offers exactly each state's actions (writing: Check; checked: Approve with Approve-and-build; approved: Build; building: running chip, Stop, Raise cap; finished: Fold), Check never moves the phase, warnings inline and in the outline, Approve anyway carries into the build, build figures (3m3s = 1m40s building + 1m16s reviewing + 7s waiting; $0.43) match the DB, the list marks a running build, filters persist across reload, anchors and Back/Forward restore position, no literal colours and no transitions under reduced motion. G -- `turn_usage`, `/accounting`, `/stats`, `/ledger` and the Activity view agree to the micro-dollar ($0.729663); spec rows sum to the project; a build's figures read only that build; wall parts sum to the total; four groupings agree; `since` works; 12 task events gave 2 stats fetches. I -- App settings from rail and palette with notifications moved out of Project settings; decline-one and the ended-wait question row; F1027-F1032 re-drives hold (F1027 partly). Not reached: the mock server, archived header, the mender on the spec page, G's send-back/verdict/beside-failing figures, decline-all, merge-row retry, zero-project rail.

## F1075 (C) -- a build's checks queue two at a time, with no view of queue time, and the side-by-side suites make timing tests fail; Fast spent 70 of its 89 minutes in checks

**Status:** open 2026-10-28. Found by slice H's Fast build (:8000, `build-f7c5b7855dbc`).
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** no -- decide the policy (serial checks, a per-task subset, or a slot count)
**Tier:** 1

The builder's three turns ended by 11:19. Each task's Hub suite then ran 40 to 45 min side by side (about 12 min alone). The third task's run (`chk-a6633ef823ea`, started 11:17) began its suite only at 11:50, when a slot freed. The build panel's `checks` (4214 s) counts the wait and the run together. The load made `test_a_busy_project_opens_inside_a_second` (1.009 s against 1.0) and `test_more_operator_streams_than_the_pool_holds_all_open` fail. The Hub approved over them as not the task's and opened follow-up `task-c9d09a9fd379` ($0.18, in no build's cost). Area: Worktrees & integration x Accounting & allowance.

## F1076 (C) -- the mender woke on a "no progress" stall while a healthy check run was queued, called it possibly hung and recommended killing it

**Status:** open 2026-10-28. Found by slice H's Fast build (:8000), stall `stall-c6e926fdf51d`, question `q-3985f03c03f5`.
**Source:** drive
**Theme:** Jobs & loops
**Ready:** yes
**Tier:** 0

At 12:27 the loop had nothing moving since 11:52 because two check runs were in progress; the stall detector raised `no_progress`. The mender's question said `chk-a6633ef823ea` was "at 70 min (previous run 41 min)" and "may be hung", with "Restart checks" recommended. The run was healthy: it had waited 33 min for a slot and finished at 12:29. A loop whose tasks are in running checks is not stalled. The mender also reads a check's age from when it was queued, not from when it started. Area: Jobs & loops (mender).

## F1077 (C) -- a build record's `spent_usd`, which the cap reads, leaves out the mender turns its own figures count ($0.87 vs $1.05 at Fast, $2.47 vs $2.87 at Gated)

**Status:** open 2026-10-28. Found by slice H (:8000). Related to F1068.
**Source:** drive
**Theme:** Accounting & allowance
**Ready:** no -- decide whether mender turns count toward a build's cap
**Tier:** 1

`builds[].spent_usd` = building + reviewing. The build panel's `figures.cost` and `GET /stats`'s build row add `mend`. The two disagree on one screen, and a cap cannot see mender spend. A follow-up task the build's checks opened (`task-c9d09a9fd379`) is in neither. Area: Accounting & allowance.

## F1078 (C) -- a check run with failing tests that were approved over as not the task's is recorded as `passed`

**Status:** open 2026-10-28. Found by slice H's Fast build (:8000), `chk-2cbb324baa52` on `task-e50d0d42e298`.
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** yes
**Tier:** 0

Two tests failed in the run and passed alone. The Hub classified them as flaky, approved and opened a follow-up. The run's `state` is `passed` and `figures.checks` counts 3 passed, 0 failed, so any count of failed check runs (FR-8 of slice H, the build panel) misses it. A "passed with N failures not the task's" state, or a count beside it, would keep it visible. Area: Worktrees & integration.

## F1079 (C) -- slice H: numbers no view shows: a build's base commit, the per-run model, operator actions, escaped defects, mender wakes with nothing stalled, expired mender questions, and any wall split for flows before builds

**Status:** open 2026-10-28. Found by slice H's comparison (`.agentweave/vault-notes/2026-10-28-the-measured-re-run.md`), whose cells marked "from a query" are these.
**Source:** drive
**Theme:** Accounting & allowance
**Ready:** no -- the build view needs `base_sha` (FR-2 of slice H fails on it today); the rest are a decision on what the project view should carry
**Tier:** 1

`measured_rerun_check.py` builds-match fails only on "the build record names no base commit". The models come from `/accounting recent_turns` (latest turns only, not tied to a build). Also seen: the build's start answer reads `reviewer: null` while `reviewers: ["QA"]` (the flow's delivery reviewer, not the build's), which reads as "no reviewer". Area: Accounting & allowance x Spec documents.
## F1046 (C) -- a spec document's task can name its reviewer but not who builds it

**Status:** open 2026-10-25. Found authoring `the-app-stays-responsive-while-agents-run`, when the operator asked to define each task to a specific agent by capability and let the rest be picked up free.
**Source:** code
**Theme:** Spec flow
**Ready:** yes
**Tier:** 1

`spec_payload.Task` (`hub/hub/spec_payload.py:136-170`) carries `reviewer` but no builder. The flow already honours a task's assignee: it resumes a task with an `assignee` only on that agent, and staffs unassigned tasks on the default agent and then any free one (`hub/hub/scheduler.py:2031-2125`). So per-task capability routing works, but only if the operator sets every assignee by hand on the board after approval. The author, who knows which tasks need the stronger model, has nowhere to write it down. Proposed shape: an optional per-task builder name, resolved against the roster when the task is materialised, kept rather than refused when it does not resolve (the same rule `reviewer` follows).

## F1091 (C) -- a landing's send-back that is refused leaves the task approved with its landing recorded sent back

**Status:** open 2026-10-30. Found by DeveloperOpus reading the landing code (task-e4a49edf95a0); the branch has not been seen to fire and no gate is known to refuse this edge.
**Source:** code reading
**Theme:** Landing
**Ready:** yes
**Tier:** 0

`_send_back` (`hub/hub/landing_queue.py:1850`) sets the landing to `SENT_BACK` before calling `apply_transition`, and its `except TransitionRefusedError` (`:1878`) only logs, then commits (`:1880`). If the approved -> revision_needed transition is refused, the task stays `approved`, its work is not on main, and nothing is left to land it. The work cannot land this way, so this is a stuck task and not bad code on main. **Expected:** a refused send-back leaves a state that someone is told about and can act on, not an approved task that never lands. **Test:** make `apply_transition` raise `TransitionRefusedError` in `_send_back`; the task must not read as approved with a sent-back landing and no signal.

## F1093 (C) -- Run now on a build past its window answers a bare 500 "Failed to fire job" although the stop worked

**Area:** Jobs & loops. Driven 2026-10-30 on :8010 at 4dba06e: a flow build whose `window_end` has passed; `POST /jobs/{id}/run` answered `500 {"detail": "Failed to fire job"}`, while the build correctly stopped with "the build's window closed at ...; extend it to resume" and `build_stopped` was emitted. The route's message is in `hub/hub/api/v1/jobs.py`; which of its branches answered was not traced. Expected: an answer saying the build stopped and why.
**Status:** open 2026-10-30.

## F1096 (C) -- a completion with uncommitted work first spends a full check run on the older commit

**Area:** Worktrees & integration. Seen 2026-10-30 on task-bf5ebb75161c. DeveloperOpus reports moving the task to completed with changes uncommitted, and HEAD still at 95bc0b1 straight after, although `update_task`'s description says uncommitted changes are committed first. Check run chk-48a8b37428a3 spent 25 minutes on 95bc0b1 and passed. The Hub then ran chk-cb53562db0a8 on the tip c0b79c3 (14:22 to 14:48, passed), and review opened only after that, so the tip was checked: the cost is the wasted run, not a gap. Not established: why this completion did not commit the worktree.
**Status:** open 2026-10-30.

## F1094 (C) -- a capability's header reads `Approved` with a change's stepper, though its phase is `current`
**Status:** Open. Found driving New capability (task-bf5ebb75161c) on 2026-10-30; true of every capability, not only a new one.
**Source:** found by driving
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

`stateOf` (`hub/ui/src/components/spec/page/adapt.ts:107`) and the list's mapping (`:223`) send every phase but `exploring` and `archived` to `approved`, so a capability the Hub reports as `phase: current` shows an `Approved` pill and the Writing/Approved/Building/Done ribbon, and its Builds section says a build can start once the document is approved. **Expected:** a capability reads as current, with no change journey. **Test:** render the header from a record with `kind: capability, phase: current`; it must not read `Approved` or show the ribbon.

## F467 (D) — facts about Copilot CLI that the exploration's appendix recorded wrongly

**Status:** open (a record, not a defect), filed 2026-09-30 from `a-copilot-agent-runs-over-acp`'s rounds and captures (task 10.1), so later slices do not inherit the old statements.

- `copilot.exe --no-auto-update` runs the npm-installed build (1.0.88 here), not the bundled 1.0.75 appendix C named.
- `~/.agents/skills` **does** load under a custom `COPILOT_HOME` ("Inherited", `r1-probe-agent.log:13`); appendix A §E said it did not.
- Copilot's MCP `timeout` defaults to 30 s, which would cut every `ask_user`; the Hub's server config sets 660 s.
- An empty `--available-tools=` means **no filter** (`app.js` `Y0`), so with `--allow-all-tools` it approves every tool; tools are removed with `--excluded-tools=builtin:*,mcp:*,custom:*` instead (task 1.2 confirmed zero tools offered).
- Project-level custom agents (`.github/agents/`, `.claude/agents/`) outrank `$COPILOT_HOME/agents/` (DOCUMENTED), so a repository agent named like the Hub's shadows it; the Hub checks the selected agent's marker and deselects on a mismatch.
- The UNC-path stall the same review measured is F464.

## F472 (D) — `each-runner-cli-is-one-adapter` task 2.3's own bullet says to delete `codex_appserver.uses_app_server`; its two real callers live in files tasks 3.3/3.6 own, not 2.3's

**Status:** open (a record, not a defect), filed 2026-10-01 from the night window's ORDER 1/24 task 2.3, writing `hub/hub/runner_adapters/codex.py`.

Task 2.3's text: *"`CodexAdapter.transport` takes `uses_app_server`'s body, keeping its `(flags or [])` guard (review 3); delete `codex_appserver.uses_app_server` (R2, design D5)."* Design D5 itself names the two real callers: `agent_trigger.py:1210` and `agents.py:253` (now `:1221`/`:260` on today's tree — a 4-line docstring shift, not a behaviour change). Both import the name directly (`from ...codex_appserver import ... uses_app_server`), not through a module-qualified call, so deleting the function the moment `codex.py` lands would raise `ImportError` at interpreter start for every test that imports `hub.api.v1.agent_trigger` or `hub.api.v1.agents` — which is effectively the whole Hub suite, not a narrow regression. tasks.md's own task breakdown puts rewiring those two call sites in **3.3** (`agent_trigger.py`, the trigger: "the sentinel strip is the union over adapters") and **3.6** (`api/v1/agents.py`: "the collaboration verdict comes from `adapter.collaboration`"), neither of which has landed yet — the same shape of gap F470/F471 already named (a design/task-text statement that assumes a later task's state).

`CodexAdapter.transport` and `CodexAdapter.collaboration` were written this task with `uses_app_server`'s/`agents.py:256-274`'s logic reproduced inline (`codex_appserver.APP_SERVER_OPT_OUT_FLAG not in (flags or [])`, and the same text respectively) rather than calling the soon-to-be-dead function, so the adapter itself does not depend on it surviving. `codex_appserver.uses_app_server` was left in place, undeleted, so `agent_trigger.py`/`agents.py` keep working unchanged until 3.3/3.6 actually replace their calls with `get_adapter(cli).transport(flags)`/`.collaboration(flags, yolo=...)` — whichever of those two tasks removes the last caller is the one that should actually delete the function. Re-read `agent_trigger.py:1221` and `agents.py:260` fresh at that task's IMPL, not this note, to confirm both are gone before deleting `uses_app_server`.

## F744 (D) -- small items from the 2026-10-18 fix pass

**Status:** open 2026-10-18. Filed from the 2026-10-18 fix pass, by reading the code.
**Source:** review
**Theme:** Resilience

(1) `copilot_acp.turn_ended_on_refusal` and the `refusal_continued` notice append "." after a reason that may already end in one ("..").
(2) The integration preview in `hub/hub/api/v1/tasks.py` treats an exception from workspace resolution as "git failed" and drops the conflict answer it already had.
(3) `test_manager_jobs.py:275` uses a fake `next(...)` with no default, so a regression hangs the test instead of failing it.
(4) `test_permission_approver.py` row 1.5a3 says `cp x $(dirname $PWD)` is refused because of the inner `$PWD`. But `cp x $(dirname "$(pwd)")` is already allowed as a runtime value, so the row protects less than it reads.

## F748 (D) -- a runner that re-reads its settings mid-turn sees a write made earlier in the same turn

**Status:** open 2026-10-18. Filed from the 2026-10-18 decision pass (F737 group); residual of the design, not a regression.
**Source:** review
**Theme:** Permissions & sandbox

F737's fingerprint runs once per turn launch (`runner_config_guard.hold_if_changed`). A runner that reloads its configuration during a turn picks up a change written earlier in that same turn before any launch can hold it. Related: F737.

## F758 (D) -- the approval gate's remedy for an awaiting piece recorded for an earlier wording is one the Hub refuses

**Status:** open 2026-10-19. Found re-driving F751 (`scripts/drive/d1019_night_recheck_spec.py`, scratch Hub :8140).
**Source:** drive
**Theme:** Requirements & evidence
**Ready:** yes -- repro below; wording is a Tier 0 text change.
**Tier:** 0

A task serves FR-1, a builder records evidence for it (`awaiting`), the requirement is then reworded, and a reviewer approves the task. F751's fix correctly leaves the stale piece `awaiting`, so the approval answers 409 `gate_unsatisfied` with `unaccepted: [{kind: awaiting_evidence, ...}]` and the remedy "accept the evidence, or grant an agent the capability to accept it" (`hub/hub/requirement_gate.py:93`). But `POST .../project/spec/evidence/{id}/decision {accepted}` answers 409 `evidence_stale` ("cannot be accepted. Record new evidence against the current wording"), and so would an agent granted the capability. What worked: the operator **rejecting** the piece (200), after which the PATCH to `approved` answered 200. The gate should name the piece as an earlier-wording one and say "reject it or record new evidence", not offer an action that is refused. Related: F751, F692.

## F766 (D) -- a change's roadmap slice can be named after the fact only through the API: no screen or tool calls `PUT .../roadmap`

**Status:** open 2026-10-19. Found in the spec sweep (`scripts/drive/s1019_spec.py`, `s1019_spec_ui.py`, scratch Hub :8160), seen in a browser.
**Source:** drive
**Theme:** Spec documents
**Ready:** yes.
**Tier:** 0

`PUT /projects/{id}/project/documents/{path}/roadmap` (F674's backfill, `hub/hub/api/v1/spec.py:882`) works, and every refusal it gave was legible: an unapproved roadmap, an unknown slice (the message names the slices), a roadmap linking itself, an unknown roadmap, a path escape (400), and a different link ("already names slice 'first' of ...; reopen it to change its slice"). The same link twice is a no-op (`changed: false`), on an archived change too. The roadmap page shows the result: "first -- archived in spec/changes/cs-sweep-.../spec.json", "second -- not started".

But nothing in `hub/ui/src` calls the route (`hub/ui/src/api/spec.ts` has no roadmap write), and no MCP tool or `/agent-actions` route does either. A "not started" slice offers no way to name the change that built it, and a change's own page has no such control. The visibility roadmap's backfill was done with a script (`d1017_roadmap_backfill.py`).

Expected: a "Roadmap slice" control on a change document's page, or "Link a change..." on a not-started slice, that calls the route and shows its refusal sentence. Seam: Spec documents (roadmaps).

## F778 (D) -- a UTF-16 text file (what PowerShell 5.1's `>` writes) is reported `binary` by `/workspace/file`, so the files tab cannot show it

**Status:** open 2026-10-19. Found in the ledger sweep (`scripts/drive/s1019_ledger.py`).
**Source:** drive
**Theme:** Conversations & composer
**Ready:** yes -- repro below.
**Tier:** 0

`utf16.txt` written with `encoding="utf-16"` (BOM + "hello in utf-16"), tracked. `GET /workspace/file?path=utf16.txt` -> `200 {"binary": true, "size": 36, "content": null}`. `read_workspace_file` (`hub/hub/workspace_file.py:84`) treats any NUL in the first 8000 bytes as binary, and every ASCII character in UTF-16 carries one. On Windows PowerShell 5.1, `echo x > notes.txt` produces exactly this. Expected: a UTF-16 BOM (`FF FE` / `FE FF`) is decoded as text before the NUL sniff. Failing test beside the existing workspace-file tests. Seam: Conversations & composer (files tab).

## F779 (D) -- `send_message` from a task-bound run does not record the task, so the Ledger's "Between agents" lane has no task link for a message sent mid-task

**Status:** open 2026-10-19. Found in the ledger sweep (`scripts/drive/s1019_ledger_p2.py`, `_p3.py`).
**Source:** drive
**Theme:** Logs, events & SSE
**Ready:** yes -- repro below.
**Tier:** 0

builder's run `run-af8019ec2ad9` was bound to `task-5f15fb870841` when it sent rev "add fixed". `messages.task_id` is NULL, so `GET /ledger` -> `messages[].task_id: null, task_title: null`, and the Ledger's "Between agents" rows link nowhere. rev's reply, from a run bound to no task, is NULL as well. `send_message`'s `task_id` is optional (`hub/hub/mcp_server.py:271`), and the Hub does not default it from the sending run's bound task. Expected: when omitted, `task_id` defaults to the sending run's `task_id`. Failing test: an agent-actions `send_message` from a run bound to a task, with no `task_id` -> `Message.task_id` equals the run's task, and the ledger's message row carries `task_title`. Seam: Inbound queue & messages x the Ledger.

## F797 (D) -- the granted root's access select is too narrow for its own label: "Read and write" reads "Read and wr"

**Status:** open 2026-10-20. Found by the day sweep `sweep-reach-sweep` (screenshot `testbed/ui-judge/s1020-reach/100046/04_agent_bad_save.png`, 1440 px, light).
**Source:** drive
**Theme:** Permissions & sandbox
**Ready:** yes
**Tier:** 0

`ReachGrantsEditor`'s access `Select` has `wrapperClassName="w-28"` (`hub/ui/src/components/environment/ReachGrantsEditor.tsx`), which clips the selected "Read and write" to "Read and wr" on both the project and agent pages. Expected: the select fits its longest option (e.g. `w-36`). Seam: Permissions & sandbox (Reach UI).

## F803 (D) -- small legibility slips on the vault-by-path doors: doubled backslashes in the CLI's refusals, a UTF-8 BOM kept in a source's text, and a runner-less firing reading "runner default"

**Status:** open 2026-10-20. Found by the day sweep `sweep-vault-sweep` (scratch Hub :8143).
**Re-verified 2026-10-22** (day sweep `sweep-vault-sweep`): still bites -- `agentweave --profile vt1022 --port 8115 vault add nope.md --no-distil` -> `refused  C:\Users\...\nope.md: No file or folder at 'C:\\Users\\huida\\...\\nope.md'.` (the reason's path doubled, the result's path not).
**Source:** drive
**Theme:** Knowledge vault
**Ready:** yes
**Tier:** 0

- `agentweave vault add missing.md --no-distil ...` prints `refused  C:\...\missing.md: No file or folder at 'C:\\Users\\huida\\Documents\\aw-vault-1020\\notes\\sub\\missing.md'.` The CLI resolves to a Windows path and `vault_intake._locate` quotes it with `{given!r}` (`hub/hub/vault_intake.py:149-165`), doubling every backslash: the class F656 fixed for permission verdicts (`mcp_server._quote`). Same in the "relative" and "outside" sentences an agent reads.
- A text file written with a UTF-8 BOM (PowerShell 5.1's `Set-Content -Encoding utf8`) is stored with it: `POST /vault/paths` answered `"opening": "\ufeffinside"`, and the Vault tab's entry preview starts with the invisible character (`in.md`, `loop/a.md`). `add_all` decodes with `data.decode("utf-8")` (`vault_intake.py:298`); `utf-8-sig` drops it.
- The Manager page's firing for F801's runner-less report reads `failed · runner default · 0.0 s` although there was no runner (the event has `"runner_id": ""`).
- (2026-10-21, sweep-vault-sweep) `agentweave vault add ... --distil` with the job off prints the Hub's API sentence "Or add the files with distil set to false, and distil them later." The CLI's flag is `--no-distil`, so the CLI could say that instead.

Expected: quote paths as written (reuse `_quote`), decode text with `utf-8-sig`, and word a runner-less firing "no runner". Tests: `hub/tests/test_vault_paths.py` for the first two; a UI test for the firing row. Seam: Knowledge vault (add by path) x Manager jobs (firing list).

## F805 (D) -- the files tab's refusals are less legible than its neighbours: an oversized file reads "file is 11200000 bytes, exceeding the 1048576 byte limit", and a file that is not UTF-8 shows replacement characters with nothing saying why

**Status:** open 2026-10-20. Found by the day sweep `sweep-questions-sweep` (scratch Hub :8146, Chromium against the served bundle).
**Source:** drive
**Theme:** Conversations & composer
**Ready:** yes
**Tier:** 0

In the side panel's Files view, `huge.txt` (11.2 MB) opens to `file-tab-error` "file is 11200000 bytes, exceeding the 1048576 byte limit". That is the raw `WorkspaceFileTooLargeError` text (`hub/hub/workspace_file.py:36-40`, passed through as the 413 detail by `hub/hub/api/v1/workspace.py`). It has unformatted numbers, while the binary notice beside it formats them ("This file is binary (16,384 bytes) and cannot be previewed."), and it does not say what would work instead (open it in an editor; "Insert into composer" still works and the agent can read it). `latin1.txt` (bytes `caf\xe9 cr\xe8me`) renders as "caf� cr�me" labelled "Plain text". `read_workspace_file` decodes with `errors="replace"` (`workspace_file.py:84`) and returns no flag saying anything was replaced.

Expected: the oversized sentence uses readable sizes and names the alternative ("This file is 11 MB; the preview reads up to 1 MB. Insert it into the composer to let the agent read it."), and a lossy decode says so (a `decoded_lossily` flag the tab turns into one line). Tests: `hub/tests/test_workspace_file*.py` for the flag; a `FileTab` UI test for both sentences. Seam: Conversations & composer (side panel files tab) x the workspace file route.

## F809 (D) -- small slips around the Add-project dialog and the Runners page: "Workingâ€¦" mojibake, a Hide control under its own popup, doubled backslashes in the browser's reasons, a long runner name over its own buttons

**Status:** open 2026-10-20. Found by the day sweep `sweep-projects-sweep` (scratch Hub :8147, Chromium against the served bundle).
**Source:** drive
**Theme:** Projects
**Ready:** yes
**Tier:** 0

- While Add project waits, its button reads **"Workingâ€¦"**. `ProjectManagerModal.tsx:249` holds the bytes `Working\xc3\xa2\xe2\x82\xac\xc2\xa6`, a UTF-8 ellipsis decoded as cp1252 and re-encoded, there since `5ee1a22` (2026-08-04), and the served bundle carries it. It is the only such string in `hub/ui/src` (scan for `â€` / `Ã`). Screenshot `testbed/ui-judge/s1020-p-picker/105638/05_pending.png`. A slow path (F806) keeps it on screen for 21 s.
- With the native dialog available, the in-Hub browser opens from "Browse within the Hub instead", which then reads "Hide the in-Hub browser". The open picker covers it: `elementFromPoint` at the link's centre is the picker's `C:\` root button. The control that should close the picker cannot be clicked (clicking outside or pressing Escape works). The picker also extends past the modal and covers Cancel and Add project.
- `/fs/list` reasons are `str(OSError)`, which repr-quotes the path. The picker therefore shows "Can't read this directory: [WinError 3] The system cannot find the path specified: 'C:\\does\\not\\exist'", with every backslash doubled, which is F803's class. `hub/hub/fs_browse.py:116`: word it from `exc.strerror` and the path as written.
- A runner name may be 256 characters (`schemas/runners.py`, `models.py:343`). On the Runners page a 200-character name runs off the page in one unbroken line, over that row's Edit and Delete icons (`testbed/ui-judge/s1020-p-keys/110136/21_runner_delete_refused.png`). Every runner select option grows the same way.

Expected: the literal `…`, a lint or test that fails on mojibake sequences in `hub/ui/src`, the in-Hub browser's toggle outside the area the picker covers (or the picker opening below it), reasons quoted as written, and runner names truncated with a title tooltip. Tests: a source scan in `hub/ui/src/__tests__/`, `hub/tests/test_fs_browse*.py` for the reason text, and a RunnersPage snapshot with a long name. Seam: Projects (Add-project dialog) x Runners & models (Runners page).

## F813 (D) -- `request_agent` and Add agent refuse an archived agent's name as merely "already exists", without saying it is archived or that names are never reused

**Status:** open 2026-10-20. Found by the day sweep `sweep-agents-sweep` (scratch Hub :8149, a real Haiku turn `run-b1b305376af9`).
**Source:** drive
**Theme:** Agents
**Ready:** yes
**Tier:** 0

With `eps` archived, alpha's `request_agent {"name": "eps", "template": "beta"}` came back `Hub rejected POST /agents/request (409): Agent 'eps' already exists` (`hub/hub/api/v1/agents.py:2734`). `POST /agents {"name": "eps"}` gives `409 "Agent name 'eps' already exists in this project"` (`:646`). eps is in no picker, so an operator or agent that looks for it finds nothing to act on. The design keeps archived names taken on purpose (F465's note: "a name is never reused"), and the sentence should say so. The budget refusal beside it already reads well: "Project agent budget exhausted (4/4) ... Ask the operator to archive an agent ... or to raise the agent budget in Settings."

Expected: "'eps' belongs to an archived agent; a name is never reused. Unarchive eps, or choose another name." on both doors.

Also measured 2026-10-21 (`sweep-agents-sweep`, scratch Hub :8154): F811's new case-twin refusal has the same gap. With `eps` archived, `POST /agents {"name": "Eps"}` -> 409 "an agent named 'eps' already exists in this project; names must differ by more than case, ...", which does not say eps is archived, and the identical name still answers the bare "Agent name 'eps' already exists in this project". The same sentence fits both: name the archived agent and how to get it back. Failing test: in `hub/tests/test_request_agent*.py`, archive then request the same name, asserting the 409 detail contains "archived". Seam: Agents.

## F818 (D) -- the dismiss refusal tells a conversation far past its threshold that it "has not reached its threshold"

**Status:** open 2026-10-20. Found by the day sweep `sweep-checkpoints-sweep` (scratch Hub :8150). Re-verified 2026-10-21 (sweep-checkpoints-sweep, :8153): `conv-0d23c17ee50a` at 31,779 tokens against 8,000, warning cleared by a Checkpoint now, dismiss -> 409 "... it has not reached its threshold." Still open.
**Source:** drive
**Theme:** Checkpoints
**Ready:** yes
**Tier:** 0

The successor `conv-1dbec82e6c34` was at 38,493 tokens against an 8,000-token threshold. Its warning had been cleared by a Checkpoint now. `POST /conversations/conv-1dbec82e6c34/dismiss-checkpoint-warning` -> 409 "This conversation has no checkpoint warning to dismiss: it has not reached its threshold. …" (`hub/hub/api/v1/checkpoints.py:320`). The refusal's reason is wrong for this case. The conversation has no warning because a checkpoint was just taken, or because nothing new happened since.

Expected: word it from the state: "This conversation has no checkpoint warning showing, so there is nothing to dismiss; a dismissal answers a warning that is showing." Failing test: dismiss on a conversation whose usage is past the threshold and whose warning is NULL; assert the detail does not say "has not reached". Seam: Checkpoints.

## F821 (D) -- Run on a loop that has ended answers 400 "Job is disabled", whose remedy, enabling it, is refused 409 "loop_ended"

**Status:** open 2026-10-20. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8160).
**Source:** drive
**Theme:** Jobs & loops
**Ready:** yes
**Tier:** 0

```
loop B (stop_at reached by the scheduler's own tick): ending_state "stopped"
POST /jobs/job-8805289b78c5/run          -> 400 "Job is disabled"
PATCH /jobs/job-8805289b78c5 {"enabled": true} -> 409 {"code": "loop_ended", "message": "This loop has ended (loop stop time reached (...)) at ... and cannot be restarted ... Create a new loop with the work instead."}
```

F222 fixed exactly this shape for an archived job: `run_job` checks `archived_at` before `enabled`, because "disabled" names a remedy the guard refuses (`hub/hub/api/v1/jobs.py:1753-1762`). An ended loop takes the same path and still gets the misleading word. The UI disables the Run button on an ended loop's card (measured in Chromium), so this reaches an agent's `run_job` or the agent plane, and anyone using the API. It was recorded as held on 2026-08-29 (row 11, before F222). **Expected:** before the `enabled` check, a job whose loop has `ending_state` answers 409 with the same `loop_ended` body as the PATCH. **Test:** next to F222's in `hub/tests/test_an_archived_job_stays_retired.py`: an ended loop's run answers 409 `loop_ended`.

## F822 (D) -- a job firing's id and an agent run's id share the `run-` prefix, so a firing id pasted into a run route reads "This run has no trace"

**Status:** open 2026-10-20. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8160).
**Source:** drive
**Theme:** Jobs & loops
**Ready:** yes
**Tier:** 0

`POST /jobs/{id}/run` answers `"job_run_id": "run-9b02d383538b"`, and the turn it started is `run-7d179cba3a19`. Both are minted `f"run-{short_id()}"` (`hub/hub/scheduler.py:3693`, `:4190`, `:4410` for `JobRun`; the same prefix as `Run`). `job_fired` events carry `job_run_id` with that prefix. `GET /traces/by-run/run-9b02d383538b` -> 404 "This run has no trace", but it is not a run at all, and `GET /traces/by-run/run-7d179cba3a19` -> 200. A reader correlating a firing with its turn by id, as the skill's own trap list warns ("Job events carry `job_run_id`, not `run_id`"), has nothing in the id to tell them apart. **Expected:** new `JobRun` ids use their own prefix (`jrun-`). Existing rows keep theirs, since ids are opaque and nothing parses the prefix (grep before changing). **Test:** a firing's `job_run_id` does not start with `run-`.

## F826 (D) -- once approved, a task's card credits the reviewer (B: "@gamma") or nobody (Land: "Unassigned"); the author appears only in the story

**Status:** open 2026-10-20. Found by the day sweep `sweep-tasks-sweep` (scratch Hub :8170).
**Source:** drive
**Theme:** Tasks
**Ready:** yes
**Tier:** 0

```
B: beta in_progress -> completed (run-2d1f9cc60be2); POST /agent/trigger {"agent": "gamma", "review_task_id": B} -> gamma under_review -> approved
GET /tasks/B -> assignee "gamma"; Dependencies view card: "@gamma"
A: alpha completed; POST /tasks/A/land -> assignee null (tasks.py:1996 "the author's hold"); drawer Details: "Assignee Unassigned"
```

Staffing a review writes the reviewer into `assignee` (by design, F70's ordering) and Land clears it, and nothing restores the author when the task reaches `approved`. Two approved tasks built by alpha and beta read "Unassigned" and "@gamma" on the board. The story ("beta worked", "alpha worked") is right. **Expected:** at `approved` the card names who built it (the last completer from `task_transitions`), or labels the reviewer as reviewer ("reviewed by @gamma"). **Test:** a board-card test with an approved task whose assignee is its reviewer renders the completer's name. Design gap, small.

## F827 (D) -- a hand-made task whose prerequisite was rejected is told to "edit the document that declared this dependency": there is no document

**Status:** open 2026-10-20. Found by the day sweep `sweep-tasks-sweep` (scratch Hub :8170).
**Source:** drive
**Theme:** Dependencies
**Ready:** yes
**Tier:** 0

```
X -> Y -> Z, all hand-made (POST /tasks/{id}/dependencies); PATCH Y {"status": "rejected"} -> 200; Z dependency_state "gated_on_rejected"
PATCH Z {"status": "in_progress"} -> 409 dependency_unmet: "... 'bulk 006 ...' (task-6668d193dfa1) was rejected and will not become approved on its own -- reopen it, or edit the document that declared this dependency."
```

`DependencyRefusal.detail` (`hub/hub/dependency_gate.py:62-66`) predates hand-authored `depends_on`: for a task with no `spec_document_id` the dependency was declared in the drawer's "Depends on" (or at creation), and the Dependencies view itself says "Hand-made tasks belong to no document". **Expected:** for a task with no document, the remedy reads "reopen it, or remove the dependency in this task's Depends on". **Test:** `hub/tests/test_dependency_gate.py`: a documentless task gated on a rejected prerequisite gets a message without "document".

## F830 (D) -- the `steps_skipped` approval gap tells the operator, on screen, to make raw HTTP calls, and the recipe it gives leaves out re-proposing

**Status:** open 2026-10-20. Found by the day sweep `sweep-spec-sweep` (scratch Hub :8180, `scripts/drive/s1020_s_ui.py`), seen in Chromium.
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

```
proposed change written in one PUT -> Approve (Chromium) -> approval-warnings:
  "steps_skipped — the document is at step 'intake'; this project's journey (no size, so every step) goes on to
   threat-model, ... delivery, which it never reached. If it already holds what those steps produce, record that:
   send it back first, POST /api/v1/projects/proj-e5b03b955646/project/documents/phase?path=...&to=exploring,
   then POST /api/v1/projects/.../documents/journey?path=... {"step": "delivery"} (the step control on its phase bar)"
-> Approve anyway -> the same text is kept on the document as "Approved over these gaps"
```

The message is built once for agents and the operator alike (`hub/hub/spec_service.py:1874-1892`, F574/F730/F752). On the app's approval card it reads as an API recipe, although the phase bar has the controls. It also stops one step short: after "send it back" and the step move, the document is `exploring` again and has to be proposed again before Approve shows. **Expected:** the finding carries the steps as data (or a second operator-facing sentence) and the card names the controls: "Send back, choose the step on the journey bar, Propose, then Approve". The agent-facing text keeps the routes and adds the propose step. **Test:** `test_the_journey_steps_a_document_never_reached_are_a_gap_naming_them` extended: a proposed document's remedy names propose after the journey move; plus a UI test that the approval card renders no `POST /api/` text.

**Extended 2026-10-22** (day sweep `sweep-spec-sweep`, Chromium, scratch Hub :8121): the recipe outlives the approval. An approved document approved over `steps_skipped` keeps an "Approved over these gaps:" block in its header (`useSpecPhaseControls.tsx:719-725`, `approval_warnings_overridden`). That block still says "send it back first, POST /api/v1/projects/proj-94e2f2f27779/project/documents/phase?path=…&to=exploring, then POST …/journey …". This is advice to un-approve a document the operator has already decided on, given as two raw HTTP calls. At 900 px wide the block, with the two other gaps, pushes the document's first line to y≈690 of 940 (`testbed/ui-judge/s1022-spec/120548/narrow_dark.png`). The header rebuild was meant to undo exactly that push (`SpecDocumentHeader`'s docstring: "pushed the document 380px down"). **Expected, in addition:** the overridden record shows each gap's code and its one-line message without the remedy, folded behind a count ("Approved over 3 gaps").

**Re-seen 2026-10-22** (docs-rework drive, demo Hub :8012, Haiku planner): the Approve anyway dialog showed the same `POST /api/v1/projects/…/project/documents/journey?path=…` recipe to the operator, for a document an agent wrote whole (F1034). Nothing new beyond F830's own text.

## F831 (D) -- the note answering a cannot-satisfy report runs the operator's reason into the next sentence with no full stop

**Status:** open 2026-10-20. Found by the day sweep `sweep-spec-sweep` (scratch Hub :8180, real Haiku reporter `builder`).
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

```
POST .../documents/spec/changes/slug-speed/spec.json/amendments/amd-6ab5b83b9196/respond
  {"response": "amend", "reason": "a typo for microseconds", "change": {"then": "it returns in under 100 microseconds"}}
inbound_queue_entries (builder): "... how_to_check: time it with time.perf_counter_ns. Their reason: a typo for
  microseconds The task is unblocked; continue the work against the criterion as it now reads."
```

`hub/hub/spec_amendments.py:845` appends `" Their reason: {reason}"`, and the next sentence follows directly. An operator's reason rarely ends in a full stop, so this happens every time. **Expected:** the reason is closed with a full stop when it lacks terminal punctuation (or is quoted). **Test:** next to the F700 respond tests: an amend with a reason without a full stop; assert the delivered note contains `"microseconds. The task"`.

## F834 (D) -- a drift candidate re-raised after "Code corrected" or "Spec updated" looks like new drift: nothing on the row says it was answered, or when

**Status:** open 2026-10-20. Found by the day sweep `sweep-evidence-sweep` (scratch Hub :8190, `scripts/drive/s1020_v_p2.py` + `s1020_v_ui.py`, Chromium). **Re-verified 2026-10-22, still open** (:8124, Chromium, `scripts/drive/s1022_ev_ui2.py`): after "No change" on drift-093f33b00c3e, a later watched commit re-raised drift-dadfd49e8675 for the same piece, and its row reads only "FR-2 · verified by count() printed 3 (builder) · todo/items.py: e7bf480 → c5ce58e" with the three answers, nothing about the earlier answer.
**Source:** drive
**Theme:** Requirements & evidence
**Ready:** yes
**Tier:** 0

```
three candidates on FR-3 answered: no_change_required, implementation_corrected, specification_updated (all 200)
POST /spec/drift/detect (no new commit) -> {"raised": ["drift-f58c2a17b807", "drift-e89f2f95fdd8"]}
  -- the two "corrected"/"updated" ones again, by design (requirement_evidence.resolve_drift docstring, D8/F730)
Drift panel: "Drifting: 3 to answer -- say which one was wrong", each re-raised row reads exactly like a first one:
  "FR-3 · verified by total() == 6, watched by locator (operator)  todo/total.py: 723004c -> a870e62  [Spec updated][Code corrected][No change]"
```

Asking again is right: the code was not put back and the requirement was not reworded. But the operator who answered a minute ago sees the same row return with no hint why, which reads as "my answer was lost". The reason sits only in the buttons' hover titles. **Expected:** the re-raised row says it was answered before, e.g. "You said Code corrected at 12:31; todo/total.py still differs." `GET /spec/drift` can carry the previous resolved candidate's answer for the same piece and fingerprint. **Test:** in the drift tests: a candidate raised again after `implementation_corrected` carries `previously` (resolution, time). A UI test renders it on the row.

## F837 (D) -- every `task_created` row in the Activity feed reads "assigned to unassigned", even for a task created with an assignee

**Status:** open 2026-10-21. Found by the day sweep `sweep-tasks-sweep` (scratch Hub :8150, Chromium).
**Source:** drive
**Theme:** Logs, events & SSE
**Ready:** yes
**Tier:** 0

```
POST /tasks {"title": "B: discounted label", "assignee": "beta", ...} -> 201, assignee "beta"
Activity feed: task_created "B: discounted label" assigned to unassigned
event_logs task_created data: {"id": "task-bf20bddeb689", "title": "B: discounted label"}   (agent column = beta)
```

`tasks.py:892-899` broadcasts and persists `{"id", "title"}` only (the assignee goes into the event's `agent` column), and `eventSummary.ts:14` reads `data.assignee ?? 'unassigned'`. So the summary is wrong for every assigned task. **Expected:** the payload carries `assignee` (null when none) and the row reads "assigned to beta". **Test:** a hub test that the persisted `task_created` payload has `assignee`; `eventSummary.test.ts` already covers the string.

## F839 (D) -- the F829 fix still refetches the deleted document: the delete's own `spec_updated` broadcast re-invalidates every spec query family, so seven GETs of the dead path 404 after the 200

**Status:** open 2026-10-21. Partial regression of F829's stated fix ("no GET of the dead path after the 200"); nothing reaches the screen (the page has already moved to the home document). Found by the day sweep `sweep-spec-sweep` (scratch Hub :8150, `scripts/drive/s1021_s_ui.py`, Chromium, live SSE).
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

```
Chromium, two documents (ui-delete2, stays): Delete document on ui-delete2 -> 200, page moves to stays, note shown
responses after the DELETE's 200, all 404, all for spec/changes/ui-delete2/spec.json:
  GET spec/coverage?document=...   GET documents/.../proposals   GET documents/.../proposals?status=resolved
  GET documents/.../rigor-history  GET spec/drift?state=candidate&document=...   GET spec/requirements?document=...   GET spec?path=...
7 console errors "Failed to load resource: 404". Same seven with one document (the last) deleted.
```

`useDeleteSpecDocument` (`hub/ui/src/api/spec.ts:1355-1379`) takes care to skip the dead path's keys, but the Hub's delete then announces `spec_updated {path: <deleted>}` (`hub/hub/api/v1/spec.py:3685`), and `useSpecEvents` (`hub/ui/src/api/spec.ts:589-611`) invalidates `specCoverage`, `specProposals`, `specRigorHistory`, `specRequirements`, `specDrift` wholesale and `['spec', <deleted path>]` by name while the panel's observers are still mounted. The F829 test stubbed `fetch` with no SSE, so it could not see this. **Expected:** the delete broadcasts something the client can tell apart (e.g. `spec_updated {path, deleted: true}`), and `useSpecEvents` removes the dead path's queries instead of invalidating them. **Test:** in `specDeleteApi.test.tsx`, deliver the `spec_updated` event the route actually emits after the 200 and assert no request for the deleted path follows; fails today.

## F840 (D) -- deleting the last document shows "No specification yet" with no word of what was deleted: `SpecDeletedNote` lives inside the document panel, which the empty state replaces

**Status:** open 2026-10-21. Follow-up to F829 (its "Not done" names only the conversation host). Found by the day sweep `sweep-spec-sweep` (scratch Hub :8150, `scripts/drive/s1021_s_ui.py`, Chromium; screenshot `testbed/ui-judge/s1021-spec/094953/02_after_delete.png`).
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

```
the project's only remaining document spec/changes/ui-delete (approved, 2 tasks, one with commit 11c9d17) -> Delete document -> 200, kept_work names the branch
page after: "No specification yet -- Open a conversation and ask an agent to write one ..."; spec-deleted-note absent
```

`SpecPage` returns the empty state before it mounts `SpecDocumentPanel` (`hub/ui/src/components/spec/SpecPage.tsx:85-95`), and the note is rendered only by the panel (`SpecDocumentPanel.tsx:256`). The store holds the notice, but no mounted component reads it. **Expected:** the empty state (and the "Everything here is archived" state at `SpecPage.tsx:101`) shows `SpecDeletedNote` above it. **Test:** a `SpecPage` test with an empty inventory and a notice in `specDeletionStore` asserts the note renders; fails today.

## F843 (D) -- the vault reports doors refuse without naming the way out: "The vault reports job is disabled." / "... has no runner." on the card, and an agent told a pending report "is being looked into" while the job is off

**Status:** open 2026-10-21. Found by the day sweep `sweep-vault-sweep` (scratch Hub :8151; Chromium for the card, a real Haiku turn's transcript for the agent's sentence).
**Extended 2026-10-22** (day sweep `sweep-vault-sweep`, Chromium): the spec page's vault popover -> "Check against the vault again" with the spec-vault-check job off toasts "Could not start the check -- The spec vault check job is disabled." (`hub/hub/vault_spec_check.py:267`), the same sentence without a way out as the reports doors (`vault_reports.py:165`). Fix both in the distillation door's form ("... Turn it on under Project settings -> Manager.").
**Source:** drive
**Theme:** Knowledge vault
**Ready:** yes
**Tier:** 0

```
POST .../vault/reports/rpt-dcaea150ac59/review   (job off)          -> 409 "The vault reports job is disabled."
POST .../vault/reports/rpt-dcaea150ac59/review   (on, no runner)    -> 409 "The vault reports job has no runner."
Vault -> Reports -> Look into it (on, no runner) -> card: "The vault reports job has no runner."      (screenshot testbed/ui-judge/s1021-vault/095732)
twin doors, same state: POST .../vault/sources/<id>/distil -> 409 "The vault distillation job has no runner. Choose one on the Manager page."
agent (job off): vault_report on an entry with a pending report -> "Entry src-1cc5d3bb5b78 already has report rpt-dcaea150ac59 (pending); it is being looked into."
```

`vault_reports.prepare` (`hub/hub/vault_reports.py:159-161`) words its refusals bare. The distillation doors add "Enable it on the Manager page." / "Choose one on the Manager page." (`hub/hub/distillation.py:225,229`). `vault_spec_check.prepare` has the same bare pair (`hub/hub/vault_spec_check.py:267-269`; read in code, not driven today). `vault.add_report`'s duplicate refusal (`hub/hub/vault.py:1652-1655`) says "it is being looked into" whatever the job's state; with the job off nothing will look into it, and the agent cannot tell. **Expected:** both prepare functions end with the Manager page's way out, as distillation does. The duplicate refusal says the report is pending and, when the job is off or has no runner, that it waits for the operator. **Tests:** `hub/tests/test_vault_reports.py`: the job-off and no-runner 409 details contain "Manager page"; the same file: a duplicate filed with the job off does not say "being looked into". Both fail today.

## F847 (D) -- after a failed Checkpoint now and a reload, the banner says "Nothing has been written yet" and nothing on the conversation says the attempt failed

**Status:** open 2026-10-21. Found by the day sweep `sweep-checkpoints-sweep` (scratch Hub :8153, Chromium against the served bundle, `scripts/drive/s1021_c_ui.py failed|reload`). The residue of F817's fix ("so the banner still offers Checkpoint now and can show the failure").
**Source:** drive
**Theme:** Checkpoints
**Ready:** yes
**Tier:** 0

Checkpoint runner pointed at a Codex runner (undrivable here). On alpha's `conv-29d1e4cd542c` (warning `due`), **Checkpoint now** -> `POST .../checkpoint` 201 `ckpt-bdb1be928049` `status: unwritten`, `generation_error: "exited 1: Reading additional input from stdin..."`; the toast "Checkpoint failed: exited 1: …" showed and the warning stayed `due` (F817 holds). After a reload: the banner reads "This conversation has reached its checkpoint threshold. Nothing has been written yet — checkpoint now, or dismiss this and keep working." with no mention of the failure (`testbed/ui-judge/s1021-c-reload/102759/failed-reloaded.png`). The failure is only in the Checkpoints sheet, as an `unwritten` entry with its error. An operator who comes back presses Checkpoint now again, not knowing it fails the same way until the runner changes.

Cause: F540's failure line (`hub/ui/src/components/agents/AgentOutputPanel.tsx:649-654`) counts only a newest checkpoint with `trigger === 'context_pressure'`; an `operator` one with `unwritten`/`failed` is ignored.

**Expected:** while the warning stands and the newest checkpoint is an `unwritten`/`failed` operator press, the banner says the last attempt failed and why ("The last checkpoint attempt failed: <error>. Check the checkpoint runner in Settings, or dismiss this."). **Test:** `hub/ui/src/__tests__/agentHandoff.test.tsx`: a conversation with `checkpoint_warning: 'due'` whose newest checkpoint is `{trigger: 'operator', status: 'unwritten', generation_error: 'x'}` renders the failure text; fails today. Seam: Checkpoints (banner) x Runners.

## F848 (D) -- under `automatic` checkpointing with the token budget spent, the threshold banner reads exactly as `offered` does: nothing says the automatic checkpoint was held by the budget

**Status:** open 2026-10-21. Found by the day sweep `sweep-checkpoints-sweep` (scratch Hub :8153, Chromium against the served bundle, `scripts/drive/s1021_c_ui.py autospent`).
**Source:** drive
**Theme:** Accounting & allowance
**Ready:** yes
**Tier:** 0

`PUT /settings {"checkpoint_mode": "automatic"}` (threshold 8,000 tokens, Haiku checkpoint runner). With the budget open, a gamma turn crossed it and the Hub wrote `ckpt-e5494f68d13e` (`context_pressure`, ready, probe passed) and cut over: automatic works. Then `PATCH /accounting/budget {"token_budget": 1000}` (exhausted) and a fresh gamma operator turn (`run-cdcdf958d787`, "42"): no checkpoint, `checkpoint_warning: due` (F240 design D3a holds: warn, do not spend). On screen: "This conversation has reached its checkpoint threshold. Nothing has been written yet — checkpoint now, or dismiss this and keep working." (`testbed/ui-judge/s1021-c-autospent/103426/autospent-before.png`), word for word the `offered` banner. The operator chose automatic, and nothing says why it did not happen. **Checkpoint now** then wrote `ckpt-3083d2f71cf9` (operator, ready) on the spent budget, by design (`worker.py:327`, "the operator's path is never gated"), but the banner does not say that pressing it spends past the budget either.

Cause: the warn path (`hub/hub/checkpoint_trigger.py:376-404`) broadcasts `checkpoint_due` with no reason and sets the same `due` as `offered`; the banner (`AgentOutputPanel.tsx:767`) has one text.

**Expected:** when the warning was raised under `automatic` because the budget is spent, the banner says so: "Automatic checkpointing is paused: the project's token budget is spent. Checkpoint now runs as your own act and is counted." (a `reason` on `checkpoint_due`, or the banner reading the budget state it already has for the budget notice). **Test:** `hub/tests/test_checkpoint_trigger*.py`: automatic policy, budget exhausted, a reading over the threshold -> the `checkpoint_due` payload carries a budget reason; fails today. Seam: Checkpoints x Accounting & allowance.

## F853 (D) -- after a criterion-only change, the piece labels still say "earlier wording" while the story, the decision and the refusal say the criteria changed

**Status:** open 2026-10-21. Found by the day sweep `sweep-evidence-sweep` (scratch Hub :8155, Chromium: `scripts/drive/s1021_e_f833b.py`, `s1021_e_ui.py`). Residue of F833 (whose fix holds: the revision reads `change: criteria`, the story says "You changed its acceptance criteria ... The statement is unchanged", and the 409 says "recorded before the acceptance criteria of FR-3 changed (its statement is unchanged)").
**Source:** drive
**Theme:** Requirements & evidence
**Ready:** yes
**Tier:** 0

```
reopen, change only c-total.then, re-approve -> GET /spec/requirements/FR-3 revisions [created, {classification: reworded, change: criteria}]
FR-3 story (Chromium): "You changed its acceptance criteria ... Evidence  1 accepted  1 for an earlier wording ... total() printed 6  rejected · earlier wording"
Evidence view row: "total() printed 6  rejected · earlier wording ... Rejected by you — earlier criteria"
```

One row says "earlier wording" and "earlier criteria" side by side. The labels come from `EvidenceBrowser.tsx:118` ("· earlier wording", and its title at `:115`) and `RequirementStory.tsx:262` ("for an earlier wording"), which read only `for_current_wording`. **Expected:** where the newest revision's `change` is `criteria`, the label reads "earlier criteria" (or a neutral "earlier version", as the story's own sentence puts it), in the chip, the row and the count. **Test:** `requirementStory.test.tsx` and the EvidenceBrowser test: a requirement whose last revision is `change: criteria` renders no "earlier wording".

## F854 (D) -- the coverage bar shows "<sha> on" with nothing after it when a piece's line of work is unknown

**Status:** open 2026-10-21. Found by the day sweep `sweep-evidence-sweep` (scratch Hub :8155, Chromium: `scripts/drive/s1021_e_ui.py`, shot `03_bar_pieces_FR-3.png`).
**Source:** drive
**Theme:** Requirements & evidence
**Ready:** yes
**Tier:** 0

```
POST /spec/evidence {identifier: FR-3, commit: dc83446 (master's tip), locator: todo/total.py} -> ev-aae23fc840ce accepted
evidence_footprints.branch = ''   (master, builder's task branch and its agent branch all point at dc83446)
coverage bar, Evidence (2) on FR-3: "total() printed 6 as an int — operator · todo/total.py · dc83446d5508 on · accepted by operator"
```

`line_of_work` (`hub/hub/requirement_evidence.py:1049-1069`) answers `""` when several branches point at the commit, and says so in its docstring: "`""` is the only spelling of 'no known line of work'". `EvidencePieces.tsx:69` falls back with `?? 'no branch'`, which does not catch an empty string. A fresh task checkout at master's tip is enough to cause it, so it is common. **Expected:** the empty branch renders as no branch: drop " on ..." or say "on no known branch". Secondary: when the main branch is one of several tips, `line_of_work` could prefer it, since the commit is on the main line. **Test:** the EvidencePieces test: a footprint with `branch: ''` renders no trailing " on".

## F855 (D) -- the document's health line counts stale, drifting, awaiting-review and changed-unreviewed requirements as "in progress"

**Status:** open 2026-10-21. Found by the day sweep `sweep-evidence-sweep` (scratch Hub :8155, Chromium on the ui-finesse bundle: `scripts/drive/s1021_e_ui.py`, `testbed/probe_v1021.py`). Also 2026-10-22 (:8114, Chromium): a `not_started` requirement is counted too -- coverage FR-1 verified, FR-2 in_progress, FR-3 not_started read "1/3 verified · 2 in progress". Also 2026-10-22 (:8124, Chromium): FR-1 not_started, FR-2 drifting, FR-3 awaiting review read "0/3 verified · 3 in progress".
**Source:** drive
**Theme:** Requirements & evidence
**Ready:** yes
**Tier:** 0

```
coverage: FR-1 stale (its only evidence is for an earlier wording, rejected), FR-2 verified, FR-3 drifting
health line (Chromium): "1/3 verified · 2 in progress | 1 drifted | 0/3 tasks decided"
menu: "FR-1 Stale  FR-2 Verified on master  FR-3 Drifting on master"
```

`SpecHealthLine.tsx:66-68` computes `working = coverage.length - verified - rejected` and labels it "in progress". Nobody is working on FR-1 (it needs new evidence) or FR-3 (it needs a drift answer), and the line never says "stale" anywhere, so the operator learns it only by opening the menu. **Expected:** the label counts states that need the operator apart from work underway, e.g. "1/3 verified · 1 stale · 1 drifting", or "2 need you" for stale / drifting / evidence awaiting review / changed-unreviewed, keeping "in progress" for `in_progress` and `not_started`. **Test:** the SpecHealthLine test: coverage [verified, stale, drifting] renders no "2 in progress".

## F857 (D) -- a Copilot startup timeout names its request twice: "Copilot did not answer `initialize` within 30 s during initialize"

**Status:** open 2026-10-21. Found by the day sweep `sweep-traces-sweep` (scratch Hub :8156 with a never-answering native `copilot.exe` stand-in first on PATH, `testbed/scratch/s1021_copilot_hang/hang.cs`; `scripts/drive/s1021_tr_traces.py f789`, `s1021_tr_traces_ui.py all`).
**Source:** drive
**Theme:** Runs
**Ready:** yes
**Tier:** 0

The F789 fix holds live (see the log). Its message reads "Copilot did not answer `initialize` within 30 s during initialize" on each of the three runs (`runs.error`), on their `run_failed` events, on the trace root's `status_message`, and in the conversation under the "not delivered" entry ("Last attempt failed: ..."). `ACPProcess.request` (`hub/hub/copilot_acp.py:1975`) puts the method in the message *and* passes `method=`, and the `AppServerError` constructor appends `" during {method}"` (`hub/hub/codex_appserver.py:721-722`). **Expected:** the method named once: "Copilot did not answer `initialize` within 30 s". Either drop it from the message, or skip the suffix when the message already contains the method. **Test:** the existing `test_a_copilot_startup_timeout_names_itself.py` asserts `str(exc).count("initialize") == 1`.

## F858 (D) -- a Copilot launchability probe that fails with a bare exception logs "failed: " with nothing after it, and when no verdict exists yet the error is discarded

**Status:** open 2026-10-21. Found by the day sweep `sweep-traces-sweep` (scratch Hub :8156, the never-answering stand-in of F857).
**Source:** drive
**Theme:** Runners & models
**Ready:** yes
**Tier:** 0

```
Hub log (twice): WARNI [hub.copilot_probe] Copilot launchability probe of ...\s1021_copilot_hang\copilot.exe failed:
GET /projects/{p}/runners/launchability -> runner-b53cbdb612a1: runnable true, reason null, "verdict_pending": true
  (after both probes ran, and after three runs had failed on `initialize`)
```

`ProbeCache._refresh` (`hub/hub/copilot_probe.py:315-320`) logs `"%s", exc`, which is '' for a bare `TimeoutError` (F789's shape, on the probe's own path). It stores `probe_error = str(exc) or type(exc).__name__` only `if previous is not None`, so on a first probe nothing anywhere says why the verdict is still pending. Not gating is deliberate (R3: one slow spawn must not make every Copilot agent unlaunchable). **Expected:** the log line uses `str(exc) or type(exc).__name__`, and a first probe's failure is kept as well, for example on a pending entry, so that `launchability` can carry `probe_error` beside `verdict_pending`. **Test:** a `probe_copilot` patched to raise `asyncio.TimeoutError()` on a fresh cache: the warning text names `TimeoutError`, and the next `launchability` answer carries it.

## F859 (D) -- a message whose every delivery attempt failed before any output has no trace button: the conversation says "Last attempt failed" but cannot open the attempt's trace

**Status:** open 2026-10-21. Found by the day sweep `sweep-traces-sweep` (scratch Hub :8156, Chromium on the served bundle, `scripts/drive/s1021_tr_traces_ui.py all`, conversation conv-3bd380095252).
**Source:** drive
**Theme:** Traces
**Ready:** yes
**Tier:** 0

The Copilot message "Say hello." failed three times on `initialize` (run-ca958336bc27, run-2af252a61d67, run-5f2ffc334eea; entry `withdrawn`, "delivery failed 3 times; the Hub stopped retrying", `delivered_in_run_id` = the last run). The conversation renders "NOT DELIVERED · delivery failed 3 times ... Last attempt failed: Copilot did not answer `initialize` ..." and no `turn-trace-*` button (count 0), because no turn rendered. All three traces exist (`GET /traces?run_id=...`, status `error`), and Settings -> Traces lists them, but only by time and agent. **Expected:** the not-delivered entry links the last attempt's trace (`delivered_in_run_id`), or each attempt's, through the same `TraceDrawer` the turn button opens. **Test:** an `AgentTimeline` test: an abandoned entry with `delivered_in_run_id` renders a trace control that opens `/traces/by-run/<that run>`.

## F868 (D) -- an ended or archived loop reports a `stall_reason` while every agent is busy ("alpha is already running a turn"), and the Loops panel prints any stall reason in amber, ended or not

**Status:** open 2026-10-21. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8159). API-observed; the panel line was not caught on screen in the moment (labelled).
**Source:** drive
**Theme:** Jobs & loops
**Ready:** yes
**Tier:** 0

Repro (`scripts/drive/s1021_l_loops.py adopt|stop`, while alpha and beta were both running F864's builder turns): `GET /loops/{A}` for the **archived** loop A -> `ending_state: "stopped"`, `archived_at` set, `stall_reason: "alpha is already running a turn"`. `PATCH /jobs/{B} {"stop_reason": ...}` -> loop B `ending_state: "stopped"`, and `GET /loops/{B}` -> `stall_reason: "alpha is already running a turn"`. Both went back to `null` once beta was free. The list route computes `decide_firing` and the busy guard for every loop in the batch, ended ones included (`hub/hub/api/v1/jobs.py:498-515`), and `LoopsIndexTab` renders `loop.stall_reason` with no check of `ending_state` (`hub/ui/src/components/spec/LoopsIndexTab.tsx:237-246`). The jobs card is not affected: it checks `finished` first (`hub/ui/src/components/jobs/JobsView.tsx:270-276`).

Expected: an ended loop has no stall reason (its state is the ending, with its `stop_reason`), and the panel shows nothing amber for it. **Test:** in the loops route tests, a stopped loop whose agent has a running turn reads `stall_reason: null`. Seam: Jobs & loops (list route x the busy guard).

## F913 (D) -- Needs you reads "now ago" for a question asked under 45 seconds ago

**Status:** open 2026-10-22. Found by the day sweep `sweep-questions-sweep` (Chromium, `testbed/ui-judge/s1022-questions/094012/needs_you.png`: "alpha is waiting  now ago").
**Source:** drive
**Theme:** Questions
**Ready:** yes
**Tier:** 0

`OverviewView.tsx:207` renders `{formatAgo(need.at, now)} ago`; `formatAgo` (`hub/ui/src/lib/format.ts:84`) returns `now` under 45 s and a calendar day (`formatDay`) past 60 days, so a row reads "now ago" or "Oct 3 ago". **Expected:** "just now" / "3m ago" / "Oct 3" (e.g. `formatAgoLong`, or append " ago" only to a relative value). **Test:** the OverviewView test: a need created 10 s before `now` renders no "now ago". Seam: Overview.

**Extended 2026-10-22** (day sweep `sweep-loops-sweep`, Chromium, `scripts/drive/s1022_lp_ui.py jobs2`): the Jobs tab has the same three: a flow fired seconds ago reads "Ran now ago" (`JobsView.tsx:285`), the Archived list "archived now ago" (`JobsView.tsx:425`), and its details' Recent runs "in_progress manual now ago" (`JobDetails.tsx:103`). One fix in `formatAgo`'s callers covers all four.


## F915 (D) -- the Dependencies view says dependencies come only from spec documents, and that a hand-made task's are "set from its task story"; the only control is the drawer's Details view

**Status:** open 2026-10-22. Found by the day sweep `sweep-tasks-sweep` (scratch Hub :8114, Chromium, `scripts/drive/s1022_tk_ui.py deps` and `drawer H3`).
**Source:** drive
**Theme:** Dependencies
**Ready:** yes
**Tier:** 0

```
Dependencies view banner        : "Dependencies come from each spec document. To change one, edit the document that declares it."
"Made by hand" group, 5 tasks   : "· no document declares these; set them from the task"  (title: "A hand-made task's dependencies are set from its task story.")
drawer (H3), Story view         : no dependency control
drawer (H3), Details view       : "Depends on  H2: after H1 ... Add vat() ... [Choose a task...] Add"   <- the picker (F571)
POST /tasks/<H3>/dependencies {"depends_on": <t-tax, a document task>} -> 201 "added"; the list then shows "Add vat() ... unblocks H3"
```

The banner sits directly above a "Made by hand" group that no document declares, and the hint sends the operator to the Story view, where there is nothing to press. `DependencyListView.tsx:64` (banner) and `:78` (hint). Related: F827 (open) is the same wrong pointer in the rejected-prerequisite refusal. **Expected:** the banner says a document's tasks take their order from the document, and that any task's prerequisites can be added in its drawer under Details -> Depends on; the hint says "from the task's Details". **Test:** a `DependencyListView` vitest asserting the hand-made hint names Details, not the story. Seam: Dependencies x Tasks (drawer).

## F917 (D) -- `POST /tasks/{id}/integrations/retry` on a skip the Hub itself marks not retryable answers 200 and records another identical "Not merged" attempt

**Status:** open 2026-10-22. Found by the day sweep `sweep-tasks-sweep` (scratch Hub :8114, `scripts/drive/s1022_tk_drive.py skip`).
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** yes
**Tier:** 0

```
PATCH N pending -> ... -> approved (no run, no evidence)
  latest_integration: {"outcome": "skipped", "reason": "no accepted evidence names a commit, so there is nothing to merge", "retryable": false}
POST /tasks/<N>/integrations/retry -> 200, integrations: [tint-7c2e90f28e1a skipped retryable false, tint-4afd34796d04 skipped retryable false]  (same reason)
drawer Story: "Not merged just now ... nothing to merge" twice
```

The card and the drawer correctly offer no Retry (F905), so only an API caller reaches this, but the route (`hub/hub/api/v1/tasks.py:1414`) ignores the `is_retryable` verdict it publishes (`task_integration.py:124`) and writes a row plus a `task_integration_retried` event for an attempt that, by that function's own docstring, cannot change anything. **Expected:** 409 when the latest attempt is not retryable, its detail the reason and what does re-attempt it ("accepting evidence re-attempts by itself", "saving the main branch re-attempts"), and no row written. **Test:** `test_task_integration.py`: retry after a `nothing to merge` skip -> 409, integration count unchanged. Fails today. Seam: Worktrees & integration (API).

## F922 (D) -- Project settings -> Manager tells a vault job with no runner that "with none, the job uses each agent's runner", one row below "This job does nothing until a runner is chosen"

**Status:** open 2026-10-22. Found by the day sweep `sweep-vault-sweep` in Chromium (scratch Hub :8115, `scripts/drive/s1022_vt_ui.py manager`).
**Source:** drive
**Theme:** Manager jobs
**Ready:** yes
**Tier:** 0

```
Project settings -> Manager -> Spec vault check (no runner):
  Runner: "This job does nothing until a runner is chosen."   No runner
  Model:  "Choose a runner first: with none, the job uses each agent's runner, whose models are not known here."
GET .../manager/jobs -> spec-vault-check needs_runner: true
```

The Model row's description (`hub/ui/src/components/settings/ManagerSettings.tsx:123`) is the conversation-titles sentence for every job; the Runner row above it already branches on `job.needs_runner`. **Expected:** for a `needs_runner` job with no runner, "Choose a runner first." (the borrowing clause only for `conversation-titles`). **Test:** a `ManagerSettings` test: a `needs_runner: true` job with no runner does not render "each agent" in its Model row. Fails today. Seam: Manager screen.

## F923 (D) -- small legibility slips on the vault doors: the Hub says "Distil" where the button now reads "Extract facts", a resolution is named with a contradiction id, "2026-02-30" is told to use the format it already uses, whitespace-only text is accepted, and the spec health line calls a superseded or missing citation a contradiction

**Status:** open 2026-10-22. Found by the day sweep `sweep-vault-sweep` (scratch Hub :8115; Chromium for the reader, the library and the spec page).
**Source:** drive
**Theme:** Knowledge vault
**Ready:** yes
**Tier:** 0

```
reader, an unread PDF: "This PDF has not been read yet, so it has no text. Distil the source to read it."  -- the button beside it reads "Extract facts"
  (hub/hub/distillation.py:666, :668; also "Distil a source from the Vault tab later." hub/hub/api/v1/vault.py:309, printed by `agentweave vault add`)
library after Resolve: Decisions -> "Decision on ctr-1d805ef79ab2"   (hub/hub/vault.py:1377; the reader's own rule: an id is behind a copy button, never in a sentence)
POST .../vault/sources {"dated": "2026-02-30"} -> 400 "dated must be a day written YYYY-MM-DD, such as 2026-09-01, not '2026-02-30'."   (vault.py:868; shown verbatim in the Add dialog)
POST .../vault/sources {"name": "w", "type": "note", "content": "   \n  "} -> 201 (an empty entry in the library; the dialog blocks it, the route does not: vault.py:966 `if not content`)
Spec page, a change citing a superseded, a disputed and a missing fact: health line "3 vault conflicts" -> popover "Some requirements contradict facts in the vault."   (SpecHealthLine.tsx:157, :162)
```

**Expected:** the Hub's sentences name "Extract facts" (or "Extract again") as the button reads; a decision source is named from the claim that stands ("Decision: <claim, shortened>"); a well-formed but impossible day says "2026-02-30 is not a day"; `add_source` refuses text that is only whitespace ("A source needs some text."); the health line counts "vault warnings" and its popover says what they are ("cite facts the vault has superseded, disputes, or no longer holds"). **Tests:** `test_vault*.py`: whitespace content -> 400; `dated="2026-02-30"` -> message contains "not a day"; after a resolve the decision source's name contains no `ctr-`; `distillation.unread_note` contains "Extract facts". Fail today. Seam: vault doors' wording x the ui-finesse renames.

## F924 (D) -- an agent's vault report that restates an open contradiction is reviewed without it: the reports job sees only the reported entry, calls the other note "a different document not in the source", and refers it as a second question beside the contradiction

**Status:** open 2026-10-22. Found by the day sweep `sweep-vault-sweep` (scratch Hub :8115, a real Haiku turn: run-01860c3b2a91; `scripts/drive/s1022_vt_drive.py agent`).
**Source:** drive
**Theme:** Knowledge vault
**Ready:** yes
**Tier:** 1

```
vault: two open contradictions between "Export note A" (dated 2026-10-01) and "Export note B" (2026-10-15): file names, and export time
alpha: vault_report on src-8c4af451d427 (Export note B): "Export note B ... disagrees with Export note A ... Please clarify which export note is current."
vault-reports firing -> referred: "The report brings a claim about Export note A (a different document not in the source) and asks which note is current.
                                  The source does not address which export note is authoritative ..."
Vault -> Disagreements: 2 open cards; Vault -> Reports: 1 "Referred to you" card on the same question; resolving the contradiction leaves the report open (closed by hand)
```

The worker is given the one entry (`hub/hub/vault_reports.py`, the review prompt), not the open contradictions on that entry's facts, so it cannot answer "the vault already records this as contradiction ctr-1d805ef79ab2, note B presumed", and the operator answers one question twice. **Expected:** the review reads the reported entry's open contradictions; a report that restates one is answered by pointing at it and closes when that contradiction is resolved (or is shown on the contradiction card). Either way the operator decides once. **Test:** `test_vault_reports*.py`: a report on an entry whose fact is a side of an open contradiction -> the review prompt contains the contradiction id; resolving it closes the report. Fail today. Seam: vault reports x contradictions.

## F927 (D) -- the agent's Charter picker answers a refused binding with "Could not update charter binding." and keeps offering the charter it could not bind

**Status:** open 2026-10-22. Found by the day sweep `sweep-agents-sweep` (scratch Hub :8116, Chromium, `scripts/drive/s1022_ag_ui.py agent`; `testbed/ui-judge/s1022-ag-agent/104053/agent-stale-charter.png`).
**Source:** drive
**Theme:** Charters
**Ready:** yes
**Tier:** 0

beta's settings -> Charter open; Underwriter deleted elsewhere (`DELETE /charters/{id}` -> 204, another tab or an API caller). Picking Underwriter in "Charter for beta": `PATCH /agents/beta {"charter_id": ...}` -> 404 "Charter 'charter-…' not found"; the section shows only "Could not update charter binding." (`AgentSettingsControls.tsx` `CharterPicker`, which drops the Hub's `detail`), the select snaps back to Code Reviewer, and Underwriter is still in the list (the charters query is not refetched). The other refusal this route gives a picker, "Agent 'x' is archived and cannot hold a charter", would be swallowed the same way. Binding from the picker otherwise holds (Code Reviewer bound, read back). **Expected:** the picker shows the Hub's sentence (`readableApiError`, as `ChartersSection` does) and refetches the charters after a refusal. **Test:** CharterPicker test with the bind mutation rejecting `{detail: "Charter 'c' not found"}` -> that sentence is rendered; fails today. Seam: Agents (settings) x Charters.

## F930 (D) -- a job's name may be blank: the route stores "  " on create and "" on rename, and the Jobs list, its menu and the archive confirm then name nothing ("Archive ?")

**Status:** open 2026-10-22. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8117, profile lp1022, project `proj-042da656a1f4`; `scripts/drive/s1022_lp_drive.py jobs`, Chromium `s1022_lp_ui.py jobs2`).
**Source:** drive
**Theme:** Jobs & loops
**Ready:** yes
**Tier:** 0

Repro: `POST /projects/{p}/jobs {"name": "  ", "agent": "alpha", "message": "Reply OK.", "cron": "0 4 1 1 *", "enabled": false}` -> **201**, `"name": "  "`. `PATCH /jobs/{id} {"name": ""}` -> **200**, `"name": ""`. In Chromium the row has no title ("alpha·0 4 1 1 *Reply OK.Never run0 firedPaused Run now"), its menu button is labelled "More for " and its switch "Pause ", the archive confirm's title reads "Archive ?", and the Archived list shows rows that differ only by agent ("alpha · fired 0 times · archived 3m ago"). The New job form refuses a blank name ("Name is required", `JobForm.tsx:84`). The route, which is also `create_job`'s door for agents, does not. Charters refuse the same input (422, driven in `sweep-agents-sweep` today). **Expected:** `POST` and `PATCH /jobs` refuse a name that is empty after trimming, with a sentence ("a job needs a name"), and nothing is written. **Test:** `hub/tests/test_jobs*.py`: create with `"  "` -> 422 and no row; PATCH to `""` -> 422 and the name unchanged. Both fail today. Seam: Jobs & loops (route validation).

## F936 (D) -- Escape on a reach grant's host or folder field discards the entry but keeps the text, so the next "A host…" or "A folder…" opens prefilled with what was thrown away

**Status:** open 2026-10-22. Found by the day sweep `sweep-reach-sweep` (Chromium against the served bundle, scratch Hub :8118; `scripts/drive/s1022_rc_ui.py`).
**Source:** drive
**Theme:** Permissions & sandbox
**Ready:** yes
**Tier:** 0

Repro: on Project settings -> General -> Granted reach, choose Add -> A host…, type `escape-me.example`, and press Escape. Nothing is saved, which is right: `GET /settings` hosts stays `[]`, Escape closed only the field, and the URL was unchanged. Add -> A host… again: the field opens holding `escape-me.example`. `ReachGrantsChips.tsx`: the input's Escape handler and the Cancel button both call `setAdding(null)` and never `setDraft('')`. Only `submit()` clears the draft. The same leftover text would open in the *folder* field if that is chosen next, because one draft serves both. **Expected:** Escape and Cancel clear the draft. **Test:** `hub/ui/src/__tests__/reachGrantsHostDraft.test.tsx`: type, Escape, reopen -> the field is empty. This fails today. Seam: Keyboard & dialogs x Permissions & sandbox.

## F937 (D) -- the turn context's one-line vault index tells a call-mode (`aw-tool`) run to use `vault_map()` and `vault_read(entry_id)`, a call shape that run cannot make

**Status:** open 2026-10-22. Found by the day sweep `sweep-reach-sweep` (scratch Hub :8118, profile rc1022; beta's `.agentweave/context/beta.md` after `run-617f5746460c`).
**Source:** drive
**Theme:** Knowledge vault
**Ready:** yes
**Tier:** 0

Repro: a project with one vault source and agent beta with `hub_client: "cli"`. beta's context, line 29: "This project has a knowledge vault with 1 entry ...: `vault_map()` lists them and `vault_read(entry_id)` reads one." Its own tool list in the same file (lines 64-65) names them `aw-tool vault_map` and `aw-tool vault_read` with an arguments file. alpha (MCP) gets the same line, while its callable names are `mcp__agentweave__vault_map` / `mcp__agentweave__vault_read`. `render_turn_index` (`hub/hub/vault.py:1770`) takes no tool surface, unlike the tool list rendered beside it. **Expected:** the line names the tools the way the run's tool list does (prefix or `aw-tool`). **Test:** `render_turn_index(entries, <call-mode surface>)` contains `aw-tool vault_map`. This fails today. Seam: Agent environment x Knowledge vault.

## F941 (D) -- after a confirmed action removes or disables the control that opened it, keyboard focus falls to `<body>`: a runner deleted, instructions cleared, a project deleted

**Status:** open 2026-10-22. Found by the day sweep `sweep-projects-sweep` (Chromium, keyboard; `scripts/drive/s1022_pj_ui.py runners|instructions|dialogs`).
**Source:** drive
**Theme:** Keyboard & dialogs
**Ready:** yes
**Tier:** 0

Repro, with `document.activeElement` read after each step:
- (a) Runners: focus **Delete kb-haiku** and press it. The row goes and focus is `BODY`.
- (b) Instructions: empty the editor, press Save, and confirm **Clear instructions**. Stored content becomes `''` (correct) and focus is `BODY`. Save is now disabled because the draft is no longer dirty (`OtherSettings.tsx:52`).
- (c) pj-two's General: **Delete project…**, type the name, and press **Delete project**. The app moves to the remaining project's Overview and focus is `BODY`.

In all three, Cancel and Escape do return focus to the opener (held). Only the confirmed path loses it, because its opener is gone or disabled. For a keyboard user the next Tab starts again from the top of the page (rail, project switcher). **Expected:** focus lands on the nearest sensible control: (a) the next row's Edit button, or **New runner**; (b) the editor; (c) the new screen's main heading or first tab. **Test:** one per site in the existing dialog tests: after confirm, `document.activeElement` is not `document.body`. These fail today. Seam: Keyboard & dialogs.

**Widened 2026-10-23** (day sweep `sweep-projects-sweep`, Keyboard & dialogs row, :8118, profile kb1023): **F941 (b) still reproduces, and also on a plain Save:** Project instructions → empty the editor → Save → **Clear instructions** sends one PUT, and focus is `BODY`. A non-empty **Save** (Enter on it) does the same: focus is `BODY`, because Save disables once the draft is clean (`s1023_kb_instructions.py`). The clear-confirm itself held: focus on Cancel, Tab trapped, Escape back on Save with the draft kept.

## F943 (D) -- a Project settings link with an unknown or retired `section` (or none) lands on Quality, not General: the default is still the first entry of the old section order

**Status:** open 2026-10-22. Found by the day sweep `sweep-projects-sweep` (Chromium, scratch Hub :8119; `scripts/drive/s1022_pj_ui.py nav`).
**Source:** drive
**Theme:** Projects
**Ready:** yes
**Tier:** 0

Repro: open `/?project=<p>&tab=environment&section=bogus`, and then `...&section=permissions` (a page that no longer exists). Both rewrite the URL to `section=quality` and open Quality. `lib/navigation.ts:67` sets `DEFAULT_ENVIRONMENT_SECTION = ENVIRONMENT_SECTIONS[0]`, and the array (`:39-49`) still starts with `'quality'`, the old rail order. `ProjectSettingsScreen`'s own order starts with General (`settings`), the page every in-app link names (the gear, the rail's project menu, the Overview links: `App.tsx:624`, `Sidebar.tsx:314`). So only a typed or stale link reaches the default. Old bookmarks and the stale "Environment › Settings" references (F934) are exactly those links, and they land on the one section that cannot be configured (F939). Held: all nine sections by click and by deep link, each with its own URL, `project-settings-<id>` testid and heading. Browser Back returns to the previous section. Enter on a nav item opens it. **Expected:** an unknown or missing section falls back to `settings` (General). **Test:** `urlNavigation.test.ts`: `parseDestination('?project=p&tab=environment&section=bogus')` has `environmentSection: 'settings'`. This fails today. Seam: Projects x Keyboard & dialogs (navigation).


<!-- 2026-10-22 day sweep `sweep-spec-sweep` (Spec documents x Corpus & folding; scratch Hub :8121, profile sp1022, project proj-94e2f2f27779 `sp-main` under testbed/drive1022s, main branch `main`; three real Haiku 4.5 turns; drives scripts/drive/s1022_sp_{lib,drive,ui}.py, Chromium against the served bundle). Ranked by what each cost. -->

## F950 (D) -- the header's "Approved <date>" is the document's last update, not its approval: a rigor change moves it

**Status:** open 2026-10-22. Found by the day sweep `sweep-spec-sweep` (API, scratch Hub :8121).
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

Repro: `hdr-main` was approved at 10:57:09 UTC (`updated_at 2026-10-22T10:57:09.426707`). `POST /project/documents/spec/changes/hdr-main/spec.json/rigor {"rigor": "contract", "reason": "drive"}` moved `updated_at` to `11:05:32`. `SpecDocumentPanel.tsx:237` passes `record.updated_at` as `approvedAt`, so the next day the fact would read "Approved Oct 23" for a document approved on Oct 22. A proposal accepted or an amendment would move it the same way. `GET /project/spec?path=…` answers `approved_at: None`, so the app has no approval time to show. **Expected:** the Hub records the approval moment (the phase event or an `approved_at` column), and the fact reads it. **Test:** a panel test: `updated_at` differs from the approval event, and the fact shows the approval's day. Seam: Spec documents (header).

## F951 (D) -- three small labels in the rebuilt Spec list and header: an untracked change is listed under "Overview", exploring reads "draft" in the list but "Exploring" in the header, and the kind word "Change" beside the rigor chip reads as an action

**Status:** open 2026-10-22. Found by the day sweep `sweep-spec-sweep` (Chromium, scratch Hub :8121; screenshots under `testbed/ui-judge/s1022-spec/`).
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

(1) The file `spec/changes/untracked-one/spec.json` (a `change-spec` payload the Hub does not track yet) is listed under **Overview**, with no phase word. `SpecDocumentList.tsx:71` sends every kind outside `roadmap`/`change-spec`/`capability` to Overview, and an untracked node has no kind. It belongs under Changes, or in an "Untracked" group with its Adopt. (2) The list's `phaseWord` (`:161`) renders `exploring` as "draft", while the header's phase pill, the palette and every API say "Exploring". (3) The title row reads "hdr-main 115709 · Approved · Sketch rigor · Change", and at 900 px "Change  Place under…". The kind label (`SpecDocumentHeader.tsx:228`, `KIND_LABEL['change-spec'] = 'Change'`) is plain text beside two controls, so it reads as a verb ("change the rigor"). "Change spec" or "Change document" is unambiguous. **Test:** `SpecDocumentList.test.tsx`: an exploring row reads "exploring", and an untracked `spec/changes/` row is not in the Overview group. Seam: Spec documents (list/header labels).

## F956 (D) -- five small accounting labels: "1 turns could not be priced", "100% used" at 266%, an empty bordered list under "Nothing has merged yet", "266k" beside "265.8K", and a limit field that refuses 1.25 without saying one decimal

**Status:** open 2026-10-22. Found by the day sweep `sweep-checkpoints-sweep` (Chromium, :8122; `s1022_ck_ui.py overview|raise`).
**Source:** drive
**Theme:** Accounting & allowance
**Ready:** yes
**Tier:** 0

(1) Budgets: "API-equivalent; 1 turns could not be priced" (`BudgetsSettings.tsx:91`, no singular). (2) Budgets, Limit tile: "100K · **100% used**" with 265.8K used (`BudgetsSettings.tsx:107`, `Math.min(1, …)`). Over the limit should read "266% used" or "165.8K over". (3) Overview: under "Nothing has merged yet." an empty `<ul class="aw-ov-list">` draws a bordered sliver (`OverviewView.tsx:246-247`; the list renders when `finished` is empty). (4) The same 265,821 tokens read "265.8K" on Overview and Budgets but "266k tokens" on the Activity Ledger (`ProjectLedger.tsx:30`, its own formatter). (5) The After field (M tokens) refuses `1.25` with "Millions of tokens, like 40 or 12.5.", because the pattern (`/^\d+(\.\d)?$/`, `BudgetsSettings.tsx:217`) allows one decimal and the sentence does not say so. `0` and `abc` get the same sentence, which is fine. **Test:** `BudgetsSettings.test.tsx` for (1), (2), (5); `OverviewView.test.tsx` for (3).

## F1036 (D) -- the agent's own rule files are stale: `.claude/rules/cli.md` says five `cmd_*` and "ALL task modifications use `with lock`", `.claude/reference/architecture.md` says two runners are wired

**Status:** open 2026-10-22. Found while writing the contributing and architecture docs.
**Source:** code
**Theme:** Harness & CI
**Ready:** yes
**Tier:** 0

- `.claude/rules/cli.md:9` (and `CLAUDE.md`'s Architecture rules) say five `cmd_*` functions survive; six exist: status, doctor, stop, hub_start, reset, vault (`src/agentweave/cli.py:98-1678`). `vault` is the one the count missed.
- `.claude/rules/cli.md:20` says "ALL task modifications use `with lock("name"):`". Tasks are Hub-owned; the CLI has no task code. The only `with lock` users are `src/agentweave/jobs.py:211`, `:307`.
- `.claude/reference/architecture.md:82-83` says "Claude and Codex are the two wired to a real spawn path today"; Copilot is a third (`hub/hub/runner_adapters/copilot.py`).

These load into every session that edits the CLI, so they mislead the agent working on this repo, not the product's users. **Expected:** the three statements match the code. **Test:** none; a text edit.

## F1037 (D) -- `CHANGELOG.md` has no entry since `[1.1.0] - 2026-08-19` and no `[Unreleased]` section, over 3900 commits later

**Status:** open 2026-10-22. Found while rewriting the docs.
**Source:** code
**Theme:** Harness & CI
**Ready:** no
**Tier:** 0

`CHANGELOG.md:9` is the newest section; `git log --oneline v1.1.0..master | wc -l` is 3927. Both `pyproject.toml` files still say 1.1.0. The next release has nothing to draw its notes from. **Open question (why Ready: no):** the operator decides whether to keep a hand-written changelog (start an `[Unreleased]` section and keep it), generate one at release time from Tier-tagged commit subjects, or drop the file. **Test:** none until that is chosen.

## F975 (D) -- the one-loop-per-document refusal names only ids and gives no way out

**Status:** open 2026-10-23. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8111).
**Source:** drive
**Theme:** Jobs & loops
**Ready:** yes
**Tier:** 0

Repro: `POST /jobs` with `spec_document_id` claimed by a live loop → 409 `"document 'spdoc-ba5dc3e6cd7b' is already claimed by loop 'loop-7871385dea5f'"`. No document path or title, no job name, and nothing saying that stopping or archiving that loop frees the document (driven: loop B adopted A's pending task once A was archived, `loop_tasks_adopted`). **Expected:** the sentence names the document's path or title and the claiming job, and says "stop or archive it first, and the new loop adopts its unfinished tasks." **Test:** `hub/tests/test_jobs.py` beside the existing claimed-document test: the 409 detail contains the job name and "archive". Seam: Jobs & loops x Spec documents.

## F977 (D) -- a drained flow reads "Active · Waiting for its next firing · Next: Jan 1 2027" after its last approval; the stop is recorded only when something next fires it

**Status:** open 2026-10-23. Extends F655 (the same display fix, for `stop_when_queue_empties`). Found by the day sweep `sweep-loops-sweep` (scratch Hub :8112; Chromium).
**Source:** drive
**Theme:** Jobs & loops
**Ready:** yes
**Tier:** 0

Repro: the flow's last approval landed 11:07:04. `GET /loops/loop-8142093fc880` then still had `stop_reason: null, ending_state: null, queue {"approved": 2}`; the Jobs card read "2 of 2 tasks approved · Waiting for its next firing · Next: Jan 1 2027 · Active". Run now at 11:08:22 → 409 "loop queue is empty" and `loop_stopped` recorded. Cause: the fallback text at `hub/ui/src/components/jobs/JobsView.tsx:276`. **Expected:** "Finished: every task approved" (or "Stops at its next firing") once a `stop_when_queue_empties` loop's queue is all approved/rejected. **Test:** a JobsView test with a loop whose queue is all approved and `stop_when_queue_empties` set → it does not read "Waiting for its next firing". Seam: Jobs & loops x Flows.

## F978 (D) -- two labels in the review machinery: an operator's send-back reaches the author as "The reviewer sent it back", and a withdrawn review's reason carries the raw status `revision_needed`

**Status:** open 2026-10-23. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8112).
**Source:** drive
**Theme:** Flows & review
**Ready:** yes
**Tier:** 0

Repro: the operator's `PATCH /tasks/{id} {"status":"revision_needed","notes":…}` (`ttr-5d9bcf579404`, `actor_kind` operator) → beta's rework briefing reads "## Why it came back / The reviewer sent it back with these notes: > Operator: …". Cause: `hub/hub/scheduler.py:3172` `by or 'The reviewer'`, where `actor_agent` is None for the operator. Withdrawn review: "Withdrawn: task task-a1499b2857e6 was revision_needed, so there is no longer a review of it to start." reaches the conversation and the story verbatim (`hub/hub/run_task_binding.py:865`). **Expected:** "The operator sent it back…"; "was sent back for revision" (words, not the enum). **Test:** the revision-briefing test for an operator transition; a test that the withdrawal reason does not contain `revision_needed`. Seam: Flows & review x Tasks.

## F984 (D) -- propose, phase and rigor on a document whose file is invalid JSON say it "has not been written by the Hub", which is false

**Status:** open 2026-10-23. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8113).
**Source:** drive
**Theme:** Spec documents
**Ready:** yes
**Tier:** 0

Repro: truncate a change's `spec.json`. `POST …/propose` and `POST …/phase?to=proposed` → 422 `no_payload` "this document carries no payload to check; it has not been written by the Hub"; `POST …/rigor {"rigor":"contract"}` → 409 "the document carries no payload; it was not written by the Hub". `GET /project/spec` correctly answers 422 "holds no readable spec payload", and a content PUT with a valid payload repairs the file (200). Cause: `hub/hub/spec_service.py:1824-1828` and `hub/hub/spec_rigor.py:148-149` do not use `spec_documents.payload_problem` (`:238`, F702). **Expected:** `payload_problem`'s wording, naming the fix (save the document's content again). **Test:** the propose route on a truncated file → detail does not contain "not been written". Seam: Spec documents x Resilience.

## F985 (D) -- `POST /tasks/{id}/checks/run` answers 202 `{"run_id": null, "running": false}` with checks configured and starts nothing, without saying why

**Status:** open 2026-10-23. Found by the day sweep `sweep-loops-sweep` (scratch Hub :8113).
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** yes
**Tier:** 0

Repro: `PUT /settings` with checks `[{"name":"status","command":"git status --short","timeout_seconds":10}]`; on an `in_progress` task with no commit, `POST /tasks/{id}/checks/run` → 202 `run_id: null, running: false`; `GET …/checks` stays `{"configured": true, "runs": []}`. Cause: `hub/hub/project_checks.py:428-457` returns `None` for six different reasons and `hub/hub/api/v1/tasks.py:1410-1411` passes none on. **Expected:** a `reason` field ("no commit to check yet", …), shown where the press is. **Test:** `test_project_checks_run.py`: a task with no targets → the answer carries a reason. Seam: Tasks (checks) x Worktrees.

## F990 (D) -- the composer's `$` menu offers a skill's supporting files as skills

**Status:** open 2026-10-23. Found by the day sweep `sweep-questions-sweep` (Conversations row; :8117, `scripts/drive/s1023_cv_composer.py`).
**Source:** drive
**Theme:** Conversations & composer
**Ready:** yes
**Tier:** 0

Commit `.claude/skills/greet/{SKILL.md,reference.md,run.py}`, type `$` in the composer: options `['greet', 'greet/reference', 'greet/run.py']`.

Cause (verified): `hub/ui/src/lib/composerTriggerSources.ts:8-13` maps every path under `.claude/skills/` and collapses only `*/SKILL.md`; the skill branch (`:41-47`) never filters to `*/SKILL.md` (or a top-level `.md`).

**Expected:** only `greet`. **Test:** a `resolveTriggerResults` unit case with those three paths -> `[greet]`. Fails today. Seam: Composer `$skill` x workspace listing.

## F991 (D) -- an operator start naming an unknown `task_id` is refused with the agent-delegation sentence ("A delegation may only name a task in the project the delegating run belongs to")

**Status:** open 2026-10-23. Found by the day sweep `sweep-traces-sweep` (Runs row; scratch Hub :8118, profile rn1023, `proj-71764bd56b63`, `scripts/drive/s1023_rn_busy.py` and direct `e2e.py api`).
**Source:** drive
**Theme:** Runs
**Ready:** yes
**Tier:** 0

`POST /projects/{p}/agent/trigger {"agent":"alpha","message":"reply ack","task_id":"task-000000000000"}` -> 404 `"Task 'task-000000000000' does not exist in this project. A delegation may only name a task in the project the delegating run belongs to."` The operator is not a delegating run. The same probe with `review_task_id` already answers in the operator's words ("There is no task 'task-000000000000' in this project to review."): F731(5), 13f76d8, fixed only that branch.

Cause (verified): `trigger_agent` calls `resolve_task_for_project(session, body.task_id, project_id)` (`hub/hub/api/v1/agent_trigger.py:2298`), whose only sentence is the delegation one (`hub/hub/run_task_binding.py:143-146`). The `review_task_id` branch below it (`agent_trigger.py:2340-2346`) got its own operator sentence; the `task_id` branch did not.

**Expected:** e.g. "There is no task 'task-...' in this project. Check the id, or omit task_id to start alpha unbound." **Test:** beside `hub/tests/test_a_start_names_its_agents_own_task.py` (F731(5)'s test): an operator trigger with an unknown `task_id` -> 404 whose detail does not contain "delegation". Fails today. Seam: Runs (trigger) x Tasks (binding).

## F992 (D) -- Stop is keyed by agent, not by run, so a Stop arriving after its run ended stops the next turn the queue just started, in another conversation, and consumes that queued message

**Status:** open 2026-10-23. Found by the day sweep `sweep-traces-sweep` (Runs row; scratch Hub :8118, profile rn1023, `scripts/drive/s1023_rn_busy.py`).
**Source:** drive
**Theme:** Runs
**Ready:** yes
**Tier:** 0

alpha ran a 200 s sleep in `conv-d66b1d033c30` (`run-589082213417`). An operator message to alpha's other conversation `conv-d8cde5a74273` was queued ("agent is already running", `entry-9d1492e68dd1`). `POST /agent/alpha/stop` -> 200 for run-589082213417; it ended 11:58:43.70 and the queue started `run-e3613547662e` in conv-d8cde5a74273 at 11:58:44.22. A further `POST /agent/alpha/stop` ~3 s later -> 200 `"Stop signal sent to alpha (run run-e3613547662e)."`; that turn went `stopped` at 11:58:47.8 without replying, and the queued message is `delivered` into it (consumed). The caller cannot say which run it means. The UI mostly avoids it (`handleStop` holds `isStopping` until `run_stopped`; since F844 the other conversation's bar has no Stop), but a second tab, a stale bar or an API client hits it. Related to F15 (stop stops one run, the queue starts another) and the openspec leftover `an-agent-can-be-paused-and-keeps-its-input`, which are about pausing, not a Stop landing on the wrong turn.

Cause (verified): `stop_agent_run` (`hub/hub/api/v1/agent_trigger.py:2554-2610`) takes no run or conversation id and selects the newest `running` run for the agent (`:2568-2574`); the UI posts with no body (`hub/ui/src/components/agents/AgentOutputPanel.tsx:981`).

**Expected:** Stop accepts an optional `run_id` (the UI sends the run its bar shows) and answers 409 "run X already ended; <agent> is now running Y in <conversation>" when that run is no longer the running one. **Test:** in the stop tests (`hub/tests/test_agent_trigger.py`): run A finished, run B running for the same agent, `POST /agent/{a}/stop {"run_id": A}` -> 409 and B not terminated. Fails today (body ignored, B stopped). Seam: Runs (Stop) x Inbound queue drain x Conversations.

## F996 (D) -- after a killed turn, the Hub's automatic re-delivery reads in the Activity digest as a second operator turn with the same message, and its `run_triggered` says `initiator: "operator"`

**Status:** open 2026-10-23. Found by the day sweep `sweep-traces-sweep` (Logs row; :8119, profile ev1023, `scripts/drive/s1023_ev_sse_f907.py kill`, `scripts/drive/f907_ui.py`).
**Source:** drive
**Theme:** Logs, events & SSE
**Ready:** yes
**Tier:** 0

`run-b90d366a5373`'s claude.exe was killed (run `failed`, `run_failed` warn). 0.3 s later the Hub re-queued `entry-e6e328365c30` (`queue_entry_queued` carrying the failed `run_id`) and delivered it in `run-676f4f39e098` (`run_triggered` `session_mode: resume`, `initiator: "operator"`; `delivery_attempts` 1). Haiku's thinking: "The previous attempt was interrupted. I'll run it again" — it re-ran the 120 s sleep. The digest shows two rows, "alpha stopped with an error | Run this exact shell command..." and "alpha was stopped | Run this exact shell command...", and nothing says the second was the Hub retrying, not the operator sending again.

Cause (verified): `queue_entry_delivered` and `run_triggered` carry no attempt number and the re-delivery is stamped `initiator: "operator"`; `buildDigest` maps an entry to its last delivery only (`hub/ui/src/lib/activityDigest.ts:76-80`), so it cannot tell attempt 2 from a new send.

**Expected:** a re-delivery's events carry the attempt (e.g. `delivery_attempt: 2`) and the digest row says "retried after ...". **Test:** an `activityDigest.test.ts` case in the Hub's order — `run_failed`, `queue_entry_queued`, `run_triggered`, `queue_entry_delivered` (attempt 2), `run_started` — the second row names the retry. Fails today. Seam: Inbound queue (re-delivery) x Activity digest.

## F999 (D) -- Clear leaves its own `DELETE /traces` request trace behind: the screen reads "0 traces" while the Hub holds 1, and the next clear promises "0 traces, 0 spans" then reports "Cleared 1 trace (1 span)"

**Status:** open 2026-10-23. Found by the day sweep `sweep-traces-sweep` (Traces row; scratch Hub :8120, Chromium on the served bundle, `scripts/drive/s1023_tc_ui.py section`).
**Source:** drive
**Theme:** Traces
**Ready:** yes
**Tier:** 0

Settings -> General -> Traces -> "Clear traces..." -> confirm: status "Cleared 67 traces (268 spans)", Recorded "0 traces · 0 spans"; `GET /traces/settings` straight after -> `trace_count 1, span_count 1`. Clear again: the dialog reads "... deleted — 0 traces, 0 spans", then the status line reads "Cleared 1 trace (1 span)".

Cause (verified): every non-GET request is kept as a trace (`hub/hub/trace_requests.py:33-38`), so the DELETE writes its own span after the delete committed; `useClearTraces` invalidates on success (`hub/ui/src/api/traces.ts:213-215`) and refetches before the span writer flushes.

**Expected:** "clear everything" leaves nothing: `DELETE /traces` is not kept as a request trace (or its span is dropped by its own clear), so Recorded, the confirm's count and the result agree. **Test:** a route test: `DELETE /traces`, flush the span writer, `trace_count == 0`. Fails today. Seam: Traces (clear) x request tracing.

## F1000 (D) -- the task story reads "0 tokens" for a run whose usage was never reported

**Status:** open 2026-10-23. Found by the day sweep `sweep-traces-sweep` (Traces row; scratch Hub :8120, task-013fd5cbc415, stopped run run-c33ff06dad08).
**Source:** drive
**Theme:** Accounting & allowance
**Ready:** yes
**Tier:** 0

The run was stopped mid-tool-call; its `turn_usage` row is `status unavailable` with every token column null, and its trace root says `aw.usage.status: unavailable`. `GET /tasks/{id}/story` returns `"tokens": 0, "cost_usd": null`; the drawer's story reads "12s · 0 tokens · stopped · ... · trace". `/ledger` `spend.by_agent` likewise reports `breaker` (3 runs, all unavailable) as `usd 0.0, tokens 0`. Same family as F961 (the Ledger's $0.00 for unpriced turns).

Cause (verified): `hub/hub/task_story.py:202,225` gives `"tokens": tokens if rows else None`; an unavailable row still counts as a row, so its null tokens sum to 0. Cost is right through `priced` (`:199`).

**Expected:** `tokens` is null when no row reported `total_tokens`, so the story shows no token count, as it shows no cost. **Test:** a task-story test: one `turn_usage` row, status `unavailable`, `total_tokens` null -> `tokens is None`. Fails today. Seam: TaskStory x Accounting.

## F1001 (D) -- a Claude run that fails at CLI startup is traced as a 3.3 s model call whose assistant output is the CLI's error, and the root says only "run failed"

**Status:** open 2026-10-23. Found by the day sweep `sweep-traces-sweep` (Traces row; :8120, runner `broken` with flags `["--definitely-not-a-flag"]`; run-58adc321402d, run-231feacb21d8, run-91f6d81bd183).
**Source:** drive
**Theme:** Traces
**Ready:** yes
**Tier:** 0

All three attempts exited 1 with `runs.error` null. Each trace: root `error`, `status_message: "run failed"`, plus a `chat claude-haiku-4-5-20251001` span of 3.3-3.6 s whose `gen_ai.output.messages` is `[{"role":"assistant","parts":[{"type":"text","content":"error: unknown option '--definitely-not-a-flag'"}]}]`. No model was called. The drawer's red line reads "run failed"; the cause appears only as the "model call" output.

Cause (verified): `parse_claude_line` turns any non-JSON stdout line into a `text` event (`hub/hub/runner_parsing.py:290-297`), traced as the chat segment's output; `finish_run` falls back to "run failed" when `run.error` is empty (`hub/hub/traces.py:738-740`).

**Expected:** the root's message names the failure, e.g. "run failed (exit 1): error: unknown option '--definitely-not-a-flag'" (exit code and last output when `run.error` is empty). **Test:** a `finish_run` test: failed run, `error` None, exit 1, one text output -> `status_message` contains "exit 1" and that text. Fails today. Seam: Traces x Runs (runner output parsing).

## F1002 (D) -- a retried delivery's trace starts at the input's first arrival: attempt 3 reads "22.1 s" with an 18.6 s delivery bar, for a turn that "Worked for 4s"

**Status:** open 2026-10-23. Found by the day sweep `sweep-traces-sweep` (Traces row; :8120, Chromium, `scripts/drive/s1023_tc_ui.py fail`, entry-09a99679e9c3).
**Source:** drive
**Theme:** Traces
**Ready:** yes
**Tier:** 0

The three attempts' `aw.deliver` spans all start at 12:07:50.449 (the entry's arrival) and end at 12:08:00.948, 12:08:05.124, 12:08:09.008 (`aw.queue.delivery_attempt` 1, 2, 3). Run 3 lasted 12:08:09.002-12:08:12.567, but its drawer header reads "error breaker ... · 22.1 s · 7 spans" with an 18.6 s delivery row; the conversation says "Worked for 4s". Each attempt's trace covers all the earlier attempts' time.

Cause (verified): `record_deliveries` starts at `min(entry.arrived_at, at)` (`hub/hub/traces.py:562`) — the docstring's "from its arrival to this delivery" — for every attempt.

**Expected:** an attempt after the first starts its `aw.deliver` at its own re-queue (the previous attempt's end / `queue_entry_queued`), so the attempts' traces do not overlap. **Test:** `record_deliveries` for an entry on its third attempt starts after attempt 2's end. Fails today. Seam: Traces x Inbound queue (retries).

## F1003 (D) -- a trace carrying a Hub warning looks like every other trace in the list and the drawer header; the warning appears only in the root span's Events

**Status:** open 2026-10-23. Found by the day sweep `sweep-traces-sweep` (Traces row; :8120, Chromium, Settings -> General -> Traces -> Work). First time a Hub warning on a project trace was reached (held a file open in a task checkout's `.agentweave/calls/` while a turn started).
**Source:** drive
**Theme:** Traces
**Ready:** yes
**Tier:** 0

Two of ten `inbound_queue` Work traces carry a WARNING `log` event (`could not remove ...calls\held.json ...: [WinError 32]`); it renders in the drawer's span detail and is exported as an OTLP log record. But all ten list rows read the same ("inbound_queue · work · 431 ms · 12 · Open") and the drawer header reads "ended ...": the warning is visible only after selecting the root span, under Events.

Cause (verified): `_summary` (`hub/hub/traces.py:1629-1649`) carries no warning fact, so `TracesSection`'s row (`hub/ui/src/components/environment/TracesSection.tsx:105-130`) and `TraceView`'s header have nothing to show.

**Expected:** the summary carries the trace's warning count, and the list row and the drawer header show it ("1 warning"). **Test:** `GET /traces` for a work trace with one `log` event -> summary warning count 1. Fails today. Seam: Traces (hub-warnings-are-on-their-trace) x Settings list.

## F1004 (D) -- a mistyped `otlp_headers` body is refused with the header's value echoed in `detail[].input`

**Status:** open 2026-10-23. Found by the day sweep `sweep-traces-sweep` (Traces row; scratch Hub :8120, `scripts/drive/s1023_tc_probes.py`).
**Source:** drive
**Theme:** Traces
**Ready:** yes
**Tier:** 2 -- secrets (CLAUDE.md's table); a response echo only, nothing persisted.

`PUT /traces/settings {"otlp_headers":{"Authorization":["Bearer quokka-header-value-7781"]}}` -> 422 with `"input": ["Bearer quokka-header-value-7781"]`; `{"otlp_headers":"Authorization=Bearer quokka-header-value-7781"}` -> 422 with the whole string as `input`. The value is in neither `trace_spans` nor `event_logs`. The section promises "Values are stored and never shown again".

Cause (verified): `otlp_headers: Optional[Dict[str, str]]` (`hub/hub/api/v1/traces.py:113-115`) is checked by the schema; the runner schema deliberately types `provider_config` as `Any` for exactly this reason (`hub/hub/schemas/runners.py:19-22`).

**Expected:** `otlp_headers` typed loosely and checked in the route, with a sentence naming the header and never its value. **Test:** the PUT above -> 422 and the body does not contain "quokka-header-value". Fails today. Seam: Traces settings x request validation.

## F1008 (D) -- a hand-made task with no branch is told "no accepted evidence names a commit" on approve, retry and preview, the evidence sentence F622 retired for tasks evidence does not govern

**Status:** open 2026-10-23. Found by the day sweep `sweep-tasks-sweep` (Worktrees row; scratch Hub :8160, profile wt1023, proj-1fff2af61236, `scripts/drive/s1023_wt_drive.py skip`).
**Source:** drive
**Theme:** Worktrees & integration
**Ready:** yes
**Tier:** 0

Task N: made by hand, no loop (`loop_id` null), no requirement link, no run, in a project with zero `requirement_evidence` rows. `PATCH` it to `approved` -> `latest_integration: skipped, "no accepted evidence names a commit, so there is nothing to merge"`; `GET /tasks/<N>/integration-preview` -> the same reason. Its siblings T1-T4 (same shape, but with a branch) merge their branch tip, so evidence never governed N either; the honest sentence is `NO_TASK_BRANCH` ("this task has no branch of its own"). With the project's `.git` moved aside, the preview of the approved branch-tip task T4 also answered the evidence sentence.

Cause (verified): `_integrate_task` picks the empty reason on `evidence_governs` alone (`hub/hub/task_transition_service.py:1204`), and so does the preview (`hub/hub/api/v1/tasks.py:1192-1195`); `merge_targets` (`hub/hub/task_integration.py:550`) also asks `review_alone_gates`, which F622 added and these two never learned.

**Expected:** both ask the same question `merge_targets` does, so a review-alone task with no branch reads `NO_TASK_BRANCH`. **Test:** `hub/tests/test_task_integration.py`: a loopless, linkless task with no branch, approved -> reason == `NO_TASK_BRANCH`, and the preview's `reason` the same. Fails today. Seam: Worktrees & integration x Tasks. Same preview sentence, other case: F1010 (awaiting evidence).

## F1012 (D) -- the task story records the operator's send-back and block with no reason: "You moved it to sent back" and "You moved it to waiting on you" carry neither the revision notes nor the blocked reason

**Status:** open 2026-10-23. Found by the day sweep `sweep-tasks-sweep` (Tasks row; scratch Hub :8162, profile tk1023, proj-d51843e66b2a, `scripts/drive/s1023_tk_drive.py revise/stall/story`, `scripts/drive/s1023_tk_ui.py drawer W|S`).
**Source:** drive
**Theme:** Tasks
**Ready:** yes
**Tier:** 2

```
PATCH /tasks/W {"status":"revision_needed","notes":"Add a test for mul() in tests/test_ops.py asserting mul(2, 3) == 6."} -> 200
PATCH /tasks/S {"status":"blocked","blocked_reason":"Which currency should OK use?"} -> 200
GET /tasks/W/story -> {"kind":"transition","from":"completed","to":"revision_needed","actor":"operator","override_reason":null, ...}   (no notes)
Chromium story W: "You moved it to sent back from completed · 3m ago"     story S: "You moved it to waiting on you from in progress · just now"
DB task_transitions columns: ... origin, job_id, policy_digest, override_reason, created_at   (no reason/notes column)
```

The why of the two operator moves that most need one lives only in the task's single `notes` / `blocked_reason` fields, which the next write overwrites (`update_task`'s own docstring: "Overwrites the task's existing notes"). After a second round the story cannot say why the task was sent back the first time. The card shows the block's reason today only because it is still blocked.

Cause (verified): `task_transitions` stores no reason except `override_reason` (`hub/hub/db/models.py:844`); the story builds transition events from those rows only (`hub/hub/task_story.py:171-189`). Tier 2 because the natural fix adds a column (a migration); reading the reason back from the `task_updated` event of the same moment avoids it.

**Expected:** a send-back, rejection or block records its reason with the transition, and the story shows it under the move ("You sent it back: Add a test for mul() ..."). **Test:** a story test: `revision_needed` with notes, then the author completes with new notes -> the story's revision_needed event still carries the first notes. Fails today. Seam: Tasks (story) x Flows & review.

## F1020 (D) -- naming a main branch on a project that is not a git repository is refused as "This project has no branch named 'main' ... it has to exist first"

**Status:** open 2026-10-23. Found by the day sweep `sweep-projects-sweep` (Projects row; scratch Hub :8116, profile pj1023, proj-cda38bae12bd, `scripts/drive/s1023_pj_api.py branch`).
**Source:** drive
**Theme:** Projects
**Ready:** yes
**Tier:** 0

A folder with no `.git` (`C:\Users\huida\Documents\aw-pj1023 sp ção`), opened as a project: `GET /main-branch-suggestion` -> `{"suggestion": null, "chosen": null, "is_repository": false}`. `PUT /settings {"main_branch": "main"}` -> 400 "This project has no branch named 'main'. Approval merges into it, so it has to exist first." There is no branch to create: the folder is not a repository, which the suggestion route knows. The app disables the field for a non-repository ("This folder is not a git repository, so there is nothing to merge into."), so only an API or agent caller meets this. Cause (verified): `update_project_settings` checks only `task_integration.branch_exists` (`hub/hub/api/v1/projects.py:685-691`). **Expected:** "This folder is not a git repository, so there is no branch to merge into; run `git init` and commit first." **Test:** beside the existing no-such-branch settings test in `hub/tests/`: a non-repository project's PUT names the missing repository (fails today). Seam: Projects (settings) x Integration.

## F1021 (D) -- F729 is back: deleting a project fires six GETs of the deleted project (all 404), and the app lands on another project's Overview with no word of the delete; a link to a deleted project does the same silently

**Status:** open 2026-10-23. Found by the day sweep `sweep-projects-sweep` (Projects row; scratch Hub :8116, profile pj1023, proj-81f4e76f8e92 and proj-c29934c5b878, Chromium against the served bundle, `scripts/drive/s1023_pj_ui.py delete` / `dead`, shots `testbed/ui-judge/s1023-pj/140401/51_after_delete.png`, `140509/60_dead_settings.png`).
**Source:** drive
**Theme:** Projects
**Ready:** yes
**Tier:** 0

Settings -> Delete project... -> type the name -> Enter. `DELETE` 204, the private vault folder is gone (fix-D1 holds), and then:

```
404 GET /api/v1/projects/proj-81f4e76f8e92/agents
404 GET /api/v1/projects/proj-81f4e76f8e92/tasks?limit=1000
404 GET /api/v1/projects/proj-81f4e76f8e92/questions?answered=false
404 GET /api/v1/projects/proj-81f4e76f8e92/ledger
404 GET /api/v1/projects/proj-81f4e76f8e92/conversations?lifecycle=open
404 GET /api/v1/projects/proj-81f4e76f8e92/accounting
```

(eight on the first delete, proj-c29934c5b878). The page then shows the other project's Overview: no toast, no "Deleted aw-pj1023-b" line. F729 (fixed 7a55bb1, 2026-10-18) promised "no query for the deleted project runs"; the ui-finesse shell rewrite (a8ca6e2) came after. Opening `/?project=<deleted id>&tab=environment&section=settings` (or `section=instructions`) lands on another project's Overview with ~12 more 404s and nothing saying the requested project does not exist -- so a failed settings read (F197's alert) cannot be provoked through a deleted id; navigation hides it.

**Expected:** no request for the deleted id after the 204 (the Overview queries included); after a delete, a one-line "Deleted <name>. Its folder was left as it was." where the app lands; a link to an unknown project says so before falling back. **Test:** `hub/ui/src/__tests__/` beside the F729 test: deliver the `project_deleted` event the route broadcasts and mount the Overview the delete navigates through -> no fetch of the deleted id (the F729 test used neither). Seam: Projects (delete) x Overview / navigation.

## F1022 (D) -- small Projects items from the 2026-10-23 sweep: `/favicon.ico` is index.html, identical compact-rail tiles, a typed UNC path ignored by the in-Hub browser, junctions listed as folders

**Status:** open 2026-10-23. Found by the day sweep `sweep-projects-sweep` (Projects row; scratch Hub :8116, profile pj1023, proj-19b3a5f0a902, `scripts/drive/s1023_pj_brand.py`, `s1023_pj_ui.py picker`, `s1023_pj_api.py fs`; shots `testbed/ui-judge/s1023-pj/135317/04_compact_light.png`, `140158/20_picker_3.png`).
**Source:** drive
**Theme:** Projects
**Ready:** yes
**Tier:** 0

1. **`GET /favicon.ico` answers 200 `text/html` (the SPA's index.html, 1059 bytes)**, while the brand commit (e23cbc6) rewrote `hub/hub/static/ui/favicon.ico` (2,941 bytes), which nothing can serve: only `/assets` is mounted and `serve_spa` (`hub/hub/main.py:744`) answers every other path. The page's own `<link rel=icon>` (`/assets/favicon-DzfNCeau.svg`, 200 `image/svg+xml`, the loop on `#15171C`) is fine, so browsers show the right icon; a client that asks for `/favicon.ico` (a bookmark/shortcut, a non-SVG consumer) gets HTML labelled 200. Either serve `favicon.ico` from the bundle root or drop the dead file.
2. **Compact rail tiles are the first two letters of the name** (`hub/ui/src/components/layout/Sidebar.tsx:433`): `aw-pj1023-a` and `aw-pj1023-b` both read **AW**, told apart only by hovering (`title`). Projects sharing a prefix (`agentweave-*`, `aw-*`) are indistinguishable at a glance; agent tiles (`:453`) have the same scheme.
3. **A typed UNC path is ignored by the in-Hub browser.** Typing `\\localhost\c$\Users\huida\Documents` and opening "Browse within the Hub instead" lists `C:\` (`$Recycle.Bin`, `c`, ...), though `GET /fs/list` lists the UNC path correctly (200, its entries): `startPath` accepts only `X:\` or `/` (`hub/ui/src/components/projects/ProjectManagerModal.tsx:159`). Same for a bare `C:` (listed from `C:\`, while `/fs/list?path=C:` is 400 "path must be absolute" without saying `C:\` would do).
4. **Junctions are listed and followed.** `GET /fs/list?path=C:\Users` lists `Default User` (a junction); `GET /fs/list?path=C:/Users/Default User` answers `path: C:\Users\Default`. `fs_browse.py`'s docstring promises "a symlinked directory is excluded rather than traversed"; `entry.is_dir(follow_symlinks=False)` (`hub/hub/fs_browse.py:109`) is true for a Windows junction on Python 3.11 and `Path.resolve` follows it (F799's class, for the picker). Harmless in native mode; it is the containment claim `AW_WORKSPACE_ROOT` relies on.

**Expected / Tests:** (1) a `hub/tests/` test that `GET /favicon.ico` is not `text/html`; (2) a Sidebar test with two `aw-*` projects whose compact tiles differ; (3) `projectManagerDirectoryPicker.test.tsx`: a typed `\\server\share\dir` starts the picker there; (4) `hub/tests/test_fs_browse*.py`: a junction (`mklink /J`) is excluded like a symlink. Seam: Projects (brand, rail, folder browser).

## F1026 (D) -- unarchiving an agent whose runner was deleted while it was archived answers "An agent with no charter still runs" while it has no runner and cannot run

**Status:** open 2026-10-23. Found by the day sweep `sweep-projects-sweep` (Runners & models row; scratch Hub :8117, profile rm1023, proj-8717fc708877, `scripts/drive/s1023_rm_edges.py`, also `s1023_rm_holders.py` with agent `a-cop`).
**Source:** drive
**Theme:** Runners & models
**Ready:** yes
**Tier:** 0

```
POST /projects/{p}/runners {"name":"arch2","cli":"claude","model":"haiku"}       -> 201
POST /projects/{p}/agents {"name":"a-arch2","runner_id":<arch2>}                  -> 201
POST /projects/{p}/agents/a-arch2/archive                                         -> 200
DELETE /projects/{p}/runners/<arch2>                                              -> 204   (a-arch2.runner_id -> NULL)
POST /projects/{p}/agents/a-arch2/unarchive -> 200
  "message": "No charter is bound. Archiving releases an agent's charter and unarchiving does not restore it. An agent with no charter still runs — bind one only if this agent should have one."
GET /projects/{p}/agents/launchability -> a-arch2: runnable false, "No runner is bound to this agent. Bind one in the Hub UI before it can run."
```

The answer names the one release it knows about (the charter) and asserts the agent runs, while the release that matters, the runner the delete unbound (`hub/hub/api/v1/runners.py:291-303`, F532's fix), goes unmentioned. A message then sent to it is held ("Input queued for a-cop", `waiting_reason` "No runner is bound ..."). The app's Unarchive (`ArchivedAgentNotice.tsx`) does not show the message, so the reader is an API or tool caller; the agent's Execution screen does say "This agent cannot run".

Cause (verified): the sentence is a constant (`hub/hub/api/v1/agents.py:3449-3456`) and does not read `agent_row.runner_id`.

**Expected:** with no runner bound, the answer says so first ("a-arch2 has no runner: the runner it had was deleted while it was archived. Bind one in its settings before it can run."), and the charter sentence no longer claims it runs. **Test:** beside `hub/tests/test_a_runner_a_setting_names_cannot_be_deleted.py`: archive an agent, delete its runner, unarchive -> the message names the missing runner and does not contain "still runs". Fails today. Seam: Runners & models (delete) x Agents (unarchive).

## F1062 (D) -- the checks' return of a task to its builder is recorded as `actor_kind='operator'`; only `origin='checks'` says otherwise

**Status:** open 2026-10-28. Found by the scoped drive of slices L/M/J (:8031): `task_transitions` sequence 5 of task-222e, `actor_kind='operator'`, `origin='checks'`. Whether the task's history names the checks on screen (`history-names-the-checks`) was not driven.
**Source:** drive
**Theme:** Checks
**Ready:** yes
**Tier:** 0

Drive record (what held, 16 Haiku turns + 2 Copilot-stub turns): fast-check validation (a fast check over 120 s is 422 with the reason); completion refused on an uncommitted ruff failure with the check, merged sha, run id and output, after the Hub snapshotted the agent's uncommitted work; one run per work; review refused 409 `checks_pending` while a slow check ran; own failure sent back with no review; reviews staged 3 s and 6 s after checks passed (the minute held); M's red-main flow landed with `override_by='hub'` and a named reason, one critical fix task filed, staffed at once, landed, and the next check ran on the fixed main; an assigned task outside a flow started in under 1 s; J's rebind claude -> copilot (stub) -> claude started a new session at each crossing with one legible diagnostic, kept the session on a same-runner turn, and usage named the model. Not reached: all UI criteria, Codex, a real Copilot turn, the 120 s budget, the hub-ui check, migration backfills, M's setting-off behaviour live.

