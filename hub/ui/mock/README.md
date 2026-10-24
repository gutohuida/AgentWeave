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

## The Thread page (pull-the-thread, task `mock`)

Its components live in `src/components/thread/` (`Thread`, `Knot`, `Fold`, `Scrubber`), its styles in
`src/styles/thread.css`, its API shapes in `src/api/thread.ts`. The fixture is the trial Hub's feed for
this repository's project, recorded with the Hub's own code over a copy of its database:

```
py -3.11 mock/record_thread.py            # writes mock/thread-fixture.json (tracked, ~230 KB)
npx vite --config vite.mock.config.ts     # http://localhost:5199/mock-thread.html?mode=light
py -3.11 mock/drive_thread.py mock/thread-shots   # checks + screenshots (the last run is committed in mock/thread-shots/)
```

`mock-thread.html` renders the page on its own, so it needs none of the replica fixtures; the same
screen is also `#thread` in the full mock. Its checks mirror the task's criteria (present, recursive,
face, access) and write the light/dark/drawing/unspooling/greyscale screenshots for the operator.

## The Thread page as a loom (mock, 2026-10-24)

The operator's feedback on the Thread page: try left to right, show more about the selected knot
underneath, make the line less like a git graph and more like a thread, and add motion. The mock
answers with real components in `src/components/thread/loom/` (`Loom`, `ThreadLoom`, `geometry.ts`)
and `src/styles/thread-loom.css`. It is a proposal, not wired into the app.

```
npx vite --config vite.mock.config.ts     # http://localhost:5199/mock-loom.html
```

Switches on the mock bar: left to right / top to bottom, a single wave / a rope with the red thread
twisted through it, dark / light, and replay the draw-in. The fixture, `mock/thread-chapters-fixture.json`,
is this repository's thread with its 17 chapters, recorded with the Hub's own code (`project_thread.build`
plus `chapters.overlay`) from a read-only copy of the operator's database. Screenshots: `mock/loom-shots/`.
