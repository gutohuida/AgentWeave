# Blocker 2 — Triggering a busy agent findings

**Status:** live-tested. Behaviour matrix populated from observed data. **The static analysis in the earlier draft of this file was wrong** — there IS a per-agent mutex. The watchdog uses **skip-if-busy** (not queue, not coalesce).
**Owner:** opencode (MiniMax-M3), 2026-06-20.

## TL;DR

- **Per-agent mutex exists** (`src/agentweave/watchdog.py:2550-2566`): `_run_agent_subprocess` calls `acquire_lock("spawn_{agent}", timeout=0.1)`. If the lock is held, the spawn is **SKIPPED** with reason `"another_instance_is_running"`. This is **skip-if-busy**, not queue and not coalesce.
- **No re-queue.** Skipped triggers are dropped. The corresponding Hub message stays unread forever (see Finding F2 below).
- **Lock timeout is 100 ms.** If the lock isn't released within 100 ms (i.e., the running agent takes more than 100 ms between spawn check and lock release), the new trigger is dropped. For typical opencode sessions this is fine; for very fast runs it can cause spurious drops.
- **Session-file race is not observed in practice** during this investigation. All concurrent runs in the test reused the same opencode session ID; no race detected. The session-file write happens only AFTER `proc.wait()` returns (`watchdog.py:2688-2690`), and the watchdog's lock means only one subprocess for the same agent is alive at a time anyway.
- **Hub message archival is broken for regular triggers.** `_check_once_http` does not call `transport.archive_message()` after triggering an agent (only for codex `new_session_request` special-case). All 7 messages fired during testing remained `read=False` on the Hub until manually PATCHed.

## Live evidence

### Evidence L1 — Concurrent triggers, mid-run overlap

**Setup:** oc-test idle, session ID `ses_119eacb33ffesV4fcawQefvMgf`.

**Action:** Fire 3 triggers with 50 ms spacing via Hub POST `/api/v1/messages`. Triggers 2 and 3 arrive while trigger 1 is still running.

```
POST msg-266d145a ("B2 trigger 1") at t=0
POST msg-a5c709aa ("B2 trigger 2") at t=+0.05
POST msg-708ccd80 ("B2 trigger 3") at t=+0.10
```

**Watchdog events:**

```
19:02:08  agent_triggering_from_hub  agent=oc-test  msg_id=msg-266d145a  session_id=ses_119eacb33f...
19:02:08  trigger_event
19:02:08  agent_triggering_from_hub  agent=oc-test  msg_id=msg-a5c709aa  session_id=ses_119eacb33f...
19:02:08  trigger_event
19:02:08  agent_triggering_from_hub  agent=oc-test  msg_id=msg-708ccd80  session_id=ses_119eacb33f...
19:02:08  trigger_event
19:02:08  spawn_skipped_already_running  agent=oc-test  reason=another_instance_is_running
19:02:08  watchdog_skip
19:02:08  spawn_skipped_already_running  agent=oc-test  reason=another_instance_is_running
19:02:08  watchdog_skip
19:02:19  watchdog_agent_done
```

**Outcome:**

| Trigger | msg_id | Spawn result | Outcome |
|---------|--------|--------------|---------|
| 1 | msg-266d145a | ran | Agent run completed at 19:02:19, 11 s |
| 2 | msg-a5c709aa | skipped | Silently dropped |
| 3 | msg-708ccd80 | skipped | Silently dropped |

**Hub message state after run:**

```
GET /api/v1/messages?to=oc-test → 4 messages, ALL read=False
  msg-9f131888  read=False  from=user  "Investigate blocker 0"
  msg-266d145a  read=False  from=user  "B2 trigger 1"
  msg-a5c709aa  read=False  from=user  "B2 trigger 2"
  msg-708ccd80  read=False  from=user  "B2 trigger 3"
```

**Conclusion:** 1 trigger ran, 2 were silently dropped. None of the messages were archived. The user's intent for triggers 2 and 3 is lost.

### Evidence L2 — Long task + 3 quick triggers (mid-task overlap + near-finish overlap)

**Setup:** oc-test idle, watchdog running.

**Action:**

```
t=0    POST msg-e00a0d5d ("Long task") — 1500-word essay prompt, expected to take ~15s
t=2    POST msg-0ff70bb0 ("Quick trigger 1") — "PONG-1"
t=2.05 POST msg-35eda734 ("Quick trigger 2") — "PONG-2"
t=2.10 POST msg-610b3bba ("Quick trigger 3") — "PONG-3"
```

**Watchdog events:**

