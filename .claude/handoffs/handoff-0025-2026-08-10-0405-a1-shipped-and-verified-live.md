# Handoff: A1 shipped and demonstrated live, and four stuck verification tasks unstuck

**Date:** 2026-08-10T04:05 · **Branch:** hub-native-experience · **HEAD:** `1b0b7cf`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0024-2026-08-10-0230-ci-green-and-the-spec-program-reconciled.md`
**Status:** complete. 5 commits, all pushed. **Working tree clean.**

## Goal

The operator approved A1 in one line — *"spec approved. I'm going to sleep Implement everything non
stop. Tomorrow I'll take a look."* — and went to bed. So: implement `2026-08-10-one-chat-surface`
end to end, verify it rather than assert it, and then keep going on whatever else was unblocked.

**A1 is done: all of sections 1–5 and 7, including the three live checks.** After that, the two
nearly-done changes' five stuck manual-verification tasks were taken on (handoff 0024's next-step
4); four of the five moved.

## Current state

### Shipped: A1, one chat surface (`54acb7f`, `a8940ce`, `5d37135`, `6ccdea0`)

`SpecChatPane.tsx` is deleted. `SpecChat.tsx` picks the agent, resolves which of that agent's
conversations is on screen, and mounts `AgentOutputPanel` — so the composer, banner stack,
permission card, question card, checkpoint warning and stream-loss notice all work on the Spec page
because they are not written twice. Both bespoke trigger paths are gone, along with
`execution_confidence`, `QUEUED_START_TIMEOUT_MS`, and the second copy of the watchdog error string.

The "Repair manifest" button is removed; the drift **report** stays. `SpecWorkspace`'s fixed
260/520/360 is now the shared `PaneResizer`, with persisted widths.

### The one design change the proposal did not anticipate

**A1 needed migration `0051`** after `proposal.md` said "no migration". The trigger route queues an
`InboundQueueEntry` and *then* asks the scheduler to start a turn, so a busy agent's turn begins
later, from a different call, out of the request that carried the document. Passing `spec_document`
straight through would have dropped it for exactly the queued case the queue exists to serve — and
"why does this say that?" is unanswerable without the document it was sent about. It rides
`InboundQueueEntry.spec_document` next to `work_dir`; the scheduler reads it from the controlling
operator entry. Recorded in `tasks.md` 2.2.

### Also: the contrast finding (`1b0b7cf`) — **this one needs the operator**

Charcoal task 8.9 said "no automated contrast-checking tool available". That was wrong — WCAG 2.1
relative luminance is arithmetic. Computed across both ramps and every surface, cross-checked
against 54 live elements:

**`--text-3` fails AA for normal text on every surface in both modes** (2.28–3.24). It is not
decorative — timestamps, the session-continuity line, composer placeholders and status labels use
it. 28 of 54 elements on one page. Light mode also puts `--green` and `--amber` under 4.5, and
under 3.0 on `--surface-3`.

**The reason this is a decision and not a fix:** reaching 4.5 needs `--text-3` at `#8c8c96`, which
is one step off today's `--text-2` (`#8e8e98`) — **AA at 4.5 collapses the three-level neutral text
ramp into two**, and the ramp is what the charcoal refresh was for. Meeting 3.0 instead needs only
`#6f6f79` (dark) / `#85858f` (light) and preserves all three levels. Written up as new task **8.11**
with every number solved. Nothing was changed: relighting the product overnight is not an agent's
call.

### Live environment — changed since last handoff

Hub **running on http://localhost:8010**, project **`proj-cddb0827`**, API key
`aw_live_58ab7d84a1bf7b34eb2d1b424875bacd` (header: `Authorization: Bearer <key>`).

**The Hub process was restarted this session** — it was serving pre-change code, so the new
`spec_document` field and migration `0051` could not be verified against it otherwise. Restarted
identically, from `hub/`:

```bash
cd hub && python -m uvicorn hub.main:app --host 127.0.0.1 --port 8010
```

Logs go to `testbed/hub-8010.log` / `.err`. Startup runs the alembic upgrade, so the live DB is at
**0051** and `inbound_queue_entries.spec_document` exists.

