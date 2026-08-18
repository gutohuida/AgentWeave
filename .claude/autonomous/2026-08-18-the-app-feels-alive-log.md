# Autonomous session — the app feels alive and unblocked

**Branch:** `autonomous/2026-08-18-the-app-feels-alive`
**Parent:** `master` @ `1e0d08e`
**Started:** 2026-08-17T23:25+01:00 · **Stop at:** 2026-08-18T08:00+01:00
**Brief:** `.claude/autonomous/STATE.json` — 12 queue items, prepared by `/autonomous-prep` with the
operator awake, before they went to sleep.

Newest entry at the **bottom**. Written for someone who was asleep.

---

## The limits this run is operating under

Recorded here as well as in `STATE.json`, so a session that inherits only this file still has them.

1. **Stay on this branch.** No commits, merges or rebases onto `master`. Merging is the operator's
   call, made awake — and it will likely be a cherry-pick, because an unattended run produces
   scratch alongside the work.
2. **Nothing outward-facing.** No publish, no release, no tag, no PR, no force-push. Pushing *this*
   branch is required, not optional — it is what makes the work durable.
3. **Nothing destructive.** In particular: do not modify `~/.agentweave/hub/data/agentweave.db`
   (the port-8000 database — it holds `proj-8f100b95 AgentWeaveWebsite`, real operator work on
   another project), and do not touch `proj-ff695d96` (`aw-loop10`). Back up any database before
   changing it.
4. **Never mark work complete because a plan exists.** Only verified implementation closes an item.
5. **Every claim is measured or labelled unverified.**
6. **Decisions that are genuinely the operator's get written down, not guessed.**
7. **Always `py -3.11`**, never bare `python` — PATH `python` is the hermes-agent venv and has no
   `agentweave`.
8. **Live agent turns:** permitted, cheap model, a few short turns only. The operator's stated
   ceiling.

## What the night is for

The operator's own framing: *make the app feel alive and unblocked*. Their items 1–6 — the working
indicator, Open project, the stray CMD window, the end-of-turn message, reopening a spec, and the
taskbar icon — are the objective. Depth over breadth: **six fixes shipped and verified beats ten
touched.** Items 7 and 9 are explorations that decide nothing. Items 8 and 10 are runway.

Breadth across all ten was offered during prep and explicitly declined. Do not trade depth for
coverage.

---

## Entry 0 — 2026-08-17T23:25+01:00 · prep handed over, driver being armed

No work done yet. This entry exists so the first firing has something to read.

`/autonomous-prep` ran with the operator awake and fixed intent *before* reading the codebase. It
located all six app fixes in real files and found six stalls that would each have cost an iteration
in the dark. Three of them change the size of the work:

- **Item 4 has a load-bearing twin.** `agent_trigger.py:1563-1568` broadcasts a
  `kind="status"/phase="completed"` line that `AgentOutputPanel.tsx`'s Handoff flow detects
  completion by *scanning for*. Its own comment says removing it breaks that. The fix removes the
  rendered text and keeps the events.
- **Item 5 is not a missing feature.** `ComposerSpecControl.tsx` only wires `onOpenPicker` when a
  document is *already* open — so the picker that reopens an existing spec is unreachable from
  exactly the state the operator is in. Much smaller than it reads.
- **Item 2 is not a missing feature either.** The Open-project backend, modal, native folder dialog
  and mutation all exist. "Open existing project" is a bare 15px icon beside a full-width labelled
  "Add project", and `ProjectRailNav` never receives the callback at all.

And three environment facts, none of which were true in the last handoff:

- Bare `python` is the wrong interpreter and fails collection with 16 `ModuleNotFoundError`s that
  look exactly like a broken tree.
- **No running Hub serves the taste-pass fixtures.** They live in `hub/data/agentweave.db`; port
  8010 serves `profiles/trial/`, which holds only `aw-loop10`. `CLAUDE.md` documents a third
  database, stale since 02:41. That is Q1.
- **The CLI suite hangs forever.** Last session's `pip install pywebview` turned
  `_open_app_window_native`'s ImportError guard into a real `webview.start()` window, and two tests
  patch only the fallback. That is Q1b, and it sits in the very function item 6 has to edit.

**Not established, and the morning should treat both as unknown:** a green baseline for the CLI
suite, and CI on this parent commit (it has never run on `1e0d08e`).

Next: arm the Scheduled Task driver, then take Q1 in this session while the heartbeat is fresh.

---

## Entry 1 — 2026-08-17T23:27+01:00 · Q1 done: the trial Hub now serves the fixtures

**Attempted:** repoint the Hub on port 8010 at the database that actually holds the taste-pass
fixtures, so both the operator's morning and this loop's own verification have realistic data.

**What was actually wrong.** Port 8010 was served by PID 23540 —
`python -m uvicorn hub.main:app --host 127.0.0.1 --port 8010`, with **no `DATABASE_URL` on its
command line**, so it was resolving one from its environment or from `config.py`'s relative default.
Whatever it resolved to, it was `~/.agentweave/hub/profiles/trial/agentweave.db`, which holds only
`proj-ff695d96` (`aw-loop10`). Everything the previous autonomous run seeded — `proj-5e960453`
(AgentWeave), `proj-b44fac0c` (Throwaway (taste pass)), the capability document, both archived
change documents — was sitting in `<repo>/hub/data/agentweave.db`, served by nothing.

**Done:**

1. Backed up **both** databases, timestamped, before touching either — the trial one because it was
   being replaced, and the fixture one because a live Hub was about to start writing to it:
   `profiles/trial/agentweave.db.bak-20260817-232616` and
   `hub/data/agentweave.db.bak-prelive-20260817-232616`, 11038720 bytes each.
2. Confirmed `hub/data/` is gitignored (`.gitignore:88`), so a Hub writing there cannot dirty the
   tree at an iteration boundary.
