# Handoff: Surface waiting_reason on queued triggers; Phase 9 up next

**Date:** 2026-08-02T13:30:00+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `5e730fa`
**Agent:** Claude Sonnet 5
**Previous handoff:** `.claude/handoffs/2026-08-02-1130-phase8-mock-fidelity-and-live-test-env.md`
**Status:** chunk complete

## Goal

Ship the `hub-native-experience` OpenSpec change in
`openspec/changes/2026-07-30-hub-native-experience/`. This session resumed from the previous
handoff, confirmed its "update LATEST.md" next-step was already done, then closed out that
handoff's Open Question #1: the frontend silently swallowed a Hub trigger's `waiting_reason`
whenever a `POST /agent/trigger` returned HTTP 200 but the input actually just got queued
instead of run — the root cause of the earlier "sent a message to codex and nothing happened"
report. The user chose to fix this now rather than defer it, then move to Phase 9.

## Current state

**The waiting_reason gap is fixed and committed (`5e730fa`).** `postTrigger` in
`AgentOutputPanel.tsx` previously only checked `response.ok` and threw the body away; it now
parses and returns the JSON body (`TriggerAgentResponse` on the Hub side, `hub/hub/api/v1/
agent_trigger.py:99-107` — `status: "running"|"queued"`, `waiting_reason: Optional[str]`).
A new `queuedNotice(result, fallback)` helper returns a message only when `status === 'queued'`,
reusing the existing `sessionNotice` UI slot (the small text line above the composer,
`data-testid="session-continuity"`) rather than adding new chrome.

All three trigger call sites were updated, not just `handleSend` — the bug class (permanently
locked composer state when a trigger silently queues instead of running) applies to all of
them:
- `handleSend`: on `queued`, sets `Queued — <reason>` and, critically, clears
  `pendingNewSessionRef.current` for a `new`-session send — without this, the "wait for a new
  session id to appear" tracking set up earlier in the same function would hang forever (nothing
  is going to run to produce one), permanently locking the composer via `isBindingNewSession`.
- `handleDeliverNow`: on `queued`, sets `Still queued — <reason>`.
- `handleHandoff`: on `queued`, resets `handoffState` back to `'idle'` (was left stuck in
  `'preparing'` forever otherwise, since nothing runs to produce the completion signal it waits
  for) and sets `Could not start handoff — <reason>`.

**A real, unrelated test bug was found and fixed while verifying this**: `agentHandoff.test.tsx`
mocked `fetch` with `fetchMock.mockResolvedValue(new Response('{}', { status: 200 }))` — a
single shared `Response` instance reused across all 3 trigger calls in that test. `Response.
json()` can only be read once per instance; before this session, nothing called `.json()` on the
trigger response, so the shared-instance mock happened to work. Now that `postTrigger` calls
`.json()`, the 2nd and 3rd calls in that test threw `TypeError: Body is unusable: Body has
already been read`, silently caught by `handleSend`'s catch block, which cleared
`pendingNewSessionRef` and broke the test's session-binding assertions. Fixed by switching to
`fetchMock.mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ status:
"running" }), { status: 200 })))` — a fresh `Response` per call, with an explicit `"running"`
status so the new `queuedNotice` branch stays inert for this test (matches its original intent).

## Files touched

- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — `postTrigger` now returns
  `Promise<TriggerResult>` (parses `response.json()`); new `TriggerResult` interface and
  `queuedNotice` helper; `handleSend`/`handleDeliverNow`/`handleHandoff` all branch on a
  `queued` result. Finished, committed in `5e730fa`.
- `hub/ui/src/__tests__/agentHandoff.test.tsx` — fetch mock changed from a single shared
  `Response` (`mockResolvedValue`) to a fresh one per call (`mockImplementation`) carrying an
  explicit `{status: "running"}` body, so `.json()` doesn't throw on repeat calls. Finished,
  committed in `5e730fa`.
- `.claude/handoffs/2026-08-02-1330-waiting-reason-fix-and-phase9-next.md` — this handoff.
- `.claude/handoffs/LATEST.md` — **not yet updated to point here** — first action of the next
  session, per Next steps.

## Key decisions

1. **Reused the existing `sessionNotice` UI slot rather than adding a dedicated banner/toast.**
   It already exists for exactly this purpose (transient status text near the composer:
   "Starting new conversation…", "Failed to send message", etc.) — consistent with the
   project's "no premature abstraction" instruction in `CLAUDE.md`.