**Live state left behind, all deliberate:** `spec/a1-probe.html` still present; three real runs on
`claude-1` (a document question, a permission probe, an `ask_user` probe), all `completed`;
`permission-probe.txt` written into `claude-1`'s worktree by the approved tool call; the Spec
navigation pane persisted at **268px** from the resizer check. `claude-1`'s conversation-level
permission override is back at **Edit files**.

## Files touched

Everything **committed and pushed**; `git status --short` is empty.

### Backend (`54acb7f`)

- `hub/hub/api/v1/agents.py` — `_render_hub_agent_context(spec_document=...)`; renders an "Open
  specification document" block, and only when a `ProjectSpec` row for that path exists.
- `hub/hub/api/v1/agent_trigger.py` — `TriggerAgentRequest.spec_document` with a `field_validator`
  reusing `validate_spec_path`; threaded through `trigger_agent_directly` and onto the queue entry.
- `hub/hub/db/models.py`, `hub/hub/inbound_queue.py`, `hub/hub/turn_scheduler.py` — the column, the
  `new_entry` parameter, and the scheduler reading it from the controlling operator entry.
- `hub/hub/migrations/versions/0051_add_queue_entry_spec_document.py` — new, guarded like 0038–0050.
- `hub/tests/test_spec_document_context.py` — new, 7 tests.
- `hub/tests/test_migrations.py`, `hub/tests/test_project_persistence.py` — head 0050 → 0051.

### Frontend (`a8940ce`, `1b0b7cf`)

- `components/spec/SpecChatPane.tsx` — **deleted.**
- `components/spec/SpecChat.tsx` — **new.**
- `components/spec/SpecPage.tsx` — repair machinery, `startNewSession`, and the second trigger gone.
- `components/spec/SpecWorkspace.tsx` — two `PaneResizer`s, measured-width budgeting,
  `useWorkspaceWidth` extracted, `SPEC_WIDE_BREAKPOINT` now **derived** (1140 → 1142; the two 1px
  dividers made the old constant two pixels short, which silently narrowed the nav pane).
- `components/spec/specPreferences.ts` — `navWidth` / `chatWidth`, clamped on read and write.
- `components/layout/PaneResizer.tsx` — optional `containerRef` and `side`; the rail's call site is
  unchanged and behaves identically.
- `components/agents/AgentOutputPanel.tsx` — optional `specDocumentPath` → `spec_document`.
- `components/accounting/AccountingPanel.tsx` — reports both outcomes (task 4.7).
- Tests: `specChatSession.test.tsx` deleted → `specChatSurface.test.tsx` (12);
  `specManifestRepair.test.tsx` → `specDriftReport.test.tsx` (repair tests dropped, report tests
  kept); `specWorkspace.test.tsx` +resizers/persistence; `specNavigationUi.test.tsx` stubs
  `SpecChat`; `accountingPresentation.test.tsx` +7.
- `hub/hub/static/ui` — rebuilt twice, `diff -rq` clean both times.

### Specifications (`6ccdea0`, `1b0b7cf`)

- `openspec/changes/2026-08-10-one-chat-surface/` — `proposal.md` approved; `design.md` gained the
  reproducible fixture command; `tasks.md` fully recorded; the delta gained a **REMOVED** section.
- `openspec/specs/spec-chat-session/spec.md` — synced.
- `openspec/changes/2026-08-04-hub-charcoal-visual-refresh/tasks.md` — 8.8/8.9/8.10 rewritten, 8.11
  added.
- `openspec/changes/2026-08-04-hub-contextual-navigation/tasks.md` — 4.7 closed, 7.7 rewritten.

## Key decisions

1. **`SpecChat` mounts `AgentOutputPanel` whole rather than re-composing `Composer` + `BannerStack`.**
   The requirement is "MUST NOT implement its own message input, run trigger, or output rendering".
   Re-composing the parts would have been a third arrangement of them to keep in step; mounting the
   surface makes drift impossible. It is deletion and reuse, which is what A1 was scoped to be.
2. **The document is rendered only when the Hub can confirm it exists.** The operator can only be
   looking at something the inventory listed, so a path resolving to no row is a stale client value
   — and naming it is the guess the requirement forbids.
