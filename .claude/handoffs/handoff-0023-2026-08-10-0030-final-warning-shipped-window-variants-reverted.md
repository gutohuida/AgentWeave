# Handoff: the checkpoint final warning shipped; the context-window variants were built and reverted

**Date:** 2026-08-10T00:30 · **Branch:** hub-native-experience · **HEAD:** `96575f5`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0022-2026-08-09-0100-checkpoint-capability-shipped-and-hardened.md`
**Status:** chunk complete. 6 commits, all pushed. **Working tree clean.**

## Goal

Three things, in order:

1. Resume from handoff 0022 and finish its next-step 1 — sync and archive the two completed
   checkpoint follow-up changes.
2. Close the two checkpoint loose ends the operator picked: **the 95% gap** (a dismissed warning
   could cost the whole conversation) and **"the context windows should be a config on the chat
   bar"**.
3. Delete the accumulated test project and start a clean one.

The *why* for (2): the warning change made dismissal final and named the cost in its own proposal
— Claude Code auto-compacts near 95%, so a conversation dismissed at 60% and run to exhaustion is
summarised by the CLI first. That is the exact defect the whole capability exists to remove,
returning through the one door dismissal had to leave open.

## Current state

### Shipped and archived: `2026-08-09-checkpoint-final-warning`

A dismissed conversation now warns **once more** at 92%, and that warning carries **no dismiss
action**. `Conversation.checkpoint_warning` gained a fourth state, `final` (no migration — the
column was already `String(16)`, nullable, unconstrained). Taking a checkpoint clears `final` as
it clears `due`; the dismissal endpoint returns **409** rather than moving `final` back.

**Live testing found a defect all 8 unit tests missed.** The backstop was originally evaluated
*after* `should_checkpoint`, which in token mode reads `context_tokens` alone — so a reading
carrying a percentage and no token count declined as "below the tokens threshold of 150000" and
the final warning was unreachable. Every unit test passed because they all configured percent mode
and supplied a percentage; the live project was in token mode. It is now answered **ahead of** the
threshold checks. Regression test:
`test_the_backstop_does_not_depend_on_the_configured_threshold`.

### Built, then reverted: `2026-08-09-model-context-window-variants`

Proposed, implemented, live-verified, archived — then **fully reverted in `96575f5`** because the
premise was wrong. The archived change directory was deleted too; it never described shipped
behaviour.

**What I got wrong, so it is not re-derived:** `claude-haiku-4-5-20251001[1m]` is refused with
*"The long context beta is not yet available for this subscription"*. That wording is
entitlement-shaped, and I inferred a real 1M Haiku sitting behind a paywall. **There is no 1M
Haiku** — Haiku 4.5's window is 200,000, full stop. The operator caught it.

The authoritative picture, from the model catalog and from Codex's own `models_cache.json`:

| model | window | alternatives |
|---|---|---|
| Opus 5, Sonnet 5, Fable 5 | 1,000,000 | none — natively 1M |
| Haiku 4.5 | 200,000 | none |
| all six Codex `gpt-5.*` | 272,000 | none |

So **no model in either provider offers a second selectable window.** The `[1m]` suffix is
vestigial — from when Sonnet 4.5 was a 200K model and 1M sat behind a context beta. It parses on
Opus/Sonnet and changes nothing because it asks for what they already have.

**Kept from that work:** the docstring correction. `model_catalog.py` had claimed Opus 5 and Fable
5 declared `context_window=None` "rather than a guessed value — the rule this catalog exists to
enforce", while the code declared `1_000_000` for both. Both are live-verified at 1,000,000, so
the code was right and the prose was stale. In its place is a note recording that `[1m]` is **not**
a window selector and that the Haiku error message misleads.

### Also archived this session

`2026-08-09-checkpoint-configuration-surface` and `2026-08-09-checkpoint-warning-before-spend` —
handoff 0022's next-step 1. Their deltas are now in
`openspec/specs/conversation-checkpoint/spec.md`.

**Note on `733ccbd` (previous session):** its message claimed the spec sync but only the archive
moves were staged; the 62-line spec edit sat unstaged. Committed this session as `293ff14`.

### In-flight changes (counts re-derived from `tasks.md`, not carried)

| change | tasks |
|---|---|
| `2026-07-30-hub-native-experience` | 119 done / **69 open** — biggest remaining front |
| `2026-08-04-hub-charcoal-visual-refresh` | 39 / **3 open** — all need a *human* |
| `2026-08-04-hub-contextual-navigation` | 43 / **2 open** — same |
| `2026-08-07-spec-execution-coordinator` | 0 / 29 — **gated skeleton, DO NOT START**, fails validate by design |

The five open tasks in the two nearly-done changes are marked "not run — tool limitation, not
skipped": live keyboard traversal, numeric contrast ratios, `prefers-reduced-motion`. Available
browser automation emulates `prefers-color-scheme` only. **Twenty minutes of operator time
archives two changes.**

### Live environment — REBUILT THIS SESSION

The old testbed was deleted at the operator's request and replaced.

| | |
|---|---|
| Project | **`proj-cddb0827`** "Testbed" (was `proj-84d218db`) |
| Workspace | `C:\Users\huida\Documents\agentweave-testbed` (fresh git repo, one commit) |
| Database | fresh, alembic head **`0050`** |
| API key | **unchanged** — `aw_live_58ab7d84a1bf7b34eb2d1b424875bacd`, recreated from `hub/.env`'s `AW_BOOTSTRAP_API_KEY` |
| Hub | running detached on **http://localhost:8010**, restarted onto the reverted code |

Seeded automatically on project creation: 2 default runners (model-less) + 21 starter charters.
Agents created via the provider+model path the UI's Add-agent dialog uses, each find-or-creating a
runner:

- `claude-1` → runner `runner-9f74c835` (Claude Code — Haiku 4.5)
- `codex-1` → runner `runner-fa16fc2e` (Codex CLI — GPT-5.6-Sol)

**Checkpointing is `off`** on the new project — operator's choice. No agent-level overrides. None
of the old 1,000-token testing thresholds carry over.

**Set aside, not deleted** (operator can remove whenever):
- `hub/data/agentweave.db.old-20260810-000742` (2.4 MB — 1 project, 9 agents, 5 runners, 55
  conversations, 115 runs, 10 checkpoints)
- `C:\Users\huida\Documents\agentweave-testbed-old-20260810-000742` (git repo + `.agentweave/`
  marker + worktrees)

Hub restart command:

```powershell
Start-Process -FilePath 'C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe' `
  -ArgumentList '-m','uvicorn','hub.main:app','--host','127.0.0.1','--port','8010' `
  -WorkingDirectory 'C:\Users\huida\Documents\projects\AgentWeave\hub' -WindowStyle Hidden