2. **Fixed all three `postTrigger` call sites, not just `handleSend`.** The user only reported
   the bug via `handleSend`'s path, but `handleDeliverNow` and especially `handleHandoff` have
   the exact same latent hang: `handleHandoff` in particular would leave `handoffState`
   permanently stuck at `'preparing'` (spinner icon, notice text "Preparing durable handoff…"
   forever) if its trigger got queued instead of run. Judged this as directly in-scope for "fix
   the waiting_reason gap," not scope creep, since it's the same root cause in the same function
   family.
3. **The test mock fix (`agentHandoff.test.tsx`) is a genuine bug in the test, not a workaround
   for the app change.** `Response.json()` being single-read is a real Fetch API constraint;
   reusing one `Response` instance across multiple calls to the same mocked `fetch` was already
   fragile, just previously unexercised because nothing called `.json()`. Chose to fix the mock
   properly (fresh `Response` per call via `mockImplementation`) rather than adding a workaround
   to `postTrigger` (e.g. `response.clone()` — would have masked a bad test, not fixed it).

## Constraints and user directives (verbatim)

- "$resume Review the changes of phase 5 and execute phase 6" (original chain-start directive —
  still the operative instruction to keep working through phases/corrections in order).
- "Yeah and always commit the changes." — commit each completed chunk without asking first
  (also independently recorded in persistent memory, `feedback_always_commit_checkpoints.md`).
- "After every threshold of implementation you must run the skill `/handoff`."
- "Only stop if there is actually a blocking issue... don't need to be conservative on the
  changes... if there is genuinely a best approach you can scrap anything that already exists."
- User answered the resume-time `AskUserQuestion` with **"Fix waiting_reason gap first"**
  (over "Move to Phase 9") — the directive that started this session's work.
- Do not tear down the persistent test environment (Hub/Vite/scratch project) without asking
  first — the user is actively using it (carried forward from the previous handoff, still true).
- Do not re-wipe the shared Hub data directory (`~/.agentweave/hub/data`) without checking first
  — it now also holds this session's live-verification conversation (see Verification).

## Dead ends