3. **The migration, over losing the value on a queued turn.** See above.
4. **`SPEC_WIDE_BREAKPOINT` is derived, not written down.** A breakpoint meaning "the panes no
   longer fit" should be computed from what has to fit, or a default change leaves the two
   disagreeing — which is exactly what happened when the dividers landed.
5. **Side panes are budgeted against the *measured* workspace.** `PaneResizer`'s static min/max
   cannot know how much room there is; at the breakpoint, dragging navigation to its 420 ceiling
   would have pushed the document 100px below its minimum. Live, `aria-valuemax` read **346**.
6. **A stored width that no longer fits is clamped for rendering, not written back.** Narrowing the
   window must not silently discard the width chosen for a wide one.
7. **The `spec-chat-session` delta gained a REMOVED section it should have had at authoring time.**
   Its three original requirements mandated `session_mode: "resume"` resolved by the watchdog, a
   Spec-tab new-session control, and a Spec-tab continuity indicator. Syncing only the ADDED
   requirements would have left a spec file asserting behaviour deleted a week ago. What those
   requirements protected survives — on the one conversation surface, where it cannot drift.
8. **The contrast remediation was not applied.** Decision recorded, numbers solved, choice left.
9. **4.7 was fixed rather than described**, because it was a real gap; the *uniformity* half of it
   is a consistency pass that belongs to B5 rather than holding the change open.

## Constraints and user directives (verbatim)

**From this session:**
- *"spec approved. I'm going to sleep Implement everything non stop. Tomorrow I'll take a look."*

**Carried and still binding:**
- **STANDING DIRECTIVE:** *"when creating the spec we have to think how to manually test this…"* —
  applied throughout: `tasks.md` §6 reports all five human items **UNRUN** with the testbed left
  ready, and the four unstuck tasks were rewritten into the same *do this → expect this → failed if
  this* form.
- *"Kind of lost"* — **the operator is sensitive to volume.** Answer briefly; point at one file.
- *"What is taking so long?"* — sensitive to wall-clock. `pytest hub/tests/` ~4:11;
  `npx vitest run` ~13s; `npm run build` ~4s.
- *"The spec should still be generated as html"*; *"no need for backups everything is test env"*;
  *"B. fixed back to the agent's conversation. Yes, no agent deletion. Just archive."*;
  *"I don't want it to be colorful it should be like the chat box but maybe a little lighter"*.
- From `CLAUDE.md`: never create `.agentweave/`, `agentweave.yml` or `spec/` at the repo root; stage
  paths explicitly; openspec never aw-spec skills; `Icon` is the only icon system;
  `approve_tool_call` keeps **no return annotation**; `hub/hub/static/ui` is a committed artefact
  refreshed after `npm run build` and confirmed with `diff -rq`; never mark a task complete on the
  strength of a plan existing.
- From memory: commit each completed checkpoint without asking; live-verify prior claimed work on
  resume; ask the operator for agent + model choice when setting up agents.

## Dead ends

**New this session:**
- **The `t3-code` preview tools return a schema-validation error on every mutating call**
  (`preview_type`, `preview_click`, `preview_press`) — *and the action usually happened anyway.*
  Never trust the error; **verify with `preview_evaluate` afterwards.** `type` and `click` both
  worked; **`press` did not** — a synthetic `Tab` from a focused text area left `activeElement`
  unmoved, which is what still blocks charcoal 8.8.
- **`preview_resize` times out** (tried 15s and 40s). The viewport stayed 1280×800 all session; that
  is still wide enough for the Spec workspace (measured 1228 ≥ 1142).
- **`preview_evaluate` must return an object.** Returning a bare array fails schema validation —
  wrap it: `{ hits: [...] }`.
- **Do not set `document.documentElement.dataset.mode` by hand to test light mode.** The app owns it
  (`App.tsx:92`) and the page ends up in a mixed state — light text tokens over dark backgrounds —
  giving nonsense contrast numbers. Compute ramp ratios from `index.css` in Python instead; it is
  deterministic and faster.
- **`sed -n` on `hub/hub/db/engine.py` combined with a `find /` in one command hit the 120s Bash
  timeout.** Do not put a filesystem-wide `find` in a compound command.
- **`cd hub/ui` fails from the Bash tool** even at the repo root — use the absolute path.

