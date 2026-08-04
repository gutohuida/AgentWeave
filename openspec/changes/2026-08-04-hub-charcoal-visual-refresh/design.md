# Design

## The token ramp

The current dark ramp is blue-navy: `#10131b`, `#171b2a`, `#1b2030`, `#242a3c` sit around hue 225°
at 15–25% saturation. The replacement is a near-neutral graphite ramp — roughly hue 240° at 3–5%
saturation, low enough to read as black but not so low that large fills look dead. Pure `#000000`
is deliberately avoided: it smears on OLED, and it removes the headroom needed to express three
distinct elevations below the ground plane's own contrast with text.

```
                        DARK                      LIGHT
  --bg                  #0a0a0b                   #fafafa
  --rail                #101012                   #f4f4f5
  --top                 #0d0d0f                   #ffffff
  --surface             #151518                   #ffffff
  --surface-2           #1d1d21                   #f4f4f5
  --surface-3           #26262b                   #e9e9ec
```

Borders, text ramps, row-state fills, and `--lift-hi`/`--press-lo` keep their current *formulas*.
They are expressed as alpha over the ground plane or as `color-mix` against `--text`, so they
re-derive correctly against the new ramp without being re-authored. This is the reason the recolour
is mostly a ramp swap: the previous change already moved interaction states onto derived tokens.

### Emphasis: monochrome primary, one accent for state

`--primary` currently carries periwinkle `#7c8cff` and is used as a button fill. On a neutral ground
a chromatic button fill is the loudest thing on screen, which is wrong for a control that appears on
every dialog. Primary becomes monochrome:

```
  --primary             #fafafa (dark)  /  #18181b (light)
  --primary-foreground  #0a0a0b (dark)  /  #fafafa (light)
```

The accent hue is retained but demoted to state only:

```
  --ring                #7c8cff (dark)  /  #5063d8 (light)   focus ring
  --rail-marker         var(--ring)                          rail active bar
```

Rule: **the accent never fills a control.** It appears as a ring, a marker, or a selection edge.
This keeps a single chromatic voice in the chrome and leaves the eight agent identity colours as the
only hues carrying data.

### Alternatives rejected

- **Pure `#000`/greyscale (0% saturation).** Rejected: large flat fills read dead, and OLED smear on
  scroll is a real artifact on the displays this app targets.
- **Warm charcoal (hue ~30°).** Rejected by operator selection; it also pushes the amber status
  colour toward the ground plane, weakening the one colour that signals a paused budget.
- **Keeping periwinkle as the button fill.** Rejected: on a neutral ground it becomes the visual
  centre of every dialog, competing with agent identity colour.

### De-tokenised colour

25 raw hex literals and 85 `rgba()` literals live in components, concentrated in `Badge.tsx`, which
hardcodes a full status palette (`#a1a1aa`, `#3b82f6`, `#f59e0b`, `#22c55e`, `#ef4444`, …). These
bypass the token system entirely and would survive the recolour unchanged, leaving the old palette
embedded in every status chip. They are moved onto semantic tokens as part of this change. This is
scoped work, not an open-ended audit: the two greps in the proposal bound it exactly.

## The composer becomes a column

```
  NOW                                    TARGET
  ┌────────────────────────────────┐     ┌────────────────────────────────┐
  │ [codex-alpha ▾] │ text    │ ▶  │     │ Message codex-alpha…           │
  └────────────────────────────────┘     │                                │
     111px          110px                ├────────────────────────────────┤
     ↑ text starts 132px in              │ [codex-alpha ▾]            ▶   │
                                         └────────────────────────────────┘
```

The composer surface becomes `flex-col`. Row one is the textarea at full width. Row two is a control
row: leading slot for target/agent controls, trailing slot for send. The row is built as **two named
slots, not a fixed arrangement**, because the model and effort controls from
`2026-08-04-hub-model-control-and-provisioning` land in the leading slot and must not require
re-laying-out the composer when they arrive.

Autogrow, `COMPOSER_MAX_HEIGHT_PX`, draft persistence, and the trigger menu are unaffected — the
trigger menu already positions against the textarea's own containing block, which survives the
change from row to column.

## The rail's active project

`data-active` currently means "paint `--row-selected`". It becomes "mark, do not fill":

```
  ▌ Two Codex Test          ← 2px leading bar in --rail-marker, label at --text, weight 550
    Other Project           ← label at --text-2, no bar
    Hovered Project         ← --row-hover fill, no bar
```

The bar occupies layout at rest for every row (transparent when inactive), so gaining it displaces
nothing — the same principle the `Button` primitive uses for its transparent border.

`aria-current` is unchanged: the accessible active state was already correct and is not what the
operator objected to. Only the visual expression changes. This matters because
`projectRail.test.tsx` asserts against `data-active`/`aria-current`, and those assertions must keep
passing.

## Project header

Fill and bottom rule are removed; the header sits on the ground plane like the conversation header
already does. The directory becomes segments rather than one string:

```
  NOW    3 agents · C:\Users\huida\Documents\projects\AgentWeave\testbed\two-codex-agents\workspace
  TARGET Two Codex Test
         3 agents · C:\ › … › testbed › two-codex-agents › workspace
```

Middle elision, not trailing: the tail of a path is the identifying part, and CSS `truncate` cuts
exactly the part worth keeping. The full path remains available as the element's `title`, and the
existing `path_display` field already supplies the string — no API change.

## Work in execution order

The defect is a partition:

```
  entries:  text_a  tool_1  text_b  tool_2  result

  NOW                          TARGET
  ┌ Work · 2 steps ┐           text_a
  │  tool_1        │           ┌ Work · 1 step ┐
  │  tool_2        │           │  tool_1       │
  └────────────────┘           └───────────────┘
  text_a                       text_b
  text_b                       ┌ Work · 1 step ┐
  result                       │  tool_2       │
                               └───────────────┘
                               result
```

`TurnBody` stops partitioning and instead reduces the turn's entries into an ordered list of blocks,
opening a new work block on the first work entry after a non-work entry and extending it while
consecutive work continues. Rendering then walks blocks in order.

Two existing behaviours are preserved inside each group and must not regress:

- a `tool_result` is rendered inline with the `tool_use` it pairs with, never as its own row
  (`findPairedResult`), so pairing is computed **within a group**, not across the whole turn;
- the disclosure's open/closed state is keyed per block, so a turn with several work groups tracks
  them independently rather than toggling as one.

Duration (`workDuration`) becomes per-group — first to last entry of that group — which is more
truthful than the current turn-wide span.

## Verification approach

Colour, alignment, and ordering are all things automated tests describe poorly and screenshots
describe well. The split:

- **Source contracts** (`hubVisualLanguage.test.ts` pattern) assert what must be *structurally*
  true: no `data-theme` write survives, no component reintroduces a raw hex, the composer renders a
  column with a control row, tokens are defined in both modes.
- **Unit tests** assert ordering: a turn with interleaved work and text produces blocks in
  execution order, pairing stays within a group, and per-group disclosure state is independent.
- **Live browser** covers what only rendering shows: the ramp in both modes, the composer's leading
  edge, the rail marker at rest versus hover, and the header without its rule.

Reduced-motion verification remains unavailable through the current browser-automation tooling
(`preview_set_appearance` emulates `prefers-color-scheme` only), carried forward unresolved from
`2026-08-04-hub-contextual-navigation` task 7.7.
