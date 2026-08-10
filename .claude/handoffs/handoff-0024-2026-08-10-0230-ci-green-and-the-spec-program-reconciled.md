# Handoff: CI gates made green, and four overlapping plans reconciled into one program

**Date:** 2026-08-10T02:30 · **Branch:** hub-native-experience · **HEAD:** `dd1561f`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0023-2026-08-10-0030-final-warning-shipped-window-variants-reverted.md`
**Status:** chunk complete. 7 commits, all pushed. **Working tree clean.**

## Goal

The operator opened with strategic questions, not a task: what is the roadmap, is this mergeable,
and can they stop using T3 and develop AgentWeave inside AgentWeave. Answering those honestly
produced three pieces of work:

1. **Make CI's gates pass** — they had never run on this branch and all three were failing.
2. **Reconcile four documents planning the same territory** into one sequenced program.
3. **Propose the first change off that program** (A1).

The *why* for (2): the specification program is the stated differentiator, has been "next" since
2026-08-02, and had accumulated four overlapping plans in three vocabularies without shipping
anything. The operator decided **1.0 ships with the differentiator**, which makes that sequence the
length of the road to 1.0.

## Current state

### Shipped: CI hygiene (`e9ce328`, `db01f40`)

`ci.yml` runs ruff, black and mypy on push/PR **to master only**, so 315 commits had never been
through them. All three failed:

- **ruff (0.15) — 29 errors.** Two real: `try/except/pass` in `codex_appserver.py` (now
  `contextlib.suppress`), unused local in `test_project_lifecycle.py`. Twenty-four were SIM117 over
  stacked `with patch(...)` in tests — deliberate, because parenthesized multi-context `with` is a
  syntax error on 3.8/3.9 and the CLI suite still targets those. Two pre-existing
  `# noqa: SIM117` comments already recorded that rationale; it now lives once as a
  `[tool.ruff.lint.per-file-ignores]` entry for `tests/**` and `hub/tests/**`.
- **mypy (2.x) refused `python_version = "3.8"`** outright — it targets 3.10+. Config now says
  `"3.10"`; `requires-python` stays `>=3.8` and the CI test matrix covers real 3.8/3.9.
- **black (26) reformatted 78 files** — the accumulated 2024/2025 stable-style changes. Committed
  separately from the fixes so the five real changes stay readable.

Also added **upper bounds** on the three tools CI gates on (`black>=23.0,<27`, `ruff>=0.1.0,<0.16`,
`mypy>=1.0,<3`). Both failures arrived as a new tool major, not a code change. Floors stay low so
the 3.8/3.9 matrix legs can still resolve `.[dev]`.

### Written: the reconciliation (`06a2657`, `13b1db5`, `3f726e5`, `a2205ab`)

Four documents planned the same territory: `explorations/2026-08-03-specification-authority-technical.md`
(4 children), `changes/2026-08-07-spec-execution-coordinator/` (6 sections), umbrella §14 (19 tasks),
umbrella §15 (4 tasks). §14 maps onto the 2026-08-03 children almost one-to-one.

Now one roadmap with **three programs**:

| | Program | Contents |
|---|---|---|
| **A** | Surface unification | **A1** one chat surface · **A2** shell conformance audit |
| **B** | Specification and governance | **B0** aw-spec honesty repair · **B1** task transition machine · **B2** portable authority and identity · **B3** traceability/evidence/drift · **B4** rigor and gates · **B5** spec authoring workspace · **B6** AI augmentation · **B7** approval gates in conversation |
| **C** | Task screen | Deliberately split: how it *looks* → A2, what it *knows* → B3/B4 |

**The coordinator change was deleted, not archived** — it never described shipped behaviour. Its
contents are redistributed and the mapping is recorded in the roadmap's `[DECIDE #1]` section.

### Proposed, NOT implemented: A1 (`dd1561f`)

`openspec/changes/2026-08-10-one-chat-surface/` — proposal, design, tasks, `spec-chat-session`
delta. `npx openspec validate 2026-08-10-one-chat-surface --strict` → valid.

**`proposal.md` ends with `**Approved:** _pending_`. Implementation must not begin until the
operator fills that in.**

### Key findings, all evidence-backed

- **The shipped spec pipeline is dead end-to-end.** The six `aw-spec-*` skills are packaged in
  `src/agentweave/templates/skills/` and **nothing installs them** — no file under `src/` or `hub/`
  writes `.claude/skills/`. `hub/hub/api/v1/spec.py` has four routes, all reading `ProjectSpec`
  rows whose only former producer (the watchdog) is deleted.