```

## Files touched

Everything is **committed and pushed**; working tree clean. `git status --short` is empty.
`hub/hub/static/ui/` is the committed build artefact, rebuilt and `diff -rq` verified after each
frontend commit.

### Final-warning change (`ec2d2bb`) — still live

- `hub/hub/checkpoint_policy.py` — `FINAL_WARNING_PERCENT = 92`; `needs_final_warning(policy, *,
  percent)`. Deliberately takes **no** `context_tokens`.
- `hub/hub/checkpoint_trigger.py` — the `dismissed`/`final` branch moved **above** the notes and
  threshold checks in `consider`; broadcasts `checkpoint_due` with `"final": True`.
- `hub/hub/api/v1/checkpoints.py` — take-checkpoint clears `final` as well as `due`;
  `dismiss_checkpoint_warning` raises 409 on `final`.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — `checkpointWarning` extracted;
  `checkpointFinal`; a `tone: 'problem'` banner with an action and **no** `secondaryAction`.
- `hub/ui/src/api/agentChat.ts` — `checkpoint_warning?: 'due' | 'dismissed' | 'final' | null`.
- `hub/tests/test_checkpoint_policy.py` — +4 tests.
- `hub/tests/test_checkpoint_cutover.py` — +6 tests, and
  `test_a_dismissed_warning_never_returns` **inverted** to
  `test_a_dismissed_warning_does_not_return_while_there_is_room` (it asserted at 99%, which this
  change reclaims).
- `hub/ui/src/__tests__/agentHandoff.test.tsx` — +2 tests (8 → 10).

### Variants change — reverted in `96575f5`, only this survives

- `hub/hub/model_catalog.py` — docstring only: the corrected live-verified windows paragraph, plus
  the "One model, one window — do not add a per-model window choice" note. **All code reverted.**

### Spec files

- `openspec/specs/conversation-checkpoint/spec.md` — three deltas applied across the session
  (`293ff14`, `8f7c267`).
- `openspec/specs/model-catalog/spec.md` — restored to its pre-variants state in `96575f5`.
- `openspec/changes/archive/2026-08-09-checkpoint-final-warning/` — proposal, tasks, delta.
- `openspec/changes/archive/2026-08-09-checkpoint-configuration-surface/`,
  `.../2026-08-09-checkpoint-warning-before-spend/` — archived this session.

## Key decisions

1. **The backstop is answered before the configured threshold.** "Near the window" is a claim
   about the window filling up, not about the operator's number. Gating it behind
   `should_checkpoint` made it unreachable in token mode — observed live, not theorised.
2. **`needs_final_warning` takes no `context_tokens`, by design.** Every other predicate accepts
   both readings because both can answer; this one cannot. A token count with no window to divide
   by does not make a smaller version of the claim. Accepting the argument would invite a caller
   to pass it and assume it was used.
3. **`FINAL_WARNING_PERCENT = 92`** — above `DEFAULT_THRESHOLD_VALUE` (80) so reaching it means
   the operator really did keep going; below the ~95% CLI compaction so there is still a
   conversation left to checkpoint. Asserted by
   `test_the_final_warning_sits_between_the_default_threshold_and_the_cli_compaction`.
4. **The final banner ignores `warningDismissed`.** That local flag hides the *first* warning
   between the click and the refetch, and the `final` state is only reachable *because* that click
   happened — so the flag is true by definition every time it matters.
5. **Dismissal is refused with 409 on `final`, not silently ignored.** The state exists precisely
   because a dismissal was already spent.
6. **The variants revert removed the archived change directory**, rather than leaving it in
   `archive/`. An archived change reads as shipped behaviour; this one never was.
7. **Rejected: keeping the variants mechanism dormant with zero declarations.** It would be a
   control with nothing to control, plus two spec requirements describing it — the same
   "readiness signal that means nothing" pattern this capability was built to remove.
8. **Fresh project created via `POST /projects/open`, not `/create`.** `/create` requires a target
   that does **not** exist (it makes the directory); the workspace had already been created.

## Constraints and user directives (verbatim)

**From this session:**
- *"Can you delete the current test project, db and all and start a new one for testing?"*
- *"Some models have the context window that we can chose. Like opus has both 200k and 1M. This
  should be a config in chat like the model. T3 has this. You choose opus model for example and
  you can chose the size of the context window"* — **this turned out to be false for the current
  model line; see Dead ends.**
- *"one things. Is the gpt models only have 256k context windows? Also the haiku one is showing to
  choose between 1m and 200k... I know that haiku only has the 200k so changing to 1m makes no
  diference. You said something about opus being the default 1m do we not have opus 200k? Is that
  config irrelevant. Check claude code about that. And algo codex"* — **the operator was right and
  I was wrong.**
- Chose **"One final non-dismissible warning"** for the 95% gap.
- Chose **"One of each provider"** for the new testbed agents, and **"Leave it off for now"** for
  checkpoint config.
- Chose **"Revert the whole variants change"** once the premise collapsed.

**Carried and still binding:**
- *"Wait. Are you already implementing? Should we dive in first to see what to do or at least give
  me the plan on what are you doing so I can make a more informed decision."* — **lay out the plan
  before building anything non-trivial.** Honoured this session; keep honouring it.
- *"B. fixed back to the agent's conversation. Yes, no agent deletion. Just archive."*
- *"okay let's ok with i for v1 but we need to take a hard note on this because I'm for sure going
  to forget this in the future."* — memory `project_checkpoint_trigger_prompts_provisional`.
- *"no need for backups everything is test env"*
- *"I don't want it to be colorful it should be like the chat box but maybe a little lighter"*
- *"What is taking so long?"* — **the operator is sensitive to wall-clock.** `pytest hub/tests/` is
  ~3:30–5:40 for ~1273 tests; `npx vitest run` ~19s. Targeted files during dev, one full sweep
  before committing.
- From `CLAUDE.md`: never create `.agentweave/`, `agentweave.yml` or `spec/` at the repo root;
  stage paths explicitly; openspec never aw-spec skills; `Icon` is the only icon system;
  `approve_tool_call` keeps **no return annotation**; `hub/hub/static/ui` is a committed artefact
  refreshed after `npm run build` and confirmed with `diff -rq`; never mark a task complete on the
  strength of a plan existing.
- From memory: commit each completed checkpoint without asking; **live-verify prior claimed work
  on resume**; when setting up agents, **ask the operator for agent + model choice** (honoured via
  AskUserQuestion this session).

## Dead ends

**New this session:**
- **A subscription-shaped error message is not evidence a feature exists.**
  `claude-haiku-4-5-20251001[1m]` returns *"The long context beta is not yet available for this
  subscription"*. I read that as entitlement-gating in front of a real 1M Haiku and built a whole
  capability on it. Haiku 4.5 is 200K and has no long-context form. **Check a model's published
  context window before declaring anything about it.**
- **`[1m]` is vestigial, not a selector.** It parses on Opus 5 / Sonnet 5 / Fable 5 and changes
  nothing, because those are natively 1M. `[200k]` and `[bogus]` are both refused identically.
  There is no way to select a *smaller* window.
- **Unit tests that all share one configuration will all miss the same bug.** Eight tests covered
  the final warning; every one used percent mode with a percentage supplied. The live project was
  in token mode and the feature was dead. **Vary the configuration, not just the input.**
- **The agent-trigger request body field is `overrides`, not `runtime_overrides`.** A payload
  using the wrong name is silently ignored and the run succeeds on the runner's own model — my
  first "successful" variant test proved nothing.
- **`POST /api/v1/projects/create` requires a target that does not exist.** Use `/open` for a
  directory you already made.
- **`hub/tests/conftest.py` forces in-memory SQLite** (`DATABASE_URL=sqlite+aiosqlite:///:memory:`),
  so the suite never touches the live `hub/data/agentweave.db`. Safe to run tests with the Hub up.

