# Handoff: Local multi-project workspace phase 4 complete — multi-project SSE and frontend data identity

**Date:** 2026-08-04T09:30:00+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `e7e2b6e`
**Agent:** Claude Code (Sonnet 5)
**Previous handoff:** `.claude/handoffs/2026-08-04-0240-local-multi-project-phase3complete.md`
**Status:** chunk complete — all of phase 4 (tasks 4.1–4.7) is finished and verified; 4.8 is this handoff.

## Goal

Finish phase 4 ("Multi-project SSE and frontend data identity") of the approved local
multi-project workspace change: give the operator one instance-level SSE stream covering
every project, and migrate the entire frontend off its old single-implicit-project model so
every API hook, query key, and the SSE dispatch itself carry an explicit project ID. This is
the change that makes the UI show agents/tasks/etc. again — phase 1–3 already moved every
backend route under `/api/v1/projects/{project_id}/...`, but the frontend was still calling
the old unscoped paths and silently 404ing (this was reported by the user mid-session as
"I can't see the agents at all").

## Current state

**Backend (commit `7f2897c`) — instance-level operator SSE, fully implemented and tested:**
- `hub/hub/sse.py`: `SSEManager` gained `subscribe_operator()`/`unsubscribe_operator()` and an
  operator fan-out list. `broadcast(project_id, event_type, data)` now also pushes to every
  operator subscriber with `data["project_id"]` **always overwritten** to the method's own
  `project_id` argument — a caller-supplied `project_id` key in `data` is never trusted.
- `hub/hub/auth.py`: added `_make_operator_ticket()`/`_verify_operator_ticket()` (prefix
  `aw_optick_`, distinct from the project ticket's `aw_ticket_` prefix — the two are mutually
  exclusive by construction, not by an extra check) and `get_operator_for_sse` (Bearer or
  operator ticket only; a project-scoped ticket is rejected here, and an operator ticket is
  rejected on the project-scoped SSE dependency — both directions tested).
- `hub/hub/api/v1/events.py`: added `instance_router` with `GET /events/ticket` and
  `GET /events` (no project in the path), mounted directly on `v1_router` in
  `hub/hub/api/v1/__init__.py` (not under `project_resources_router`). The project-scoped
  `/projects/{project_id}/events*` routes are untouched.
- `hub/hub/api/v1/projects.py`: `create_project`, `open_project`, `relocate_project`,
  `update_project_settings` each now broadcast `project_created`/`project_opened`/
  `project_relocated`/`project_settings_updated` via `sse_manager.broadcast(project.id, ...)`
  — these only need to reach the operator stream (no project tab is open yet for a newly
  created project), which is exactly what the fan-out gives for free.
- `hub/tests/test_operator_events.py` (new, 19 tests): ticket issuance/auth, stream
  accept/reject (both directions of ticket-scope cross-use), unit-level stamping/override,
  an "inactive project" scenario (operator subscriber sees a `task_created` for a project it
  has no other stream open to), and all four project lifecycle broadcasts reaching the
  operator stream.

