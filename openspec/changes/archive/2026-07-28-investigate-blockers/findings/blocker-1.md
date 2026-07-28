# Blocker 1 — Forced-reset behaviour findings

**Status:** live-tested partially. Cooperative path exercised in-process (the watchdog's HTTP polling branch never fires it — see Finding F1 below). Force-kill path confirmed absent by code search + absence of any signal-sending call site in the agent subprocess path.
**Owner:** opencode (MiniMax-M3), 2026-06-20.

## TL;DR

- **Cooperative reset path is implemented** for `local` / `git` transports: `compact_decision.md` is written by `_write_compact_decision` (`watchdog.py:548`); user marks `[x]`; watchdog polls and sends an inbox message via `MessageBus.send` (`watchdog.py:587`).
- **NEW FINDING F1 — Cooperative reset is DEAD under HTTP transport.** `_check_once_http` (`watchdog.py:686`) does NOT call `_check_compact_decision`. Only `_check_once_local` (`watchdog.py:319-320`) does. **The Hub polling path skips the entire cooperative-reset workflow.** Live confirmed in this investigation.
- **Force-kill path does NOT exist.** No code anywhere sends SIGTERM or SIGKILL to a running agent subprocess. Live + static confirmation.
- **Worktree hygiene** (per spec): AgentWeave does not use git worktrees; "recoverable worktree" maps to "project working tree not corrupted." A force-killed process leaves in-progress edits on disk (kernel flushes dirty pages on SIGKILL), so tracked-file content is recoverable by design — UNTESTED live.

## Live evidence

### Evidence L1 — `_write_compact_decision` works in isolation

**Action:** Instantiate `Watchdog.__new__(Watchdog)` to bypass `__init__`, call `_write_compact_decision(data)` directly with `{agent: oc-test, percent: 88, model: opencode/big-pickle, threshold_warning: 70}`.

**Result:**

```
file: C:\Users\huida\AppData\Local\Temp\aw-investigation\project\.agentweave\shared\compact_decision.md
exists: True
```

**Content:**

```
# Context Decision Required — oc-test — 2026-06-20T18:01:06Z

Agent **oc-test** (opencode/big-pickle) has reached **88%** context utilization.
Recommended action threshold for this model: 70%.

Run `/aw-checkpoint` in oc-test's session first, then choose one action below.

## Choose one action

- [ ] **Compact** — agent writes checkpoint, then runs /compact and resumes
- [ ] **New Session** — agent writes checkpoint, then you start a fresh session
- [ ] **Continue** — skip this warning; next alert at 90%

Mark one option with [x] and save this file. The watchdog will notify the agent.
```

**Conclusion:** the writer itself is correct. (Encoding shows mojibake in PowerShell `Get-Content` but the file is UTF-8; the `—` em-dash renders correctly when read as UTF-8.)

### Evidence L2 — `_check_once_http` does NOT call `_check_compact_decision` (NEW FINDING)

**Action:** Mark `[x] **Compact**` in the `compact_decision.md` written in L1, restart the watchdog against the dev Hub (HTTP transport), wait 60 seconds.

**Watchdog events** (filtered for "compact" / "Context:"):

```
(none)
```

**Hub inbox for oc-test after 60 s:**

```
GET /api/v1/messages?to=oc-test → 1 messages
  msg-9f131888 read=False from=user subject='Investigate blocker 0'
```

No "Context: please compact now" message was sent. **The compact decision polling did not fire.**

**Root cause** — `src/agentweave/watchdog.py`:

```python
# _check_once_local (line 256-324) — DOES call:
self._check_context_usage()
self._check_compact_decision()       # line 320

# _check_once_http (line 686-727) — does NOT:
def _check_once_http(self) -> None:
    """Poll Hub REST API for new messages and tasks."""
    # Context files are always local, even when using HTTP transport
    self._check_context_usage()       # line 689 — only this one
    ...
```

The HTTP polling path is missing the `self._check_compact_decision()` call entirely. **Any user using the Hub cannot trigger a reset via `compact_decision.md`** — the file is written, but no one reads it.

**Severity:** HIGH. The cooperative reset workflow is the primary reset mechanism in production (the only one), and it's silently broken under HTTP transport — which is the recommended transport per the project's own docs.

**Suggested fix:** add `self._check_compact_decision()` immediately after `self._check_context_usage()` in `_check_once_http`.

### Evidence L3 — Force-kill path does NOT exist

`grep -n "SIGTERM\|SIGKILL\|proc\.terminate\|proc\.kill\|os\.kill" src/agentweave/*.py`:

| File | Line | What it kills |
|------|------|---------------|
| `src/agentweave/cli.py` | 1706 | Sibling **watchdog** daemons during `cmd_stop` |
| `src/agentweave/cli.py` | 1811 | The **watchdog daemon** during `cmd_stop` |
| `src/agentweave/watchdog.py` | 2000 / 2004 | The **codex MCP server** subprocess during `_CodexMcpClient.close()` |
| `src/agentweave/diagnostics.py` | 470 | PID existence check (`kill(pid, 0)`), not a kill |
| `src/agentweave/cli.py` | 683 | PID existence check |
| `src/agentweave/cli.py` | 3337 | PID existence check |

**There is no code path that terminates a running agent subprocess in response to a context-pressure event.** The agent process is spawned via `subprocess.Popen` inside `_run_cmd` (`watchdog.py:2752`+) and runs to natural completion. The watchdog waits on `proc.wait()` (`watchdog.py:2897`) with no timeout.

If the agent ignores the `/aw-checkpoint` instruction and keeps running with high context, the only escape hatches are:

1. The agent eventually exits on its own.
2. The user manually kills the agent process from outside the watchdog.

**Live confirmation:** during the Blocker 2 experiments we fired 3 concurrent triggers to oc-test; trigger 1 ran a 16-second task; triggers 2 and 3 were SKIPPED (see blocker-2.md Evidence L1). The watchdog did not attempt to interrupt trigger 1's run — it just waited it out.

### Evidence L4 — Cooperative path wall-clock times (single data point, opencode)

**Action:** Mark `[x] **Compact**`, restart watchdog, observe the path from file mark → inbox message.

**Result:** not exercised, because the HTTP polling branch never reads the file (Finding F1). Cannot measure wall-clock under HTTP transport.

**Static-path-only estimate:** if Finding F1 is fixed, the watchdog's 5-second poll interval is the lower bound on detection latency. From "user marks `[x]`" to "watchdog reads file" is up to 5 s. From "watchdog reads file" to "agent receives inbox message" is sub-second (synchronous POST + MessageBus.send). Agent reaction time depends entirely on the runner; opencode typically polls its inbox at session start only, so the cooperative path effectively requires the agent to start a new turn to see the message.

### Evidence L5 — Worktree / dirty-state recovery (untested live)

`grep -rn "worktree" src/agentweave/`: no matches. AgentWeave does not use git worktrees for per-agent isolation.

A SIGKILL on a Linux process leaves dirty pages flushed to disk; on Windows the kernel flushes modified file mappings on process termination. Uncommitted edits to tracked files are preserved as `git diff` output. UNTESTED in this investigation (no live SIGKILL was performed).

## Findings summary

| ID | Finding | Severity |
|----|---------|----------|
| **F1** | `_check_once_http` skips `_check_compact_decision` → cooperative reset is dead under HTTP transport. Live-confirmed. | **HIGH** |
| **F2** | No force-kill path (SIGTERM/SIGKILL) for agent subprocesses. Confirmed by code search + live observation (watchdog waits out long tasks). | **HIGH** |
| **F3** | `load_json` rejects UTF-8 BOM (see blocker-0.md FP5) → context_warning path silently fails for any file written by PowerShell/Notepad. Indirect impact: `compact_decision.md` never gets written if context_usage file has a BOM. | **MEDIUM** (duplicate of blocker-0 FP5) |

## Recommendation (to be approved before any fix lands)

The fix change `add-auto-reset-mode` should, in this order:

1. **Fix F1 first.** Add `self._check_compact_decision()` to `_check_once_http` immediately after `self._check_context_usage()` (`watchdog.py:689`). This single line restores cooperative reset under HTTP transport.
2. **Add a force-kill escalation** in `_do_run_agent_subprocess` (`watchdog.py:2602+`): when a `compact_request` or `new_session_request` is pending for this agent's session, after T1 seconds send `proc.terminate()` (SIGTERM), after T2 more seconds send `proc.kill()` (SIGKILL).
3. **Wire T1 and T2 to be configurable per runner.** Defaults informed by live measurements: opencode ~11 s for a 500-word essay (blocker-2.md Evidence L1); claude variable; codex/kimi unmeasured.
4. **Make the cooperative-path grace window the user-facing knob** (T1 = "how long to wait for /aw-checkpoint before SIGTERM").
5. **Fix F3** (load_json BOM) as part of this change, since it blocks cooperative reset end-to-end.
6. **Live-test all of the above** with opencode, kimi, codex, claude before shipping. The investigation's live wall-clock data is insufficient — the agents that actually exercise the cooperative path (Claude with `/aw-checkpoint` skill loaded, Kimi with skill loaded, Codex with skill loaded) were not all exercisable in this env.

Specific grace windows are NOT recommended yet — live data is required across all runners.