**Carried and still true:**
- **Bash-tool cwd resets between calls, unpredictably.** Bit me ~4 times this session, including
  `Set-Location hub/ui` running twice and resolving to `hub/ui/hub/ui`. **Always `cd
  /c/Users/huida/Documents/projects/AgentWeave && …` first**, or use absolute paths.
- **`ORDER BY EventLog.id` does not order by recency** — order by `timestamp`.
- **`openspec` CLI cannot handle date-prefixed change names for sync/archive.** Do it by hand.
  `npx openspec validate <name> --strict` (no `change/` prefix) does work.
- **`openspec validate` wants SHALL/MUST on the *first line* of a requirement body.**
- **`npm run lint` does not work at all.** ESLint 9 needs a flat config the repo lacks; `tsc` is
  what checks. `ruff check hub/hub/` reports 3 pre-existing errors (`jobs.py`,
  `codex_appserver.py`) — none mine.
- **`pytest hub/tests/ tests/` together fails collection** — both trees have `tests/__init__.py`.
  Run separately, as `make test-all` does. **Pre-existing.**
- **The default `python` on PATH has no pytest** — use
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **The live DB is `hub/data/agentweave.db`**; `cd hub` first, table is `event_logs` (plural).
- **The Hub API rejects `X-API-Key`** — use `Authorization: Bearer <key>`.
- **Bash heredocs break on apostrophes.** Use the Write tool for prose files.
- **Adding a hook to a component breaks every test that mocks that api module** — patch the mocks
  in the same commit.
