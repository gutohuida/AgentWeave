# Tasks — One chat surface

> Verification is split per the standing directive of 2026-08-10: section 5 is what the agent
> verifies, section 6 is the operator's guide. **A human-only item is never left as a bare
> unchecked box** — each carries steps, an expected result, and what failure looks like.

## 1. Fixture — make the Spec page renderable

- [ ] 1.1 Confirm the Hub is running and the testbed project resolves.
- [ ] 1.2 Push a spec document through `POST /api/v1/projects/{id}/project/specs/sync`. A probe
      document (`spec/a1-probe.html`) was pushed on 2026-08-10 and is present; re-push if the
      database was reset.
- [ ] 1.3 Record the fixture command in the change so verification is reproducible.

## 2. Backend — the open document reaches the agent

- [ ] 2.1 Extend `_render_hub_agent_context` to carry the document the operator is viewing, when the
      request supplies one. Absent value renders nothing — never a guess.
- [ ] 2.2 Thread the value from the trigger request through to the render call in
      `agent_trigger.py`.
- [ ] 2.3 Hub tests: context contains the document when supplied; contains no document line when
      not; identical for a `claude` and a `codex` runner.

## 3. Frontend — one composer

- [ ] 3.1 Replace the Spec workspace's chat pane with `Composer` + `BannerStack` over conversation
      history, dropping `useAgentOutput`.
- [ ] 3.2 Delete `SpecChatPane.tsx` and its bespoke trigger, `QUEUED_START_TIMEOUT_MS`,
      `TriggerResponse`, and the dead `execution_confidence` branch.
- [ ] 3.3 Pass `conversationId: null` for an agent with no conversation; let the first message create
      one. Do **not** set `origin` (design.md Decision 1).
- [ ] 3.4 Pass the open document path to the trigger so task 2.2 can use it.
- [ ] 3.5 Delete the "Repair manifest" button, `buildRepairMessage`, `MAX_REPAIR_ITEMS`,
      `handleRepair`, and the second bespoke trigger path in `SpecPage.tsx`.
- [ ] 3.6 Remove `startNewSession` from `SpecPage` if task 3.5 leaves it with no remaining consumer.
- [ ] 3.7 Replace `SpecWorkspace`'s fixed widths with the shared `PaneResizer`, retaining
      `useWorkspaceMode` and the compact drawers (design.md Decision 5).
- [ ] 3.8 Remove watchdog references in the touched files only (design.md Decision 6).

## 4. Tests

- [ ] 4.1 Delete or rewrite `specChatSession.test.tsx` — 5 of its assertions cover watchdog
      behaviour that no longer exists.
- [ ] 4.2 Spec workspace tests: composer renders; sending creates a conversation; a question card
      renders and can be answered; a permission request renders and can be answered.
- [ ] 4.3 Update every test that mocks a now-unused api module — adding a hook to a component breaks
      each test mocking that module, and the fix belongs in the same commit.

## 5. Agent verification — expected behaviour, run by the agent

- [ ] 5.1 `npx vitest run` — green, with the file count and the delta from 640 recorded.
- [ ] 5.2 `npx tsc --noEmit` — clean.
- [ ] 5.3 `pytest hub/tests/` — green; expected 1273 + the tests added in 2.3.
- [ ] 5.4 `ruff check` and `black --check` on every touched path — clean.
- [ ] 5.5 Grep proof: no `SpecChatPane`, `execution_confidence`, `queued_watchdog_healthy`,
      `buildRepairMessage`, or `watchdog` in `components/spec/`.
- [ ] 5.6 Live: trigger a run from the Spec page against the fixture document; the run reaches
      `completed` and its output renders in the pane.
- [ ] 5.7 Live: with the agent on `manual` permissions, drive a tool call and confirm the permission
      card renders **on the Spec page** and the answer resolves the run. *This is the defect the
      change exists to fix — it must be demonstrated, not asserted.*
- [ ] 5.8 Live: have the agent call `ask_user` from the Spec page; confirm the question card renders
      and the answer returns.
- [ ] 5.9 `npm run build`, copy `hub/ui/dist` over `hub/hub/static/ui`, confirm with `diff -rq`.
- [ ] 5.10 `npx openspec validate --specs --strict`.

## 6. Human test guide — what the agent cannot verify

> Each item: **do this → expect this → it failed if this.** Report the outcome; an unrun item is
> reported as unrun, never as passed.

- [ ] 6.1 **Pane resizing feels right.** Open the Spec page on a wide window. Drag the divider
      between navigation and document, then between document and chat.
      *Expect:* the drag tracks the pointer with no lag or snap-back; each pane stops at a minimum
      that still shows usable content; the width survives a page reload.
      *Failed if:* a pane collapses to unusable width, the document reflows jarringly mid-drag, or
      the width resets on reload.

- [ ] 6.2 **The Spec page reads as the same product as the agent page.** Open the agent conversation,
      then the Spec page, and switch between them a few times.
      *Expect:* the composer, its control row, and the message styling are indistinguishable between
      the two.
      *Failed if:* anything about the input area reads as a different generation of the product —
      different spacing, different control shapes, different colours.

- [ ] 6.3 **Keyboard traversal of the composer inside the Spec workspace.** Click the document pane,
      then press Tab repeatedly.
      *Expect:* focus reaches the composer text area and every control in its row; each shows a
      visible focus ring; Shift+Tab reverses in the same order; focus never enters the document
      iframe and get stuck.
      *Failed if:* any control is unreachable, shows no focus ring, or traps focus.
      *Agent cannot run this — available browser automation cannot drive real focus traversal.*

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

## 7. Closeout

- [ ] 7.1 Record which 5.x and 6.x items ran and their results, in the change.
- [ ] 7.2 Sync the `spec-chat-session` delta into `openspec/specs/`.
- [ ] 7.3 `/handoff`.
