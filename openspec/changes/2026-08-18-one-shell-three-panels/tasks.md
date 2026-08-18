# Tasks — One shell, many tabs

Nothing in this file has been started. Every box is unchecked because this change is a spec only —
CLAUDE.md: "Never mark a task complete on the strength of a plan existing."

**Rewritten 2026-08-18** alongside the proposal, design and specs. The loop panel's tasks are gone —
they live in `2026-08-18-a-loop-writes-its-own-queue` (B5, B6), which owns the data they display.

Sequence matters here: **1 → 2 → 3 before 4 or 5.** The shell's contract has to exist before anything
is built against it, or the file tab gets built against `SpecDocumentPanel`'s current one-off shape
and re-plumbed later — the cost the exploration named and this ordering exists to avoid.

## 1. The tab store

- [ ] 1.1 A per-project tab store: which tabs are open, their order, which is visible, whether the
      shell is open. Keyed by project id. Persisted to `localStorage` under a **versioned** key.
- [ ] 1.2 Tab kinds as a fixed literal union with template-literal ids: index kinds take a fixed id
      (`specs`, `files`), detail kinds a keyed one (`spec:${documentId}`, `file:${relativePath}`).
      Design D3/D4 — key by durable id where one exists; only files key by path.
- [ ] 1.3 Open/close/activate/reorder actions. Opening an already-open keyed tab **refocuses and
      re-reveals** rather than duplicating (a reveal counter, T3's `revealRequestId` shape).
- [ ] 1.4 `closeOthers` / `closeToRight` / `closeAll`, since a strip that accumulates tabs needs them
      and they are cheap once the store exists.
- [ ] 1.5 A migration function invoked on load when the stored version is older than current. Write it
      now even though there is only version 1 — retrofitting versioning after shipping is what forces
      a silent data loss.
- [ ] 1.6 Reconciliation on load: drop a `file:` tab whose path is not in the workspace listing.
      `spec:` tabs are keyed by document id and survive rename, so they need reconciling only against
      a document that no longer exists at all.
- [ ] 1.7 The two restore rules from design D5, each with its own test: every tab dropped ⇒ the shell
      restores **closed**, not open and empty; the visible tab dropped but others surviving ⇒ promote a
      survivor.
- [ ] 1.8 Unit tests for the store: persistence round-trip, migration from a stale shape,
      reconciliation, refocus-not-duplicate, and both restore rules.

## 2. The shell

- [ ] 2.1 Shell component owning the strip, the plus affordance, and the visible tab's content. One
      tab's content rendered at a time.
- [ ] 2.2 Move `ConversationView.tsx`'s panel-hosting block (`:150-291`) into the shell. Do **not**
      rewrite `SpecDocumentPanel`'s internals — this is a re-hosting, and the breadcrumb, archived
      marker, phase and coverage bars, proposals panel, `SpecFrame` bridge and outline rail must all
      still work afterwards.
- [ ] 2.3 Generalize the breakpoint: compute the combined minimum from the **visible tab's** own
      minimum rather than `SPEC_DOC_MIN_WIDTH` specifically, keeping it *derived* so threshold and
      layout cannot disagree (`ConversationView.tsx:34-38`).
- [ ] 2.4 Overlay below the breakpoint using the existing `Drawer`, with the reopen affordance kept.
      Dismissing the overlay keeps the tabs.
- [ ] 2.5 Width stays `specPreferences.ts`'s single global value. Extend that store; do not invent a
      second one.
- [ ] 2.6 Keyboard: ARIA `tablist`, sequential focus, `Enter`/`Space` to activate, arrow keys between
      tabs, close control reachable, plus menu navigable. Design D11 — nothing here to inherit.
- [ ] 2.7 `Icon` only for every control in the strip. CLAUDE.md forbids a second icon system; audit
      the map before assuming a close or plus glyph exists.

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