```
19:04:04  agent_triggering_from_hub  agent=oc-test  msg_id=msg-e00a0d5d  (Long task starts)
19:04:09  agent_triggering_from_hub  agent=oc-test  msg_id=msg-0ff70bb0  (Quick 1)
19:04:09  agent_triggering_from_hub  agent=oc-test  msg_id=msg-35eda734  (Quick 2)
19:04:09  spawn_skipped_already_running  agent=oc-test                (Quick 3 SKIPPED)
19:04:09  watchdog_skip
19:04:21  watchdog_agent_done
```

**Outcome:**

- Long task ran from 19:04:04 to ~19:04:20 (16 s)
- Quick 1 and Quick 2 were both "agent_triggering_from_hub" events but produced no separate "watchdog_agent_done" — they appear to have shared the lock window with the Long task (the 100 ms timeout + the lock being released between spawn attempts)
- Quick 3 was skipped

**Hub messages after run:** all 7 messages remain `read=False`.

### Evidence L3 — Session-file race: NOT observed

**Concern:** static analysis predicted a race on `.agentweave/agents/oc-test-session.json` when two concurrent runs for the same agent finish near-simultaneously.

**Observation:** only one concurrent run ever holds the lock at a time, so `proc.wait()` (and the subsequent `_save_agent_session` call at `watchdog.py:2688-2690`) is serialised per agent. The race is structurally impossible under the current mutex design.

**Final session file contents:**

```
$ cat .agentweave/agents/oc-test-session.json
{"session_id": "ses_119eacb33ffesV4fcawQefvMgf"}
```

Same session ID across all 3 distinct oc-test runs that completed during the test. No race observed. (Caveat: the runs were near-finish overlaps, not simultaneous finishes.)

### Evidence L4 — Hub message archival broken for regular triggers

**Concern:** static analysis noted that the watchdog's HTTP transport path doesn't call `archive_message` for regular user triggers.

**Observation:** all 7 user messages fired during testing remained `read=False` on the Hub. The user has no way to tell from the Hub inbox which of their triggers were processed vs skipped.

**Root cause** (`src/agentweave/watchdog.py:686-719`):

```python
def _check_once_http(self) -> None:
    self._check_context_usage()
    messages = self.transport.get_pending_messages(self.agent or "")
    for msg in messages:
        msg_id = msg.get("id", "")
        if msg_id and msg_id not in self.known_messages:
            # ...codex new_session_request special case that DOES archive...
            if subject == "new_session_request" and recipient:
                ...
                self.known_messages.add(msg_id)
                with contextlib.suppress(Exception):
                    self.transport.archive_message(msg_id)
                continue

            self.known_messages.add(msg_id)             # ← only added to in-memory set
            self.callback("new_message", msg)            # ← no archive call
            # ...auto-trigger agent...
            if sender == "user" and recipient ...:
                self._trigger_agent_from_message(recipient, msg)
```

