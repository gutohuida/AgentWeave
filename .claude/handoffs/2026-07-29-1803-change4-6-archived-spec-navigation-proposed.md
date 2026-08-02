# Handoff: Change 4/6 archived; Spec Navigation proposed

**Date:** 2026-07-29T18:03:34+01:00 · **Branch:** `master` · **HEAD:** `f6663a9`
**Agent:** Codex (GPT-5)
**Previous handoff:** `.claude/handoffs/2026-07-29-1225-change4-section7-complete-section8-next.md`
**Status:** chunk complete

## Goal

Close the completed combined Change 4/6 stream-events and context-usage work without losing its
canonical requirements, then move to the next spec-journey capability: a navigable Hub Spec
workspace. The next capability should make current and historical specs easy to consult while
keeping daily navigation uncluttered and preserving the sandboxed document/chat workflow.

## Current state

The previous handoff was stale. Its pending section 8 work had already been completed by later
commits, and all sections 1-9 in the OpenSpec change task list were checked before this session.

`add-agent-stream-kinds` has been archived as the combined Change 4/6 record at
`openspec/changes/archive/2026-07-29-add-agent-stream-kinds/`. OpenSpec synchronized 15
agent-context-usage requirements and 17 agent-stream-events requirements into canonical specs.
There are no active OpenSpec changes, and all 12 canonical OpenSpec specs validate strictly.

The next change was explored as `add-spec-navigation`, including the formerly separate layout
Change 3. Product exploration settled these points:

- normal navigation shows core documents, roadmaps, active changes, and Needs attention;
- archived changes do not appear in normal navigation;
- a separate History browser groups archives by parent roadmap, newest first;
- title and change name provide topic search, with standalone archives under Other changes;
- current and archived documents remain searchable through Ctrl/Cmd+K;
- a shell-hosted page outline, safe iframe bridge, and responsive document/chat layout are part of
  the same vertical capability.

An approval-gated AW-Spec draft now exists at
`spec/changes/add-spec-navigation/spec.html`. It has 11 requirements, 13 acceptance criteria, and
11 pending tasks across frontend, QA, and reviewer roles. It is linked bidirectionally to roadmap
row R5 and registered in `spec/index.json` with status `draft`. It has not been approved and no
application implementation has begun.

The draft resolves implementation-scope choices as follows: 52 px Hub rail, 260 px combined
library/outline pane, 520 px minimum document width, 360 px chat, compact overlays below a measured
1140 px workspace, no resizable splitter, no new dependency, no backend/schema change, no topic
taxonomy, and no application-wide URL routing.

## Files touched

- `openspec/changes/add-agent-stream-kinds/.openspec.yaml` — deleted from the active path by the
  archive move; finished.
- `openspec/changes/add-agent-stream-kinds/design.md` — deleted from the active path by the archive
  move; finished.
- `openspec/changes/add-agent-stream-kinds/proposal.md` — deleted from the active path by the archive
  move; finished.
- `openspec/changes/add-agent-stream-kinds/specs/agent-context-usage/spec.md` — deleted from the
  active path by the archive move; finished.
- `openspec/changes/add-agent-stream-kinds/specs/agent-stream-events/spec.md` — deleted from the
  active path by the archive move; finished.
- `openspec/changes/add-agent-stream-kinds/tasks.md` — deleted from the active path by the archive
  move; finished.
- `openspec/changes/add-agent-stream-kinds/verification.md` — deleted from the active path by the
  archive move; finished.
- `openspec/changes/archive/2026-07-29-add-agent-stream-kinds/.openspec.yaml` — archived OpenSpec
  schema metadata; finished.
- `openspec/changes/archive/2026-07-29-add-agent-stream-kinds/design.md` — archived combined Change
  4/6 design; finished.
- `openspec/changes/archive/2026-07-29-add-agent-stream-kinds/proposal.md` — archived combined Change
  4/6 proposal; finished.
- `openspec/changes/archive/2026-07-29-add-agent-stream-kinds/specs/agent-context-usage/spec.md` —
  archived context-usage delta; finished.
- `openspec/changes/archive/2026-07-29-add-agent-stream-kinds/specs/agent-stream-events/spec.md` —
  archived stream-events delta; finished.
- `openspec/changes/archive/2026-07-29-add-agent-stream-kinds/tasks.md` — archived fully completed
  task list; finished.
- `openspec/changes/archive/2026-07-29-add-agent-stream-kinds/verification.md` — archived verification
  evidence; finished.
- `openspec/specs/agent-context-usage/spec.md` — new canonical spec created by OpenSpec archive,
  containing 15 requirements; finished.
- `openspec/specs/agent-stream-events/spec.md` — new canonical spec created by OpenSpec archive,
  containing 17 requirements; finished.
