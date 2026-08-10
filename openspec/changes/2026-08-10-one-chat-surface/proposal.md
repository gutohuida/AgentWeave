# One chat surface

## Why

The Spec page is a second application surface, not merely an old-looking one. It was built before
the single-runtime change and before conversations existed, and was never migrated.

**It cannot involve the operator.** `SpecChatPane.tsx` does not import `Composer`. Searching it for
`permission|question|checkpoint|Banner` returns nothing. So on the Spec page there is no permission
card, no `ask_user` question card, no checkpoint warning, and none of the composer's intelligence —
`@path`, `$skill`, `/model`, the model picker, drafts, batched questions. An agent that calls
`ask_user` there blocks with nothing rendered; a `manual`-posture run hangs waiting for an approval
card the surface cannot draw.

**It talks to a runtime that was deleted.** The watchdog was removed by
`archive/2026-08-03-single-runtime`, yet:

- `SpecChatPane.tsx:46` — *"The session id itself is never sent — the watchdog resolves it."*
- `SpecChatPane.tsx:74` — a **user-facing** string: *"Message is queued, but the agent did not start
  within 15 seconds. Check the watchdog."*
- `SpecPage.tsx:227` — a second copy of the same watchdog string in `handleRepair`.

**Its success path is dead code.** It branches on
`triggerResponse.execution_confidence !== 'queued_watchdog_healthy'`. `agent_trigger.py`'s own
docstring records that the field was deliberately removed: *"no `execution_confidence` guess about
whether some other process might eventually pick the request up."* The field is always `undefined`,
so the warning branch is unreachable and the surface always sets `queued`, then races a 15-second
timeout against a heartbeat.

**It duplicates the trigger path twice.** `SpecChatPane.handleSend` and `SpecPage.handleRepair` each
build their own `fetch` to `/agent/trigger`, with their own timeouts, session-mode handling, and
error strings.

**Why this blocks the specification program rather than sitting beside it.** Program B's entire
authoring story — an agent proposing a requirement change, asking the operator to clarify an
ambiguity, requesting approval on a gate — runs through this pane. Built on it as-is, each of those
is built against a surface that structurally cannot do operator-in-the-loop, and then rebuilt.
Deferring this change causes the double-build that deferring it appears to avoid.

See `openspec/explorations/2026-08-10-specification-and-surface-program-roadmap.md` (Program A1).

## What changes

- **Delete `SpecChatPane.tsx`.** The Spec workspace's chat pane renders the same `Composer` and
  banner stack the agent conversation uses, over conversation history rather than the raw agent
  output tail.
- **Remove both bespoke trigger paths.** Sending from the Spec page goes through the same path the
  agent conversation uses, so permissions, questions, checkpoints, and stream errors work there
  because they are not re-implemented.
- **Reuse the agent's conversation** — the Spec pane shows the selected agent's conversation, with
  `conversationId: null` creating one on first message, exactly as `NewConversationSurface` does.
  **`Conversation.origin` gains no new producer** (see `design.md` Decision 1).
- **Put the open document in the turn context.** The agent is told which spec document the operator
  is viewing, through the existing `.agentweave/context/<agent>.md` materialisation.
- **Remove the "Repair manifest" button** and `buildRepairMessage`. It instructs an agent to run
  `aw-spec-reindex`, a skill nothing installs. The drift it responds to cannot occur while nothing
  produces documents. A deterministic reindexer belongs in B2, where the parser it depends on will
  exist (`design.md` Decision 4).
- **Give the Spec workspace the shared `PaneResizer`**, replacing its fixed 260/520/360 layout.
- **Remove the stale watchdog references** in the files this change touches.

## Non-goals

- **The Spec screen's information architecture** — where evidence sits beside a requirement, how
  proposals render in position, what the pane structure becomes. That depends on data B2/B3/B5
  create; it is change **B5**, as `archive/2026-08-04-2026-08-04-hub-ui-mock-alignment` already
  stated when it deferred *"the Spec document, evidence, proposal, or verification experience."*
- **A deterministic manifest reindexer.** B2.
- **Producing spec documents.** Nothing authors them today; that is B0/B2. This change is verified
  against a document pushed through the existing `POST /specs/sync` endpoint.
- **`origin="spec"` conversations**, spec-scoped threads, or a phase control. Those need the
  document/phase model from B2 and B5.
- **The 19 remaining watchdog references** outside this change's files — 10 in `eventSummary.ts`,
  plus `LogLine`, `LogsView`, `streamModel`, `useSSE`. Their own cleanup.
- **No visual redesign.** The identity comes from composing existing components; there is no mock.

## Impact

- **Frontend:** `components/spec/SpecChatPane.tsx` (deleted), `SpecPage.tsx`, `SpecWorkspace.tsx`;
  reuse of `Composer`, `BannerStack`, `PaneResizer`. Tests: `specChatSession.test.tsx` (deleted or
  rewritten — 5 of its assertions are about watchdog behaviour), plus spec workspace tests.
- **Backend:** the document-in-context addition to `_render_hub_agent_context`. No new endpoint, no
  migration.
- **Specifications:** delta on `spec-chat-session`.
- **Static assets:** `hub/hub/static/ui` rebuilt and `diff -rq` verified.

## Verification ownership

Per the standing directive of 2026-08-10, verification is split at authoring time. `tasks.md`
carries both sections; the human guide is concrete steps with expected results, not a checkbox.

- **Agent-verifiable:** the composer mounts and sends; a question card renders and answers; a
  permission request renders and is answered; no `SpecChatPane`, `execution_confidence`, or
  `watchdog` references remain in the touched files; vitest, `tsc`, `ruff`, the Hub suite.
- **Human-only:** that the resizer feels right and the pane minimums are usable; that the Spec page
  reads as the same product as the agent page; keyboard traversal of the composer control row inside
  the Spec workspace; reduced-motion behaviour of the pane transitions.

## Approval gate

Implementation MUST NOT begin until the user explicitly approves this proposal.

**Approved:** _pending_
