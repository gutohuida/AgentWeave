# Tasks — One chat surface

> Verification is split per the standing directive of 2026-08-10: section 5 is what the agent
> verifies, section 6 is the operator's guide. **A human-only item is never left as a bare
> unchecked box** — each carries steps, an expected result, and what failure looks like.

## 1. Fixture — make the Spec page renderable

- [x] 1.1 Confirm the Hub is running and the testbed project resolves.
      *Ran:* `/health` → `{"status":"ok"}`; project `proj-cddb0827` resolves.
- [x] 1.2 Push a spec document through `POST /api/v1/projects/{id}/project/specs/sync`. A probe
      document (`spec/a1-probe.html`) was pushed on 2026-08-10 and is present; re-push if the
      database was reset. *It was still present; no re-push needed.*
- [x] 1.3 Record the fixture command in the change so verification is reproducible.
      *`design.md` → "The fixture command, so verification is reproducible".*

## 2. Backend — the open document reaches the agent

- [x] 2.1 Extend `_render_hub_agent_context` to carry the document the operator is viewing, when the
      request supplies one. Absent value renders nothing — never a guess.
      *Also renders nothing when the path names no `ProjectSpec` row: the operator can only be
      looking at a document the inventory listed, so a stale path is a guess too.*
- [x] 2.2 Thread the value from the trigger request through to the render call in
      `agent_trigger.py`.
      **Amended:** the route queues an entry and asks the scheduler to start a turn, so the value
      could not be passed straight through — a busy agent's turn starts later, from a different
      call. It rides `InboundQueueEntry.spec_document` next to `work_dir`, and the scheduler reads
      it from the controlling operator entry. **This adds migration `0051`**, which the proposal
      said would not be needed. Keeping it only for the immediately-scheduled turn would have
      dropped it for exactly the queued case the queue exists to serve.
- [x] 2.3 Hub tests: context contains the document when supplied; contains no document line when
      not; identical for a `claude` and a `codex` runner.
      *`hub/tests/test_spec_document_context.py`, 7 tests — plus the unknown-path case, the
      stored-on-the-entry-not-in-the-message case, and the unsafe-path rejection.*

## 3. Frontend — one composer

- [x] 3.1 Replace the Spec workspace's chat pane with `Composer` + `BannerStack` over conversation
      history, dropping `useAgentOutput`. *`SpecChat.tsx` mounts `AgentOutputPanel`, so the whole
      conversation surface comes with it rather than a re-composed subset.*
- [x] 3.2 Delete `SpecChatPane.tsx` and its bespoke trigger, `QUEUED_START_TIMEOUT_MS`,
      `TriggerResponse`, and the dead `execution_confidence` branch.
- [x] 3.3 Pass `conversationId: null` for an agent with no conversation; let the first message create
      one. Do **not** set `origin` (design.md Decision 1).
- [x] 3.4 Pass the open document path to the trigger so task 2.2 can use it.
      *`AgentOutputPanel.specDocumentPath` → `spec_document` in the trigger body, omitted when null.*
- [x] 3.5 Delete the "Repair manifest" button, `buildRepairMessage`, `MAX_REPAIR_ITEMS`,
      `handleRepair`, and the second bespoke trigger path in `SpecPage.tsx`.
      *The drift **report** stays; only the button went.*
- [x] 3.6 Remove `startNewSession` from `SpecPage` if task 3.5 leaves it with no remaining consumer.
      *It did. Session continuity is the composer's, and it speaks in conversations.*
- [x] 3.7 Replace `SpecWorkspace`'s fixed widths with the shared `PaneResizer`, retaining
      `useWorkspaceMode` and the compact drawers (design.md Decision 5).
      *`PaneResizer` gained `containerRef` and `side` so it can size a pane that does not start at
      the viewport edge; the rail's call site is unchanged. Widths persist through
      `specPreferences`. Each side is budgeted against the measured workspace so neither can push
      the document below `SPEC_DOC_MIN_WIDTH`, and `SPEC_WIDE_BREAKPOINT` is now derived — it was
      exactly the three defaults, which the two new dividers made two pixels short.*
- [x] 3.8 Remove watchdog references in the touched files only (design.md Decision 6).

## 4. Tests

- [x] 4.1 Delete or rewrite `specChatSession.test.tsx` — 5 of its assertions cover watchdog
      behaviour that no longer exists. *Deleted; replaced by `specChatSurface.test.tsx` (12 tests).*
- [x] 4.2 Spec workspace tests: composer renders; sending creates a conversation; a question card
      renders and can be answered; a permission request renders and can be answered.
      *All four in `specChatSurface.test.tsx`, against the real components rather than stubs.*
- [x] 4.3 Update every test that mocks a now-unused api module.
      *`specManifestRepair.test.tsx` → `specDriftReport.test.tsx` (repair tests dropped, report
      tests kept); `specNavigationUi.test.tsx` stubs `SpecChat`; `specWorkspace.test.tsx` gains the
      resizer and width-persistence coverage.*

## 5. Agent verification — expected behaviour, run by the agent

- [x] 5.1 `npx vitest run` — **654 passed / 73 files** (was 640 / 73). +14 tests; two files deleted,
      two added.
- [x] 5.2 `npx tsc --noEmit` — **clean, exit 0.**
- [x] 5.3 `pytest hub/tests/` — **1280 passed, 10 skipped** (4:11). 1273 + the 7 added in 2.3.
- [x] 5.4 `ruff check src/ hub/ tests/` — **All checks passed!**
      `black --check src/ hub/hub/ hub/tests/ tests/` — **288 files unchanged.**
      Also `pytest tests/` — 372 passed, 3 skipped; `mypy src/` — no issues in 22 files.
