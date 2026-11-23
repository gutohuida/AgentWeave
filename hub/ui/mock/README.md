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
8. **Fixtures are local.** `mock/fixtures/*.json` is recorded from your own project and gitignored. On a
   fresh checkout `mock/ensureFixtures.mjs` (run by the mock vite config and `npm run typecheck:mock`)
   copies the minimal tracked stubs from `mock/fixtures-stub/` for any file that is missing; recorded
   files are never overwritten. Raw `tsc -p tsconfig.mock.json` needs that to have run once.
9. **States the data lacks** (an empty vault, an open question) may be simulated in the screen file, marked
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

Approved by the operator on 2026-11-12 as it renders.

The roadmap's other tabs are mocked in the same shell (`mock/screens/SidePanel.tsx`, fed by the
hand-written Terra checkout in `mock/panelMock.ts`): Changes (`ChangesTab`: the agent's last turn or
its whole branch, as diffs), Files (`FilesTab`: the agent's worktree or the project root, its changes
marked, "Changed only"), Terminal (`TerminalTab`: up to four shells as tabs, + for where and which
detected shell, WSL included, an ended shell with its exit code, Send to the agent; the app mounts the
real terminal emulator where the mock shows a recording; `terminal-full` is at the limit of four,
`terminal-remote` the state from another computer, `terminal-docker` Docker mode; spec
`a-terminal-in-the-side-panel`, 2026-11-14) and Watch (`WatchTab`:
a peer's conversation through the app's own `AgentTimeline`, read-only). The panel store's ids for
the new tabs are cast in the mock (`// mock state`) until the slices add them.

```
http://localhost:5199/mock.html#conversation/Architect/conv-9cdda4865e0b/changes
http://localhost:5199/mock.html#conversation/Architect/conv-9cdda4865e0b/files
http://localhost:5199/mock.html#conversation/Architect/conv-9cdda4865e0b/terminal
http://localhost:5199/mock.html#conversation/Architect/conv-9cdda4865e0b/terminal-full
http://localhost:5199/mock.html#conversation/Architect/conv-9cdda4865e0b/terminal-remote
http://localhost:5199/mock.html#conversation/Architect/conv-9cdda4865e0b/terminal-docker
http://localhost:5199/mock.html#conversation/Architect/conv-9cdda4865e0b/watch
```

## Dashboards: change by asking (mock, 2026-11-14)

Spec `spec/changes/change-a-dashboard-by-asking`. `DashboardsView` gains three optional props the
app wires once the slice's routes exist: the edited-by line (`edited_by`, `edited_at`), Undo (shown
only when `can_undo`; restoring is itself an edit, so Undo again puts the edit back) and Ask to
change (pick an agent; the app opens its new conversation with `askToChangeLine` in the composer
through `lib/composerDrafts`, unsent; the mock shows that line in a toast). "Where the spend goes"
was edited by Developer, who added "Runs per day"; "Review queue" was never edited.

```
http://localhost:5199/mock.html#tab/dashboards
```

The answers it shows (Ask to change, one-step undo, stale edits refused) were approved by the operator on 2026-11-14; the render itself awaits their look.

## Dashboards in motion (mock, 2026-11-14)

Same route. Drawn without a charting library still (`PanelChart.tsx`), the motion is CSS in
`src/styles/dashboards.css` on the app's `--ease`/`--dur-*` tokens: panels arrive staggered; bars
grow, lines trace themselves, dots pop and the number counts up (drawn over the real figure, which
the element always holds, so tests and drives never read a mid-count value); Refresh dims the
figures and then slides bars, lines and dots to the new values; an edit's removed panel fades out
where it was and an added one glows once (`usePanelPresence`); hovering a mark dims the rest and
shows the app-styled tooltip; a skeleton stands in while the queries first run. All of it stops
under `prefers-reduced-motion`. In the mock, opening takes 0.9 s, Refresh returns varied numbers,
and Undo on "Where the spend goes" removes and re-adds "Runs per day".

## The build view (mock, 2026-11-17)

