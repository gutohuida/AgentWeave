# Tasks — One shell, many tabs

Nothing in this file has been started. Every box is unchecked because this change is a spec only —
CLAUDE.md: "Never mark a task complete on the strength of a plan existing."

**Rewritten 2026-08-18** alongside the proposal, design and specs. The loop panel's tasks are gone —
they live in `2026-08-18-a-loop-writes-its-own-queue` (B5, B6), which owns the data they display.

Sequence matters here: **1 → 2 → 3 before 4 or 5.** The shell's contract has to exist before anything
is built against it, or the file tab gets built against `SpecDocumentPanel`'s current one-off shape
and re-plumbed later — the cost the exploration named and this ordering exists to avoid.

## 1. The tab store

Implemented 2026-08-18 in `hub/ui/src/store/panelTabsStore.ts`, tested in
`hub/ui/src/__tests__/panelTabsStore.test.ts` (27 tests). Nothing imports the store yet — that is
section 2's job, and the bundle is byte-identical because of it.

- [x] 1.1 A per-project tab store: which tabs are open, their order, which is visible, whether the
      shell is open. Keyed by project id. Persisted to `localStorage` under a **versioned** key.
      Width deliberately excluded — it stays `specPreferences.ts`'s global value per D5, asserted by
      a test that no width key is ever written.
- [x] 1.2 Tab kinds as a fixed literal union with template-literal ids: index kinds take a fixed id
      (`specs`, `files`), detail kinds a keyed one (`spec:${documentId}`, `file:${relativePath}`).
      Design D3/D4 — key by durable id where one exists; only files key by path. `kind` is *derived*
      from the id rather than stored beside it, so the two cannot disagree.
- [x] 1.3 Open/close/activate/reorder actions. Opening an already-open keyed tab **refocuses and
      re-reveals** rather than duplicating (a reveal counter, T3's `revealRequestId` shape).
- [x] 1.4 `closeOthers` / `closeToRight` / `closeAll`, since a strip that accumulates tabs needs them
      and they are cheap once the store exists.
- [x] 1.5 A migration function invoked on load when the stored version is older than current. Write it
      now even though there is only version 1 — retrofitting versioning after shipping is what forces
      a silent data loss. A version with no step forward is discarded, not guessed at; state from a
      *newer* version than this build understands is discarded too.
- [x] 1.6 Reconciliation on load: drop a `file:` tab whose path is not in the workspace listing.
      `spec:` tabs are keyed by document id and survive rename, so they need reconciling only against
      a document that no longer exists at all. An **absent** listing means "not loaded yet" and
      leaves that kind alone — reading it as empty would drop every tab on a slow load.
- [x] 1.7 The two restore rules from design D5, each with its own test: every tab dropped ⇒ the shell
      restores **closed**, not open and empty; the visible tab dropped but others surviving ⇒ promote a
      survivor. Applied on load and after reconciliation, *not* on every mutation — a shell
      deliberately opened with no tabs is a live state 2.1 may choose to render; a restored one is not.
- [x] 1.8 Unit tests for the store: persistence round-trip, migration from a stale shape,
      reconciliation, refocus-not-duplicate, and both restore rules. Verified non-vacuous by mutation
      probe: disabling `normalize` fails exactly the 4 restore-rule tests, and making the migration
      chain accept an unknown version fails exactly the stale-shape test.

## 2. The shell

- [x] 2.1 Shell component owning the strip, the plus affordance, and the visible tab's content. One
      tab's content rendered at a time.

      Implemented 2026-08-18 in `hub/ui/src/components/spec/PanelShell.tsx`. Deliberately generic:
      it takes `availableTabs`/`describeTab`/`renderTabContent` and knows nothing about specs or
      files, so section 3's tenant work and the file endpoint (4/5) plug in without re-plumbing.
      Not yet mounted anywhere — that is 2.2, a separate task on purpose. An explicit empty state
      (`panel-empty-state`) renders when no tabs are open, satisfying the task-8 user-guide's "not an
      empty grey box" requirement; which of 2.1's two allowed readings (shell renders empty vs. shell
      does not open) was chosen is recorded there, not guessed at.