- [x] 5.5 Grep proof: no `execution_confidence`, `queued_watchdog_healthy`, `buildRepairMessage`,
      `watchdog`, `QUEUED_START_TIMEOUT_MS`, `MAX_REPAIR_ITEMS`, `handleRepair` or `startNewSession`
      anywhere under `components/spec/`. `SpecChatPane` survives only in two comments that record
      what was removed and why.
- [x] 5.6 **Live.** Sent from the Spec page against `spec/a1-probe.html` in a real browser at
      `:8010`. `entry-8196942f` carried `spec_document="spec/a1-probe.html"`; the materialised
      `.agentweave/context/claude-1.md` contained the "Open specification document" block; the run
      reached `completed` and its output rendered in the pane. The agent answered *"The
      specification document is `spec/a1-probe.html`"* — the context reached the model, not just
      the file.
- [x] 5.7 **Live, and this is the defect the change exists to fix.** With Permissions set to
      "Ask me" from the Spec page's own composer, the agent attempted `Write`. `perm-ff497133`
      rendered **inside `[data-testid="spec-chat-pane"]`** as *"claude-1 wants to use Write"* with
      Allow/Deny. Allow was clicked on that page; the request went to `allowed` / `decided_by=operator`,
      `permission-probe.txt` was written with `ok`, and the run reached `completed`.
- [x] 5.8 **Live.** The agent called `ask_user` from the Spec page. `q-672c346b` blocked the run;
      the card rendered in the Spec chat pane with both options and the composer placeholder became
      "Answer claude-1…". Clicking *Yes* answered it, the answer returned to the waiting run
      (*"The answer is: **Yes**"*), and the run reached `completed`.
- [x] 5.9 `npm run build`, copied `hub/ui/dist` over `hub/hub/static/ui`, `diff -rq` → identical.
- [x] 5.10 `npx openspec validate --specs --strict` — **27 passed, 0 failed.**
      `npx openspec validate 2026-08-10-one-chat-surface --strict` — **valid.**

### Also verified live, beyond the list

- The Spec workspace reported `data-mode="wide"` at 1228px with **two** dividers present.
- The navigation divider exposed `aria-valuemax="346"` — budgeted from the measured workspace, not
  the static 420 ceiling — so the document pane could not be squeezed below its 520 minimum. It
  held 598px throughout.
- Keyboard resize moved the pane to 268px, persisted
  `{"chatCollapsed":false,"libraryMode":"library","navWidth":268,"chatWidth":360}`, and **the width
  survived a page reload.** That is 6.1's third clause; the first two are still pointer-feel and
  remain human-only.

## 6. Human test guide — what the agent cannot verify

> Each item: **do this → expect this → it failed if this.** Report the outcome; an unrun item is
> reported as unrun, never as passed.
>
> **Status: all five are UNRUN.** Available browser automation can dispatch events but cannot judge
> pointer feel, drive real focus traversal, or emulate reduced motion. The testbed is left ready:
> Hub on `:8010`, project `proj-cddb0827`, `spec/a1-probe.html` open, navigation width already at
> 268 from the automated check.

- [ ] 6.1 **Pane resizing feels right.** Open the Spec page on a wide window. Drag the divider
      between navigation and document, then between document and chat.
      *Expect:* the drag tracks the pointer with no lag or snap-back; each pane stops at a minimum
      that still shows usable content; the width survives a page reload.
      *Failed if:* a pane collapses to unusable width, the document reflows jarringly mid-drag, or
      the width resets on reload.
      *Partially covered:* the reload clause was verified live (268px survived). The pointer-feel
      clauses are yours.

- [ ] 6.2 **The Spec page reads as the same product as the agent page.** Open the agent conversation,
      then the Spec page, and switch between them a few times.
      *Expect:* the composer, its control row, and the message styling are indistinguishable between
      the two.
      *Failed if:* anything about the input area reads as a different generation of the product —
      different spacing, different control shapes, different colours.
      *Note:* they are now literally the same component, so a difference here is a layout or width
      problem, not a styling one — say which pane it appears in.

- [ ] 6.3 **Keyboard traversal of the composer inside the Spec workspace.** Click the document pane,
      then press Tab repeatedly.
      *Expect:* focus reaches the composer text area and every control in its row; each shows a
      visible focus ring; Shift+Tab reverses in the same order; focus never enters the document
      iframe and get stuck.
      *Failed if:* any control is unreachable, shows no focus ring, or traps focus.
      *Agent cannot run this — available browser automation cannot drive real focus traversal.*
      *New since this was written:* the two dividers are `tabIndex={0}` separators and now sit in
      that tab order. Check they are reachable and that arrow keys move them.

- [ ] 6.4 **Reduced motion.** Enable the OS reduced-motion setting, reload, and resize a pane and
      open a compact drawer.
      *Expect:* panes and drawers change state without animated transitions, and every state remains
      distinguishable.
      *Failed if:* transitions still animate, or a state becomes ambiguous once animation is removed.
      *Agent cannot run this — available automation emulates `prefers-color-scheme` only.*

- [ ] 6.5 **Narrow-window drawers still work.** Narrow the window below the compact breakpoint. Open
      the Documents drawer, then the Chat drawer; dismiss each with Escape and with its close button.
      *Expect:* focus returns to the button that opened the drawer, both times.
      *Failed if:* focus lands on the page body or the drawer does not dismiss.
      *Note:* the breakpoint moved from 1140 to 1142 (two dividers), and the Chat drawer now holds
      the whole conversation surface rather than a small pane — check it is usable at that width.

## 7. Closeout

- [x] 7.1 Record which 5.x and 6.x items ran and their results, in the change. *Above.*
- [x] 7.2 Sync the `spec-chat-session` delta into `openspec/specs/`.
- [x] 7.3 `/handoff`.