3. Stopped PID 23540. Confirmed 8010 down **and 8000 still up** — 8000 serves
   `proj-8f100b95 AgentWeaveWebsite`, real operator work on another project, and the limits forbid
   touching it.
4. Restarted 8010 detached via `Win32_Process.Create` with an explicit
   `DATABASE_URL=sqlite+aiosqlite:///.../hub/data/agentweave.db`, started from `hub/` rather than
   the repo root (the root shadows the installed `hub` package and kills the child 60s later with
   its output already sent to DEVNULL). New PID 27792. Detached so it outlives this session — that
   is the one thing that survived the failed 2026-08-15 night.

**Verified, not assumed:**

- `/health` → 200 within 2s.
- `GET /api/v1/projects` → **3 projects**: `proj-b44fac0c`, `proj-5e960453`, `proj-ff695d96`.
- `GET /api/v1/projects/proj-5e960453/project/specs` → both fixtures present:
  `spec/capabilities/quiet-hours/spec.html` phase **`current`**, and
  `spec/changes/quiet-hours-for-agent-notifications/spec.html` phase **`archived`**.

**What a reviewer should distrust / note:**

- The specs response carries `"state": "unindexed"` on both documents and a `home_ambiguous`
  diagnostic listing them both. Not chased — it does not block the taste pass, but it is the kind
  of thing that reads as broken to an operator, and it was **not** caused by this change (the same
  rows were unindexed in the source database).
- Repointing rather than copying was deliberate: a fourth divergent copy is how this ambiguity
  started. The consequence is that the live Hub now writes into `<repo>/hub/data/`, which is
  gitignored but *is* inside the working tree.
- `CLAUDE.md` still documents the `beta` profile as the trial Hub's database. It is now wrong in a
  third way. Left alone deliberately — `CLAUDE.md` is the operator's instrument; recorded as
  decision **N3** rather than rewritten unilaterally.
- Also noted, not acted on: `CLAUDE.md` says `spec/` at the repo root "is tracked", while handoff
  0054 says it is untracked scratch that must not be committed. Both cannot be true. Folded into N3.

**Next:** Q1b — the CLI suite hangs forever on a real pywebview window. Fix before touching CLI code.

---

## Entry 2 — 2026-08-17T23:33+01:00 · Q1b done: the CLI suite terminates again

**Attempted:** make `py -3.11 -m pytest tests/` finish. It had stopped terminating entirely, which
blocked this loop from validating any CLI change — including Q7, which edits the very function at
fault.

**The defect, and what it was not.** `agentweave.cli._open_app_window_native` (cli.py:740-757) does
`import webview` inside the function body and then calls `webview.start()`, which blocks until a
human closes the window. Two call sites reach it: `cmd_hub_start`'s already-running branch
(cli.py:977) and `_hub_native_start`.

None of that is a product bug — the blocking is deliberate, and `test_cli.py:400-422` records
*why* (`pywebview requires the main thread`). The bug was that **the suite's behaviour depended on
whether an optional package happened to be installed on the developer's machine.** While pywebview
was absent, the ImportError guard returned `False` and every caller fell through to
`_open_app_window`; tests that patched only that fallback passed. Handoff 0054 records
`pip install pywebview` being run on 2026-08-17, and from that moment those same tests opened a real
window and never returned.

**Fixed** with a new `tests/conftest.py`: one autouse fixture setting `sys.modules["webview"] = None`
for every test in the directory, which is the documented way to force `import webview` to raise
regardless of what is installed. That pins the suite to the state it was written against and CI
runs in. Tests that need the *installed* path still get it — `TestAppModeNativeWindow` injects its
own fake over the top, and `monkeypatch.setitem` in a test body runs after the fixture and undoes in
reverse, so an explicit fake always wins.

Chosen over patching the two named tests individually: that fixes today's two and leaves the trap
armed for the next test that touches app mode. Chosen over changing the product: the blocking
behaviour is correct.

**Verified — this is a real before/after, not a passing suite asserted over nothing:**

- The two tests that hung forever, run alone: **2 passed in 0.05s**. Before the fix, both were
  bisected to an infinite hang with unbuffered `-v` output, twice, and had to be killed.
- Full CLI suite: **381 passed, 3 skipped in 11.77s.** That number now matches handoff 0054's
  claim exactly — so the handoff was right, and it simply could not be reproduced while pywebview
  was installed. **This is the first verified green CLI baseline of the run.**
- `TestAppModeNativeWindow` — the 6 tests that exercise both the installed and not-installed
  paths — still pass, so the fixture has not masked the path it neutralises.
- `ruff check` clean; `black --check` reports the file unchanged.
- No stray pytest processes left behind.

**What a reviewer should distrust:**

- The fixture is directory-scoped to `tests/`. `hub/tests/` was not touched and was not checked for
  the same hazard; if anything there reaches a windowing call it will still hang. Not investigated.
- Nothing here proves the *desktop app* works — only that the suite no longer waits on one. The
  window itself remains unverified, as it was in handoff 0054.

**Next:** Q2 — remove the end-of-conversation message, keeping the events that Handoff detection
scans for.

---

## Entry 3 — 2026-08-17T23:48+01:00 · Q2 done: no end-of-conversation message for a successful turn

**Attempted:** remove the rendered "Completed" text the operator sees at the end of every
successful turn, while keeping both underlying status events intact (decision N2 — Handoff
detection and the failed-run error path must both survive).

