# Design

## Visual authority

`openspec/changes/2026-07-30-hub-native-experience/mock-full.html` remains the authority for
palette, density, radii, and the conversation surface. Two areas are not covered by it and are
specified here from T3's interaction model: the contextual rail, and the settings-row layout.

`mock-contextual-nav.html` in this change directory renders those two areas plus the corrected
conversation chrome, using the same token block as the full mock. It is a reference for the new
material only; where the two disagree on anything the full mock already covers, the full mock wins.

## What was read from T3 rather than guessed

T3 Code ships its renderer stylesheet at
`resources/app.asar.unpacked/apps/server/dist/client/assets/index-6Ivh-FEr.css`. The relevant
declarations, extracted directly:

```css
/* light */          --sidebar-row-hover: var(--color-zinc-25);
                     --sidebar-row-active: var(--color-white);
                     --sidebar-row-selected: var(--color-white);
/* dark */           --sidebar-row-hover:    color-mix(in srgb, var(--foreground)  8%, transparent);
                     --sidebar-row-active:   color-mix(in srgb, var(--foreground) 11%, transparent);
                     --sidebar-row-selected: color-mix(in srgb, var(--foreground)  7%, transparent);

.hover\:bg-sidebar-row-hover:hover                          { background-color: var(--sidebar-row-hover) }
.active\:bg-sidebar-row-active:active                       { background-color: var(--sidebar-row-active) }
.data-\[active\=true\]\:bg-sidebar-row-selected[data-active=true]
                                                            { background-color: var(--sidebar-row-selected) }
.group-hover\/project-header\:bg-sidebar-row-hover:is(:where(.group\/project-header):hover *)
                                                            { background-color: var(--sidebar-row-hover) }
[&_[data-slot=input]::-webkit-inner-spin-button]:appearance-none
                                                            { appearance: none }
--default-transition-duration: .15s;
--default-transition-timing-function: cubic-bezier(.4, 0, .2, 1);
```

Four things follow, and they are the substance of this change:

1. **Three row states, not one.** Hover, press, and selected are separate fills. A row that only
   changes on hover reads as half-built; a row that uses the same fill for hover and selected loses
   the distinction between "the pointer is here" and "this is where you are".
2. **Fill only.** No row gains a border on hover. AgentWeave already reserves a transparent border
   at rest (`index.css:235`), so it *can* colour a border without reflow — the mock does this for
   `.navitem` and `.tab` — but list rows use fill alone, which is why they feel lighter in T3.
3. **Group hover reveals row actions.** A row's secondary controls are present in layout and
   revealed when the row is hovered. This is how the project gear can exist without the rail
   becoming a bank of icons.
4. **Number spinners are removed deliberately**, not left to the browser.

AgentWeave's own tokens already match the timing (`--dur-fast: 150ms`), so only the row-state fills
are new.

## The contextual rail

The rail has two modes, and one destination model behind them.

```
project mode                         section mode (environment)
┌──────────────────────┐             ┌──────────────────────┐
│ AW  AgentWeave       │             │ ←  Environment       │   back → project mode
│ PROJECTS        [⌸]  │             │ AgentWeave           │   which project this configures
│ ▾ AgentWeave  ⚙ ●    │  ← gear     │ ─────────────────    │
│    ● claude          │             │ Quality              │
│    ● codex           │             │ Instructions         │
│    ● opencode        │             │ Runners              │   ← selected row
│    + Add agent       │             │ Charters             │
│ ▸ IFiance            │             │ Worktrees            │
│ ▸ GalaxySpec         │             │ Diagnostics          │
│                      │             │ Budgets              │
│ + Add project        │             │ Settings             │
└──────────────────────┘             └──────────────────────┘
```

**Why the rail and not the content area.** The eight environment sections are navigation, and the
product now has exactly one place navigation lives. Keeping a second nav column inside the content
area was what produced both the "two places to go to configs" complaint and the empty-looking
screens — the column ate horizontal space that the content then declined to use.

**Why a gear on the project row rather than a rail entry.** A permanent `Environment` entry in the
rail would sit beside projects and agents as if it were a peer entity, which it is not. A gear
attached to the project it configures states the scope in its position. It is revealed on
group-hover of the project row and is persistently visible for the active project, so it is
discoverable without being noise on every row.

