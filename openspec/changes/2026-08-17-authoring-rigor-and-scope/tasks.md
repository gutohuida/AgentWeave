# Tasks — rigor-gated editing, in-position proposals, authoring scope

Ordered per `design.md`: data model (1) before the functions that use it (2), functions before the
routes that call them (3), backend before UI (4), F1-F3 (rigor gating) independent of F4 (tool
scoping) so either can land first — F4 is sequenced last only because it touches a different module
(`runner_commands.py`) with no shared code, not because it depends on F1-F3.

## 1. Data model — `spec_edit_proposals`

- [x] 1.1 Add `SpecEditProposal` to `hub/hub/db/models.py` per `design.md` D3's column table
      (round-2 revision: `unit_key` is the requirement's **key**, not a minted identifier — an `add`
      proposal has no identifier yet — and the table carries a nullable `position_after_key` for
      rendering an `add` proposal in position). Index on `(document_id, status)`.
- [x] 1.2 New migration (next head after 0074) adding the table. Guard for a missing parent table the
      way 0033/0034/0073/0074 do. No `CheckConstraint` naming a column — `status`/`unit_kind`/
      `change_kind` are validated in the one writer function (D3), not at the schema layer.
- [x] 1.3 Bump the head assertions in `hub/tests/test_migrations.py` and
      `hub/tests/test_project_persistence.py` (CLAUDE.md).

## 2. F1/F2 — the diff-and-propose path

- [x] 2.1 In `hub/hub/spec_service.py`, add `async def propose_edit(...)` per `design.md` D1/D2: diff
      the incoming payload's requirements (matched by **key** — round-2 correction; a minted
      identifier does not exist for an `add` unit until acceptance) and metadata bundle against the
      document's currently stored content; create one `SpecEditProposal` row per changed unit,
      setting `position_after_key` for `add` units from the submitted requirement ordering; create
      none for a no-op submission.
- [x] 2.2 In `save_document()`, branch on `document.rigor`: `sketch` keeps today's path unchanged;
      `contract`/`gate` calls `propose_edit()` instead of writing, and returns a `ProposeResult` (new
      response shape — created proposal ids/units, and which units were unchanged) instead of
      `SaveResult`.
- [x] 2.3 Unit tests: a `gate`-rigor document's submission creates the expected proposals and does not
      change the live document (assert both); a `sketch`-rigor document's identical submission still
      applies immediately (regression guard — this is the one path that must not change); an
      unchanged resubmission against `contract`/`gate` creates zero proposals and is not reported as
      an error; a submission changing three requirements and the summary creates exactly four
      proposals (three `modify` + one `metadata`).

## 3. F3 — accept, reject, attribution, staleness

- [x] 3.1 `async def accept_proposal(...)` and `async def reject_proposal(...)` in `spec_service.py`
      per `design.md` D4: operator-only, enforced in the function; refuses a non-`pending` proposal;
      `accept_proposal` refuses on digest mismatch (D5, sets `status="stale"`) and otherwise applies
      the unit, calls `spec_lifecycle.record_content` **passing `extra_detail` per 3.2 below — not an
      `accepter` parameter, which record_content does not gain** (round-3 correction: this line
      previously described the mechanism round 2 explicitly rejected in D4/3.2; kept in sync here so
      3.1 and 3.2 do not describe two different implementations), sets `status="accepted"`.
- [x] 3.2 **Settled at round 2 — no longer an open decision.** Extend
      `spec_lifecycle.record_content` with an additive `extra_detail: Optional[Dict[str, Any]] = None`
      parameter, merged into the `detail` dict it already builds; existing callers are unaffected
      (default `None` merges nothing). `accept_proposal` is the only caller that passes it:
      `{"proposal_id": proposal.id, "proposer_actor_kind": ..., "proposer_actor_name": ...}`. The
      event's own `actor` is the accepter (consistent with every other content-write event); the
      proposer is reachable via `proposal_id` from `SpecEditProposal`, which already holds it in full.
      `SpecDocumentEvent`'s schema is not touched — no migration needed for this task.