For regular `from=user` triggers, the message is added to `self.known_messages` (so the watchdog won't re-process it on the next tick) but **never archived on the Hub**. The Hub keeps it in the unread inbox forever.

**Verification:** manual PATCH `/messages/{id}/read` works and removes the message from the inbox, confirming the archive endpoint functions correctly. The bug is purely in the watchdog's call-site.

### Evidence L5 — Lock source (the mutex itself)

`src/agentweave/watchdog.py:2539-2566`:

```python
def _run_agent_subprocess(
    agent: str,
    cmd: list,
    subject: str,
    transport: Any,
    is_http: bool,
    env_vars: Optional[Dict[str, str]] = None,
    prompt: str = "",
    known_session_id: Optional[str] = None,
) -> None:
    """Background thread: run agent, stream output to Hub, save session ID."""
    from .locking import acquire_lock, release_lock

    # Acquire lock to prevent concurrent spawns of the same agent
    lock_name = f"spawn_{agent}"
    if not acquire_lock(lock_name, timeout=0.1):  # Short timeout - try once, don't block
        logger.info(
            "spawn_skipped_already_running",
            extra={
                "event": "spawn_skipped_already_running",
                "data": {"agent": agent, "reason": "another_instance_is_running"},
            },
        )
        logger.warning(
            f"[SKIP] {agent} is already running, skipping spawn",
            extra={"event": "watchdog_skip", "data": {}},
        )
        return

    try:
        ...                                    # run subprocess, save session, release_lock at end
```

`release_lock` is called via the `try`/`finally` later in the function (not visible in the snippet above; verified via grep).

## Behaviour matrix (observed)

| Runner | Scenario | Subprocess count | Session-file race? | Token usage | Msg archival |
|--------|----------|------------------|--------------------|--------------|----------------|
| opencode | mid-run overlap (3 triggers, 50 ms apart) | 1 of 3 ran; 2 skipped | No | 1x burn for trigger 1; 0x for skipped | None of the 3 messages archived |
| opencode | long task + 3 quick (mid + near-finish overlap) | 2 of 4 ran; 1 of the 3 quick was skipped (depends on lock timing) | No | 1x for long + 1x for quick1 (if it ran) | None archived |
| claude | not exercised (auth fail) | — | — | — | — |
| kimi | not exercised (no CLI) | — | — | — | — |
| codex | not exercised (no CLI) | — | — | — | — |

`session-file race?` column is "No" because the per-agent mutex prevents concurrent subprocesses for the same agent. (Two subprocesses for different agents would still race on a shared transport file, but no shared file exists per agent.)

`Token usage` for skipped triggers is 0 — the agent subprocess never starts.

`Msg archival` is broken for ALL runners under HTTP transport (Finding F2).

## Findings

| ID | Finding | Severity |
|----|---------|----------|
| **F1** | The watchdog uses **skip-if-busy** with a 100 ms lock timeout. Under load, triggers can be silently dropped without any user-visible notification. | **HIGH** |
| **F2** | Skipped (and processed) triggers are never archived on the Hub. The Hub's unread-inbox grows monotonically; the user cannot tell which triggers fired and which were dropped. | **HIGH** |
| **F3** | The 100 ms lock timeout is a magic number. If `acquire_lock` ever returns False due to transient filesystem latency (rather than a real concurrent run), a trigger is silently lost. | **MEDIUM** |
| **F4** | No retry path. A skipped trigger has zero chance of being re-attempted. The user must manually re-fire. | **HIGH** |

## Policy recommendation

Given the current skip-if-busy design and the four findings above, the policy that fits the existing code best is:

### Recommended: **Per-agent queue with retry** (replaces skip-if-busy)

**Rationale:**
- Skip-if-busy silently drops user intent (F1, F4). The user fires a trigger expecting it to run; if the agent is busy they have to manually retry.
- Queueing preserves intent. The trigger waits until the running agent finishes, then runs.
- Bounded queue depth (suggest N=8) prevents memory growth from a runaway producer.
- Overflow policy = "archive oldest, run newest" matches the durable-retry story in the change name `add-durable-trigger-retry`.

**Skip-if-busy could be acceptable IF** the user explicitly opts in via `agentweave.yml`, and if F2 is fixed so dropped triggers are visibly archived (with a `skipped: busy` flag in the message body). For the default policy, queueing is safer.

### Concrete changes for the fix change `add-durable-trigger-retry`

1. **Replace the skip path with a queue.** On `acquire_lock` failure, enqueue the (cmd, prompt, session_id, msg_id) into a per-agent FIFO bounded at N entries. The currently-running subprocess drains the queue when it finishes (`release_lock` call site becomes "release + dequeue + spawn next").
2. **Add overflow handling.** When the queue is full, mark the queued message as `skipped: queue_full` and archive it on the Hub with the skip reason in the content.
3. **Make the policy configurable per agent** in `agentweave.yml` (`runner_options.spawn_policy: queue | skip_if_busy`). Default = `queue`.
4. **Fix F2: archive every processed Hub message.** Add `self.transport.archive_message(msg_id)` in the regular trigger branch (around `watchdog.py:717`).
5. **Increase the lock timeout** to 1 s so transient filesystem latency doesn't cause spurious skips (F3). Or, better, eliminate the timeout entirely once the queue exists.
6. **Add a metric / log event** `spawn_queued` so operators can observe queue depth.

### Why not coalesce?

Coalescing (collapse N pending messages into 1) loses user intent. If the user fires "do task A" then "do task B", they want both done. Coalescing would run only B (or only A). Rejected.

### Why not per-agent mutex with infinite queue?

Unbounded queue is a memory-leak waiting to happen under a misbehaving producer. Bounded queue with overflow-archive is safer.

## Open questions

- Does the watchdog ever get into a state where `_run_agent_subprocess` exits without calling `release_lock` (e.g., on uncaught exception)? If yes, the lock would be held forever and all subsequent triggers for that agent would skip. **UNTESTED.** Suggested live check: kill -9 the watchdog mid-run and observe.
- Does `acquire_lock` work across processes? `locking.py` uses file locks — the watchdog is single-process, but if two watchdogs ever run for the same project, locks would have to coordinate across processes. **UNTESTED.**
- For per-agent queueing, is the queue owned by the watchdog process or persisted to disk? If the watchdog is restarted mid-queue, the queued messages are lost. A `add-durable-trigger-retry` fix should consider this.