Spec `spec/changes/a-build-view-showing-every-task-and-run-of-a-build`. The components are
`src/components/builds/BuildView.tsx` (the full view) and `BuildSummary.tsx` (the compact summary,
`panel` in the Running tab's build row, `strip` on the spec page's build card), with every count,
word and order in the pure `buildViewModel.ts`, whose `*Read` types are the read route's contract;
`src/styles/builds.css` styles them. Runs open the app's own `TraceDrawerPanel`, which gained a
head line (the run, and its conversation link) and a focus-return ref. The cost cell is
`lib/format`'s `formatCost`/`CostCell`, now shared with Traces (its own `money()` is gone). The
fixtures are six of this repository's builds, recorded read-only from the operator's Hub by
`py -3.11 mock/record_builds.py <db> <project>` (`builds.json`, and `builds_traces.json` for the
drawer); the states they lack are `?state=` in `mock/buildsMock.ts` (`// mock state`).

```
http://localhost:5199/mock.html#build/build-04e780a89c1c?task=LFBTO-2                # sent back, rebuilt
http://localhost:5199/mock.html#build/build-04e780a89c1c?task=LFBTO-2&run=run-8473bd53a398   # a trace open
http://localhost:5199/mock.html#build/build-e36c054f9e59?state=live&task=PNSOS-3     # running, a stalled task
http://localhost:5199/mock.html#build/build-76f63278bad5?state=unpriced&task=LTTFA-2  # live | unpriced | all-unpriced | empty | loading | error | stale
http://localhost:5199/mock.html#build-summaries                                      # both summaries, real containers
http://localhost:5199/mock.html#conversation/Architect/conv-9cdda4865e0b/running     # the summary in the panel
```

Awaiting the operator's look.

## A profile's pool of runners and models (mock, 2026-11-19)