**Reconciliation.** The in-flight `2026-07-30-hub-native-experience` delta for `hub-visual-language`
states that project-scoped views "SHALL be reached within the content area rather than by adding
entries to the navigation region", and that adding a view "MUST NOT require adding a navigation
entry". That direction was about *work* views — tasks, spec, jobs, activity — which remain project
tabs and are untouched. Configuration is a different class: it is not a view of the project's work
but of the project's setup, and it is entered, not switched to. Section mode adds no permanent
entry — the rail's project mode is unchanged, and a new environment section still adds nothing to
it. `hub-workspace-shell` records this explicitly so the two documents do not drift.

**Alternatives rejected.** A permanent rail `Settings` entry (the mock's hidden `.foot` item) was
rejected: it reintroduces a fixed nav destination and cannot express which project it configures. A
modal settings dialog was rejected: eight sections with live data are not modal work, and it would
break the existing deep links.

## Navigation state

The destination model in `hub/ui/src/lib/navigation.ts` is unchanged. `environmentDestination` and
`?tab=environment&section=…` keep working, so existing links resolve. What changes is only which
region renders the section list, and that `environment` is no longer offered in `PROJECT_TABS`.

Rail mode is *derived* from the destination, never stored: a destination whose tab is `environment`
puts the rail in section mode. This matters because the operator can arrive by deep link, by back
button, or by the gear, and all three must produce the same rail. Storing a mode flag would let the
rail disagree with the URL.

The back control returns to that project's overview — the same single-action guarantee the
conversation's back-to-project control already carries.

## The conversation surface

The current implementation and the mock differ structurally, not cosmetically. Today the screen is
three stacked boxes: a filled header closed by a rule, a stream, and a filled footer closed by a
rule that contains the controls, banners, continuity line, and composer. The mock has no boxes.

| | current | mock |
|---|---|---|
| header | `--surface-2` fill + `border-b` | no fill, no border; `color-mix(bg 88%)` + `blur(12px)` |
| back control | literal `←` text | icon control |
| turn actions | inside a dropdown in the footer | `Fold all turns` / `Stop turn` in the header |
| stream width | `max-w-[760px]`, gap 18px | `max-w-[960px]`, 30px gutters, gap 21px |
| composer region | `--surface-2` strip + `border-t` | gradient fade to `--bg`, no border |
| composer | inherits the strip | own lifted surface, `--radius-content`, deep shadow, focus-within ring |
| work disclosure | transparent, no hover | `--surface` fill, summary hover |

Moving `Fold all turns` and `Stop turn` into the header is not decoration: the header is where the
turn's state is already reported (`turn 4 running`), so the controls that act on that turn belong
beside it. `Only high-frequency controls remain visible` in `agent-conversation-workspace` is
satisfied — these two are the high-frequency ones, and conversation switching, handoff, and agent
details stay in the overflow menu.

The banner stack and the continuity line keep their specified positions above the composer; they
move out of a bordered strip and onto the fade, so the composer reads as the only lifted thing.

## Settings-row layout

Each environment section becomes a bounded single column of rows:

```
Section title
One line saying what this section governs.
──────────────────────────────────────────────────────────
Hop budget                                    [    6     ]
How many agent-to-agent hops a chain may take
before it pauses for you.
──────────────────────────────────────────────────────────
Allow agent jobs                                    ( ●  )
Agents may create and run scheduled jobs.
──────────────────────────────────────────────────────────
```

Label and explanatory text on the left, control right-aligned, hairline between rows, no card
around each row. Two properties matter: the column is bounded to a readable width but the *section*
fills the content region, so there is no dead zone beside a narrow panel; and a section with three
settings still looks deliberate because the heading, the description, and the separators give it
structure. That is the answer to "the environment screen looks too empty" — the emptiness was
missing structure, not missing content.

Numeric fields suppress `::-webkit-inner-spin-button`, `::-webkit-outer-spin-button`, and Firefox's
`appearance: textfield`. Range constraints stay on the input for validation; only the visible
steppers go.

## Interaction feedback as a capability

This is specified as its own capability rather than as scattered requirements because the defect is
systemic: one primitive exists, nothing uses it, and every screen hand-rolls inline-styled buttons.
Fixing it per-component would leave the next component to make the same mistake.

The implementation rule is that an activatable element uses `components/ui/button.tsx` for controls
and a row treatment driven by `--row-hover` / `--row-active` / `--row-selected` for list rows. New
tokens are added to `index.css` for both themes alongside the existing `--accent`.

Verification uses the existing source-contract pattern from `hubVisualLanguage.test.ts`
(`readFileSync` over component sources, because Vite empties CSS imports under Vitest) plus rendered
assertions on `data-active` / hover class presence for the rail, tabs, and section list.

`prefers-reduced-motion` already collapses transition durations globally at `index.css:301`; the
state fills remain, only their animation stops. Feedback must never be motion-only.