- [x] 3.3 Routes in `hub/hub/api/v1/spec.py`: `GET /documents/{path}/proposals` (list pending, each
      with both payloads for a diff view), `POST /documents/{path}/proposals/{id}/accept`, `POST
      .../reject` — following the existing `RigorRequest`/`_document_view` pattern.
- [x] 3.4 Unit tests: an agent-kind actor attempting accept/reject is refused, proposal status
      unchanged (mirrors `test_spec_rigor.py`'s operator-only test if one exists — reuse its pattern);
      accepting applies only the targeted unit, leaving sibling pending proposals untouched; accepting
      a proposal whose digest has moved (simulate: accept a second proposal first, then attempt the
      first) is refused and marked `stale`; a rejected proposal leaves the live document byte-identical
      to before rejection; the resulting event/record names both proposer and accepter distinctly and
      both survive a second read.

## 4. F2 UI — in-position rendering

- [x] 4.1 `GET /spec/documents?path=` (or the operator equivalent already used by the Spec tab) surfaces
      pending proposals per requirement **key** (round-3 correction: not "id" — an `add` proposal has
      no minted identifier yet, per D2/D3) and the metadata unit, reusing 3.3's list route.
- [x] 4.2 The requirement renderer (wherever `SpecCoverageBar`/`SpecPhaseBar`/the document view render
      a requirement today) shows a pending-proposal indicator at that requirement, with accept/reject
      controls an operator can use without leaving the document. **`modify`/`remove` proposals attach
      to their existing requirement row by key. `add` proposals have no existing row (round-3 addition
      — section 4 was not updated when D2/D3 gained `position_after_key` in round 2): render them
      inline immediately after the requirement whose key matches `position_after_key`, or at the top of
      the requirements list if `position_after_key` is null, styled as a proposed-but-not-yet-real row
      so it is visibly distinct from an accepted requirement.**
- [x] 4.3 The metadata proposal (if any) shows at the document's summary/problem/scope section with
      the same controls.
- [x] 4.4 `npm run lint`, `npx tsc --noEmit`, `npm test` clean; rebuild the UI bundle
      (`cd hub/ui && npm run build && python scripts/refresh_ui_bundle.py`) and commit source + bundle
      together (CLAUDE.md).

## 5. F4 — authoring turns lose file-write tools

- [x] 5.1 In `hub/hub/runner_commands.py`, add a `spec_document`-shaped parameter to `build_command`
      (it does not exist there today — round-2 correction: `spec_document` currently reaches
      `trigger_agent_directly`, `agent_trigger.py:267`, for `_spec_phase_for`/`spec_turn_notice`, but
      the `build_command(...)` call at `agent_trigger.py:500` does not pass it yet; this task adds
      that one hop) and thread it into both branches per `design.md` D6, round-2 revision:
      - Claude (`_build_claude_command`): append `--disallowedTools "Edit,Write,NotebookEdit"`
        whenever the flag is set, **unconditionally — including when `yolo=True`**, a deliberate
        divergence from the `if not yolo: cmd += ["--allowedTools", ...]` line right above it.
        Confirm `--disallowedTools` and `--allowedTools "mcp__agentweave__*"` can both be present on
        the same command — confirm the CLI accepts both, do not assume.
      - Codex (`_build_codex_command`): when set, skip the existing `if yolo: ... else: ["--sandbox",
        "workspace-write"]` branch entirely (the two are mutually exclusive flags, not a value to
        override) and emit `["--sandbox", "read-only"]` in its place.
- [x] 5.2 Extend `spec_turn_notice()` (`hub/hub/launchability.py:222-264`) with a line stating the
      restriction is in effect and that discovered implementation work should be proposed via
      `create_task` — only once 5.1 makes it mechanically true, not before.
- [x] 5.3 Unit tests: `build_command` with `spec_document` set includes the restriction flag for both
      Claude and Codex branches, **including a case with `yolo=True`** (Claude: `--disallowedTools`
      still present alongside whatever `yolo` otherwise adds; Codex: `--sandbox read-only` present and
      `--dangerously-bypass-approvals-and-sandbox` absent) — this is the exact case round 2 found
      unaddressed, so it is the one most worth a regression test. `build_command` with `spec_document`
      unset is byte-identical to before this change (regression guard — this is the path every
      non-spec turn takes).
- [x] 5.4 **Done narrower than planned — recorded honestly rather than left unchecked or ticked on
      the strength of the unit tests alone.** A full live trigger against the trial Hub (a real
      agent process, a real spawn) was not run this iteration. What was verified instead, by reading
      the actual code path rather than assuming it: `agent_trigger.py:632` passes `build_command`'s
      return value to `pty_runner.py` as `cmd`, and `pty_runner.resolve_executable` (`:105-129`,
      called at both spawn sites, `:235`/`:312`) only resolves `cmd[0]` — the binary path — via
      PATH/PATHEXT; every other argv element, including `--disallowedTools`/`--sandbox read-only`,
      reaches `subprocess.Popen` unchanged (`:338`). There is no intermediate rewriting layer between
      `build_command`'s output and the real spawned process's command line, so 5.3's unit tests
      (which assert directly on that return value) are evidence about the real spawn, not only about
      the function in isolation. A live trigger with a real agent turn and a live `create_task` call
      is still worth doing before this restriction is trusted in anger — flagged for whoever next
      touches this path, rather than silently treated as equivalent to having done it.

## 6. Retire 14.15

- [ ] 6.1 Update `openspec/changes/2026-07-30-hub-native-experience/tasks.md`'s 14.15 line from
      "confirmed superseded design, needs re-wording or explicit retirement" to a waived closure
      citing this change's `design.md` D7, matching the waive-with-reason convention this run's N6
      pass already used elsewhere in that file. Do this only once this change's own tasks are
      implemented and merged — not as part of authoring it.

## 7. Whole-stack verification

- [x] 7.1 `pytest hub/tests -n 8` full suite green against the session's last recorded baseline count
      plus this change's new tests.
- [x] 7.2 `pytest tests/ -n 4` unchanged (CLI side untouched by this change).
- [x] 7.3 `openspec validate --changes --strict` and `--specs --strict` both clean.
- [x] 7.4 `ruff check hub/ src/`, `black --check` on every touched file, `npm run lint`,
      `npx tsc --noEmit` all clean.

## 8. User test guide

**Setup.** A project with a specification document at `gate` rigor carrying at least two requirements
(promote one from `sketch` through `contract` to `gate` if none exists — `spec_rigor.py`'s promotion
check needs stable, non-duplicate requirement ids, already true of any document that reached 14.1's
identifier requirement).

1. **Ask an agent to revise two requirements on the gate-rigor document.** — *Expect:* the document's
   text does not change immediately. Two pending proposals appear, each shown at the requirement it
   targets, not buried in a separate screen.
2. **Accept one proposal, leave the other pending.** — *Expect:* only the accepted requirement's text
   changes; the other requirement still shows its original text with its proposal still pending.
3. **Reject the remaining proposal.** — *Expect:* the requirement's text is exactly what it was before
   either proposal existed — no leftover marker, no partial text.
4. **Check who gets credit.** Find where the accepted change's history is shown. — *Expect:* it names
   both the agent that proposed it and you (the operator) as the one who accepted it — not just one or
   the other.
5. **Open a specification document in the chat composer and ask the agent to fix a bug it notices in
   the code while reading around the spec.** — *Expect:* it cannot edit the file directly (no Edit/
   Write tool succeeds); it should instead say it created a task for the fix, and that task should
   exist on the board afterward.
6. **Repeat step 1's edit against a `sketch`-rigor document instead.** — *Expect:* this one still
   applies immediately, no proposal, unchanged from how editing worked before this change existed.

**Where it would go wrong:** if step 1 shows the document already changed, the gate did not engage. If
step 3 shows any trace of the rejected text, "no residue" was not achieved. If step 5's agent still
edits the file, F4's tool restriction did not reach the actual spawn command — check the real process
command line, not just the code that builds it.
