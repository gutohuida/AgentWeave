# S5 research — the rendered spec documents

Per `decisions_for_user` D-spec-render: this screen is generated server-side in Python
(`hub/hub/spec_render.py`), not a React component. A mock is HTML either way, so the process is
unchanged — but implementing anything found here later touches Python string-building, not
components, and that is noted plainly rather than glossed over (repeated in `RATIONALE.md` at P4).

## What was read

- **`hub/hub/spec_render.py`** (full, all 533 lines, including every comment). The renderer's own
  design notes are unusually explicit and were treated as binding, not merely descriptive:
  anchors cannot dangle (identifiers are minted once and reused for the link and the target), the
  document carries no navigation script of its own (the *shell* — `specBridge.withSpecBridge` —
  owns same-document anchor interception), and `_STYLE` is the document's **own, separate** token
  namespace (`--bg/--fg/--muted/--border/--surface/--surface-2/--aw-accent/--aw-warn/--aw-ok`) —
  not `hub/ui/src/index.css`'s tokens. This is a real constraint on how `IDENTITY.md`'s rejection
  test clause 1 applies here — see "A genuine tension" below.
- **`hub/ui/src/components/spec/SpecFrame.tsx`** (full). The sandboxed iframe host: `sandbox=
  "allow-scripts"` with no `allow-same-origin` (opaque origin, message-identity instead of origin
  checking), `srcDoc={withSpecBridge(withHubTheme(content, mode))}` — two wrapping passes before
  anything paints.
- **`hub/ui/src/components/spec/hubTheme.ts`** (full, including its comments). Confirms exactly
  which six neutral custom properties the Hub overrides (`!important`, appended before `</head>`)
  and which four it deliberately leaves alone (`--aw-accent/--aw-warn/--aw-ok` plus the document's
  `color-scheme`) — "those carry meaning inside the specification and are not the Hub's to
  recolour." A prior incident is recorded in the comments: the document's own `--surface` used to
  be *darker* than the Hub's light `--bg`, so re-grounding without remapping the whole ramp
  inverted every lifted block. Whatever this mock changes about surfaces must keep the ramp moving
  together, the same way.
- **`hub/ui/src/components/spec/SpecDocumentPanel.tsx`** (full). The chrome *around* the iframe —
  breadcrumb, `SpecPhaseBar`, `SpecCoverageBar`, `SpecProposalsPanel`,
  `SpecDocumentTasksLink`, a drift-diagnostics disclosure, a nav-rejection toast, and a 200px
  outline sidebar built from `toc-ready` postMessage anchors. **This chrome is a different,
  already-styled React surface and is out of scope for S5** — S5 is the document `spec_render.py`
  itself produces, per the queue item's own framing. Read in full anyway, because two of its
  decisions constrain the mock: the shell's outline sidebar means the document must **not** invent
  its own sticky TOC (that would duplicate what the shell already renders outside the frame, the
  same non-duplication argument `spec_render.py`'s own module docstring already makes for
  navigation script), and `withHubTheme` stamps `data-theme` onto `<html>` so the mock's own
  three-layer cascade (`:root` / `prefers-color-scheme` / `:root[data-theme]`) must stay intact for
  the Hub-embedded path to keep working, not just the standalone-file path.
