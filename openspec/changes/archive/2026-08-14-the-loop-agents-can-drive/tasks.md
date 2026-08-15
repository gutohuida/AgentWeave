# Tasks — The loop agents can drive

Phased so each phase ends green and is independently shippable. The critical path is phase 4;
phases 1–3 are cheap, touch nothing phase 4 touches, and are banked first.

**No migration.** `agents.can_accept_evidence` and its migration already exist (`0068`). Head stays
`0071` and no head assertion moves.

## 1. The Hub stops committing build artefacts

- [x] 1.1 Add `__pycache__/`, `*.pyc`, `node_modules/`, `.venv/` to `EXCLUDE_PATTERNS` in
      `hub/hub/repo_hygiene.py`.
- [x] 1.2 **Rewrite the module's own rule in the same commit.** The comment at `:39-41` currently
      reasons that language artefacts are the project's business; that comment *is* the prior
      decision. Restate it as D10: `snapshot_worktree` uses `git add -A`, so the Hub is the writer,
      and the list covers what the Hub's own commit would sweep in.
- [x] 1.3 Say in the docstring that this does **not** untrack anything already committed, and why
      the Hub does not fix that itself.
- [x] 1.4 Note that `requirement_evidence.SKIP_DIRECTORIES` carries nearly the same list, which is
      canonical, and why they cannot share code.
- [x] 1.5 New `hub/tests/test_repo_hygiene.py` — none exists. Block written; idempotent; rewritten
      in place when patterns change; foreign lines outside the markers survive; and
      `git status --porcelain` clean in a real temp repo after creating `__pycache__/x.pyc`.

## 2. Declared tasks get usable titles

- [x] 2.1 `title: str = Field(default="", ...)` on `spec_payload.Task`.
- [x] 2.2 `spec_tasks.materialise` prefers the declared title; `_title_from` remains the fallback.
- [x] 2.3 `_title_from` clips on a **word** boundary at a board-sized `MAX_TITLE`.
- [x] 2.4 Name `title` in `submit_spec_document`'s `tasks` docstring, so an author knows to set it.
- [x] 2.5 Render it in `spec_render._tasks`, which today prints the description as the list item.
- [x] 2.6 Tests: a long single-sentence description yields a short title ending on a word boundary;
      a declared title wins; round-trip and render cases.
- [x] 2.7 **`test_spec_declared_tasks.py:116/122/155-159` must pass unchanged** — a short
      single-sentence description still comes through as-is. Change `_title_from`, not the test.

## 3. The main branch is choosable

- [x] 3.1 `main_branch: string | null` on the `ProjectSettings` interface in
      `hub/ui/src/api/projects.ts`.
- [x] 3.2 A control in `ProjectSettingsPanel.tsx` fed by the existing
      `GET /projects/{id}/main-branch-suggestion` (`suggestion`, `chosen`, `is_repository`).
      Tolerate `undefined` — the existing fixture omits fields.