- `openspec/explorations/2026-07-29-spec-navigation.md` — new exploration covering product model,
  iframe boundary, history behavior, layout, verification, and non-goals; finished for proposal.
- `spec/changes/add-spec-navigation/spec.html` — new authoritative AW-Spec draft with 11
  requirements, 13 acceptance criteria, and 11 pending traced tasks; finished as a draft and
  awaiting explicit approval.
- `spec/index.json` — added the draft change with parent
  `spec/roadmaps/agentweave-reconstruction.html` and sibling order 10; finished for proposal.
- `spec/roadmaps/agentweave-reconstruction.html` — added the reciprocal R5 child-spec link while
  leaving the broader R5 status planned; finished for proposal.
- `.claude/handoffs/2026-07-29-1803-change4-6-archived-spec-navigation-proposed.md` — this durable
  handoff; finished.
- `.claude/handoffs/LATEST.md` — updated to point to this handoff; finished.

## Key decisions

- Change 6 (`fix-context-tracking-all-runners`) is represented as folded into Change 4
  (`add-agent-stream-kinds`), not as a second archive directory. A duplicate archive was rejected
  because Change 6 never had an independent active change artifact and its requirements already
  live in the combined record.
- The next change is `add-spec-navigation`, including layout. A separate layout proposal was
  rejected because document tree, page outline, iframe navigation, and responsive panes share one
  selection/workspace state and one demonstrable outcome.
- History is separate from normal navigation. An always-expanded archive tree was rejected because
  archive volume would eventually dominate daily navigation.
- History groups by parent roadmap and uses title/change name as topic vocabulary. A new topic/tag
  manifest field was rejected because it would create a second taxonomy that propose/archive skills
  must maintain.
- The wide navigation pane shows the current library and page outline together with independent
  scrolling. Tabs were rejected because they hide one navigation scale while the user is operating
  the other.
- The first layout uses deterministic pane dimensions and compact drawers below 1140 px. A splitter
  was deferred because it adds interaction, accessibility, and persistence complexity without being
  necessary to solve the document squeeze.
- The iframe remains `sandbox="allow-scripts"` without `allow-same-origin`. Since srcDoc events have
  an opaque origin, bridge validation uses exact source-window identity plus a versioned, bounded
  runtime shape. Origin matching and weakening the sandbox were rejected.
- Relative spec links route through the shell. Unknown, missing, unsafe, non-HTML, or external
  targets stay on the current document and produce a dismissible polite inline status; native iframe
  navigation was rejected because it can blank the opaque-origin frame.
- No backend, database, API schema, SSE vocabulary, authored-document contract, runtime dependency,
  topic taxonomy, or application-wide router is included.
- The draft belongs to roadmap row R5 and consumes SM-K-002 additively while using the existing
  SM-K-003 nav.toc convention. It does not claim the whole R5 dashboard slice complete.
- No AgentWeave session, roles file, or quality configuration is present, so frontend, QA, and
  reviewer tasks have role suggestions with empty agent assignments.

## Constraints and user directives (verbatim)

- `"I want to archive the change 4 and 6 that were folded togheter and work on the next one. Exploring first the next one"`
- `"oh yeah the handoff might be stale"`
- `"yes. Let's do this"`
- `"okay let's explore this one"`
- `"I would like to have a easy way to consult historical changes but I don't want them poluting the navigations."`
- `"yes that it! roadmap and topic"`
- `"Perfect"`
- `"propose"`
- `"$handoff"`
- Carried forward and still binding:
  - `"Kimi's session-status service (task 3.10) is intentionally not implemented — do not silently implement it."`
  - `"New commits, not amends."`
  - `"Zero new runtime dependencies (stdlib only)."`
  - `"Never commit .agentweave/*; use template loading not hardcoded template strings; lock task mutations; preserve unrelated dirty work; target Kimi v0.29.x only."`
  - `"Live CLI probes must run in isolated scratch directories outside the repo, cleaned up after."`
  - Pushing has not been requested.

## Dead ends

- The previous handoff recorded `master` at `17f6f76` with section 8 next, but live HEAD was
  `f6663a9` and later commits had completed sections 8-9. Live git and task state superseded it.
- Direct `functions.apply_patch` twice failed before touching the exploration note because the
  Windows restricted-token sandbox could not enforce split writable roots. Calling the underlying
  Codex apply-patch helper directly succeeded. The current environment later changed to unrestricted.
- Piping a multiline patch through PowerShell to `apply_patch.bat` failed with a UTF-8 argument
  error; passing it as one argument through the batch wrapper then lost the final delimiter. Calling
  `codex.exe --codex-run-as-apply-patch` directly preserved the patch.
