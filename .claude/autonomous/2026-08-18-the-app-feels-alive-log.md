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

---

## Iteration 9 — Q8: the spec-archiving exploration (2026-08-18T02:33+01:00)

Wrote `openspec/explorations/2026-08-18-what-archiving-a-spec-means.md`, answering the operator's
three verbatim questions about archiving a spec — delta vs. direct update, structure/tree of a
large spec, and whether a defined entry point exists — with evidence, at least two viable models
per question with costs and rejection reasons, and no recommendation, exactly as instructed.

**The headline finding: CLAUDE.md's own premise for this question is stale, and the exploration
says so plainly.** CLAUDE.md states AgentWeave's lifecycle has "no archive phase and no concept of
a current-behaviour specification" — the whole stated reason openspec still owns the corpus. Reading
`hub/hub/spec_lifecycle.py` directly, rather than trusting that citation, shows five phases, not
three: `exploring`, `proposed`, `approved`, **`archived`**, **`current`**. `git log` on that file
shows why — commit `5e36209`, *"N2: implement the archive transition and the capability document
kind"*, shipped to master on 2026-08-16, three days before this run, via
`openspec/changes/2026-08-16-the-corpus-keeps-what-shipped/` (still open, unreconciled with
CLAUDE.md's prose). Migration `0074` added the phases; the migration head is `0076`. The gap
CLAUDE.md names as blocking the migration was already closed in code before this run started.

**Verified against the live trial Hub, not reasoned about in the abstract.** Queried
`hub/data/agentweave.db` directly (the database Q1 last iteration pointed the running Hub at):
`proj-5e960453`'s one capability document, `spec/capabilities/quiet-hours/spec.html`, is an
untouched empty scaffold — zero requirements, empty summary, sitting at `current`. Its matching
change document, `quiet-hours-for-agent-notifications`, is `archived` with 7 real requirements
ready to cite. `spec_document_merges` has **zero rows in this project**. The merge mechanism —
`POST /project/documents/{path}/merge`, `hub/hub/api/v1/spec.py:1127`, unit-tested with 270 lines
in `test_spec_merge.py` — has shipped and has never been exercised against real content anywhere in
this repository. The "delta vs. direct" question has a code answer (direct, whole-document,
operator-authored, citing sources but not diffing them) but not yet a *lived* one.

**A second, sharper finding, found by reading `save_document`'s branch order rather than assuming
the merge path is self-contained.** `SpecEditProposal` (`hub/hub/db/models.py:1764`, shipped one day
*after* the merge machinery, for a different purpose — gated-rigor review of ordinary document
edits) is a genuine per-requirement add/modify/remove delta, matching openspec's own
ADDED/MODIFIED/REMOVED shape closely. `merge_document()` calls `save_document()` directly
(`spec_service.py:578`), and `save_document()`'s branch to the per-requirement delta path is gated
on `document.rigor`, not on `document.kind` (`spec_service.py:148`). A capability document's rigor
is an ordinary, operator-settable field, independent of `kind`/`phase`. Today the one real
capability document sits at `rigor='sketch'` (confirmed live), so merges apply directly — but
raising it to `contract`/`gate` would silently switch every future merge onto it to per-requirement
review, and `test_spec_merge.py` has zero references to `rigor` (grepped) — this interaction is
unbuilt-for and untested, not merely undocumented. Two features, three days apart, never connected.

Three models given, each with real costs and rejection reasons: (A) adopt the merge mechanism as
built and actually run it for real, starting with the one merge sitting ready right now; (B)
deliberately route capability merges through the already-existing-but-accidentally-reachable
per-requirement delta instead of building anything new; (C) build real capability-level tree
structure, enforcing the `spec/capabilities/<name>/` convention that today nothing in code checks.
Recommends none of them, per instruction.

**What Q10 needs from this, stated concretely rather than left implicit**, since Q10 `depends_on`
Q8: the merge endpoint requires at least one `from_changes` source document in `approved`/`archived`
phase (design D5 step 4) — a first-generation openspec-to-AgentWeave translation has no such source,
because the capability being translated was approved inside openspec, a system the Hub's data model
cannot see. Q10 will hit this as a live 409 the moment it tries the merge route on a first
translation, unless it reads this finding first and decides how to handle it (fabricate a synthetic
source, seed directly the way `hub/seed_taste_doc.py` did for the change-spec document, or something
else) — a decision this exploration surfaces but does not make.

Verified: the exploration's every specific claim (phase list, migration numbers, git commit, table
row counts, test-file grep results, rigor gate location) was checked directly against the code or a
live query this session, not carried from memory or a prior handoff — file paths and line numbers
are cited throughout for a reader who wants to check any of them.

Not touched: `spec/` and `hub/seed_taste_doc.py` (prior-session scratch, left alone per the queue's
own limits), CLAUDE.md's prose (flagged as stale in the exploration and already recorded as
`decisions_for_user.N3` from an earlier iteration; fixing it is the operator's call, not this
iteration's).

**Queue status:** Q1-Q8 done. Next is Q9, the second decide-nothing exploration (does "AgentWeave"
and "hub" still fit), folding in `decisions_for_user.N1` per its own pre-authorisation. The night's
stated actual objective (items 1-6, i.e. Q1-Q7) was already complete as of iteration 8; Q8 and the
coming Q9 are the two explicitly-scoped discussion items (7 and 9), decided nothing, exactly as
asked.

---

## Iteration 10 — 2026-08-18T02:45+01:00 — Q9: the naming exploration, decide nothing

