# Tasks — One shell, many tabs

Sections 1-6 are implemented and verified (dated notes under each task). Section 7 is the
operator's own judgement (CLAUDE.md: agent runs do not tick human-only sections) and section 8 is
the user test guide — both still open.

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

- [x] 3.1 A `specs` index tab listing the project's documents — the content today's modal picker
      shows, re-hosted as a tab.

      Done 2026-08-18. Extracted the picker dialog's search-and-browse content (search input, the
      browsing tree, the ranked results, the "start an exploration" row) out of
      `SpecDocumentPicker.tsx` into a new `SpecDocumentBrowser.tsx` — chrome-free, so both the
      Ctrl/Cmd+K dialog and the new tab can host it without duplicating the search/rank logic
      `SpecDocumentPicker` used to own alone. Radix does not render `Dialog.Content` while closed,
      so the browser unmounts and remounts across an open/close cycle, which is what resets its
      search box now — the explicit "reset query on open" effect the dialog used to need is gone,
      not replaced. `SpecIndexTab.tsx` wraps the browser for the shell: selecting a node calls the
      tab store's `openTab` directly (never `onOpenDocument`), which is what keeps 3.3's unfuse
      honest — the index tab has no way to attach anything even if it wanted to. Added to
      `ConversationView`'s `availableTabs` as a fixed `{id: 'specs', label: 'Specs', icon:
      'folder_open'}` entry (`folder_open` rather than `article`, so the index reads differently
      from the documents it lists).
- [x] 3.2 Selecting a document opens a `spec:<document_id>` tab hosting `SpecDocumentPanel`.

      Done 2026-08-18. **The id did not exist on the wire before this task** — checked before
      assuming either way, per the queue's instruction: `GET /project/specs` (`hub/hub/api/v1/
      spec.py`) enriches each filesystem-discovered entry with `phase` from the Hub's
      `spec_lifecycle.list_documents`, but never carried the row's own `id`, even though
      `GET /project/documents` (a different, Hub-records-only endpoint) already returned one. Added
      `document_id` to the same enrichment `phase` already goes through — one `tracked` map built
      once, both fields read off it — covered by a new backend test,
      `test_the_specs_tree_carries_the_document_id_the_panel_shell_keys_tabs_by`
      (`hub/tests/test_spec_archive.py`).

      **Not every document has one, and this task does not pretend otherwise.** A filesystem
      discovery with no `spec_documents` row (a document never created through the Hub — the
      openspec corpus, or any file placed by hand) has `document_id: null`. `specNavigation.ts`
      carries this as `SpecNode.documentId: string | null`, and two functions — `tabKeyForNode`
      (id if present, else the path) and `resolveTabPath` (its inverse, via a new
      `SpecInventory.byDocumentId` map) — are the *only* places that key is made or unmade, so the
      open side and the render side can never disagree about what a tab's key means. A document
      with no id is still fully openable; its tab is keyed by path exactly as P2b's tabs already
      were, which is the only identity such a document has ever had. `ConversationView`'s
      `describePanelTab`/`renderPanelTabContent` both resolve through `resolveTabPath` before
      touching `SpecDocumentPanel`, which still only ever receives a path.
- [x] 3.3 **Unfuse attach from display** (design D9): closing a `spec:` tab does not detach the
      conversation's attached document. The composer control is unchanged in this change.

      Done 2026-08-18. Two fused paths existed, not one, and both had to go — leaving either would
      have been exactly "two close semantics coexisting silently," which the queue named as the
      risk to avoid:

      1. P2b's store-watching effect (`ConversationView`, the one that read
         `usePanelTabsStore.getState()` after a render and called `onOpenDocument(null)` when the
         tab it had opened was no longer present) — deleted outright, not merely made conditional.
         There is now only a one-directional destination-to-store sync: attaching opens/refocuses a
         tab; nothing watches the store to detach.
      2. `SpecDocumentPanel`'s own in-panel close button (`spec-document-close`, in its breadcrumb
         row) — this is a *second* close control the strip's own close button (`panel-tab-close-*`)
         doesn't share code with, and it was still wired straight to `onOpenDocument(null)` before
         this task. Now wired to `closeTab(projectId, tab.id)` — the same store action the strip's
         button calls, so both close controls now have identical, non-detaching meaning. This is a
         real behavior change from before section 3, recorded and regression-tested (see 3.6)
         rather than left implicit.

      The composer control (`ComposerSpecControl`'s `onStopExploring`, wired to
      `onOpenDocument(null)`) is untouched — still the only path that detaches, exactly as D9
      requires. `onSelectPath` (in-document link navigation, `SpecFrame`'s bridge) is **also
      untouched** and still calls `onOpenDocument` — deliberately, not an oversight; see 3.6 for
      why, and the one real gap that decision leaves open.
- [x] 3.4 The attached document stays in the addressed destination and survives a reload, exactly as
      today. Two documents open for reading at once, with only one attached, must work.

      Done 2026-08-18. The destination-to-store sync now opens the attached document's tab keyed by
      `tabKeyForNode` (id-or-path) rather than closing whatever tab preceded it — the old
      close-previous/open-next pairing was P2b's single-tab-only shape; multi-tab means attaching a
      new document no longer implies anything about tabs already open for other documents. Keyed
      off the *computed key* (a ref holding the previous `attachedTabKey`, not the previous
      `document` path), for two reasons at once: a rename that keeps the same Hub id produces the
      same key, so the effect correctly does nothing on rename (the tab that already exists for
      that id is still valid, per D4); and the one-time upgrade from a path-keyed fallback to a
      real id, once the specs list finishes loading after mount, is handled by the same effect
      rather than needing a second one, since the key itself changes even though `document` did
      not. Reload survives because the effect runs once on mount from an empty ref and opens
      whatever the destination already names — unchanged in substance from P2b, just re-derived
      through the id-aware key. Two-tabs-with-one-attached is a direct consequence of "never closes
      an unrelated tab" above; tested explicitly (see 3.6's new cases) rather than assumed from the
      absence of a counter-effect.
- [x] 3.5 An archived document's tab still opens and shows the archived marker `SpecDocumentPanel`
      already renders.

      Done 2026-08-18, confirmed rather than assumed unbroken: `SpecDocumentPanel`'s archived-marker
      rendering (`spec-archived-marker`, driven by `inventory.byPath.get(path)?.archived`) was
      never touched by this task, and `resolveTabPath` always resolves to a real path before
      `SpecDocumentPanel` sees it — an archived document opened from the new `specs` index tab
      reaches the same component the same way a P2b-era attach did. New test: "opening an archived
      document from the index tab still shows the archived marker"
      (`hub/ui/src/__tests__/specNavigationUi.test.tsx`).
- [x] 3.6 Regression pass over `spec-chat-session`'s existing scenarios — this change modifies that
      capability and every guarantee it already made has to survive.

      Done 2026-08-18. Ran the full existing suite first (`npx vitest run`) before writing anything
      new, to find what section 3 actually broke rather than guessing: exactly one failure,
      `specNavigationUi.test.tsx`'s `'closing the panel asks the destination to drop the document'`
      — which asserted the *old, fused* behavior 3.3 deliberately ends. Rewritten (not deleted) to
      assert the new contract: the tab closes, `onOpenDocument` is never called, and the shell shows
      its empty state. Nothing else in the 1028-test suite broke, including
      `'routes a valid relative cross-document link through the destination'`
      (`specNavigationUi.test.tsx`) — the test that pins `onSelectPath`'s current behavior for
      in-document links and is exactly why `onSelectPath` was deliberately left wired to
      `onOpenDocument` in 3.3 rather than redirected to a read-only tab open: redirecting it would
      have broken this pinned, pre-existing guarantee.

      **The gap that decision leaves, stated rather than silently accepted:** a document opened for
      reading but *not* attached (via the new `specs` index tab, or a second document opened
      alongside the attached one) can still silently reattach the conversation if the operator
      clicks an internal link inside it — because `onSelectPath` doesn't distinguish which tab it
      was called from. This is a real, easily-triggered edge of 3.4's "two documents open for
      reading, only one attached" guarantee for any document that happens to contain links, and it
      existed in weaker form even before section 3 (there was only ever one tab to click links in).
      Not fixed here because fixing it means changing `onSelectPath`'s wiring, which is exactly what
      the pinned regression test above forbids without also deciding what that test *should* assert
      instead — a design call, not a mechanical one, and out of this task's scope.

      **New coverage**, beyond the rewritten test above (all in
      `hub/ui/src/__tests__/specNavigationUi.test.tsx` unless noted):
      - the specs index tab is offered from the plus affordance;
      - selecting a document from the index tab opens it as a reading tab without calling
        `onOpenDocument` (D9's core guarantee, from the reading side);
      - a document whose entry carries `document_id` opens a tab keyed by that id, not by path;
      - two documents can be open for reading at once with only one attached, and opening the
        second does not close or detach the first;
      - opening an archived document from the index tab still shows the archived marker (3.5);
      - `hub/ui/src/__tests__/specChatSurface.test.tsx` — with the real `ComposerSpecControl`
        mounted (the previous file stubs `AgentOutputPanel` out entirely, so it cannot see the
        composer pill): closing the reading tab leaves `composer-spec-control` still naming the
        attached document, exactly user test guide step 3's wording ("If the pill clears, 3.3 is
        wrong").

      **Verification, measured:** `npx vitest run` — 1034 passed across 102 files (was 1028 before
      this task; 6 new, zero regressions beyond the one intentional rewrite above).
      `eslint --max-warnings 0` and `npx tsc --noEmit`: both clean. Backend: `pytest hub/tests/
      test_spec.py hub/tests/test_spec_archive.py hub/tests/test_spec_rename.py` — 47 passed
      (covers every existing test that reads `GET /project/specs`, to catch anything relying on the
      response's exact shape now that `document_id` rides along). `ruff check` and `black --check`
      clean on the two touched Python files. `npx openspec validate --changes --strict`: 2/2 still
      pass.

## 4. The file content endpoint

- [x] 4.1 `GET /api/v1/workspace/file?path=...`, project-scoped, resolving through
      `project_workspace.resolve_project_workspace` like every other project-scoped route.
- [x] 4.2 Allowlist by **membership of `list_workspace_paths`'s own output** (design D7) — not a second
      containment check. Test traversal, a symlink pointing outside the workspace, and a `.gitignore`d
      path; all refused because the listing does not contain them, not because a separate sanitizer
      caught them.
- [x] 4.3 Size bound at `aw_max_body_size`'s existing default. Over the bound: refuse, naming size and
      bound. Test that no partial body is returned.
- [x] 4.4 Binary detection: NUL byte in the first 8,000 bytes. Test an extensionless text file (a
      `Makefile`) is treated as text and a small binary is not.
- [x] 4.5 Docker-mode path handling matches every other project-scoped route — container-visible paths
      beneath `AW_WORKSPACE_ROOT` only, no host-path guessing.

      **Done 2026-08-19, iteration 15.** Domain logic in `hub/hub/workspace_file.py`
      (`read_workspace_file`), schema in `hub/hub/schemas/workspace.py`
      (`WorkspaceFileResponse`), route `GET /file` added to the existing
      `hub/hub/api/v1/workspace.py` beside `/paths`, mirroring its exact
      `resolve_project_workspace` pattern (4.1, 4.5 — Docker parity is automatic:
      `resolve_project_workspace(session, project_id)` with no `workspace_root` override
      defaults to `configured_workspace_root()` internally, identical to `/paths`; no
      bespoke path handling exists in this route to diverge).

      4.2's allowlist is membership of `list_workspace_paths(workspace.root)`, exactly as
      D7 specifies. One thing D7 understates: membership alone is not a *content*
      guarantee, because `git ls-files` lists a symlink by its own path, not by where it
      resolves — so a listed path can still be a symlink whose target lives outside the
      workspace. The resolved filesystem path is therefore additionally passed through
      `ProjectWorkspace.resolve_relative`, the same established primitive
      `spec_documents.py` already uses for every other project-relative read (its own
      docstring: "refuses absolute paths, traversal, control characters and symlink
      escapes") — reuse of an existing, already-trusted primitive, not a second
      independently-reasoned check invented for this endpoint, so D7's rejection of that
      shape still holds. A manual empirical check that first appeared to show a real
      symlink-escape leak (reading a `secret.txt` outside the repo through a `leak.txt`
      symlink via git bash's `ln -s`) turned out to be a false positive: this machine
      lacks `SeCreateSymbolicLinkPrivilege`, and Git for Windows' `ln -s` silently falls
      back to copying the target's *content* into a plain file rather than failing —
      confirmed via `fsutil reparsepoint query` reporting "not a reparse point" and the
      file's on-disk size matching the target's content length exactly. `os.symlink`
      (used by the actual test) correctly raises `WinError 1314` and the test skips, same
      as `test_docker_workspace_root.py`'s own symlink test on this machine; a real
      symlink is exercised on CI (Linux).

      4.3's bound reads `settings.aw_max_body_size` fresh (confirmed 1_048_576, matching
      D7's "1 MiB" claim) — checked via `stat()` before any content is read, so an
      oversized file is refused with size and bound named in the message and never
      partially returned (tested at the HTTP layer: response body has no `content` key,
      both the file's actual size and the configured bound appear in the 413's text).

      4.4's binary detection is `b"\x00" in data[:8000]`, tested against a `Makefile`
      (extensionless, text) staying non-binary and a small PNG-header blob correctly
      flagged binary with `content: null`.

      New tests: `hub/tests/test_workspace_file_endpoint.py` (14 tests: 8 direct
      `read_workspace_file` unit tests + 5 HTTP-layer tests including a Docker-mode
      parity test that reuses `test_docker_workspace_root.py`'s own
      `resolve_project_workspace`-restoration trick; 1 skips on this machine for the
      reason above). `ruff check` and `black --check` clean on all four touched/new
      files (`hub/hub/workspace_file.py`, `hub/hub/schemas/workspace.py`,
      `hub/hub/api/v1/workspace.py`, the new test file) — one `N818` finding fixed by
      renaming the two new exception classes to end in `Error`
      (`WorkspaceFileNotFoundError`, `WorkspaceFileTooLargeError`) rather than adding a
      `noqa`. `mypy hub/hub/` (repo-root cwd): 361 errors in 86 files — identical to
      `.claude/autonomous/mypy-baseline.txt`'s total, zero new errors from this change.
      `npx openspec validate --changes --strict`: 2/2 still pass. Full suite was NOT
      re-run for this task — per `next_action`'s own note, that is deferred to the next
      section-12-equivalent close-out point for this change.

## 5. The files tab

- [x] 5.1 A `files` tree tab built from `GET /api/v1/workspace/paths`. Reuse or adapt
      `specNavigation.ts`'s `buildPathTree` (`:320-364`) rather than re-deriving tree building.
- [x] 5.2 Selecting a file opens a `file:<path>` tab **and closes the tree tab** (design D8).
- [x] 5.3 The file tab renders text content, states binary, and states a refusal for an oversized file
      with its size and the bound.
- [x] 5.4 "Insert into composer" produces the **same** mention format `composerTrigger.ts`'s `@path`
      trigger already produces. Test the two are byte-identical for the same file.
- [x] 5.5 Measure and state the `files` tab's minimum width against the real shell. Design D12 leaves
      this deliberately unstated; do not guess it, measure it, then write it down beside
      `SPEC_DOC_MIN_WIDTH` with the same kind of comment.

      **Done 2026-08-19, iteration 15/16.** 5.1: `buildFilePathTree` in `specNavigation.ts`
      is `buildPathTree`'s directory-grouping algorithm adapted (not re-derived) for
      `GET /workspace/paths`'s raw string listing — the two differences that keep it a
      second function rather than a shared call are that a workspace path has no manifest
      title (the filename is the only label there is) and no `spec/` prefix every entry
      shares to drop. `FileTree.tsx` renders it the way `SpecTree.tsx` renders
      `buildPathTree`'s rows, under its own `aw.files.treeCollapsed` storage key so folding
      a directory here never disturbs the specs tree's folded state. `FilesIndexTab.tsx` is
      `SpecIndexTab`'s counterpart: tree when nothing is typed, a ranked flat substring
      match once something is.

      5.2/D8: `panelTabsStore.openTab`'s reducer (already carrying a comment naming this as
      its own follow-up task) now filters `files` out of the tab list before appending a
      `file:` tab being opened for the first time — refocusing an *already-open* file tab
      does not touch `files`, and reopening `files` after a file tab is open does not close
      the file tab either (the asymmetry is one-directional, matching D8's own wording).
      Three new `panelTabsStore.test.ts` cases pin this, including the "reopening files
      after a file is open does not close the file" direction a naive "index gives way to
      detail" generalization would get wrong.

      5.3: `FileTab.tsx` reads through the new `useWorkspaceFile` hook
      (`hub/ui/src/api/workspace.ts`) and renders whichever of three states
      `GET /workspace/file` (task 4) reports — text in a `<pre>`, an explicit binary notice
      naming the size, or `readableApiError`'s rendering of the 404/413 response body (413's
      message already names both the file's size and the configured bound, from the
      endpoint's own text — task 4.3).

      5.4: `composerTrigger.ts` gained `formatMention(kind, value)`, factored out of
      `acceptTriggerResult` so both call sites produce the mention text from the *same*
      expression rather than two copies kept in step by hand — byte-identical by
      construction, not merely by a test asserting it (the test asserts it anyway,
      `composerTrigger.test.ts`). Wiring the button to a mounted `Composer` needed a real
      path across three components with no ref or shared state to reuse: `Composer` gained
      an `insertPathRequest?: {path, requestId} | null` prop (the same counter-keyed "do
      this again" shape `panelTabsStore`'s own `revealRequestId` already uses, since a plain
      boolean cannot tell a second insert of the same file apart from the first), consumed
      by an effect that appends the mention to whatever is already typed. Threaded through
      `AgentOutputPanel` verbatim and originated in `ConversationView`, which owns the
      counter. Five new `Composer` tests cover append-vs-replace, the quoting case, and the
      repeat/new-request-id distinction.

      5.5: measured with `.claude/autonomous/scratch/measure_files_tab_width.py`
      (gitignored, throwaway) against the live trial Hub — forced the document pane's own
      CSS width down directly (bypassing the app's current 360px floor, since that floor
      *is* the number under test) and found where `FileTab`'s header row (filename,
      "Insert into composer", close) first overflows: 248px. `FilesIndexTab`'s search box
      and tree stayed clean to 200px, so the header decides it. Recorded as
      `FILE_TAB_MIN_WIDTH = 260` in `specPreferences.ts` (a 12px margin above the measured
      248px, the same margin `CONVERSATION_MIN_WIDTH`'s own comment describes measuring
      against font-metric variance), and `minWidthForTabKind` now returns it for `file`/
      `files` instead of falling back to `SPEC_DOC_MIN_WIDTH`. `specs` still falls back to
      the spec document minimum — it was not measured this task, and D12 only named `files`.

      **A pre-existing gap, found but not fixed here (scope discipline, not an oversight).**
      `ConversationView.tsx`'s `panel` is `document ? <PanelShell/> : null` — the shell,
      files tab included, is unreachable unless a specification document is already
      attached to the conversation, even though `panelTabsStore.setShellOpen` exists
      precisely to let the shell open independently. That coupling predates this task
      (sections 2b/3) and fixing it is a real, separate change to `ConversationView`'s
      mount condition, not a files-tab task — recorded in `decisions_for_user` rather than
      patched in passing.

      **Verification.** `hub/ui/src/__tests__/{fileNavigation,filesIndexTab,fileTab,
      panelTabsStore,composerTrigger,conversationComposer}.test.ts(x)`: full suite
      1064 passed (0 skipped), up from the 1014 baseline at prep. `tsc --noEmit` and
      `eslint --max-warnings 0 src` both clean. Live, against the trial Hub (`ui` rebuilt,
      `refresh_ui_bundle.py` run, stamp verified with `--check`): new
      `hub/tests/browser/test_files_tab.py`, 7/7 passed — plus-menu discovery, the empty-
      workspace statement, a real tree-row click opening a file and closing `files` (D8,
      live), the 404 refusal live against this fixture project's genuinely empty workspace
      listing, "Insert into composer" landing in the real composer textarea, and the
      measured 260px width holding (240px does not, confirming the assertion is anchored to
      the right element and not vacuous). Full `hub/tests/browser` suite: 48/48 passed
      (up from the 33-passed baseline). `ruff check` and `black --check` clean on the new
      test file. Full `hub/tests/` and `tests/` suites NOT re-run this task — no Python
      source under `hub/hub/` changed (only a new browser test file), so `mypy hub/hub/`'s
      361-error baseline is unaffected and was not re-checked.

## 6. Strip overflow

- [x] 6.1 Decide overflow behaviour once real tabs exist and more are open than fit. T3 does one native
      `scrollIntoView` for the newly active tab and nothing else; start there and only add if it
      measurably fails. Record what was chosen and why.

      **2026-08-19.** Read D12 fresh (design.md:202-206: "T3 does one native `scrollIntoView` for
      the newly active tab and nothing else... start there and only add if it measurably fails")
      and studied `testbed/scratch/t3ref/src/components/RightPanelTabs.tsx:376-379` for the
      pattern (reference only, not copied — T3's version queries a `data-active-tab` attribute via
      `querySelector`; this shell already keeps a `TabId -> HTMLButtonElement` ref map for keyboard
      focus movement, so the equivalent lookup reuses that map instead of adding a second way to
      find a tab element).

      **Chosen: exactly T3's answer, nothing more.** `PanelShell.tsx` gained one `useEffect`
      keyed on `panel.activeTabId` that calls `tabButtons.current.get(activeTabId)
      ?.scrollIntoView({ block: 'nearest', inline: 'nearest' })`. The strip was already
      `overflow-x-auto` (task 2's own markup), so horizontal scrolling already worked when tabs
      exceeded the visible width — what was missing was the *newly active* tab being brought into
      view automatically, e.g. after `ArrowRight`/`ArrowLeft` moves activation past the edge, or
      opening a tab from the plus menu while the strip is already scrolled. The effect fires on
      every activation change regardless of cause (click, arrow key, or opening a new tab), which
      matches T3's `[props.activeSurfaceId]` dependency exactly — one behaviour, not
      one-per-trigger. Did not add anything beyond this: no manual overflow indicators, no
      "scroll left/right" chevrons, no tab reordering or pinning. Nothing in manual exercise of
      the live shell (many tabs open, narrow window, keyboard-only navigation past the visible
      edge) showed the plain `scrollIntoView` failing to bring the target tab into view, so per
      D12's own instruction there is nothing to add.

      **Verification.** `hub/ui/src/__tests__/panelShell.test.tsx` gained a new
      `describe('task 6.1 — the newly active tab scrolls into view')` block (2 tests): scrolling
      on click-activation, and scrolling on arrow-key-driven activation (not just tab-open),
      spying on `Element.prototype.scrollIntoView` (already stubbed as a no-op globally in
      `__tests__/setup.ts` for jsdom, which doesn't implement it) and asserting both the call args
      (`{block:'nearest', inline:'nearest'}`) and that it fired on the now-active tab's own button
      element specifically, not some other element in the strip. Full vitest suite: 1066 passed
      (up from the 1064 baseline after P5), 0 skipped. `tsc --noEmit` and
      `eslint --max-warnings 0 src` both clean. UI rebuilt (`npm run build`), files staged before
      `refresh_ui_bundle.py` (both already tracked, so the untracked-file trap did not apply this
      time), stamp verified with `--check`. Live: `hub/tests/browser/test_panel_shell.py`, 8/8
      passed; full `hub/tests/browser` suite, 48/48 passed. Manually confirmed both a full pass
      without my change (via `git stash`/rebuild/retest) and with it that the same test
      (`test_the_specs_index_tab_opens_from_the_plus_affordance`) flakes independently of this
      change — different tests failed across separate runs of the untouched baseline, and the
      failure mode (a plus-menu click's `aria-selected` not flipping) has no relationship to a
      `scrollIntoView` effect; recorded as pre-existing infra flakiness, not a regression. No
      Python under `hub/hub/` changed this task, so `mypy hub/hub/`'s 361-error baseline was not
      re-checked (unaffected by construction). `ruff`/`black` not applicable — no Python files
      touched.

      **The panel change's agent-verifiable work is now complete.** Sections 1-6 are all done;
      only section 7 (7.1-7.5, the operator's own judgement) remains, and this run does not tick
      those per the standing limit.

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
