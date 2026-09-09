"""D-2/D-3: write a machine-readable `**Status:**` line into each unclassified finding.

Run once per batch, from the repo root, under `py -3.11`. Idempotent: a section that already
leads with a `**Status:**` line is skipped rather than written twice, and the skipped count is
reconciled against the dictionary so a mis-targeted insert cannot hide among them.

The classification each line states was made by reading the section and its cross-references,
not by this file. This file only places the text.
"""

import importlib.util
import re

spec = importlib.util.spec_from_file_location("cf", "scripts/classify_findings.py")
cf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cf)
lines = cf.load()
res = {r["num"]: r for r in cf.classify(lines)}

# Each batch stamps its own tag. D-2's 40 lines are already in the ledger with
# theirs; entries already carrying a `**Status:**` line are skipped, so only this
# batch's insertions are stamped D-3.
TAG = " [classified 2026-09-09, D-3]"

S = {
    109: """**Status:** fixed `d9ad1e0` (2026-09-04, by F285's change). The 2026-08-29 decision recorded
below was **reversed**: CI made the file-backed fixture unavoidable and the operator took it.
`hub/tests/conftest.py:22-36` now names F285 and states the same three candidates this entry
measured. *"Do not re-propose the file-backed fixture"* no longer applies -- it shipped.""",
    111: """**Status:** open. The wrong sentence still ships: `POST /agents/register` is live at
`hub/hub/api/v1/agents.py:2144` (verified 2026-09-09). The operator's 2026-08-29 decision settled
the *route* out -- delete self-registration, alongside F3 -- rather than taking it. That deletion
is unimplemented, and F3 is itself still open.""",
    119: """**Status:** open on the CLI half. The Hub half landed -- `hub/hub/scheduler.py:57`
`_safe_error_summary` calls `redact_secrets` (verified 2026-09-09). `src/agentweave/diagnostics.py`
keeps the broad pre-F31 third alternative deliberately, and the question this entry ends on --
should the CLI's catch-all be narrowed -- has never been put to the operator or answered.""",
    127: """**Status:** open. Reproduced deterministically (`t_run_while_busy2.py`, 7/7) and never
repaired: this entry's own *"shape of the fix (not implemented -- it wants a round)"* still
describes the code. No openspec change covers it; the only external mention is the 2026-08-30
release roadmap.""",
    129: """**Status:** open. Verified 2026-09-09: `hub/ui/src` contains no reference to `spec/drift`,
`drift/detect` or `requirement_drift`, so the detection route is still unreachable from the app.
Named in the 2026-08-30 release roadmap, never specced. F132 sharpens it -- read that entry's
*"what this changes about F129's fix"* before proposing one.""",
    136: """**Status:** open. This entry says so itself -- *"they are not fixed"* -- and it shares a root
with F111: the `self_registered` guard in `get_agent_config`. Both close by deleting
self-registration, which is unimplemented.""",
    138: """**Status:** open, with the larger half fixed. The three hard-wired harnesses were repaired in
the filing commit. The residual left for the operator is now half-closed too: `aw.py`'s `KEY`
default is gone (`scripts/drive/aw.py:18`, plus a `require_key()` that exits, 2026-09-07), but
`HUB` still defaults to `http://127.0.0.1:8010` -- the one instance a drive must not disturb.""",
    139: """**Status:** open. Non-deterministic and unfixed. The archived change
`2026-09-01-a-flow-briefing-names-its-contract` cites it in `design.md:35` as a reason its own
briefing cannot assume a tool call, and repairs nothing here.""",
    156: """**Status:** open, and twice declared out of scope by the changes nearest to it:
`2026-09-01-a-conflict-refusal-names-what-clears-it/proposal.md:116` (*"F156 is not in scope"*) and
`2026-09-01-a-loop-declares-whether-it-needs-evidence/design.md:403` (*"adjacent and is not fixed
here"*). `integration-preview` still answers `will_merge: true` for a task approval refuses.""",
    158: """**Status:** open. This entry says *"not fixed"*, and the change it was raised against agrees:
`2026-09-01-a-loop-declares-whether-it-needs-evidence/design.md:729` -- *"F158 stands, unfixed and
out of scope"*. The candidate repair is still the open decision that design names.""",
    159: """**Status:** fixed `eeab0d3` (2026-09-01), in the same change that introduced it -- it never
shipped as a defect. Verified 2026-09-09: `hub/hub/task_workspace.py:239-240` applies the
`approved` filter only where `task_integration.evidence_governs` is False, and both guards exist --
`test_an_unapproved_evidence_free_prerequisite_contributes_nothing` and the shipped
`test_a_prerequisites_accepted_commits_are_in_the_task_checkout`
(`hub/tests/test_turn_workspace.py:907` and `:547`). Kept for the transferable lesson at the end,
which is this entry's real value.""",
    167: """**Status:** open, and said so by the change that met it:
`2026-09-01-a-review-nobody-is-doing-is-named/proposal.md:119` -- *"it does not repair the
recovery's blindness, and F167 stays open"*. `spec-queue/ROADMAP.md:187` records it as a known
residual on the adjacent `wedged_review` path that does not reopen F142.""",
    171: """**Status:** open. Filed by the row-1 sweep (`3280f52`), never fixed and never specced. The
regression assertion in `t_sweep_row1_ui.py` asserts the defect's shape for a future fix; it is not
a fix.""",
    172: """**Status:** open. Deterministically reproduced
(`t_f172_relocate_onto_a_claimed_path.py`), filed by the row-1 sweep (`3280f52`), never fixed and
never specced.""",
    174: """**Status:** open. Filed by the row-2 sweep (`6908cfd`). The catalog drift is unrepaired; the
adjacent effort control was re-checked and holds, which is a vindication inside this entry rather
than a resolution of it. Reappears in the 2026-09-03 and 2026-09-04 research pages, still open.""",
    178: """**Status:** open, and sharper than filed. Verified 2026-09-09: `useAgentLaunchability`
(`hub/ui/src/api/agents.ts:376`) has **no non-test caller** anywhere in `hub/ui/src` -- its only
consumers are three `__tests__` mocks. So the report reaches no screen, and three tests mock a hook
no component renders.""",
    179: """**Status:** open. Filed by the row-3 sweep (`58bd3fd`) alongside F178, never fixed. Named in
the 2026-09-01 exploration `a-refusal-reaches-the-operator` and in `spec-queue/DECISIONS.md`;
neither repairs it.""",
    186: """**Status:** open. Filed by the row-4 sweep (`66e085f`), never fixed and never specced. No
external mention anywhere in `openspec/` or `spec-queue/`.""",
    189: """**Status:** open, and explicitly excluded by the nearest change:
`2026-09-04-a-blocked-agent-workspace-holds-its-input/design.md:44` -- *"not a fix for F189 (the
Workspace section's invented session path), which is adjacent in the ledger"*.""",
    193: """**Status:** open. `spec-queue/DECISIONS.md:540` does not resolve it -- it says the product
already made the analogous three-way choice for archiving a conversation with a live run, and that
F193 should follow that precedent. That is guidance for a fix, not a fix.""",
    196: """**Status:** open. `spec-queue/DECISIONS.md:825` carries the decided remedy -- *"F196 + F198 --
remove `PATCH /queue/settings`"* -- as queue work. It has not been specced or implemented.""",
    197: """**Status:** open, and sized. `spec-queue/DECISIONS.md:296` supersedes the original estimate
with a count taken by the night window on 2026-09-02 (N-11): 51 reachable MISREPORT sites of 107
call sites. `713544d` established it is F271 with a skeleton in front of it. Sized, not fixed.""",
    202: """**Status:** open. Filed by the row-8 sweep (`7e45a27`). `spec-queue/DECISIONS.md:530` records
the shape -- `GET /projects/{id}/tasks` defaults to `limit=100` with no `total`/`has_more`/`next` --
as undecided work, not as a repair.""",
    206: """**Status:** open. Filed by the row-9a sweep (`fce9f83`) and carried into the 2026-09-01
research page and review page. No change addresses it.""",
    215: """**Status:** open, and confirmed open by sampling. `spec-queue/ROADMAP.md` drew four
unclassified findings at random to test whether the population was noise; this was one of the four,
and all four were *"real, unfixed, and none is anywhere in this plan"*.""",
    222: """**Status:** open, and confirmed open by the same random sample as F215
(`spec-queue/ROADMAP.md`) -- an archived job switched back on with one PATCH, which this entry's own
docstring calls *"the exact governance failure loops exist to make impossible"*.""",
    227: """**Status:** open, and enlarged rather than repaired. The 2026-09-06 re-measurement appended
below reaches the same defect through a second door -- a race between decline and answer in
`AgentQuestionCard.tsx`, where the decline button is held during an in-flight answer but nothing
holds the answer path during an in-flight decline. Both doors close on the one fix this entry
already asked for: a `declined` guard on `PATCH /questions/{id}`. That guard is unwritten.""",
    237: """**Status:** open, and confirmed open by the same random sample as F215
(`spec-queue/ROADMAP.md`) -- two controls write `Project.token_budget` through different routes and
emit different events, and the one in Settings leaves every surface displaying it stale.""",
    240: """**Status:** open. Filed by the row-14 drive (`d68f39a`) and carried into the 2026-09-06 and
2026-09-07 research pages. F92 recorded the `worker_invocations` half as an operator question
rather than a defect; neither half has been repaired.""",
    241: """**Status:** open. Filed by the row-15 drive (`4488e8f`), never fixed and never specced. Its
only external mention is the 2026-09-01 review page.""",
    242: """**Status:** open. Filed by the row-15 drive (`4488e8f`), never fixed and never specced.""",
    245: """**Status:** open. Filed by the row-15 drive (`4488e8f`), never fixed and never specced.""",
    251: """**Status:** open. Filed by the row-16 drive (`00b5dd9`), never fixed and never specced.""",
    252: """**Status:** open. Filed by the row-16 drive (`00b5dd9`), never fixed and never specced.""",
    253: """**Status:** open. Filed by the row-16 drive (`00b5dd9`), never fixed and never specced.""",
    258: """**Status:** open. Filed by the row-17 drive (`78461c9`), never fixed and never specced.""",
    259: """**Status:** open in substance, with its headline struck. The amendment below (2026-09-02, D-5)
withdraws the consequence, not the finding: `StatusBar.tsx` is imported by nothing and absent from
the bundle, so no operator sees the chip. What survives is that nothing in the product ever marks a
message read while `GET /status` and `hub/hub/scheduler.py:420` both depend on the flag -- which is
where F264 picks it up. Read this entry as that sentence; the chip is gone.""",
    264: """**Status:** open, and half-driven. The code half is established: `_pending_loop_request`
(`hub/hub/scheduler.py:415`) has no project filter and depends on a flag nothing sets (F259). The
live pass of 2026-09-01 fired the branch but **did not reproduce the leak**, and this entry records
itself as inconclusive rather than negative. It names the drive still owed -- one pass in which the
foreign row is the newest at firing time -- and that pass has not been run.""",
    265: """**Status:** open. Filed by the row-14 drive, never fixed and never specced. The refused
`create_loop` still leaves a committed job **enabled** with a next firing stamped, which is the half
of this entry that costs something.""",
    268: """**Status:** open. Filed alongside F267 by the 2026-09-02 catalog drive (`7b7720d`), never
fixed and never specced.""",
}

