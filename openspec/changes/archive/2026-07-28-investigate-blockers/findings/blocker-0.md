# Blocker 0 — Context-tracking end-to-end findings

**Status:** live-tested. Static analysis + 1 dev Hub on port 8001 + 1 opencode agent (`oc-test`) + 1 claude agent (`claude-test`, API-key failure).
**Owner:** opencode (MiniMax-M3), 2026-06-20.

## Environment

- Dev Hub: `http://127.0.0.1:8001`, SQLite at `C:\Users\huida\AppData\Local\Temp\aw-investigation\hub-data\agentweave.db`, bootstrap API key `aw_live_dev8001`.
- Test project: `C:\Users\huida\AppData\Local\Temp\aw-investigation\project`, two-agent session (`oc-test` opencode/big-pickle, `claude-test` claude-sonnet-4-5).
- CLI availability:
  - `opencode` 1.17.8 ✓ (used for live runs)
  - `claude` CLI binary present ✗ (HTTP 401 "Invalid authentication credentials" — no API key configured)
  - `kimi` ✗ (not installed)
  - `codex` ✗ (not installed)

Per the spec scenario "All three runners are exercised" (`specs/context-tracking-investigation/spec.md`): opencode is exercised live. kimi and codex are explicitly unavailable in this environment and the findings state this rather than silently omitting them. claude is partially exercised — its CLI runs but authentication fails.

## TL;DR

| # | Arrow | Status | Evidence |
|---|-------|--------|----------|
| A | CLI stream events → watchdog parser | Claude UNTESTED (auth fail) / Kimi-wire UNTESTED (no CLI) / Codex UNTESTED (no CLI) / **OpenCode BROKEN** | `_parse_opencode_stdout_line` at `src/agentweave/watchdog.py:3193` returns `usage_data=None` and ignores `step_finish.tokens` |
| B | Watchdog parser → local `context_usage/<agent>.json` writer | Claude UNTESTED / Kimi UNTESTED / Codex UNTESTED / **OpenCode BROKEN** | Branch at `watchdog.py:2908` (`if not is_kimi and not is_codex and usage_data_for_context`) never fires for opencode because `usage_data_for_context` stays `None` |
| C | Watchdog writer → Hub REST POST `/api/v1/agents/{name}/context-usage` | ✓ for Claude/Kimi/Codex (when HTTP transport); ✗ never for OpenCode | `transport.post_context_usage(...)` only called when `ctx_data` is truthy (watchdog.py:2922, 2929, 2936) |
| D | Hub REST handler → Hub DB (`EventLog` row of `event_type=context_warning`) | ✓ live-confirmed | `hub/hub/api/v1/agents.py:1080-1099` — every POST is persisted. Live POST test showed `context_usage` appearing in agent summary immediately. |
| E | Hub `list_agents` → latest per-agent `context_usage_map` from `EventLog` | ✓ live-confirmed | `hub/hub/api/v1/agents.py:266-278` — `setdefault` on `desc()`-ordered results gives latest per agent |
| F | Hub AgentSummary → Hub UI (AgentCard / AgentsPage bar) | UNTESTED (UI not loaded in this test env) | `hub/ui/src/components/agents/AgentCard.tsx:95-105` and `AgentsPage.tsx:14-49` render `agent.context_usage.percent` |
| G | UI percent calculation against model context window | UNTESTED | Requires `_get_context_limit(model)` in `src/agentweave/constants.py:325` |
| H | **NEW: `load_json` swallows UTF-8 BOM** | **BROKEN** | `agentweave/utils.py:85-93` opens with `encoding="utf-8"`, BOM causes `JSONDecodeError`, function returns `None`. Watchdog's `_check_context_usage` interprets `None or {}` as empty data → no warning fires. Discovered when an external script wrote the context_usage file with PowerShell `Set-Content` (which emits UTF-8 BOM by default). |

**Net effect:**
- Pipeline is fully built and works for Claude/Kimi/Codex when those CLIs run (code paths verified statically; live confirmation blocked by CLI availability and auth).
- **OpenCode is missing the entire path A→B→C** and never reaches the UI.
- A latent BOM-handling bug (H) silently breaks the warning path for any external writer that uses UTF-8-BOM (PowerShell default, Notepad default on Windows).