- The first proposal self-check script had a Python f-string expression containing a backslash and
  failed before checking the spec. The corrected checker passed.
- A live manifest check initially failed because `agentweave` was not installed in the shell.
  Setting `PYTHONPATH=src` fixed import resolution.
- Running `discover_spec_files(Path('.'))` traversed `.venv-linux/lib64` and hit Windows
  `OSError 1920`. The function's intended root is `Path('spec')`; using that root passed with zero
  diagnostics or conflicts.
- `git diff --stat HEAD` does not include untracked archive, canonical spec, exploration, or
  spec.html files. `git status --porcelain=v1 --untracked-files=all` was used to enumerate them.

## Verification

Ran and passed:

- `openspec status --change add-agent-stream-kinds` — 4/4 artifacts complete.
- `openspec validate add-agent-stream-kinds --strict` — change valid before archive.
- `agentweave task list --status under_review` and
  `agentweave task list --status revision_needed` — no tasks found.
- `openspec archive add-agent-stream-kinds -y` — archived as
  `2026-07-29-add-agent-stream-kinds`; created 15 context-usage and 17 stream-event canonical
  requirements.
- `openspec validate --all --strict` — 12 passed, 0 failed.
- `openspec list` — no active OpenSpec changes.
- `git diff --check` — passed after archive, exploration, and proposal edits.
- Custom HTML proposal self-check — `requirements=11 acceptance=13 tasks=11 ids=43 hrefs=81`,
  `PASS`; checked metadata, unique IDs, local anchors, task attributes, requirement coverage,
  offline assets, theme layers, anchor interceptor, progress totals, manifest entry, and reciprocal
  roadmap links.
- `pytest tests\test_spec_manifest.py -q` — 40 passed, 1 skipped.
- Live manifest validation with `PYTHONPATH=src` and `discover_spec_files(Path('spec'))` —
  `manifest_documents=4 discovered=4 diagnostics=0 conflicts=0`.
- The draft HTML was opened in the system browser for user review.

Not tested:

- The user has not yet approved the draft.
- No application code was implemented.
- No Hub UI tests or production build were run for Spec Navigation because only specification
  artifacts changed.
- No manual browser verification of the proposed future iframe bridge, drawers, search, focus, or
  responsive behavior is possible before implementation.
- No full CLI or Hub backend suite was run.
- Nothing was committed, amended, or pushed in this session.

## Git state

- Branch: `master`.
- HEAD: `f6663a9` (`Track session handoff notes`).
- Worktree: dirty with the archive move, two new canonical OpenSpec specs, one exploration, one
  draft AW-Spec change, manifest/roadmap edits, and this handoff metadata. Every uncommitted path is
  listed under Files touched.
- `git log origin/master..HEAD --oneline` returned no commits: there are no unpushed commits at this
  point.
- `.claude/handoffs/` is tracked. `.agents/` is ignored, so the existing tracked handoff chain was
  correctly continued under `.claude/handoffs/`.

## Next steps

1. Open `spec/changes/add-spec-navigation/spec.html`, present its approval gate, and ask the user to
   explicitly choose approval or request changes. Do not implement or mark it approved without that
   decision.
2. If approved, update `aw-spec-status` to `approved`, set `aw-spec-approved-by` to the user's
   identity or `user`, set `aw-spec-approved-at` to `2026-07-29`, change the visible draft pill and
   Approval section, and update only this document's `spec/index.json` status to `approved`.
3. Re-run the structural self-check, live manifest validation, `pytest
   tests\test_spec_manifest.py -q`, and `git diff --check`.
4. Decide with the user whether to commit the completed Change 4/6 archive and approved Spec
   Navigation proposal before running `/aw-spec-apply`. Do not amend or push.
5. After approval and any requested commit boundary, run `/aw-spec-apply` to implement tasks T1-T11
   in test-first order. Preserve all unrelated archive/proposal worktree changes.

## Open questions for the user

- Approve `spec/changes/add-spec-navigation/spec.html` for implementation, or request changes?
- After approval, should the archive and proposal artifacts be committed before implementation?

## Read on resume

- `spec/changes/add-spec-navigation/spec.html` — authoritative draft and approval gate.
- `openspec/explorations/2026-07-29-spec-navigation.md` — rationale and settled product decisions.
- `spec/index.json` — draft manifest entry and parent relationship.
- `spec/roadmaps/agentweave-reconstruction.html` — R5 scope and reciprocal child link.
- `openspec/changes/archive/2026-07-29-add-agent-stream-kinds/verification.md` — archived Change 4/6
  evidence and coverage limits.
- `.claude/handoffs/2026-07-29-1225-change4-section7-complete-section8-next.md` — stale prior handoff;
  read only to understand superseded constraints, not as current progress.