**Carried and still true:**
- **PowerShell here-strings break on bash-style quote escaping.** Use the Write tool for a commit
  message file, then `git commit -F <file>`. Worked every time again this session.
- **PowerShell cwd persists between calls.** Always `Set-Location` to the repo root first.
- **The spec API is at `/api/v1/projects/{id}/project/specs`**, not `/api/v1/specs`.
- **`ORDER BY EventLog.id` does not order by recency** — order by `timestamp`.
- **`openspec` CLI cannot handle date-prefixed change names for sync/archive.** Do it by hand.
  `npx openspec validate <name> --strict` does work.
- **`openspec validate` wants SHALL/MUST on the *first line* of a requirement body.**
- **`npm run lint` does not work at all** (ESLint 9 needs a flat config the repo lacks); `tsc` checks.
- **`pytest hub/tests/ tests/` together fails collection** — run separately.
- **The default `python` on PATH has no pytest** — use
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **`hub/tests/conftest.py` forces in-memory SQLite** — safe to run tests with the Hub up.
- **The Hub API rejects `X-API-Key`** — use `Authorization: Bearer <key>`.
- **`black --check` emits a stderr warning** about py312 parsing. Exit code is still 0. Not a failure.
- **Adding a hook to a component breaks every test that mocks that api module.** This bit hardest
  this session: mounting `AgentOutputPanel` inside `SpecPage` would have forced ~12 api mocks into
  two navigation test files. **Stubbing `@/components/spec/SpecChat` in those files is the fix** —
  they are about navigation, and the chat has its own suite.

## Verification

**Ran, with real output:**
- `pytest hub/tests/` — **1280 passed, 10 skipped** (4:11). Was 1273; +7 from `test_spec_document_context.py`.
- `pytest tests/` — **372 passed, 3 skipped.**
- `npx vitest run` — **661 passed / 73 files.** Was 640 / 73.
- `npx tsc --noEmit` — **clean, exit 0.**
- `ruff check src/ hub/ tests/` — **All checks passed!**
- `black --check src/ hub/hub/ hub/tests/ tests/` — **288 files unchanged.**
- `mypy src/` — **no issues in 22 source files.**
- `npx openspec validate --specs --strict` — **27 passed, 0 failed.**
- `npx openspec validate 2026-08-10-one-chat-surface --strict` — **valid.**
- `npm run build` + `diff -rq hub/ui/dist hub/hub/static/ui` — identical (twice).

**Live, in a real browser against `:8010` — the three that matter:**
- **5.6** A message sent from the Spec page produced `entry-8196942f` carrying
  `spec_document="spec/a1-probe.html"`; the materialised `.agentweave/context/claude-1.md` contained
  the "Open specification document" block; the run reached `completed`; the agent replied *"The
  specification document is `spec/a1-probe.html`"*. The context reached the model, not just the disk.
- **5.7** Under "Ask me" set from the Spec page's own composer, a `Write` attempt rendered
  `perm-ff497133` **inside `[data-testid="spec-chat-pane"]`**. Allowing it there took the request to
  `allowed` / `decided_by=operator`, wrote `permission-probe.txt`, and completed the run. *This is
  the defect A1 exists to fix, demonstrated rather than asserted.*
- **5.8** `ask_user` blocked a run; `q-672c346b` rendered in the Spec chat pane with both options and
  the composer placeholder became "Answer claude-1…"; clicking *Yes* returned the answer to the
  waiting run (*"The answer is: **Yes**"*).

**Also live:** workspace `data-mode="wide"` at 1228px with two dividers; nav divider
`aria-valuemax="346"` (budgeted, not the static 420); document pane held 598px; keyboard resize
persisted `navWidth: 268` and **survived a reload**.

**Explicitly NOT verified — do not assume:**
- **All five human-only items remain UNRUN**, in both changes. A1 §6.1's reload clause was verified;
  its pointer-feel clauses were not and are not claimed.
- **CI has still never run on this branch.** `ci.yml` triggers only on push/PR to `master`. Now
  **327 commits** with no Linux, no macOS, no Python 3.8/3.9/3.10/3.12. Green locally on
  Windows/3.11 only.
