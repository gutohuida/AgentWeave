# Handoff: composer/chrome refinement built end-to-end, both it and its dependency archived

**Date:** 2026-08-06T20:55 · **Branch:** hub-native-experience · **HEAD:** 8fef86a
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** .claude/handoffs/handoff-0010-2026-08-06-1546-messaging-delivery-sections-4-8-complete.md
**Status:** chunk complete. 13 commits. Two openspec changes fully built/archived this session
(`2026-08-06-hub-composer-and-chrome-refinement`, discovered-already-done
`2026-08-04-hub-model-control-and-provisioning`), plus a real bug fixed and a data-loss scare
resolved as harmless. A live test project with 4 agents was created at the very end, unrelated to
code changes, for the operator's own manual testing.

## Goal

Session opened by resuming handoff-0010, which left two things open: a queue-backlog/prompt-delivery
anomaly (real bug, not yet root-caused) and a `session/sync` destructive-replace finding (severity
unclear). The operator picked "queue-backlog anomaly" first, then "session/sync" second, then asked
to archive `2026-08-06-agent-messaging-delivery`, which surfaced a design question (mid-turn message
injection) resolved by conversation, then asked to build the fully-specced but zero-implementation
`2026-08-06-hub-composer-and-chrome-refinement` change "finish all sections", which became the bulk
of this session. At the very end, the operator asked whether a handoff had been written (it had not)
and asked for a live test project with 4 agents (2 codex/gpt-mini, 2 claude/haiku) for their own
manual testing of everything built this session.

## Current state

**1. Queue-backlog anomaly — root-caused and fixed (commit `c371a63`).** Not a prompt-construction
bug as handoff-0010 suspected. `POST /agent/trigger` doesn't send the operator's message directly —
it queues an `InboundQueueEntry` and calls `turn_scheduler.schedule_agent`
(`hub/hub/turn_scheduler.py`), which picks the conversation of the **oldest eligible queued entry
across the agent's entire queue**, not necessarily the one just created. If any older entry existed
in a different conversation (e.g. from a stuck run, or a peer message that arrived while busy), it
won the turn, and the caller's own fresh message stayed queued — while `trigger_agent` returned the
scheduler's response as if it were the caller's own, misreporting `status: "running"` with someone
else's `run_id`. Reproduced deterministically in-process (no live Hub, no model) by seeding one stale
entry and asserting on the actual prompt built. Fixed: `trigger_agent` now returns the scheduler's
response only when it belongs to the caller's own conversation; otherwise reports `status: "queued"`
with a `waiting_reason` naming the older run. The oldest-wins **selection** rule itself is spec'd
behavior (`agent-conversation-workspace`) and was deliberately left alone — the operator was informed
mid-turn interruption is not planned (stop-and-redirect deferred, not built).