- [x] 3.3 Correct the stale comment at `hub/ui/src/api/projects.ts:73` ("the endpoint replaces what
      it receives"), which no longer matches the handler.
- [x] 3.4 UI test: the control renders the suggestion and submits the choice.

## 4. Partial project settings updates

- [x] 4.1 `ProjectSettingsUpdate` with all-optional fields, **derived from `ProjectSettings`** —
      `projects.py:416-417` `setattr`s over `merged.model_dump()`, so a field the response model
      lacks writes nothing, silently. `ProjectSettings` stays the `response_model`.
- [x] 4.2 Do **not** copy the cross-field `validate_threshold` onto it; the route already
      re-validates the merged object at `:371-376`.
- [x] 4.3 Test: `PUT` with only `{"main_branch": "main"}` returns 200 and leaves `hop_budget`
      untouched. **This fails today with 422**, which is what proves the diagnosis.
- [x] 4.4 Test: only `{"checkpoint_notes_value": N}` on a project that already has a threshold.

## 5. A Codex refusal is recorded

**Cannot be split** — the callback parameter, the caller invocation and the emitter land together,
or the parameter is dead code.

- [x] 5.1 Optional callback on `run_turn` (`codex_appserver.py:664-672`), beside `on_event` /
      `request_approval`. `decide_approval` stays pure (D9).
- [x] 5.2 Invoked from the caller loop at `:783-800` once the decision is final; **only** on a
      decline, and **only** when it did not come from the operator path.
- [x] 5.3 Map the JSON-RPC method to a readable label before it becomes `tool_name`.
- [x] 5.4 Wire it in `agent_trigger.py:1625-1650`, where `async_session_factory` and `persist_event`
      are already in scope.
- [x] 5.5 Pick one SSE event name — `agent_actions.py:549` broadcasts `permission_denied`,
      `permissions.py:129` broadcasts `permission_decided`. They already disagree.
- [x] 5.6 Tests: a declined command approval invokes the callback; an accepted one does not; an
      operator-resolved decline is not double-emitted; the outside-workspace decline reaches the
      event log.
- [x] 5.7 **`test_codex_appserver.py`'s purity assertions must not be edited.** If they need
      editing, the seam is in the wrong place.

## 6. The evidence loop reaches the agents

### 6a. Grant plumbing and the read route — before any tool

- [x] 6a.1 `GRANT_FIELDS = (*CHECKPOINT_GRANT_FIELDS, "can_accept_evidence")` in
      `hub/hub/api/v1/agents.py`, used for `_unrestricted_fields` and the boolean apply loop. Do
      **not** append to `CHECKPOINT_GRANT_FIELDS` (D4).
- [x] 6a.2 **`AgentSummary` is built by hand at `agents.py:598`** — edit that construction or a
      schema default of `False` silently wins over the row.
- [x] 6a.3 Response field on `hub/hub/schemas/agents.py`.
- [x] 6a.4 `hub/ui/src/api/agents.ts` — type and the `grant:` union.
- [x] 6a.5 A separate `EvidenceGrantSetting` in `AgentSettingsControls.tsx`, not inside
      `CheckpointGrantsSetting`. Copy states both refusals: no self-acceptance, and that this is
      what opens integration.
- [x] 6a.6 `GET /agent-actions/spec/evidence`, mirroring `spec.py:494-518`, scoped to
      `actor.project_id`, with a `review_state` filter. Reuse `_evidence_view` / `_footprints_for`
      (D3); keep `actor` in the view.
- [x] 6a.7 New `hub/tests/test_agent_evidence_plane.py` — record → `awaiting`; list shows `actor`
      and `footprint`; ungranted decide → 403 `acceptance_not_granted`; granted decide **own** → 403
      `self_acceptance`; granted decide another's → `accepted`; cross-project id → 404.
- [x] 6a.8 New `hub/tests/test_agent_evidence_grant.py` — PATCH sets it and **GET returns it**
      (catches 6a.2).
- [x] 6a.9 UI test mirroring `agentCheckpointSettings.test.tsx`.

### 6b. The tools — never before 6a

- [x] 6b.1 `record_evidence`, `list_evidence`, `decide_evidence` in `hub/hub/mcp_server.py`,
      **above the `__main__` guard**, which must remain last in the file.
- [x] 6b.2 `kind` stays a bare `str`; only `decision` gets a `Literal` alias matching
      `EVIDENCE_DECISIONS` (D2).
- [x] 6b.3 Three bullets in `_tool_surface_lines`, in `` `name(` `` form, or
      `test_tool_surface_matches_server.py` fails.
- [x] 6b.4 `record_evidence`'s docstring says evidence is what makes approval merge (D5).
- [x] 6b.5 A context line telling a **granted** agent it has the grant (D5).
- [x] 6b.6 `hub/tests/test_mcp_body_contract.py` rows for both POSTs — highest value, because both
      request models set `extra: "forbid"`.
- [x] 6b.7 `hub/tests/test_mcp_tool_schemas.py` — the `decide_evidence` / `decision` row.

### 6c. The chain, end to end

- [x] 6c.1 Test: agent A records against a requirement **linked to the task**, granted agent B
      accepts, approval merges. **`task_integration.py:145-165` joins through
      `TaskRequirementLink`, not `RequirementEvidence.task_id`** — a task without links still
      reports `NOTHING_TO_MERGE`, and a verification that misses this reads as "the fix failed".

## 7. A task-triggered agent finds its document

**Cannot be split** — hoisting the resolver and consuming it are one change; the hoist alone is a
behaviourless refactor that would land unverified. Landed clear of phase 6 to keep a bisect readable.

- [x] 7.1 Extract read-only `resolve_bound_task` into `run_task_binding.py`, covering all three
      branches. Call it once above the context render.
- [x] 7.2 The staged mutations do **not** move (D6). `turn_scheduler.py` is **not** changed.
- [x] 7.3 `create_task_for_actor` sets `spec_document_id` from `body.spec_document` (D8), or the
      block reaches declared tasks only.
- [x] 7.4 Expose `spec_document_id` / `spec_task_key` on `TaskResponse` and `hub/ui/src/api/tasks.ts`.
- [x] 7.5 A distinct context block (D7), not the open-document block reworded. When both would name
      the same path, only the task framing renders.
- [x] 7.6 The task-derived path does **not** go through `spec_turn_notice`.
- [x] 7.7 Tests: the block names the document; "the operator is viewing" does not appear in it; both
      blocks present without duplication; the resolver returns the same task in all three branches.
- [x] 7.8 `hub/tests/test_spec_turn_notice.py` — a task-derived document produces **no**
      SPECIFICATION TURN notice. The regression most likely to slip through.

## 8. Verification — agent-verifiable

- [x] 8.1 `pytest hub/tests/ -q` and `pytest tests/ -q` **separately**, Python311 interpreter.
- [x] 8.2 `ruff check hub/ src/`; `black --target-version py311` on every file touched.
- [x] 8.3 `npx tsc --noEmit`; `npx vitest run`.
- [x] 8.4 `npx openspec validate --changes --strict`.
- [x] 8.5 `npm run build`; `hub/hub/static/ui` replaced and confirmed with `diff -rq`. Required
      after phases 1–3 and 6, which all touch `hub/ui/src`.
- [x] 8.6 Expected to need updating: `test_tool_surface_matches_server.py` (until 6b.3),
      `test_spec_procedure_precedence.py`, `test_conversation_task_binding.py`,
      `test_agent_trigger.py` (phase 7 ordering).

## 9. Verification — human-only

- [x] 9.1 **Re-run `/e2e-loop` from zero.** Pass condition: an agent-driven project reaches
      `integration: integrated` with **no operator HTTP calls** — no minted credential, no curl —
      against a task carrying requirement links.
      **Passed 2026-08-14** on `aw-loop7` (`proj-e6c1de74`): 9/9 requirements `verified /
      integrated`, `b38e4646 → master` merged, tests green from a clean `master` checkout, every
      evidence action via the agents' own MCP tools. Three defects found *around* the change cost
      six extra runs and three operator interventions —
      `openspec/explorations/2026-08-14-loop7-evidence-drives-but-a-skipped-merge-is-terminal.md`.
      Not exercised: the grant's refusal paths (`self_acceptance`, `acceptance_not_granted`) were
      never hit live, and no Codex refusal reached a timeline (test-guide step 7).
- [ ] 9.2 Does granting an agent evidence acceptance read as safe? It is authority over what ships.
- [ ] 9.3 Does the task-derived specification block change what a builder actually does, or does it
      read past it the way it read past the missing path?
- [ ] 9.4 Are the shortened titles a board you would use?
- [ ] 9.5 Does a recorded Codex refusal read usefully in the timeline, or as noise?

## 10. User test guide

**Setup.** A git-backed project with a main branch chosen, an approved document declaring tasks, and
two agents — one that writes, one you have granted evidence acceptance.

1. **Open an agent's settings and grant it evidence acceptance.**
   - *Expect:* a control that says what it confers, separate from the checkpoint grants.
2. **Ask a builder to implement a task, and read its turn context.**
   - *Expect:* it names the document the task implements, and the builder reads it without asking
     another agent for the path.
3. **Ask the builder to record evidence when it finishes.**
   - *Expect:* it can, without being told a document path, and the evidence shows `awaiting`.
4. **Ask the granted agent to review the evidence.**
   - *Expect:* it can list what is awaiting, and accept. It cannot accept its own.
5. **Approve the task.**
   - *Expect:* the work merges. Coverage reads `verified / integrated`.
6. **Approve a task on a project with no main branch chosen.**
   - *Expect:* the integration note tells you to choose one, and the settings panel has the control
     it is pointing at.
7. **Watch a Codex agent try something outside its workspace.**
   - *Expect:* a refusal in the timeline, naming a readable tool.
8. **Look at the board after approving a document that declares tasks.**
   - *Expect:* titles you can scan.

**Where it would go wrong:** if step 5 still reports `nothing to merge`, check the task carries
requirement links — evidence joins to a task through them, not through the evidence's own `task_id`.