**Where it actually lived.** `runner_parsing.py:356` (`status_event("completed", summary="Completed")`)
is a persisted `agent_output` row with `output_kind="status"`, `payload.phase="completed"`. It flows
through to the main conversation view (`AgentTimeline.tsx`), where `entryCategory` already classified
any `status`/`diagnostic` output_kind as a `'result'` block, rendered as a visible `ResultCard` — that
card, showing the literal word "Completed", is what the operator was looking at. The *other* surface
named in the queue item, `agent_trigger.py`'s two `kind="status"`/`phase="completed"` SSE broadcasts
(:1569, :2090), turned out to be a red herring for this particular complaint: those are never persisted
(no `persist_event` call, unlike the `queue_entry_queued` broadcasts right above them) — they only ever
reach `useAgentOutput`'s live `lines` state, which `AgentOutputPanel.tsx` explicitly does not render
into the conversation any more (a comment there says so: its only consumer used to be the deleted
handoff-readiness effect). So there was only one rendering site to fix, not two.

**The fix, UI-only.** Added `isSuccessCompletionEntry(entry)` to `agentTimelineModel.ts` — true only
for `kind="agent_output"`, `output_kind="status"`, `payload.phase==="completed"`. `AgentTimeline.tsx`'s
`TurnBody` now returns `null` for that one entry instead of a `ResultCard`, ahead of the existing
`entryCategory === 'result'` check. Nothing else about `entryCategory` or `ResultCard` changed — a
mid-turn status phase (codex's `"plan"`) still renders exactly as before, and a failed run's
`error_event` (`kind="error"`, a structurally different code path — `MessageEntry`'s `isError` branch)
is untouched. Zero backend files changed.

**Verified three ways, not just asserted:**

1. **Unit tests** on the helper itself: `completed` phase → true; `plan` phase → false; `diagnostic`
   output_kind with `phase: completed` → false (wrong output_kind, must not falsely match); an
   `error`-kind entry → false (proves the failed-run path was never at risk).
2. **AgentTimeline render tests**: a two-entry successful turn (`text` + `status/completed`) renders
   the text but not "Completed" and mounts no `result-card-*` testid; a `status/plan` entry still
   renders its `ResultCard`; a `kind="error"` entry's text still renders. Full `hub/ui` suite, run
   last after every test file above was in its final state: **967 passed** (961 recorded in handoff
   0054, +6 new tests this iteration — 3 in `agentTimeline.test.tsx`, 3 in `agentTimelineModel.test.ts`).
3. **A real live turn against the trial Hub on :8010** — not a fixture. Created a throwaway Haiku 4.5
   runner and agent (`q2verify`) in `proj-b44fac0c` ("Throwaway (taste pass)"), sent
   "Reply with exactly the word: pong. Nothing else.", waited for it to finish. Fetched the persisted
   chat history directly: the `status`/`completed` entry is there, byte-identical in shape to before
   (`{phase: completed, summary: Completed}`) — **the event survived**, confirming N2's hard
   constraint. Then drove an actual headless Chromium session (seeded `sessionStorage`/`localStorage`
   the same way `taste_shots.py` does, since no existing script targets a specific agent's
   conversation) to the real running app on :8010, screenshotted the conversation, and read both the
   image and the page's plain text: the turn visibly ends right after "pong" — no chip, no "Completed"
   anywhere in `document.body.innerText`. The one-off driver script was written to `testbed/scratch/`
   and deleted after use, per its own README.

**Checks before commit:** `npx tsc --noEmit` clean, `npm run lint -- --max-warnings 0` clean, full
`npm test` 966/966, `hub/tests/test_agent_output_stream.py` (the closest backend coverage of this
exact payload shape) still 6/6 since nothing there changed. Bundle rebuilt (`npm run build`) and
`hub/hub/static/ui` + its stamp refreshed via `scripts/refresh_ui_bundle.py`, committed together with
`hub/ui/src` as CLAUDE.md requires.

**What a reviewer should distrust:**

- The live-turn verification used a throwaway runner/agent left behind in `proj-b44fac0c` (harmless —
  that project exists for exactly this). Not cleaned up; the operator can delete it or leave it as
  future taste-pass scratch.
- Only the *successful*-turn path was driven live. The failed-run guarantee rests on the backend being
  provably untouched (diffed: zero lines changed outside `hub/ui/`) plus the unit test asserting the
  new helper never matches an `error`-kind entry — not on an actual live failure being forced and
  watched. Forcing a real API error live was judged not worth spending turn budget on, given the
  backend code path itself has zero diff.
- Codex's `status_event("plan", ...)` mid-turn card was checked only via a synthetic unit/render test,
  not a live Codex turn (Codex was not part of tonight's ceiling — Claude-only per the operator's
  stated budget).

**Next:** Q3 — a visible "Working…" indicator with an elapsed-time counter in the composer, replacing
reliance on the header's small `animate-pulse` dot.

---

## Entry 4 — 2026-08-18T00:03+01:00 · Q3 done: a Working indicator with an elapsed counter, in the composer

**Attempted:** put a louder, better-placed signal that the agent is actively responding right next
to the composer, per the operator's complaint that the header's small `animate-pulse` status dot
isn't enough.

**Timestamp source, decided up front.** Prep flagged two candidate fields (`session_started_at`,
`AgentSession.started_at`) as unconfirmed for a *live* run and said to derive from the `run_started`
SSE event if neither held up. Checked all three before writing anything: `session_started_at` is
about the current provider session, not this turn; `AgentSession.started_at` is on session objects
returned by a different endpoint, same mismatch; and `run_started`'s own SSE payload
(`agent_trigger.py:1315-1320`, `:1807-1812`) carries `agent`/`run_id`/`runner`/`model` only — no
timestamp of its own beyond the outer `SSEEvent.timestamp`, which is broadcast time, not run-start
time. None of the three is the thing prep was hoping for. Rather than plumb a new backend field for
one UI counter, added `useElapsedSeconds(active)`
(`hub/ui/src/hooks/useElapsedSeconds.ts`) — it times locally from the moment `isRunning` flips
false→true (`Date.now()`, 1s `setInterval`), which is already the same signal the composer's
placeholder text was already keying off. The one known gap: a run already in progress when the panel
mounts (e.g. switching agents mid-turn) reads from when it was *observed*, not from when it truly
began — the same class of imprecision the header dot already had, not a new one introduced here.

**The fix.** `Composer.tsx`'s control row (trailing slot, beside the send button) now renders three
`animate-pulse` dots plus `Working · {formatElapsedSeconds(elapsed)}` whenever `isRunning` is true —
`0s`–`59s` as bare seconds, `m:ss` at and beyond a minute. Reused Tailwind's existing `animate-pulse`
rather than inventing new keyframes (three staggered instances read as a sequence, and
`index.css`'s blanket `prefers-reduced-motion` rule already caps every animation in the app, this one
included, with no extra work). **The header pill stays** — it is the only place *every* agent status
(not just running) is visible, including with the composer scrolled out of view or collapsed; keeping
both is not an accidental duplication, it is two different jobs at two different distances from the
operator's eyes, and the commit message says so.

**Verified three ways:**

1. **Unit/render tests**, `composerWorkingIndicator.test.tsx`: `formatElapsedSeconds` at the 60s
   boundary (`59` → `59s`, `60` → `1:00`); the indicator is absent while idle; it appears at exactly
   `Working · 0s` the instant `isRunning` flips true and reads `Working · 3s` after 3 fake-timer
   seconds; it disappears the instant `isRunning` flips back to false; and — the trap this class of
   hook invites — a *second* run after an idle gap restarts the count from `0s` rather than resuming
   whatever the first run left behind. Full `hub/ui` suite: **973 passed** (967 → 973, +6). `npx tsc
   --noEmit` and `npm run lint -- --max-warnings 0` both clean.
2. **A real live turn against the trial Hub on :8010** — reused the `q2verify` agent in
   `proj-b44fac0c` from Q2's verification (still present, still idle beforehand). A throwaway
   Playwright script (`testbed/scratch/shot_working_indicator.py`, written and deleted in the same
   turn per its scratch convention) sent a message designed to take a few seconds to generate,
   captured the indicator's text immediately after it appeared and again ~3s later, in both themes:
   light `Working · 0s` → `Working · 3s`, dark `Working · 1s` → `Working · 4s`. The counter visibly
   advancing between two real captures — not a single static screenshot — is what actually proves it
   ticks. Screenshots viewed directly: three green dots and the counter sit cleanly in the control row
   in both themes, legible against both backgrounds.
3. **Post-run settle**: polled the agent's status a few seconds after the turn and it read `idle`,
   with the indicator gone in the next render — matching the "disappears on completion" unit test
   against a real run, not just a synthetic prop flip.

**What a reviewer should distrust:**

- The "already running when the panel mounts" gap above is real and not covered by any test — every
  test and every live drive here observed the transition from idle, none opened the panel mid-run.
- The live verification's two turns overlapped (the dark-theme send queued behind the light-theme
  turn still finishing) — harmless for what was being checked, but means the dark capture's numbers
  reflect a turn that had already been running a moment before the browser navigated to it, not a
  fresh 0s start; the *ticking* is still real, just the absolute numbers are not clean instrumentation.
- Only Claude/Haiku was driven live, per the operator's stated ceiling — Codex's `isRunning` plumbing
  is identical (`agent.status === 'running'` is provider-agnostic) but was not separately watched.

**Next:** Q4 — a distinct control to reopen an existing spec document, alongside Explore rather than
buried inside it.

---

## Entry 5 — 2026-08-18T00:18+01:00 · Q4 done: a distinct control to reopen an existing spec

**Attempted:** give the composer a second, distinct control alongside Explore that reopens a
document not currently attached to the conversation — the operator's complaint was that leaving a
conversation or closing the document panel left no way back except starting a fresh exploration.

**Confirmed the diagnosis before touching anything.** `ComposerSpecControl.tsx`'s no-document
branch rendered only the Explore toggle; `onOpenPicker` was already threaded all the way down from
`ConversationView.tsx`'s `openPicker` (the same callback the Ctrl+K shortcut and the document-open
pill both use to launch the real `SpecDocumentPicker`), but nothing in the no-document branch ever
called it. The picker itself needed no changes — it was simply unreachable from that one state.

