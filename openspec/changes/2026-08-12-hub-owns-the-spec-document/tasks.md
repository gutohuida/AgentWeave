# Tasks — The Hub owns the specification document

Change 1 of five. §7 of `openspec/explorations/2026-08-12-spec-hub-integration.md` states the
sequence and the five forward commitments; **sections 8 and 9 exist only to keep changes 2–5
possible** and nothing in this change consumes them. Do not drop them as unused.

## 1. Check the premises before building on them

This change's whole diagnosis is that three subsystems were removed by changes that had other
subjects. Establish that, rather than inheriting it from a proposal.

- [x] 1.1 Confirm `HttpTransport.push_spec` and `reconcile_specs` still have no callers anywhere in
      `src/`, `hub/`, or the packaged templates. If either is called, deleting the endpoints breaks a
      live path and section 2 is wrong.
      **Confirmed:** no production caller. The only references outside the definitions are in
      `tests/test_http_transport.py:607-706` — two test classes covering the two methods, which are
      deleted with them in 2.2.
- [x] 1.2 Confirm `POST /project/specs/sync` is the only writer of `ProjectSpec` rows, and that
      nothing else writes `ProjectSpecSnapshot`.
      **Confirmed:** `hub/hub/api/v1/spec.py:123` and `:216` are the only construction sites of
      either model.
- [x] 1.3 Confirm no code writes `.claude/skills/`. The only expected reference is
      `hub/hub/workspace_paths.py` filtering the composer's `@path` autocomplete client-side, which
      reads a directory the operator populates and installs nothing.
      **Confirmed:** that comment is the only occurrence in `src/` or `hub/hub/`. Nothing installs a
      skill.
- [x] 1.4 Confirm `ProjectWorkspace.resolve_relative` refuses absolute paths, traversal, control
      characters and symlink escapes, and that a configured workspace root still confines a project.
      This is the boundary that replaces the cache's path re-validation (D1).
      **Confirmed:** `project_workspace.py:62-71` rejects control characters, absolute paths and
      `..` parts, then resolves (following symlinks) and checks `_is_within`. Covered by
      `test_project_workspace.py:135,152,162` and `test_project_scoped_runtime.py:286`.
      `_require_workspace_containment` (`:104-112`) still confines the Docker path.
- [x] 1.5 Record the live `project_specs` row count before the migration. Rows exist (3 at the time
      of writing) and the migration destroys them; confirm with the operator that they are the stale
      residue of the deleted watchdog and not content anyone wants.
      **Finding — the premise was half wrong, and this is why the task existed.** The three rows all
      belong to `proj-cddb0827` (Testbed) and date from 2026-08-10: `spec/a1-probe.html` (248 B),
      `spec/changes/queued-message-delivery/spec.html` (**17,941 B**) and
      `spec/roadmaps/collaboration.html` (9,120 B). Their origin is the deleted watchdog, as
      expected — **but none of them exists on disk.** That project's working directory
      (`C:\Users\huida\Documents\agentweave-testbed`) contains only `README.md` and has no `spec/`
      directory at all, so the cache holds the **only** copy of a substantive spec and a roadmap.
      All three were exported to `testbed/scratch/rescued-project-specs/` (gitignored) before any
      further work, so the migration cannot destroy them regardless of what is decided.
      **Resolved by the operator:** *"you can drop the testbed project and reset everything. Create
      new test project. you can delete the folder where the testbed also existed in"* — discarded.
      The rescued copies were left in place under `testbed/scratch/` at no cost; nothing depends on
      them. The database was renamed to `hub/data/agentweave.db.old-20260812-172717` rather than
      deleted, so the decision stays reversible.
      **Consequence for 2.3:** the live database is now a *fresh* one created at head `0064`, so the
      `0063 → 0064` upgrade path is exercised only by `test_migrations.py`, never against real data.
      That is the normal state for a migration, but worth knowing it was not observed here.

## 2. Delete the push apparatus (D1)

- [x] 2.1 Remove `POST /project/specs/sync` and `POST /project/specs/reconcile` from
      `hub/hub/api/v1/spec.py`, with the drift computation, the source TTL, and the snapshot
      handling.
- [x] 2.2 Delete `HttpTransport.push_spec` and `HttpTransport.reconcile_specs`.
- [x] 2.3 Migration dropping `project_specs` and `project_spec_snapshots`. **Guard for a missing
      table**, as `0033`/`0034` do — an upgrade starting from an early revision reaches it with only
      that revision's tables.
      **Decided against rescuing content inside the migration** (see 1.5). An alembic migration
      writing files to a path read out of a database row fails badly exactly where it matters — in
      the container deployment the working directory may not be mounted at upgrade time. The
      defensible reading is that `project_specs` was always a *cache* of files on disk: in the normal
      case the disk copy exists and dropping loses nothing, and where it does not, the operator
      removed the source directory. **This must be stated in the upgrade notes** rather than left for
      someone to discover: cached content with no file on disk is discarded by this migration.
