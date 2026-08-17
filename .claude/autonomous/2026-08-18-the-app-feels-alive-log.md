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
