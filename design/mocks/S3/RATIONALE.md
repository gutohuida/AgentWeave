# S3 rationale — the right side panel

Four passes (P1 explore, P2 validate + mock, P3 iterate, P4 finish — this document).
`PanelShell.tsx` and its five tenants (`FileTree`, `FilePreview`, `SpecIndexTab`, `LoopsIndexTab`,
`FilesIndexTab`). Unlike S1/S2, this surface is described in the queue as "always on screen while
working" — chrome the operator lives beside constantly rather than a page they navigate to, so
plainness here reads as a background irritant rather than a one-off bad first impression. That
framing shaped the P2 choice below on why no third "expressive" variant exists for this screen.

## Research → changes

Full findings and sourcing live in `RESEARCH.md` (T3 Code's `RightPanelTabs.tsx` /
`RightPanelSheet.tsx` / `FileBrowserPanel.tsx`, plus general side-panel/file-tree/code-preview
convention research). Nine verified gaps, all confirmed by reading the actual component files —
not assumed from the outside — before building anything.

1. **No hover/press/focus-visible state on any row**, across `FileTree`, `FilesIndexTab`,
   `LoopsIndexTab`, and `SpecDocumentBrowser`'s search results — despite `--row-hover` /
   `--row-active` / `--row-selected` already existing in `index.css` and being unused in all five
   files (`grep`-confirmed, zero hits). Both variants apply them; `considered` layers a left accent
   bar on the selected row on top of the token fill, `restrained` uses the token fill alone.
2. **Tab strip had no hover feedback on inactive tabs**, no tooltip on a truncated label, no context
   menu, and a redundant always-visible close icon competing with the descriptor icon for the same
   horizontal space. `considered`: T3-pattern crossfade (icon → close glyph on hover, one slot, not
   two), a `title`-based tooltip on the label, and a demonstrated (not wired) right-click context
   menu shown in its own labelled column beside the tab strip — captioned explicitly as
   "not implemented here, only demonstrated" so it reads as a proposal, not a broken control.
   `restrained`: hover feedback and the tooltip only, no crossfade, no context-menu illustration —
   the smaller, real fix without the speculative addition.
3. **Launcher empty-state cards had no interaction states at all** — no hover, no press, no
   focus-visible ring beyond the browser default — and discarded information the app already
   computes: `LoopsIndexTab` knows `counts.running` but the empty-state Loops card never shows it.
   `considered`: hover lift + border, press settle, a live count badge on the Loops card.
   `restrained`: hover border-colour swap only, no lift, no badge — a real state change without the
   extra commitment of a numeric badge on a static launcher.
4. **`FilePreview` had no path header, no copy button, no visible language indicator** beyond
   filename inference — the file's full path was knowable only from the tree it came from or a
   truncated tab label. Both variants add a persistent header: breadcrumb path + copy-path button +
   language chip. `considered` adds a refresh control alongside; `restrained` omits it — a preview
   pane doesn't need a manual refresh affordance to demonstrate the header gap is fixed.
5. **Search inputs (files, specs) had no icon, no Escape-to-clear, and no visible affordance**
   beyond placeholder text. Both variants add a leading search icon and an inline clear button that
   appears once text is typed.
6. **`LoopsIndexTab`'s "Show archived" is a bare native checkbox**, while U0b already defined a
   `.ctl-switch` toggle vocabulary this exact control should be using. Both variants swap it for the
   real switch control from `controls.html` — not a new control, the one already specified.
7. **Loading states were a plain `Loading…` paragraph** in three of the five tabs, while
   `foundations.html` already defines skeleton primitives sized for exactly this use. Both variants
   replace the paragraph with `.sk-row`/`.sk-line`/`.sk-chip` skeletons shaped like the real rows
   they precede, matching `LoopsIndexTab`'s row shape specifically (the point of a skeleton is that
   it previews the shape of what's coming).
8. **Directory rows always render `folder_open`'s glyph regardless of collapsed state** — a real,
   present-tense gap: `Icon.tsx`'s map has no closed-folder entry, so `FileTree.tsx` can't
   distinguish the two states even though it tracks `collapsed[row.path]`. This is a source-level
   fix (a new `Icon.tsx` map entry), out of a mock's scope per `limits`. Both variants demonstrate
   the corrected visual only — an open glyph for expanded rows, a closed one for collapsed rows,
   using inline SVGs the same way S1/S2 already do rather than depending on the live component map
   — and flag the real fix here rather than silently leaving the gap unmocked.
9. **No connecting structure in the file tree beyond indentation.** `considered` adds a 1px
   `--border` guide line per the research note that a connecting guide is structure, not the
   literal "texture" clause 7 rejects. `restrained` keeps indentation alone — this was the one
   candidate finding closest to the rejection-test boundary, and `restrained`'s job is specifically
   to be the variant that doesn't take it.

## A bug found by looking, not by reading source (P3)