# ---------------------------------------------------------------------------
# D-3, 2026-09-09: severity C (55), D (14) and the 6 with no severity label.
# Part 1 stopped at the severity boundary; these are the remaining 75 sections.
# Same rule as above -- the classification was made by reading the section and
# checking the code it cites, not by this file. This file only places the text.
#
# Every claim below marked "verified 2026-09-09" rests on a grep or a read taken
# that day against HEAD; everything else rests on the ledger and on a
# cross-reference sweep over `openspec/`, `spec-queue/`, `hub/` and `scripts/`.
S.update(
    {
        66: """**Status:** fixed by `f5b46e9` (`2026-08-27-every-run-knows-its-task`, archived). Verified
2026-09-09 in code rather than from the paragraph below: `hub/hub/turn_scheduler.py:287-293` narrows
a batch to the controlling entry's kind before a turn starts, and `_review_task_from_entries`
(`agent_trigger.py:397`) still refuses a hand-assembled mixed batch. The operator question this
entry ends on was answered, and the batch the two rules would disagree about can no longer be
assembled.""",
        130: """**Status:** open. Verified 2026-09-09: `hub/hub/checkpoints.py:386` still stores
`covers_through_run_id=runs[-1].id if runs else None`, and `runs_to_cover` still reads that NULL as
*cover everything*. None of the three fix shapes below was taken. The 2026-08-30 release roadmap
lists it as decided and queued for a full spec loop; no change carries it.""",
        131: """**Status:** fixed `5958200` (2026-08-30, `continue-starts-what-it-names`). Verified
2026-09-09: `hub/hub/api/v1/checkpoints.py:284-314` computes `started` by comparing the scheduler's
`started_conversation_id` against the conversation in the path, returns that id, and gives the two
waiting cases distinct reasons. The account below is the pre-fix record and is left as written.""",
        132: """**Status:** open. Verified 2026-09-09: `hub/ui/src` still contains no reference to
`spec/drift`, `drift/detect` or `requirement_drift`, so neither plane can raise or clear a candidate,
and the gate's `DRIFTING` remedy still names an action no surface offers. Carried by the release
roadmap as a proposal that was never written.""",
        137: """**Status:** NOT A DEFECT in the product. Three harness defects in
`scripts/drive/t_sweep_queue.py`, all corrected in the filing commit; with the preconditions enforced
the row itself came through clean. Four later harnesses cite this entry as the reason they check
their own preconditions rather than assume them.""",
        157: """**Status:** open, and the product's own code says so. Verified 2026-09-09:
`hub/hub/api/v1/jobs.py:569` reads *"That asymmetry is filed ... and is not fixed here"*, `create_job`
still reads `spec_document_id` only inside `_loop_opts_in` (`:671-680`), and
`hub/tests/test_jobs_crud.py:537` pins the silent drop as deliberate.""",
        160: """**Status:** open. Verified 2026-09-09: `hub/tests/test_tool_surface_matches_server.py`
carries 18 tests and none of them asserts that a tool's *optional* arguments are described, so the
one-word-wide gap is exactly as filed. The repair was left for its own piece of work and nothing has
taken it.""",
        166: """**Status:** open. `spec-queue/ROADMAP.md:190` records this entry and its sibling as
standing after their parent was withdrawn, and `requirement_evidence.footprint_root`'s three answers
are unchanged. Never specced.""",
        169: """**Status:** open. Verified 2026-09-09: `grep -rn "approval_report\\|approvalReport"
hub/ui/src` still returns nothing, so the advisory the approving request carries still reaches no
component, and nothing persists it. Counted by
`2026-09-01-a-refusal-reaches-the-operator` as one of six instances of one shape; that exploration
produced no change.""",
        170: """**Status:** open. Verified 2026-09-09: `hub/hub/repo_hygiene.py`'s `EXCLUDE_PATTERNS`
still contains no entry matching `.agentweave/project.json`, so both symptoms stand -- the operator's
`git add -A` sweeps the marker in, and the `@path` picker offers it.""",
        175: """**Status:** open. Verified 2026-09-09: alias resolution still lives only in
`context_window_for_model` (`hub/hub/model_catalog.py:288`), and the refusal sentence still names no
value that would work. The catalog change that shipped a model picker made this API-only rather than
repairing it.""",
        176: """**Status:** open. Verified 2026-09-09: `RunnerCreate.name`
(`hub/hub/schemas/runners.py:14`) still declares `max_length=256` with no minimum, so the empty string
is still accepted with a 201 while the dialog refuses it. The catalog change's design names this as a
separate open finding rather than folding it in.""",
        177: """**Status:** open. Verified 2026-09-09: `hub/hub/api/v1/runners.py:82` still orders by
`Runner.created_at` alone, with no sequence column and no tiebreaker, so the coin flip this entry
measured 10-of-20 is unchanged.""",
        180: """**Status:** open. Filed 2026-09-01 out of row 3's screen pass; the route still composes
its own discard-only sentence over the lifecycle module's fuller one, so binding a runner is still
never offered as the non-destructive remedy. One of the six instances
`2026-09-01-a-refusal-reaches-the-operator` counted, which produced no change.""",
        181: """**Status:** open, with the remedy already chosen and unimplemented.
`spec-queue/DECISIONS.md:536` files this under *"already answered by something already written
down"* -- clear an archived agent's bindings at source. Verified 2026-09-09: the launchability query
is still `select(Agent).where(Agent.project_id == project_id)` with no lifecycle predicate.""",
        183: """**Status:** open. Verified 2026-09-09: `hub/hub/api/v1/charters.py` still carries no
duplicate-name refusal on either the create or the rename door, and `Charter.name` has no unique
constraint. Named in no change.""",
        184: """**Status:** open. Verified 2026-09-09: `CharterCreate.name`
(`hub/hub/schemas/charters.py:12`) is still `Field(min_length=1, max_length=256)`, which a
whitespace-only string satisfies, so the screen remains stricter than the API it calls.""",
        191: """**Status:** open. Verified 2026-09-09: the single sentence is still at
`hub/hub/api/v1/agent_trigger.py:1366` (and `:594`), unchanged, for all three causes, on a route
whose other refusals are exemplary. Named in no change.""",
        192: """**Status:** open. Verified 2026-09-09: the stop route still answers
`"{agent} has no run in progress."` at `hub/hub/api/v1/agent_trigger.py:1597` without consulting the
roster, while the trigger route in the same file distinguishes the case precisely.""",
        194: """**Status:** open. Both routes still take `{agent}` as a path parameter and never ask
whether it names an agent; the same shape was met one router over during row 7 and filed separately
there. Named in no change.""",
        195: """**Status:** open, and sized. `spec-queue/DECISIONS.md:263` counts 21
`subprocess.run`/`Popen` sites of which 13 already pass `cwd`, leaving about 8, and `:545` decides to
do the narrow repair and that sweep together. Neither has been done; the titler still inherits the
Hub process's directory.""",
        198: """**Status:** open, with a decided remedy nobody has taken.
`spec-queue/DECISIONS.md:825` chose to remove the route rather than repair it. Verified 2026-09-09:
`update_queue_settings` still assigns all four columns unconditionally
(`hub/hub/api/v1/inbound_queue.py:91-94`), so a partial PATCH still revokes a permission the operator
granted and answers 200.""",
        199: """**Status:** open. Neither route consults the roster, and the status route still answers
a healthy-looking zero for a name that is on no roster. The invalid-`state` refusal that still does
not enumerate the three legal values is part of the same entry.""",
        200: """**Status:** open. One sentence still covers an unknown id, a cross-project id, a
delivered entry and a withdrawn one, and it still asserts a delivery that never happened. Named in no
change.""",
        201: """**Status:** open, and sized. `spec-queue/DECISIONS.md:264` counts 9 `model_validator`s
under `hub/hub/schemas/` with the same ordering hazard, and `:545` decides the narrow repair and the
sweep should be done together. Neither has been done.""",
        204: """**Status:** open. Verified 2026-09-09: `hub/hub/api/v1/spec.py:1501` still declares
`body: PhaseRequest` with no default, so a model whose every field is optional is still required by
FastAPI and a bodyless operator decision is still answered as malformed.""",
        205: """**Status:** open. Verified 2026-09-09: `SpecPhaseBar.tsx:136-145` still renders Archive
only under `document.phase === 'approved'`, so neither of the two edges added for F37 is reachable
from any screen, and the empty exploring document those edges exist for still has nothing on screen
that retires it.""",
        207: """**Status:** open. The second door into `proposed` still bypasses the completeness check
the first one runs, and it is the same door the sibling entry's dead edge depends on. Named in no
change.""",
        208: """**Status:** open. The arrange refusal still names neither the cause nor the reindex that
would clear it; the harness that meets the sentence records it unchanged. Low, and it compounds the
reachability entry beside it rather than standing alone.""",
        209: """**Status:** open, decided twice and never implemented. `spec-queue/ROADMAP.md:337` and
`DECISIONS.md:820` both choose *thread the reason through, or delete the field*, and the R-3.1
re-check records **HOLDS, exactly**. Verified 2026-09-09: `spec_service.accept_proposal` still takes
no `reason` parameter while `reject_proposal` three functions away stores one.""",
        210: """**Status:** open. Verified 2026-09-09: both proposal routes still bind
`body: ProposalDecision` with no default (`hub/hub/api/v1/spec.py:618`, `:668`), so the one-word
repair this entry names is untaken at both sites.""",
        211: """**Status:** open. Verified 2026-09-09: `spec/requirements` and `rigor-history` still
have **0** occurrences anywhere under `hub/ui/src`, so all three routes remain reachable only by a
direct HTTP client -- including the audit trail the demotion feature argues its own legitimacy
from.""",
        212: """**Status:** open, with the remedy decided. `spec-queue/DECISIONS.md:527` records the
shape and `:40` notes the response already carries the `document_id` that would answer it. Verified
2026-09-09: `hub/hub/api/v1/spec.py:713` still projects `[row.identifier for row in unserved]`.""",
        213: """**Status:** open. The compare-and-swap still catches the twin, so nothing is
misapplied, and there is still no withdraw route -- the only exit remains a rejection that records a
judgement nobody made. Named in no change.""",
        216: """**Status:** open. Verified 2026-09-09: the drift list still projects the same six fields
(`hub/hub/api/v1/spec.py:968-978`), with no identifier, no document path and no timestamp, and the
route that would resolve the database id is the one with no operator surface.""",
        217: """**Status:** open. The branch-basis asymmetry stands: an agent's footprint is always a
worktree branch, so agent evidence is always the case drift cannot see, and nothing states that
anywhere a reader of the coverage bar would meet it. Named in no change.""",
        221: """**Status:** open, and deliberately so.
`2026-09-02-runner-model-is-chosen-from-the-catalog` names the alias refusal out of scope in its
design, and its `tasks.md:176` states in as many words that this entry stays open. The picker makes
it unreachable from the screen; the API answer is still untrue.""",
        223: """**Status:** open. Verified 2026-09-09: `get_job`'s hand-built `job_dict`
(`hub/hub/api/v1/jobs.py:788-812`) still omits `source`, so the schema default fills the hole and the
detail route still reports a value that was never stored.""",
        224: """**Status:** open. Verified 2026-09-09: `archive_loop` still tests `ending_state` before
`archived_at` (`hub/hub/api/v1/loops.py:174`, `:177`), so a loop archived through its job is still
told it is running, permanently, and still cannot be given an ending.""",
        225: """**Status:** open. Verified 2026-09-09: `hub/ui/src/api/loops.ts` still exports exactly
`useLoops` and `useLoop`, both `useQuery`, so neither operator-only route has a call site while the
index screen still offers a *Show archived* toggle for a state no screen can produce.""",
        226: """**Status:** open. Verified 2026-09-09: the detail route's embedded history still carries
six keys (`hub/hub/api/v1/jobs.py:805-814`) and neither `error_summary` nor `tick_count` is among
them, so the card's `??` preference is still satisfied by rows with no reasons in them.""",
        228: """**Status:** open. Verified 2026-09-09: the questions route still filters on
`Question.answered` alone (`hub/hub/api/v1/questions.py:242`), so a declined question is still
returned to the panel that renders *Unanswered* and still offered an answer box. The 2026-09-04
second surface narrowed one measurement inside this entry and repaired nothing.""",
        229: """**Status:** open. The decline control still lives only on the in-run card, and the page
the sidebar labels *Questions* still contains no decline control and no rendering of the flag. Named
by the survey as covered by its row, never specced.""",
        230: """**Status:** open. The card schema still carries no workspace and nothing derived from
one, so an operator answering under the `manual` posture still cannot see which side of the boundary
a path is on. Named by the 2026-09-02 research beside its sibling; neither was specced.""",
        231: """**Status:** open. Verified 2026-09-09: `pending_only` appears **0** times under
`hub/ui/src`, so the one parameter that would return an answered card is still unused, and an
approval still reaches no timeline while a refusal does.""",
        232: """**Status:** open. Verified 2026-09-09: the dismiss guard still refuses only `pending`
(`hub/hub/api/v1/permissions.py:165`), so `allowed` and `denied` still fall through and the
contract's second clause is still unimplemented. Confined to the record, as filed.""",
        233: """**Status:** open. Verified 2026-09-09: `dismiss_checkpoint_warning` still guards only
the `final` state (`hub/hub/api/v1/checkpoints.py:235`) and still writes `dismissed` over a NULL, so
a warning can still be silenced before it is shown, and the state it writes is still terminal and
shown nowhere.""",
        234: """**Status:** open. Verified 2026-09-09: `take_checkpoint` still clears only
`("due", "final")` (`hub/hub/api/v1/checkpoints.py:190`), so a dismissed conversation still keeps the
state after the checkpoint that answers it. The control run recorded below is what makes this a
divergence rather than a reading.""",
        235: """**Status:** open. Verified 2026-09-09: `visibility` is still declared only on the
checkpoint *response* (`hub/hub/api/v1/checkpoints.py:37`, `:58`) and by no request body anywhere, so
the grant is still all-or-nothing while the operator's own hint says it is bounded.""",
        236: """**Status:** open. Verified 2026-09-09: the notes query still takes the newest unconsumed
note (`hub/hub/checkpoint_generation.py:419`) and still marks only that one consumed (`:570`), so a
passed-over note still surfaces in a later checkpoint as though it were fresh.""",
        238: """**Status:** open. Verified 2026-09-09: `PUT /settings` still only broadcasts
(`hub/hub/api/v1/projects.py:528-530`) with no `persist_event` beside it, so every setting that route
writes still leaves no record while the accounting route's writes do.""",
        239: """**Status:** open. Verified 2026-09-09: the route still passes the id straight to
`conversation_usage` (`hub/hub/api/v1/accounting.py:40`) with no existence check, so a typo, a
cross-project id and an unmeasured conversation are still one honest-looking zero.""",
        243: """**Status:** open. Both clears still answer 200 and change nothing, so *put it back the
way it was* still fails silently on this route -- the same shape the runner-model clear has, which is
what makes it a pattern rather than a slip. Named in no change.""",
        244: """**Status:** open. Verified 2026-09-09: `OperatorAgentResponse`
(`hub/hub/api/v1/agents.py:113-120`) still declares seven fields and no `config`, so an agent moved
off isolation is still indistinguishable from every other one on the roster.""",
        246: """**Status:** open. Releasing the checkout still takes the branch out of
`list_workspace_branches`, so a finished task's branch still stops being conflict-checked while the
Hub's own release event records unmerged commits on it. Named in no change.""",
        247: """**Status:** open. The route still validates the name and never asks whether it belongs
to anything, so it still answers about a roster entry that was never created -- the third instance of
that shape in three days, and the others are unrepaired too.""",
        248: """**Status:** open. Verified 2026-09-09: `GET /worktrees/conflicts`
(`hub/hub/api/v1/worktrees.py:142`) is still declared before `GET /worktrees/{agent}` (`:231`), and
`AGENT_NAME_RE` still accepts `conflicts`, so an agent legally named that still cannot have its
workspace read. The repair is a namespace, not a reordering.""",
        249: """**Status:** open. Both list routes still `return []` for a project that is not a
repository, indistinguishably from a healthy one with no checkouts, while the per-agent route says so
and explains what would change it.""",
        250: """**Status:** open. Nothing invalidates the worktrees query and no SSE event reaches it,
so the panel still shows whatever was true at mount while agents provision checkouts behind it.""",
        254: """**Status:** open. Verified 2026-09-09: `get_project_for_sse` still tolerates an empty
lookup (`hub/hub/auth.py:204`), so a minted ticket still opens a stream for a project the header path
refuses, for up to the ticket's TTL.""",
        255: """**Status:** open. Verified 2026-09-09: `list_logs` still swallows a malformed `since`
(`hub/hub/api/v1/logs.py:62-65`) and answers the whole window as though no filter had been asked for.
A trap laid for the next caller rather than a live defect, which is when it is cheapest to repair.""",
        256: """**Status:** open. The union of roster names with every string ever logged is still
deliberate and still undistinguished on screen, so the filter still offers names that are on no
roster.""",
        257: """**Status:** open. Both readers still apply an unvalidated severity while the write path
normalises an unknown one, so a typo still reads as *there are no events of that kind* on the screen
whose job is saying whether something happened.""",
        260: """**Status:** open. Verified 2026-09-09: `MessagesFeed` is still named by no file outside
its own, so the subtree is still tree-shaken out and the cross-agent view is still absent. The
2026-09-02 reachability sweep found six more routes of this shape, and the note below records why six
is a floor -- a depth-1 symbol grep cannot see a whole unreachable subtree, and the walk it asks for
has still not been run.""",
        261: """**Status:** open. The recipient is still checked against the roster and the sender is
still not, so a name nobody registered still becomes a listed agent that the send route then refuses.
Reaching it needs a direct API call, which is what holds it at C.""",
        262: """**Status:** open. Verified 2026-09-09: `hub/hub/api/v1/messages.py:350` still reads
`conversation` as an agent pair and still drops anything without a colon, so a real thread id is
still ignored and the answer still reads as everything for that thread.""",
        263: """**Status:** open. Verified 2026-09-09: `hub/hub/api/v1/messages.py:359` still reverses
only on the exact literal `desc`, so any other spelling still means ascending and the default page is
still the oldest hundred a project recorded.""",
        270: """**Status:** fixed `3b1b8f0` (2026-09-03, `a-turn-says-how-it-ended` task 2.2), which is
the side effect this entry predicted rather than a repair aimed at it. Verified 2026-09-09: the
finalize block now writes the terminal `kind="status"` / `phase="completed"` row through
`record_agent_output` (`hub/hub/api/v1/agent_trigger.py:2353-2363`) for every run it reaches, on
either runner, so the client's first settled signal is no longer Claude-only.""",
        279: """**Status:** open, and undiagnosed. `spec-queue/ROADMAP.md:93-99` separates it from the
CI flake it had been conflated with -- different exception, different locus, different latency,
different reproducibility -- and that separation is the only work it has had. Both tests still stand
and the concurrent-session reproduction this entry names has never been pursued.""",
        280: """**Status:** fixed `c063e28` (2026-09-04), in the iteration that filed it. Verified
2026-09-09: the agent's recording response carries `footprint` through the shared `footprint_view`
helper (`hub/hub/api/v1/agent_actions.py:1137`, `:1145`). The sweep this entry asks for at the end --
which other shipped requirements phrased around *the response* are implemented on the operator plane
only -- has not been run.""",
        282: """**Status:** open. The declared path is still what both the refusal and the record print,
so the verdict still disagrees with the path beside it. `spec-queue/APPROVALS.md:511` carries it to
the operator as the day window's to take up; nothing has been taken up.""",
        284: """**Status:** open. The card still names the tool and the absolute path and nothing
derived from the boundary the Hub itself computed. `spec-queue/APPROVALS.md:512-515` carries it with
the instruction that it be decided together with the posture finding beside it; neither has been
decided.""",
    }
)