- `extra: "forbid"` rejects a forbidden **key** regardless of value; there is **no `db_session`
  fixture** — use `async_session_factory()`.

## Verification

**Ran, with real output:**
- `pytest hub/tests/` — 1262 (resume baseline) → 1281 (both changes) → **1273 passed, 10 skipped**
  after the revert. The −8 is exactly the reverted variant tests.
- `npx vitest run` — 638 (baseline) → 644 → **640 passed / 73 files** after the revert. The −4 is
  exactly the reverted window-pill tests.
- `npx tsc --noEmit` → clean at every frontend commit, including post-revert.
- `ruff check` on every touched file → clean (3 known pre-existing elsewhere).
- `npx openspec validate --specs --strict` → **27 passed, 0 failed** at every checkpoint.
- `npm run build` + copy to `hub/hub/static/ui` + `diff -rq` → identical, every frontend commit.
- **Live, against `:8010`:**
  - Final warning driven through the real `consider` against the running Hub's own database:
    85% → `dismissed`, 96% → `final`, 98% → still `final` (no re-fire), worker invocations
    unchanged at 23, zero checkpoints generated. **The first run of this produced `dismissed` at
    96% and exposed the ordering defect.**
  - Model windows read from each run's own `result.modelUsage.<model>.contextWindow`: opus-5
    1,000,000 · sonnet-5 1,000,000 · fable-5 1,000,000 · haiku-4-5 200,000. `[200k]` and `[bogus]`
    refused; `haiku[1m]` refused with the long-context-beta message.
  - Codex windows read from `~/.codex/models_cache.json` — 272,000 for all six listed models.
  - New project smoke test: `run-f583db71` (claude-1) and `run-242a1ec4` (codex-1) both completed
    exit 0 with the exact requested text; usage recorded (30,137 and 15,767 tokens).
  - Post-revert catalog endpoint: no `windows` field on any model; one window per model.