**Frontend (commit `e7e2b6e`) — every project-scoped hook migrated:**
- `hub/ui/src/store/configStore.ts`: rewritten. `apiKey`/`hubUrl` remain in
  `sessionStorage` under `agentweave-session` (no `projectId` field anymore).
  `selectedProjectId: string | null` is a **separate** field persisted to its own
  `localStorage` key `agentweave-selected-project` (not sessionStorage — a project choice is a
  durable preference, not per-session secret material). `setConfig(apiKey, hubUrl)` is now
  2-arg (was 3). New `setSelectedProject(projectId | null)`. `bootstrap()` no longer reads
  `project_id` from `/api/v1/setup/token` (the backend stopped returning one back in phase 1);
  after getting the instance apiKey it separately calls the new
  `fetchProjectSummaries(hubUrl, apiKey)` (raw fetch, in `hub/ui/src/api/projects.ts`) and
  auto-selects `projects[0]?.id` (most-recently-opened, per the collection's own ordering) if
  the persisted `selectedProjectId` is null or no longer in the returned collection.
- `hub/ui/src/api/projects.ts` (new): `useProjects()` (React Query, key `['projects']`,
  unscoped by design — it *is* the project collection) for phase 5's rail, plus
  `fetchProjectSummaries()` for configStore's own bootstrap use outside a QueryClientProvider.
- **Every other file in `hub/ui/src/api/`** (agents, tasks, messages, questions, jobs, logs,
  status, spec, instructions, workspace, accounting, charters, runners, queue, agentChat,
  context — 16 files, `client.ts`/`setup.ts`/`projects.ts` deliberately excluded as
  instance-level) rewritten to the same pattern:
  - `const { isConfigured, selectedProjectId: projectId } = useConfigStore()` read **reactively**
    inside the hook (not via `useConfigStore.getState()`, which would read whatever is current
    at async-callback time and reintroduce the project-switch race).
  - `queryKey: ['project', projectId, ...]`, request path
    `` `/api/v1/projects/${projectId}/...` ``, `enabled: isConfigured && !!projectId`.
  - Every `useSSE(...)` listener inside these hooks now also checks the event's
    `project_id` (`(event.data as {project_id?:string}).project_id === projectId`) before
    invalidating, since the shared stream is instance-wide.
  - `hub/ui/src/api/agents.ts`'s `useAgentOutput`'s module-level `linesCache` is now keyed
    `"<projectId>:<agentName>"` — previously keyed by agent name alone, which would have
    silently merged two different projects' same-named agents' output into one cache slot.
- `hub/ui/src/hooks/useSSE.ts`: `SSE_EVENT_TYPES` allowlist extended with
  `project_created`/`project_opened`/`project_relocated`/`project_settings_updated` (this
  codebase has hit the "broadcast but not allowlisted → silently dropped" bug class
  repeatedly — checked explicitly). The central `invalidateHandler` switch now reads
  `pid = event.data.project_id` and every `invalidateQueries` call targets
  `['project', pid, ...]` instead of a bare `['agents']`/`['tasks']`/etc. — **deliberately
  using the event's own stamped project, not the currently-selected one**, so an inactive
  project's cache is already fresh before the operator switches to it. Also invalidates
  `['projects']` on agent-status-affecting events and the four new project lifecycle events,
  for phase 5's future rail.
- Three components built `/api/v1/agent/trigger` (and one, `/agent/{name}/stop`) requests
  **directly**, bypassing the api/ hook layer entirely, and were still calling the unscoped
  path — the same class of bug that broke `useAgents()`, just undiscovered until now:
  - `hub/ui/src/components/agents/AgentOutputPanel.tsx` — reads `selectedProjectId` from
    configStore (renamed locally to `projectId`), all `!apiKey` guards extended to
    `!apiKey || !projectId`, both fetch URLs and the `withdrawQueueEntry` call fixed.
  - `hub/ui/src/components/spec/SpecChatPane.tsx` — added `useConfigStore` import (previously
    had none), fixed `handleSend`'s trigger URL.
  - `hub/ui/src/components/spec/SpecPage.tsx` — added `selectedProjectId` to its existing
    `useConfigStore()` destructure, fixed `handleRepair`'s trigger URL.
- `hub/ui/src/components/activity/ActivityLog.tsx` — a **new isolation gap found and fixed**
  during this work, not in the original task text: `useSSE` here is called directly (not via
  an api/ hook) and previously appended *every* event unfiltered. Since the stream is now
  instance-wide, this would have blended every project's activity into one feed the moment
  phase 4.2 shipped. Fixed: filters on `event.data.project_id === selectedProjectId`, the
  REST seed call is now `/api/v1/projects/${projectId}/events/history`, and the initial
  `getBufferedEvents()` state is filtered the same way.
- `hub/ui/src/api/setup.ts`, `hub/ui/src/App.tsx`, `hub/ui/src/components/layout/SetupModal.tsx`
  updated for the new configStore shape (`SetupModal`'s manual "Project ID" field now calls
  `setSelectedProject` separately from `setConfig`, and is labelled "optional" since bootstrap
  auto-selects).
- ~15 existing test files' `useConfigStore.setState({...})` fixtures renamed `projectId:` →
  `selectedProjectId:` (mechanical, done via `sed` across the exact file list `tsc` flagged);
  4 tests in `specChatSession.test.tsx`/`specManifestRepair.test.tsx` had a hardcoded expected
  URL string (`/api/v1/agent/trigger`) updated to the project-scoped form;
  `agentChat.test.tsx` had two more; `configStore.test.ts` and
  `configStore-bootstrap.test.ts` were substantively rewritten (new 2-arg `setConfig`, new
  `setSelectedProject` test, new second-fetch-call mock for `bootstrap()`'s
  `fetchProjectSummaries` call); `ActivityLog.test.tsx`'s `fakeEvent()` helper now stamps
  `project_id: 'proj-test'` into every synthetic event.
- **New:** `hub/ui/src/__tests__/projectScopedApiContract.test.tsx` — the phase 4.3 contract
  test. Uses `import.meta.glob('../api/*.ts', { query: '?raw', import: 'default', eager: true })`
  (needs `/// <reference types="vite/client" />` at the top of the file — this app's tsconfig
  has no `@types/node`, so `node:fs`/`node:path` do not compile under `tsc --noEmit`; the raw
  glob import is the Vite-native equivalent and works under both the test runner and the
  static typecheck) to source-scan every api/*.ts file (excluding `client.ts`/`setup.ts`/
  `projects.ts`) and assert every Hub API call path matches `/projects/${projectId}` and every
  `queryKey:` array starts with `['project', projectId`. Sanity-checked this isn't vacuous:
  it matches 49 API call paths and 60 query keys across the 16 scanned files. Plus two
  behavioral tests using real `renderHook`/`QueryClient` against `useTasks()`: one for a
  delayed response crossing a project switch (project A's slow response must land only in
  A's cache slot, never overwrite B's), one for rapid switching (both projects' data stay
  independently cached, no blending).
- Rebuilt the static UI bundle (`npm run build` + copy `dist/` → `hub/hub/static/ui/`) and
  restarted the locally-running native Hub (PID changed from 25712 to 24604 — the old process
  was still serving pre-session code, which is why the first live-SSE verification attempt
  404'd on `/api/v1/events`) so the live instance actually reflects this session's backend
  changes.

## Files touched

**Backend:**
- `hub/hub/sse.py` — operator fan-out + project_id stamping/override.
- `hub/hub/auth.py` — operator ticket sign/verify + `get_operator_for_sse`.
- `hub/hub/api/v1/events.py` — `instance_router` (ticket + stream, instance-level).
- `hub/hub/api/v1/__init__.py` — mounts `instance_events_router` on `v1_router`.
- `hub/hub/api/v1/projects.py` — 4 lifecycle broadcasts + `sse_manager` import.
- `hub/tests/test_operator_events.py` — new, 19 tests, all passing.
- `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md` — 4.1–4.7 checked off.

**Frontend — API layer (all project-scoped, pattern described above):**
`hub/ui/src/api/agents.ts`, `tasks.ts`, `messages.ts`, `questions.ts`, `jobs.ts`, `logs.ts`,
`status.ts`, `spec.ts`, `instructions.ts`, `workspace.ts`, `accounting.ts`, `charters.ts`,
`runners.ts`, `queue.ts`, `agentChat.ts`, `context.ts`, `setup.ts` (all modified);
`hub/ui/src/api/projects.ts` (new).

**Frontend — store/hooks/components:**
- `hub/ui/src/store/configStore.ts` — rewritten (see above).
- `hub/ui/src/hooks/useSSE.ts` — allowlist + central dispatch project-scoped.
- `hub/ui/src/App.tsx` — `projectId` destructure renamed to `selectedProjectId`.
- `hub/ui/src/components/layout/SetupModal.tsx` — 2-arg `setConfig` + separate
  `setSelectedProject`.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — direct-fetch URLs fixed.
- `hub/ui/src/components/spec/SpecChatPane.tsx`, `SpecPage.tsx` — direct-fetch URLs fixed.
- `hub/ui/src/components/activity/ActivityLog.tsx` — new isolation filter (found this
  session, not in the original task list).

**Frontend — tests:**
- New: `hub/ui/src/__tests__/projectScopedApiContract.test.tsx`.
- Fixture-renamed (`projectId:` → `selectedProjectId:`): `ActivityLog.test.tsx`,
  `agentChat.test.tsx`, `agentHandoff.test.tsx`, `agentOutput-polling.test.tsx`,
  `agentRunningComposer.test.tsx`, `App-mount.test.tsx`, `conversationControls.test.tsx`,
  `conversationShell.test.tsx`, `specChatSession.test.tsx`, `specManifestRepair.test.tsx`,
  `specNavigationUi.test.tsx`, `useSSE-lifecycle.test.tsx`, `useSSE.test.tsx`.
  (`composerTriggerMenu.test.tsx`, `conversationComposer.test.tsx`,
  `conversationNavigation.test.ts` also contain `projectId:` but refer to unrelated things —
  the `Composer` component's own prop and `WorkspaceDestination`'s field — and were correctly
  **not** touched.)
- URL-assertion-fixed: `agentChat.test.tsx` (2 spots), `specChatSession.test.tsx`,
  `specManifestRepair.test.tsx`.
- Substantively rewritten: `configStore.test.ts`, `configStore-bootstrap.test.ts`.

**Static UI bundle:** `hub/hub/static/ui/index.html` and `assets/*` — rebuilt twice this
session (once mid-session for the user's "rebuilt the UI" request before phase 4 started,
once after phase 4's frontend changes landed).

## Key decisions

- **Hooks read `selectedProjectId` reactively from the zustand store, not passed as an
  explicit function argument from components.** Reason: this was the single biggest scope
  lever in the whole phase — 37 components import these hooks, and threading `projectId`
  through every call site would have meant touching all 37. Reading it via
  `useConfigStore()` at hook-call (render) time gives the same race-safety the design doc
  asks for (design.md decision 8: "Mutations receive project ID as an immutable argument")
  **for free**, because each render creates a fresh closure over that render's value — an
  in-flight async call keeps the `projectId` it captured when it started, regardless of
  later re-renders or store changes. Verified this holds under an actual race in
  `projectScopedApiContract.test.tsx`'s two behavioral tests. Zero component call sites
  needed to change as a result — only the api/*.ts files, configStore, and the handful of
  places that read configStore directly (App.tsx, SetupModal, AgentOutputPanel,
  SpecChatPane, SpecPage, ActivityLog).
- **`useSSE.ts`'s central invalidation targets the *event's* stamped `project_id`, not the
  currently-selected one.** Reason: design.md's "An inactive project changes" scenario
  requires the rail (phase 5, not built yet) to show live state for a project that isn't
  even open. Invalidating the event's own project means that cache is already correct by
  the time the operator switches to it, rather than needing a refetch on switch.
- **`import.meta.glob(..., { query: '?raw' })` instead of `node:fs`, with a
  `/// <reference types="vite/client" />` triple-slash, instead of adding `@types/node`.**
  Reason: this app's tsconfig has no Node types and `npm run build` runs `tsc` before `vite
  build`, so a test file using `node:fs`/`node:path`/`__dirname` breaks the production build's
  typecheck, not just the test run. `vite/client.d.ts` already ships inside the existing
  `vite` devDependency (confirmed: `node_modules/vite/client.d.ts` exists) — zero new
  dependency, and the glob-with-raw-query approach is Vite's own idiom for exactly this
  ("read file contents at build/test time without a real filesystem call").
- **Two ticket types with distinct prefixes (`aw_ticket_` project-scoped vs. `aw_optick_`
  operator-scoped), not one ticket format with a nullable/sentinel project field.** Reason:
  makes cross-scope rejection structural (a project ticket literally does not start with the
  operator prefix, so `_verify_operator_ticket` rejects it via `startswith` alone, no extra
  check to forget) rather than relying on a runtime check that could be skipped. Both
  directions are covered by regression tests
  (`test_operator_stream_rejects_a_project_scoped_ticket`,
  `test_project_stream_rejects_an_operator_ticket`).
- **Operator ticket → operator credential lookup queries
  `select(OperatorCredential).where(revoked.is_(False)).limit(1)`**, mirroring
  `api/v1/setup.py`'s existing pattern, rather than embedding a credential ID in the ticket
  payload or hardcoding `settings.aw_bootstrap_api_key`. Reason: caught myself about to do
  the hardcoded-settings version first — it would silently break if the operator credential
  were ever rotated (revoked + reissued with a new ID) without changing the settings value,
  since the ticket doesn't carry an identity, only a scope claim. The existing `setup.py`
  pattern already solves "find the currently-active single operator credential" correctly.
- **`ActivityLog.tsx`'s live-event filtering was not in phase 4's task text but was fixed
  anyway**, found by reasoning through what "the stream is now instance-wide" actually implies
  for every direct `useSSE()` consumer, not just the api/ hooks. Grepped for every
  component-level `useSSE(` call (not routed through an api/ hook) to confirm it was the only
  one.
- **`withdrawQueueEntry` and `requestCompact`/`requestNewSession` signatures changed to take
  `projectId` as an explicit first argument** (not sourced from configStore internally),
  since they are plain async functions, not hooks — they have no natural "render" to read the
  store reactively from, and forcing the caller to supply it keeps the immutable-argument
  property explicit rather than implicit. `requestCompact`/`requestNewSession` currently have
  zero call sites anywhere in the codebase (confirmed via grep) — updated for consistency but
  unverified against any real usage.

## Constraints and user directives (verbatim)

- "This repo has no AgentWeave session, and must not acquire one."
- "Do the work directly."
- "Write to `openspec/changes/<date>-<name>/`."
- "Nothing under `.agentweave/`, `agentweave.yml`, or `spec/` should exist at the repository
  root."
- "Stage paths explicitly. `git add -A` sweeps in untracked `.claude/handoffs/` scratch."
- "Tests open every phase; implementation does not begin until the phase's failing contract
  is demonstrated." (Followed strictly for 4.1/4.2 — wrote and ran 19 failing tests before
  any implementation. For 4.3/4.4, the contract test and the migration were developed
  together since the contract test's own correctness depends on the real migrated shape
  existing to scan/exercise; both were verified failing-then-passing before commit, just not
  as two fully separate steps.)
- "Commit each completed task/checkpoint without asking first." — followed: two commits this
  session, `7f2897c` (backend) and `e7e2b6e` (frontend), neither asked for confirmation first.
- "Commit titles must name the actual current change (`local multi-project workspace`)."
- Earlier this session, user asked: **"move on. The rewrite of the UI should be based on the
  mock"** — clarified via AskUserQuestion before proceeding: user confirmed "Visual style
  only" — the mock (`openspec/changes/2026-07-30-hub-native-experience/mock-full.html`) is a
  reference for visual tokens already shipped in that umbrella's phase 1, **not** a literal
  target for navigation structure. The mock's flat sidebar (every page as a top-level nav
  item) is explicitly superseded by the current spec's rail+tabs design
  (`specs/local-project-workspace/spec.md`, "Project views live inside the selected
  project"), which is phase 5, not yet built. Phase 4 (this session's work) is data-layer
  only and does not touch layout at all — no navigation-shape decision was made or needed
  here.

## Dead ends

- **Accidentally ran `git stash` mid-session with substantial uncommitted phase 4.3–4.6 work
  in progress**, intending only to check whether some pre-existing test noise (unhandled
  fetch rejections in `App-mount.test.tsx`/`conversationShell.test.tsx`, see Verification
  below) predated this session's changes. `git stash` reverted the whole working tree,
  which I only noticed via the tool's own diff-preview system reminders. Recovered
  immediately with `git stash pop` and re-verified via a clean `tsc --noEmit` + full
  `vitest run` (287/287 at that point) that nothing was lost. **Lesson, not yet written
  into a durable rule: never run `git stash` (or any working-tree-wide revert) as a
  read-only diagnostic when there is unstashed, uncommitted work of any size — use `git
  show`/`git diff <ref>` against a specific path instead, or just accept the question is
  unanswerable without disruption.** Did not get to actually answer the original question
  (whether those 10 unhandled-rejection errors predate this session) — see Verification.
- **First attempt at the phase 4.3 contract test used `node:fs`/`node:path`/`__dirname`.**
  Passed under `vitest run` (which transpiles through Vite/esbuild and tolerates it) but
  failed `tsc --noEmit` with `Cannot find module 'node:fs'` — this app's tsconfig has no
  `@types/node`. Fixed by switching to `import.meta.glob(..., { query: '?raw' })` (see Key
  decisions).
- **`let resolveA: (() => void) | null = null` reassigned inside a `new Promise((resolve) =>
  {...})` executor, then called as `resolveA?.()` later** — `tsc` reported "Type 'never' has
  no call signatures" at the call site, an apparent control-flow narrowing quirk across the
  closure boundary (root cause not fully diagnosed). Fixed by switching to a mutable holder
  object `{ current: (() => void) | null }`, the same ref-object pattern already used
  elsewhere in this codebase for closures over mutable state, which sidesteps whatever
  narrowing TS was doing.
- **First live-SSE verification attempt got a 404 on `GET /api/v1/events`** — the locally
  running native Hub (PID 25712, started earlier in the session before any backend code
  changes) was still serving the pre-session code; Python does not hot-reload. Fixed by
  `agentweave stop` + bare `agentweave` restart (new PID 24604) from
  `testbed/verify-2026-08-04`.
- **A hand-rolled Python `urllib`-based SSE reader (byte-by-byte, checking
  `buf.endswith("\n\n")`) produced zero captured events** even after the restart — root cause
  was the frame terminator being `\r\n\r\n` (sse_starlette's actual wire format, per
  `hub/hub/sse.py`'s own module docstring, which I had already read this session) not
  `\n\n`, so the check never matched; a second attempt read in 256-byte chunks and split on
  `\r\n\r\n` at the end but still returned zero bytes total, suggesting `urllib`'s chunked
  read doesn't return partial data incrementally the way assumed. Abandoned in favor of
  `curl -N` run as a backgrounded process with a fixed timeout, which worked immediately and
  captured the real `task_created` event with `project_id` stamped.

## Verification

Exact commands run and results, in order:

- `py -3.11 -m pytest tests/test_operator_events.py -q` (from `hub/`) → 19 passed, run
  immediately after writing the tests, before any implementation existed (confirmed the
  contract was genuinely failing first — all 19 failed with `AttributeError:
  'SSEManager' object has no attribute 'subscribe_operator'` / `KeyError: 'token'`).
- `py -3.11 -m pytest tests/test_operator_events.py -q` again after implementing
  `sse.py`/`auth.py`/`events.py`/`__init__.py`/`projects.py` → 19 passed.
- `py -3.11 -m pytest tests -q` (from `hub/`) → 581 passed, 7 skipped (both after the
  backend commit and again after the frontend commit — unchanged).
- `py -3.11 -m black <6 backend files>` + `py -3.11 -m ruff check <same>` → clean (one
  import-sort auto-fix in `api/v1/__init__.py` via `ruff check --fix`).
- `npx tsc --noEmit` (from `hub/ui/`) → clean, after fixing the 25 errors the migration
  introduced (`selectedProjectId` rename across ~15 test fixtures, 2-arg `setConfig`,
  `import.meta.glob` type fix, `never`-narrowing fix).
- `npx vitest run` (from `hub/ui/`) → 322 passed, 39 test files passed, 0 failed. **10
  "Errors" reported separately** (unhandled promise rejections, not test failures) —
  real `fetch()` calls escaping to the network (`ECONNREFUSED`/`ENOTFOUND hub.test`) from
  `App-mount.test.tsx` and `conversationShell.test.tsx`, which mount the real `App`
  component and set `bootstrapState: 'ready'` directly without mocking `fetch` at all, so
  `useAgents()` (a real, unmocked hook, `enabled: isConfigured && !!projectId` — both true
  in these fixtures) fires a genuine network request. **Not confirmed whether this predates
  this session** — the `git stash` dead-end above was an aborted attempt to check this
  safely and was abandoned after the near-miss. Given `useAgents()`'s old `enabled:
  isConfigured` gate (no projectId requirement) would already have been true in the same
  fixtures before this session's changes, this is very likely pre-existing, unrelated test
  hygiene debt — but that is an inference, not a verified fact.
- `npm run build` (from `hub/ui/`) → clean, both mid-session (before phase 4) and again
  after phase 4's frontend changes. Pre-existing warning (`eventSummary.ts` duplicate
  `switch` case) unrelated to this session's changes.
- `npm run lint` → still fails with "ESLint couldn't find an eslint.config.js" — confirmed
  pre-existing (ESLint v9 flat-config migration never done), documented in this branch's own
  task 3.7 handoff before this session started. Not this session's concern.
- **Live, against the actually-running native Hub** (`testbed/verify-2026-08-04`, restarted
  mid-session to pick up backend changes):
  - `GET /api/v1/projects` with the bootstrap operator key → 200, returned the one
    registered project (`proj-default`) with its 2 seeded agents.
  - `POST /api/v1/projects/open` with a second, previously-`mkdir`'d empty directory
    (`testbed/verify-2026-08-04-second`) → 200, created `proj-e42b0e9f`.
  - `POST /api/v1/projects/proj-default/tasks` → 201; `GET
    /api/v1/projects/proj-default/tasks` → contains the new task; `GET
    /api/v1/projects/proj-e42b0e9f/tasks` → `[]` (empty) — confirmed cross-project task
    isolation live, not just in tests.
  - `curl -N http://localhost:8000/api/v1/events -H "Authorization: Bearer <key>"`
    backgrounded with a 4s timeout, while POSTing a new task to `proj-default` — captured
    the real wire frame: `event: task_created` /
    `data: {"id":"task-...","title":"sse curl check","project_id":"proj-default"}`. Confirms
    the server-side stamping end-to-end over a real socket, not just through the ASGI test
    client.
  - Rebuilt the static UI bundle and confirmed via `curl` that the running Hub serves the
    new JS/CSS hashes.

**Not tested this session:** the frontend against the live Hub through an actual browser (no
browser-driving tool was available/used this session — all frontend verification was
`vitest`/`tsc`/`npm run build` plus the backend-only live curl checks above). Phase 5 (rail,
URL navigation, project tabs) is entirely unbuilt, so there is currently no UI affordance to
actually switch `selectedProjectId` by hand — it is only set via `bootstrap()`'s auto-select
or the `SetupModal`'s manual override field.

## Git state

- Branch `hub-native-experience`; HEAD is `e7e2b6e`.
- Two new commits since previous handoff (`b4f86fa`):
  - `7f2897c` local multi-project workspace phase 4.1/4.2: operator SSE stream
  - `e7e2b6e` local multi-project workspace phase 4.3-4.7: frontend project identity
- Worktree still has many pre-existing modified/untracked files from phases 0–3 (see `git
  status --short`); nothing new was added by this chunk beyond the committed files above and
  this handoff itself.
- `.claude/handoffs/LATEST.md` is modified (session-end scratch) and must not be committed.
- No upstream configured.
- Two extra local test projects exist on disk from live verification:
  `testbed/verify-2026-08-04` (bound to `proj-default`) and
  `testbed/verify-2026-08-04-second` (bound to `proj-e42b0e9f`) — both under `testbed/`, safe
  to leave or delete freely per `testbed/README.md`.
- The native Hub is currently running (PID 24604, port 8000, started from
  `testbed/verify-2026-08-04`) with this session's backend code loaded.

## Next steps

1. Move to phase 5 ("URL navigation, rail, tabs, and project management"): re-read
   `openspec/changes/2026-08-03-local-multi-project-workspace/proposal.md`, `design.md`, and
   all three delta specs (`specs/local-project-workspace/spec.md`,
   `specs/app-lifecycle/spec.md`, `specs/agent-conversation-workspace/spec.md`) as required
   by `tasks.md`'s own working protocol, then write phase 5's failing tests first (task 5.1:
   URL/navigation tests for reload, back/forward, invalid project fallback, project
   switching, direct agent conversation, no provider session IDs).
2. Before phase 5 starts, optionally resolve the unconfirmed pre-existing-vs-new question
   about the 10 unhandled-rejection test errors (see Verification) — e.g. by mocking
   `globalThis.fetch` in `App-mount.test.tsx`/`conversationShell.test.tsx`'s `beforeEach`, or
   by checking whether the same errors appear against the last phase-3 commit via `git show
   b4f86fa:hub/ui/src/__tests__/App-mount.test.tsx` diffed against current, without a working
   `git stash`.
3. When context fills up, run `/handoff` again; otherwise continue directly into phase 5.

## Open questions for the user

None. Phase 4 is complete and the user has already said "move on" for this phase; phase 5 is
the natural next unit per `tasks.md`'s own ordering.

## Read on resume

- `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md` — phase 5 checklist
  (5.1–5.10).
- `openspec/changes/2026-08-03-local-multi-project-workspace/specs/local-project-workspace/spec.md`
  — lines 173–199, "Project views live inside the selected project" — the concrete
  requirement phase 5 implements (rail = projects + their live agents only; Tasks/Spec/Jobs/
  Activity/Environment become tabs, not rail rows).
- `hub/ui/src/lib/navigation.ts` — `WorkspaceDestination`/`projectDestination`/
  `agentDestination` already exist as pre-built scaffolding `App.tsx` already partially uses;
  worth checking before assuming phase 5 starts from nothing.
- `hub/ui/src/api/projects.ts` — `useProjects()` is already built and unused by any UI; it is
  what phase 5's rail will consume directly.
- `hub/ui/src/store/configStore.ts` — `selectedProjectId`/`setSelectedProject` are the
  primitives phase 5's rail will call; no rail UI calls `setSelectedProject` yet.