- **Migration 0051 has only been applied to SQLite**, on the live testbed DB and in-memory in tests.
- Carried: no live agent has called `submit_checkpoint_notes` or `recall`; `files_changed` has never
  been observed non-empty; the checkpoint final-warning banner has never been seen in a browser.

## Git state

Branch `hub-native-experience`, HEAD **`1b0b7cf`**, **working tree clean, everything pushed.**
**327 commits ahead of master, 0 behind.**

**5 commits this session**, `f317310..1b0b7cf`:

| sha | what |
|---|---|
| `54acb7f` | The agent is told which specification document the operator is looking at |
| `a8940ce` | One chat surface: the Spec page stops being a second application |
| `5d37135` | Rebuild the committed UI bundle so the Hub serves the one chat surface |
| `6ccdea0` | Close A1: record what was verified, and stop the spec describing a deleted watchdog |
| `1b0b7cf` | Unstick four of the five deferred verification tasks, and measure the ramp |

## Next steps

1. **Answer 8.11 — the contrast decision.** It is the only thing blocking the charcoal change from
   archiving, and it is a three-way look-and-feel call with the numbers already solved.
   `openspec/changes/2026-08-04-hub-charcoal-visual-refresh/tasks.md`, task 8.11.
2. **One reduced-motion sitting closes two tasks** (charcoal 8.10 and contextual-navigation 7.7 are
   the same check). Roughly five minutes with Windows animation effects off.
3. **One keyboard sitting closes A1 6.3 and charcoal 8.8.** Also both the same check.
4. **Archive `2026-08-04-hub-contextual-navigation`** once 7.7 is run — 4.7 is now closed, and it
   was the only other open item.
5. **Then A1 archives**, and Program A is complete.
6. **Program B needs its first proposal.** B0 is still blocked on the charter question below; **B1
   (task transition machine) is not blocked** and is the natural next proposal — handoff 0024's
   finding stands: `updated_by_run_id` is a single mutable column, so the schema cannot tell the run
   that completed a task from the run that approved it, and author/reviewer separation cannot be
   bolted onto existing columns.
7. **The `ci.yml` branch trigger** — raised three times now, unanswered. One line adding
   `hub-native-experience` to `on.push.branches`. It touches `master` not at all and is the only way
   the 3-OS × 5-Python matrix sees this branch before merge.

## Open questions for the user

1. **The contrast bar for 1.0** — AA 4.5 and lose the third text level, 3.0 and keep it, or a
   recorded exemption. Blocks the charcoal archive. (New; the most consequential of these.)
2. **The `ci.yml` branch trigger** — yes or no.
3. **How many charters, and which non-software domains should the starter set demonstrate?** The
   operator said to cut the 21; the target number and domain examples are undecided. **Still blocks
   B0.**
4. **Is "explore" a phase, or just the absence of one?** Affects B5's phase model.
5. **Should the propose offer come from the agent mid-turn, or from the machine at a threshold?**
6. Carried and still unanswered across ten handoffs: **should `.claude/handoffs/` stay tracked?**
7. Carried: the two model-less default runners on `proj-cddb0827`; `testbed/CHECKPOINT-TEST-GUIDE.md`
   still names the old project `proj-84d218db`; peer-thread grouping deferred 2026-08-08; titling
   should migrate onto the Worker.

## Read on resume

- `openspec/changes/2026-08-10-one-chat-surface/tasks.md` — **read this first.** What A1 did, what
  was verified and how, and the five human items with the testbed state they expect.
- `openspec/changes/2026-08-04-hub-charcoal-visual-refresh/tasks.md` task **8.11** — the contrast
  decision, with the full ratio table in 8.9 above it.
- `openspec/explorations/2026-08-10-specification-and-surface-program-roadmap.md` — the orientation
  document. Program A is now complete bar its human checks; B is next.
- `hub/ui/src/components/spec/SpecChat.tsx` — 120 lines, and the whole shape of A1.
- `openspec/explorations/2026-08-10-charters-phases-and-the-spec-on-ramp.md` — needed before B0 or B5.
- `openspec/explorations/2026-08-03-specification-authority-technical.md` — the technical design
  source for B2–B5. Long; read when B2 starts, not before.