**Explicitly NOT verified — do not assume:**
- **No UI has been driven in a browser this session.** The final-warning banner (absent dismiss
  action, `problem` tone, `warningDismissed` interaction) is **vitest-only**.
- **No live agent has ever called `submit_checkpoint_notes`.** The whole notes design assumes a
  real model treats it as a tool call rather than replying in prose. Still untested.
- **`recall` has never been called by a live agent.**
- **The senderless peer path and the peer archive-successor path** remain API-test only.
- **`files_changed` has never been observed non-empty in production.**
- The five manual-verification tasks in the two nearly-done changes — **cannot** be done with
  available tooling.
- The new testbed has **no checkpoint config**, so no checkpoint path has been exercised on
  `proj-cddb0827` at all.

## Git state

Branch `hub-native-experience`, HEAD **`96575f5`**, **working tree clean, everything pushed**
(`git status --short` empty, no unpushed commits).

**6 commits this session**, `7a375eb..HEAD`:

| sha | what |
|---|---|
| `293ff14` | The spec edit that the previous commit's message described |
| `af6d45d` | Two proposals: the dismissal that cannot cost everything, and a model with two windows |
| `ec2d2bb` | A dismissal buys time, not the whole conversation |
| `40fb4eb` | A model may offer more than one context window, and the operator picks |
| `8f7c267` | Both changes become part of what the capabilities say they do |
| `96575f5` | There is no 1M Haiku: revert the context-window variants |

## Next steps

1. **Ask the operator to close the five manual-verification tasks.** Two changes archive on the
   back of it. Exact items, verified against the files:
   - `2026-08-04-hub-charcoal-visual-refresh/tasks.md` — **8.8** live keyboard pass on the
     composer control row (reachable, shows focus); **8.9** numeric contrast check of text,
     primary controls and the accent ring in both themes; **8.10** reduced-motion check.
   - `2026-08-04-hub-contextual-navigation/tasks.md` — **4.7** confirm save success *and* save
     failure are both reported in the section; **7.7** live check with reduced motion on (states
     still distinguishable, transitions suppressed).

   Available browser automation emulates `prefers-color-scheme` only, so it can do none of these.
2. **Decide the per-agent notes point** (open question 1 below) — small, self-contained, and the
   last checkpoint loose end.
3. **Exercise the checkpoint path on the new testbed** if you want it covered: it is currently
   `off`, so set a mode and threshold in project settings first. The final-warning banner has
   never been seen in a browser.
4. Then the biggest open front is `2026-07-30-hub-native-experience` (69 open), concentrated in
   *specification traceability and authoring* (19) and *agent identity, charters and skills* (15).
   **Read those two sections before proposing an order — it is several changes wearing one
   number.**

## Open questions for the user

1. **Per-agent notes point is not settable.** The project-level one is; the agent control sends
   `notes: null`. Left out rather than inventing a field they may not want per-agent.
2. **Should `.claude/handoffs/` stay tracked?** 109 files now. Unanswered across eight handoffs.
3. **The two model-less default runners** (`Claude (default)`, `Codex (default)`) sit alongside the
   two real ones on `proj-cddb0827`, because find-or-create won't match a runner with no model.
   Harmless, but four runners show in the UI. Worth pruning the defaults on project creation?
4. **`testbed/CHECKPOINT-TEST-GUIDE.md` still names the old project `proj-84d218db`** — it should
   be `proj-cddb0827`. Offered to update it; not yet done.
5. Carried: peer-thread grouping was deferred on 2026-08-08 and section 2 has landed, so the
   navigation tree will be busier. Raise as its own change when it becomes noticeable.
6. **23 skill templates in `src/agentweave/templates/skills/` are packaged but unreachable** —
   nothing installs them. Needs its own change.
7. Design says **titling should migrate onto the Worker**; it is still bespoke in
   `conversation_titles.py`.

## Read on resume

- `hub/hub/checkpoint_trigger.py` — `consider`'s ordering is load-bearing and was the session's
  one real defect; read the dismissed/final branch before touching anything above it.
- `hub/hub/checkpoint_policy.py` — `FINAL_WARNING_PERCENT` and `needs_final_warning`, including
  why the latter refuses a token count.
- `hub/hub/model_catalog.py` — the docstring now records why `[1m]` is not a window selector.
  Read it before anyone proposes a window picker again.
- `openspec/specs/conversation-checkpoint/spec.md` — the shipped capability, now carrying all
  three of this session's deltas.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — the 69 open tasks, if picking up
  next-step 4.
- `testbed/CHECKPOINT-TEST-GUIDE.md` — the operator's testing checklist; **stale project id**.
