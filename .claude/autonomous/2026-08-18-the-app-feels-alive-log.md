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