- [x] 2.4 Bump the head assertions in **both** `hub/tests/test_migrations.py` and
      `hub/tests/test_project_persistence.py`. Check the diff afterwards: a blind replace of the old
      revision string also hits assertion *message* text.
- [x] 2.5 Keep `validate_spec_path` and manifest parsing in both `spec_manifest` modules; remove only
      the snapshot and drift half. Reading from disk still needs path validation.

## 3. The document store (D1)

- [x] 3.1 A store that reads and writes documents beneath the project working directory, resolving
      every path through `ProjectWorkspace.resolve_relative`.
- [x] 3.2 Discovery that walks the specification tree, including nested directories, and reports
      rather than silently skips a path that fails validation.
- [ ] 3.3 Index read/write owned by the Hub, written in the same operation as the document it
      describes.
- [x] 3.4 Index degradation: when the index is absent, unreadable or invalid, still list discovered
      documents and report the index's state. Retain an entry that cannot be explained.
- [x] 3.5 Home-document selection: preserve an existing choice, record the single candidate when
      there is exactly one and none is recorded, ask when there are none or several.

## 4. The payload contract (D2, D3, D4)

- [x] 4.1 Define the payload schema. Required at minimum: `schema_version`, document kind, title,
      summary, problem, scope, non-goals, requirements (text plus modal obligation), acceptance
      criteria (given/when/then, each naming its requirement), tasks (each naming at least one
      requirement), algorithms as ordered steps, evidence and coverage limits, open questions.
- [x] 4.2 **Do not declare the contract final** (§3.5). Version it, and preserve unrecognised fields
      across a read/write round trip so a later change can extend it without migrating documents.
- [x] 4.3 Refuse a payload with no `schema_version`, naming the missing version rather than a
      downstream field.
- [x] 4.4 Validation refuses with a field path. **The write half belongs to section 6** — nothing is
      written in this section because nothing renders yet; `validate_payload` raises before any
      caller reaches a write.
- [x] 4.5 Derive the schema's field descriptions from the disposition table in §6 of the exploration,
      so the guidance a model gets is the guidance the skills carried.

## 5. The tool (D2, D3)

- [ ] 5.1 Add `submit_spec_document` to `hub/hub/mcp_server.py`. It may import **only stdlib and
      fastmcp** — restate anything it needs from the Hub there, with a test asserting the two agree.
- [ ] 5.2 The tool exposes **no** argument by which an agent can set a phase or approve (D6).
- [ ] 5.3 Identity comes from the run's minted credential, never from an argument.
- [ ] 5.4 Confirm the tool's input schema reaches a Codex-run agent as well as a Claude-run one.
      **This is the claim the skills' deletion rests on** — if the schema does not reach both, the
      format is undelivered for one runner and section 12 must stop.

## 6. The renderer (D2)

- [x] 6.1 Render a validated payload to a self-contained document: inline styles only, no external
      CSS, JS, font or image reference.
- [x] 6.2 The Hub owns anchors and identifiers, so dead anchors and duplicate identifiers cannot
      occur by construction. Assert this rather than checking for it at author time.
- [x] 6.3 Preserve the existing theme layers and the same-document anchor interception the current
      documents rely on, so a rendered document behaves in the frame as today's do.
      **Half of this task was wrong.** The three theme layers are the renderer's (done). The anchor
      interception is **not**: `specBridge.withSpecBridge` injects the bridge into the frame before
      `srcdoc` is set, so the shell already owns it. A copy in the renderer would be a second,
      divergent implementation of something that is applied to every document anyway. The task was
      written from the old conventions, where the *agent* had to include it. A test asserts the
      rendered document carries no navigation script of its own.
- [ ] 6.4 Verify the rendered document displays in `SpecFrame` under the existing sandbox —
      `allow-scripts` with **no** `allow-same-origin`. Do not add `allow-same-origin`; the approved
      spec prohibits it, and a document with same-origin access could reach the Hub.
      **Not yet done — needs the app, not a test.** Deferred until section 13 makes a document
      reachable in the UI.

## 7. Identifiers (D5)

- [x] 7.1 Mint requirement identifiers Hub-side. Ignore any identifier present in a payload.
      **Correlation is by `key`, not by position (D5a).** The delta spec originally said position;
      that was corrected during section 4, because inserting a requirement would renumber every
      requirement below it and identifiers are what tasks and evidence point at.
- [x] 7.2 Preserve an identifier across rewording of its requirement.
- [x] 7.3 Never reassign an identifier, including after its requirement is removed. Persist the
      high-water mark rather than deriving the next identifier from the current document.