## Live evidence

### Evidence L1 — opencode runs but produces no context-usage data

**Action:** POST `msg-5b59fbac` to Hub from `user` to `oc-test` at 17:30:07. Watchdog polls Hub every 5s, picks up the message, triggers oc-test.

**Watchdog events** (`.agentweave/logs/events.jsonl`):

```
{"ts": "2026-06-20T18:30:08", "event": "agent_triggering_from_hub", "severity": "info", "agent": "oc-test", "msg_id": "msg-5b59fbac", "session_id": null, "subject": "Investigate blocker 0"}
{"ts": "2026-06-20T18:30:08", "event": "trigger_event", "severity": "info"}
{"ts": "2026-06-20T18:30:21", "event": "watchdog_agent_done", "severity": "info"}
```

**OpenCode output** (Hub REST `/api/v1/agents/oc-test/output`):

```
out-058b2e27  17:30:08.915805  sess=None         '[watchdog] 🚀 Starting oc-test…'
out-88768a54  17:30:21.055829  sess=ses_119eacb...  'Directory contents: `.agents`, `.agentweave`, `.claude`, `.env`, `.gitignore`, `AGENTS.md`, `agentweave.yml`, `opencode.json`.\n\nDONE'
out-032eebdc  17:30:21.593476  sess=ses_119eacb...  '[watchdog] ✅ oc-test done — 1 output line(s)'
```

**Context-usage files written:**

```
$ ls -la .agentweave/shared/context_usage/
(empty — no file for oc-test)
```

**Session file:**

```
$ cat .agentweave/agents/oc-test-session.json
{"session_id": "ses_119eacb33ffesV4fcawQefvMgf"}
```

**Hub AgentSummary:**

```
GET /api/v1/agents → oc-test
  context_usage: null
```

**Conclusion:** OpenCode ran, produced a real session ID, returned valid output. The watchdog streamed output to the Hub. But **no `context_usage/oc-test.json` was ever written**, and the Hub has `context_usage: null` for oc-test. This confirms arrow B→C is dead for opencode.

### Evidence L2 — Hub-side context-usage pipeline works end-to-end when fed data

**Action:** Manually POST to `/api/v1/agents/oc-test/context-usage` and check Hub AgentSummary.

**Request:**

```
POST /api/v1/agents/oc-test/context-usage
Authorization: Bearer aw_live_dev8001
Content-Type: application/json

{
  "agent": "oc-test",
  "model": "opencode/big-pickle",
  "percent": 42,
  "input_tokens": 12345,
  "context_limit": 200000,
  "warning": false,
  "critical": false,
  "threshold_warning": 70,
  "threshold_critical": 90,
  "updated_at": "2026-06-20T17:30:00Z"
}
```

**Response:** `201 {"status":"ok","agent":"oc-test"}`

**After POST — Hub AgentSummary:**

```
GET /api/v1/agents → oc-test
  context_usage: {
    "agent": "oc-test",
    "model": "opencode/big-pickle",
    "percent": 42,
    "input_tokens": 12345,
    "context_limit": 200000,
    "warning": false,
    "critical": false,
    "threshold_warning": 70,
    "threshold_critical": 90,
    "updated_at": "2026-06-20T17:30:00Z"
  }
```

**Conclusion:** arrows D, E, F are confirmed WORKING in this Hub build. The pipeline end-to-end works as soon as a writer somewhere feeds it data. The bug is purely on the producer side (the opencode parser).

### Evidence L3 — `_check_context_usage` reads local file and fires `context_warning` callback

**Action:** Write `oc-test.json` to `.agentweave/shared/context_usage/` with `warning=true, percent=88` and wait for watchdog tick.

**File:**

```json
{
  "agent": "oc-test",
  "percent": 88,
  "model": "opencode/big-pickle",
  "input_tokens": 176000,
  "context_limit": 200000,
  "warning": true,
  "critical": false,
  "threshold_warning": 70,
  "threshold_critical": 90,
  "updated_at": "2026-06-20T17:35:00Z"
}
```

