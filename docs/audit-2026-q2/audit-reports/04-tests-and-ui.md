# Audit Report 04 — Tests & Hub UI

**Scope:** CLI tests, Hub tests, Hub UI (React/TypeScript)
**Date:** 2026-06-12
**Auditor:** opencode (MiniMax-M3) via Task tool, subagent_type=explore
**Method:** Read whole files, cross-reference coverage matrix, identify stale closures, security issues, and performance problems.

## Files in scope

### Tests
- CLI: `C:\Users\huida\Documents\projects\AgentWeave\tests\*.py` (26 files)
- Hub: `C:\Users\huida\Documents\projects\AgentWeave\hub\tests\*.py`
- Makefile targets: `make test-all`, `make test`

### Hub UI (React/TypeScript)
- `C:\Users\huida\Documents\projects\AgentWeave\hub\ui\src\`
- Components in `components/`, `pages/`, `api/`, `hooks/`, `store/`

---

## Test coverage matrix

### CLI tests (`tests/`)

| Source file | Test file | Coverage quality |
|---|---|---|
| `src/agentweave/cli.py` | `test_activate.py`, `test_cli.py`, `test_cli_pilot.py`, `test_hub_commands.py`, `test_init.py` | partial — activate/init/integration, but no tests for many `cmd_*` helpers (`cmd_run`, `cmd_relay`, `cmd_status`, `cmd_logs`, `cmd_mcp_serve`, `cmd_doctor` non-redaction path, etc.) |
| `src/agentweave/config.py` | `test_config.py` | good |
| `src/agentweave/constants.py` | `test_constants.py` | good |
| `src/agentweave/context_builder.py` | `test_context_builder.py` | good |
| `src/agentweave/diagnostics.py` | `test_diagnostics.py` | partial — proxy key / heartbeat / injection / staleness paths, no tests for `cmd_doctor` happy path or any `check_*` negative branches |
| `src/agentweave/eventlog.py` | **none** | none |
| `src/agentweave/jobs.py` | `test_jobs.py` | partial — covers validation/persistence/should_fire/record_run, **no scheduler integration tests** |
| `src/agentweave/locking.py` | `test_locking.py` | partial — only sequential, no concurrent test |
| `src/agentweave/logging_handlers.py` | **none** | none |
| `src/agentweave/messaging.py` | `test_messaging.py` | partial — happy path only, no error/edge cases (malformed content, invalid type, recipient not in session) |
| `src/agentweave/roles.py` | `test_roles.py` | good |
| `src/agentweave/runner.py` | **none** | none |
| `src/agentweave/session.py` | `test_session.py` | partial — covers `sync_agents` for runner_options/model, no tests for `add_completed_task`, `add_active_task`, JSON corruption recovery |
| `src/agentweave/task.py` | `test_task.py` | partial — CRUD only, no `update` validation, no transition rules |
| `src/agentweave/utils.py` | `test_utils.py` | good |
| `src/agentweave/validator.py` | `test_validator.py` | good |
| `src/agentweave/watchdog.py` | `test_watchdog.py`, `test_watchdog_pilot.py`, `test_watchdog_self_registered.py`, `test_watchdog_session.py` | good |
| `src/agentweave/transport/base.py` | **none** (ABC) | n/a |
| `src/agentweave/transport/config.py` | **none** | none |
| `src/agentweave/transport/git.py` | **none** | none — entirely untested, high risk |
| `src/agentweave/transport/http.py` | `test_http_transport.py` | partial — happy + URLError, no 4xx/5xx, no timeout, no malformed JSON, no `HubTransportError` paths (the `classification` field is never asserted in the http transport test) |
| `src/agentweave/mcp/server.py` | `test_mcp_server.py` | partial — tests `register_agent`, `update_agent_config`, `get_context`, `get_agent_context`, `heartbeat`. **Does not test the 11 Hub MCP server tools** in `hub/hub/mcp_server.py` (which is a separate file) |

### Hub tests (`hub/tests/`)

| Source file | Test file | Coverage quality |
|---|---|---|
| `hub/hub/auth.py` | `test_auth.py` | partial — 3 happy/sad path tests only, no rate-limiting, no revoked-key path, no test that the `?token=` query-param path is actually accepted |
| `hub/hub/config.py` | **none** | none |
| `hub/hub/main.py` | indirect only | none |
| `hub/hub/mcp_server.py` | **none** | none — the 11 MCP tools have zero direct test coverage |
| `hub/hub/scheduler.py` | `test_runtime_diagnostics.py` (only the failure path) | none — happy-path scheduler is untested |
| `hub/hub/sse.py` | `test_sse.py` | partial — 2 tests, no backpressure, no multi-project fan-out, no slow-consumer / `QueueFull` test |
| `hub/hub/utils.py` | **none** | none |
| `hub/hub/api/v1/agents.py` | `test_agents_self_registered.py`, `test_pilot_mode.py`, `test_tasks.py` (assignee count), `test_runtime_diagnostics.py` (logs/agents), `test_setup.py` | partial — covers register/patch/pilot/timeline/context paths. No tests for `compact`, `new-session`, `register-session` body validation, `context-usage` endpoint, `configured` endpoint, or `roles/config` GET |
| `hub/hub/api/v1/agent_chat.py` | **none** | none — the file AGENTS.md flags as bug-prone is entirely untested |
| `hub/hub/api/v1/agent_trigger.py` | `test_pilot_mode.py`, `test_runtime_diagnostics.py` | partial — only the watchdog-heartbeat branches, no test of the `[NewSession]`/`[Session: <id>]` tag generation, no test of pilot-vs-manual vs stale interaction |
| `hub/hub/api/v1/events.py` | `test_sse.py` (manager only, not endpoint) | none — `event_history` and `event_stream` endpoints untested |
| `hub/hub/api/v1/instructions.py` | `test_instructions.py` | good |
| `hub/hub/api/v1/jobs.py` | `test_runtime_diagnostics.py` (only failure path) | none — happy-path CRUD, pause/resume/run/delete untested |
| `hub/hub/api/v1/logs.py` | `test_runtime_diagnostics.py` (1 test) | none — no filter tests, no agent filter |
| `hub/hub/api/v1/messages.py` | `test_messages.py` | partial — happy path only, no test for `mark read` 404, no conversation filter, no history sort |
| `hub/hub/api/v1/questions.py` | `test_questions.py` | partial — happy path only, no test for answer-without-question, no test for `answered` filter |
| `hub/hub/api/v1/session_sync.py` | indirect via `test_agents_self_registered.py` and `test_quality_health` | none — no direct endpoint test |
| `hub/hub/api/v1/setup.py` | `test_setup.py` | partial — `test_setup_token_requires_localhost` is a **meta-test** using `inspect.getsource()` (lines 18-34). It does not exercise the actual code path; a real test that sends a request with a spoofed `X-Forwarded-For` or `Host` header is missing |
| `hub/hub/api/v1/status.py` | `test_status.py` | partial — 1 structural test, no negative cases |
| `hub/hub/api/v1/tasks.py` | `test_tasks.py` | partial — happy path only, no PATCH validation, no invalid-status rejection |

---

## Critical test gaps

- **No `tests/test_git_transport.py`** — `src/agentweave/transport/git.py` is the cross-machine collaboration transport and is the riskiest component. Zero coverage.
- **`tests/test_locking.py` does not exercise concurrent access** — only sequential acquire/release. The whole point of the module is concurrent correctness; running `acquire_lock` from two threads inside `tmp_path` with a short timeout would catch real races.
- **`tests/test_http_transport.py` does not test HTTP error semantics** — no test for `urllib.error.HTTPError(401/404/500)`, no test for the `HubTransportError` `classification` field, no test for malformed-JSON body, no test for socket `timeout`.
- **`tests/test_mcp_server.py` does not cover the 11 tools advertised in AGENTS.md** — `send_message`, `get_inbox`, `mark_read`, `list_tasks`, `get_task`, `update_task`, `create_task`, `get_status`, `ask_user`, `get_answer`, `get_agent_config` are all in `hub/hub/mcp_server.py` and are completely untested. Only the self-registration / heartbeat tools on the CLI side have tests.
- **`tests/test_jobs.py` does not test the scheduler** — `Job.should_fire()` is tested in isolation, but the `Watchdog._fire_job` scheduler loop has no integration test. `test_runtime_diagnostics.py` only covers the scheduler-missing branch.
- **`hub/hub/api/v1/agent_chat.py` has zero direct tests** — AGENTS.md devotes 60+ lines to a recent three-tier lookup refactor in this file. None of the three tiers (session_id exact, `[Session: {id}]` content tag, time-window fallback) is regression-tested.
- **`hub/hub/api/v1/agent_trigger.py` `[Session:]` / `[NewSession]` tag generation untested** — lines 129-133 build the content with a session tag; an accidental refactor that drops the tag would silently mis-route messages.
- **No test asserts that the `?token=` query param is the only SSE path** — `auth.py` accepts the API key via Authorization header OR `?token=`. The UI uses `?token=` in plain sight in `useSSE.ts:70`. A test that confirms this design is intentional (or that blocks it) is missing.
- **No test for `Watchdog._fire_job` across `runner` types** — codex, codex_mcp, opencode, claude_proxy branches are all unverified.
- **`tests/test_session.py` does not test orphan cleanup, completed-task migration, or corrupted-JSON recovery** — those branches are silent fallbacks.
- **No test for the `summaryForEvent` `default` branch fallback in `hub/ui/src/lib/eventSummary.ts:33-37`** — this is the path 99% of log lines will hit.

---

## Hub UI bugs

### Security

**CRITICAL: API key in SSE URL** — `hub/ui/src/hooks/useSSE.ts:70`

```ts
const url = `${hubUrl}/api/v1/events?token=${encodeURIComponent(apiKey)}`
```

The full API key is now visible in: nginx/uvicorn access logs, browser history, `Referer` headers on any subresource, and any in-network sniffer. AGENTS.md says "Bearer token auth" but the SSE path cannot use `EventSource` headers — the right fix is a short-lived signed token (or `URL.createObjectURL` over a `fetch()` with `Authorization` header). The companion server-side `auth.py:18,26` literally exists to accept this leaky channel.

**Closes:** S3 (client half) in `findings.md`. **See PR 9 in `pr-roadmap.md`.**

**API key persisted to `localStorage`** — `hub/ui/src/store/configStore.ts:65, 71, 77`

```ts
try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ apiKey, hubUrl, projectId, theme, mode })) } catch {}
```

Any XSS anywhere in the app exfiltrates the live API key. There is no `dangerouslySetInnerHTML` in the tree today, but the key is also readable by every browser extension. The store should at minimum use `sessionStorage` and only persist `theme`/`mode` in `localStorage`.

**Closes:** S4 in `findings.md`. **See PR 9 in `pr-roadmap.md`.**

**Config injected from `window.__AW_CONFIG__` without validation** — `hub/ui/src/store/configStore.ts:25-26`

```ts
const injected = (window as unknown as Record<string, unknown>).__AW_CONFIG__ as Partial<StoredConfig> | undefined
if (injected?.apiKey) { return { apiKey: injected.apiKey, ... } }
```

An XSS that runs before the store hydrates can plant a stolen key here. There is no schema check.

**Closes:** Same fix as the SPA key leak — `pr1-spa-key-leak.md`.

**SetupModal does not require any confirmation of a fresh API key** — `hub/ui/src/components/layout/SetupModal.tsx:110-117`

The input is `type="password"`, but the value is sent in the request body on submit and re-saved to `localStorage`. No length/format check (`aw_live_…`).

### Stale closure & useEffect bugs

**`ActivityLog.tsx:75-81` — `useSSE` callback captures stale `paused`**

```ts
useSSE((event) => {
  if (paused) return         // ← reads paused from render-0 closure
  setEvents(...)
})
```

This is the exact pattern AGENTS.md documents as already-fixed for `AgentPromptPanel`. `useSSE` does not accept a ref-based callback; the listener reads `paused` once and never updates. Toggle "Pause" and events keep flowing because the *first* listener (with `paused=false`) is still in the set.

**Closes:** M19 in `findings.md`. **See PR 9 in `pr-roadmap.md`.**

**`AgentActivityTab.tsx:52-56` — autoscroll effect ignores its dep, then re-runs on every tick**

```ts
useEffect(() => {
  if (shouldAutoScroll.current && scrollRef.current && !isPaused) { ... }
}, [activityItems, isPaused])
```

`activityItems` changes every SSE event (a `useMemo` dep on `outputLines` and `timelineEvents`). The `if (!isPaused)` guard is correct, but the autoscroll toggle `setIsPaused` does not actually pause the useMemo work — it just stops the visual scroll. With thousands of output lines this is a perf hazard.

**`AgentPromptPanel.tsx:64-99` — effect on `outputLines` triggers refetch loop**

```ts
useEffect(() => {
  if (sessionMode === 'new' && outputLines.length > 0 && selectedSessionId) { ... }
}, [outputLines, sessionMode, selectedSessionId, refetchSessions]
```

`refetchSessions` is from `useQuery`; depending on React Query version, its identity may change every render. Combined with `useAgentOutput` (line 34) which polls every 2s *and* consumes SSE, this can over-render. Also note that on line 70-71 the code calls both `setSelectedSessionId(detectedSession)` *and* `setSessionMode('resume')` *and* `refetchSessions()` — but the `chatHistory` query will refetch as well because `selectedSessionId` changed. Three refetches per detected session.

**`AgentPromptPanel.tsx:188-192` — `handleKeyDown` swallowed Shift+Enter silently** — actually fine, but the textarea has `onInput` to auto-grow; under React 18 strict-mode that handler runs twice, and the `target.style.height` is mutated imperatively then re-set in the next render (no issue today but a code smell).

**`useCopy.ts:18-19` — `setTimeout` on unmounted component**

```ts
await navigator.clipboard.writeText(text).catch(...)
setCopied(true)
setTimeout(() => setCopied(false), timeout)
```

No `useEffect` cleanup. If the component unmounts (e.g. `Modal` closes, agent changes) within `timeout` ms, React 18 will log "state update on an unmounted component" warnings in dev. Multiple rapid copy clicks leak timers.

**`LogsView.tsx:66-68` — autoscroll on `dataUpdatedAt`** — `useLogs` invalidates on every SSE event of any type (line 45-50). A single `message_created` makes the user jump to the bottom even if they're reading the top.

**`useSSE.ts:130-136` — `agent_session_changed` invalidation silently no-ops on missing agent**

```ts
case 'agent_session_changed': {
  const d = event.data as { agent?: string }
  if (d?.agent) { queryClient.invalidateQueries({ queryKey: ['agent', d.agent, 'sessions'] }) }
  break
}
```

If the server forgets to include `agent`, the cache is never invalidated. Better: invalidate the broader `['agent']` key.

**`useSSE.ts:30-32, 56-63` — module-level `eventSource` and `listeners` leak across StrictMode double-invokes**

React 18 StrictMode in dev mounts effects twice. The first mount adds a listener, the cleanup removes it, then the second mount adds it again — but `connect()` short-circuits on the "already connected" check. So the *first* mount's listener is left attached after the second mount's cleanup, leading to **double event dispatch** in dev. Production is unaffected; QA-only red herring.

**`useSSE.ts:83-88` — `onerror` schedules a reconnect with no cancel path**

```ts
eventSource.onerror = () => {
  eventSource?.close()
  eventSource = null
  if (reconnectTimer) clearTimeout(reconnectTimer)
  reconnectTimer = setTimeout(() => connect(hubUrl, apiKey), 3000)
}
```

If the user clears their config (`clearConfig`), `isConfigured` flips to false and the first effect's `connect` is skipped, but the **pending `reconnectTimer` from the prior `onerror` is never cleared**. The next page that re-enters and re-configures may immediately receive a stale `connect` call.

**Closes:** M22 in `findings.md`. **See PR 9 in `pr-roadmap.md`.**

### UI behavior bugs

**`agentChat.ts:22-23` — `sessionId !== 'new'` is wrong** — the codebase uses `NEW_SESSION_ID = '__new__'` everywhere else (`AgentPromptPanel.tsx:12`). The check is `sessionId !== 'new'`, so the "new" branch of the prompt panel still tries to fetch `/api/v1/agent/<agent>/chat/new`. Either the API returns 404 silently or it returns stale data. Either way the user sees flicker.

**Closes:** M20 in `findings.md`. **See PR 9 in `pr-roadmap.md`.**

**`AgentPromptPanel.tsx:14, 196-198` — `useNewChat` sets `selectedSessionId=NEW_SESSION_ID` then immediately reads it back via `selectedSessionIdRef`**. AGENTS.md claims this was fixed; the fix is in place, but **`useAgentChatHistory` is called with `null` when `sessionMode !== 'resume'`** (line 38). The query is disabled. Correct. But: line 65-66 (`outputLines` watcher) checks `selectedSessionId` *after* `userChoseNewRef` flipped to `true`, so the session-detection loop keeps running. If the first line of the new chat's output happens to carry a `session_id` field, it auto-flips back to resume mode before the user finished typing. AGENTS.md says the fix was "added `newSessionOutputIndexRef`" — it is there, but the first-effect watcher at line 64-99 does *not* use it; the `linesSinceNew` slice is built but never read.

**`AgentOutputPanel.tsx:46` — `sessionId` is recomputed on every render** — `[...lines].reverse().find((l) => l.session_id)?.session_id`. Acceptable for a small list, but for 10k+ output lines this scans the whole array twice.

**`useSSE.ts:71` URL gets the `apiKey` *and* `useConfigStore.getState()` (line 11) for `fetchWithAuth`** — two different `useConfigStore` callers; if React Query calls `fetchWithAuth` while a re-render is in flight, a stale `apiKey` could be sent. Today this is fine, but the centralized `fetchWithAuth` should also use a `useRef`-like snapshot like `getState()` is already doing.

**`ActivityLog.tsx:131-134` — events rendered in reverse order from `getBufferedEvents()`** — but `getBufferedEvents` already returns them in append order (line 38), so `[...visibleEvents].reverse()` produces newest-first. Fine. But the `key={event.localId}` uses a ref counter (line 53) — under StrictMode double-mount, the counter starts at 0 each mount, so the keys collide with prior events. Mostly harmless but causes the first paint to look weird in dev.

**`App.tsx:31` — `useSSE()` is called with no args** — relying on its side effect of invalidating queries. Every time the user navigates between pages, the parent is *not* re-rendered (just the `page` state changes), so the effect does not re-run. Fine, but it's a hidden coupling — the side effect should be documented or moved into `main.tsx` once.

**`InstructionsPage.tsx:10-14` — local `content` state desyncs with the data when `useSaveInstructions.isSuccess` becomes true mid-edit** — the useEffect on line 16-22 sets `saved` then a `setTimeout`; but if the user edits the textarea after save, the "Saved" indicator stays visible while the textarea shows new content. Cosmetic.

**`OverviewPage.tsx:144-146` — `recentEvents` is memoized with deps `[agents, tasks, questions]`** — completely unrelated to the events buffer. So `recentEvents` recomputes on every task update, every agent heartbeat, every question. The buffer read is cheap but the `.reverse().slice(-10)` allocation is unnecessary work.

---

## Hub UI security concerns

**`SetupModal.tsx:73-85` — `if (value !== theme)` is fine, but the modal has no cancel — only "Connect"**. A user closing the modal via Esc will still see the "open" backdrop because of the `open` prop binding in `App.tsx:58`. This is more UX than security but it does mean the *last* entered key always gets saved even if the user changes their mind.

**`agents.ts:111, 143` and `AgentMessageSender.tsx:43` and `AgentOutputPanel.tsx:54` and `AgentPromptPanel.tsx:151`** — all five of these `fetch('/api/v1/...')` calls use relative URLs. If the UI is served from `https://hub.example.com` and the user enters `http://localhost:8000` in SetupModal, the relative `fetch('/api/...')` still hits `hub.example.com`. There's no warning. The client uses `hubUrl` for SSE but a relative URL for everything else.

**`LogLine.tsx:58` — copies log entry as JSON to clipboard**. Log entries are server-controlled, so this is safe, but if the server ever includes `data.api_key` (e.g. in a `proxy_api_key_missing` event), it would land on the user's clipboard. The server event format in `agents.py:1041-1042` is `{"agent": ..., "action": ..., "message_id": ...}` — no key. Good. But this is a contract worth testing.

**Missing `Content-Security-Policy` meta tag in `index.html`** — combined with the localStorage API key, an XSS that escapes the React tree is catastrophic. The repo's `index.html` was not in scope of this audit but the absence of any CSP is a finding.

**`configStore.ts:25-26` — `as Partial<StoredConfig> | undefined` cast on `window.__AW_CONFIG__`** — typed escape hatch. The injected config (when present) is trusted to be in the right shape. There is no schema validator.

---

## Hub UI performance issues

**`useAgentOutput` double-fetches (poll + SSE) — `hub/ui/src/api/agents.ts:174-255`**

- `useQuery(['agents', name, 'output', 'seed'])` is called on mount (`staleTime: 5 min`).
- Then a `useEffect` polls `setInterval(poll, 2000)` (line 253) that hits `/api/v1/agents/<name>/output?since=…` every 2s.
- Separately, SSE events of type `agent_output` are appended via `useSSE`.
- The poll is intentionally a "SSE-miss fallback" per the comment, but it runs unconditionally, generating one HTTP call per agent per 2s *per mount*. On the Agents page with multiple selected agents (e.g. via `useAgentOutput(name)` in `AgentActivityTab` *and* `AgentOutputPanel` and `AgentPromptPanel` *all for the same agent*), the same poll runs three times because the cache is keyed on `name` but the `cacheKey` includes `name` only once. **The `linesCache.set(cacheKey, …)` is a module-level `Map` that all callers share** — so they all see the same lines, but each one's `useEffect` is still registered and running. Three `setInterval` per agent = 1.5 calls/sec per visible agent for no reason.

**Closes:** M21 in `findings.md`. **See PR 10 in `pr-roadmap.md`.**

**`useAgents` and `useAgentTimeline` and `useAgentSessions` poll + SSE — `hub/ui/src/api/agents.ts:83, 93, 290`**

- `useAgents` polls every 10s.
- `useAgentTimeline` polls every 5s.
- `useAgentSessions` polls every 10s.
- All three are also invalidated by SSE. So in steady state the network is hit on every SSE event *and* on the polling timer. With a busy Hub the polling timers will fire a lot of redundant requests.

**`useAgentChatHistory` polls every 3s — `hub/ui/src/api/agentChat.ts:24`**

The chat panel refetches `/api/v1/agent/<agent>/chat/<sessionId>` every 3s. This is the heaviest endpoint (joins across `Message` and `AgentOutput`). The SSE bridge could be used to invalidate on `agent_output` events, but the code doesn't do that.

**`LogsView.tsx:45-50` — `useLogs` invalidates on every SSE event** — `useSSE(() => invalidateQueries(['logs']))` with no event-type filter. A heartbeat (one per minute per agent) will refetch the whole logs table.

**`useSSE` — `queryClient.invalidateQueries({ queryKey: ['tasks'] })` on `agent_heartbeat` — `useSSE.ts:123-125`**

Heartbeats fire every minute per agent; a project with 5 agents triggers 5 task-table refetches per minute on top of the explicit `['tasks']` invalidation on task events. Cheaper: invalidate only when the heartbeat status changes.

**`useEffect` chain in `AgentPromptPanel.tsx:60-99` does `.sort()` on a freshly-merged list every render** — `merged.sort((a,b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())`. The list is created on every outputLines tick. If output lines arrive at 10Hz, that's 10 sorts/sec plus 3 array allocations. Use `useMemo` and keep the merge incremental.

**`MessagesFeed.tsx:27` — `useMessageHistory({})` runs on every mount to compute `agents`** — separate from the user-selected `useMessageHistory({ sort })`. Two requests on mount, one of them is to compute a list of agent names for the filter chips.

**StatusBar shows 4–6 React Query subscriptions and the `useStatus` refetch timer at 30s — `hub/ui/src/components/layout/StatusBar.tsx:11-13`**. Even when the user is on the Logs page, StatusBar is mounted. That's expected, but it means the status endpoint is hit every 30s on every page.

---

## Hub UI code quality

- **`contextBarColor(percent, warning)` duplicated 3 times**: `hub/ui/src/components/agents/AgentCard.tsx:0` (inline), `AgentsPage.tsx:12-16`, `AgentDetailPanel.tsx:18-22`, `OverviewPage.tsx:14-18`. Extract to `lib/agentStatus.ts`. **Closes:** Q6 in `findings.md`. **See PR 10 in `pr-roadmap.md`.**
- **`STATUS_CONFIG` table duplicated 3 times**: `AgentCard.tsx:11-16`, `AgentDetailPanel.tsx:23-28`, `AgentInfoTab.tsx:23-28`. Same `as Record<string, StatusConfig>` shape. Extract.
- **"Status dot + ping animation" JSX duplicated 5+ times** across `AgentCard.tsx:48-67`, `AgentsPage.tsx:38-46`, `AgentDetailPanel.tsx:78-87`, `AgentInfoTab.tsx:68-80`, `OverviewPage.tsx:40-49`. Extract to `<AgentStatusDot status={...} />`.
- **"Role tag" JSX duplicated 4 times** across the same files plus `OverviewPage.tsx:55-87`. Extract to `<RoleTag role={...} label={...} />`.
- **"Nav item button" JSX duplicated 3 times in `Sidebar.tsx`** (top-level, sectioned, settings) at lines 128-167, 178-218, 228-243. Extract to `<SidebarItem id={...} label={...} icon={...} active={...} badge={...} onClick={...} />`. **Closes:** Q14 in `findings.md`. **See PR 10 in `pr-roadmap.md`.**
- **"Mouse hover styles" pattern duplicated ~15 times** (`onMouseEnter={(e) => { e.currentTarget.style.background = '...' }}` + matching `onMouseLeave`). The proper fix is a Tailwind `hover:` utility or a `useHover` hook. The current code reattaches a fresh closure on every render.
- **Inline `style={{}}` objects on every component** — every render creates a new object. Combine with Tailwind theme tokens and `useMemo` for the few that need computation.
- **Large components**: `AgentPromptPanel.tsx` (399 lines), `AgentsPage.tsx` (226 lines), `MessagesFeed.tsx` (163 lines), `LogsView.tsx` (265 lines), `LogsView.tsx`'s `eventCategory` function (lines 21-32) is its own micro-rule engine that doesn't belong inline.
- **No `useMemo` on `StatusBar.tsx:20` `Object.values(data.task_counts).reduce(...)`** — fine, but `Sidebar.tsx:43-46` does a `.filter` on every render. With 100 messages and 10 agents, that's 100 + 10 iterations on every state change in the parent.
- **`useApiConfig.ts:1-6` is a 6-line trivial selector** — fine, but it's only used in `useApiConfig` itself? Let me check… `grep` shows it's exported. It's used in `useApiConfig` only. Could be inlined.
- **Magic numbers throughout**: `'5min'` (LogsView), `60_000` (status.ts), `256` (sse.py queue max), `2 min` (liveness in `agents.py:347`). Pull to a constants file.
- **`useSSE.ts:91` is called in many components but its API does not let callers know if SSE is connected**. A `useSSEStatus()` hook returning `'connected' | 'reconnecting' | 'disconnected'` would let the StatusBar show a real "live"/"paused" indicator.
- **Module-level state in `useSSE.ts:30-32`** — `listeners`, `eventSource`, `eventBuffer` — is fine for the singleton pattern but makes unit testing impossible. Extracting a `SSEClient` class would help.
- **TypeScript `any`**: `grep` shows no explicit `: any`, but `as Record<string, unknown>` is used 12 times. This is correct safety, but `as unknown as` casts in `useSSE.ts:43` and `configStore.ts:25` are a code smell — a typed `SSEEvent` factory would remove the cast.
- **Per-page scaffolding repeated in every page**: `if (isLoading) return <div>Loading…</div>` then `if (data.length === 0) return <EmptyState …/>`. Extract to `<DataView query={…} empty={…}>`.
- **All pages mounted concurrently with CSS hidden** so all `useEffect`s and `setInterval`s run. **Closes:** Q15 in `findings.md`. **See PR 10 in `pr-roadmap.md`.**

---

## Quick wins

1. **Remove API key from SSE URL** — `hub/ui/src/hooks/useSSE.ts:70`. Either: (a) use a `fetch()` with `Authorization` and stream the response, or (b) on the server, accept a short-lived signed ticket from `/events/ticket` and embed that instead. The current `?token=` channel should be removed or wrapped. **Closes:** S3 (client half) in `findings.md`. **See PR 9 in `pr-roadmap.md`.**
2. **Stop storing `apiKey` in `localStorage`** — `hub/ui/src/store/configStore.ts:65, 71, 77`. Move it to `sessionStorage` and only persist `theme` + `mode` to `localStorage`. Server-injected config (when present) already wins. **Closes:** S4 in `findings.md`. **See PR 9 in `pr-roadmap.md`.**
3. **Add `EventSource` reconnection to the `useEffect` cleanup** — `hub/ui/src/hooks/useSSE.ts:100-103`. If `isConfigured` flips to false, `eventSource.close()` and clear `reconnectTimer` to prevent stale reconnects.
4. **Fix the `sessionId !== 'new'` check** — `hub/ui/src/api/agentChat.ts:23`. The codebase uses `NEW_SESSION_ID = '__new__'` everywhere; this query is currently firing for the "new" branch. **Closes:** M20 in `findings.md`. **See PR 9 in `pr-roadmap.md`.**
5. **Add a real concurrent test for `acquire_lock`** — `tests/test_locking.py`. Two threads, short timeout, assert one wins and one raises `LockError`. **Closes:** T2 in `findings.md`. **See PR 12 in `pr-roadmap.md`.**
6. **Add `tests/test_http_transport.py` cases for HTTPError 401/404/500, `HubTransportError` classification, malformed JSON, and `socket.timeout`**. **Closes:** T8 in `findings.md`. **See PR 12 in `pr-roadmap.md`.**
7. **Add a test that asserts the SSE endpoint requires auth and accepts `?token=`** — `hub/tests/test_sse.py` only tests the in-memory `SSEManager`, not the FastAPI endpoint. Currently the auth is untested through the URL query channel.
8. **Test the three-tier agent chat lookup** — `hub/hub/api/v1/agent_chat.py:91-144`. AGENTS.md highlights this code; the test does not exist. **Closes:** T4 in `findings.md`. **See PR 12 in `pr-roadmap.md`.**
9. **Add a test for `[NewSession]` / `[Session: <id>]` tag generation** — `hub/hub/api/v1/agent_trigger.py:129-133`. Refactor that drops the tag will silently mis-route. **Closes:** T7 in `findings.md`. **See PR 12 in `pr-roadmap.md`.**
10. **Replace the meta-test in `test_setup.py:18-34`** with a real request against the endpoint with a spoofed `Host` header. **Closes:** T10 in `findings.md`. **See PR 12 in `pr-roadmap.md`.**
11. **Dedupe `contextBarColor`, `STATUS_CONFIG`, and the status-dot JSX** — extract to `lib/agentStatus.tsx`. Eliminates ~80 lines. **Closes:** Q6 in `findings.md`. **See PR 10 in `pr-roadmap.md`.**
12. **Replace the `useEffect` poll in `useAgentOutput` with SSE-only** — `hub/ui/src/api/agents.ts:220-255`. Add a single "missed events" reconciliation that only runs when an SSE gap is detected (track last SSE event id, query REST only if gap > 30s). **Closes:** M21 in `findings.md`. **See PR 10 in `pr-roadmap.md`.**
13. **Add a `useSSEStatus()` hook** — `hub/ui/src/hooks/useSSE.ts:91`. Lets StatusBar show a real "Live" indicator and surfaces reconnect failures to the user.
14. **Stop rendering all pages concurrently** — `hub/ui/src/App.tsx:44-53`. Only the active page should mount; today every page is mounted and CSS-hidden, so every page's `useEffect`s and `setInterval`s run. Use `{page === 'messages' && <MessagesFeed />}` instead of CSS hiding. **Closes:** Q15 in `findings.md`. **See PR 10 in `pr-roadmap.md`.**
15. **Wrap the chat history 3s poll in a memoized timer** — `hub/ui/src/api/agentChat.ts:24`. When the user is on the Agents page (not in chat), this still polls every 3s per visible agent. Gate it on the chat panel being mounted.
16. **Add a test for `Watchdog._fire_job` happy path** — `tests/test_jobs.py` covers only `Job` CRUD; the scheduler path is dark. The closest is `test_runtime_diagnostics.py:74-100` which only tests the *failure* path. **Closes:** part of T6 in `findings.md`. **See PR 12 in `pr-roadmap.md`.**
17. **Fix the `paused` stale-closure in `ActivityLog.tsx:75-81`** — same fix as `AgentPromptPanel` already has; see AGENTS.md. **Closes:** M19 in `findings.md`. **See PR 9 in `pr-roadmap.md`.**
18. **Add an `ErrorBoundary` at the App root** — `hub/ui/src/main.tsx`. Today any throw inside a page (e.g. SSE listener) will unmount the entire tree.
19. **Use `date-fns/format` consistently in timestamps** — `AgentPromptMessage.tsx:37` uses `format`; other components use `toLocaleDateString` (`Sidebar.tsx`, `JobForm.tsx`) and `toLocaleTimeString` (`LogsView.tsx:81`). Pick one.
20. **Fix the duplicated `/api/v1/agent/sessions/{agent}` endpoint shape** — `hub/hub/api/v1/agent_trigger.py:285` returns `{ "sessions": [...] }` and `hub/ui/src/api/agents.ts:286` types it as `{ sessions: AgentSession[] }` — fine — but the same path in `AgentMessageSender.tsx:43-46` does an unstructured `fetch`, not through the hook, and does no type check. Move through the hook.

---

## Summary

| Severity | Count |
|---|---|
| Critical security | 2 (API key in SSE URL, API key in localStorage) |
| Stale closure / useEffect bugs | 7 |
| UI behavior bugs | 7 |
| Hub UI security | 5 |
| Performance issues | 8 |
| Code quality (duplication) | 10+ |
| Test gaps | 11 areas |
| Quick wins | 20 |

**The two CRITICAL issues (S3 client half and S4) are the foundation of PR 9.** The 4 useEffect / stale closure bugs (M19, M20, M21, M22) are also PR 9 / PR 10.

**The most impactful single fix in this report is the SSE URL key leak** (S3 client) — combined with the server half (HUB-C3 in audit 02) it's the largest user-data exposure in the project.

**The `agentChat.ts:22` `sessionId !== 'new'` bug** is a real UX papercut that's been silently affecting every "new chat" attempt; the fix is one line.

**The `ActivityLog.tsx:75-81` `paused` stale closure** is a 5-minute fix that closes a real UX bug (the pause button does nothing).