**The trap this one actually had, found while wiring it rather than in prep's notes.**
`onOpenSpecPicker` is not a single well-defined "open the picker" callback across every caller —
`NewConversationSurface.tsx` aliases it to `() => setExploring(true)`, the same handler as
`onStartExploration`, because that surface has no conversation yet to attach an existing document
to and therefore no real picker to open. Reusing `onOpenPicker` for the new button would have put a
button on that surface labelled "Open an existing specification document" that actually just armed
Explore — a control that lies about what it does. Instead of reusing the overloaded prop, I added a
new one, `onOpenExistingSpec`, threaded through `Composer.tsx` → `AgentOutputPanel.tsx`, optional
end to end. `ConversationView.tsx` wires it to `openPicker` (a real picker exists there);
`NewConversationSurface.tsx` does not pass it, so the component renders no second control on that
surface at all, rather than a working-differently-than-labelled one.

**The fix.** `ComposerSpecControl.tsx`'s no-document branch now renders `composer-open-existing-spec`
next to `composer-start-exploration` whenever `onOpenExisting` is provided and the control is not
`armed` (armed means a document is about to be created from the first message — reopening a
different one mid-arm would silently discard that intent, so it is hidden then, matching how the
existing-document branch already hides Explore entirely once a document is open). Icon is
`folder_search`, distinct from Explore's `article`.

**Verified three ways:**