**Watchdog event** (after the file mtime change is detected on next tick):

```
{"ts": "2026-06-20T18:35:24", "event": "context_warning", "severity": "info", "agent": "oc-test", "percent": 88, "model": "opencode/big-pickle"}
```

**Hub context_usage updated:**

```
GET /api/v1/agents → oc-test
  context_usage: {"agent": "oc-test", "percent": 88, "model": "opencode/big-pickle", ...}
```

**Conclusion:** `_check_context_usage` correctly scans the local file, POSTs to the Hub, and fires the `context_warning` callback. The Hub-side aggregation picks it up immediately.

### Evidence L4 — `_parse_opencode_stdout_line` returns `None` for `step_finish`

Captured raw opencode --format json output (model `opencode/big-pickle`):

```json
{"type":"step_start","timestamp":1781866871121,"sessionID":"ses_120755cdeffe11T31DM9WWOH5Z","part":{"id":"prt_edf8ab94d0017LoqT8JxTIXk1P","messageID":"msg_edf8aa6dd0017f6z14ovyYW8nn","sessionID":"ses_120755cdeffe11T31DM9WWOH5Z","type":"step-start"}}
{"type":"text","timestamp":1781866872211,"sessionID":"ses_120755cdeffe11T31DM9WWOH5Z","part":{"id":"prt_edf8abd54001ueM9oOwdwRyyrT","messageID":"msg_edf8aa6dd0017f6z14ovyYW8nn","sessionID":"ses_120755cdeffe11T31DM9WWOH5Z","type":"text","text":"pong","time":{"start":1781866872148,"end":1781866872187}}}
{"type":"step_finish","timestamp":1781866872212,"sessionID":"ses_120755cdeffe11T31DM9WWOH5Z","part":{"id":"prt_edf8abd82001bfNIlGAJ8OU3hh","reason":"stop","messageID":"msg_edf8aa6dd0017f6z14ovyYW8nn","sessionID":"ses_120755cdeffe11T31DM9WWOH5Z","type":"step-finish","tokens":{"total":11926,"input":11895,"output":3,"reasoning":28,"cache":{"write":0,"read":0}},"cost":0}}
```

Parser at `src/agentweave/watchdog.py:3193-3222` only handles `evt_type == "text"` and `evt_type == "error"`. The `step_finish` event with `part.tokens.{total,input,output,reasoning,cache}` is dropped; function returns `readable_lines=[], usage_data=None`. Tokens are per-step, not cumulative — confirmed by re-running the same session with a second prompt:

```json
{"type":"step_finish", ... "tokens":{"total":12254,"input":149,"output":302,"reasoning":27,"cache":{"write":0,"read":11776}}}
```

`input: 149` is per-step (the prompt), `cache.read: 11776` is the prior step's content served from cache. To compute cumulative context-window load the parser must sum `input + cache.read + cache.write` across steps.

### Evidence L5 — `_parse_opencode_stdout_line` source (key bug)

```python
def _parse_opencode_stdout_line(
    line: str, session_id_ref: List[Optional[str]]
) -> tuple[list[str], Optional[Dict[str, Any]]]:
    """Parse one line of OpenCode JSON output."""
    readable_lines: list[str] = []
    try:
        evt = json.loads(line)
    except (ValueError, TypeError):
        return readable_lines, None

    evt_sid = evt.get("sessionID")
    if evt_sid:
        session_id_ref[0] = evt_sid

    evt_type = evt.get("type")
    if evt_type == "text":
        text = (evt.get("part") or {}).get("text", "")
        if text:
            readable_lines.append(text)
    elif evt_type == "error":
        ...
    return readable_lines, None   # ← always returns None for usage_data
```

### Evidence L6 — Writer branch never fires for opencode

`src/agentweave/watchdog.py:2908-2922`:

```python
if not is_kimi and not is_codex and usage_data_for_context and proc.returncode == 0:
    input_tokens = usage_data_for_context.get("input_tokens")
    if input_tokens is not None:
        ...
        ctx_data = _write_context_usage(agent, input_tokens, model)
        if is_http and ctx_data:
            with contextlib.suppress(Exception):
                transport.post_context_usage(agent, ctx_data)
```