- **`hub/hub/data/charters/spec.md` is seeded into every new project** and instructs agents to use
  all six absent skills (line 34), describes Hub file discovery that does not exist (lines 28–33),
  assigns an approval gate nothing enforces (line 15), and escalates to a "Tech Lead" that exists
  only by coincidence (lines 62, 83).
- **`openspec/specs/aw-spec-workflow/spec.md` requires behaviour from the deleted role subsystem.**
- **Task run attribution is overwritten.** `updated_by_run_id` (`tasks.py:194`) is a single mutable
  column, so the schema cannot distinguish the run that completed a task from the run that approved
  it. B1 must add an append-only transition record; author/reviewer separation is not a check that
  can be bolted onto existing columns.
- **`SpecChatPane.tsx` predates two architectural changes.** No `Composer` import; greps empty for
  `permission|question|checkpoint|Banner`; two user-facing "check the watchdog" strings
  (`SpecChatPane.tsx:74`, `SpecPage.tsx:227`); branches on `execution_confidence`, which
  `agent_trigger.py`'s docstring records as deliberately removed, so the branch is unreachable.
  **Two** bespoke trigger paths, not one (`handleSend` and `SpecPage.handleRepair`).
- **`SpecPage` has a "Repair manifest" button** sending an agent the literal string
  `Run aw-spec-reindex to repair spec/index.json`, targeting *"an idle agent named `spec` first"*.
- **Plan mode is not exposed at all.** `model_catalog.py`'s `permission_mode` control offers
  `acceptEdits`, `workspace`, `manual`, `bypassPermissions`. Claude's `--permission-mode plan` is
  absent.
- **`Conversation.origin` accepts `spec` and nothing produces it.** Writers are only `peer`,
  `operator`, `handoff`.

### Live environment

Hub **running on http://localhost:8010**, project **`proj-cddb0827`**, API key
`aw_live_58ab7d84a1bf7b34eb2d1b424875bacd` (header: `Authorization: Bearer <key>`).

**A probe spec document was pushed to the testbed this session** —
`spec/a1-probe.html`, via `POST /api/v1/projects/proj-cddb0827/project/specs/sync`. Left in place
deliberately: A1 needs a document to test against, and before it the Spec page returned
`{"specs":[],"home":null,"manifest":null}`. Delete it whenever.

## Files touched

Everything **committed and pushed**; `git status --short` is empty.

### Code (`e9ce328`)

- `pyproject.toml` — mypy `python_version` 3.8→3.10 with rationale; `[tool.ruff.lint.per-file-ignores]`
  for SIM117 in both test trees; upper bounds on black/ruff/mypy in `[dev]`.
- `hub/hub/codex_appserver.py` — added `import contextlib`; two `try/except/pass` → `contextlib.suppress`
  (the stdin close in `close()`, the turn-interrupt in `run_turn`).
- `hub/tests/test_project_lifecycle.py` — dropped unused `project =` assignment at ~line 124.
- `hub/tests/conftest.py` — moved `# noqa: N812` onto the aliased-import line itself; the closing
  paren keeps `# noqa: E402`.
- `tests/test_hub_commands.py` — removed one now-redundant `# noqa: SIM117`.

### Formatting only (`db01f40`)

- 78 files across `src/`, `hub/hub/`, `hub/tests/`, `tests/` — black 26, no behaviour change.

### Explorations — all new

- `openspec/explorations/2026-08-10-coordinator-terms-and-format.md` — coordinator cluster 1
  (tasks 1.1–1.4) plus an early answer to 1.16.
- `openspec/explorations/2026-08-10-specification-and-surface-program-roadmap.md` — **the orientation
  document.** Three programs, ten changes, both decisions resolved, and the standing
  verification-ownership directive. Edited after creation to resolve `[DECIDE #1]` and `[DECIDE #2]`
  and to add the directive section.
- `openspec/explorations/2026-08-10-authoring-flow-without-skills.md` — why skills decompose; carries
  the retired change's eight unanswered questions.
- `openspec/explorations/2026-08-10-charters-phases-and-the-spec-on-ramp.md` — explore session
  capture: charter/phase split, agent-vs-conversation, plan-vs-spec, document-owns-phase,
  discoverability, the parked steward agent.

### Deleted (`3f726e5`)