Spec `spec/changes/a-profile-runs-each-task-on-a-runner-and-model-chosen-from-its-pool`. The components
are `src/components/agents/pool/` (`PoolEditor` for the agent's Running page, which takes the single
Model choice's place through `AgentRunningSettings`' `pool` prop; `PoolPicker` for the composer, which
replaces the model picker and the Effort pill; the pure rules in `poolModel.ts`) and the Build dialog's
per-task model under each agent (`BuildPlanDialog`'s optional `pools`); `src/styles/profile-pool.css`
styles them. The types the agents API is to return are in `src/api/agentPool.ts`; the Build payload
and recommendation gain `task_builder_entries`/`task_checker_entries`. Every pool, runner and the
catalog are hand-written in `mock/poolMock.ts` (`// mock state`): no Hub records a pool yet.

```
http://localhost:5199/mock.html#agent-settings/Builder/running              # five entries, Sonnet the default
http://localhost:5199/mock.html#agent-settings/Builder/running?pool=empty   # empty | one | refused
http://localhost:5199/mock.html#profile-pools/build                         # the slice's own seven tasks
http://localhost:5199/mock.html#profile-pools/chat                          # new chat, started chat, one model
```

Approved by the operator on 2026-11-19 as it renders, including the author's choices: a started chat lists another coding agent's entries greyed out (a new chat is needed for them), an agent's menu detail is its default plus a count, and efforts use the catalog's labels.

## The sidebar's threads and builds (profiles-threads-and-builds-everywhere)

`src/components/layout/ThreadsAndBuilds.tsx` (rules in `threadsAndBuildsModel.ts`, tested in
`src/__tests__/threadsAndBuildsModel.test.ts`) replaces the agent tree and the recency view under
each project. The mock passes it to the real `Sidebar` through `projectBody`, and the collapsed
rail's marks through `buildsNeedingYou`; the app passes neither yet, so the app is unchanged. The
data is mock state (`mock/sidebarMock.tsx`): neither `operator_threads` nor `needs_operator` exists
on a route yet. Review it at `#tab/jobs?sidebar=<state>` (mixed, quiet, empty, many40, many300,
loading, error, today); the Jobs screen renders on the stub fixtures, Overview does not.

Decided with the operator, 2026-11-20, against the vault UI note (src-0b85ea5a1d1d):
- Two sections, Builds then Threads. No Profiles section; no "All builds" link (the side panel's
  Running tab already lists every build). Finished builds needing nothing are not listed.
- Rows are one line. A build: hammer (running) or hand (needs you), title, one word ("3/9",
  "Stopped", "Stalled", "Question", "Given up"); the reason is in the tooltip. A thread: profile
  colour edge, title, profile name, and a shape for running (dot in a ring) or waiting (hand); its
  age is in the tooltip, the list already being in recency order.
- Needs-you rises: such builds above running ones, waiting threads above the rest.
- Section headers are disclosures with a count and remember being collapsed; Builds also says
  "N need you". Past 15 threads a filter appears; "Show N more" and "Show archived" stay.
- Loading is a delayed skeleton; an error says so with "Try again", never an empty list.
- Rows hold their places while the pointer is over the list.
- Collapsed, the rail shows projects only, with an amber hand when a build needs the operator.
- Amber is never text colour: light-theme amber is 3.35:1 on the rail. Measured text: 5.86 to
  17.44 (dark), 6.01 to 16.12 (light).

Names a drive can rely on: sections "Builds" and "Threads" (disclosure buttons of the same names);
"Build: <title>, <n> of <m> tasks done, running" or "..., <stopped|stalled|question|given up>,
needs you"; "Dismiss build: <title>"; "New thread"; "Filter threads"; test ids
`rail-threads-builds-<project>`, `rail-build-<id>`, `rail-thread-<conversation>`,
`rail-compact-needs-<project>`. Arrow keys, Home and End move between rows; Enter opens; after a
dismiss, focus goes to the Builds header. Executable checks: `testbed/ui-judge/mock/sidebar/
check_sidebar.py` (names, keyboard walk, dismiss focus, contrast in both themes, greyscale).

Heuristic pass (Nielsen's ten):
1. Visibility of status: builds show progress or the need in words; threads show working/waiting.
2. Match with the real world: profile, thread, build; no ids or enum values on screen.
3. Control and freedom: dismiss is undoable in effect (a new need brings the build back); filters
   clear with Escape or "Clear the filter".
4. Consistency: the rows reuse ConversationRow and the rail's tokens and disclosure chevrons.
5. Error prevention: a running build offers no dismiss.
6. Recognition over recall: each thread names its profile; the tooltip gives build reasons.
7. Flexibility: keyboard movement, filter past 15, collapsible sections.
8. Minimal design: one status per row; age and reasons move to tooltips.
9. Recovering from errors: a failed list says so with Try again.
10. Help: the dismiss tooltip says the build comes back if it needs you again.
Not checkable by an agent: whether it feels calm at a glance, left to the operator's review.

## The Vault page that says what it holds (mock, 2026-11-23)

Spec `spec/changes/a-vault-page-that-says-what-it-holds`, slice `vault-that-explains-itself` of the
project UI cleanup roadmap. The components are `src/components/vault/VaultOverview.tsx` (the
Overview, the Facts list and the search results) with their pure rules in `vaultOverviewModel.ts`;
`VaultLibrary` shows them only when its container passes `uses`, so the app is unchanged until it
is wired. The proposed route contracts are the `VaultFactUse` and `VaultTextHit` types in
`src/api/vault.ts`. The fixtures are this repository's own vault, recorded read-only by
`py -3.11 mock/record_vault.py <db> <project> <repo root>` (map with read counts and readers, the
facts specs cite or contradict, each source's text, each fact's citations); the search inside
documents is worked out in the screen from the recorded texts.

```
http://localhost:5199/mock.html#tab/vault                       # Overview on the real vault
http://localhost:5199/mock.html#tab/vault?state=no-uses         # uses-loading | uses-error | search-slow | search-error | no-uses
http://localhost:5199/mock.html#tab/vault?data=replica          # the replica's small vault, as before
```

Awaiting the operator's look.