Both `restrained.html` and `considered.html` attached the theme-toggle label's
`addEventListener('click', …)` **before** the trailing icon-substitution step
(`document.body.innerHTML = document.body.innerHTML.replace(...)`), which rebuilds the entire
`<body>` from a string to swap in the real SVGs. That rebuild discards every DOM node the listener
was attached to; the inline `onclick` that flips `dataset.mode` survives because it's plain markup
reflected into the new nodes, so the theme itself still switched correctly — only the runtime
listener updating the `dark`/`light` label text was orphaned. In the light-theme screenshots this
showed as a toggle button that visibly worked (the whole page changed to the light palette) while
its own label kept reading "dark". Found by screenshotting and reading all four PNGs, confirmed by
a direct Playwright before/after check (`dataset.mode` vs. `#theme-label.textContent`), fixed by
moving the `addEventListener` call to after the `innerHTML` replace in both files, then
re-screenshotted and re-read to confirm. `S2/considered.html` has the identical ordering bug —
confirmed by the same check — and was deliberately **not** fixed here as out of scope for this
screen's pass; `S1` has no `#theme-label` span so it never carried this bug.

## What was rejected, and under which clause

- **A third "expressive" variant.** Considered explicitly for this screen because it's chrome the
  operator sits beside constantly rather than a navigated-to page — a case that could have argued
  either way. Rejected: this panel is peripheral to where attention is actually meant to go while
  working, and an expressive treatment on chrome that is supposed to recede risks reading as
  clause 5's "complete jump in design" more than S1/S2's own navigated screens would. Two variants
  stands, same count as S1/S2, but for this screen-specific reason rather than an unexamined
  default carried over from them.
- **Building the tab context menu, or middle-click-to-close, for real.** Both are missing features
  (`RESEARCH.md` findings 4–5 from the T3 comparison), not styling gaps. `considered` illustrates
  the context menu only, in its own labelled column, explicitly captioned as not implemented — per
  `pre_authorised`'s "mock it and note it, don't implement it."
- **A dedicated `Tooltip` component.** Grepped `hub/ui/src/components` for `Tooltip` — none exists
  anywhere in the app; 54 files use native `title=` only. The CSS-only `::after` tooltip in
  `considered` isn't diverging from an established pattern, since none exists — it's proposing one
  where there is a gap, correctly scoped as a missing-feature note rather than a risk to reconcile
  against an existing component.
- **Fixing the closed-folder icon in `Icon.tsx` for real.** Finding 8 is a source-level fix; mocks
  demonstrate the corrected visual only, per `limits`'s mock-only constraint (C6 is the sole
  exception and this isn't it).
- **A second, competing empty-state pattern.** `foundations.html`'s general `.empty-state` primitive
  and `PanelShell`'s own bespoke launcher grid were checked against each other before building —
  they don't disagree; the launcher grid is the right-fit specific instance the general primitive
  already anticipates, so both mocks keep the launcher-grid structure and apply the general
  primitive's *states* (hover/press/focus) to it, rather than replacing it.

## What's already good and was left alone

Carried forward from `RESEARCH.md`'s P1 findings, confirmed still true after building and two full
render-and-read passes: `PanelShell`'s ARIA `tablist` with roving `tabIndex` and arrow-key/Home/End
navigation (design D11); `scrollIntoView` on tab activation for strip overflow (design D12);
`FilePreview`'s deliberate refusal to reuse `MarkdownMessage` — a workspace file is content the
operator opened themselves, agent output is not, and that trust boundary is untouched in both
mocks; `fileIcons.ts`'s whole-filename-before-extension precedence and its colour-carries-
recognition reasoning at 12px; `LoopsIndexTab`'s ending-state bucketing from `ending_state` rather
than `stop_reason` text (design D17) and its agent-attribution row; `SpecDocumentBrowser`'s
current/archived/missing grouping, including missing-but-visible documents; the chevron rotation in
`FileTree`, already correctly on the motion scale before this pass touched anything. None of these
were changed — both mocks add appearance and feedback only, never the interaction or information
architecture these decisions protect.

## Live before-shot: not captured this pass, and why

`next_action` going into this iteration asked for a screenshot of the current live `PanelShell` via
the trial Hub on port 8010. The trial Hub was already running (PID open since before this iteration
started, project `proj-5e960453` loaded) — but that project has zero agents, and `PanelShell` only
mounts inside `ConversationView`, which requires an active agent conversation to reach. Getting a
live shot would have meant creating a runner and an agent in the trial database purely to open a
panel for one screenshot — a real, if small, state mutation to a shared instance, and more setup
than this pass's scope justified for a shot neither S1 nor S2 actually took either (both screens'
`index.html` entries and `RATIONALE.md`s only ever compare mock-to-mock, e.g. the toggle-label
before/after above, never live-app-to-mock). Matching that established precedent rather than the
aspirational note in the prior iteration's `next_action`; not treating this as a gap to revisit.
