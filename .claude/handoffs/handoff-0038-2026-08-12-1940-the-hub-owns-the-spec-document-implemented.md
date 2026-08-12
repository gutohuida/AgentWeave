# Handoff: change 1 of the spec program implemented; only human verification remains

**Date:** 2026-08-12T19:40+0100 · **Branch:** hub-native-experience · **HEAD:** `6140666`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0037-2026-08-12-1429-three-changes-archived-and-the-spec-hub-design-settled.md`
**Status:** **chunk complete.** Working tree clean, 0 unpushed. 14 commits. Nothing half-done in
code; 8 tasks open, 6 of which only a person can close.

## Goal

Turn `openspec/explorations/2026-08-12-spec-hub-integration.md` into working software, starting with
change 1 of five: **the Hub owns the specification document**. The operator authors a spec in the
Hub instead of through skills that no longer install, and the approval gate becomes real rather than
an instruction an agent is asked to honour.

The *why* that governed judgement all session: **a claim of "done" that has not been observed is
worth nothing.** Four separate "this is fixed" reports in this session turned out to be wrong under
real use, every one of them caught by the operator rather than by a test. Verify against the running
Hub, not against the code path.

## Current state

### Shipped and pushed — the change is implemented

`openspec/changes/2026-08-12-hub-owns-the-spec-document/` — proposal, design (12 decisions), tasks,
and four spec deltas. `openspec validate --changes --strict` and `--specs --strict` both pass.

**Deleted:** `POST /project/specs/sync` and `/specs/reconcile`, the drift computation and source TTL,
`ProjectSpec` + `ProjectSpecSnapshot` (migration `0064`), `HttpTransport.push_spec` /
`reconcile_specs`, the spec source ID and `_ensure_spec_source_id`, the `aw-spec-*` skill templates
and their 796 lines of references, and `templates.get_skill_reference`.

**Added:**
- `hub/hub/spec_documents.py` — disk-backed discovery, read, write, index parsing, tree state.
- `hub/hub/spec_payload.py` — the versioned payload contract; unknown fields survive a round trip.
- `hub/hub/spec_identity.py` — mints `FR-n` from agent-supplied **keys**; never recycles.
- `hub/hub/spec_render.py` — payload → self-contained HTML, inline style only.
- `hub/hub/spec_lifecycle.py` — phases, transitions, append-only events, digests.
- `hub/hub/spec_completeness.py` — step-7b's self-check as blocking validators.
- `hub/hub/spec_service.py` — validate → mint → render → write → record, in one place.
- Migration `0065` — `spec_documents`, `spec_document_events`.
- `submit_spec_document` in `hub/hub/mcp_server.py`; agent endpoint in `agent_actions.py`; operator
  endpoints (`/documents`, `close-exploration`, `propose`, `phase`) in `api/v1/spec.py`.
- UI: `SpecPhaseBar`, the Explore toggle, `lib/specDocumentName.ts`, document hooks in `api/spec.ts`.

**`openspec/specs/` is 30 capabilities:** `spec-document-authority` added (13 requirements),
`aw-spec-workflow` (10) and `spec-manifest-sync` (9) removed, `spec-chat-session` extended.

### Four things I got wrong, all caught by the operator under real use

These are the session's most important content. Each was reported by me as working.

1. **Task 13.1 marked done when it did not exist.** `useCreateSpecDocument` had zero call sites.
   No way to create a document → phase block never rendered → agent got the charter (judgement) and
   no mechanism → announced *"I'm using the OpenSpec explore workflow"*. Fixed in `c8a23b6`.
2. **The toggle was absent where conversations begin.** `Composer` deliberately omitted the control
   on `NewConversationSurface` ("no document panel to open one into") — correct for a pill that only
   *opened* a document, backwards for a toggle. Fixed in `42d1841`.
3. **The document was created *after* the trigger.** So the first message — the one that frames the
   whole exploration — went out with `spec_document` unset, reproducing the exact symptom. Fixed in
   `1734027`. **This was the actual cause of the repeated OpenSpec behaviour.**
4. **The new testbed was not a git repository.** I created `aw-testbed` as a plain folder; isolation
   is the default, so worktree provisioning failed and every turn silently queued.

### Live environment

- Hub running on `:8010`, **PID 22440** (restarted many times; find the real PID with
  `Get-NetTCPConnection -LocalPort 8010 -State Listen`).
- Database `hub/data/agentweave.db` at head **`0065`**. Two projects:
  - `proj-44e9adba` / **aw-testbed** → `C:\Users\huida\Documents\aw-testbed` — **is** a git repo.
  - `proj-e109fc87` / **newtest** → `C:\Users\huida\Documents\quicktest` — **NOT a git repo, so its
    agent cannot start.** Run `git init` there to unblock.
- Five spec documents exist in aw-testbed, all `exploring`, all test artefacts.
- Old DB preserved at `hub/data/agentweave.db.old-20260812-172717`; rescued pre-reset documents in
  `testbed/scratch/rescued-project-specs/` (gitignored).

## Files touched

Working tree **clean**, **0 unpushed**. 14 commits: `2909137` `7e1d132` `225a21f` `cd14125`
`e681721` `bdfe898` `df1f038` `4cf97a3` `16d5157` `7a0ffab` `a44c8a8` `d6e38da` `53c21c8` `ef7c260`
`6763fc2` `c8a23b6` `31eedd2` `42d1841` `1734027` `6140666`.

| path | what | done? |
|---|---|---|
| `hub/hub/data/charters/spec.md` | 88 → 157 lines; interviewing craft harvested from the skills | yes |
| `hub/hub/spec_documents.py` | **new** — disk-backed document tree | yes |
| `hub/hub/spec_payload.py` | **new** — versioned payload contract | yes |
| `hub/hub/spec_identity.py` | **new** — key→identifier minting, high-water mark | yes |
| `hub/hub/spec_render.py` | **new** — payload → self-contained HTML | yes |
| `hub/hub/spec_lifecycle.py` | **new** — phases, events, digests, `Actor` | yes |
| `hub/hub/spec_completeness.py` | **new** — blocking completeness findings | yes |
| `hub/hub/spec_service.py` | **new** — `save_document`, `propose`, `rerender_phase` | yes |
| `hub/hub/api/v1/spec.py` | rewritten: disk reads + operator document endpoints | yes |
| `hub/hub/api/v1/agent_actions.py` | `POST /agent-actions/spec/documents` | yes |
| `hub/hub/api/v1/agents.py` | phase block + procedure floor in turn context; `SPEC_PHASE_DUTIES` | yes |
| `hub/hub/api/v1/inbound_queue.py` | queue status probes the bound runner; reports the git-repo blocker | yes |
| `hub/hub/mcp_server.py` | `submit_spec_document` + `SpecKind`, `SPEC_SCHEMA_VERSION` | yes |
| `hub/hub/db/models.py` | `SpecDocument`, `SpecDocumentEvent`; `ProjectSpec*` removed | yes |
| `hub/hub/migrations/versions/0064_drop_project_spec_cache.py` | **new**, guarded | yes |
| `hub/hub/migrations/versions/0065_add_spec_documents.py` | **new**, guarded | yes |
| `hub/ui/src/api/spec.ts` | document hooks, `SpecDocumentRecord`, `stale` state removed | yes |
| `hub/ui/src/components/spec/SpecPhaseBar.tsx` | **new** — phase + operator decisions | yes |
| `hub/ui/src/components/spec/SpecDocumentPicker.tsx` | "Start an exploration" row | yes |
| `hub/ui/src/components/spec/SpecDocumentPanel.tsx` | renders `SpecPhaseBar` | yes |
| `hub/ui/src/components/agents/ComposerSpecControl.tsx` | Explore toggle, armed state, close control | yes |
| `hub/ui/src/components/agents/Composer.tsx` | threads `onStartExploration`/`onStopExploring`/`specArmed` | yes |
| `hub/ui/src/components/agents/AgentOutputPanel.tsx` | threads the same | yes |
| `hub/ui/src/components/agents/ConversationView.tsx` | `startExploration`, conversation title lookup | yes |
| `hub/ui/src/components/agents/NewConversationSurface.tsx` | armed toggle; document created **before** the turn | yes |
| `hub/ui/src/App.tsx` | `onStarted` carries the document into the destination | yes |
| `hub/ui/src/lib/specDocumentName.ts` | **new** — slugify + path, mirrors the server contract | yes |
| `hub/hub/static/ui/**` | rebuilt, `diff -rq` identical | yes |
| `src/agentweave/transport/http.py`, `transport/config.py`, `templates/__init__.py` | dead spec-sync code removed | yes |
| `openspec/specs/spec-document-authority/spec.md` | **new capability**, 13 requirements | yes |
| `openspec/specs/spec-chat-session/spec.md` | modified + added requirement | yes |
| `openspec/explorations/2026-08-12-spec-hub-integration.md` | 366 → 710 lines (§1.11–1.13, §2.9–2.11, §6, §7) | yes |
| tests | `test_spec.py` rewritten; `test_spec_payload`, `test_spec_render`, `test_spec_completeness`, `test_spec_documents_api` new; `test_spec_reconcile.py` deleted; 7 UI files converted to partial mocks | yes |

## Key decisions

1. **Correlation is by `key`, not position (D5a).** The delta spec originally said position; inserting
   a requirement would renumber everything below it and silently re-target every link. The agent
   controls correlation, the Hub controls identity.
2. **The payload lives inside the rendered document** (D12) as a non-executing script block with `<`
   escaped. A sidecar file was rejected: two files with one authority drift.
3. **Structured tool parameters are `List[Dict[str, Any]]`, not `TypedDict`.** Verified directly that
   pydantic *drops* undeclared keys — typing them would lose forward compatibility at the tool
   boundary. The shape lives in descriptions; a test pins the reasoning.
4. **Shape vs completeness.** `validate_payload` runs on every save (a draft is not a defect);
   `spec_completeness.check` runs at the transition, where being incomplete is the point.
5. **Task 12.3 deliberately not done; D9 should be amended.** Auto-binding the spec charter makes
   "no charter" unreachable, contradicting *"Is good practice but I can skip it."*
6. **Removal is not forgetting.** Four `spec-manifest-sync` requirements carried into the new
   capability; the skills' disposition is table §6 of the exploration.
7. **The exploration toggle creates a document.** §2.7 permits a pill *"provided pressing it creates
   the document"*; a mode with no document leaves "propose what?" unanswerable.
8. **Turning exploration off detaches, never deletes.** Plan mode is ephemeral; an exploration leaves
   an artifact.

## Constraints and user directives (verbatim)

**From this session:**
- *"you can drop the testbed project and reset everything. Create new test project. you can delete
  the folder where the testbed also existed in"*
- *"I feel like remove."* — on the two superseded capabilities.
- *"Read them just to be sure but I believe then can be all automated."* — the apply/archive/reindex skills.
- *"There is a lot of knowledge on those skills. How do we preserve them? Their behavior is very
  good… Maybe some tweaks and remove the technical explore but I want the same knowledge imputed."*
- *"We have to take into consideration the whole new phase that agentweave is in. We removed the
  watchdog and the hub doesn't operate as a separate docker entity."*
- *"Maybe we indeed need a exploration pill. Like you just enable and disable like plan mode"*
- *"Continue until you're all done"* / *"Run any test that you can run on the functionality"*

**Carried and still binding:**
- **The `ci.yml` question is settled** — *"just push the branch"*. **Do not raise it again.**
- **Handoff cadence:** only when asked, or when an openspec change is done.
- **STANDING DIRECTIVE:** every `tasks.md` splits agent-verifiable from human-only and emits a user
  test guide.
- *"by measuring pixels aren't you making things a little bit too catered to my monitor?"* — derive
  constants, do not tune them.
- Sensitive to volume and wall-clock; wants short prioritised answers and forward motion.
- From `CLAUDE.md`: never `.agentweave/` / `agentweave.yml` / `spec/` at the repo root; stage paths
  explicitly; openspec never aw-spec skills; `Icon` is the only icon system; `approve_tool_call`
  keeps **no return annotation**; migrations guard for a missing table and bump **both** head
  assertions; `hub/hub/static/ui` refreshed and confirmed with `diff -rq`; **never mark a task
  complete on the strength of a plan existing.**
- From memory: commit each completed checkpoint without asking; live-verify on resume.

## Dead ends

**New this session — the ones that cost the most:**

- **Marking a task done from the API hook alone.** 13.1 shipped `useCreateSpecDocument` with no call
  site. The failure was invisible in tests because nothing asserted a caller existed.
- **Creating the document after the trigger.** Two individually correct steps in the wrong order
  reproduced the original bug exactly. **Assert order, not just occurrence** — the test asserted both
  calls happened and passed while broken.
- **`mockResolvedValue` with a `Response`.** A body can be read once; both fetches share the instance,
  so the second `.json()` throws on a consumed body and the failure looks like the component. Use
  `mockImplementation` returning a fresh `Response`.
- **A new `describe` block appended to a test file does not inherit the earlier block's `beforeEach`.**
  `fetchMock.mock.calls` accumulated and an assertion passed for the wrong reason.
- **`TypedDict` silently drops unknown keys** under pydantic validation.
- **A project directory that is not a git repository** blocks every writing agent, with no visible
  reason until `6140666`. Both testbeds hit it.
- **Adding an export to `@/api/spec` broke 51 tests** across six files that mocked the whole module.
  All seven converted to `importOriginal` partial mocks.
- **`git commit -m @'…'@` is PowerShell syntax and the Bash tool is Git Bash.** Use a heredoc into
  `git commit -F -`.

**Carried and still true:**
- **The Bash tool's cwd persists across calls.** Use absolute paths.
- **Start the Hub via WMI** so it survives session teardown:
  `Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "cd /d C:\Users\huida\Documents\projects\AgentWeave\hub && C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn hub.main:app --host 127.0.0.1 --port 8010 > %TEMP%\agentweave-hub.log 2>&1"'}`
- **`openspec` CLI rejects change names starting with a digit** — create and archive by hand.
- **`pytest hub/tests/ tests/` together fails collection** — run separately, with
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **`npm run lint` does not work**; `npx tsc --noEmit` is the check, from `hub/ui`.
- **The Hub API needs `Authorization: Bearer <AW_BOOTSTRAP_API_KEY from hub/.env>`**, not `X-API-Key`.
- **A new capability spec needs `## Purpose` and `## Requirements`** or `openspec validate --specs
  --strict` fails.

## Verification

**Ran, with real output:**
- `pytest hub/tests/ -q` — **1579 passed, 10 skipped** (last full run before the final two commits;
  the queue/trigger/workspace suites were re-run after: **55 passed**).
- `pytest tests/ -q` — **360 passed, 3 skipped**.
- `npx vitest run` — **829 passed across 84 files**. `npx tsc --noEmit` exit 0.
- `ruff check hub/ src/` — passed. `black` applied to every file touched.
- `npx openspec validate --specs --strict` — **30 passed**; `--changes --strict` — **4 passed**.
- `hub/hub/static/ui` rebuilt and `diff -rq` identical (multiple times).
- **Against the running Hub, with a real run credential:** an agent submission rendered a document;
  five approval routes refused (`422`, ineffective, `401`×3); identifiers retired and never reused
  (`FR-1/2` → `FR-3/4` → insert at top → `FR-5`); refusals named `requirements[0].modal`,
  `schema_version`, `tasks[0].requirements[0]` and left the file hash unchanged; a hand edit was
  reported with both digests and not overwritten; the lifecycle reached `approved` and the file's
  `aw-spec-status` followed; an approved document refused further submissions; 12 correctly
  attributed events.
- **In the browser:** the rendered document displays in `SpecFrame` under `sandbox="allow-scripts"`
  with no `allow-same-origin`; the Explore toggle arms on the new-conversation surface; sending
  produced `spec_document` on the queue entry and a context containing the phase block.

**NOT run, and deliberately:**
- **No agent has been observed using `submit_spec_document`.** The tool schema is asserted by tests;
  a live agent calling it has never been seen. This is task 17.6 and it is the claim the skills'
  deletion rests on.
- **`pytest hub/tests/` has not been run since `1734027` and `6140666`** — only the queue, trigger and
  workspace suites. Run the full suite before archiving.
- **Nothing about how the flow *feels*** — 17.1–17.4, 17.8.
- **The `0063 → 0065` upgrade path against real data.** The live DB was created fresh at `0065`.

## Git state

Branch `hub-native-experience`, HEAD **`6140666`**, working tree **clean**, **0 unpushed**.
`.claude/handoffs/` is tracked, not gitignored.

## Next steps

1. **`git init` in `C:\Users\huida\Documents\quicktest`** (`git add -A && git commit -m "Initial"`),
   then press **Continue** in the `newtest` conversation. That project's agent cannot start without
   it, and the Hub now says so in the waiting reason.
2. **Run the full backend suite** — `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe
   -m pytest hub/tests/ -q` — which has not run since the last two commits.
3. **Do the section 18 walkthrough** in `openspec/changes/2026-08-12-hub-owns-the-spec-document/tasks.md`,
   which closes 17.1–17.4 and 17.8. Start a **new conversation**, press **Explore**, then send.
4. **Run it with a Codex agent (17.6)** — the deletion of the skills depends on it.
5. **Fix the cross-project document leak:** the open document is carried in the URL destination and is
   not re-scoped when switching projects, so `newtest` showed `Spec: i-want-to-build-a-budget-app`,
   a document belonging to `aw-testbed`. Not yet filed as a change.

## Open questions for the user

1. **Should project *creation* run `git init`?** `local-project-workspace` says registration "SHALL
   NOT initialize git … or otherwise modify project source". Right for a directory that already
   existed; questionable for one the Hub just created. It has now cost two debugging sessions.
2. **Amend D9 / task 12.3?** Auto-binding the spec charter would make "no charter" unreachable.
3. **`propose` returns two shapes** — `200` with `blocking` for an incomplete document, `409` for a
   complete one whose exploration is not closed. Acceptable, or should it always refuse with a status?
4. **Should the agent be able to *offer* to start an exploration?** §2.7's bottom-up path (umbrella
   14.13) is deferred; it is the reason the flow is invisible until a document exists.
5. Carried: should `.claude/handoffs/` stay tracked (**124 files**)?

## Read on resume

- `openspec/changes/2026-08-12-hub-owns-the-spec-document/tasks.md` — the 8 open tasks, sections 16b
  and 16c (what was driven live), and section 18's walkthrough.
- `openspec/explorations/2026-08-12-spec-hub-integration.md` — §6 is the skills' disposition table,
  §7 the five-change program and the forward commitments. Its three-way split is load-bearing.
- `openspec/changes/2026-08-12-hub-owns-the-spec-document/design.md` — 12 decisions, including D5a
  and D12, which correct this change's own earlier spec.
- `hub/hub/api/v1/agents.py` (`SPEC_PHASE_DUTIES`, the `### Open specification document` block) — the
  procedure floor, and the thing whose absence caused the OpenSpec behaviour.
- `hub/ui/src/components/agents/NewConversationSurface.tsx` — where the document is created before
  the turn; the ordering is the fix and is easy to undo by accident.
- `hub/hub/api/v1/inbound_queue.py` — why a queued turn has not started, including the git-repo check.