- [x] 7.4 Preserve identifiers across a schema version change.

## 8. Events — forward commitment, nothing here consumes it (D8)

- [ ] 8.1 Append-only event record for every content or phase change: actor, origin (operator control
      or agent submission), run identifier where one exists, and what changed.
- [ ] 8.2 Refuse modification or deletion of a recorded event.
- [ ] 8.3 **Do not build a UI for this.** Changes 4 and 5 read it. It ships now because history
      cannot be backfilled.

## 9. Digests — forward commitment, nothing here consumes it (D8)

- [ ] 9.1 Store a content digest on every document write.
- [ ] 9.2 Store a per-requirement text digest, so change 3 can detect that a requirement's meaning
      moved out from under evidence accepted against the old wording.
- [ ] 9.3 Report divergence between the file and its stored digest. **Do not resolve it** — no
      overwrite, no merge, no choice made for the operator. §1.3 forbids the Hub silently winning,
      and the resolution interface is change 5.

## 10. The phase machine (D6, D7, D10)

- [ ] 10.1 Phase field on the document: `exploring`, `proposed`, `approved`.
- [ ] 10.2 Transitions evaluated Hub-side against entry conditions. A phase stated in a payload
      changes nothing.
- [ ] 10.3 `exploring → proposed` requires the payload to validate **and** an operator action
      declaring exploration complete (D10 — reopenable; §3.6 does not settle whether "complete
      enough" is mechanically checkable).
- [ ] 10.4 `proposed → approved` is recorded **only** from an operator action, with actor and time.
- [ ] 10.5 Transitions are append-only and attributed (feeds section 8).
- [ ] 10.6 **Assert the negative:** there is no tool argument, payload field, or document content by
      which an agent can approve. This is the property §4 says no skill could have.

## 11. Blocking validation (D7)

- [ ] 11.1 Refuse `proposed` when a requirement is referenced by no acceptance criterion.
- [ ] 11.2 Refuse when a requirement is referenced by no task, or a task references no requirement.
      **Report both directions** — an orphan either way is a real gap.
- [ ] 11.3 Refuse when a requirement states no modal obligation.
- [ ] 11.4 Refuse when non-goals are empty.
- [ ] 11.5 Refuse when an unresolved clarification marker remains.
- [ ] 11.6 Carry the manifest checks across as validation: unique safe paths, a home that resolves,
      acyclic parents, kind and status compatible.
- [ ] 11.7 Each refusal names what failed and where. A refusal the author cannot act on produces a
      retry loop.

## 12. Context, charter, and the skills (D9)

- [ ] 12.1 Extend the `### Open specification document` block in `_render_hub_agent_context`
      (`hub/hub/api/v1/agents.py:1015`) with the document's phase and the obligation that phase
      carries.
- [ ] 12.2 The procedure floor — roughly five lines, code-owned: you are exploring; ask before
      assuming; use `ask_user` for anything that changes scope; ground claims in the codebase; you
      cannot propose until the operator says exploration is complete.
- [ ] 12.3 A spec-phase run binds the spec charter by default unless the operator overrides.
- [ ] 12.4 Verify a **blank charter** still produces a valid document (§1.8).
- [ ] 12.5 Delete `src/agentweave/templates/skills/aw-spec-*.md` and
      `templates/skills/references/`, checking each section against the disposition table in §6.
      **Do not start this before 5.4 passes** — it is what makes the deletion safe.
- [ ] 12.6 Confirm nothing else references the deleted templates.

## 13. The entry point (spec-chat-session)

- [ ] 13.1 An operator control that creates an empty document in `exploring` and opens it beside the
      conversation.
- [ ] 13.2 Creation asks for nothing beyond what identifies the document.
- [ ] 13.3 No content-based inference that a conversation is an exploration — it is declared (§2.7).
- [ ] 13.4 Use the `Icon` component. Do not introduce a second icon system.

## 14. Broadcast

- [ ] 14.1 Broadcast content, phase, and index-state changes to project subscribers.
- [ ] 14.2 Frontend invalidates the relevant project-prefixed query keys on receipt.

## 15. Spec deltas

- [ ] 15.1 Sync `spec-document-authority` into `openspec/specs/`.
- [ ] 15.2 Remove `openspec/specs/aw-spec-workflow/` and `openspec/specs/spec-manifest-sync/`.
      **In the same change as 15.1**, never ahead of it (D11).
- [ ] 15.3 Sync the `spec-chat-session` modification and addition.
- [ ] 15.4 Run the round-trip gate over all main specs before and after syncing.
      `testbed/scratch/sync_delta.py` carries it.
- [ ] 15.5 `npx openspec validate --specs --strict` and `--changes --strict`.

## 16. Tests — agent-verifiable

- [ ] 16.1 Path containment: absolute, traversal, control-character and symlink-escape paths refused;
      a configured workspace root still confines.
- [ ] 16.2 Payload validation: each required field's absence produces a field-named error and no
      write.
- [ ] 16.3 Round trip preserves unrecognised fields.
- [ ] 16.4 Identifier stability: reworded requirement keeps its identifier; agent-supplied identifier
      ignored; removed identifier never reused; identifiers survive a version change.
- [ ] 16.5 **Agent cannot approve** — assert against the tool surface, not only the API.
- [ ] 16.6 A payload asserting a phase does not change the phase.
- [ ] 16.7 Each blocking validator refuses the transition, and its message names the offender.
- [ ] 16.8 Events are appended with actor, origin and run; modification and deletion are refused.
- [ ] 16.9 Digest divergence is reported and the file is not modified.
- [ ] 16.10 Blank-charter run produces a valid document.
- [ ] 16.11 The MCP server's restated constants agree with the Hub's.
- [ ] 16.12 Rendered document has no external resource reference.
- [ ] 16.13 Migration: guarded against a missing table; both head assertions updated.
- [ ] 16.14 UI tests use `importOriginal` when mocking `@/api/*` — nine existing files do not, and new
      ones should not join them.
- [ ] 16.15 `pytest hub/tests/ -q` and `pytest tests/ -q` **run separately** — together they fail
      collection. `npx vitest run` and `npx tsc --noEmit` from `hub/ui`.
- [ ] 16.16 `ruff check hub/ src/`, `black` on every file touched.

## 17. Verification — human-only (the operator runs these)

Nothing below can be closed by an agent. Each needs a person looking at a running app.

**Environment as of 2026-08-12:** the old `Testbed` project and its directory were deleted and the
database reset. The live project is **`proj-44e9adba` / `aw-testbed`** at
`C:\Users\huida\Documents\aw-testbed`, on a fresh database at head `0064` with the 9-charter seed —
so its `Spec Author` charter is the harvested one from `2909137` (8,203 bytes), which is what 17.3
needs.

**Already observed against the running Hub** (sections 2 and 3 only): documents on disk are listed
and read; an edit made outside the Hub is visible on the next read with no cache to invalidate; a
traversal path is refused with 400 and a message naming the rule; `POST /project/specs/sync` is gone
(405). None of this covers the questions below, which are about how the flow *feels*.

- [ ] 17.1 **Does the authoring flow feel like authoring?** Create a document, be interviewed, watch
      it appear. This is the question the whole change exists to answer and no test covers it.
- [ ] 17.2 Is the rendered document as readable as the ones the skills produced? The renderer replaces
      713 lines of hand-tuned conventions.
- [ ] 17.3 Does the interview feel like the old skill's interview? The craft was harvested into the
      charter in `2909137`; this is whether the harvest worked.
- [ ] 17.4 Is a validation refusal actionable, or does it produce a retry loop?
- [ ] 17.5 Try to get an agent to approve its own document. Ask it to. It should be unable to.
- [ ] 17.6 Run the flow with a **Codex** agent as well as a Claude one. Runner-agnostic delivery is
      the reason the skills were removed.
- [ ] 17.7 Edit a document in an external editor. Confirm the Hub reports it and changes nothing.
- [ ] 17.8 Confirm nothing of value was lost with the skills — read §6's table against what the flow
      now does.

## 18. User test guide

**Setup.** Create a fresh project. Charters seed per project at creation, so an existing project keeps
its own copies and will not show the harvested spec charter.

1. **Start an exploration.** Open a conversation, create a specification document. It should open
   beside the conversation, empty, marked `exploring`.
2. **Be interviewed.** Describe something you want built, vaguely on purpose. The agent should ask
   about the problem, who it affects, what is out of scope, and what it found in the code — and it
   should not read you a questionnaire.
3. **Try to skip ahead.** Ask it to write the specification immediately. It should be able to draft,
   but not to move the document to `proposed` until you say exploration is done.
4. **Propose.** Say exploration is complete. If the document is incomplete the Hub should refuse and
   say exactly what is missing — a requirement no test covers, a task pointing at nothing, an empty
   non-goals list.
5. **Read it.** The document renders in the Hub. Check it reads as well as the old ones.
6. **Try to have the agent approve it.** Ask directly. It should have no way to do so.
7. **Approve it yourself.** The phase becomes `approved`, recorded against you.
8. **Break it from outside.** Edit the file in a text editor. The Hub should tell you it diverged and
   change nothing — no merge, no overwrite. It will not yet offer to resolve it; that is change 5.
9. **Repeat 1–5 with a Codex agent.** Same behaviour, no skills involved.

**What is deliberately absent:** the document creates no tasks (change 2), evidence and gates do not
exist (change 3), there is no rejection reason or reviewer metric (change 4), and a divergence is
reported but not resolvable (change 5).