- `openspec/changes/2026-08-07-spec-execution-coordinator/` — `.openspec.yaml`, `proposal.md`,
  `tasks.md`.

### New change (`dd1561f`)

- `openspec/changes/2026-08-10-one-chat-surface/proposal.md`
- `openspec/changes/2026-08-10-one-chat-surface/design.md` — six decisions plus the fixture note.
- `openspec/changes/2026-08-10-one-chat-surface/tasks.md` — **section 5 agent-verifiable, section 6
  the human test guide.** First change written under the new directive.
- `openspec/changes/2026-08-10-one-chat-surface/specs/spec-chat-session/spec.md` — three ADDED
  requirements.

### Outside the repo

- `C:\Users\huida\.claude\projects\C--Users-huida-Documents-projects-AgentWeave\memory\feedback_specs_must_carry_test_guides.md` — new memory.
- `...\memory\MEMORY.md` — one index line appended.

## Key decisions

1. **1.0 ships with the differentiator.** Operator overruled a recommendation to defer spec
   traceability to 1.1. Consequence: B2–B4 are release-blocking, and the umbrella
   `2026-07-30-hub-native-experience` is now the **last** thing to close, not a thing to close soon.
2. **Merge and launch are separable.** `publish.yml` fires on a GitHub *release* with a `v*` tag, so
   merging publishes nothing to PyPI. Only `hub-image.yml` auto-publishes (a ghcr Hub image on any
   master push touching `hub/**`). Operator chose **hygiene only, no PR yet**.
3. **Three programs, A first.** Rejected one bundle: the spec program is months, and bundling means
   the UI stays old until all of it lands. Rejected building B first: A1 is a prerequisite, because
   B's authoring story runs through a pane that cannot render a question or approval card, so
   deferring A1 *causes* the double-build it appears to avoid.
4. **Program A splits by what B can invalidate.** A1 (delete duplicate chat, mount `Composer`, shared
   resizer) cannot be invalidated — it is deletion and reuse. A2/spec-screen information architecture
   depends on data B2/B3 create, so it folds into **B5** — which is where the archived
   mock-alignment change already said it belonged.
5. **HTML stays the spec format** (operator decision).
6. **No visual mock.** Rejected mocking the spec screen: the identity already lives in code
   (`Composer`, `BannerStack`, `Button`, `Icon`, the token set), and a new mock is a second
   description to reconcile — which is how `components/spec/` drifted originally. Navigation inside
   the document is already built (`specBridge.ts`: `toc-ready`, `active-section`, `postScrollTo`,
   path-allowlisted link resolution). **One page of design still comes first in B5** — the bridge
   interaction contract, because the iframe is a security boundary (`sandbox="allow-scripts"`, no
   `allow-same-origin`, "message identity replaces origin checking").
7. **The coordinator change is retired and deleted, not archived** — an archived change reads as
   shipped behaviour and this never was. Same rule applied to the reverted window variants on
   2026-08-10.
8. **Skills decompose, then get deleted** — this replaced both options originally offered.
   `.claude/skills/` is **Claude-only** and AgentWeave is multi-runner: a Codex agent cannot invoke
   `aw-spec-propose` at all. The runner-agnostic mechanism already ships —
   `agent_trigger.py:352` writes `.agentweave/context/<agent>.md` every turn for both runners. So:
   procedure → coordinator phase machine, format contract → Hub parser that refuses, judgment →
   charter.
9. **Charter is accountability; phase is activity.** Rejected "charters are vestigial" — the
   operator's underwriter/approver example is two accountabilities, which is G2 with a business
   meaning. Software misleads because one model can do every *activity*.
10. **A conversation never becomes an agent.** An agent is a unit of concurrency, isolation and
    accountability; a conversation is a unit of context. One agent speccing in one thread and
    implementing in another is sound **when the operator is the reviewer**.
11. **Phase belongs to the document, not the thread.** This dissolved the detection problem: both
    "promote" (human classifies) and "infer" (machine classifies) fail, because "add SSO" is either
    kind of conversation depending on what the user wants next. A thread is in a phase because a
    document is open in it. Consequence: `origin` may be the wrong axis; the durable relationship is
    a link.
12. **Ship plan mode alongside spec mode.** Different altitudes — plan is a per-run posture about
    actions, spec is a document-level phase about behaviour; plan is used *inside* the apply phase.
    Plan belongs in the Permissions pill as one more `ControlValue`; phase sits near the document.