- [x] 2.2 Move `ConversationView.tsx`'s panel-hosting block (`:150-291`) into the shell. Do **not**
      rewrite `SpecDocumentPanel`'s internals — this is a re-hosting, and the breadcrumb, archived
      marker, phase and coverage bars, proposals panel, `SpecFrame` bridge and outline rail must all
      still work afterwards.

      Done 2026-08-18. `ConversationView` now renders `<PanelShell>` with `availableTabs={[]}`
      instead of a bare `<SpecDocumentPanel>`; `renderTabContent`/`describeTab` construct that same
      `SpecDocumentPanel` unchanged, so its internals were never touched. `availableTabs` is empty
      on purpose — the plus affordance has nothing to offer until section 3 gives the shell a
      `specs` index tab.

      **Chose the *path-keyed*, single-tab reading, stated explicitly per the queue's instruction
      not to guess between the two.** This component only ever knew a document *path* (`document:
      string | null`), never a document id, so the tab it opens is keyed `spec:<path>` rather than
      `spec:<document_id>` — a real `SpecTabId` by the type (the union is a plain template-literal
      string), but not yet the durable, rename-surviving key section 3 will switch to once it has
      an id to key by. Two effects keep the destination (`document` prop) and the store in sync in
      both directions: opening/changing `document` opens (and closes the previous) tab; closing the
      tab from the strip calls `onOpenDocument(null)`, reading the store's *live* state
      (`usePanelTabsStore.getState()`) rather than a possibly one-commit-stale subscribed value, so
      the two effects cannot race each other when `document` changes in the same render.

      **An honest, unscoped observation, not a bug to fix here:** because the store persists tabs
      per project independent of this component's lifecycle, navigating away from a conversation
      entirely and back to a *different* one that opens a *different* document can leave the first
      document's tab present alongside the new one (only the active one is closed/opened on a
      `document` prop change within the same mounted instance; a fresh mount does not know about a
      previous instance's last document to close it). This is section 1's per-project tab memory
      working as designed, surfacing earlier than section 3's real multi-tab UI — not a defect, but
      recorded here since it was not this task's use case to solve, and it means the shell can show
      more than the "one tenant" framing above suggests even before section 3 lands.
- [x] 2.3 Generalize the breakpoint: compute the combined minimum from the **visible tab's** own
      minimum rather than `SPEC_DOC_MIN_WIDTH` specifically, keeping it *derived* so threshold and
      layout cannot disagree (`ConversationView.tsx:34-38`).

      Done 2026-08-18. Added `minWidthForTabKind(kind: TabKind | null): number` to
      `specPreferences.ts` — today every kind (`spec`, `specs`, `file`, `files`, `null`) resolves to
      `SPEC_DOC_MIN_WIDTH`, because `files` has no measured minimum of its own until task 5.5, but
      the breakpoint, `conversationMax`'s subtraction, and the document-pane's own `minWidth` style
      all now read from this one function keyed off the *actual visible tab's* kind
      (`tabKind(panelActiveTabId)`) rather than the constant directly — the three cannot drift apart
      the way the three-column workspace's did. `DOCUMENT_COLUMN_BREAKPOINT` stays exported as a
      constant (`minWidthForTabKind('spec')`-derived) because every existing caller and test only
      ever has a spec tab open; the component itself computes the real, tab-derived threshold
      (`documentColumnBreakpoint`) rather than reading the export.
- [x] 2.4 Overlay below the breakpoint using the existing `Drawer`, with the reopen affordance kept.
      Dismissing the overlay keeps the tabs.

      Unchanged behaviourally from before this task — the `Drawer`/overlay logic already existed
      and already kept the destination's `document` (and now the store's tab) across a dismiss; this
      task's only change was making the drawer's `width` read from the same derived minimum as 2.3
      rather than `SPEC_DOC_MIN_WIDTH` directly. Verified live: narrowing to 700px (below the
      741px breakpoint) shows the drawer with the shell inside; Escape dismisses it; the reopen
      button restores it with the same tab still present (Playwright, see task list section 8/PW1).