- **A real generated document**, `spec/capabilities/task-lifecycle-governance/spec.html`
  (1204 lines) — read in full, not sampled, specifically because it is dense: 32 requirements, a
  110-row acceptance-criteria table, real production prose. This is what "realistic content" means
  for this screen and is where every finding below actually comes from, not from an imagined
  document. Two things only a real document showed:
  1. **108 of 110 acceptance-criteria rows have an empty "Given" cell** — confirmed both by reading
     the table and by the document's own `Limits` section, which names this
     (`scenarios-state-no-starting-state`) as a known, deliberate limitation of the source
     translation. The rendered table gives that empty column exactly the same width and border
     weight as the two populated ones.
  2. **Rationale prose regularly runs longer than the requirement statement it explains** (e.g.
     FR-21's rationale is roughly triple the length of FR-21 itself). `_requirements()` renders
     both as a plain `<p>`, differing only by the rationale's muted colour — secondary content
     given the same typographic weight as the primary claim.
- **`.agents/skills/aw-spec-apply/html-spec-conventions.md`** — the **legacy**, pre-Hub convention
  for a different, agent-authored `spec.html` (`change-spec`/`roadmap`/`system-map`/`baseline`
  kinds, not the `SpecPayload` schema `spec_render.py` renders today). Per `CLAUDE.md`, the `aw-*`
  skills are product source to be implemented, not workflow to run — this file was read purely as
  **design reference**, the same status `IDENTITY.md` gives T3 Code, not as something this mock
  should treat as the current contract. Two things in it are still useful precedent even though
  they don't apply verbatim: its skeleton badges MUST/SHOULD/MAY as filled pills
  (`.badge-must { background: var(--danger-bg); color: var(--danger); }`) rather than coloured
  text, and it dedicates a sticky `header.spec-header` with a live progress bar computed from task
  elements — both superseded here (progress bars need a `data-status` this payload doesn't carry;
  the sticky TOC is superseded by the shell's own outline sidebar, confirmed above), but the pill
  treatment for modal badges is a legitimate steal *within* `spec_render.py`'s own existing tokens.
- **T3 Code sourcemaps** — grepped for any component resembling a document/spec/plan viewer
  (`TableOfContents`, `DocViewer`, `PlanView`, `SpecView`, `Requirement`, `Markdown`,
  `ReactMarkdown`, `prose-`) across all 384 maps. The only hit was a syntax-highlighting grammar
  file (`@shikijs/langs/.../markdown.mjs`) — not a component. **T3 Code has no comparable surface
  to study here**; it is a chat-first product with no document-authority screen at all, unlike
  every other screen in this queue. External research therefore carries more of this pass's weight
  than usual, and is reported as such rather than papered over with an invented comparison.

## A genuine tension with `IDENTITY.md` clause 1, and how it resolves

`IDENTITY.md`'s rejection test clause 1 says "every colour resolves to an existing token in
`hub/ui/src/index.css`." Read literally that cannot apply to this screen: `spec_render.py`'s `_STYLE`
is deliberately a **separate, self-contained token namespace** — the document renders standalone,
outside any Hub, and `hubTheme.ts`'s own comment states the four semantic hues
(`--aw-accent/--aw-warn/--aw-ok` and the fourth would-be danger tone it doesn't yet define) are
"not the Hub's to recolour." Treating clause 1 as "must use `--blue`/`--amber` etc." would mean
either breaking the document's standalone contract or fighting `hubTheme.ts`'s own stated boundary.
The reading that keeps clause 1's actual intent (no invented hues, no arbitrary hex) while
respecting this screen's real architecture: **every colour in the mock resolves to an existing
custom property already declared in `spec_render.py`'s own `_STYLE` block** (`--aw-accent`,
`--aw-warn`, `--aw-ok`, `--bg`, `--fg`, `--muted`, `--border`, `--surface`, `--surface-2`) — no new
hue, no literal hex outside what a token already contains, same rule, applied to the document's own
existing vocabulary rather than the Hub's. This is stated up front so P2's validation pass applies
it consistently rather than improvising a call mid-mock.

## External research

- **API reference documentation practice** (Speakeasy, Stoplight, and related developer-docs
  guides): the shared advice is "instantly scannable via bold combinations of whitespace, fonts,
  and visual hierarchy" versus "walls of text with buried important information," and structuring
  by the natural hierarchy of the content with strong cross-references. Directly names this
  document's actual failure mode — 32 nearly-identical-looking requirement blocks and a 110-row
  table are exactly a wall of text once the one 3px border is the only differentiation.
  ([Speakeasy — API documentation](https://www.speakeasy.com/api-design/documentation/),
  [Stoplight — API documentation guide](https://stoplight.io/api-documentation-guide))
- **Long-document reading UX** (Nielsen Norman Group and related 2025/2026 sources): a scroll
  progress indicator answers "how much is left," a sticky/active-highlighted TOC answers "where am
  I" — both recommended once a document passes roughly five H2 sections. This document's shell
  already supplies the "where am I" half (`SpecDocumentPanel`'s outline sidebar, active-section
  highlighting via `aria-current`) but nothing answers "how much is left," and the outline is
  section-level only — inside "Requirements" a reader has no way to tell they are at FR-6 of 32
  without scrolling past it. ([NN/g — Table of contents design guide](
  https://www.nngroup.com/articles/table-of-contents/))
- **Badge/status-pill design practice** (general 2026 UI-pattern sources): pick one content type
  per badge and keep contrast high; a filled pill (background + foreground) reads faster at a
  glance than colour-on-text alone, which is exactly the legacy convention's `.badge-must` idiom
  above and the same "icon/fill + colour, not colour-on-text alone" principle S2's and S4's own
  research already invoked for task cards and DAG nodes — this screen inherits that same idiom
  rather than deciding it fresh. ([Eleken — Badge UI design](
  https://www.eleken.co/blog-posts/badge-ui-design))

## What's actually missing from *this* screen, specifically

1. **Modal tone (MUST/SHOULD/MAY) is a 3px border colour plus a coloured word** — the single most
   important scan signal in a document that is otherwise 32 visually-identical grey blocks, given
   the least visual weight a semantic signal could have. No pill, no background, nothing that reads
   at a glance while scrolling past rather than reading each line.
2. **Rationale and requirement statement have inverted visual weight** — confirmed on a real
   document (FR-21) where the "why" prose is several times longer than the "what," rendered in the
   same size, differing only by a muted colour that is easy to miss entirely on a fast scroll.
3. **The acceptance-criteria table wastes width on an all-but-empty column** — 108/110 rows in the
   sampled real document have no "Given," yet the column is drawn at full, unconditional width on
   every row, pushing "When"/"Then" — the columns that actually carry content — narrower than they
   need to be.
4. **No sense of "how far into this document am I,"** beyond the shell's section-level outline.
   Once inside a 32-requirement or 110-row section, nothing local orients a reader — no requirement
   counter, no visual grouping of the acceptance table by requirement beyond sort order (confirmed:
   `_acceptance()` already groups rows by requirement position, but nothing in the rendered HTML
   shows that grouping — a reader sees 110 undifferentiated `<tr>`s).
5. **No copy-anchor affordance on a requirement's own id.** `requirement_anchor()` mints a stable,
   collision-free `#FR-N` specifically so links never dangle — but the only way to get that link
   today is to already be inside the document and manually build a URL; the `<span class="aw-id">`
   is inert text, not something a reader can right-click or click-to-copy.
6. **Tasks render as a bare `<ul>` with trailing muted "satisfies" text** — same "wall of
   near-identical list items" problem as the requirements section, one level down.
7. **The corpus map's children are undifferentiated rows** — `_map_child()` produces
   chip+chip+paragraph per child with no visual separation between siblings; a home document with
   many children (today's corpus has 41 documents server-side) renders as one long unbroken list.
8. **`.aw-nav` (Home/parent breadcrumb, inside the frame) sits directly above the shell's own,
   differently-styled breadcrumb** (icon + truncated title + chevron, in `SpecDocumentPanel.tsx`) —
   two navigation affordances, adjacent, in two unrelated visual languages, for a broadly similar
   purpose (finding another document).
9. **Loading state is bare text** — `SpecDocumentPanel.tsx:310` and `:325` both render plain
   "Loading…" / "Loading spec…" strings — same finding pattern S1–S4 already made for their own
   screens, extended here.
10. **The meta chips row and summary line are already the best-styled part of the document** (see
    below) — but everything below them regresses to plain paragraphs and an unstyled table, so the
    document's one considered screenful is also its only one.

## What's already good and must not be redesigned

- **The three-layer theme cascade** (`:root` → `prefers-color-scheme` → `:root[data-theme]`) and
  `hubTheme.ts`'s neutral-only override — this is a tested contract
  (`hubVisualLanguage.test.ts` pins token parity) solving a real, previously-shipped bug (dark
  scrollbar on a light document, a re-grounded surface inverting its own lift plane). Not a styling
  gap; do not touch the mechanism, only what paints inside it.
- **The phase/rigor/modal colour *assignments*** — `_PHASE_TONE`, `_RIGOR_TONE`, `_MODAL_TONE` are
  already deliberately reasoned in the module's own comments (why `current`/`approved` take the
  done tone, why `kind` stays plain, why MUST and SHALL share a tone under RFC2119). The gap is
  visual *weight*, not the mapping — keep every existing assignment.
- **Anchor stability and the single `requirement_anchor()` definition** — a correctness property,
  not a display choice; a mock demonstrating a copy-link affordance must use the same anchor, not
  invent a second identifier scheme.
- **The summary line above the fold** (`_summary()`) — already exists specifically to fix an
  earlier "entirely monochrome first screenful" complaint (per its own comment) and already carries
  the modal colour scheme. Extend its visual treatment; do not replace the idea.
- **No navigation script inside the document itself** — deliberate (the shell owns it); a mock must
  not add a competing anchor-click interceptor or TOC, per the module's own stated boundary.

## Next

P2: validate every finding above against `IDENTITY.md`'s rejection test — applying clause 1 as
scoped above (the document's own existing tokens, not `hub/ui/src/index.css`'s) — then build
`design/mocks/S5/<variant>.html` in two or three degrees of refinement, using the real
`task-lifecycle-governance` document's density (30+ requirements, a 100+ row acceptance table,
long rationale prose) as the realistic content, not a short toy example. Show both a `light`/`dark`
pair per variant, per the standing instruction. Because this document is also a real standalone
artefact (opened outside the Hub, `color-scheme: light dark` honouring the OS preference), consider
demonstrating that path too, not only the Hub-embedded one `hubTheme.ts` produces — worth deciding
explicitly at P2 rather than defaulting to only the embedded case.
