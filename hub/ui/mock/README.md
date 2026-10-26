# The UI mock (ui-finesse)

The mock is the real UI, rendered against recorded data with no Hub. Every component a mock screen
shows lives in `src/` and is the component the app will ship; the mock only feeds it fixtures. So
applying a screen means wiring its existing component to the app's hooks, not redrawing it.

```
npx vite --config vite.mock.config.ts            # http://localhost:5199/mock.html
npx vite build --config vite.mock.config.ts      # static build in dist-mock/ (ignored)
py -3.11 mock/shoot.py ../../testbed/ui-judge/mock/<area> tab/vault settings/manager --light --narrow
npx tsc -p tsconfig.mock.json --noEmit
```

It never touches `hub/hub/static/ui`, the bundle the operator's `:8000` serves.

## Layout

| Path | What |
|---|---|
| `src/components/ui/` | Primitives: `switch`, `segmented`, `menu` (Menu, MenuSelect), `dialog`, `toast`, `dropzone`, `settings` (SettingsPage/Group/Row, Field), plus the existing `button` and `input` |
| `src/lib/format.ts` | Every number, amount, duration, date and schedule on screen |
| `src/styles/primitives.css`, `shell.css`, `<area>.css` | Styles, on index.css's tokens only |
| `src/components/layout/TopBar.tsx`, `Sidebar.tsx` | The shell: the top bar, and the real rail (`Rail.tsx` is gone) |
| `src/components/<area>/…View.tsx` etc. | Each screen's presentational components (props in, callbacks out) |
| `mock/screens/<Screen>.tsx` | Maps fixtures to those props; holds the UI state a real container would hold |
| `mock/fixtures/*.json`, `mock/fixtures.ts` | Real data recorded from the Terra replica's API, typed with `src/api` types |
| `mock/queryClient.ts` | The React Query cache the mock renders under, seeded from fixtures |

**A component that fetches through hooks renders in the mock by seeding its query keys.** The rail is
the app's own `Sidebar`, which reads `useProjects` and `useProjectConversations`; `mock/queryClient.ts`
writes the fixtures into the cache under exactly those keys (`['projects']`,
`['project', id, 'conversations', 'open']`), with nothing stale and nothing refetching, so the mock
shows the component the app ships rather than a presentational copy of it. Add a key there when a
seeded component reads a new one.
| `mock/before/*.webp` | Today's build, for the mock bar's "Compare with today" |

## Rules for a screen

1. **Components are the deliverable.** Put them in `src/components/<area>/`, presentational: typed props
   (prefer `src/api` types so the hooks' data plugs in unchanged), callbacks for actions, no fetching, no
   fixture imports. Their CSS goes in `src/styles/<area>.css`, imported by the component.
2. **Use the primitives.** Switch, Segmented, MenuSelect/Menu, Dialog, `toast()`, DropZone, SettingsRow/Field,
   `Input`/`Textarea` (now with a default size), `Button` (primary/ghost/outline/destructive), `Icon`. No
   native checkbox, select, date, file input or `<details>`. Add a lucide icon by appending an alias to
   `Icon.tsx`'s map.
3. **Every new `<button>` or `role="button"` carries `data-slot="<name>"`.** index.css's baseline rule
   styles every button without a `data-slot`, and outranks a class.
4. **Tokens only** (`var(--…)`), checked in dark and light. No literal colours except white on an accent fill.
5. **Words are the operator's.** No event names, raw ids, cron strings or file instructions on screen; ids
   go in a `title` or a copy action. Numbers and dates only through `format.ts`.
6. **No page title that repeats the active tab.** Reading pages are centred at ~1100px; workspaces (Tasks,
   Spec, Vault) use the full width.
7. **Motion** uses the tokens in `primitives.css` (`--ease-out`, `--dur-pop`, `--dur-overlay`, `--dur-exit`),
   `.aw-delayed` for any loader, and stops under `prefers-reduced-motion`.
8. **States the data lacks** (an empty vault, an open question) may be simulated in the screen file, marked
   `// mock state`. Never edit fixture JSON by hand; add fixtures by dumping a replica route.

## The Thread page (the loom, approved 2026-10-24/25)

The Thread page is drawn by the components in `src/components/thread/loom/` (`Loom`, `ThreadLoom`,
`geometry.ts`) and `src/styles/thread-loom.css`; the app's `ThreadScreen` feeds them from the Hub. The
mock feeds the same components a recording:

```
npx vite --config vite.mock.config.ts     # http://localhost:5199/mock-loom.html?mode=light
```

The bar switches dark / light and replays the draw-in. (The left-to-right / top-to-bottom and wave /
rope switches the operator compared on 2026-10-24 are retired: left to right and the wave were chosen,
and the others were removed from the components.) The fixture, `mock/thread-chapters-fixture.json`, is
this repository's thread with its 17 chapters, recorded with the Hub's own code (`project_thread.build`
plus `chapters.overlay`) from a read-only copy of the operator's database. The operator approved it as
it renders ("it should look exactly like that"). The same screen is `#thread` in the full mock.
`mock/thread-fixture.json` (written by `py -3.11 mock/record_thread.py`) is the trial Hub's structural
feed without chapters, kept for checks of a surface that pages. `py -3.11 mock/shoot.py`-style
screenshots land in `mock/loom-shots/` (PNGs are ignored).

## The Spec page, redesigned (mock, 2026-10-26)

Spec `spec/changes/the-spec-page-redesigned`. The components are in `src/components/spec/page/`
(`SpecWorkspace` for the tab, `SpecSidePanel` for the conversation's panel, both built from
`SpecPageHeader`, `SpecDocumentBody`, `SpecOutline`, `SpecDocList` and `SpecBuilds`). Their view
model and its pure rules (which actions each state offers, filters, build order, list grouping)
are in `model.ts`; `src/styles/spec-page.css` styles them. The document is drawn from its structure
(the payload the recording kept inside the rendered HTML), not a frame.

`mock/specMock.ts` holds what a container would hold. The five document states, Check's findings
and the builds are simulated (`// mock state`): the behaviour behind them is roadmap slices C and D.

```
http://localhost:5199/mock.html#tab/spec?state=building            # writing | ready | approved | building | archived
http://localhost:5199/mock.html#tab/spec?state=approved&layout=switcher
http://localhost:5199/mock.html#tab/spec?state=building&at=FR-9   # a copied link: opens at FR-9
http://localhost:5199/mock.html#conversation/Architect/conv-9cdda4865e0b/spec?state=building
```

The mock bar switches the state and, on the tab, the list between a left column and a top switcher
(the document's open question 2). The panel sits at its narrowest width (360px) below a 1200px window.