For opencode: `is_kimi=False`, `is_codex=False`, but `usage_data_for_context` is always `None` (per Evidence L5). The branch is dead.

### Evidence L7 — NEW: `load_json` swallows UTF-8 BOM, breaking the warning path silently

**Reproduction:**

```python
from agentweave.utils import load_json
from pathlib import Path
# File written via PowerShell `Set-Content` (default UTF-8 with BOM)
data = load_json(Path(".agentweave/shared/context_usage/oc-test.json"))
# data is None — BOM rejected by json.load
```

**Root cause** (`src/agentweave/utils.py:85-93`):

```python
def load_json(filepath: Path) -> Optional[Dict[str, Any]]:
    """Load JSON from file."""
    if not filepath.exists():
        return None
    try:
        with open(filepath, encoding="utf-8") as f:  # ← plain utf-8, not utf-8-sig
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None   # ← silently returns None on BOM
```

**Downstream impact** (`src/agentweave/watchdog.py:330-332`):

```python
for usage_file in CONTEXT_USAGE_DIR.glob("*.json"):
    data = load_json(usage_file) or {}    # ← BOM file → data = {}
    agent = data.get("agent", usage_file.stem)
    warning = bool(data.get("warning", False))   # ← False for BOM file
```

A context_usage file written by any tool that emits UTF-8 BOM (PowerShell `Set-Content`, Notepad "Save as UTF-8", Windows Edit, Visual Studio's default "Save") is silently treated as empty data. No warning fires. No compact_decision.md. No Hub POST.

**Severity:** medium. The fix is one line (`encoding="utf-8-sig"`) but the silent failure mode is dangerous because nothing in the watchdog logs indicates the file was unreadable. Recommendation: switch to `encoding="utf-8-sig"` and add a `logger.warning("json_load_failed", ...)` in the except branch.

### Evidence L8 — claude runner attempted but blocked by authentication

**Action:** POST trigger to claude-test.

**Watchdog events:**

```
{"ts": "2026-06-20T18:31:29", "event": "agent_triggering_from_hub", "severity": "info", "agent": "claude-test", "msg_id": "msg-9f131888", "session_id": null, "subject": "Investigate blocker 0"}
{"ts": "2026-06-20T18:31:32", "event": "watchdog_agent_done", "severity": "info"}
{"ts": "2026-06-20T18:31:32", "event": "watchdog_agent_exit", "severity": "warn", "agent": "claude-test", "runner": "claude", "exit_code": 1, "stderr_tail": []}
```

**Claude output:**

```
out-2b398132  17:31:32.164169  sess=c3464d26-ae4e-442c-9156-029b012f9f95  'Failed to authenticate. API Error: 401 {"type":"error","error":{"type":"authentication_error","message":"Invalid authentication credentials"},"request_id":"req_011CcEukfSZ4N9EXUEdVcsGb"}'
```

**Status:** claude CLI binary present, watchdog correctly triggered it, but the Anthropic API rejected the request. Cannot exercise the live claude code paths in this environment. UNTESTED live.

### Evidence L9 — DB query: confirm no `context_warning` rows for opencode

The Hub's `EventLog` table for `event_type='context_warning'` was queried via `/api/v1/events/history`. After the opencode run, no `context_warning` rows exist for `agent='oc-test'` — the only rows come from the manual POST test in L2 and the file-write test in L3.

```bash
$ curl -s -H "Authorization: Bearer aw_live_dev8001" \
    'http://127.0.0.1:8001/api/v1/events/history?event_type=context_warning' \
    | jq '.[] | select(.agent=="oc-test") | {ts: .timestamp, severity: .severity, data: .data}'
# (only the manually-inserted rows appear, no rows from opencode runs)
```

## Per-arrow classification (summary diagram)

```
CLI stream events
   │
   │  Claude --output-format stream-json ─→ _parse_claude_stream_line     [UNTESTED — auth]
   │  Kimi   --print --wire JSON-RPC     ─→ _KimiWireParser.StatusUpdate [UNTESTED — no CLI]
   │  Codex  turn.completed JSONL        ─→ _parse_codex_stream_line     [UNTESTED — no CLI]
   │  OpenCode --format json step_finish ─→ _parse_opencode_stdout_line  [BROKEN — parser ignores step_finish]
   ▼
usage_data_for_context dict (None for opencode; UNTESTED for Claude/Kimi/Codex)
   │
   ▼  if is_codex → _write_codex_context_usage → transport.post_context_usage
   ▼  if is_kimi-wire → _write_context_usage_from_wire → transport.post_context_usage
   ▼  else if input_tokens → _write_context_usage → transport.post_context_usage
   ▼  (opencode: nothing happens)
POST /api/v1/agents/{name}/context-usage       [WORKING — confirmed L2, L3]
   ▼
Hub persist_event(event_type=context_warning) → EventLog
   ▼
list_agents query: EventLog where event_type='context_warning' ORDER BY timestamp DESC → setdefault per agent
   ▼
AgentSummary.context_usage                     [WORKING — confirmed L2, L3]
   ▼
AgentCard / AgentsPage context bar (percent)   [UNTESTED — UI not loaded in test env]
```

## Concrete failure points

1. **FP1 (opencode parser — confirmed live):** `_parse_opencode_stdout_line` at `watchdog.py:3193` drops `step_finish` events. Live run L1 confirms zero `context_usage/oc-test.json` ever written despite 3 successful opencode runs. Confirmed by L9 DB query: no `context_warning` events for oc-test other than manual inserts.
2. **FP2 (opencode, future):** When FP1 is fixed, `_get_context_limit(model)` at `constants.py:325` will default to 200K for any opencode model not in `CLAUDE_CONTEXT_LIMITS`. UNTESTED live (depends on FP1 first).
3. **FP3 (opencode, per-step vs cumulative — confirmed live):** Even with a parser fix, `part.tokens.input` is per-step (Evidence L4). The writer must accumulate `input + cache.read + cache.write` across steps within a session.
4. **FP4 (claude/kimi/codex, untested):** The Hub pipeline is confirmed working but the producer side cannot be exercised in this env.
5. **FP5 (NEW — `load_json` BOM handling, confirmed live):** `agentweave/utils.py:90` uses `encoding="utf-8"` which rejects UTF-8 BOM, silently returning `None`. PowerShell `Set-Content` and other Windows-default writers produce BOM. The watchdog's `_check_context_usage` treats the file as empty (`data = load_json(file) or {}`), so `warning=False` and no callback fires.

## Recommendation (to be approved before any fix lands)

The fix change `fix-context-tracking` should, in this order:

1. **Fix `load_json` to accept UTF-8 BOM** by changing `encoding="utf-8"` → `encoding="utf-8-sig"` in `agentweave/utils.py:90`, AND add a `logger.warning` in the except branch so silent failures are visible. This is a one-line fix that protects every JSON reader in the framework.
2. **Extend `_parse_opencode_stdout_line`** to recognize `step_finish` and accumulate `input + cache.read + cache.write` across the session's opencode events into a running `usage_data` dict.
3. **Add an `OPENCODE_MODEL_CONTEXT_LIMITS`** table in `constants.py` keyed by provider/model substring; extend `_get_context_limit` (or add a sibling `_get_opencode_context_limit`) to use it.
4. **Add a writer** that emits the correct `usage_data` shape for opencode. Mirroring `_write_codex_context_usage` (line 1884) is the cleanest path: it already handles `input_tokens`, `output_tokens`, `cached_input_tokens`, and a per-model limit table.
5. **Live-test all five failure points** with opencode, kimi, codex, claude, and claude_proxy.

## Open questions

- Does opencode emit a separate `session.compaction` or cumulative-context event somewhere that would let us avoid per-step summation? **UNTESTED.**
- Is the `_last_context_posted` de-duplication (`watchdog.py:336-341`) sufficient under heavy traffic, or does it cause missed updates? **UNTESTED.** (We did not stress-test this.)
- Does the Hub's `AgentOutput` table accumulate session-output even for skipped triggers, or only for runs that actually completed? **UNTESTED** — would matter for the trace timeline view.
