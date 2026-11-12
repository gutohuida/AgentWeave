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

## The traces view (mock, 2026-11-02)

Spec `spec/changes/a-traces-view-with-filters-grouping-and-stats`. The components are
`src/components/traces/TracesPage.tsx` and its pure model `tracesModel.ts` (filters, the error rule,
totals, grouping); `src/styles/traces.css` styles them. The run drawer is the app's own
`TraceDrawer`, now also usable controlled. The fixtures are recorded read-only from the operator's
Hub by `py -3.11 mock/record_traces.py <db> <project>`: every run trace, the newest 200 of each kind
of the Hub's own, and 22 whole run traces (the newest five and every error).

```
http://localhost:5199/mock.html#traces     # Activity → Traces
```

Decided by the operator on 2026-11-02 after driving it: the view is a fourth view inside Activity
(an own tab was the other choice shown, and is retired); the Hub's own traces sit behind a quieter
"Hub internals" menu rather than beside agent runs; a task with no reference or title is "A task
that no longer exists", never its raw id.

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

## The Build dialog (mock, approved 2026-11-03)

Roadmap `building-a-spec-ties-together-from-plan-to-board`, slice `build-dialog-overhaul`. The component
is `src/components/spec/BuildPlanDialog.tsx`, styled by `src/styles/build-plan.css`. It takes the
Hub's `SpecRecommendedBuild` and the document's tasks and answers `BuildChoices`, so applying it
replaces `BuildDialog` in `useSpecPhaseControls` without redrawing. The recommendation over the
recorded document's five tasks is simulated (`// mock state`, `PLAN_RECOMMENDED` in `specMock.ts`):
one task names an agent that is not open (Codex), and two give no reason.
```
http://localhost:5199/mock.html#tab/spec?state=approved     # then Build in the header
```
Decided by the operator on 2026-11-03 after looking at it in dark and light: two sections, "How it
runs" and "Who builds and checks", with a row per task showing its builder, its checker and each
reason; the separate Builders list and Flow agent control are gone (the builders are those the table
names, and the default builder works the flow); the window end is a short list of ends, not a date
input; the Fast level hides the checker column. Agents carry their colour and their model; reasons
are plain muted text, not italic. The dialog is 760px, the widest in the app, for the table.

## The Checkpoints tab (mock, 2026-11-04)

Spec `spec/changes/every-checkpoint-findable-and-readable`. The components are
`src/components/checkpoints/CheckpointsPage.tsx` (rows, filters, the opened checkpoint) and its pure
wording in `checkpointModel.ts`; `src/styles/checkpoints.css` styles them. `CheckpointsScreen.tsx` is
the container the app uses. The mock feeds the page hand-written fixtures (`// mock state`) that cover
each trigger and status, a title the Hub made from the body and one from its facts, a probe that found
files missing, a carried-over pair and a checkpoint covering no run.

```
http://localhost:5199/mock.html#tab/checkpoints
```

## A trace of a whole conversation (mock, approved 2026-11-06)

Spec `spec/changes/a-trace-of-a-whole-conversation`. The components are
`src/components/traces/ConversationTrace.tsx` and its pure model `conversationTraceModel.ts` (turn
numbering, the range and start-time narrowing, the shared axis with gaps over 20 minutes folded,
an unfolded turn's spans on its own scale, totals); `src/styles/conversation-trace.css` styles them.
The conversation bar gains `onOpenConversationTrace` ("Trace of this conversation"). The fixtures are
three of this repository's conversations, recorded read-only from the operator's Hub by
`py -3.11 mock/record_conversation_trace.py <db> <conv-id> ...` (ignored, like every fixture).

```
http://localhost:5199/mock.html#conversation-trace/conv-c6c83418230a   # 24 turns, carried over from conv-18c9f0a31db7
http://localhost:5199/mock.html#conversation-trace/conv-b7158addff32   # QA, 17 turns over two days
```

Approved by the operator on 2026-11-06 as it renders ("Perfect. Loved it."), including the author's choices: gaps over
20 minutes fold, an unfolded turn's spans draw on its own scale, overlapping axis labels move to hover text.

## The side panel's Running tab (mock, 2026-11-12)

Roadmap `spec/changes/a-side-panel-worth-keeping-open-activity-changes-files-terminal-and-peers`,
slice `activity-tab`. It replaces the panel's Loops tab, and is named Running because the project
already has an Activity tab. The component is `src/components/panel/RunningTab.tsx`, with its pure
rules (which group a build, loop or job falls in, what it says it is doing, the filters) in
`runningModel.ts`; `src/styles/running-panel.css` styles it. It is drawn in the app's own
`PanelShell`. Every state is hand-written in `mock/runningMock.ts` (`// mock state`), apart from the
replica's two finished builds.

```
http://localhost:5199/mock.html#conversation/Architect/conv-9cdda4865e0b/running
```