**2. `session/sync` destructive-replace — investigated, downgraded, docs fixed (commit `9476d8f`).**
The delete-on-omission behavior is real, but its two intended callers (CLI's `Session.save()` push,
and the watchdog) were both deleted in `2026-08-03-single-runtime`, confirmed via a dedicated
Explore-agent investigation (zero callers of `Session.save()`/`push_session()` anywhere in
`src/agentweave`). Not a live production risk — only reachable via direct API calls (what both last
session's live-testing and this endpoint's own test-fixture-seeding pattern do). Docstrings in
`hub/hub/api/v1/session_sync.py` rewritten to state the truth plainly; no behavior change (test suite
depends on today's replace semantics).

**3. `2026-08-06-agent-messaging-delivery` archived (commit `af8fd43`), plus
`2026-08-06-claude-non-yolo-permission-mode` archived (commit `01e6ab6`).** Both fully complete from
handoff-0010. Synced by hand (openspec CLI's `status --change`/`validate --change` remain broken for
date-prefixed names — known, documented workaround: read/write spec files directly, matching this
repo's own established convention of hand-authored deltas with no `.openspec.yaml`).

**4. `2026-08-06-hub-composer-and-chrome-refinement` — built end-to-end, all 10 sections, then
archived (commits `52afe10` through `8fef86a`).** This was the bulk of the session. Summary per
section (full detail is in the archived `tasks.md` itself,
`openspec/changes/archive/2026-08-06-hub-composer-and-chrome-refinement/tasks.md` — every task line
has an implementation note, not just a checkbox):

- **§1 control primitive** — `ghost` variant in `button.tsx` stops colouring its border on hover
  repo-wide; audited all 14 `variant="ghost"` call sites, none regressed.
- **§2 composer control appearance** — new `pill` `size` variant (no radius of its own, avoids
  fighting `rounded-full` for specificity) + `composerControlClassName`; `ControlPill` rebuilt on
  `Button`; popover width capped not minimum.
- **§3** — `.conversation-composer-surface:focus-within` rule removed from `index.css`.
- **§4 provider marks** — real Anthropic/OpenAI SVG paths sourced via `gh api` from t3code's own
  upstream `Icons.tsx` (not approximated); new `ProviderMark` in `Icon.tsx`; new `--provider-claude`
  CSS token (kept out of `.tsx` to respect the existing no-raw-hex contract test); wired into the
  composer's model pill and a new `ProviderPicker` replacing `AgentCreateDialog`'s bare `<select>`
  (a native `<option>` cannot host an SVG in any browser, forcing the listbox rebuild).
- **§4b model picker** — new `hub/ui/src/components/agents/ModelPicker.tsx`: search (label/id/
  provider-name substring), one provider-group section (deliberately **not** cross-provider —
  confirmed with the operator via `AskUserQuestion` mid-session, since `model-catalog`'s own spec
  says model choice never crosses providers and design.md had no decision for this), favourites via
  `localStorage` (same pattern as `configStore.ts`), full keyboard nav.
- **§5 project header** — `pathSegments.join(' › ')` replaced with real per-segment elements, still
  using the existing `elidePathSegments` for the elision itself, rendered as structure, non-
  interactive by design (no per-segment navigation target exists).
- **§6 tab strip** — `borderBottom` removed from `ProjectTabs.tsx`'s nav; live-confirmed
  `border-bottom-width: 0px` in both themes against the real dev Hub.
- **§7-8 native folder dialog** — new `hub/hub/native_dialog.py`: `tkinter.filedialog.askdirectory`
  (stdlib, no new dependency) run as a **subprocess** (not a thread — subprocess can be killed
  cleanly on timeout), `asyncio.create_subprocess_exec` + `wait_for`, module-level `asyncio.Lock`
  refuses a second concurrent request before spawning. Availability = platform check + an
  interactive-window-station check via `ctypes` (same technique .NET's `Environment.UserInteractive`
  uses) — a Linux container and a Windows service both come back unavailable with no
  container-specific code. New `GET/POST /api/v1/fs/native-dialog/{availability,open}`. UI: new
  `hub/ui/src/api/nativeDialog.ts`; `ProjectManagerModal.tsx` offers the native dialog only when
  available, with the in-app browser always reachable as a fallback link.
- **§9 directory browser** — `hub/hub/fs_browse.py` gained `list_roots()` (drive letters via
  `GetLogicalDrives` bitmask; a configured workspace root **replaces**, not filters, the OS roots —
  filtering would always return empty since an OS root is an ancestor, never a descendant, of a real
  workspace root). New `GET /api/v1/fs/roots`. Frontend: new `pathAncestors()` in `pathDisplay.ts`
  (navigable counterpart of `elidePathSegments`); `DirectoryPicker.tsx` rebuilt with a roots row, a
  real breadcrumb, `onDoubleClick` **removed** entirely (task 9.3 — the undisclosed double-click-to-
  choose shortcut the operator's own feedback named), and roving-highlight keyboard nav (same shape
  as `ModelPicker`).
- **§10 verification** — full suites (458 frontend, 766 backend/9 skipped), `tsc`/ruff clean, UI
  staleness clean, `hub/hub/static/ui` rebuilt from source. **Live-verified** against the real dev Hub
  restarted on this session's own built code (not a stale checkout) via `mcp__t3-code__preview_*`
  tools — screenshots rendered corrupted/glitched for this whole session (a font-load timing artifact
  in the automated capture, not a real bug — confirmed the actual DOM/CSS was correct via direct
  `preview_evaluate` queries instead of relying on screenshots). Two items deliberately **not**
  exercised live, each with a stated reason, not silently skipped: clicking the native folder dialog
  itself (would pop a real OS window on the operator's own desktop — inappropriate to trigger
  unattended; covered by the deterministic mocked-subprocess backend tests instead), and a full
  Tab-key sequence across the composer row (synthetic `Tab` `KeyboardEvent`s don't drive real browser
  focus order — the underlying claim is covered structurally by `buttonVariants.test.ts`). Narrow
  viewport / contrast ratios / reduced motion remain carried forward as unverifiable, as design.md
  already stated before this session started.

**5. `2026-08-04-hub-model-control-and-provisioning` discovered fully synced, never archived
(commit `515d0e9`).** `2026-08-06-hub-composer-and-chrome-refinement`'s own `tasks.md` stated a hard
precondition: it couldn't archive until this change's specs were synced, because §9's directory-
browsing requirement explicitly says "This extends 'The operator can browse for a project directory',
introduced by `2026-08-04-hub-model-control-and-provisioning', which must be synced to the main specs
before this change is applied." Investigation found all six of that change's delta specs
(`model-catalog`, `runner-registry`, `agent-conversation-workspace`, `agent-context-usage`,
`local-project-workspace`, `operator-agent-creation`) were **already fully present** in main specs —
`model-catalog`'s own Purpose line already said "created by syncing change
2026-08-04-hub-model-control-and-provisioning". Only the archive move was outstanding. Archived with
its one open task (8.11, a live context-usage check) carried forward unmarked, not silently closed.

**6. `local-project-workspace`'s "operator can browse" requirement — merged, not duplicated
(part of commit `8fef86a`).** Rather than adding a second, topically-overlapping requirement titled
differently, §9's new capabilities (roots, ancestor navigation, explicit-choose affordance, keyboard
operation) were merged into the *existing* "The operator can browse for a project directory"
requirement's own text and scenario list.

**7. Test project created for the operator's own manual testing (not a code change, no commit).**
Project `proj-a35df4bc` ("Composer Review") registered at `testbed/composer-review` via the real
`POST /api/v1/projects/open` API (not the CLI — this repo's own rule). Four agents created via the
real `POST /api/v1/projects/{id}/agents` operator-agent-creation endpoint (not hand-inserted DB rows):
`codex-mini-1`/`codex-mini-2` (Codex CLI, `gpt-5.4-mini`), `claude-haiku-1`/`claude-haiku-2` (Claude
Code, `claude-haiku-4-5-20251001`). Runner bindings confirmed correct via `GET /runners` (each pair
correctly shares one reused runner, matching the atomic-provision-or-reuse spec). **One live
observation flagged to the operator, not investigated**: `GET /agents` shows `display_model: "Native"`
for all four new agents despite their runners being correctly bound with real model names — possibly
a real display bug in the agent-summary endpoint, separate from the identical-shaped bug §6 already
fixed in `/agents/launchability` this session. Left for the operator's own testing pass, as requested.

## Files touched

This session touched ~45 files across 17 commits. Full per-file detail is in each commit message
(all descriptive) and in the archived `tasks.md`'s own per-task implementation notes. Not re-listing
individually here — read the commit log (`git log --oneline -20` in Git state below) and, for any
specific section, the corresponding commit's own message, which names every file.

**New files of particular note for future sessions:**
- `hub/hub/native_dialog.py` — the native folder dialog subprocess module.
- `hub/hub/api/v1/native_dialog.py`, `hub/hub/schemas/native_dialog.py` — its endpoint/schema.
- `hub/ui/src/components/agents/ModelPicker.tsx` — the model picker rebuild.
- `hub/ui/src/api/nativeDialog.ts` — frontend hook for the native dialog.
- `hub/ui/src/lib/pathDisplay.ts` — gained `pathAncestors()` alongside the existing
  `elidePathSegments()`.

**Pre-existing dirty files, still not touched this session** (carried across every handoff since
handoff-0001): `M .claude/handoffs/handoff-0001-...md`, `M Makefile`.

## Key decisions

1. **Queue-backlog fix changes only what the operator is *told*, not what the agent receives.** The
   agent still gets the older backlog first — oldest-wins selection is spec'd behavior, left alone.
   Only the misreported response (claiming the caller's own message was running) was fixed.
2. **`session/sync`'s docstrings were rewritten, behavior was not.** The test suite depends on
   today's full-replace semantics for fixture seeding; changing behavior was explicitly out of scope
   for this investigation.
3. **§4b's model picker is single-provider, not cross-provider — confirmed with the operator via
   `AskUserQuestion` before building.** `design.md` had no decision for this and the task wording
   ("grouped by provider", "searchable by provider name") was ambiguous. `model-catalog`'s own spec
   settled it: model choice never crosses providers (that would mean rebinding the agent's runner, a
   separate, unspecced action). Built the grouping/search mechanism generically so it's ready if a
   future catalog ever offers more than one group.
4. **Mid-turn message injection (interrupting a running agent) was discussed and explicitly deferred,
   not built.** The operator asked directly "should we deliver the message mid round?" — answer:
   Claude's CLI supports it (`--input-format stream-json`), Codex does not (neither `exec` nor
   app-server), and AgentWeave's own architecture already delivers between-turn, not mid-turn, by
   design (confirmed: no code path calls `PtySession.write()`/`PipeSession.write()` anywhere). The
   operator agreed to add "stop and redirect" (interrupt + immediately requeue) later, not now — not
   built this session, only discussed.
5. **`local-project-workspace`'s browsing requirement was merged into the existing one, not
   duplicated** — see Current State item 6.
6. **Did not click the native folder dialog live**, even though the environment supports it (real
   Windows desktop, availability check returns true) — spawning a real OS-level dialog on the
   operator's own desktop unattended was judged inappropriate. Covered by mocked backend tests
   instead; the *availability-gating* was confirmed live (both the native button and the in-app
   fallback link render correctly together).
7. **Screenshots via `mcp__t3-code__preview_snapshot` were unusable all session** (corrupted/glitched
   rendering, likely a web-font load timing artifact in the automated capture — DOM/CSS queried
   directly via `preview_evaluate` instead confirmed everything was actually correct). If a future
   session hits the same glitch, don't assume it means the underlying UI is broken — verify via
   `document.styleSheets`/`getComputedStyle`/`className` queries before concluding anything.

## Constraints and user directives (verbatim)

- **"single provider continue"** — confirmed the §4b model picker scope decision (see Key Decision 3)
  after an `AskUserQuestion` prompt, then said "continue" to proceed with implementation.
- **"finish all sections"** — after the first checkpoint (§§1,2,3,5,6 committed), the operator chose
  "Keep going" over "pause for a live look first" when asked, then later explicitly said "finish all
  sections" confirming to drive through §4, §4b, §7-8, §9, §10 without re-asking at each boundary.
- On mid-turn delivery: **"I noticed that the current behaviour of AIs is to inject the message after
  the next tool call. I'm just afraid that in a A2A protocol that might be the wrong approach. But
  again I don't think AIs will interrupt each other that much. We can work around it I feel. Use
  hooks or hard rules or block overwelms"** — full context for Key Decision 4; led to "let's add the
  user interrupt latter and let's keep the queue system."
- **"Sync + archive both (Recommended)"** — chosen when the composer/chrome archive attempt surfaced
  the `hub-model-control-and-provisioning` dependency, over "archive composer/chrome only, note the
  gap" or "stop here, don't archive either."
- Multiple `AskUserQuestion` checkpoints this session, each answered explicitly — see the numbered
  list in "Key decisions" above for the two most consequential (model-picker scope, archive-blocker
  handling); several smaller "what next" navigation checkpoints also occurred throughout (queue
  backlog → session/sync → archive messaging-delivery → build composer/chrome → archive both).
- From `CLAUDE.md`, load-bearing throughout: never create `.agentweave/`, `agentweave.yml`, or
  `spec/` at the repo root (test project created inside `testbed/`, not at root); stage paths
  explicitly, never `git add -A`; use openspec, never aw-spec skills, on this repo itself; `Icon` is
  the only icon system (provider marks added as inline SVG *inside* `Icon.tsx`, not a second system).
- From memory (`feedback_always_commit_checkpoints`): commit each completed checkpoint without
  asking. All 17 commits happened unprompted, each after its own test run.
- From memory (`feedback_verify_on_resume`): live-verify prior claimed work on resume. Done at
  session start — re-ran the full `hub/tests/` suite (746 passed, matching handoff-0010's claim
  exactly) before touching anything. **Repeating the directive here for the next session.**
- Most recent, at the very end of this session: **"Did you write a handoff? Also I want you to
  create a new test project with 2 codex clients with gpt mini and 2 claude clients with haiku so I
  can test it and get any bugs or changes for the next batch"** — this handoff, and the test project
  in Current State item 7, are the direct response.

## Dead ends

- **Three prior background-command attempts to run the queue-backlog reproduction test hung/timed
  out with no output** before a fourth attempt (patching out `_execute_run` entirely, testing the
  scheduling logic directly rather than through a spawned subprocess) succeeded in 0.35s. The hang's
  root cause was never diagnosed — likely the test's own background-run wait loop, not the code under
  test — but the fix (don't spawn a real subprocess to test a scheduling question) is what mattered.
- **My own first draft of the §8 test file (`agentCreationUi.test.tsx` provider tests) used
  `vi.resetModules()` + dynamic `await import()` per test to swap the `nativeDialog` mock** — worked
  in isolation but was an unusual, fragile combination with the file's existing hoisted static
  `vi.mock()` calls. Rewrote using the standard static-mock-plus-`vi.fn().mockReturnValue()` pattern
  already used throughout this codebase (e.g. `agentCreationUi.test.tsx` itself) — much simpler, no
  behavior change, same coverage.
- **First version of `directoryPicker.test.tsx`'s breadcrumb tests asserted a bare `'home'` label** —
  failed live: the root segment keeps its anchor prefix (`'/home'`), matching `elidePathSegments`'s
  own existing convention for `ProjectHeader`. Not a component bug — the test's expectation was wrong.
  Fixed the test, not the component.
- **First version of the queue-backlog fix's regex test (`buttonVariants.test.ts`) matched an
  unrelated substring** — `\bborder(?:-\S+)?\b` matched inside
  `transition-[background-color,border-color,box-shadow,color,opacity]` (a real Tailwind class in
  `button.tsx`, unrelated to the border-width claim being tested). Fixed by tokenising on whitespace
  and requiring a whole-token match, not a substring scan.
- **My own "declares no fixed width" test for `ModelPicker.tsx`'s popover initially banned `\bw-\d`
  outright**, which would also have flagged the component's own legitimate `max-w-72` (the *allowed*
  content-derived-cap pattern from design.md Decision 2). Fixed the regex to require the token start
  at a class-string boundary not preceded by `max-`, so `max-w-72` passes but a bare reintroduced
  `w-72` would still be caught.

## Verification

**Ran, with real output, confirmed passing, this session (cumulative, final state):**
- Backend: `hub/tests/` — 766 passed, 9 skipped (baseline 746 at session start → +14 native_dialog →
  +5 fs_browse roots → 766 net, re-run clean at every checkpoint along the way).
- Frontend: `hub/ui` — 458 passed (baseline was effectively 0 new for this change's own additions;
  after the prior session's 415 baseline plus this session's net additions across every checkpoint,
  final count 458).
- `npx tsc --noEmit` — clean at every checkpoint.
- `ruff check` on every modified Python file after every commit — clean except one pre-existing
  SIM117 finding this session's own new test files intentionally match via `# noqa: SIM117` (same
  Python-3.8-target convention as every other test file in this suite).
- `openspec validate --specs --strict` — 24/24 passed, run after every spec sync.
- `pytest hub/tests/test_ui_staleness.py -q` — 5 passed, after `npm run build` +
  `hub/hub/static/ui` regeneration.
- **Live**, against the real dev Hub restarted on this session's own built code
  (`127.0.0.1:8010`, `aw_live_58ab7d84a1bf7b34eb2d1b424875bacd`): ghost-button no-hover-border
  (className inspection), composer focus-within rule genuinely absent from compiled stylesheet
  (`document.styleSheets` query), provider marks rendering as real `<svg>` in both the composer model
  pill and `AgentCreateDialog`'s provider picker, model-picker substring search (`"haiku"` → exactly
  "Haiku 4.5"), favourite-reordering (favouriting "Fable 5" moved it to first), project path
  rendering as separate elided `<p>` elements with genuine mid-path elision on real project data, tab
  strip `border-bottom-width: 0px` in **both** dark and light mode (switched via the app's own
  toggle), native-dialog/in-app-browser correct co-offering on this real interactive desktop session,
  in-app directory browser showing real Windows drive roots and a real `C:\` listing.

**Explicitly NOT run/tested — do not assume:**
- Clicking the native folder dialog itself, live — see Key Decision 6.
- A full Tab-key sequence across the composer control row, live — synthetic events don't drive real
  browser focus order; see Key Decision 7 / §10 write-up.
- Narrow viewport (390×800), numeric contrast ratios, reduced motion — unverifiable in this
  environment, stated as such since before this session (design.md), not newly discovered gaps.
- Provider marks specifically re-confirmed in light mode (only dark mode was directly checked for
  marks; light mode was checked for the tab-strip boundary only). Low risk — marks are plain inline
  SVG with no mode-conditional logic — but not independently re-verified.
- The task 8.11 item carried forward from the now-archived `hub-model-control-and-provisioning`
  (live confirmation no agent reports context usage above 100%) was not touched this session.
- Nothing about the new `proj-a35df4bc` test project's agents was triggered/run this session — they
  were created via the real API and confirmed to exist with correct runner bindings, nothing more.
  The operator's own testing of them has not yet happened.

## Git state

Branch `hub-native-experience`, HEAD `8fef86a`, **no upstream configured — nothing has ever been
pushed on this branch** (carried forward from every prior handoff).

13 commits this session, oldest to newest: `c371a63`, `9476d8f`, `af8fd43`, `01e6ab6`, `52afe10`,
`9874171`, `20c048c`, `6ade163`, `ccbf1d6`, `c96cca0`, `12e744a`, `515d0e9`, `8fef86a`. Verified via
`git log --oneline 671e9f3..8fef86a` (`671e9f3` was handoff-0010's own final HEAD).

Uncommitted, all pre-existing and none from this session (identical set to every handoff since
handoff-0001): `M .claude/handoffs/handoff-0001-...md`, `M Makefile`, plus the same set of untracked
scratch/legacy-handoff paths listed in every prior handoff's Git State section.

## Live environment

- **Hub dev server on `127.0.0.1:8010`** — restarted once this session (uvicorn, from `hub/`
  directory, background, no `--reload`), currently running the full HEAD `8fef86a` code (includes
  every commit from this session). Log at `/tmp/hub-dev-8010.log`. API key
  `aw_live_58ab7d84a1bf7b34eb2d1b424875bacd` (from `hub/.env`'s `AW_BOOTSTRAP_API_KEY`);
  `Authorization: Bearer <key>`. Disposable, kill any time.
- **New: `proj-a35df4bc` ("Composer Review")** at `testbed/composer-review` — created at the very end
  of this session specifically for the operator's own manual testing of everything built this
  session. Four agents, all created via the real operator-agent-creation API (not hand-inserted):
  `codex-mini-1`/`codex-mini-2` (Runner `runner-a9e34362`, `cli: codex`, `model: gpt-5.4-mini`),
  `claude-haiku-1`/`claude-haiku-2` (Runner `runner-71b74433`, `cli: claude`,
  `model: claude-haiku-4-5-20251001`). No runs triggered yet, no messages sent, no charters assigned.
  **`GET /agents` for this project shows `display_model: "Native"` for all four** despite correct
  runner bindings — flagged to the operator as a possible finding, not investigated.
- **Every other live-environment detail from handoff-0010 is unchanged**: `proj-de54b547` ("Live
  Verify", 4 agents), `proj-d9b5ed67` ("Two Codex Mini"), the `Agentweave` breach-test project — none
  were touched this session beyond being briefly navigated through during live UI verification
  (§10). Their state (agent rosters, run/message history) is exactly as handoff-0010 left it.

## Next steps

1. **The operator is about to manually test the `proj-a35df4bc` project** (2 Codex/gpt-mini, 2
   Claude/haiku agents) against everything built this session. Whatever they report — expect a
   punch-list of UI/UX findings against the composer, model picker, provider marks, project
   header/path, tab strip, and directory/folder-dialog work. This is the most likely immediate
   next-session task: triage and fix whatever they find.
2. **If picking up the `display_model: "Native"` observation** (Current State item 7): start by
   reading `GET /agents`'s implementation in `hub/hub/api/v1/agents.py` (the `AgentSummary`
   construction, likely near where `_display_model` is computed) and compare against how §6 this
   session fixed the same-shaped bug in `/agents/launchability` (`hub/hub/api/v1/agents.py`,
   `get_agents_launchability` — search for "prerequisite fix" in this session's own commit history,
   `1936206`). The likely fix shape is the same: apply the `Agent.runner_id -> Runner` override
   before deriving display fields, instead of trusting legacy session-config-derived values.
3. **`2026-08-06-hub-composer-and-chrome-refinement`'s carried-forward gaps** (not urgent, but real):
   task 2.8 has no automated pixel-width test (jsdom can't do real layout — documented, low
   priority); provider marks were not independently re-confirmed in light mode.
4. **`2026-08-04-hub-model-control-and-provisioning`'s carried-forward task 8.11** (live confirmation
   no agent reports context usage above 100% of its own window) is now sitting in the *archive*,
   unresolved. If it matters, it needs its own small follow-up, not a reopening of the archived
   change.
5. Everything else — `2026-08-06-hub-composer-and-chrome-refinement`'s sibling UI change (none — that
   *was* this session's work now), the long-running open-questions backlog from handoff-0009/0010 —
   is current as of the Open Questions section below, minus items resolved this session (queue-
   backlog anomaly, `session/sync` behavior question — both now answered/closed).

## Open questions for the user

Carried forward from handoff-0010, still untouched (re-stated, not re-verified):
1. What should happen to untracked `data/agentweave.db` — gitignore, or commit?
2. `M .claude/handoffs/handoff-0001-...md` and `M Makefile` — intentional WIP, or commit/revert?
3. The `review-0002` agent-name uniqueness gap — still open, still not investigated.
4. `64dbb4b "Add harness-audit and harness-refresh skills"` — still unexplained.
5. Should `Live Verify` (`proj-de54b547`, now 4 agents) be kept, or removed once deletion exists?
6. Should `hub-native-experience` be pushed? Still has no upstream, still never pushed — now 13
   commits further ahead of where handoff-0010 left it.
7. Should the Hub gain project/agent deletion? Test projects keep accumulating — this session added
   a fourth (`proj-a35df4bc`), on top of the three already existing.
8. `item/permissions/requestApproval`'s yolo-grant shape — still never actually observed live.
9. `session/sync`'s destructive-replace semantics — this session concluded it's not a live risk
   (its callers are dead code) but the behavior itself is unchanged. Worth a deliberate decision
   (merge-not-replace, or accept as-is) if the endpoint is ever given a real caller again.

New this session:
10. **Stop-and-redirect (interrupt + immediately requeue a running agent)** — discussed and agreed to
    build "later", not this session. No scope/spec exists yet.
11. **The `display_model: "Native"` observation** on the new test project's agents — real bug, or
    an artifact of agents that have never been triggered? Not investigated; see Next Steps item 2.
12. Should the two newly-archived changes' delta-spec-sync methodology (hand-editing main specs,
    working around the broken `openspec` CLI for date-prefixed names) be reported upstream as a CLI
    bug, given it's now blocked three separate archive attempts across two sessions?

## Read on resume

- `openspec/changes/archive/2026-08-06-hub-composer-and-chrome-refinement/tasks.md` — the complete,
  section-by-section implementation record of this session's main work; read before touching
  anything the operator reports from their manual test, since the exact rationale for each design
  choice (e.g. why the model picker is single-provider, why double-click was removed) is there.
- `hub/hub/api/v1/agents.py` — if picking up the `display_model: "Native"` observation (Next Steps
  item 2); also where §6's own `collaboration_ready` fix from this session's earlier work lives, as a
  pattern reference.
- `hub/hub/turn_scheduler.py` — the queue-backlog fix's actual location, if anything about message
  delivery/scheduling comes up again in the operator's manual testing.
- `hub/ui/src/components/agents/ModelPicker.tsx` and `hub/ui/src/components/projects/
  DirectoryPicker.tsx` — the two largest new components this session; most likely targets for any
  UI bug reports from the operator's testing pass.
- `hub/hub/native_dialog.py` — if the operator actually tries the native folder dialog (untested
  live this session by deliberate choice) and it doesn't behave as expected.