1. **Unit/render tests.** `specChatSurface.test.tsx` gained a test asserting both controls render
   in a real mounted `ConversationView` with no document open, and that clicking the new one opens
   the actual `SpecDocumentPicker` dialog (`findByRole('dialog')` named "Search documents") — not a
   mock. `newConversationSurface.test.tsx` gained a test asserting the new control is *absent* on
   that surface, proving the optional-prop gating actually gates rather than merely compiling.
   Full `hub/ui` suite: **975 passed** (973 → 975). `npx tsc --noEmit` and
   `npm run lint -- --max-warnings 0` both clean.
2. **A real session against the trial Hub on :8010.** Opened `q2verify`'s existing conversation in
   `proj-b44fac0c` (left over from Q2/Q3's verification, no document attached) via a throwaway
   Playwright script. Both controls rendered; clicking the new one opened the real picker dialog.
   Created one scratch document via the API (`teal-roc`, `spec/changes/teal-roc/spec.html`) so
   there was something concrete to select — the picker's own tree browsing and selection mechanics
   are pre-existing, unmodified code, already covered by `specPickerTree.test.tsx`, so this was
   about proving the *new wiring* reaches them, not re-proving the tree itself. Selecting it from
   the tree produced a "Spec: teal-roc" pill in the composer and opened the document panel beside
   the conversation — the full reopen path end to end, screenshotted at each step.
3. **The gate, not just the button.** The new-conversation-surface test above is the thing that
   would have caught silently reusing `onOpenPicker` for both the label and the wrong behaviour —
   worth stating because that reuse was the natural first draft and was caught by writing the test
   before assuming the prop was safe to share.

**What a reviewer should distrust:**

- The scratch document `teal-roc` was left in `proj-b44fac0c`, per that project's stated purpose —
  not cleaned up, and the throwaway Playwright script was deleted after use per `testbed/README.md`.
- `armed` is always `false` in `ConversationView` today (nothing passes `specArmed` there); the
  `!armed` guard on the new button is only exercised, live, on `NewConversationSurface` — and that
  surface never renders the new button at all (no `onOpenExisting`), so the guard's *interaction*
  with a truly armed state is asserted only by inference from the code, not observed live. If a
  future surface passes both `specArmed` and `onOpenExisting` together, that combination has not
  been driven.
- Only Claude-side surfaces were driven live; nothing here touches runner-specific code, so this is
  a low-risk gap, not a skipped requirement.

**Next:** Q5 — promote "Open existing project" to equal billing with "Add project" in the sidebar,
including wiring `ProjectRailNav`, which is missing the callback entirely today.


---

## Entry 6 — 2026-08-18T00:31+01:00 · Q5 done: "Open existing project" promoted to equal billing

**Attempted:** make opening an already-registered project as visible and reachable as creating a
new one, per the operator's complaint that "the only option is Create project."

**Confirmed the diagnosis before touching anything.** Everything the feature needs already
existed and worked: `ProjectManagerModal` already serves both `'open'` and `'create'` modes,
`App.tsx` already wired `onOpenExisting` to arm `'open'` mode, and the native folder dialog /
in-app directory browser / path input were all functional. The only defect was the entry point:
`Sidebar.tsx`'s expanded rail rendered "Open existing project" as a bare 15px `folder_open` icon
button with no visible label in a small header row, while "Add project" was a full-width labelled
button at the bottom — different weight, different place, reads as two different tiers of feature
rather than two equally valid actions. Separately, `CompactRail` (the queue item called it
`ProjectRailNav`; no component by that name exists in this codebase — `CompactRail` is what
renders when `compact={true}`) was passed `onCreateProject` but never `onOpenExisting`, so in that
view opening an existing project was not merely hard to see, it was structurally unreachable —
there was no button wired to call it at all.

**The fix.** `Sidebar.tsx`'s expanded (non-compact) branch: removed the header-row icon-only
button entirely, keeping only the recency/tree view toggle there. At the bottom of the project
list, replaced the lone full-width "Add project" button with a two-button row —
`data-testid="open-existing-project"` labelled "Open existing" and `data-testid="create-new-project"`
labelled "Add project", both `variant="outline" size="md"`, `flex-1` so they split the width
evenly. `CompactRail` gained a new required `onOpenExisting` prop, threaded from its one call site,
and now renders an `open-existing-project` icon button (folder_open) directly above the existing
`create-new-project` icon button (folder_plus), both `icon-sm` ghost buttons with accessible
`aria-label`s — the same equal-footing relationship as the expanded view, adapted to the icon-only
idiom that view already uses everywhere else.

**Verified three ways:**

1. **Unit/render tests.** Added one test to `projectRail.test.tsx`'s "the collapsed rail" describe
   block asserting both `open-existing-project` and `create-new-project` render in compact mode
   and each fires its own callback exactly once — the existing expanded-rail test for the same
   pair (`'offers distinct open-existing and create-new actions'`) already covered that half.
   Full `hub/ui` suite: **976 passed** (975 → 976, +1). `npx tsc --noEmit` and
   `npm run lint -- --max-warnings 0` both clean.
2. **A real end-to-end reopen against the trial Hub on :8010.** A throwaway Playwright script
   (`testbed/scratch/shot_open_existing_project.py`, deleted after use) confirmed the expanded
   rail's two buttons read "Open existing" and "Add project" side by side; clicked the new button,
   confirmed the modal opened titled "Open existing project"; typed this repository's own absolute
   path (`C:\Users\huida\Documents\projects\AgentWeave`) into the Directory path field — genuinely
   dogfooding, since this repo is already registered as `proj-5e960453` — and clicked "Open
   project". The app navigated to the AgentWeave project overview, its Activity tab showing a
   fresh "project opened" event. `GET /api/v1/projects` afterward still returned exactly the same
   three project IDs (`proj-5e960453`, `proj-b44fac0c`, `proj-ff695d96`) — no duplicate project was
   created by opening a path that was already registered, which is the failure mode this control
   could plausibly have had and didn't.
3. **The compact rail, separately.** Collapsed the rail in the same script and confirmed
   `open-existing-project` renders there too, with `aria-label="Open existing project"` —
   the previously-unreachable path, now reachable and screenshotted.

**What a reviewer should distrust:**

- Visible label text is "Open existing" (not the full "Open existing project") on the expanded
  button, to fit beside "Add project" in a 252px-wide rail without wrapping; the `aria-label` and
  `title` both carry the full phrase, so this is a visual truncation, not an accessibility gap —
  not independently re-verified against a narrower custom sidebar width (`width` prop range
  180–420px) beyond the default.
- The native folder dialog itself (`openNativeFolderDialog`, OS-level) was not driven — the live
  check went through the modal's manual path-entry field instead, which is pre-existing,
  unmodified code already covered by `ProjectManagerModal`'s own tests; today's changes never
  touched that dialog's wiring.
- Only the expanded and compact rail states were driven live; the `agentSettings` and
  `configuration` rail branches were not touched by this change and were not re-checked.

**Next:** Q6 — stop the console window flashing during normal app use. `pty_runner.py` is the only
spawn site with `CREATE_NO_WINDOW` today; every other bare subprocess call in `hub/hub/` needs a
shared helper and a guard test, and the operator's own eyes watching for the flash matter more here
than the test suite does.

---

## Entry 7 — 2026-08-18T01:50+01:00 · Q6 done: no more console-window flash on Windows

**Inherited state.** This iteration started with the fix already written but uncommitted and
unlogged — `hub/hub/subprocess_windows.py` (new), ten `hub/hub/*.py` files wired to it, a new
`hub/tests/test_no_console_flash.py` guard test, and a matching `src/agentweave/cli.py` fix for
the Docker-probe spawn, all sitting dirty in the tree with no prior log entry. Rather than trust
that and move on (never mark complete on the strength of a plan existing applies just as much to
someone else's unlogged work as your own), this iteration read every diff line by line before
doing anything else, then ran the full verification the queue item asked for.

**The fix, as found.** `hub/hub/subprocess_windows.py` exports one function,
`no_console_kwargs()` — returns `{"creationflags": subprocess.CREATE_NO_WINDOW}` on Windows,
`{}` elsewhere, so the same `**no_console_kwargs()` splat works for `subprocess.run`/`Popen` and
`asyncio.create_subprocess_exec`/`create_subprocess_shell` alike. Every spawn site prep had
identified — `conversation_titles.py`, `requirement_evidence.py` (x2), `launchability.py`,
`main.py` (x3 git/UI-fingerprint calls), `task_integration.py`, `workspace_paths.py`, `worker.py`,
`worktrees.py` (x2), `codex_appserver.py`, `native_dialog.py` — now passes it, plus
`pty_runner.py`'s pre-existing literal `creationflags=subprocess.CREATE_NO_WINDOW` was refactored
to call the same helper so there is exactly one place the flag is decided.

**The guard.** `hub/tests/test_no_console_flash.py` walks the AST of every `.py` file under
`hub/hub/`, flags any `subprocess.run/Popen/call/check_call/check_output` or
`asyncio.create_subprocess_exec/create_subprocess_shell` call whose enclosing function does not
contain `no_console_kwargs` or `creationflags` anywhere in its source, and fails with the exact
line numbers. It matches on (attribute, allowed base identifiers) pairs specifically so it does
not false-positive on `uvicorn.run(...)`, `mcp.run(...)` (FastMCP, not a spawn), or
`asyncio.run(...)` in the migrations env — a real risk given how common `.run(` is outside the
subprocess context. A second test asserts the file-discovery glob actually found something, so an
empty parametrize list (e.g. a bad path after a directory rename) cannot pass this vacuously.

**`src/agentweave/cli.py`'s Docker probe** (`_docker_available`, was line 337) got the same
treatment directly with `subprocess.CREATE_NO_WINDOW` (not the hub helper — the CLI has no
dependency on `hub`, deliberately, per `CLAUDE.md`), with a comment pointing at the existing
`DETACHED_PROCESS` handling for the long-lived Hub spawn as the established precedent. Checked
`src/agentweave/` for the same pattern elsewhere: `cli.py`'s `_open_app_window` `Popen` launches a
GUI browser binary (`chrome.exe --app=...`), which never attaches a console regardless of
`creationflags` — correctly left alone. `tool_surface.py`'s `probe_mcp_registered` has the
identical `shell=True` `cli mcp list` pattern `launchability.py` already fixed, but grepping for
its callers turned up nothing in `src/agentweave/` or `hub/hub/` — it is dead, unreferenced code
(the live path is `hub.launchability.resolve_access_path`, called from `agent_trigger.py`), and
out of the queue item's stated `hub/hub/` scope besides. Left untouched rather than fixed
speculatively.

**Verified, not assumed:**

1. **The guard test itself**, `test_no_console_flash.py`: 192 passed — meaning every spawn site in
   the package today reaches the helper, confirmed by the test that exists specifically to prove
   that claim rather than eyeballing the diff.
2. **Every touched module's own test file** plus `test_pty_runner.py`: 428 passed
   (`test_no_console_flash.py`, `test_pty_runner.py`, `test_launchability.py`,
   `test_conversation_titles.py`, `test_workspace_paths.py`, `test_worktrees.py`,
   `test_requirement_evidence.py`, `test_task_integration.py`, `test_worker.py`,
   `test_codex_appserver.py`, `test_native_dialog.py`).
3. **The CLI suite, in full, including the two tests that used to hang** (Q1b's fixture removed
   the trap): 379 passed, 3 skipped with all 384 collected items selected — no deselection needed
   this time, unlike every prior iteration's note that assumed Q1b's fix but never re-tested it
   with the hanging tests included. `ruff check` and `black --check` both clean on `hub/hub/` and
   `src/agentweave/`.
4. **Live, twice — because the first attempt did not exercise the real code path.** Restarted the
   trial Hub on :8010 (it was still running yesterday's binary, so today's fix was not loaded)
   against the same `hub/data/agentweave.db` fixture DB Q1 pointed it at, from `hub/` per the
   startup trap, and confirmed the same three projects came back with no duplicate registration.
   A background PowerShell poller logged any new `conhost.exe`/`cmd.exe` process for its
   duration. First attempt drove a real turn through the actual UI via Playwright
   (`testbed/scratch/shot_console_flash_check.py`, deleted after use) — but the app has no URL
   router (confirmed by grep: no react-router in `hub/ui/src`), so navigating by URL fragment
   silently no-opped and the turn landed on the wrong agent; fixed by clicking through the sidebar
   instead, which reached `q2verify` and got a real "pong" back. That reused an existing
   conversation, though, so it never touched `conversation_titles.py` (title generation is
   new-conversation-only) — the queue item's own prime suspect. Followed up with a second, more
   surgical probe: called `hub.conversation_titles._run_titler` directly with a real
   `build_title_command(cli="claude", model="claude-haiku-4-5-20251001", ...)` invocation
   (`testbed/scratch/probe_titler_flash.py`, deleted after use) while the same poller watched —
   real `claude` CLI spawn, real "Hi!" response, and the poll log's only new process during that
   window was an unrelated `tasklist | findstr ...Code.exe...` from something outside this
   session's control (a different parent PID each time, not `python.exe` or `claude`) — no new
   `conhost.exe`/`cmd.exe` traceable to the titler spawn. This is the actual site the operator's
   complaint pointed at, driven directly rather than hoped-for via a UI path that happened not to
   reach it.

**What a reviewer should distrust:**

- This iteration inherited the diff rather than writing it from scratch. Every file was read in
  full during this session and the guard test's own pass proves the coverage claim mechanically,
  but the design choices (which files, the AST-matching strategy, the CLI/hub split) were made by
  whichever process wrote them, unlogged. Nothing here found a defect in that work, but "found no
  defect" is not the same confidence as having derived the design.
- The live poller is a proxy, not a screenshot of an actual flash — it detects new
  `conhost.exe`/`cmd.exe` process creation, which is what a console flash requires, but a human
  eye watching the screen (the queue item's own stated stronger bar) was not available in this
  unattended run. The absence-of-new-console-process signal is strong but not identical to "an
  operator watched and saw nothing."
- `tool_surface.py`'s duplicate, unused `probe_mcp_registered` still has the un-suppressed
  `shell=True` spawn. It is dead code today, confirmed by a caller search, but if something starts
  importing it later without noticing the live copy in `hub.launchability`, the flash comes back
  through a path this session's guard test cannot see (it only walks `hub/hub/`, not
  `src/agentweave/`).
- The Hub restart (needed to load today's code) means the taste-pass fixtures Q1 pointed at are
  being served by a fresh process; not expected to matter, but worth naming since a prior entry's
  guard rail was specifically about not losing track of which database was live.

**Next:** Q7 — ship a provisional AgentWeave taskbar icon in place of the generic Python one.
`cli.py`'s `webview.create_window('AgentWeave', url)` call (was line 752) has no icon; no
`.ico`/`.png`/`.svg` asset exists anywhere in the repo yet. Pillow 12.1.1 is available to generate
one programmatically. Per the queue item: timebox the taskbar-icon mechanism hunt (pywebview may
not expose it at all on Windows, where the taskbar often follows the host process rather than the
window) — a committed `.ico` plus a working favicon plus a precise written explanation of what
blocks the taskbar is an acceptable stopping point; do not spend the whole remaining budget
chasing the mechanism.

---

## Entry 8 — 2026-08-18T02:09+01:00 · Q7 done: a real taskbar icon, not just a written blocker

**What shipped.** `scripts/generate_icon.py` renders a provisional mark with Pillow — a rounded
dark badge (`#0a0a0b`, matching `index.css`'s `--bg`) with two diagonal ribbons crossing in a woven
over/under: the blue ribbon (`#7c8cff`, `--blue`/`--ring`, the only real accent hue in the theme's
mostly-grayscale palette) passes through unbroken, the purple one (`#a855f7`, `--purple`) breaks at
the crossing to read as passing under it. Saved as a real multi-size `.ico` (16/32/48/64/128/256)
to `src/agentweave/assets/icon.ico` and `hub/ui/public/favicon.ico` — not a stub, verified by
reopening both with Pillow and asserting the `ICO` format and the size set. `pyproject.toml`'s
`package-data` gained `assets/*` so the CLI's own asset ships in the wheel — confirmed by building
one and inspecting its contents, not assumed (see the trap below). `hub/ui/index.html`'s favicon
link changed from `/vite.svg` — which never actually resolved to anything; `hub/ui/public/` did not
exist before this entry, confirmed by git status reporting it untracked-new, so that reference had
been a silent 404 the whole time — to `/favicon.ico`.

**The window and taskbar are two different fixes, and the risk note was right to flag it.**
`_open_app_window_native` now calls `webview.start(icon=_app_icon_path())`. Read pywebview's actual
Windows backend (`webview/platforms/winforms.py:242-251`) rather than trusting its docstring, which
claims icon support is "Supported only on GTK/QT" — false for the installed 12.1.1: without an
icon, the code falls back to `ExtractIconW(handle, sys.executable, 0)`, i.e. it explicitly pulls the
icon out of `python.exe` itself. That line is the defect the operator saw. Passing `icon=` makes
it `Icon(_state['icon'])` instead — this sets the WinForms `Form.Icon`, which Windows uses for the
title bar and Alt-Tab. It does NOT reach the taskbar button, confirmed empirically (below), which
is exactly the risk the queue item named: on Windows the taskbar icon often follows the host
process. The actual second mechanism is `ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID`,
called once before `create_window` in a new `_set_windows_app_user_model_id()` — this tells Explorer
the process is its own app rather than a fungible `python.exe`, which is what the taskbar keys its
icon and grouping off. Both are needed; each alone was insufficient in testing.

**Verified live, not assumed — screenshots, not guesses.** A throwaway probe
(`.claude/autonomous/scratch/probe_taskbar_icon.py`, deleted after use) opened a real pywebview
window via `webview.start(func, icon=...)`, slept 2.5s for the taskbar to settle, grabbed the full
virtual screen with `PIL.ImageGrab`, then destroyed the window. First pass (icon set, no AUMID):
title bar showed the new mark, taskbar button still showed the stock Python two-snake icon —
confirmed by diffing against a baseline screenshot taken with no AgentWeave window open at all, so
the icon in that taskbar slot could be attributed to this window specifically rather than an
unrelated pinned app. Added the AUMID call, reran: taskbar button now shows the new mark too, same
diff-against-baseline method. Both screenshots were read back through the image tool and visually
confirmed, not inferred from process behaviour. The screenshots are deleted; they were throwaway
verification artifacts, not release material.

**Test coverage added to `tests/test_cli.py`, `TestAppModeNativeWindow`.** Three new tests:
`test_open_app_window_native_sets_windows_app_user_model_id_first` (asserts the AUMID call fires,
and fires before `create_window`, not after — order matters, confirmed empirically it must
precede window creation to take effect), `test_set_windows_app_user_model_id_noop_off_windows`,
`test_set_windows_app_user_model_id_swallows_shell_errors` (mirrors the existing swallow-and-continue
posture right next to this call site). Plus two for the icon path itself:
`test_app_icon_path_resolves_to_a_real_multi_size_ico` (opens the actual packaged file with Pillow
and checks its format and size set — the wheel-content check's unit-test-level twin) and
`test_app_icon_path_missing_asset_returns_none` (a stripped install must not crash window-opening,
just fall back to pywebview's own icon). Two existing tests needed updating for the new
`webview.start(icon=...)` call signature — `test_pywebview_installed_opens_window_with_resolved_url`
now asserts the icon path is passed and resolves to a real file;
`test_webview_start_exception_falls_back`'s fake `start` took a zero-arg lambda before, now accepts
`**kwargs`. 8 → 11 tests in the class.

**What a reviewer should distrust — and one real, unrelated defect this session did NOT fix.**
Verifying the wheel actually ships `assets/icon.ico` required building one, which surfaced something
that has nothing to do with Q7: a stale local `build/lib/` directory (gitignored, untracked, never
cleaned by anyone) still contained `agentweave/transport/git.py` and `transport/local.py` —
files CLAUDE.md records as deleted, and not to be recreated. setuptools' incremental `build_py`
only adds/updates files, never removes ones absent from a later source tree, so this local cache had
silently been resurrecting deleted modules into every wheel built on this machine, indefinitely,
until this entry's `rm -rf build`. That in turn unmasked a second, independent, pre-existing bug:
`tests/test_packaging.py::test_wheel_ships_skill_reference_docs` asserts a specific path,
`agentweave/templates/skills/references/html-spec-conventions.md` — a file commit `a44c8a8` (six
days ago, 2026-08-12, "Ship the authoring flow") deliberately deleted along with the rest of the
aw-spec-* skill references, and the test was never updated to match. It only ever passed locally
because the same stale `build/lib` cache kept resurrecting this file too. `known_debts` in
`STATE.json` records `ci-never-ran-on-master` — this is very likely why nobody caught it: a clean
checkout (what CI would build from) would fail this test today, independent of anything from
tonight's queue. Confirmed reproducible from a clean `build/`: 385 passed, 3 skipped, 1 failed
before this entry's own new tests, same one failure after — Q7's own additions are not its cause.
Deliberately left unfixed: it is a different subsystem (packaging/skills, not app-feel), it
predates this session by six days, and the operator's own scope instruction for tonight (breadth
across all ten items was offered and declined) argues against picking up an eleventh, unplanned
repair mid-session. Recorded in `STATE.json`'s `known_debts` instead. The local `build/` and
`.wheelcheck/` directories used for verification were deleted afterward — gitignored, nothing to
commit, nothing left dirty.

**Full verification, this entry's own change only:** CLI suite 385 passed, 3 skipped plus the one
pre-existing unrelated failure named above (`py -3.11 -m pytest tests/ -q`, from a clean `build/`);
`ruff check` and `black --check --target-version py311` both clean on every touched Python file;
hub UI `npm run lint` and `npx tsc --noEmit` both clean; hub UI `npm test -- --run`: 976 passed
(unchanged from Q5's count — Q7 touched `index.html` and added a `public/` asset, no UI logic, so no
UI test count change was expected and none occurred). `npm run build` succeeded and
`scripts/refresh_ui_bundle.py` recorded a fresh stamp; `hub/hub/static/ui/index.html` now serves
`/favicon.ico` and `hub/hub/static/ui/favicon.ico` exists in the committed bundle.

**Not verified, stated plainly:** this session cannot watch a human open the real packaged app (the
Hub start to app-mode window flow end to end) and see the taskbar with their own eyes — the
screenshot-diff method above is the closest an unattended session can get, and it is a real
screenshot of a real running window, not a mocked assertion, but it is still a different standard of
proof than the operator glancing at their own taskbar tomorrow. Worth a 10-second glance when the
operator is next at the machine.

**Queue status:** Q1 through Q7 are now all done — the six app-feel fixes plus the CLI-suite-hang
prerequisite. Next is Q8, the first of the two decide-nothing explorations
(`openspec/explorations/2026-08-18-what-archiving-a-spec-means.md`).
