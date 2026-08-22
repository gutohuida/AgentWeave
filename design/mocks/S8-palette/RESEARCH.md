# S8-palette — research (P1)

## The component

`hub/ui/src/components/palette/CommandPalette.tsx`, opened by `Cmd+K`/`Ctrl+K` (`App.tsx` wires it
alongside the other top-level chrome). It is a thin wrapper around [`cmdk`](https://cmdk.paco.me/)
(`Command.Dialog`) — cmdk ships zero styling, only `cmdk-*` data-attribute hooks, styled in
`hub/ui/src/index.css:324-372` under a comment that already states the intent: *"composes with the
app's own tokens rather than a competing look."* That intent is sound; the styling that exists
under it is minimal, not wrong.

Four flat groups, always all rendered together, never filtered by "mode": **Agents**, **Tasks**,
**Spec documents**, **Conversations** — each a `Command.Group` with a heading, populated from props
the app already loaded elsewhere (no fetch of its own, confirmed by the component's own doc
comment). Conversation rows carry a deliberately truncated `searchText` (a documented fix for a
real ranking bug — full-prompt text let one long conversation match nearly every query). Every row
is `<Icon> <span>{label}</span>` and nothing else: one icon, one line of text, no secondary line, no
trailing content, no keyboard-shortcut hint, no timestamp, no match highlighting.

Current CSS (`index.css:324-372`): overlay uses `var(--scrim)` ✓, input is borderless with a single
bottom rule, list caps at `min(60vh, 420px)` with `overflow-y: auto`, group headings are the
established uppercase/letter-spaced treatment already used elsewhere (`--text-3`, 11px, 600 weight,
0.04em), items get `border-radius: var(--radius-md)` and a flat `var(--surface-2)` background on
`[data-selected="true"]` — no transition on that background swap, no focus/hover distinction from
selection, no border or ring. Empty state (`cmdk-empty`) is a single centered "No matches." line,
`--text-3`, no icon, no suggestion of what to try. `Command.Dialog`'s appearance/disappearance has
no transition at all — cmdk provides `data-state` attributes for exactly this and nothing in the
CSS reads them.

## What's missing, concretely

1. **No keyboard-hint footer.** Nothing in the palette tells a first-time user that arrow keys
   navigate, Enter selects, or Esc closes — the whole point of a keyboard-first surface undersold
   at the one moment a new user is looking right at it.
2. **No open/close transition.** Every other overlay-style surface in the app (menus, drawers per
   `_system/foundations.html`'s elevation work) uses `--dur-fast`/`--dur-base` with the shared
   expo-out easing; this dialog snaps in the instant `open` flips true, no scale/fade, and the
   scrim has no fade either.
3. **No match highlighting.** cmdk filters and ranks internally but nothing marks *why* a row
   matched. Typing "spec" gives four results with no visual indication of which substring
   qualified each one — a user re-reads every row to find the connection themselves.
4. **Selection state has no motion and no secondary cue.** The `--surface-2` background swap
   between rows is instant (no `transition`), and there's nothing beyond background colour — no
   left accent bar, no icon-colour shift — so on a low-contrast monitor the selected row is easy to
   miss entirely, which matters most for exactly the sighted-but-fast-glancing use this surface is
   built for.
5. **Rows carry no secondary information.** A task row shows only its title — no status, no
   assigned agent. A conversation row shows agent + truncated prompt but no recency or lifecycle
   (open/closed) signal, even though that data exists on the `AgentConversation` type already
   passed in. A document row shows only title, no phase/kind. Compare against every other list
   surface in the app (`TaskCard`, `ConversationView`'s history), all of which surface at least one
   secondary attribute.
6. **No visual distinction between groups beyond the heading.** Four different domains — agents,
   tasks, documents, conversations — share one icon-plus-label treatment differentiated only by a
   14px monochrome `--text-3` icon per row. There is no colour coding at all, notably no use of the
   app's own 8-colour agent scale for the Agents group, where it would be free identity information
   rather than decoration.
7. **No indication of the shortcut that opened it, nor any per-item shortcut.** T3 Code's
   equivalent surfaces the resolved keybinding per action (see below) — AgentWeave's palette has no
   assignable actions today (it is pure navigation), so this is lower priority here, but the
   opening shortcut itself (`⌘K`/`Ctrl K`) is not shown anywhere the user would learn it if they
   found the palette by some other means (there isn't one today, but a future "?" hint or empty
   state could teach it).
8. **Empty state is a dead end.** "No matches." offers no next step — no suggestion to check
   spelling, no indication of what's searchable at all if the box is empty before any typing.

## External patterns (WebSearch, 2026-08-22)

Sources: [Mobbin — Command Palette UI Design](https://mobbin.com/glossary/command-palette),
[UX Patterns for Developers — Command Palette](https://uxpatterns.dev/patterns/advanced/command-palette),
[Destiner's notes — Designing a Command Palette](https://destiner.io/blog/post/designing-a-command-palette/),
[techinterview.org — Build a Command Palette: Cmd+K Like Linear and Vercel](https://www.techinterview.org/post/3233475212/build-command-palette-cmd-k/).

- **Hint discoverability**: "nobody is going to use it if they can't find it" — the product should
  hint at the palette's existence in the UI itself (e.g. a `⌘K` badge somewhere visible), separate
  from the mock itself but worth noting for RATIONALE.md.
- **Coverage**: a command palette should include everything reachable through the app's menus and
  context actions — AgentWeave's is scoped to navigation only today (agents/tasks/docs/
  conversations), which is a reasonable, deliberate scope, not a gap to mock around.
- **Search feedback**: fast, accurate filtering with visible feedback on execution — match
  highlighting (below) is the concrete form of this.
- **Recent items**: several sources recommend surfacing recently-used items at the top when the
  query is empty, ahead of full lists. Relevant future-feature note, not a styling fix — flagging
  per the loop's "missing feature" allowance, not implementing.
- **Linear-style density**: small badge for current "mode"/scope, 13px density, near-black tokens —
  AgentWeave's existing 13px input font-size and near-black scale already matches this; nothing to
  change there.

## T3 Code reference (sourcemap, genuine equivalent found)

`index-DiDfaONg.js.map` sourcesContent for `CommandPaletteContent.tsx` and
`CommandPaletteResults.tsx` (T3 Code's own command palette, not adapted from a generic library
example — paraphrased below, no code copied into any tracked file per `IDENTITY.md`/CLAUDE.md's
"reference only" rule):

- **Footer with `Kbd`/`KbdGroup` hint chips**: a persistent footer row below the results list
  showing `↑↓ Navigate`, `Enter <contextual action label>`, optionally `Backspace Back` (for
  drill-in modes), always `Esc Close`. Each hint is a small bordered key-cap element plus a text
  label, grouped with a small gap.
- **Match highlighting**: search hits wrap the matched substring in `<mark>` with a semantic,
  non-chromatic treatment (`font-semibold`, foreground colour, transparent background — i.e. weight
  and colour-strength carry the emphasis, not a highlighter colour). Directly reusable within
  `IDENTITY.md`'s tokens-only rule.
- **Row anatomy is richer than a single line when there's something to show**: icon, then a
  flex column of title (with optional leading/trailing inline content) plus an optional secondary
  line — either a description or, distinctively, a "thread content match" snippet coloured by
  who said it (`You:` / `Agent:` in two different accent colours) with the matched substring
  highlighted inside that snippet too. Directly analogous to AgentWeave's conversation rows, which
  currently show only the truncated opening prompt with no speaker attribution.
- **Trailing content is used, not empty**: a right-aligned timestamp (tabular-nums, muted, fixed
  min-width so columns align), a resolved keyboard-shortcut badge when the action has one, or a
  chevron icon when the row opens a submenu rather than executing directly.
- **Disabled rows are dimmed** (`opacity-64`) and rendered as a plain `div`, not a focusable
  `CommandItem` — visually present (so the user knows the option exists) but explicitly
  non-interactive, rather than simply omitted.
- **Selection styling is intentionally NOT cmdk's default highlight classes** — T3 Code strips
  `data-highlighted`/`data-selected`'s default background/text via Tailwind overrides and applies
  its own single `isActive` treatment (`bg-accent! text-accent-foreground!`) so hover and keyboard
  selection can't fight each other visually. AgentWeave's current CSS only styles
  `[data-selected="true"]` and lets `:hover` fall through to nothing explicit — worth checking in
  P2/P3 that mouse-hover and keyboard-selection read consistently once a hover state is added.

## What's in scope for this mock vs. rejected up front

Per `IDENTITY.md`'s rejection test, checked before building anything:

- Adding a footer hint row, match highlighting via `<mark>`, secondary row lines, trailing
  timestamp/status content, open/close transition using the existing `--dur-*`/easing tokens, and a
  hover state distinct from keyboard-selection — all refinement of the existing language using
  existing tokens. **In scope.**
- Colour-coding the Agents group using the existing 8-colour `--agent-*` scale — the scale already
  exists and is used elsewhere for the same identity; applying it here is consistent use, not a new
  system. **In scope**, but each agent row uses its *own* assigned colour (already computed
  elsewhere in the app for agent identity), not a single new hue for the whole group — a
  single-hue-per-group scheme would fail clause 1 (inventing colour meaning) if it doesn't map to
  data that already carries that meaning.
- A new "recent items" section — a genuine missing **feature**, not a styling gap. Per the loop's
  pre-authorised allowance, this gets mocked and flagged in RATIONALE.md as a feature note, not
  treated as an obligatory part of the styling refinement.
- Any new colour hue, a border/ring/glow that isn't already an established selection pattern
  elsewhere in the app, or restyling cmdk's structure into a different visual language (e.g. a
  full-screen takeover, a sidebar-style palette) — **rejected under clause 5** (no jump in design,
  refinement only) before it's built.

## Next (P2)

Validate the above against `IDENTITY.md` (mostly done inline above already — nothing here reads as
a violation) and build 2-3 variants in `design/mocks/S8-palette/` exploring degree of refinement
(footer hints + highlighting alone, vs. + agent colour + secondary lines, vs. + recent-items
feature note) using realistic content (real-looking agent names, task titles, conversation
snippets, doc titles) — not lorem ipsum — importing `../../../hub/ui/src/index.css`.