13. **Discoverability: inversion, not interruption.** Rejected a checkpoint-shaped banner (nags;
    dismiss-forever was already a problem for the *urgent* case). Chose: every thread starts in
    explore, which is indistinguishable from ordinary conversation, so nothing about a typo fix
    changes. The real decision is explore→propose, where the agent can offer a *draft* rather than
    homework. Coverage reporting becomes the safety net, not the mechanism.
14. **Explore needs no new artifact.** Conversations are durable; `submit_checkpoint_notes` →
    `Checkpoint`/`CheckpointNote` already distils one. It has never been called by a live agent; the
    propose phase would be its first real user.
15. **A1 reuses the agent's conversation and produces no `origin="spec"`** (design.md Decision 1).
16. **The "Repair manifest" button is removed in A1**, and a deterministic reindexer goes to B2 —
    writing a manifest repairer before B2 defines the manifest format is backwards. Recorded:
    `aw-spec-reindex` is the clearest case in the product of a "skill" that should never have been a
    model prompt.
17. **B6 splits.** Advisory *in-flow* (coordinator consults a model at a gate) is high-risk and
    blocked on the binding/advisory classification. Advisory *out-of-flow* (the steward) has no
    authority, needs no governance design, and can ship much earlier.
18. **B2 must not freeze the parse contract** until B3/B4 state their requirements on it — every
    element in the format exists to serve a downstream feature.

## Constraints and user directives (verbatim)

**From this session:**
- *"Should I improve agentweave first in this branch before merging? Because this merge will be a
  big depart from the old version. Will be a totally new app. My instinct is to launch a polished
  version. 1.0 so we need to improve more things."*
- Chose **"1.0 — the differentiator ships or nothing does"** and **"Hygiene only, no PR yet."**
- *"I want a full reconceliation. We also have to take a look at the UI. Because still follows the
  old UI. For example the left panel collapses, the chat box on the right is the old one. So the UI
  needs a full revamp as well to follow the new aesthetic. Should we also look at the task screen as
  well since it will be closely related to the spec?"*
- *"The spec should still be generated as html"*
- Chose **"Three programs, A first."**
- *"Now that I think why mock if we can build it already and debug it?"*
- *"I want to fold the coordinator change inside this one. So take what was explored and it's useful,
  we can do even more exploration on it and retire the old change."*
- *"first I think we have to many we need to cut some of those"* — on the 21 charters.
- *"the charter exists to give instructions so I can use agentweave for more then developing. I can
  use as an underwriter and another agent as an approver"* — **the reason charters survive.**
- *"I would also want this agent to be triggered by event in the agentweave hub not cron jobs. Like,
  upon handoff do some stuff, or creating a thread, or an agent, finishing a spec. Moving a spec to
  done, archiving… But it does not need to be built now."*
- **STANDING DIRECTIVE:** *"when creating the spec we have to think how to manually test this. How
  the agent can test what's the expected behavior and what can only be done by the user to create a
  guide for the user to test. Also take a hard note on this because we should improve the agentweave
  spec with these directives."* — memory `feedback-specs-must-carry-test-guides`; roadmap "Standing
  directive" section; first applied in A1 `tasks.md` §5/§6.
- *"Kind of lost"* — **the operator is sensitive to volume.** Answer briefly; point at one file.

**Carried and still binding:**
- *"Wait. Are you already implementing? Should we dive in first…"* — **lay out the plan before
  building anything non-trivial.**
- *"What is taking so long?"* — sensitive to wall-clock. `pytest hub/tests/` ~5:00; `npx vitest run`
  ~22s.
- *"no need for backups everything is test env"*
- *"B. fixed back to the agent's conversation. Yes, no agent deletion. Just archive."*
- *"okay let's ok with i for v1 but we need to take a hard note on this"* — memory
  `project_checkpoint_trigger_prompts_provisional`.
- *"I don't want it to be colorful it should be like the chat box but maybe a little lighter"*
- From `CLAUDE.md`: never create `.agentweave/`, `agentweave.yml` or `spec/` at the repo root; stage
  paths explicitly; openspec never aw-spec skills; `Icon` is the only icon system;
  `approve_tool_call` keeps **no return annotation**; `hub/hub/static/ui` is a committed artefact
  refreshed after `npm run build` and confirmed with `diff -rq`; never mark a task complete on the
  strength of a plan existing.
- From memory: commit each completed checkpoint without asking; live-verify prior claimed work on
  resume; ask the operator for agent + model choice when setting up agents.

## Dead ends

