# One shell, many tabs

> **Rewritten 2026-08-18 afternoon.** The first version of this change was authored by an unattended
> firing at 13:00–13:04 and read by nobody. An operator conversation that afternoon overturned six of
> its decisions — the descriptor model, the persistence scope, the tab/plus relationship, the loop
> tab's scoping, spec's status as a special case, and its live-ness design. This is a rewrite rather
> than an amendment because those are the change's load-bearing decisions, not its details. The
> conversation is recorded in
> `openspec/explorations/2026-08-18-the-side-panel-with-the-operator.md`, which supersedes the
> recommendations (not the research) of `2026-08-18-the-side-panel-family.md`.
>
> **The loop panel is no longer in this change.** It moved to
> `2026-08-18-a-loop-writes-its-own-queue` (addendum D20), which owns every fact it displays. This
> change owns the container; that change owns that tenant.

## Why

**The right side of the screen has exactly one tenant, and it cannot have two.**
`hub/ui/src/components/agents/ConversationView.tsx` hosts `SpecDocumentPanel` and nothing else — no
tab strip, no plus affordance, no second slot. It was never asked to coexist with anything, so
nothing in this codebase has ever had to answer "which panel is open," only "is *the* panel open."

The operator's brief:

> "We should have a button that opens the side panel (just like t3 does and other harnesses as
> well). On top we can click a plus sign and open something else... We could start with a file
> viewer/navigation of the repo of the project. A loop tab with loop information... and the spec that
> we already have. This could solve also our explore button problem."

And, on what the container actually is:

> "On the side panel we have only one tab active is just like a tab from a browser so to speak. The
> plus just adds another tab with information and we click to navigate between the tabs but the whole
> panel is dedicated to one tab at a time of displayed information."

> "Each project we might want to have different tabs configurations... when we reopen the side panel
> it loads what was being used (For that project)."

## What Changes

- **A panel shell replaces the spec-only hosting block in `ConversationView.tsx`**, owning the tab
  strip, the plus affordance, and the resize/overlay breakpoint math that today serves one panel.
  `SpecDocumentPanel` becomes a tab's content, unchanged internally — breadcrumb, archived marker,
  phase and coverage bars, proposals panel, the sandboxed `SpecFrame` bridge and the outline rail all
  keep working exactly as they do.
- **The strip holds only what is open.** A tab is added from the plus affordance and can be closed;
  one tab is visible at a time. This replaces the first version's fixed strip of three panels, which
  contradicted itself: it also specced a plus menu offering *"every registered panel... hidden or
  omitted"* for none, so the menu always listed exactly the tabs already on screen.
- **Index tabs open keyed detail tabs.** A `specs` index (today's modal document picker) opens
  `spec:<document_id>` tabs; a `files` tree opens `file:<path>` tabs. Reopening an already-open keyed
  tab refocuses and re-reveals it rather than duplicating it. This replaces `singleton: true` on
  every panel, which foreclosed the drill-down the operator asked for.
- **Detail tabs are keyed by id wherever an id exists.** `rename_spec_document` is agent-callable, so
  a `spec:<path>` tab would dangle the moment an agent renamed a document that still exists. Only
  `file:` tabs key by path, because a file has no other identity — and those are exactly the tabs that
  need reconciling against the workspace listing.
- **Opening a file replaces the tree tab.** The tree is a launcher, not a destination, and a tab spent
  on the thing that only got you there is wasted in a narrow column. (The loops index, in the loop
  change, deliberately does *not* behave this way — it is a governance glance worth keeping open. The
  asymmetry is intentional and stated in both changes.)
- **Tab configuration persists per project**, in a versioned store with a migration and
  reconciliation for tabs whose target no longer exists. This replaces the first version's
  per-conversation destination state. Panel **width** stays the single global preference
  `specPreferences.ts` already persists.
- **Reading a document is unfused from attaching one.** Today the composer's `Spec: <title>` control
  means both "this document is attached to this conversation" — what the agent writes into during an
  explore turn — and "this is what the right side shows," so a second document cannot be read at all.
  The attachment keeps its meaning and its place in the conversation's addressed destination;
  *reading* becomes tabs like everything else. **Closing a spec tab does not detach the document.**
- **A file tab, backed by a new content-read endpoint.** `GET /api/v1/workspace/paths` already lists
  every path a project contains; nothing returns a file's bytes. The new endpoint's allowlist is
  defined as exactly what `list_workspace_paths` returns — no second, independently-reasoned
  path-safety check — with a size bound refused rather than truncated, and a binary check inheriting
  git's own first-bytes heuristic.

## Capabilities

### Added Capabilities

- `conversation-side-panel`: the panel shell, its tab model and keying rules, per-project persistence
  with reconciliation, the resize/overlay rule, the files tree and its detail tabs, the file content
  endpoint, and the keyboard and reduced-motion requirements.

### Modified Capabilities

- `spec-chat-session`: "A specification document opens beside a conversation" is restated as opening
  in a keyed tab within the shell, and the attachment a conversation carries is separated from the
  tab that displays a document. Every guarantee the requirement already makes — closable, part of the
  addressed destination, survives a reload, an operator-owned resize boundary — is preserved.

## Impact

**Behaviour** — a conversation that opens no panel is unaffected. A conversation with a document open
today continues to show it, now in a `spec:<document_id>` tab. The operator gains the ability to read
one document while a different one is attached, which is impossible today.

**API** — new `GET /api/v1/workspace/file?path=...`, project-scoped, resolving through the same
`project_workspace.resolve_project_workspace` boundary every other project-scoped route uses. No
existing endpoint's request or response shape changes.

**Migration** — none in the database. The client-side panel store is new and versioned from the
start, with a migration function, because T3's equivalent reached storage version 9 through exactly
this kind of change.

**UI** — `ConversationView.tsx`'s panel-hosting block is rewritten as shell-plus-tabs.
`SpecDocumentPanel`'s internals are not rewritten, only re-hosted.

## Non-Goals

- **Not the loop panel.** Moved to `2026-08-18-a-loop-writes-its-own-queue` D20/B5/B6, which owns the
  data it shows. This change must land its shell first; that change is its first non-spec tenant.
- **Not removing the explore button.** Per `DEC-explore-button`, removing a shipped entry point is a
  taste call the operator should make while looking at the replacement. The unfusing above is what
  makes that possible later; it does not do it now.
- **Not a plugin system.** Tab kinds are a fixed literal union, matching what T3 itself does with six
  kinds. Keyed multi-instance is not dynamic registration.
- **Not per-conversation tab configuration.** Explicitly rejected by the operator in favour of
  per-project. Named here so it is not reintroduced as an obvious improvement.
- **Not a file editor.** The file tab reads; nothing in this change writes a file.
- **Not "recently used" ordering in the plus menu.** A short, fixed list does not need it.