Wrote `openspec/explorations/2026-08-18-does-the-name-still-fit.md`, answering both operator
questions from item 9 ("AgentWeave may not fit the product anymore — it feels more like a factory
now") and item 2's folded-in aside ("also open to renaming hub if there's a better term") as one
document, per `decisions_for_user.N1`'s pre-authorisation.

Read both required documents first, as `next_action` specified, rather than writing from the name
alone: `2026-08-15-where-agentweave-fits.md` (already narrowed the surviving claim to durability,
addressable identity, and an operator-facing UI — not "multi-agent collaboration" as a headline) and
`2026-08-17-architecture-proposals.md` (proposed building on `Loop` and the capability document's
`current` phase, and named directly that "the loop that runs this very session is not in the
product"). Grounded the "feels like a factory" instinct in three shipped, load-bearing facts rather
than restating the operator's mood back at them: the Runner/Agent/Charter separation now three
distinct concepts instead of one CLI role; the archived/current spec lifecycle (confirmed shipped
2026-08-16, this run's own Q8 finding last iteration); and `Loop` as a first-class recurring,
purposeful, queued unit, quoting the operator's own "security scans" example from the architecture
document. Gave both sides of whether "weave" still fits — interlacing threads that depend on each
other mid-process, vs. independent stations producing durable output that accumulates for later
operator inspection — and named what adopting "factory" language would imply (production lines,
a foreman/operator review role, throughput/repeatability) without picking a winner.

Priced a rename against six surfaces, each grepped directly rather than estimated: `agentweave-ai`
and `agentweave-hub` (both published PyPI packages at `1.0.1` — the name-permanence problem exists
the moment a name is published, independent of user count, which sharpens rather than dulls the
operator's "no users yet, wouldn't be too disruptive" framing — it's true for social cost, not for
this mechanical list); the `agentweave`/`aw` CLI entry points (`pyproject.toml:67-68`); the GHCR
image `ghcr.io/gutohuida/agentweave-hub` (`hub/docker-compose.yml:12`); the docs site and its
GitHub-Pages URL, which is coupled to the *repository* name, not just `mkdocs.yml`'s `site_name`;
and the per-project `.agentweave/` marker directory (`src/agentweave/constants.py:8`, with every
other on-disk path derived from it) — this one is not just an in-repo constant, it is a marker
already bound to real registered projects including this repo's own `proj-5e960453`, so renaming it
needs a migration path, not a find-replace. `CLAUDE.md` itself was named as a seventh cost: it uses
"the Hub" as a specific proper-noun referent in well over 100 places, which a bare find-replace of
the word "hub" would corrupt if that term is also renamed — the two questions (product name, hub
term) interact at the prose level even though the document treats them as two separately-costed
decisions.

For the "hub" term specifically, gave three options — keep it (short, matches the literal
multi-project topology, comparatively low external cost since it's a common noun not a trademarked
registry name), rename it to match a factory reframing if one is chosen (same shape of cost as the
product rename, one layer down: `hub/` the directory, `hub.main:app`/`hub.main:run`, the
`agentweave-hub` PyPI package, the GHCR image), or decouple the two decisions entirely (lower
per-decision cost but risks the half-migrated feel `CLAUDE.md`'s own opening section already warns
against for the openspec migration) — recommending none.

Closed with a point this run is well-placed to make honestly: `CLAUDE.md`'s own prose about the
product already went stale once this week — its "no archive phase" claim was true when written and
false by the time this run's Q8 exploration read the code directly (the archive phase shipped
2026-08-16, three days before Q8 checked it, unreconciled with the file's prose). Named that
explicitly as the reason a naming decision, whenever made, should be dated and re-verified against
the code before anyone acts on it, rather than treated as permanently settled prose — the exact
failure mode that bit the archive-phase claim.

No name touched anywhere in code, docs, or UI. Committed on its own
(`openspec/explorations/2026-08-18-does-the-name-still-fit.md`), leaving `spec/` and
`hub/seed_taste_doc.py` (prior-session scratch) untouched per the queue's own limits.

**Queue status:** Q1–Q9 all done. Both decide-nothing explorations (items 7 and 9) are written; the
night's actual objective (items 1–6, Q1–Q7) has been complete since iteration 8. Next in queue order
is Q10 (item 8, translating one openspec capability into an AgentWeave-native document), which
depends on Q8 and inherits the concrete 409 blocker Q8's done_note already named — read it before
starting rather than rediscovering it live against the merge endpoint. Q11 (Tier 2/3 runway) remains
lowest priority and gated behind Q10 finishing or being explicitly parked.

---

## Iteration 11 — Q10: translate one openspec capability into an AgentWeave-native document

Picked `openspec/specs/project-instructions/spec.md` (47 lines, 3 requirements, 4 scenarios) —
small, self-contained, and unlike `opencode-config` (the other short candidate, describing a runner
type carried in dead-looking config surface) every claim in it re-verified against code still
running today: `hub/hub/api/v1/instructions.py` (GET/PUT `/project/instructions`, matches
requirement 1 exactly), `hub/hub/api/v1/agents.py:1054-1058,1293-1296` and `:1865-1871` (both
charter-context read paths prepend instructions when non-empty, matches requirement 2), and
`hub/ui/src/components/instructions/InstructionsPage.tsx` (textarea, Save button, "Saved"
confirmation, pre-fill, and the exact "Changes take effect when agents start a new session" notice,
matches requirement 3). Read Q8's exploration in full before touching the merge route, per its own
last section — Q8 named the blocker precisely: `POST /documents/{path}/merge` requires a
`from_changes` source in `approved`/`archived` phase, and a first-generation openspec translation
has none to cite, because the capability was approved inside openspec, not AgentWeave.

Confirmed the blocker is real, not just documented, by reading the code myself before writing
anything: `spec_service.save_document()` refuses a capability write from any actor whose `kind` is
not `"operator"` (`spec_service.py:129-133`), and the **only** two HTTP routes that call
`save_document`/`merge_document` with an operator actor are `POST /documents` (creates an empty
scaffold — title only, no way to hand it content) and the merge route (blocked, per above). There is
no plain "PUT content onto an existing document" route reachable as operator over HTTP at all —
Q8's "seed directly" recommendation isn't a preference, it's the only path that exists. Took Q8's
first option: a throwaway script (`testbed/scratch/seed_capability_project_instructions.py`, deleted
after use, same disposability as the Playwright probes Q2-Q7 used) that calls
`spec_lifecycle.create_document(..., kind="capability")` then `spec_service.save_document(...)`
in-process with `actor.kind="operator"`, the same shape `hub/seed_taste_doc.py` used for the one
existing change-spec document, run from `hub/` against the live `hub/data/agentweave.db` (confirmed
`cwd` was actually the repo root's `hub/` and not the nested `hub/hub/` before running — an earlier
`cd hub` left the shell there from a prior check and the first attempt silently opened a stray
0-byte `hub/hub/data/agentweave.db`, gitignored and pre-existing, not created by this iteration;
caught before the real write by reading the traceback, `no such table: projects`, rather than
retrying blindly).

Per Q8's finding 2 and 3: left `rigor` at its default (`sketch`) rather than raising it — the one
existing capability document in this project already sits at `sketch`, and Q8 flagged raising rigor
on a capability document as an untested interaction (`test_spec_merge.py` has zero references to
`rigor`) not worth introducing on a first translation with nobody watching. Used the
`spec/capabilities/<name>/spec.html` path convention Q8 identified as unenforced-but-real —
`spec/capabilities/project-instructions/spec.html`.

**The translation itself, and what it lost** — written into the document's own `evidence.limits`
field, not just this log, so an operator reading the document in the app sees the caveat where the
content is: (1) openspec's four scenarios collapsed into three requirements / seven acceptance
criteria because AgentWeave's schema has no heading-level grouping the way openspec's three
`### Requirement:` blocks did — a flattening, not a content loss; (2) openspec's scenarios state
WHEN/THEN only, AgentWeave's `AcceptanceCriterion` schema requires a GIVEN too, so one was authored
for each of the seven that lacked one in the source — new prose, not present in openspec, flagged
rather than presented as an equivalent transcription.

**Verified live against the trial Hub (127.0.0.1:8010), not just by running the script cleanly:**
`GET /api/v1/projects/proj-5e960453/project/documents` lists the new document —
`kind: capability`, `phase: current`, `rigor: sketch`, a real `content_digest`; `GET
/api/v1/projects/proj-5e960453/project/spec?path=spec/capabilities/project-instructions/spec.html`
returns real rendered HTML (not a scaffold) whose stripped text contains the minted requirement
identifiers `FR-1`/`FR-2`/`FR-3` and the literal requirement statements ("ProjectInstructions
table", "prepends project instructions", "markdown textarea") — the same API surface the Hub UI's
document viewer reads from, so "readable in the app" is confirmed at the layer the app actually
uses, not asserted from the write path alone. `GET /api/v1/projects` re-checked afterward: still
exactly the same three projects, no duplicate created. Port 8000 not touched.

**Not done, deliberately, per Q10's own `done_when`:** this is a start, one capability, not a batch
translation of the remaining 29. `spec/` and `hub/seed_taste_doc.py` (prior-session scratch)
untouched. Nothing committed to git for this iteration beyond this log and `STATE.json` — the new
document lives in `hub/data/agentweave.db`, which is gitignored by design (`.gitignore:88`), the
same way every other fixture this run created or restored already did.

**Queue status:** Q1–Q10 done. Q11 (Tier 2/3 runway, lowest priority) is next if time remains before
`stop_at` (2026-08-18T08:00+01:00) — prefer Tier 2 item 7 (the StaticPool fixture race) per its own
note in `known_debts`, do not re-derive the diagnosis already recorded there.

---

## Iteration 12 — Q11: found and reverted a broken fixture-overhead attempt, restored a verified baseline

Started this iteration fresh (no memory of prior iterations) per the process. `git status` showed
uncommitted, unlogged changes to `hub/hub/db/engine.py` and `hub/tests/conftest.py` — nothing in
`STATE.json` or the log said any prior iteration had started this, so treated it as work-in-progress
left by a run that never reached its commit step, and investigated rather than assumed either "safe
to keep" or "safe to discard."

**What the WIP did.** Split `init_db()` into `_bootstrap_data()` (the seeding half) plus the existing
`create_all`/alembic half, then changed `hub/tests/conftest.py`'s `app` fixture to depend on a new
session-scoped `_schema_ready` fixture that runs `Base.metadata.create_all` exactly once, with each
test's `app` fixture only deleting every table's rows and re-running `_bootstrap_data()` — exactly
the shape `known_debts.fixture-overhead` describes as the fix (`create_app()` + `drop_all`/`create_all`
across 43 tables per test is the suite's near-100% overhead).

**It doesn't work.** Ran the full `hub/tests/` suite against it from a verified `hub/` cwd (see the
cwd-drift note below) and got `7 failed, 1934 passed, 8 skipped, 1 xfailed, 399 errors in 587s` — worse
than broken, since 399 errors is not a marginal regression. The errors cluster in bursts early in the
run (`OperationalError: no such table: agent_job_deletions` repeated across `test_jobs_crud.py` and
`test_launchability.py`, among others) then the suite runs clean for the remaining ~60%. Root cause,
read directly rather than guessed: `_schema_ready` calls `Base.metadata.create_all` alone and never
calls `_run_alembic_upgrade()`, so anything the migration chain does beyond what the current models
declare is silently missing for the whole session — the original `init_db()` (which every test used to
call in full) always ran both. `agent_job_deletions` genuinely is in `models.py`, so the missing-table
error is more likely a downstream symptom of the shared `engine`'s single StaticPool connection
landing in a bad state once schema creation and per-test bootstrapping stopped being one atomic
`init_db()` call per test — consistent with, though not a full reproduction of, the exact
`known_debts.staticpool-fixture-race` mechanism (one shared DBAPI connection, a concurrent session's
close rolling back another's pending write). Did not chase the mechanism further than that — the
`do_not_redo` list attached to that debt exists precisely so a single iteration doesn't sink its whole
budget re-deriving a diagnosis seven prior theories already died on.

**Reverted, not repaired.** `git checkout -- hub/hub/db/engine.py hub/tests/conftest.py`. Verified the
revert is actually a fix, not an assumption: full `hub/tests/` suite on the clean tree —
`2337 passed, 11 skipped, 1 xpassed, exit 0, 646.44s (0:10:46)`. `2337 + 11 + 1 = 2349`, exactly
matching `pytest --collect-only`'s count both before and after, so nothing silently dropped out this
time (unlike the broken run, which only ran 2077 of 2349 once errors started cascading). The one
`xpassed` is the known flaky StaticPool-race test itself (`xfail(strict=False)`), passing this run —
expected flakiness, not a new signal.

**Runtime note, worth recording since it revises a number in `known_debts`:** the clean baseline took
10:46, not the ~8 minutes `known_debts.fixture-overhead` cites. Did not re-time a second run to see if
that's noise or a real drift (machine load, more tests added since that estimate was written — the
suite is 2349 tests now) — flagging the discrepancy rather than either trusting or silently correcting
the old number.

**Process note, also worth recording:** hit real cwd drift in this session's own Bash tool — a `cd
hub && <command that errored on bad args>` still executed the `cd` half before the argument error,
and that directory change persisted to the next command despite the command's overall failure,
which combined with the tool's stated "cwd doesn't persist out of `run_in_background`" behavior to
send one full-suite run off into the repo-root CLI suite instead of `hub/tests/` without any error
message announcing the switch (it just silently ran a different, smaller, real suite and reported a
real, pre-existing, unrelated failure — `test_wheel_ships_skill_reference_docs`, already named in
`known_debts.test-packaging-stale-skill-doc-assertion` — which read as a plausible result long enough
to cost real time chasing a phantom "the fixture change broke something" theory before the mismatched
test count (2077 vs 2349 collected) gave it away). Every pytest invocation after that point in this
iteration used an explicit `cd /c/Users/.../hub && pwd` check before trusting the run.

**Not attempted this iteration, deliberately:** the StaticPool race itself. `known_debts` is explicit
that it's a deep, previously-dead-ended problem (seven theories dead, a file-backed DB attempt hung
the suite for 55 minutes) and this iteration's actual finding — that the *shallow* fixture-overhead
fix also runs into it — is now evidence the two debts are more entangled than the queue's phrasing
("if the StaticPool race proves too deep, fixture-overhead is the easier win sitting right next to
it") assumed. Recorded as a new `known_debts` entry below rather than left to be rediscovered blind.

**Tree state:** clean. `hub/hub/db/engine.py` and `hub/tests/conftest.py` match `origin`. `spec/` and
`hub/seed_taste_doc.py` (prior-session scratch) untouched, per the queue's own limits.

**Queue status:** Q1–Q10 done. Q11 (Tier 2/3 runway) remains open — this iteration spent its budget
establishing that the easy path is not actually easy, rather than landing a fix. Runway to `stop_at`
(2026-08-18T08:00+01:00) is still several hours; a future iteration should read
`known_debts.fixture-overhead-hits-the-staticpool-race` below before trying again, and should budget
for the ~11-minute full-suite cost of verifying any attempt twice (broken + reverted, as this one did).

---

## Iteration 13 — Q11: picked a different Tier 2/3 item, closed the fastapi/starlette version bound

Started fresh, verified the branch (`autonomous/2026-08-18-the-app-feels-alive`) and `git log` match
`STATE.json`'s `iteration: 12` claim, and re-read the newest log entry (iteration 12: reverted a
broken fixture-overhead attempt, restored `2337 passed, 11 skipped, 1 xpassed`). Clock check against
`stop_at` (2026-08-18T08:00+01:00): about 4 hours of runway remained.

`STATE.json`'s own `next_action` offered two paths for Q11 — retry the fixture fix at session scope
preserving full `init_db()` semantics, or accept the ~11-minute suite cost and pick a different Tier
2/3 item. Given iteration 12's finding that the "easy" fixture-overhead fix collides with the deep,
seven-theories-dead StaticPool race (`known_debts.fixture-overhead-hits-the-staticpool-race`), and
that this is explicitly the *lowest*-priority queue item (runway filler, not the night's objective),
retrying it a third time did not look like the right use of the budget. Read
`openspec/explorations/2026-08-17-what-to-work-on-next.md`'s Tier 2/3 list for an alternative.

**Checked #4 (trace `pid_alive`'s POSIX callers) first, since it looked cheap** — and found it
already done. `git log --all --grep pid_alive` turned up `b602d9a` ("pid_alive is not a defect: reap
in the two tests that occupy the window") on `autonomous/2026-08-17-one-version-one-product`, and
`git merge-base --is-ancestor b602d9a 1e0d08e` confirmed it is already an ancestor of `master` (hence
of this branch's parent). The roadmap document predates that commit landing, so it lists an item
that's already closed. Did not re-do it.

**Picked #5 instead: decide the `fastapi`/`starlette` version bound.** `hub/pyproject.toml` still
declared `fastapi>=0.110` with no upper bound — confirmed by reading the file directly, not
assuming the roadmap's age meant this one was stale too. Re-read
`openspec/explorations/2026-08-17-the-hub-suite-has-never-run-clean.md` for the actual finding before
picking a number: CI once resolved fastapi 0.141.1 / starlette 1.6.0 while the dev machine ran
0.136.3 / 0.52.1 — a major starlette version boundary crossed silently — and both are now *verified*
compatible (`hub/tests/_routing.py` walks either route shape, confirmed to produce the identical
140-path set on both). So the fix is not "the product is broken above some version," it's "the range
was unbounded and nobody had signed off on what's above what's tested."

**What I did.** Added `starlette<2.0` as an explicit direct dependency in `hub/pyproject.toml`
(starlette is otherwise only transitive via `fastapi`), with an inline comment naming the incident,
citing the exploration, and stating both verified-good versions. Deliberately did NOT add a floor —
the only two data points are 0.52.1 and 1.6.0, and inventing a lower bound neither was tested against
would assert something not established. Left `fastapi>=0.110` itself untouched: the actual incident
crossed a *starlette* major while fastapi stayed on 0.x on both sides (0.136 -> 0.141), so bounding
fastapi's own range would not have caught the real problem and isn't where the evidence points. Also
checked PyPI's index for starlette (`pip index versions starlette`) — latest is still 1.6.0, no 2.x
exists yet, so this bound costs nothing today and only forces a conscious bump whenever 2.0 ships.

**Verified, not just edited.** `tomllib.load()` on the changed file parses cleanly and the
`dependencies` list contains the new entry in the right place. `pip install -e . --no-deps` (no
package versions changed, purely a metadata refresh) succeeded. Ran the two tests most directly
implicated by the original finding, `test_spec_documents_api.py` (the one whose route-introspection
assertion was the sharp edge in the original incident) plus `_routing.py`'s own tests: 23 passed.
`pytest tests/ --collect-only -q` reports 2349 tests collected — the exact count iteration 12's clean
baseline verified, so the change did not break collection anywhere else in the suite. Did not re-run
the full ~11-minute suite: nothing here touches product code, only a dependency declaration, and the
installed environment (starlette 0.52.1) already satisfies the new bound unchanged, so there is
nothing else in the suite that this edit could plausibly affect beyond what was directly tested.

**Not done, deliberately:** roadmap item #6 (make CI prove it's testing a clean environment) — a
separate, larger item, not part of this one. Item #9 (retro-cover 1.0.1) is explicitly parked per
`decisions_for_user` D3 ("Not tonight"). Item #10 needs an actual release and is out of scope for
this driver per `limits`.

**Tree state before commit:** `hub/pyproject.toml` modified; `spec/` and `hub/seed_taste_doc.py`
(prior-session scratch) untouched, staged nothing from them.

**Queue status:** Q1–Q10 done. Q11 (Tier 2/3 runway) — roadmap item #5 closed this iteration; #4 found
already closed on a merged branch; #7 (StaticPool race/fixture overhead) remains open and is the
deepest remaining item, not attempted again this iteration per the reasoning above. Runway to
`stop_at` (2026-08-18T08:00+01:00) is still roughly 3.5 hours.

---

## Iteration 14 — Q11: roadmap item #6, scoped down and verified, not the full literal proposal

Started fresh, verified branch (`autonomous/2026-08-18-the-app-feels-alive`) and `git log` matched
`STATE.json`'s `iteration: 13` claim exactly (`a62f910` heartbeat back-date on top of `6caf230`, the
starlette-bound commit). Clock at start: `2026-08-18T04:12:04+01:00`, ~3h48m of runway to `stop_at`.

`next_action` offered roadmap item #6 ("make CI prove it's testing a clean environment") as the more
approachable of the two remaining Tier 2/3 candidates, item #7 (StaticPool race) being the deep one
with two prior failed attempts already on record. Read both source documents before writing anything:
`openspec/explorations/2026-08-17-what-to-work-on-next.md`'s item 6, and the incident it cites,
`openspec/explorations/2026-08-17-the-hub-suite-has-never-run-clean.md` decision #3.

**The literal roadmap proposal turned out to be weaker than it reads.** Its own sizing note hedges
("likely a CI-only assertion that skip counts match an expected baseline, or that CI's dependency
resolution is pinned/checked" — the author's own uncertainty, not a spec). Traced the actual incident
narrative in the source doc rather than trusting the roadmap's compressed summary: `hub-test` failed
in CI with `ModuleNotFoundError: No module named 'agentweave'` for three weeks, unfixed, because a
red CI job was dismissed as "a CI problem" rather than investigated — the job was already loud and
failing; nobody looked. A skip-count baseline assertion would not have caught that (it never reached
a skip; it failed outright), and no code change fixes "a red job got ignored for three weeks" — that's
vigilance, not a coverage gap. Recording this rather than silently implementing the literal proposal
and claiming it solves what the roadmap said it solves.

**Checked whether a skip-count baseline was even implementable.** Grepped `hub/tests/` and `tests/`
for `skipif`/`pytest.mark.skip`: every skip is a legitimate platform gate (Windows-only pty/ConPTY
behaviour, POSIX-only file-mode tests, `croniter` availability) — none skip because CI is missing a
binary it's "meant to provide." Also confirmed the CLI suite's skip count is platform-dependent
(`tests/test_utils.py`'s two POSIX-only tests skip on Windows, run on Linux/macOS), so a single fixed
baseline number across the `test` job's 3-OS × 2-Python matrix would be wrong on at least two of six
legs from day one — a fragile, matrix-aware baseline file was the only correct version, and verifying
it would need pushing and watching six real GitHub Actions legs, which this session cannot do (no CI
credentials/runner access here, and matrix-fragile baselines are exactly the kind of check people
learn to ignore, the same failure mode as the incident itself). Decided not to build something that
can only be verified by trusting it, unpushed, against six unseen runners.

**Scoped down to what's small, safe, and actually verifiable from here — a `Verify environment` step
in both `test` and `hub-test`, running an import check plus `pip check`, right after each job's
install step.** This targets the same incident more literally: `pip install` succeeding is not the
same as the installed packages resolving correctly from that checkout (exactly what went silently
missing) or the dependency graph being internally consistent (the same class of surprise as the
fastapi/starlette incident item #5 closed last iteration, even though `pip check` would not itself
have caught that specific case — it catches conflicting requirement declarations, not an unpinned
range resolving to an untested version). A dedicated, clearly-named step gives CI a distinct,
unambiguous failure point for "the environment is broken" separate from "a test failed" — the
closest a code change gets to preventing a repeat, short of fixing human vigilance.

**Hit and worked around a real trap while writing the `test`-job check, rather than shipping it
blind.** First attempt checked both `agentweave` and `hub` from the repo root (the `test` job's cwd
throughout) — `python -c "import hub"` from there raises `ImportError: cannot import name
'__version__' from 'hub' (unknown location)`, the exact shadowing bug CLAUDE.md's "trial Hub" section
documents for `-m uvicorn`: the repo-root `hub/` directory resolves as a namespace package before the
editable-installed `hub` package (rooted at `hub/hub/`) is found, because cwd is on `sys.path[0]` for
plain `python -c` too, not just `-m`. This would have made the new check fail every single `test` job
run for a reason with nothing to do with what it exists to catch — verified the failure directly with
`py -3.11 -c "import hub"` from the repo root before deciding what to do about it, not assumed from
memory of CLAUDE.md's prose. Fixed by checking only `agentweave` in the `test` job's step (its cwd is
the repo root, where `hub` cannot be checked safely) and checking both `agentweave` and `hub` in the
`hub-test` job's step (its cwd is `hub/`, confirmed clean by testing the same import from there — no
shadowing, since the namespace-package match at that level doesn't recur one directory down). Left an
inline comment on both steps explaining the asymmetry so a future editor doesn't "fix" it back into
the trap.

**Verified, not just written.** Ran both exact `run:` blocks locally, from the exact cwd each job
uses (repo root for `test`; `hub/` for `hub-test`, matching the job's `defaults.run.working-directory`
and the one step-level override): both `python -c` imports resolved to the expected editable-install
paths (`src/agentweave/__init__.py`, `hub/hub/__init__.py`) and both `pip check` runs reported "No
broken requirements found" with exit 0. Parsed the new YAML with `yaml.safe_load` to confirm it's
well-formed. Cross-checked the PowerShell quoting (GitHub's `windows-latest` runner defaults `run:`
steps to `pwsh`, not bash) by running the identical `python -c "..."` line through this session's own
PowerShell tool — it parsed and ran correctly, so the double-quoted-with-embedded-single-quotes form
is not bash-only syntax that would break on the Windows matrix legs. Did **not** verify by pushing and
watching real Actions runs — no way to do that from here — which is exactly why the change was kept
to the smallest piece that's provably correct standalone, rather than the matrix-aware baseline file
that could only be trusted after the fact.

**What this does not solve, stated plainly rather than left implicit:** it would not, by itself, have
prevented the three-week gap the roadmap item is named for — that job was already failing loudly and
was ignored regardless of how clearly the failure was named. It also does not implement either of the
roadmap's own two literal suggestions in full (no skip-count baseline, and `pip check` doesn't cover
the "unpinned range, untested version" class the fastapi/starlette incident actually was). It is a
smaller, honestly-scoped, verifiable slice: a broken install now fails at an unmistakably-named step
instead of surfacing as one more red result buried inside the pytest step's output.

**Tree state before commit:** `.github/workflows/ci.yml` modified (two new steps); `spec/` and
`hub/seed_taste_doc.py` (prior-session scratch) untouched, staged nothing from them.

**Queue status:** Q1–Q10 done. Q11 (Tier 2/3 runway) — roadmap items #4, #5, and now a scoped #6 are
closed or addressed; only #7 (StaticPool race / fixture overhead) remains, still deliberately not
attempted a third time this iteration for the reasons `known_debts.fixture-overhead-hits-the-staticpool-race`
already records. Runway to `stop_at` (2026-08-18T08:00+01:00) is still roughly 3.5 hours.

---

## Iteration 15 — Q11: third attempt at the StaticPool race, reverted; a new failure mode found, not a fix

Started fresh, verified branch (`autonomous/2026-08-18-the-app-feels-alive`) and `git log` matched
`STATE.json`'s `iteration: 14` claim exactly (`835c3ce` heartbeat back-date on top of `e182307`, the
CI environment-sanity commit). Clock at start: `2026-08-18T04:27:03+01:00`, ~3h33m of runway to
`stop_at`. Tree clean apart from the carried-forward `spec/` and `hub/seed_taste_doc.py` scratch.

`next_action` pointed at the one remaining Q11 item, roadmap #7 (the StaticPool race / fixture
overhead), explicitly framed as the deepest item with two prior failed attempts on record and
permission to park it if runway got short. Runway was not short, so attempted it — this entry
records a third failure, of a new kind, and the decision to revert rather than push a partially
understood fix onto the branch.

**What was built.** Read `known_debts.staticpool-fixture-race` and
`known_debts.fixture-overhead-hits-the-staticpool-race` in full before writing anything, per their own
instruction not to re-derive a diagnosis seven-plus prior theories already died on. Both debts agree
the real fix needs two halves together: (a) a file-backed test `DATABASE_URL` instead of `:memory:`,
so each session gets its own real connection from `AsyncAdaptedQueuePool` instead of one shared
`StaticPool` connection racing itself, plus WAL + `busy_timeout` pragmas so concurrent file access
doesn't immediately fail; and (b) session-scoped schema creation, so `_run_alembic_upgrade()`'s 70+
migrations run once per test *session* rather than once per *test* — iteration 12's attempt did only
half of (b) (create_all-only, no alembic, still on `:memory:`) and produced 399 errors; the plain
"file-backed alone" shape is on record as having hung the suite for 55 minutes, almost certainly
because *every one of ~2350 tests* would otherwise re-run the full alembic chain against a real file.

Implemented both halves together this time:
- `hub/hub/db/engine.py`: a `sqlalchemy.event.listens_for(engine.sync_engine, "connect")` hook setting
  `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000` on every new connection, gated on
  `"sqlite" in database_url and ":memory:" not in database_url` so production (already file-backed,
  already on `AsyncAdaptedQueuePool`) picks it up too and nothing changes for `:memory:` callers.
  `init_db()` split into `_create_schema()` (the `create_all` + `_run_alembic_upgrade()` half) and
  `_bootstrap_data()` (the project/key/operator-credential/runner/charter seeding half) — same split
  iteration 12 already tried, but this time paired with the file-backed switch below rather than used
  alone against `:memory:`.
- `hub/tests/conftest.py`: `DATABASE_URL` now a pid-suffixed temp file
  (`%TEMP%/agentweave_hub_test_<pid>.db`) instead of `:memory:`. A new session-scoped autouse fixture
  calls `_create_schema()` exactly once. The per-test `app` fixture no longer does
  `drop_all`/`create_all`/`init_db()`; it deletes every table's rows (`reversed(Base.metadata.sorted_tables)`,
  respecting FK order) and calls `_bootstrap_data()` to re-seed, keeping the schema itself untouched
  for the whole session. A session-scoped `_cleanup_test_db` fixture removes the db file plus its
  `-wal`/`-shm`/`-journal` sidecars at teardown.

**It does not cleanly work, and the failure is not the one that was expected.** Ran
`tests/test_agent_trigger_overrides.py` (the file holding the `xfail(strict=False)` test this whole
debt is named after) in isolation, three times in a row: every run reported `1 xfailed, 1 xpassed` for
that *single* test, i.e. pytest emitted TWO separate outcome lines
(`tests/test_agent_trigger_overrides.py::test_a_conversation_whose_model_changed_attributes_usage_per_turn XPASS`
then the identical nodeid again as `XFAIL`) for one collected item — confirmed via `--collect-only`
that only one test is actually collected. This is not the documented failure (a silently lost commit);
it is a NEW symptom. Isolated the cause by disabling just the WAL/`busy_timeout` listener
(`if False and ...`) and re-running: the double-report persisted identically, so it is not
WAL-specific — merely switching off `:memory:`/`StaticPool` onto a real per-session connection pool
is enough to trigger it, on its own, regardless of the pragmas. Most likely mechanism (not fully
confirmed): pytest 9's built-in `unraisableexception`/`threadexception` plugins turning a background
asyncio task's now-genuinely-concurrent exception (something that could not surface under the single
shared `StaticPool` connection's accidental serialization) into a second, xfail-marked-so-non-fatal
report for the same node. Ran the same file alongside three others (`test_agent_trigger.py`,
`test_jobs.py`, `test_worker.py`, 91 tests collected) and the double-report did NOT reproduce that
time (`89 passed, 1 skipped, 1 xpassed`, no `xfailed`) — genuinely non-deterministic across runs, the
signature of a timing race rather than a deterministic bug, which is consistent with switching pools
having changed the race's shape rather than removed it.

**A second, independent, fully deterministic bug surfaced in the same run:** the session-scoped
cleanup fixture failed with `PermissionError: [WinError 32] The process cannot access the file because
it is being used by another process` trying to `unlink()` the temp db — the engine's connection pool
was never disposed (`await engine.dispose()`) before teardown, so Windows still held the file open.
Fixable (dispose the engine first), but left unfixed since the whole approach was reverted.

**Reverted, not repaired.** `git checkout -- hub/hub/db/engine.py hub/tests/conftest.py`. Re-ran
`tests/test_agent_trigger_overrides.py` alone afterward to confirm the tree is back to documented
baseline behaviour: `5 passed, 1 xpassed` (no `xfailed` this run — consistent with the xfail reason's
own text, "this machine won it every time"). Sixteen leftover
`%TEMP%/agentweave_hub_test_*.db(-wal/-shm)` files from the experiment's various runs were deleted
(outside the repo, in the OS temp directory, not tracked by git — cleanup for hygiene, not required
for tree cleanliness).

**Why this was not pushed further this iteration.** The double-report artifact breaks the exact
invariant every prior iteration's verification relied on (`passed + skipped + xfailed + ... ==
--collect-only`'s count) in a way that is non-deterministic and not understood — landing it and
declaring the suite "green" would risk silently making future verification unreliable across all 2349
tests, not just the one test that happened to surface it here. That is a worse outcome than a third
recorded failure. `known_debts` already establishes the norm of stopping at understanding-plus-revert
rather than pushing a partially-diagnosed change through the full suite; followed that norm rather than
spending the remaining runway chasing the exact plugin mechanism live.

**What the next attempt needs, concretely, that this one didn't have:**
1. Diagnose the double-report mechanism directly rather than guessing — run the isolated failing test
   under `python -X dev` or with `-p no:unraisableexception -p no:threadexception` to see if either
   flag makes the second report disappear, which would confirm the mechanism above; if confirmed, find
   *which* background task raises and why the new pool makes that possible.
2. Call `await engine.dispose()` in the cleanup fixture before unlinking the file (the deterministic
   Windows bug above).
3. Only after (1) is understood, re-run enough of the suite (chunked, given the ~600s command cap) to
   confirm the collected-count invariant holds everywhere, not just in the one file this iteration
   touched — the non-reproduction in the 91-test combined run means a single-file check is not enough
   evidence either way.

**Tree state:** clean. `hub/hub/db/engine.py` and `hub/tests/conftest.py` match `origin`. `spec/` and
`hub/seed_taste_doc.py` (prior-session scratch) untouched.

**Queue status:** Q1–Q10 done. Q11 (Tier 2/3 runway) — roadmap #7 now has three recorded failed
attempts (55-minute hang; 399 errors; this iteration's non-deterministic double-report). Runway to
`stop_at` (2026-08-18T08:00+01:00) is still roughly 3h15m. Given three independent failure modes now
on record for the same debt and no code changes safe to land, the next iteration should treat Q11 as
parked pending a human decision on whether it is worth a fourth attempt, and pick from what remains of
the roadmap document or another self-directed task instead, per the queue's own "do not leave a
half-migration in the tree at 08:00" instruction — there is no half-migration here, the tree is clean,
but roadmap #7 itself should not be attempted a fourth time blind.

---

## Iteration 16 — Q11/roadmap #8: one requirement-level mapping slice of the `2026-07-30-hub-native-experience` audit

Started fresh, verified branch (`autonomous/2026-08-18-the-app-feels-alive`) and `git log` matched
`STATE.json`'s `iteration: 15` claim exactly (`7b59df7` heartbeat back-date on top of `680539a`,
iteration 15's StaticPool revert). Clock at start: `2026-08-18T04:42:16+01:00`, ~3h18m of runway to
`stop_at`. Tree clean apart from the carried-forward `spec/` and `hub/seed_taste_doc.py` scratch.

`next_action` explicitly parked roadmap #7 (the StaticPool race — three independent failure modes on
record) and pointed at re-reading `openspec/explorations/2026-08-17-what-to-work-on-next.md` for
anything else in scope. Re-read it. Tier 1 (judge taste-pass, archive six changes, decide the branch)
is explicitly the operator's own eye per the roadmap document's own closing line — not something an
autonomous pass should self-certify. Tier 2 #4–#6 are already closed (iterations 13–14); #7 is parked.
Tier 3 #9 and #10 are `decisions_for_user` items the operator already answered "None yet" to. That
left Tier 3 #8 — "Reconcile or retire `2026-07-30-hub-native-experience`" — as the one item genuinely
open and self-directed.

**The roadmap's own framing turned out to be stale.** It describes phase 13/14 of that 1911-line
`tasks.md` as needing "an audit pass... read each unchecked task, check it against `openspec/specs/`
and `CLAUDE.md`." Reading the file first (before writing anything) found this had already happened,
repeatedly, with dated notes as recent as 2026-08-17 — phase 13's N6 triage pass ticked six items on
re-confirmed code citations and left seven genuinely open with file:line evidence each; phase 14 went
through a full scenario-level pass the same day and closed to "15 of 19 ticked, 2 partial, 2
structural." Phases 9–12 all carry "closed by real successor implementation" notes citing specific
archived changes. The roadmap document was written *before* several of these updates landed the same
day, so its "needs an audit" framing was accurate when written and stale by the time this iteration
read it. Redoing that audit from scratch would have been pure duplicate work — reading first, rather
than assuming the task was as raw as its own description, avoided that.

**What was actually still open: phase 16.2**, the umbrella-archival blocker, whose own 2026-08-12 note
says "closing 16.2 requires deciding, per delta spec and per requirement, whether its content lives
somewhere in the current 31 [`openspec/specs/`]" — and that note's own recommended order was "settle
phase 14's design question, then do the mapping." Phase 14 was settled five days later (2026-08-17),
so the mapping itself had never actually been started. Picked one delta spec to map rather than
attempting all nine remaining in one pass, given runway and the size of each (137–221 lines per delta,
compared against either a same-named current spec or, for the eight renamed/absent ones, a search for
where the content actually landed).

**Picked `agent-composer`**, one of the two 16.2 called "present under the same name" — the smallest,
most direct comparison (no renaming to trace first). Read both files in full:
`openspec/changes/2026-07-30-hub-native-experience/specs/agent-composer/spec.md` (138 lines) against
`openspec/specs/agent-composer/spec.md` (306 lines, substantially grown since). The current spec's
final requirement, "The composer addresses the conversation it belongs to" ("the composer MUST NOT
offer a control that redirects a submission to a different agent"), reads as the literal opposite of
the delta's "The active agent can be changed from the conversation... without leaving the
conversation." Both cannot be true of the same shipped product, so this could not be resolved by
reading prose alone — traced it against history and the live tree instead of guessing which document
was current.

Found the archived change `2026-08-06-hub-collaboration-and-conversation-fixes` **REMOVED** the
in-place agent selector three days after phase 12's own 2026-08-03 note claimed it "shipped... every
item in 12.1–12.4 is now implemented and verified" — its delta spec quotes the operator's own reason
verbatim: the redirect "left no trace in the conversation the operator was looking at... the operator
reported the affordance as counterintuitive and asked for its removal." Did not trust the archived
spec's word alone that this reversal is still what's live today: grepped
`hub/ui/src/components/agents/Composer.tsx` and confirmed lines 277–283 have no recipient-selector
control at all, with the component's own inline comment stating the identical removal rationale —
independent confirmation in the running product, not just in spec history.

**What was written, not implemented.** Two dated notes added to
`openspec/changes/2026-07-30-hub-native-experience/tasks.md` (the only file touched this iteration):

1. Under phase 12, a `**Correction (2026-08-18)**` block laying out the contradiction, the evidence
   trail (delta spec → archived removal spec, quoted → live `Composer.tsx` lines), and what it means
   for task 12.1 specifically: "in-place switching" is not merely unbuilt, it is a *rejected design* —
   reopening it would contradict a recorded operator decision — while "search" and "launchability
   indicators" did ship, just on a different surface (agent creation, not in-conversation redirect)
   than 12.1 names as a whole. The 2026-08-03 note's "every item in 12.1–12.4... implemented and
   verified" is corrected to "12.2–12.4 verified; 12.1 built-then-reversed, and now not wanted at
   all" — a materially different claim a future reader relying on the old note alone would not get.
2. Under 16.2, an update note recording that its own stated prerequisite (phase 14's design question)
   is now satisfied, so the requirement-level mapping can start in earnest; that this iteration did
   exactly one of the nine remaining specs; and that even `agent-composer` — one of the two 16.2 had
   called "present under the same name," implying a clean match — is not actually clean at requirement
   level, so a name match alone cannot be trusted for the other name-match case (`agent-tool-surface`)
   either without its own check. Named the eight specs still needing this pass explicitly
   (`agent-conversation-timeline`, `agent-identity-and-skills`, `agent-inbound-queue`,
   `hub-interface-feel`, `hub-native-runtime`, `hub-visual-language`, `spec-authoring`,
   `spec-traceability`, plus re-confirming `agent-tool-surface`) so the next pass has the list rather
   than having to rediscover it.

No checkbox was ticked — this file's own reconciliation rule (established by every phase's prior
notes) is that a box ticks for verified behaviour, not for a decision or a correction, and nothing new
was *built* this iteration. No archiving was attempted; that stays the operator's call per the
umbrella's own 16.3 task and per `decisions_for_user` D1 in this branch's `STATE.json`, both of which
this iteration re-confirmed rather than overrode.

**Verified before committing:** `git status --short` showed only the one intended file modified, plus
the carried-forward `spec/` and `hub/seed_taste_doc.py` scratch — nothing else touched. Re-read the
edited region in full after a line-wrap fix (an inline code span had split a file path across two
blockquote lines, which would have rendered with a literal space injected into the path — caught by
re-reading, not assumed correct from the Edit tool's success alone, and fixed to keep the path
intact). Confirmed `openspec` CLI 1.4.1 is on PATH but did not run `openspec validate` against this
file — `tasks.md` is prose/checklist, not a `proposal.md`/`design.md`/`specs/*.md` the validator
schema-checks; the two other in-flight edits this session (STATE.json, this log) are outside its
scope entirely.

**Tree state before commit:** `openspec/changes/2026-07-30-hub-native-experience/tasks.md` modified
(2 new notes, 64 lines); `.claude/autonomous/STATE.json` updated (iteration, heartbeat, Q11 done_note,
next_action); `spec/` and `hub/seed_taste_doc.py` (prior-session scratch) untouched, staged nothing
from them.

**Queue status:** Q1–Q10 done. Q11 — roadmap #7 stays parked (three failure modes on record); roadmap
#8 has one of nine remaining delta-spec mappings done (`agent-composer`), with the other eight and a
re-check of `agent-tool-surface` explicitly listed in the new 16.2 note for whoever continues it.
Runway to `stop_at` (2026-08-18T08:00+01:00) is still roughly 3h.

---

## Iteration 17 — Q11/roadmap #8: second 16.2 requirement-level mapping slice (`agent-inbound-queue`)

Started fresh, verified branch (`autonomous/2026-08-18-the-app-feels-alive`) and `git log` matched
`STATE.json`'s `iteration: 16` claim exactly (`77b7ba2` heartbeat back-date on top of `d96fcf8`,
iteration 16's `agent-composer` mapping). Clock at start: `2026-08-18T04:57:10+01:00`, ~3h of runway
to `stop_at`. Tree clean apart from the carried-forward `spec/` and `hub/seed_taste_doc.py` scratch.

`next_action` pointed straight at continuing the 16.2 requirement-level mapping, one delta spec at a
time, and specifically suggested `agent-inbound-queue` next (16's own REDEFINED note already flags it
as one of two deltas that "overstate the system"). Followed that.

Read `openspec/changes/2026-07-30-hub-native-experience/specs/agent-inbound-queue/spec.md` in full
(173 lines, six requirements: one ordered queue per agent, turns start on arrival, inline delivery up
to a cap, a hop budget, stop-without-losing-queued-work, configurable limits). No file named
`agent-inbound-queue` exists under `openspec/specs/` — confirmed by listing the directory rather than
trusting the umbrella's own "absent under that name" list at face value, since 16.2's 2026-08-12 note
already warned absence-by-name is not evidence of being unsynced.

Grepped `hop budget`, `hop depth`, `inbound queue`, `per-turn delivery`, and `queue` across all 31
current specs to find where the content actually landed, rather than guessing. It surfaced in at
least six: `agent-capability-plane`, `agent-configuration`, `agent-conversation-workspace`,
`agent-tool-surface`, `conversation-lifecycle`, `local-project-workspace`, `run-task-binding`, and
`spec-document-authority` — the delta's content did not move to one successor, it scattered.

**Five of six requirements confirmed shipped as described**, checked against both current spec prose
and live code rather than prose alone:

- Turn-starts-on-arrival and inline delivery: `agent-tool-surface/spec.md:20-39` ("the agent has its
  queued entries... not instructed to call a retrieval tool").
- Hop budget: `agent-tool-surface/spec.md:61-65` ("Messages sent through the tool surface obey the
  queue... subject to the hop budget"), and the numeric default checked directly in code —
  `hub/hub/inbound_queue.py:15-16` (`DEFAULT_HOP_BUDGET = 6`, `DEFAULT_TURN_DELIVERY_CAP = 10`) and
  `hub/hub/db/models.py:48-49` (`Project.hop_budget` default 6, `turn_delivery_cap` default per the
  same file) — both numbers match the delta's stated defaults exactly, five weeks after it was
  written.
- Configurable limits: `local-project-workspace/spec.md:127-138` ("Each project SHALL expose its
  name, hop budget, per-turn delivery cap...").
- Delivered-entries-not-redelivered-after-stop: intact but reworded — the delta says "MUST NOT be
  redelivered," the current spec says "its input is not returned to the queue"
  (`agent-conversation-workspace/spec.md:1210`, scenario at `:1268-1271`, "A stopped run keeps its
  input").

**One requirement was not a rename, it was superseded by a materially different architecture** — the
kind of finding that only shows up by reading the current spec's own scenarios and the live code, not
by pattern-matching prose, and the reason this pass is worth doing per-requirement rather than
per-file. The delta's first requirement is "each agent has one ordered inbound queue... both operator
input and peer messages SHALL enter that same queue" — singular and agent-scoped, with no notion of
which conversation an entry belongs to. Checked whether the delta ever mentions conversations at all:
`grep -ni conversation` on the delta file returned nothing — confirmed, not assumed, before writing
the finding. The shipped model is conversation-scoped: `InboundQueueEntry` carries a `conversation_id`
column (`hub/hub/db/models.py:546`), `queued_entries()` filters by it when one is supplied
(`hub/hub/inbound_queue.py:72-89`), and `agent-conversation-workspace/spec.md`'s own scenario
"Different conversations never share one provider turn" (line 71) states plainly that "one agent has
eligible queued entries for multiple conversations" — the literal opposite of one ordered queue.
Conversations did not exist as a first-class entity when this delta was written (`2026-07-30`, before
the `agent-conversation-workspace` successor that introduced `conversation_id`), so this is not
oversight or drift, it is the model genuinely widening under a later change. A requirement-level sync
must record this as a redefinition, not tick it as a match on the strength of the surviving numbers
and hop-budget mechanics being otherwise faithful.

**What was written, not implemented.** One dated note added under 16.2 in
`openspec/changes/2026-07-30-hub-native-experience/tasks.md` (the only file touched this iteration),
recording: the six requirements and where each landed; the two verified-live numeric defaults with
file:line; the stop-semantics rewording with file:line; the conversation-scoping supersession with the
grep-confirmed absence of the word "conversation" in the delta and the three code/spec citations that
establish the current shape; and an updated tally — two of the eight remaining unmapped specs now done
(`agent-composer` from iteration 16, `agent-inbound-queue` this iteration), six left
(`agent-conversation-timeline`, `agent-identity-and-skills`, `hub-interface-feel`, `hub-native-runtime`,
`hub-visual-language`, plus re-confirming `agent-tool-surface` at requirement level).

No checkbox ticked, no code changed, no archiving attempted — consistent with the file's own
reconciliation rule and with `decisions_for_user` D1 in `STATE.json`, both re-confirmed rather than
overridden.

**Verified before committing:** `git status --short` showed only the one intended file modified, plus
the carried-forward `spec/` and `hub/seed_taste_doc.py` scratch. Re-read the added note in full after
writing it, including re-checking the "31 current specs" count against a live `ls` (not carried over
from memory) and re-grepping the `hub/hub/db/models.py`/`hub/hub/inbound_queue.py` line numbers cited
against the actual file contents rather than trusting the first grep's line numbers to still be
accurate after re-reading surrounding context. Did not run `openspec validate` — same reasoning as
iteration 16: `tasks.md` is prose/checklist, outside that validator's schema-checked scope.

**Tree state before commit:** `openspec/changes/2026-07-30-hub-native-experience/tasks.md` modified
(1 new note, 33 lines); `.claude/autonomous/STATE.json` updated (iteration, heartbeat, Q11 done_note,
next_action); `spec/` and `hub/seed_taste_doc.py` (prior-session scratch) untouched, staged nothing
from them.

**Queue status:** Q1–Q10 done. Q11 — roadmap #7 stays parked (three failure modes on record); roadmap
#8 now has two of nine remaining delta-spec mappings done (`agent-composer`, `agent-inbound-queue`),
with six specs plus a re-check of `agent-tool-surface` still listed in the 16.2 note for whoever
continues it. Runway to `stop_at` (2026-08-18T08:00+01:00) is roughly 2h50m.

---

## Iteration 18 — Q11/roadmap #8: third 16.2 requirement-level mapping slice (`agent-conversation-timeline`)

Started fresh, verified branch (`autonomous/2026-08-18-the-app-feels-alive`) and `git log` matched
`STATE.json`'s `iteration: 17` claim exactly (`41fa190` heartbeat back-date on top of `6cf37dc`,
iteration 17's `agent-inbound-queue` mapping). Clock at start: `2026-08-18T05:12:08+01:00`, tree clean
apart from the carried-forward `spec/` and `hub/seed_taste_doc.py` scratch.

`next_action` pointed at continuing the 16.2 mapping one delta spec at a time; picked
`agent-conversation-timeline`, next on the six-item list iteration 17 left behind.

Read `openspec/changes/2026-07-30-hub-native-experience/specs/agent-conversation-timeline/spec.md` in
full (158 lines, seven requirements: one timeline with no separate inbox; typed entries instead of
uniform bubbles; stable per-agent identity color; peer messages tinted with the other agent's color;
queued entries visible before delivery with a hop-budget explanation; undelivered entries
withdrawable; timeline built from recorded association, not timestamp proximity). No current spec
carries this name — confirmed by listing `openspec/specs/`, not by trusting the umbrella's own
"absent under that name" list.

Grepped `timeline`, `agent color`, `identity color`, `undelivered`, `withdraw`, `fold`, `collapse`,
`typed entr`, `conversation bubble`, `color`, `tint`, `clipped`, `truncat` across all current specs to
find where the content landed, rather than guessing from one file. It scattered across
`agent-conversation-workspace` (most of it), `agent-stream-events` (typed entries, tool-activity
grouping), `local-project-workspace` and `operator-agent-creation` (identity color).

**Five of seven requirements confirmed shipped and adequately documented**, checked against both
current spec prose and live code:
- No separate inbox / peer traffic inline: `agent-conversation-workspace/spec.md:174` ("no *Agents*
  destination and no *Messages* destination") — re-grepped and confirmed the line still reads that
  way before citing it.
- Typed entries, intermediate work collapsible: `agent-stream-events/spec.md:238-273` (tool activity
  grouped into a collapsible block); confirmed live in `AgentTimeline.tsx`, which renders
  `operator_input`, `inbound_peer`, `outbound_peer`, tool-activity, and `ResultCard` entries through
  entirely distinct branches.
- Queued-visible / hop-budget explanation: `agent-conversation-workspace/spec.md:181-204,440-443`,
  deferring to `agent-tool-surface`'s hop-budget requirement per iteration 17's own note; confirmed
  live at `AgentTimeline.tsx:193,197` — "Autonomous continuation paused ... reached the hop budget.
  They'll be delivered with your next message," near-verbatim to the delta's own scenario language.
  Re-grepped the exact line numbers against the live file before citing them.
- Undelivered entries withdrawable: `agent-conversation-workspace/spec.md:426-443` ("withdraw" named
  four times across the requirement and its scenarios).
- Attribution recorded, not inferred: `agent-conversation-workspace/spec.md:79`, a verbatim match —
  "neither provider session matching nor timestamp proximity determines membership."

**Two requirements are shipped and verified live in code, but have zero requirement text anywhere in
the current 31 specs — a documentation gap distinct from the previous two passes' findings (renamed
content, superseded content); this is the first *undocumented* content found in this mapping.**
- Peer messages tinted with the sending/receiving agent's color: grepped `tint`,
  `sending agent's color`, `recipient.*color` across every current spec — nothing. Live at
  `AgentTimeline.tsx:678-698`: `colorByName.get(entry.participant)` applied as a background tint on
  inbound peer entries and a left-border accent on outbound ones, matching the delta's sender/receiver
  split exactly.
- Clipped content is signalled: grepped `clipped`, `truncat`, `exceeds.*height` — the only truncation
  requirements found are for conversation titles and composer option labels, an unrelated concern.
  Live at `AgentTimeline.tsx:534-563`: `ResultCard` caps height at 96px past a 240-character threshold
  and renders a gradient "Show more" button that lifts the cap — realizing both the delta's
  "structured results as a distinct surface" and "clipped content is signalled" scenarios in one
  component, neither ever written into `openspec/specs/`.

**The identity-color requirement was narrowed when carried forward, not lost.**
`local-project-workspace/spec.md:223-232` and `operator-agent-creation/spec.md:20` carry the
requirement's outcome (consistent across surfaces, always paired with the name) but drop three
specifics the delta stated explicitly: stability across restart/rename, non-derivation from the
agent's name, and distinct colors until the palette is exhausted. Verified all three are still true
directly in `hub/hub/agent_colors.py` rather than trusting its own docstring: `color_index` is a
persisted column on the `Agent` row (survives restart/rename because it's database state), assignment
is `func.max(Agent.color_index) + 1` per project (monotonic, no gap-reuse, no two concurrently
registered agents share a color). No UI test exercises restart/rename stability or non-derivation
directly — grepped `restart`/`rename`/`derive`/`hash` in `agentColorSurfaces.test.tsx` and
`agentColors.test.ts`, no matches — so this is spec-prose thinning plus a light test gap, not a
behavior gap.

**What was written, not implemented.** One dated note added under 16.2 in
`openspec/changes/2026-07-30-hub-native-experience/tasks.md` (the only file touched this iteration),
recording all seven requirements and where each landed, the two live-but-undocumented findings with
file:line evidence, the color requirement's narrowed prose versus its still-true implementation, and
an updated tally — three of the eight remaining unmapped specs now done (`agent-composer`,
`agent-inbound-queue`, `agent-conversation-timeline`), five left (`agent-identity-and-skills`,
`hub-interface-feel`, `hub-native-runtime`, `hub-visual-language`, plus re-confirming
`agent-tool-surface`).

No checkbox ticked, no code changed, no archiving attempted — consistent with the file's own
reconciliation rule and `decisions_for_user` D1 in `STATE.json`.

**Verified before committing:** `git status --short` showed only the one intended file modified, plus
the carried-forward `spec/` and `hub/seed_taste_doc.py` scratch (`git diff --stat`: 66 insertions, one
file). Re-checked every cited line number against the live files with a fresh grep immediately before
writing this log entry, not carried over from the earlier exploration grep. Did not run
`openspec validate` — same reasoning as iterations 16 and 17: `tasks.md` is prose/checklist, outside
that validator's schema-checked scope.

**Tree state before commit:** `openspec/changes/2026-07-30-hub-native-experience/tasks.md` modified (1
new note, 66 lines); `.claude/autonomous/STATE.json` updated (iteration, heartbeat, Q11 done_note,
next_action); `spec/` and `hub/seed_taste_doc.py` (prior-session scratch) untouched, staged nothing
from them.

**Queue status:** Q1–Q10 done. Q11 — roadmap #7 stays parked (three failure modes on record); roadmap
#8 now has three of eight remaining delta-spec mappings done (`agent-composer`,
`agent-inbound-queue`, `agent-conversation-timeline`), with five specs plus a re-check of
`agent-tool-surface` still listed in the 16.2 note for whoever continues it. Runway to `stop_at`
(2026-08-18T08:00+01:00) is roughly 2h45m.

## Iteration 19 — Q11/roadmap #8: fourth 16.2 requirement-level mapping slice (`agent-identity-and-skills`)

**Timestamp:** 2026-08-18T05:33+01:00. Branch and `git log` matched `STATE.json` exactly at start
(HEAD `c702f34`, iteration 18 recorded). Runway to `stop_at` (2026-08-18T08:00+01:00) was roughly
2h30m.

Continued the `openspec/changes/2026-07-30-hub-native-experience` umbrella's 16.2 requirement-level
mapping with the fourth of nine still-unmapped delta specs, `agent-identity-and-skills`. No current
spec carries that name. Read the full 222-line delta spec first — ten requirements: runner reuse and
identity separation, unique names, no-persona creation, charter-as-boundary (not persona), skills as
invocable capability, agent templates, live roster, single-agent no-overhead, budgeted agent-request
with template approval, and an inspectable behaviour-precedence order.

Grepped `persona`, `template`, `skill`, `roster`, `budget`, `scope`, and `precedence` across all 31
current specs to find where each requirement landed, rather than trusting the umbrella's own
pointer — the same method as the prior three passes. This pass surfaced substantially more
divergence than `agent-composer`, `agent-inbound-queue`, and `agent-conversation-timeline`
combined: those three found renames, supersessions, and undocumented-but-shipped content; this one
found three requirements that were **never built** as the delta described, one that was **reversed**
by a later decision, and one built **more crudely** than specified — a different and sharper category
of finding than anything the prior three passes reported.

**Four of ten requirements confirmed shipped and adequately documented**, re-checked against live
code immediately before citing: unique names refused on duplicate
(`operator-agent-creation/spec.md:39-43`, live in `hub/hub/api/v1/agents.py:1386-1391`); no
persona/job-title required at creation or configurable afterward
(`operator-agent-creation/spec.md:11-12`, `agent-configuration/spec.md:295-296,303-306`); charter
defines behaviour with an unbound agent staying fully usable (`agent-charter/spec.md:56-71`); a live
roster supplied every turn, confirmed freshly queried per turn rather than cached at
`hub/hub/api/v1/agents.py:1074-1077` (`agent-context-onboarding/spec.md:34,42-45`).

**One requirement is shipped and verified live but has zero requirement text anywhere in the current
31 specs** — the same undocumented-but-shipped pattern iteration 18 found twice for
`agent-conversation-timeline`: a single-agent project renders no `### Team` section at all
(`hub/hub/api/v1/agents.py:1238-1246`), with the code's own comment naming and rejecting the removed
alternative (an earlier `else` branch that printed "No other agents are registered" on every
single-agent turn). Grepped `single.agent`, `no.*roster`, `collaboration protocol` across every
current spec first — nothing states this.

**Three requirements were never built as the delta described**, confirmed by grepping the actual
Python source, not just the specs:

- *Skills.* Grepped `class Skill`, `invoke_skill`, `skill_id` across `hub/hub/` — no matches. The
  only "skill" concept in the shipped product is the composer's `@`-mention autocomplete over a
  project's `.claude/skills/` directory (`agent-composer/spec.md:80-94`) — a file-reference
  convenience for whatever the runner's own CLI supports, not a Hub-modelled, charter-independent
  invocable capability. The delta's scenarios about a skill not widening scope and default skills not
  precluding others have nothing in the product to be true or false of.
- *Agent templates.* Grepped `AgentTemplate`, `agent_template` across `hub/hub/` — no matches. What
  `request_agent` (`hub/hub/api/v1/agents.py:1348-1466`, MCP tool at `hub/hub/mcp_server.py:491`)
  reads as a "template" is `session_data.get("agents", {})` (`agents.py:1377-1379`) — a dict keyed by
  name inside the legacy synced-session blob. `agent-context-onboarding/spec.md:30-32` states that
  synced session state "MAY continue to be read... provided it never determines... what work it is
  permitted to do." Whether an agent-creation request is fulfilled at all is gated on a name existing
  in that legacy dict (`agents.py:1379-1384`, refused with 400 if absent) — a direct contradiction
  between two *current* specs' own terms, found by reading the code behind both rather than either
  spec's prose alone.
- *Inspectable behaviour precedence.* Grepped `precedence`, `more specific`, `inspectable` across all
  current specs — every hit is unrelated (`spec-document-authority`'s charter-independent authority
  statement, `requirement-traceability`'s coverage-state ranking, `run-task-binding`'s
  conversation-rebind rule). No current spec states an ordering among project instructions, charter,
  and task acceptance criteria, or exposes the composition for inspection. `agents.py` does compose
  them in one fixed sequence — re-read end to end at :1081-1326 to confirm — but nothing states this
  is a conflict-resolving precedence rule.

**One requirement is implemented more crudely than specified, not absent.** The agent-request budget
gate is real (`agent-tool-surface/spec.md:67-78`, live at `agents.py:1396-1403`), but the delta's
finer distinction — a within-budget, pre-approved-template request auto-fulfils, while an
over-budget or unapproved-template request "SHALL be presented to the operator as a decision awaiting
response" — was not built. Both refusal paths (`agents.py:1381-1384` unknown template,
`:1396-1403` budget exhausted) raise a synchronous `HTTPException` the requesting agent simply sees
as a failed call; there is no pending-decision record for the operator to later resolve. The
"approved for automatic instantiation" distinction cannot exist either, since there is no template
record to carry that flag.

**One requirement was reversed, not merely left undocumented.** The delta: "A runner SHALL be
reusable by any number of agents across any number of projects." The current spec, unambiguous:
`runner-registry/spec.md:10-14`, "The Hub SHALL persist runner definitions as **project-scoped**
database rows." This reads as a considered later decision — narrowing a runner to one project is a
coherent design choice consistent with the rest of `runner-registry` (project-scoped seeding,
project-scoped binding) — rather than drift, and is called out distinctly in the written note for
that reason: it is the first finding across four specs and three iterations of this mapping that
looks deliberate rather than accidental.

**What was written, not implemented.** One dated note added under 16.2 in
`openspec/changes/2026-07-30-hub-native-experience/tasks.md` (the only file touched this iteration),
recording all ten requirements, the four shipped-and-documented, the one shipped-but-undocumented,
the three never-built, the one built-more-crudely, and the one reversed, each with file:line
evidence, and an updated tally — four of the nine remaining unmapped specs now done
(`agent-composer`, `agent-inbound-queue`, `agent-conversation-timeline`, `agent-identity-and-skills`),
four remain (`hub-interface-feel`, `hub-native-runtime`, `hub-visual-language`, plus re-confirming
`agent-tool-surface`).

No checkbox ticked, no code changed, no archiving attempted — consistent with the file's own
reconciliation rule and `decisions_for_user` D1 in `STATE.json`.

**Verified before committing:** `git status --short` showed only the one intended file modified,
plus the carried-forward `spec/` and `hub/seed_taste_doc.py` scratch (`git diff --stat`: 86
insertions, one file). Every cited line number was re-grepped against the live file immediately
before writing this entry, not carried over from earlier exploration. `openspec validate` was not
run, for the same reason as iterations 16–18: `tasks.md` is prose/checklist, outside that
validator's schema-checked scope.

**Tree state before commit:** `openspec/changes/2026-07-30-hub-native-experience/tasks.md` modified
(1 new note, 86 lines); `.claude/autonomous/STATE.json` updated (iteration, heartbeat, Q11 done_note,
next_action); `spec/` and `hub/seed_taste_doc.py` (prior-session scratch) untouched, staged nothing
from them.

**Queue status:** Q1–Q10 done. Q11 — roadmap #7 stays parked (three failure modes on record);
roadmap #8 now has four of nine remaining delta-spec mappings done, four left, listed in the 16.2
note for whoever continues it. This iteration's findings (skills and agent templates never built as
specified, budget-request escalation built more crudely, cross-project runner reuse reversed) are
concrete enough that the operator may want them surfaced directly rather than only left inside the
umbrella's own tasks file — noted here for the morning report. Runway to `stop_at`
(2026-08-18T08:00+01:00) is roughly 2h15m.

---

## Iteration 20 — fifth 16.2 requirement-level mapping: `hub-interface-feel`

Continued Q11/roadmap #8, the same pattern iterations 16–19 established: read a delta spec from
`openspec/changes/2026-07-30-hub-native-experience/specs/`, work out where its concepts live in the
current 31 `openspec/specs/`, verify any code-level claim against the live tree, write a dated note,
tick nothing. This pass picked `hub-interface-feel` — nine requirements, none renamed content from a
current spec of a similar name (no current spec is called that).

**Why this one needed a different method than iterations 16–19.** The prior four passes each found
their delta's requirements scattered across current specs by *content* — grep the delta's nouns
(`skill`, `precedence`, `hop budget`) across `openspec/specs/` and something usually turned up, even
if renamed or superseded. Grepping `hub-interface-feel`'s vocabulary the same way (`corner radius`,
`elevation`, `touch target`, `tabular`, `variable font`, `subordinate`) returned **nothing** for six
of nine requirements. That is not the same finding as iterations 18–19's "shipped but undocumented"
— those still involved reading a spec's neighbourhood and recognising the shipped behaviour under
different words. Here there was no neighbourhood to read; the delta describes design-token mechanics
(CSS custom properties, a `cva()` button variant map, font imports) that a prose requirements
document doesn't naturally host at all. So this pass changed method mid-mapping: for every
requirement that grepped to nothing in `openspec/specs/`, it went straight to
`hub/ui/src/index.css`, `hub/ui/src/components/ui/buttonVariants.ts`, and `hub/ui/src/api/*.ts` and
checked the requirement against the code directly, the same standard iterations 18–19 already held
themselves to before citing a line number — just applied first instead of last, because the spec-side
search wasn't going to get there.

**Findings, by requirement (nine total):**

1. **Interactive state feedback** (hover/pressed/focus/reduced-motion/shared tokens) — already
   well-documented. `hub-interaction-feedback/spec.md` (split from `hub-workspace-shell` by
   `2026-08-04-hub-contextual-navigation`) covers this near-verbatim, including its own "gaining
   emphasis never moves anything" and reduced-motion scenarios. No gap.

2. **Single icon system, no blocking font/stylesheet** — documented, but narrower than the delta.
   `hub-workspace-shell/spec.md:83-106` states the Lucide-only rule for seven named project-rail
   actions specifically, not the interface globally. The global claim is true in code —
   `Icon.tsx:67-77`'s own comment names exactly what the requirement worries about and says it was
   fixed: "This previously wrapped the Material Symbols Rounded variable font, loaded from a
   third-party stylesheet with `display=block` — which held every icon invisible until that network
   request completed. Icons are now SVG components bundled with the app" — but no current spec states
   this for the interface as a whole, only for the rail.

3. **Typography self-hosted and variable, tabular figures** — shipped, zero spec text. `index.css:1-5`
   states the intent as a comment ("Self-hosted variable fonts... Replaces the former
   fonts.googleapis.com stylesheets") and `@fontsource-variable/dm-sans` is a genuine variable font
   for UI text; `@fontsource/jetbrains-mono` is static-weight, which the requirement's own wording
   permits — only "the UI typeface" is required to be variable, not the monospace one. `tabular-nums`
   is applied at `:233-235` with a matching comment and used at two live-number call sites (`:605,
   :613`).

4. **Controls change appearance without changing layout** — shipped, zero spec text beyond the
   general principle in finding 1. `buttonVariants.ts:6-19`'s own docstring names the mechanism as
   deliberate: `border border-transparent` always present in the base class (no variant can opt out),
   padding subtracts the border thickness so label insets read identical regardless of visibility.

5. **Controls express press physically** — shipped, zero spec text, one scenario a partial match not
   a clean one. `buttonVariants.ts:44-52`'s `primary` variant: `inset_0_1px_0_var(--lift-hi)` at rest,
   `active:shadow-[inset_0_1px_0_var(--press-lo)]` on press — the top-edge highlight is replaced by an
   inset shadow while pressed, exactly as specified; `disabled:opacity-[0.64] disabled:shadow-none
   disabled:pointer-events-none` in the shared base class removes elevation and reactivity together
   for disabled controls. The "tinted, not neutral" elevation scenario only partially holds:
   `--lift-hi`/`--press-lo` (`index.css:53-54,129-130`) are fixed neutral white/black alpha values,
   identical across `primary`, `ghost`, `outline`, and `destructive` — not a per-colour token.
   Composited over each variant's own background colour they read as a tint of that background rather
   than plain grey, so the visible effect happens, but by alpha-blending accident rather than a
   mechanism built to be "tinted by that colour."

6. **Corner radius distinguishes chrome from content** — shipped, zero spec text. `index.css:168-176`:
   "Radius and motion are mode-independent. One base, derived steps" — `--radius: 10px` with every
   other step a `calc()` off it, and a separately-declared `--radius-content: 24px` ("Self-contained
   results are markedly softer than chrome") applied to result cards while control radii stay in an
   8-14px band. Not spot-checked this pass: the nested-concentric-corner scenario (an inset
   decoration's radius reduced by the separating thickness) — flagged rather than assumed true.

7. **Iconography subordinate to its label** — shipped, zero spec text.
   `buttonVariants.ts:34`, `"[&_svg:not([class*='opacity-'])]:opacity-80"` — every icon inside a
   button defaults to 80% opacity, and the selector explicitly spares any icon that already carries
   its own `opacity-*` class, matching the requirement's "deliberate emphasis is preserved" scenario
   precisely.

8. **Pointer targets adequate on coarse pointers** — shipped, zero spec text.
   `buttonVariants.ts:36-40`: a `pointer-coarse:after` pseudo-element sized `min-h-11 min-w-11` (44px,
   the platform minimum) centered on the control, gated on `pointer-coarse` media state so the
   control's own box — and its fine-pointer visual size — is untouched. Both scenarios match exactly.

9. **Live state from the event stream, not polling** — the one requirement this pass found narrowed
   by a considered, written-down decision rather than left undocumented or dropped. The delta is
   absolute: "The interface MUST NOT poll REST endpoints on a fixed interval to discover state that
   the event stream already reports." Grepped `refetchInterval` across every file in
   `hub/ui/src/api/` and `hooks/`: exactly three hits, no others —
   `usePendingPermissionRequests` (`api/permissions.ts:21-51`, 3s), `useQuestions`
   (`api/questions.ts:39-49`, 3s), `usePendingUnaskedQuestions` (`api/unaskedQuestions.ts:16-40`, 5s).
   All three already invalidate on SSE and layer a fixed-interval refetch *on top*, and each carries
   its own comment explaining why: a permission request blocks a running agent
   ("arriving late is the same as not arriving, and a dropped event would leave an agent waiting for a
   card that never appeared"), a blocking question the same way, and an unasked-question notice
   because "a dropped event would leave the operator looking at a finished conversation with no sign
   that the agent is waiting on them." Every other query hook checked (`agents.ts`, `tasks.ts`,
   `messages.ts`, `agentChat.ts`) carries no `refetchInterval` at all — the delta's rule holds
   everywhere except these three, and all three read the same way iteration 19's runner
   cross-project-reuse reversal did: a later, considered decision with its rationale left in the code,
   not drift.

**What was written, not implemented.** One dated note added under 16.2 in
`openspec/changes/2026-07-30-hub-native-experience/tasks.md` (the only file touched this iteration,
96 lines), recording all nine requirements — one already documented, one documented-but-narrower,
five shipped-with-zero-spec-text, one deliberately narrowed with its own rationale — with file:line
evidence and an updated tally. Five of the nine remaining unmapped specs are now done
(`agent-composer`, `agent-inbound-queue`, `agent-conversation-timeline`, `agent-identity-and-skills`,
`hub-interface-feel`); three remain (`hub-native-runtime`, `hub-visual-language`, plus re-confirming
`agent-tool-surface`).

No checkbox ticked, no code changed, no archiving attempted — consistent with the file's own
reconciliation rule and `decisions_for_user` D1 in `STATE.json`.

**Verified before committing:** `git diff --stat` on the touched file: 96 insertions, one file.
`git status --short` showed only that plus the carried-forward `spec/` and `hub/seed_taste_doc.py`
scratch, staged nothing from them. Every cited line number (`index.css`, `buttonVariants.ts`,
`Icon.tsx`, the three API hook files) was grepped and read live immediately before writing this
entry — none carried over from memory of an earlier session. `refetchInterval` grep was run against
the whole `api/` and `hooks/` directories, not just the three files cited, specifically to be able to
state "no others" with evidence rather than by omission. `openspec validate` was not run, for the
same reason as iterations 16–19: `tasks.md` is prose/checklist, outside that validator's
schema-checked scope.

**Tree state before commit:** `openspec/changes/2026-07-30-hub-native-experience/tasks.md` modified
(1 new note, 96 lines); `.claude/autonomous/STATE.json` updated (iteration, heartbeat, Q11 done_note,
next_action); `spec/` and `hub/seed_taste_doc.py` (prior-session scratch) untouched.

**Queue status:** Q1–Q10 done. Q11 — roadmap #7 stays parked (three failure modes on record);
roadmap #8 now has five of nine remaining delta-spec mappings done, three left
(`hub-native-runtime`, `hub-visual-language`, `agent-tool-surface` re-check), listed in the 16.2 note
for whoever continues it. This iteration's polling-vs-event-stream finding (three query hooks keep a
fixed refetch interval on purpose alongside SSE) is a second instance of the same "considered later
decision, not drift" pattern iteration 19 found once — worth surfacing next to that one in the
morning report rather than treating either as an isolated curiosity. Runway to `stop_at`
(2026-08-18T08:00+01:00) is roughly 2h15m.

## Iteration 21 — sixth 16.2 requirement-level mapping: `hub-native-runtime`

Continued Q11/roadmap #8, same pattern as iterations 16–20. Picked `hub-native-runtime` — eight
requirements, no current spec carries that name. Delegated the research (read the delta spec in
full, grep all 31 current specs by concept rather than name, check live code wherever spec prose
came up empty — following iteration 20's own method, which needed it for `hub-interface-feel`) to a
background research agent rather than doing every grep and file read inline, since the delta spans
process lifecycle, worktree isolation, run reconciliation, token accounting, and the scheduler —
five genuinely separate subsystems. Read the agent's report in full, then personally spot-checked
its four most load-bearing citations before writing anything into `tasks.md`: `WorktreesPanel.tsx`'s
static "No worktree activity yet." stub and the absence of any `useWorktreeConflicts` hook or
`worktrees/conflicts` caller anywhere in `hub/ui/src/` (grepped myself — zero hits, confirming an
operator genuinely cannot see a detected conflict today), `worktrees.py`'s `detect_conflicts`
docstring citing this exact umbrella delta scenario by name, and the `usage_accounting.py` /
`run_reconciliation.py` line citations. All four held up exactly as reported.

**Findings, by requirement (eight total):**

1. **Turns accounted in tokens, currency reported as derived** — shipped and cleanly documented.
   `usage-accounting/spec.md` is an expanded, near-verbatim restatement, checked against
   `hub/hub/usage_accounting.py:39,170,176` directly. The cleanest, most fully-reconciled requirement
   found across all six passes so far (iterations 17–21) — no gap, no drift, no crude
   implementation.

2. **Hub runs natively, owns process lifecycle, container mode stays non-default** — shipped and
   documented for the installation half (`app-lifecycle/spec.md:10-14`, `local-project-workspace/
   spec.md:256-270`). Process-lifecycle ownership itself (spawn/output/session/interruption/exit)
   has no requirement text of its own anywhere — only a code comment,
   `hub/hub/pty_runner.py:3-4`: "Decision 1 makes the Hub own agent execution directly... its server
   spawns the agent, owns the PTY."

3. **Trigger is direct, no message-polling, no text-encoded session directive** — shipped, zero spec
   text, but `agent_trigger.py:9-12`'s own module docstring states this almost verbatim. The delta's
   binary started/failed outcome model was deliberately widened to a third state, `queued`, once
   conversations could compete for one agent — `agent-conversation-workspace/spec.md:36,190-192`
   states this as intentional, consistent with the widening iteration 17 already found for
   `agent-inbound-queue`. Not a violation of "no speculative status" — `queued` is itself definite.

4. **Manual connection ceremony removed** — shipped, zero spec text anywhere in the current 31.
   True in code: `launchability.py:115-155` resolves provider credentials inside the Hub process
   before spawn; `agent_trigger.py:371-372` feeds the session id in as a typed field, no operator
   entry. Apparently never written up once the legacy CLI ceremony was deleted.

5. **Agent output streams live via SSE, no client poll** — mechanism documented
   (`agent-stream-events/spec.md`), the explicit anti-polling half of the rule itself is not, verified
   true in code rather than assumed: `hub/ui/src/api/agents.ts` has three `useSSE` call sites and no
   `refetchInterval`, checked against iteration 20's own three named exceptions.

6. **Interrupted runs reconciled on restart; entries returned undelivered; no orphaned process on
   stop** — shipped, zero spec text for the mechanism itself; only its downstream consequence has
   prose (`run-task-binding/spec.md:145-189` assumes reconciliation happens without documenting how).
   Read `hub/hub/run_reconciliation.py` in full: `reconcile_interrupted_runs()` runs once from
   `main.py:280`'s `lifespan()` startup, marks any `"running"` row with a dead/absent pid as
   `"interrupted"`, and returns delivered-but-uncommitted entries to the queue — plus a refinement
   the delta didn't anticipate, a per-entry delivery-attempt cap that gives up rather than requeuing
   forever. `terminate_all_active_runs()` force-terminates every tracked process on Hub stop,
   deliberately not touching `Run` row status itself (its own docstring explains why — a single-owner
   decision, not a gap). The clearest case this pass of a load-bearing startup routine with zero
   requirement-level coverage.

7. **Watchdog limited to time-based duties** — shipped, zero spec text. `src/agentweave/watchdog.py`
   no longer exists; remaining "watchdog" references in `hub/hub/` are code comments citing the
   deleted mechanism (`scheduler.py:41-42,287,304-307`). `JobScheduler` fires scheduled jobs through
   the same direct-execution path a manual trigger uses.

8. **Agents write in isolated checkouts; divergent changes surface as a conflict** — the one genuine,
   actionable product gap found across all six passes of this reconciliation, not a documentation gap.
   Isolation and release are shipped and documented cleanly (`operator-agent-creation/
   spec.md:63-72,79-91`, `worktrees.py:364-388`). But the conflict-detection backend
   (`detect_conflicts`, `worktrees.py:447-460`, and `GET /api/v1/projects/{id}/worktrees/conflicts`)
   is fully built, even cites this exact umbrella delta scenario by name in its own docstring
   ("the 'interface identifies which agents diverged' half of hub-native-runtime's 'Divergent changes
   surface as a conflict' scenario"), and has **no UI consumer anywhere** —
   `WorktreesPanel.tsx` unconditionally renders "No worktree activity yet." and never calls the
   endpoint; `workspace.ts` exposes only the single-agent `useAgentWorkspace` hook. An operator has
   no way to see a detected conflict today. Recorded as IMPLEMENTED MORE CRUDELY THAN SPECIFIED, same
   register as iteration 19's synchronous-`HTTPException`-instead-of-pending-decision finding.

**What was written, not implemented.** One dated note added under 16.2 in
`openspec/changes/2026-07-30-hub-native-experience/tasks.md` (113 lines, the only file touched this
iteration) — six of the nine remaining unmapped specs now done (`agent-composer`,
`agent-inbound-queue`, `agent-conversation-timeline`, `agent-identity-and-skills`,
`hub-interface-feel`, `hub-native-runtime`); two remain (`hub-visual-language`, plus re-confirming
`agent-tool-surface`). The worktree-conflict UI gap is not fixed — 16.2 is a mapping exercise, not
implementation, per the file's own reconciliation rule and `decisions_for_user` D1 — but it is worth
surfacing to the operator as a shippable follow-up, distinct from a documentation debt, since it's
the first genuine product gap this reconciliation pass has found rather than a prose omission.

No checkbox ticked, no code changed, no archiving attempted.

**Verified before committing:** fixed one typo the research introduced while drafting the note
(`CLAAUDE.md` → `CLAUDE.md`). Personally re-ran and read, not trusted from the agent's report alone:
`grep -n "No worktree activity" hub/ui/src/components/environment/WorktreesPanel.tsx` and
`grep -rn "useWorktreeConflicts\|worktrees/conflicts" hub/ui/src/` (zero hits, confirming the gap),
`sed -n` over `worktrees.py:1-10,445-452` (confirmed the docstring citation), and grep over
`usage_accounting.py` and `run_reconciliation.py` for the four cited lines/functions — all four
checks matched the report exactly. `git diff --stat` showed exactly the one file, 113 insertions.
`git status --short` showed only that plus the carried-forward `spec/` and `hub/seed_taste_doc.py`
scratch, staged nothing from them.

**Tree state before commit:** `openspec/changes/2026-07-30-hub-native-experience/tasks.md` modified
(1 new note, 113 lines); `.claude/autonomous/STATE.json` updated (iteration, heartbeat, Q11
done_note, next_action); `spec/` and `hub/seed_taste_doc.py` (prior-session scratch) untouched.

**Queue status:** Q1–Q10 done. Q11 — roadmap #7 stays parked (three failure modes on record);
roadmap #8 now has six of nine remaining delta-spec mappings done, two left (`hub-visual-language`,
`agent-tool-surface` re-check), listed in the 16.2 note for whoever continues it. Runway to `stop_at`
(2026-08-18T08:00+01:00) is roughly 1h55m.

## Iteration 22 — seventh 16.2 requirement-level mapping: `hub-visual-language`

Continued Q11/roadmap #8, same pattern as iterations 16-21. Picked `hub-visual-language` — six
requirements, no current spec carries that name. Did the research inline this time rather than
delegating: six requirements over one subsystem (the visual shell) is small enough not to need a
background agent, unlike iteration 21's five-subsystem `hub-native-runtime`. Grepped all 31 current
specs by concept (indigo/ink plane, dividing line, resiz, scrollbar, navigation region, agent
colour), then read live code wherever spec prose came up empty: `PaneResizer.tsx`, `App.tsx`,
`ConversationView.tsx`, `hub/ui/src/index.css`.

**Six requirements, five findings plus one already-closed:**

1. **Navigation lists live entities; project views reached in content area** — already reconciled,
   and not by this pass. The delta file itself carries a "Superseded in part by
   `2026-08-04-hub-contextual-navigation`" note, written directly into the requirement text rather
   than left for a `tasks.md` note to catch. `git log` on the file confirmed the note is dated the
   same day as that change (commit `8526bea`), and it points at
   `hub-workspace-shell/spec.md:387`'s navigation-region-carries-whatever-is-entered requirement.
   Checked it is still current, not stale: nothing since has moved configuration back into a
   content-area tab or column. No action taken; flagged in the `tasks.md` note so the next pass does
   not spend time re-deriving what a previous change already settled.

2. **The interface presents related navigation and content planes** (the delta's indigo rail / ink
   content plane) — a considered, documented supersession, not drift. `hub-workspace-shell/
   spec.md:15-18` states outright that the mock's palette is explicitly superseded and the running
   application uses the neutral graphite ramp instead. The requirement at `:49-57` says in its own
   text that it supersedes the subsequent direction that required the mock's indigo and ink fills.
   Same register as iteration 19's runner cross-project reversal and iteration 20's SSE-polling
   exceptions — a later decision recorded in the spec's own words, not an omission.

3. **Two adjacent regions are separated by one signal, not two** — documented, but folded into the
   same requirement as #2 above rather than standing alone, and scoped narrower than the delta asked.
   The delta states this as a general rule for any two adjacent regions; `hub-workspace-shell/
   spec.md:49-63` states it only for the nav/content boundary (boundary stays subtle, MUST NOT
   combine strong fill contrast with a strong dividing line, remains less prominent than an
   interactive control outline — a near-verbatim match to the delta's two scenarios, but scoped to
   one boundary). Checked whether the general principle actually holds elsewhere in code before
   calling this a gap: `PaneResizer.tsx:30-32`'s own comment states the panes share one ground plane
   with a single separation signal, and the component is used for both the nav/content boundary
   (`App.tsx:482`) and the conversation/spec-panel boundary (`ConversationView.tsx:263`). The
   practice is general; only the one instance is specified as a requirement. Documented-but-narrower,
   the same pattern iteration 20 found for the single-icon-system requirement.

4. **An agent's identity colour is applied consistently wherever it appears** — cleanly documented,
   no narrowing. `local-project-workspace/spec.md:223-232`'s agent-identity-colour requirement
   matches almost word for word, including the colour-never-stands-alone half (colour must always be
   accompanied by the agent name). Unlike iteration 18's finding for the same underlying mechanism
   inside `agent-conversation-timeline` (which asked for three more specifics — stability across
   restart/rename, non-derivation from name, distinct-until-exhausted — that this delta's simpler
   wording never asked for), there is nothing left over to narrow here.

5. **Primary panes are resizable and the choice is remembered** — shipped, zero requirement text
   anywhere in the current 31. Only a passing mention survives at all: "rail resizing" in
   `hub-workspace-shell/spec.md:33`'s scenario list for an unrelated requirement (visual alignment to
   the mock), with no dedicated requirement for drag affordance, clamping, persistence, or reset. All
   four are shipped and read directly rather than assumed from the component's docstring:
   `PaneResizer.tsx:38-113` — an 11px hit target around a 1px line (`:125`) that only changes colour
   on hover/focus so nothing reflows while aiming (`:136-142`), pointer-capture dragging clamped to
   min/max (`:50-53,79-81`), keyboard resizing with arrow keys (`:101-113`), and reset-to-default on
   double-click or Home (`:112,132`). Persistence: `App.tsx:72-96` reads/writes `SIDEBAR_WIDTH_KEY`
   in localStorage, clamping the stored value against `SIDEBAR_MIN_WIDTH`/`SIDEBAR_MAX_WIDTH` on read
   and falling back to the default gracefully if it is missing or invalid.

6. **Scrollbars are unobtrusive** — shipped exactly as specified, zero requirement text anywhere.
   Grepped `scrollbar` across all 31 specs: zero hits. `hub/ui/src/index.css:238-259` sets
   `scrollbar-width: thin` with a transparent track for Firefox, and for WebKit hides the track,
   corner, and stepper buttons outright while rendering only an inset, rounded thumb (transparent
   border plus content-box background-clip, so the border reads as inset padding rather than a
   visible ring) that strengthens on hover.

**What was written, not implemented.** One dated note added under 16.2 in
`openspec/changes/2026-07-30-hub-native-experience/tasks.md` (70 lines, the only file touched this
iteration) — seven of the nine remaining unmapped specs now done (`agent-composer`,
`agent-inbound-queue`, `agent-conversation-timeline`, `agent-identity-and-skills`,
`hub-interface-feel`, `hub-native-runtime`, `hub-visual-language`). One remains: re-confirming
`agent-tool-surface` at requirement level — the 2026-08-03 partial note only confirmed it survives by
name, the way iteration 18's note found `agent-composer` needed a real requirement-level look despite
also surviving by name (and found a genuine drift there). No checkbox ticked, no code changed, no
archiving attempted, per the file's own reconciliation rule and `decisions_for_user` D1.

**Verified before committing:** re-read every cited line directly rather than trusting the earlier
grep pass alone — `hub-workspace-shell/spec.md` lines 1-90 in full (not just the matched lines, to
catch the supersession language in context), `local-project-workspace/spec.md:223-232`,
`PaneResizer.tsx` in full (145 lines), the `App.tsx` sidebar-width block (lines 60-104), and
`index.css` lines 235-259. `git log -1` on the delta spec file confirmed the inline supersession
note's date (commit `8526bea`, 2026-08-04) rather than assuming it was current. `git diff --stat`
showed exactly the one file, 70 insertions. `git status --short` showed only that plus the
carried-forward `spec/` and `hub/seed_taste_doc.py` scratch, staged nothing from them.

**Tree state before commit:** `openspec/changes/2026-07-30-hub-native-experience/tasks.md` modified
(1 new note, 70 lines); `.claude/autonomous/STATE.json` updated (iteration, heartbeat, Q11 done_note,
next_action); `spec/` and `hub/seed_taste_doc.py` (prior-session scratch) untouched.

**Queue status:** Q1–Q10 done. Q11 — roadmap #7 stays parked (three failure modes on record);
roadmap #8 now has seven of nine originally-unmapped delta specs mapped at requirement level, one
left (`agent-tool-surface` re-check). Once that lands, 16.2's requirement-level mapping is complete
for every delta spec under this umbrella — worth flagging to the operator that 16.2 itself may then
be close to done, though 16.1 (scenario exercise) and 16.3 (archive) are separate, larger asks that
stay the operator's call per the umbrella's own notes. Runway to `stop_at` (2026-08-18T08:00+01:00)
is roughly 1h45m.

---

## Iteration 23 (2026-08-18T06:31+01:00) — eighth and final 16.2 requirement-level mapping: `agent-tool-surface`

Closed the last item in the loop iterations 16–22 built: `agent-tool-surface` was one of the two
delta specs the 2026-08-12 note found "present under the same name" (the other, `agent-composer`,
turned out to hide a real contradiction when iteration 18 finally checked it at requirement level).
`agent-tool-surface` had never gotten that same check — only confirmed by filename, plus two prose
revisions the current spec's own preamble already names. This pass did the real check: all seven
delta requirements against the current 335-line spec (grown to 11 requirements since the delta),
and wherever spec prose was silent or the preamble made a claim, against `hub/hub/launchability.py`
and `hub/hub/api/v1/agent_trigger.py` directly, plus `git log -p` to date the code changes.

**Four requirements are a clean or self-documented match.** *Outbound intent remains available* and
*Creating agents and scheduling recurring work are governed, not free* carry over verbatim, text and
scenarios both. *The Hub supplies state; the tool surface carries intent* is revised — an
effect-only boundary replaced by a least-privilege read boundary — but the current spec's own
preamble names the reconciliation, dates it (2026-08-07), and cites its source
(`openspec/explorations/2026-08-02-product-direction.md`); scenarios unchanged. *An agent's identity
is bound by the Hub, never asserted by the agent* is revised to run-credential authentication in
place of environment-variable binding, plus a new "credential from another instance is refused"
scenario — the 2026-08-03 partial note already named and correctly cited this one
(`archive/2026-08-03-agent-capability-plane`, confirmed archived and real by directory listing).

**One requirement's stated removal held up exactly as documented.** *The tool surface is available
without a tool-protocol server* — the delta's full-capability command-based fallback. The current
spec's preamble says `2026-08-03-single-runtime` removed it because it deletes the CLI collaboration
commands it depended on. Confirmed live: `launchability.py:275-291`'s `access_path_notice`, on its
non-`mcp` branch, carries its own code comment — "No CLI equivalents are offered any more... Saying
so plainly is better than sending an agent after commands that do not exist" — and tells the agent
it has **no** tool surface at all this turn, not an equal-capability command alternative. No
qualification needed here.

**One requirement's stated removal was overclaimed, and this is the real finding of the pass.** *The
access path is chosen per runner from probed capability.* The preamble bundles this into the same
"removed... since it deletes the CLI collaboration commands they depended on" sentence as the
command fallback above. That is not what the code shows. `resolve_access_path(runner, cli,
override)` (`launchability.py:215-222`) still executes on every triggered turn —
`agent_trigger.py:474`, `access_path = resolve_access_path(runner, probe["cli"] or agent,
config.get("hub_client"))` — still resolves per runner via a capability table
(`MCP_INJECTABLE_RUNNERS`), and still honours an explicit operator override
(`config.get("hub_client")`, a direct match for the delta's own "operator MAY override" scenario).
`git log -p` on `launchability.py` pinned exactly what changed and when: at the `single-runtime`
commit itself (`c31b3df`, 2026-08-03), the function body was rewritten from
`return "mcp" if probe_mcp_registered(cli) else "cli"` to a static `MCP_INJECTABLE_RUNNERS`
membership check with the `cli` parameter explicitly discarded (`del cli`). `probe_mcp_registered`
(`launchability.py:185-212`) still exists and is still unit-tested (`test_launchability.py`), but a
repo-wide grep for its name found no caller left in `hub/hub/` outside its own tests — it is dead in
production. So the delta's "the Hub SHALL record what is actually available, not what is
theoretically supported" and its "prohibited is distinguished from unsupported" scenario are no
longer true of the code: there is no live probe left to draw that distinction, only a fixed table.
The requirement was narrowed to a static lookup, not removed, and the spec's own preamble
overstates what happened by filing it under the same "removed" sentence as the command fallback,
which really was deleted outright. Worth a correction in the current spec itself at some point, not
attempted here — this pass records findings, per the umbrella's own reconciliation rule, it does not
edit `openspec/specs/`.

**One requirement kept its title but had its scenarios swapped out from under it, not merely
narrowed.** *One tool surface, configured automatically.* The delta's two original scenarios ("tools
available without operator configuration," "only one surface exists") are absent from the current
text entirely — replaced by three newer scenarios about verifying the served surface against a
spawned subprocess rather than trusting an import, added 2026-08-13 alongside the entry-point-guard
fix. Checked whether the delta's original guarantee still holds even though its scenario text is
gone: it does. `runner_commands.py:224-236` (Claude) and `:273-292` (Codex) build `--mcp-config` /
`-c mcp_servers...` dynamically on the spawn command line per run — no config file for the operator
to edit — and a repo-wide grep for `FastMCP(` finds exactly one server, `hub/hub/mcp_server.py`.
Shipped, verified live, zero requirement text stating it — the same pattern iterations 18, 19, and
21 found repeatedly for other deltas under this umbrella, here landing inside a requirement whose
*name* survived while its *content* moved on to a different, newer concern (spawn verification
rather than configuration-free startup).

**What this closes.** All eight originally-in-scope delta specs under
`2026-07-30-hub-native-experience/specs/` are now checked at requirement level: `agent-composer`,
`agent-inbound-queue`, `agent-conversation-timeline`, `agent-identity-and-skills`,
`hub-interface-feel`, `hub-native-runtime`, `hub-visual-language`, and now `agent-tool-surface`. The
other two originally-listed delta specs, `spec-authoring` and `spec-traceability`, were never part
of this tally — they are already established elsewhere in `tasks.md` (14.18, 15.3, the 2026-08-12
note) as genuinely never built, because phase 14 was never implemented. That is a different category
from "renamed or superseded" and there is no successor content to map them into.

**16.2's per-delta-spec requirement-level mapping is complete. 16.2 itself is not ticked.** Its own
task text also requires reconciling `agent-stream-events`, `runtime-diagnostics`, and
`agent-conversation-handoff` with new behaviour, and no iteration in this run has attempted that —
per this file's own reconciliation rule a box ticks for verified behaviour, not for a decision, and
this pass did not touch those three. One dated note added under 16.2 in
`openspec/changes/2026-07-30-hub-native-experience/tasks.md` (77 lines, the only file touched this
iteration) records everything above with file:line evidence.

**Verified before committing:** re-read `openspec/specs/agent-tool-surface/spec.md` in full (335
lines) rather than trusting the earlier grep-and-skim, read the delta spec in full (173 lines),
read `launchability.py` in full (319 lines) rather than the matched lines alone, confirmed
`archive/2026-08-03-agent-capability-plane` and `archive/2026-08-03-single-runtime` both exist as
directories, and ran `git log -p --follow -- hub/hub/launchability.py` to date the `resolve_access_path`
rewrite to the `single-runtime` commit itself rather than assuming which change made it. `git diff
--stat` showed exactly the one file, 77 insertions. `git status --short` showed only that plus the
carried-forward `spec/` and `hub/seed_taste_doc.py` scratch, staged nothing from them.

**Tree state before commit:** `openspec/changes/2026-07-30-hub-native-experience/tasks.md` modified
(1 new note, 77 lines); `.claude/autonomous/STATE.json` updated (iteration, heartbeat, Q11 done_note,
next_action); `spec/` and `hub/seed_taste_doc.py` (prior-session scratch) untouched.

**Queue status:** Q1–Q10 done. Q11 — roadmap #7 stays parked (three failure modes on record);
roadmap #8's requirement-level mapping loop (iterations 16–23) is now finished for all eight
originally-in-scope delta specs. Worth flagging to the operator directly: 16.2 is not done — it
still needs the three named reconciliations — but the much larger mapping exercise that occupied
this run's last eight iterations is complete. If a next iteration continues Q11/roadmap #8, the
right next unit is one of those three reconciliations, `agent-stream-events` first (the most
load-bearing of the three, referenced by several findings across this pass and earlier ones). Runway
to `stop_at` (2026-08-18T08:00+01:00) is roughly 1h30m.

## Iteration 24 (2026-08-18T06:45+01:00) — Q11/roadmap #8, second half: `agent-stream-events` reconciliation

16.2's own task text names three specs directly — `agent-stream-events`, `runtime-diagnostics`,
`agent-conversation-handoff` — separately from the ten delta specs iterations 16–23 spent eight
iterations mapping. None of the three is one of this umbrella's ten deltas; all three are *current*
specs the 2026-08-03 `single-runtime` note already claims to have synced. 16.2's text is asking a
different question about them: does that sync still hold against what actually shipped since? This
iteration did the first of the three, `agent-stream-events`, the most load-bearing per iteration 23's
own note.

**Method, deliberately different from iterations 16–23.** There is no delta spec to diff against —
the comparison is the current spec's own 19 requirements versus live code, requirement by
requirement, the same shape those iterations used for the *delta* specs but here aimed at whether a
week-old sync (2026-08-11) is still accurate rather than whether a month-old delta ever landed.

**Every requirement checked held, exactly.** Concrete numeric and structural claims were checked
directly rather than trusted from memory of the codebase: the closed seven-kind taxonomy
(`text`/`thinking`/`tool_use`/`tool_result`/`status`/`diagnostic`/`error`) matches
`hub/hub/schemas/agents.py:11-19`'s `StreamEventKind` literal verbatim. The 64 KiB payload bound and
8 KiB tool-result bound match `hub/hub/runner_events.py:23-24`'s `MAX_PAYLOAD_BYTES` /
`MAX_TOOL_RESULT_BYTES` exactly. "Chat history preserves stream semantics" holds —
`agent_chat.py:64,162` carries `output_kind` through the projection rather than flattening to plain
content. The two newest-looking requirements in the spec text, "A turn renders in execution order"
and "Each work block carries independent state" (grouped, independently-expandable tool blocks), are
not just specified but actually implemented, confirmed by grep hits in `agentTimelineModel.ts` and
`AgentTimeline.tsx`. "Shared stream renderer" holds too, once "spec chat" was traced to what it
actually is: not a fourth component, but the same conversation view with a document attached,
rendered through the identical `AgentOutputPanel`/`AgentTimeline` path as the output panel and
activity tab — confirmed by grep, no `SpecChat`-named component exists anywhere.

**One observation recorded, explicitly not a violation.** The `diagnostic` event kind is fully wired
on the UI consumer side — `agentTimelineModel.ts:8` groups it with `status` as a result-rendered kind,
`AgentTimeline.tsx:536` treats it as error-styled — but grepping every producer site in `hub/hub/`
and `src/agentweave/stream_events.py` found `diagnostic_event()` (`stream_events.py:556`) defined and
never called, anywhere. Checked this against the only two scenarios that could require it —
"Provider adds a new event type" and "Stream line is malformed" — and both say the Hub SHALL emit a
diagnostic *or* a readable fallback. `parse_claude_line`'s malformed-JSON branch
(`runner_parsing.py:235-239`) takes the fallback path, wrapping the raw line as a `text_event`. That
is spec-compliant; the `diagnostic` kind is simply the half of an either/or that nothing currently
exercises. Worth remembering the next time diagnostics never appear in the UI's own hide-diagnostics
toggle during testing — it is not broken, it has never had a producer to be broken.

**One thing noted and deliberately left out of scope.** `git log --since=2026-08-11` on this spec's
own code (`runner_parsing.py`, `agentTimelineModel.ts`, `AgentTimeline.tsx`) turns up several real,
shipped changes since the last sync — Markdown message rendering, an edit-diff view for tool calls,
tool-call icons, and this run's own Q2 (no end-of-turn text). All of them belong to
`openspec/changes/2026-08-16-conversation-formatting-and-quick-nav`, a separate, still-open change
with its own future archive-and-sync step. They are not this umbrella's content and not evidence
against `agent-stream-events` today — noted here only so a future reconciliation of *that* change
does not have to rediscover which files moved.

**Conclusion: `agent-stream-events` needs no changes to reconcile with current behaviour.** One dated
note added under 16.2 in `openspec/changes/2026-07-30-hub-native-experience/tasks.md` (44 lines, the
only file touched this iteration). No checkbox ticked, no code changed, per the file's own
reconciliation rule.

**Verified before committing:** re-read `agent-stream-events/spec.md` in full (284 lines) rather than
trusting a grep-and-skim; every code citation above was opened and read at the cited lines, not
assumed from a prior iteration's memory; `git diff --stat` showed exactly the one file, 44 insertions.
`git status --short` showed only that plus the carried-forward `spec/` and `hub/seed_taste_doc.py`
scratch, staged nothing from them.

**Tree state before commit:** `openspec/changes/2026-07-30-hub-native-experience/tasks.md` modified
(1 new note, 44 lines); `.claude/autonomous/STATE.json` updated (iteration, heartbeat, Q11 done_note,
next_action); `spec/` and `hub/seed_taste_doc.py` (prior-session scratch) untouched.

**Queue status:** Q1–Q10 done. Q11 — roadmap #7 stays parked. Roadmap #8: the eight-delta mapping
from iterations 16–23 is finished; this iteration started the three-current-spec half 16.2's own text
also names, closing `agent-stream-events` with no gap found. Two remain — `runtime-diagnostics`,
`agent-conversation-handoff` — `runtime-diagnostics` next if a future iteration continues this. Runway
to `stop_at` (2026-08-18T08:00+01:00) is roughly 1h.