**New this session:**
- **PowerShell here-strings break on bash-style quote escaping.** `git commit -q -m @'…'@`
  containing `'"'"'` fails with `error: pathspec 'the' did not match`. **Use the Write tool to
  create a message file, then `git commit -F <file>`.** This worked every time.
- **`Select-String -Pattern "'plan'|\"plan\""` is an invalid regex** in PowerShell — the escaping
  collapses to a trailing backslash. Use the Grep tool instead.
- **PowerShell cwd persists between calls.** `npx vitest run` left it at `hub/ui`, and the next
  `git diff -- README.md docs/` silently returned nothing because the paths resolved under
  `hub/ui/`. **Always `Set-Location 'C:\Users\huida\Documents\projects\AgentWeave'` first.**
- **The spec API is not at `/api/v1/specs`.** `spec.py`'s router carries `prefix="/project"` under
  `project_resources_router`, so the real path is
  `/api/v1/projects/{project_id}/project/specs`. Query `http://localhost:8010/openapi.json` and
  filter paths rather than guessing.
- **`pytest -q` buffers all output**; a background run's file stays empty until it exits. Use
  `TaskOutput` with `block=true` rather than polling the output file.
- **mypy's missing `types-PyYAML` was a local-only failure** — it is already declared in `[dev]`, so
  CI has it. Installed locally to get a truthful signal. Do not "fix" it in `pyproject.toml`.
