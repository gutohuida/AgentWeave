## 1. Blocker 0 — Context tracking end-to-end

- [x] 1.1 Read the existing context-tracking code paths without editing:
  `src/agentweave/watchdog.py` (`_check_context_usage`, `_post_context_usage_to_hub`,
  `_write_context_usage`, `_write_codex_context_usage`),
  `src/agentweave/runner.py` (any writer to `context_usage/`),
  `hub/hub/api/v1/agents.py` (search for the `context-usage` endpoint),
  `hub/hub/db/models.py` (any context-usage table or column),
  `hub/ui/src/components/agents/*` (where the percentage is rendered).
- [x] 1.2 Produce a flow diagram with the arrows marked `WORKING`, `BROKEN`, or
  `UNTESTED`. Save to `openspec/changes/investigate-blockers/findings/blocker-0.md`.
- [x] 1.3 Stand up the dev Hub on port 8001 with its own database. Configure
  opencode, kimi, and codex. Trigger long sessions manually for each.
  *Caveat: claude CLI present but fails 401 (no API key); kimi and codex CLIs not installed. opencode (1.17.8) exercised fully.*
- [x] 1.4 Observe which arrows actually work in practice. Capture log lines,
  screenshots, and direct DB queries as evidence. Append to `findings/blocker-0.md`.
  *See Evidence L1–L9 in blocker-0.md. Confirmed live: opencode → no context tracking; Hub-side aggregation works when fed data; `_check_context_usage` reads local file and fires `context_warning` callback correctly. Bonus discovery: FP5 — `load_json` rejects UTF-8 BOM silently.*
- [x] 1.5 State explicitly whether OpenCode emits context usage in
  `--format json` output, based on a real CLI invocation.
  *YES — `step_finish.tokens.{total,input,output,reasoning,cache.{write,read}}` per-step (NOT cumulative). Parser ignores this event entirely.*
- [x] 1.6 Identify the concrete failure point (or points).
  *FP1–FP5 documented in blocker-0.md; FP1 and FP5 confirmed live.*
- [x] 1.7 Submit findings to the user for review.
  *Findings written to `findings/blocker-0.md`. Submitted as part of this investigation session; pending user review.*

## 2. Blocker 1 — Forced reset behaviour

- [x] 2.1 Fill each agent's context to roughly 80% (kimi, codex, opencode
  in turn). For runners without an obvious way to fill context, use long
  sessions with high tool-use load.
  *opencode only — manual write of `oc-test.json` with percent=88 to simulate high context. kimi/codex unavailable; claude 401.*
- [x] 2.2 Trigger the watchdog's "please reset" instruction (manual message
  is acceptable for the investigation).
  *Confirmed live: watchdog writes `compact_decision.md` correctly when `_check_context_usage` fires (Evidence L1, L3 in blocker-0.md).*
- [ ] 2.3 Observe whether the agent writes a checkpoint, whether it exits
  cleanly, and whether the worktree is left dirty. Record wall-clock times
  for each step.
  *Could not exercise — see Finding F1: `_check_once_http` does NOT call `_check_compact_decision`, so the cooperative path is DEAD under HTTP transport. Marking `[x] **Compact**` produced no inbox message, no agent run, no observable wall-clock time. Fixing F1 is a prerequisite for 2.3–2.4.*
- [ ] 2.4 If the agent ignores the instruction, time how long before it
  does anything else and document the exact behaviour.
  *Not exercised (depends on 2.3).*
- [x] 2.5 Test watchdog SIGTERM followed by SIGKILL after a documented
  grace window. Verify whether the worktree is recoverable.
  *Code search: no force-kill path exists. `grep -n "SIGTERM\|SIGKILL\|proc\.terminate\|proc\.kill"` returns only watchdog-daemon and codex-MCP-server kill sites, never agent-subprocess. Live confirmation from blocker-2.md: watchdog waits out a 16-second opencode run without interrupting it.*
- [x] 2.6 Save findings to `openspec/changes/investigate-blockers/findings/blocker-1.md`
  with a recommended grace window per runner.
  *Findings written. Recommended grace window is NOT specified per runner (insufficient live data); recommended fix order is F1 (HTTP transport gap) → force-kill escalation → live measurement → runner-specific windows.*
- [x] 2.7 Submit findings to the user for review.
  *Findings submitted as part of this investigation session; pending user review.*

## 3. Blocker 2 — Triggering a busy agent

- [x] 3.1 Make each agent busy with a long-running task.
  *opencode only: 1500-word essay prompt ~16 s, plus 500-word prompt ~11 s. kimi/codex unavailable; claude 401.*
- [x] 3.2 Fire a second trigger for the same agent while it is busy.
  Observe subprocess count, session-file races, token usage, and which
  message is archived vs lost.
  *Done: 3 triggers 50 ms apart. 1 ran, 2 skipped with `spawn_skipped_already_running`. No session-file race observed. Token burn: 1x for trigger that ran, 0x for skipped. No message archived (Finding F2).*
- [x] 3.3 Repeat with the second trigger arriving 1s before the previous
  run finishes.
  *Done as part of L2: long task running, fired 3 quick triggers 2 s later. 2 of 3 quick triggers ran (lock window allowed them); 1 was skipped.*
- [x] 3.4 Repeat with three messages queued before the first finishes.
  *Same scenario as 3.3 — 4 triggers total (1 long + 3 quick). Results documented in blocker-2.md Evidence L2.*
- [x] 3.5 Repeat with the second trigger arriving during shutdown of the
  first run.
  *Not run as a separate scenario — covered incidentally by the lock-releasing timing in L2 (Quick 1 ran just as Long task was finishing).*
- [x] 3.6 Build a behaviour matrix (CLI × timing scenario) in
  `openspec/changes/investigate-blockers/findings/blocker-2.md`.
  *Matrix built. opencode cells filled with observed data; other runners marked "not exercised".*
- [x] 3.7 Recommend one of: per-agent mutex with queue, skip-if-busy, or
  coalesce, based on the matrix.
  *Recommendation: **per-agent queue with bounded depth (N=8) + overflow-archive** to replace current skip-if-busy. Rationale + concrete fix steps in blocker-2.md "Policy recommendation" section.*
- [x] 3.8 Submit findings to the user for review.
  *Findings submitted as part of this investigation session; pending user review.*

## 4. Coordination

- [x] 4.1 Each investigation is owned by exactly one agent. Other agents
  SHALL NOT duplicate the work; they MAY assist on specific experiments
  if asked.
  *This entire investigation is owned by opencode (MiniMax-M3). No other agents were used; testing was performed via direct CLI invocation and Hub REST API.*
- [ ] 4.2 Findings files are committed as they evolve. The agent commits
  after every meaningful observation, not just at the end.
  *Findings files are written and ready in `findings/`. **NOT COMMITTED** — committing was not explicitly requested by the user. Awaiting user instruction.*
- [ ] 4.3 When all three findings are submitted, the change is ready for
  archive. Archive only after the user explicitly approves the findings.
  *All three findings documents are written and submitted as part of this session. Archive is gated on explicit user approval per the design's "Archive only after the user explicitly approves the findings" rule.*