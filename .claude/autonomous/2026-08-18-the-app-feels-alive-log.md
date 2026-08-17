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