- None new this session. (Carried forward from the previous handoff, still relevant if this
  class of issue resurfaces: the `codex`→`claude` `send_message` routing anomaly — a codex-CLI-
  side `live agent path '/root/claude' not found` internal error — was not investigated further
  this session and remains an open aside, not a Hub bug per the previous handoff's diagnosis.)
- The browser preview-automation tool (`mcp__t3-code__preview_*`) intermittently returns
  "Preview automation {evaluate,...} failed on client ..." — reconfirmed this session on both
  the original tab and a freshly opened one. This looks like a client-side/transport issue in
  the automation tool itself right now, not a per-tab staleness problem (the documented "open a
  fresh tab" workaround from the previous handoff did not resolve it this time). When it failed,
  fell back to `curl`-ing the Hub API directly with the recorded API key — that path worked
  reliably and is the better first choice for this kind of live-verification anyway.

## Verification

Ran and passed:

- `cd hub/ui; npx tsc --noEmit` — clean, both before and after the test-mock fix.
- `cd hub/ui; npx vitest run` — **223/223 passed, 26/26 files** (one initial run had 1 failure
  in `agentHandoff.test.tsx` from the shared-`Response` mock bug described above; fixed, then
  reran clean).
- Live-verified against the persistent test Hub (`http://localhost:8000`) + Vite dev server
  (`http://localhost:5173`) left running from the previous session: opened the real dashboard in
  a browser, selected the `claude` agent, typed a real message ("Resume-verification ping: reply
  with \"ack\" and nothing else.") into the composer, clicked Send. Confirmed via direct `curl`
  to `GET /api/v1/agents` that `claude`'s status flipped to `"running"` with a real session id
  (`75320140-3cbc-4617-9720-148f308d87de`) and rising context-token usage, and via `GET
  /api/v1/agent/claude/chat/{session_id}` that the run produced real tool-call output (it invoked
  its own `aw-collab-start` skill and started reading `roles.json`/`agentweave.yml` in its
  worktree) — i.e. the JSON-body-parsing change to `postTrigger` does not break the normal
  (non-queued) trigger path end-to-end against a real spawn, only the previously-silent `queued`
  case changed behavior.

Not tested:

- The `queued` branch itself (the actual new notice text: "Queued — ...", "Still queued — ...",
  "Could not start handoff — ...") was **not** exercised live in the browser this session — no
  queued/stuck state existed in the live test conversation to trigger it against (both `claude`
  and `codex` were launchable). It is covered by `agentHandoff.test.tsx`'s existing assertions
  only in the sense that the test now returns `"running"` explicitly and passes; there is no new
  unit test asserting the queued-branch notice text itself. If this needs airtight coverage, add
  a test that mocks a `{status: "queued", waiting_reason: "..."}` response and asserts the
  `session-continuity` text.
- Dark theme was not re-checked this session (last checked two handoffs ago, before this
  session's changes — which don't touch styling at all, so low risk, but not re-verified).
- Did not re-attempt the `codex`→`claude` `send_message` routing anomaly from the previous
  handoff.

## Git state

- Branch: `hub-native-experience`.
- HEAD: `5e730fa Surface waiting_reason when a trigger queues instead of running`.
- Working tree: clean relative to HEAD. Untracked (pre-existing, not part of this session's
  work, do not stage): every `.claude/handoffs/*.md` file except this one and its immediate
  predecessor, plus `.claude/skills/aw-spec-reindex/`.
- `.claude/handoffs/LATEST.md` still points at the previous handoff
  (`2026-08-02-1130-phase8-mock-fidelity-and-live-test-env.md`) as of this write — update it to
  this file as the very first action of the next session, per Next steps.
- No upstream tracking branch configured; nothing pushed.
- **Outside this repository**, the persistent test environment from the previous session is
  still running and now has additional live-verification traffic on it from this session:
  - Native Hub at `http://localhost:8000` (still up, confirmed responsive this session).
  - Vite dev server at `http://localhost:5173` (still up, confirmed responsive this session).
  - Scratch AgentWeave project at `C:\Users\huida\AppData\Local\Temp\aw-phase8-test` — unchanged
    git repo, roster `claude` (colour index 0) + `codex` (colour index 1, `yolo: true`).
  - Hub API key: `aw_live_71b0560849ca74d02b882593ad4d10b1` (also in that project's
    `.agentweave/transport.json`).
  - `claude` was actually running (spawned by this session's live verification, session id
    `75320140-3cbc-4617-9720-148f308d87de`, run `run-f108231d`) as of this handoff's write time
    — it may still be mid-turn or may have completed by the time the next session reads this;
    check `GET /api/v1/agents` before assuming either way.

## Next steps

1. Update `.claude/handoffs/LATEST.md` to point to this file
   (`2026-08-02-1330-waiting-reason-fix-and-phase9-next.md`), then commit it alone (matches the
   established "checkpoint" commit precedent).
2. Re-read `openspec/changes/2026-07-30-hub-native-experience/tasks.md` starting at Phase 9
   ("Accounting and budgets") — this is genuinely the next unstarted phase now; both correction
   chunks (mock-fidelity revision, waiting_reason fix) that were blocking it are done.
3. Optional, not blocking: if stronger regression coverage is wanted for the `queued` branch
   specifically, add a test in `agentHandoff.test.tsx` or a new file that mocks a `{status:
   "queued", waiting_reason: "..."}` trigger response and asserts the `session-continuity`
   notice text and that the composer does not lock up (`isBindingNewSession`/`handoffState`
   stay resolvable).
4. Do not tear down the persistent test environment (Hub/Vite/scratch project) without asking
   first — still true, unchanged from the previous handoff.

## Open questions for the user

- None outstanding from this session. (The previous handoff's other open question — the
  `codex`→`claude` routing anomaly — remains open but was not addressed here; carry it forward
  if it resurfaces.)

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — Phase 9 ("Accounting and
  budgets") onward; this is the next actual work.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — the just-fixed trigger/notice logic;
  read before touching `postTrigger` or any of its three call sites again.
- `hub/hub/api/v1/agent_trigger.py` — `TriggerAgentResponse` (lines 99-107) and `trigger_agent`
  (lines 352-424) for the exact `status`/`waiting_reason` contract the frontend now consumes.
- `openspec/changes/2026-07-30-hub-native-experience/mock.html` — still the authoritative visual
  reference for any further Hub UI work in this change.
