# Conversation-first specification workspace

## Why

The Spec page has **two left rails**, and everything wrong with the screen follows from that.

`App.tsx:361` passes `compact={activePage === 'spec'}` to the Hub rail. `Sidebar`'s compact mode is
not an icon rail — every branch in it is gated `!compact`, so it renders the "AW" avatar and
**nothing else**: no projects, no agents, no conversations, no way back. The operator did not ask
for it and cannot undo it. It exists to buy horizontal space for `SpecNavigator`, a second left
column carrying the document library and the page outline.

With two columns spent, the chat gets what is left. A1 mounted `AgentOutputPanel` there — a surface
whose body is `max-w-[820px]` and whose header carries agent identity, a status chip, a context
meter, settings, Checkpoint, and Fold-all. At ~360px it fails visibly: **the composer's control row
overflows the right edge** (`Permissions: Edit files` is clipped mid-word), the header crowds and
truncates, and `Jump to newest` lands on top of the run's completion line.

A1 also introduced a defect of its own. `SpecChat` added an agent `<select>` — the only raw select
in the application, and a **second way to choose an agent** when the rail already does that. It is
the same "second application" mistake A1 existed to delete, reintroduced one layer up, and it is why
the agent's name appears three times in one header.

**The structural cause is the model, not the CSS.** The application currently says a specification
is *a place you go*: `spec` is a project tab holding its own three-column application, with a chat
bolted to the side. But a specification is not a destination — it is a thing you work on *with an
agent*. Modelled that way, the layout falls out on its own and the second rail has no reason to
exist.

This also matches a decision already taken. The exploration of 2026-08-10 concluded that **phase
belongs to the document, not the thread** — a conversation is a specification conversation *because
a document is open in it*. "Conversation as the frame, document open beside it" is that conclusion
drawn as a screen. The present tab layout is the older model still showing through.

## What changes

- **The conversation becomes the frame.** `AgentOutputPanel` gets a real column at a width its
  composer was designed for, instead of a 360px side pane.
- **The document opens beside it, and closes.** A document panel belongs to the *conversation view*,
  which means any conversation can open one — not only ones reached through a Spec tab.
- **`tab: 'spec'` stays as an entry point and stops being a place.** Choosing it resolves into a
  conversation destination with the specification home document open, rather than rendering a
  different application (`design.md` Decision 1).
- **The Hub rail stops collapsing itself.** The automatic `compact` on the Spec page is removed.
  Collapsing becomes operator-controlled, remembered, and — while collapsed — an icon rail that can
  still be navigated, never a blank strip (`design.md` Decision 4).
- **`SpecNavigator`'s library column is deleted.** Choosing a document is the Ctrl+K
  `SpecDocumentPicker` that already exists, plus a breadcrumb in the document panel's own header.
  The page outline moves inside the document panel, where the page it indexes is.
- **The agent `<select>` is deleted**, and `SpecChat` collapses with it. The agent is whichever
  conversation the operator is in, as it is everywhere else.
- **The composer control row stops overflowing at every width it can be shown at**, including inside
  a narrowed panel.

## Non-goals

- **What the specification screen *knows*.** Where evidence sits beside a requirement, how proposals
  render in position, what a phase control looks like — all of that depends on data B2/B3 create and
  remains **B5**. This change moves and deletes surfaces; it adds no new information to the screen.
- **The document rendering pipeline.** `SpecFrame`'s iframe stays a security boundary on exactly its
  present terms — `sandbox="allow-scripts"`, no `allow-same-origin`, message identity in place of
  origin checking — and `specBridge.ts`'s `toc-ready` / `active-section` / `postScrollTo` /
  path-allowlisted link resolution contract is carried across unchanged, not redesigned
  (`design.md` Decision 6).
- **A new visual language.** The identity comes from components that already exist. No mock, for the
  reason A1 gave: a second description is what let `components/spec/` drift in the first place.
- **HTML as the specification format.** Settled; unchanged.
- **The remaining watchdog references** outside these files. Their own cleanup.

## Impact

- **Frontend:** `components/spec/SpecPage.tsx`, `SpecWorkspace.tsx`, `SpecNavigator.tsx`,
  `SpecChat.tsx` (deleted); `components/agents/AgentOutputPanel.tsx` and `Composer` control-row
  layout; `components/layout/Sidebar.tsx` (real compact mode) and `App.tsx` (the automatic collapse,
  and routing the Spec entry point). `lib/navigation.ts` — the destination gains the open document.
- **Backend:** none expected. The document already reaches the agent through
  `TriggerAgentRequest.spec_document`; this change only alters which surface supplies it.
- **Specifications:** deltas on `spec-chat-session` and `hub-workspace-shell`.
- **Static assets:** `hub/hub/static/ui` rebuilt and `diff -rq` verified.

## Verification ownership

Per the standing directive of 2026-08-10, verification is split at authoring time, and `tasks.md`
carries both halves.

**One correction to how the agent verifies, carried from A1.** A1's live checks confirmed that the
permission card and the question card were *present in the DOM* and reported that as verified. They
were present and unreadable — the pane they were in was overflowing. **Presence is not rendering.**
Every live check in this change asserts geometry: that no element's right edge exceeds its
container's, that no two interactive elements overlap, and that text is not clipped — measured, at
several widths. A DOM-presence assertion alone does not close a task in this change.

- **Agent-verifiable:** no overflow or overlap at each tested width; the rail is navigable at every
  state including collapsed; the document panel opens, closes, and survives reload; only one agent
  selector exists in the application; conversation and document keep working together live.
- **Human-only:** whether the proportions feel right; whether the document is comfortable to *read*
  at the width it gets; pointer feel of the divider; keyboard traversal; reduced motion.

## Approval gate

Implementation MUST NOT begin until the user explicitly approves this proposal.

**Approved:** _pending_