- **`black --check` emits a stderr warning** ("Python 3.11 cannot parse code formatted for Python
  3.12") because `target-version` includes py312. Exit code is still 0; PowerShell wraps the stderr
  as `NativeCommandError`. Not a failure.

**Carried and still true:**
- **`ORDER BY EventLog.id` does not order by recency** — order by `timestamp`.
- **`openspec` CLI cannot handle date-prefixed change names for sync/archive.** Do it by hand.
  `npx openspec validate <name> --strict` (no `change/` prefix) does work.
- **`openspec validate` wants SHALL/MUST on the *first line* of a requirement body.**
- **`npm run lint` does not work at all.** ESLint 9 needs a flat config the repo lacks; `tsc` checks.
- **`pytest hub/tests/ tests/` together fails collection** — both trees have `tests/__init__.py`.
  Run separately, as `make test-all` does. Pre-existing.
- **The default `python` on PATH has no pytest** — use
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **`hub/tests/conftest.py` forces in-memory SQLite**, so the suite never touches the live database.
  Safe to run tests with the Hub up.
- **The Hub API rejects `X-API-Key`** — use `Authorization: Bearer <key>`.
- **Adding a hook to a component breaks every test that mocks that api module** — patch the mocks in
  the same commit.
- `extra: "forbid"` rejects a forbidden **key** regardless of value; there is **no `db_session`
  fixture** — use `async_session_factory()`.

## Verification

**Ran, with real output:**
- `ruff check src/ hub/ tests/` — 29 errors → **All checks passed!**
- `black --check src/ hub/hub/ hub/tests/ tests/` — 78 would reformat → **286 files unchanged.**
- `mypy src/` — config error → **Success: no issues found in 22 source files.**
- `pytest hub/tests/` — **1273 passed, 10 skipped** (5:11). Re-run after the black sweep:
  **1273 passed, 10 skipped** (5:01). Unchanged.
- `pytest tests/` — **372 passed, 3 skipped** (16s). Re-run after black: **372 passed, 3 skipped.**
- `npx vitest run` — **640 passed / 73 files** (22s). *Baseline only — run before any code change.*
- `npx openspec validate --specs --strict` — **27 passed, 0 failed.**
- `npx openspec validate 2026-08-10-one-chat-surface --strict` — **valid.**
- **Live against `:8010`:** `/health` 200 · projects → `proj-cddb0827` ·
  `GET .../project/specs` → `{"specs":[],"home":null,"manifest":null,...}` ·
  `POST .../project/specs/sync` with `{path,content}` → 200 ·
  `GET .../project/specs` → one entry, `state:"unindexed"`, `home` resolved ·
  `GET .../project/spec?path=…` → 248 bytes returned.

**Explicitly NOT verified — do not assume:**
- **CI has still never run on this branch.** `ci.yml` triggers only on push/PR to `master`. **322
  commits** have seen no Linux, no macOS, and no Python 3.8/3.9/3.10/3.12. The gates are green
  *locally on Windows/3.11 only*.
- **No UI was driven in a browser this session.** The probe document was verified through the
  **API only** — it has *not* been confirmed to render on the Spec page.
- **A1 is not implemented.** Proposal only, and unapproved.
- **`npm run build` was not run** and `hub/hub/static/ui` was not touched — no frontend source
  changed.
- Carried: no live agent has ever called `submit_checkpoint_notes` or `recall`; `files_changed` has
  never been observed non-empty; the checkpoint final-warning banner has never been seen in a
  browser; the five manual-verification tasks in the two nearly-done changes remain unrun.

## Git state

Branch `hub-native-experience`, HEAD **`dd1561f`**, **working tree clean, everything pushed**
(`git status --short` empty; `git log origin/hub-native-experience..HEAD` empty).
**322 commits ahead of master, 0 behind.**

**7 commits this session**, `57f4d94..dd1561f`:

| sha | what |
|---|---|
| `e9ce328` | The three CI gates run clean, and a new tool major cannot silently break them |
| `db01f40` | black 26 over the tree, so the format gate has something stable to check |
| `06a2657` | Cluster 1 of the coordinator exploration: the pipeline it would execute is dead |
| `13b1db5` | One sequence to replace four plans for the same territory |
| `3f726e5` | Retire the coordinator change; the authoring flow is not a skill problem |
| `a2205ab` | Charter is accountability, phase is activity, and the phase belongs to the document |
| `dd1561f` | Propose A1: one chat surface, and make verification ownership part of authoring |

## Next steps

1. **Ask the operator to approve or amend A1.** `openspec/changes/2026-08-10-one-chat-surface/proposal.md`
   ends with `**Approved:** _pending_`; edit that line to `**Approved:** 2026-08-__` before any
   implementation. Nothing in that change may start first — including task 1.1.
2. **Once approved, start A1 task 2.1**: extend `_render_hub_agent_context` in
   `hub/hub/api/v1/agents.py` to include the spec document the operator is viewing when the trigger
   request supplies one, rendering nothing when it does not.
3. **Offer the one-line `ci.yml` change again** — add `hub-native-experience` to
   `on.push.branches` alongside `master`. Raised twice, unanswered both times. It touches `master`
   not at all and is the only way the 3-OS × 5-Python matrix ever sees this branch before merge.
4. **Optional, high value for ~20 minutes of operator time:** rewrite the five stuck
   manual-verification tasks in A1 `tasks.md` §6's *do this → expect this → failed if this* format —
   `2026-08-04-hub-charcoal-visual-refresh` 8.8–8.10 and `2026-08-04-hub-contextual-navigation` 4.7,
   7.7. That would archive two changes.

## Open questions for the user

1. **Approve A1?** Blocking next-step 2.
2. **The `ci.yml` branch trigger** — yes or no.
3. **How many charters, and which non-software domains should the starter set demonstrate?** The
   operator said to cut the 21; the target number and the domain examples are undecided. Blocks B0.
4. **Is "explore" a phase, or just the absence of one?** Affects B5's phase model.
5. **Should the propose offer come from the agent mid-turn, or from the machine at a threshold?**
   Very different failure modes when the model is wrong.
6. Carried and still unanswered across nine handoffs: **should `.claude/handoffs/` stay tracked?**
   Now 110 files.
7. Carried: the two model-less default runners on `proj-cddb0827`; `testbed/CHECKPOINT-TEST-GUIDE.md`
   still names the old project `proj-84d218db`; peer-thread grouping deferred 2026-08-08; titling
   should migrate onto the Worker.

## Read on resume

- `openspec/explorations/2026-08-10-specification-and-surface-program-roadmap.md` — **read this
  first.** The orientation document: three programs, ten changes, both decisions resolved, and the
  standing verification-ownership directive.
- `openspec/changes/2026-08-10-one-chat-surface/proposal.md` and `design.md` — the pending change and
  its six decisions. `design.md`'s closing section records how to get a document onto the Spec page.
- `openspec/explorations/2026-08-10-charters-phases-and-the-spec-on-ramp.md` — the charter/phase
  split and the open questions in §6 and §7. Needed before B0 or B5.
- `hub/ui/src/components/spec/SpecChatPane.tsx` and `SpecPage.tsx` — what A1 deletes; read before
  implementing it.
- `hub/hub/api/v1/agent_trigger.py` around lines 330–390 — the canonical-context materialisation A1
  task 2.1 extends.
- `openspec/explorations/2026-08-03-specification-authority-technical.md` — **retained as the
  technical design source for B2–B5.** Long; read when B2 starts, not before.
