# Task board drag-and-drop E2E — 2026-08-22

## Scope

Exercise legal task movement, hover feedback, board overflow, keyboard parity, specification
rendering, and dependency visualization against the live Hub on port 8010. The persistent fixture is
project `proj-408eb5d2` (`ui-showcase-2026-08-22`), created outside this source checkout.

## Finding — browser navigation captured the first keyboard shortcut

The initial keyboard equivalent used `Alt+Left` and `Alt+Right`. A real Chromium run moved a task
right, but Windows reserved `Alt+Left` for browser Back before the task could move left. This was an
interaction-boundary defect that the React keyboard-event test did not expose.

The shortcut was changed to `Ctrl+Left` / `Ctrl+Right`. Playwright then moved the same task from
pending to assigned and back to pending, and the persisted task row ended at `pending`.

## What held

- Native drag moved the task pending → assigned through the live PATCH API, then assigned → pending.
- An illegal destination remains unavailable because the UI consumes the Hub's operator transition
  map rather than maintaining a second map.
- Hover changed surface, border, shadow, and translation without restoring the earlier bright fill.
- The desktop document had zero horizontal overflow; the board owned its 281 px overflow.
- At 390 px, the document again had zero horizontal overflow while the board retained its internal
  1,330 px scrollable width.
- The approved mock spec rendered 10 requirements, 10 acceptance criteria, and 19 tasks.
- Its dependency board returned 19 nodes and 35 edges; expanding terminal layers rendered all
  19 task cards in the browser.

## Evidence limits

The fixture uses real Hub APIs and real browser interactions but does not execute the four Codex
agents registered on the project. It is intentionally left in place for operator inspection.