- [x] 2.5 Width stays `specPreferences.ts`'s single global value. Extend that store; do not invent a
      second one.

      No second store: `minWidthForTabKind` and `DOCUMENT_COLUMN_BREAKPOINT` both live in
      `specPreferences.ts` beside `SPEC_DOC_MIN_WIDTH`/`CONVERSATION_MIN_WIDTH`, and the
      conversation-column width itself is still the one `conversationWidth` preference — unchanged
      by this task.
- [x] 2.6 Keyboard: ARIA `tablist`, sequential focus, `Enter`/`Space` to activate, arrow keys between
      tabs, close control reachable, plus menu navigable. Design D11 — nothing here to inherit.

      Chose **automatic activation** (WAI-ARIA APG's other supported tablist variant, not the
      manual-activation reading task 2.6's bullet order might suggest): arrow keys move focus *and*
      activate, roving `tabIndex` keeps only the active tab in the page's Tab sequence, and
      `Enter`/`Space` activate for free via native `<button>` semantics — no bespoke handler needed
      for them. The close control is a plain second button inside the same tab, reached by `Tab`
      right after it, deliberately outside the arrow-key roving set. The plus menu reuses `RowMenu`
      (`hub/ui/src/components/layout/RowMenu.tsx`), whose Radix `DropdownMenu` already owns full
      keyboard support. Covered by 8 keyboard-specific tests in
      `hub/ui/src/__tests__/panelShell.test.tsx` (roving tabIndex, wrap-around both directions,
      Home/End, Enter/Space activation, close-by-keyboard, plus-trigger-by-keyboard).
- [x] 2.7 `Icon` only for every control in the strip. CLAUDE.md forbids a second icon system; audit
      the map before assuming a close or plus glyph exists.

      Audited `hub/ui/src/components/common/Icon.tsx`'s `ICONS` map first, per the task's own
      instruction: `close` → `X` and `add` → `Plus` both already exist, so no new mapping was
      needed. Every glyph in the strip (tab icons via the caller's `describeTab`, the close button,
      the plus trigger inside `RowMenu`) goes through `Icon`; nothing in `PanelShell.tsx` imports
      from `lucide-react` directly.

## 3. Specs as the shell's first tenant

Proves the whole shell without a loop or a file endpoint existing.

- [ ] 3.1 A `specs` index tab listing the project's documents — the content today's modal picker
      shows, re-hosted as a tab.
- [ ] 3.2 Selecting a document opens a `spec:<document_id>` tab hosting `SpecDocumentPanel`.
- [ ] 3.3 **Unfuse attach from display** (design D9): closing a `spec:` tab does not detach the
      conversation's attached document. The composer control is unchanged in this change.
- [ ] 3.4 The attached document stays in the addressed destination and survives a reload, exactly as
      today. Two documents open for reading at once, with only one attached, must work.
- [ ] 3.5 An archived document's tab still opens and shows the archived marker `SpecDocumentPanel`
      already renders.
- [ ] 3.6 Regression pass over `spec-chat-session`'s existing scenarios — this change modifies that
      capability and every guarantee it already made has to survive.

## 4. The file content endpoint

- [ ] 4.1 `GET /api/v1/workspace/file?path=...`, project-scoped, resolving through
      `project_workspace.resolve_project_workspace` like every other project-scoped route.
- [ ] 4.2 Allowlist by **membership of `list_workspace_paths`'s own output** (design D7) — not a second
      containment check. Test traversal, a symlink pointing outside the workspace, and a `.gitignore`d
      path; all refused because the listing does not contain them, not because a separate sanitizer
      caught them.
- [ ] 4.3 Size bound at `aw_max_body_size`'s existing default. Over the bound: refuse, naming size and
      bound. Test that no partial body is returned.
- [ ] 4.4 Binary detection: NUL byte in the first 8,000 bytes. Test an extensionless text file (a
      `Makefile`) is treated as text and a small binary is not.
- [ ] 4.5 Docker-mode path handling matches every other project-scoped route — container-visible paths
      beneath `AW_WORKSPACE_ROOT` only, no host-path guessing.

## 5. The files tab

- [ ] 5.1 A `files` tree tab built from `GET /api/v1/workspace/paths`. Reuse or adapt
      `specNavigation.ts`'s `buildPathTree` (`:320-364`) rather than re-deriving tree building.
- [ ] 5.2 Selecting a file opens a `file:<path>` tab **and closes the tree tab** (design D8).
- [ ] 5.3 The file tab renders text content, states binary, and states a refusal for an oversized file
      with its size and the bound.
- [ ] 5.4 "Insert into composer" produces the **same** mention format `composerTrigger.ts`'s `@path`
      trigger already produces. Test the two are byte-identical for the same file.
- [ ] 5.5 Measure and state the `files` tab's minimum width against the real shell. Design D12 leaves
      this deliberately unstated; do not guess it, measure it, then write it down beside
      `SPEC_DOC_MIN_WIDTH` with the same kind of comment.

## 6. Strip overflow

- [ ] 6.1 Decide overflow behaviour once real tabs exist and more are open than fit. T3 does one native
      `scrollIntoView` for the newly active tab and nothing else; start there and only add if it
      measurably fails. Record what was chosen and why.

## 7. Human-only — the operator's judgement

- [ ] 7.1 **Does the plus affordance read as "add a tab" rather than "settings"?** It is the only entry
      point to everything the shell can do.
- [ ] 7.2 **Does closing a spec tab feel safe** — is it obvious the document is still attached and
      nothing was lost? D9's whole value rests on this reading correctly.
- [ ] 7.3 **Does opening a file eating the tree tab feel right or feel like a bug?** T3 does it; that
      is evidence, not proof, and this is the one borrowed behaviour most likely to surprise.
- [ ] 7.4 **At the narrowest window you actually use, is the shell usable or merely present?**
      Especially the file tree plus a preview.
- [ ] 7.5 **After a week, does per-project tab memory help or does it restore stale clutter?**

## 8. User test guide

1. **Open the shell with nothing open.** Press the panel button.
   - *Expect:* the shell opens with the plus affordance and no tabs, or does not open at all until a
     tab is chosen — whichever 2.1 implements, it should not open showing an empty grey box.
2. **Add the specs index, open a document, then open a second document.**
   - *Expect:* three tabs; one visible at a time; both documents readable.
3. **Attach a document via the composer's explore control, then close its tab.**
   - *Expect:* the composer still names it as attached. If the pill clears, 3.3 is wrong.
4. **Reload.**
   - *Expect:* the same tabs, the same visible tab, the same attached document.
5. **Switch to another project, open different tabs, switch back.**
   - *Expect:* each project keeps its own configuration.
6. **Open the file tree, open a file.**
   - *Expect:* the tree tab is replaced by the file tab.
7. **Open a file, then delete it on disk, then reload.**
   - *Expect:* the tab is gone and the rest survive. If the shell opens empty, 1.7's first rule is
     not implemented.
8. **Request a 5 MB file and a binary file.**
   - *Expect:* refused with size and bound; identified as binary. Neither renders as garbled text.
9. **Narrow the window until the shell overlays. Dismiss it.**
   - *Expect:* a control remains to bring it back, with the same tabs.
10. **Do all of the above using only the keyboard.**

**Where it would go wrong.** If step 3 clears the pill, attach and display are still fused. If step 5
shows the first project's tabs, the store is global rather than per project. If step 7 opens an empty
shell, 1.7 is missing. If step 9 loses the tabs, 2.4 is discarding state on dismiss.