# Sections that already open with a prose `**Status:**` paragraph. The new line goes above it and
# the old one is relabelled, so a reader can tell a classification from the author's own words.
#
# D-2's three (F109, F111, F119) have been applied and are in git; the four below are D-3's.
# `main()` is idempotent for both: a pair whose new text is already in place is a no-op.
RELABEL = {
    66: (
        "**Status:** **closed 2026-08-30",
        "**Status as filed:** **closed 2026-08-30",
    ),
    144: (
        "**Status:** harness fixed in the same commit",
        "**Status as filed:** harness fixed in the same commit",
    ),
    145: (
        "**Status:** no product defect. Harness fixed",
        "**Status as filed:** no product defect. Harness fixed",
    ),
    148: (
        "**Status:** no product defect. Filed as the coverage record",
        "**Status as filed:** no product defect. Filed as the coverage record",
    ),
}

# The three relabelled sections whose own words are already a verdict get a classification of those
# words rather than a fresh judgement. Kept separate from the block above only for readability.
S.update(
    {
        144: """**Status:** NOT A DEFECT in the product. The single red check was the harness looking
for a tool result on a transcript that structurally cannot carry one; the product half held 16 of 17,
including the unattended-expiry path three earlier sweeps had recorded as unreached.""",
        145: """**Status:** NOT A DEFECT in the product. Two harness defects, both corrected in the
filing commit. What the drive measured is the opposite of what it was written to expect: a hard Hub
kill loses nothing and wedges nothing, 4/4 on both runs.""",
        148: """**Status:** NOT A DEFECT in the product. A coverage record -- the last two rows any
sweep had listed as unreached, driven 6/6 and 9/9, with both harnesses repaired in the filing
commit.""",
    }
)

# The trap D-2 fell into and caught: a status line that names another finding beside a resolution
# word is read by the cross-section arm as a verdict about THAT finding. One draft put "closed" on
# the same line as a reference to F3, and F3 flipped OPEN -> CONFLICT. Checked here rather than left
# to the diff, because the diff is what caught it and a guard is cheaper than a diff.
_EXT = re.compile(r"\b(RETIRED|RETRACTED|FIXED|SUPERSEDED|WITHDRAWN|closed|resolved)\b", re.I)
_FREF = re.compile(r"\bF\d+\b")


def _refuse_cross_section_verdicts(block, num):
    for line in block:
        if _FREF.search(line) and _EXT.search(line):
            raise SystemExit(
                f"F{num}: a line names another finding beside a resolution word, which the "
                f"cross-section arm reads as a verdict about that finding -- reword:\n  {line}"
            )


def main():
    relabelled = already_relabelled = 0
    for num, (old, new) in RELABEL.items():
        lo, hi = next(rg for rg in res[num]["ranges"] if rg[0] == res[num]["line"] - 1)
        for i in range(lo, hi):
            if lines[i].startswith(old):
                lines[i] = new + lines[i][len(old) :]
                relabelled += 1
                break
            if lines[i].startswith(new):
                already_relabelled += 1
                break
        else:
            raise SystemExit(f"relabel target not found for F{num}")

    edits, already = [], []
    for num, body in S.items():
        r = res[num]
        h = r["line"] - 1
        if not lines[h].lstrip().startswith("#"):
            raise SystemExit(f"F{num} does not anchor on a heading")
        j = h + 1
        while j < len(lines) and lines[j].strip() == "":
            j += 1
        if lines[j].startswith("**Status:**"):
            # Classified by an earlier batch. Skipping is what makes this file idempotent; the
            # count is asserted below so a mis-targeted insert cannot hide in here.
            already.append(num)
            continue
        block = (body.rstrip() + TAG).split("\n")
        _refuse_cross_section_verdicts(block, num)
        edits.append((j, block))

    if len(already) + len(edits) != len(S):
        raise SystemExit("accounting: every entry is either inserted or already present")

    for j, block in sorted(edits, reverse=True):
        lines[j:j] = block + [""]

    with open(cf.PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print(
        f"inserted {len(edits)}, already classified {len(already)}, "
        f"relabelled {relabelled} (+{already_relabelled} already relabelled)"
    )


if __name__ == "__main__":
    main()
