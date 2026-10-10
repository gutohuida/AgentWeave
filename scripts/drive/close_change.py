"""Close an app-authored change's Hub records once its build is committed: record operator
evidence per requirement, then walk each change task pending -> in_progress -> completed -> land.

Commit first: integration skips on a dirty tree. A change's optional "commit" names the commit that
built it, which its evidence is footprinted at (F529); without one the footprint names HEAD. A commit
already on the main branch lands as `already integrated`; nothing is merged.

  AW_HUB=http://127.0.0.1:8010 AW_KEY=... AW_PROJECT=proj-d85a82bf4216 \
      MSYS_NO_PATHCONV=1 py -3.11 scripts/drive/close_change.py f440 f450

Then fold the change into the capability it changes, which archives it, through the Hub's fold
route (`a-finished-change-is-folded-into-its-capability`; the app's "Fold into capability" does the
same):  close_change.py --fold fold spec/capabilities/spec-document-authority/spec.json
The Hub refuses the fold while a task is open and on a key collision; nothing is written then.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from aw import P, api  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]

TESTS = "hub/tests/test_a_decided_task_withdraws_its_waiting_reviews.py"
CLAIM_TESTS = "hub/tests/test_a_run_claims_only_its_agents_or_nobodys_work.py"
READ_ONLY_TESTS = "hub/tests/test_a_read_only_agent_holds_no_task_work.py"
CODEX_SPEC_TESTS = "hub/tests/test_a_codex_app_server_spec_turn_keeps_no_write_tools.py"
DEFAULT_REVIEWER_TESTS = "hub/tests/test_a_document_names_its_default_reviewer.py"
STRICT_MCP_TESTS = "hub/tests/test_a_hub_run_gets_only_the_hubs_tool_server.py"
FOLD_TESTS = "hub/tests/test_a_finished_change_is_folded_into_its_capability.py"
DELETE_TESTS = "hub/tests/test_the_operator_can_delete_a_document_a_task_or_an_archived_agent.py"
REFRESH_TESTS = "hub/tests/test_re_approving_refreshes_open_tasks.py"
RETIRE_TESTS = "hub/tests/test_a_capability_can_be_retired.py"
RETIRE_DRIVE = "scripts/drive/d1008_retire_capability_drive.py"
COLLAB_TESTS = "hub/ui/src/__tests__/collaborationSummary.test.tsx"
CHIP_TESTS = "hub/ui/src/__tests__/agentPostureChips.test.tsx"
SETTINGS_TESTS = "hub/ui/src/__tests__/projectSettingsPanel.test.tsx"
PROJECT_PAGE_DRIVE = "scripts/drive/d1008_project_page_settings.py"
MANAGER_TESTS = "hub/tests/test_manager_jobs.py"
MANAGER_DRIVE = "scripts/drive/d1012_manager_framework.py"
VAULT_TESTS = "hub/tests/test_vault.py"
VAULT_DRIVE = "scripts/drive/d1015_vault_text_sources.py"
DISTIL_TESTS = "hub/tests/test_vault_distillation.py"
DISTIL_DRIVE = "scripts/drive/d1016_distillation.py"
CONTRA_TESTS = "hub/tests/test_vault_contradictions.py"
CONTRA_DRIVE = "scripts/drive/d1017_contradictions.py"
REPORTS_TESTS = "hub/tests/test_vault_reports.py"
REPORTS_DRIVE = "scripts/drive/d1024_reports.py"

JOURNEY_TESTS = "hub/tests/test_spec_journey.py"
BRIEFING_TESTS = "hub/tests/test_spec_journey_briefing.py"
JOURNEY_DRIVE = "scripts/drive/d1009_step_journey.py"
JOURNEY_MIGRATION_TESTS = "hub/tests/test_migrations.py"
BAR_TESTS = "hub/ui/src/__tests__/specPhaseBar.test.tsx"

# Folded by owner (operator, 2026-10-08): what the Hub holds on a document goes to
# spec-document-authority, what a turn is told goes to spec-chat-session.
JOURNEY_FOLD = {
    "spec/capabilities/spec-document-authority/spec.json": [
        "step-recorded", "default-journey", "advance-tool", "criterion-check-fields",
        "operator-moves-journey", "propose-without-close", "existing-documents",
    ],
    "spec/capabilities/spec-chat-session/spec.json": [
        "one-step-briefing", "step-asks-to-advance", "resume-anywhere", "intake-sizes",
        "acceptance-step", "context-preview",
    ],
}

CHANGES = {
    "fjourney": {
        "document": "spec/changes/a-spec-is-written-one-step-at-a-time/spec.json",
        "commit": "90e8273",
        "tasks": ["task-c92b4f2b2e36", "task-d1486fcad84e", "task-92e550885015", "task-c04af8b96474"],
        "evidence": [
            ("FR-1", "task-d1486fcad84e", "test_result", JOURNEY_TESTS,
             "A new change document starts at intake with no size (route and list view); a roadmap "
             "has no step. Red before the build."),
            ("FR-2", "task-d1486fcad84e", "test_result", JOURNEY_TESTS,
             "The journey per size (none/large, small, fix) is exactly the listed steps in order; "
             "next_step walks it and moves forward from a step the size no longer holds."),
            ("FR-3", "task-92e550885015", "manual_observation", JOURNEY_DRIVE,
             "Scratch Hub, real Haiku: the intake preview held only [step: intake] and the journey "
             "line; after the move only [step: requirements-and-acceptance]. 0/1 before the build, "
             "10/10 after. Unit: every step's briefing holds its own marker and no other."),
            ("FR-4", "task-92e550885015", "test_result", BRIEFING_TESTS,
             "Every step's duty (but delivery's) names what it writes and the three choices through "
             "ask_user; in the drive the agent asked 'continue here / fresh / stop' at each step end."),
            ("FR-5", "task-92e550885015", "test_result", BRIEFING_TESTS,
             "advance_spec_step at requirements with nothing written moves to acceptance, answers "
             "missing=['requirements'] and the next duty, and records a journey event with the run."),
            ("FR-6", "task-92e550885015", "manual_observation", JOURNEY_DRIVE,
             "A turn in a new conversation was briefed at requirements-and-acceptance and wrote "
             "requirements with a criterion for every MUST. Unit: another agent is briefed at tasks."),
            ("FR-7", "task-92e550885015", "manual_observation", JOURNEY_DRIVE,
             "Haiku asked one question per ask_user ([1,1,1,1,1,1]) and asked the size as a "
             "question; the first drive found batches of 3 (the tool text said ask all at once)."),
            ("FR-8", "task-92e550885015", "test_result", BRIEFING_TESTS,
             "The acceptance duties ask how_to_check, checked_by and the drive per MUST; the tasks "
             "duty makes task 1 the failing acceptance drive."),
            ("FR-9", "task-d1486fcad84e", "test_result", JOURNEY_TESTS,
             "how_to_check/checked_by round-trip through render and extract; a criterion without "
             "them stores as before; checked_by='robot' is refused naming the field."),
            ("FR-10", "task-c04af8b96474", "manual_observation", JOURNEY_DRIVE,
             "In Chromium the bar showed the small journey with the recorded step current. vitest: "
             "moves any step, changes the size, says a refusal; the journey route moves back and "
             "sizes (test_spec_journey)."),
            ("FR-11", "task-d1486fcad84e", "test_result", JOURNEY_TESTS,
             "A complete document never marked complete proposes; vitest: no Exploration is "
             "complete control, Propose shown while exploring."),
            ("FR-12", "task-d1486fcad84e", "test_result", JOURNEY_MIGRATION_TESTS,
             "0122 places empty exploring changes at intake, written ones at requirements, others "
             "null, and downgrades to the prior schema; a trial-DB copy went up and down (77 rows)."),
            ("FR-13", "task-92e550885015", "test_result", BRIEFING_TESTS,
             "GET /agents/agent-context?spec_document= returns the same open-document block a turn "
             "on that document is rendered with."),
        ],
    },
    "f379": {
        "document": "spec/changes/the-settings-that-gate-collaboration-are-on-the-project-page/spec.json",
        "commit": "e38f017",
        "tasks": ["task-cb35c27ccb6e", "task-c8730b35bd7a"],
        "evidence": [
            ("FR-1", "task-c8730b35bd7a", "test_result", COLLAB_TESTS,
             "The Overview's Collaboration block, mounted above Attention, reads flows, hop budget, "
             "token budget, merge branch, checks and limits as live values, each linked to where it "
             "is edited; no limit and no branch are flagged."),
            ("FR-1", "task-cb35c27ccb6e", "manual_observation", PROJECT_PAGE_DRIVE,
             "The acceptance drive, written and run before the build: 0/1 on today's bundle (no "
             "Collaboration block on a loaded Overview)."),
            ("FR-2", "task-c8730b35bd7a", "test_result", COLLAB_TESTS,
             "Switching agents may start flows sends {allow_agent_jobs} alone; a refused save is "
             "shown and the stored value kept."),
            ("FR-3", "task-c8730b35bd7a", "test_result", CHIP_TESTS,
             "An agent whose queue is held past the hop budget is flagged on its card, and the block "
             "counts the held agents (collaborationSummary FR-3). Unit-tested only; not seen live."),
            ("FR-4", "task-c8730b35bd7a", "manual_observation", PROJECT_PAGE_DRIVE,
             "In Chromium on a scratch Hub: beta's evidence chip off, alpha's on; clicking beta's "
             "grants beta evidence only. vitest agentPostureChips: pressed chips, one-agent switch."),
            ("FR-5", "task-c8730b35bd7a", "manual_observation", PROJECT_PAGE_DRIVE,
             "Details start collapsed; expanded they show the built-in posture, the bound runner and "
             "the 120 s/240 s wait fallbacks, while the other agent's stay collapsed."),
            ("FR-6", "task-c8730b35bd7a", "manual_observation", PROJECT_PAGE_DRIVE,
             "Settings group headings read Collaboration, Integration, Checkpointing, Conversations, "
             "Project in Chromium; vitest projectSettingsPanel 'groups its rows under headings'."),
            ("FR-7", "task-c8730b35bd7a", "manual_observation", PROJECT_PAGE_DRIVE,
             "Settings renders no token budget input and its save sends no token_budget while the "
             "hop budget lands; vitest 'leaves the token budget to Budgets'."),
            ("FR-8", "task-c8730b35bd7a", "test_result", SETTINGS_TESTS,
             "Settings and the Overview say agent budget caps agents an agent staffs, not agents "
             "running at once (both components' FR-8 cases)."),
            ("FR-10", "task-c8730b35bd7a", "manual_observation", PROJECT_PAGE_DRIVE,
             "A settings change from another surface flips the Overview's flows value to On without "
             "a reload (project_settings_updated invalidates the settings query); 10/10 after the "
             "build, vitest 1953/1953."),
        ],
    },
    "f536": {
        "document": "spec/changes/a-capability-can-be-retired/spec.json",
        "commit": "14695f6",
        "tasks": ["task-9695e6dc92b4", "task-5a7592c5b666", "task-40cef1d4fea7"],
        "evidence": [
            ("FR-1", "task-5a7592c5b666", "test_result", RETIRE_TESTS,
             "Retiring archives a capability with a reason and optional absorber; refused without a "
             "reason, with a bad absorber, by an agent, and while open work links a requirement "
             "(13 tests red before the build)."),
            ("FR-2", "task-5a7592c5b666", "test_result", RETIRE_TESTS,
             "Its requirements are retired, leave coverage, and stay retired through a reindex."),
            ("FR-3", "task-5a7592c5b666", "test_result", RETIRE_TESTS,
             "A merge into a retired capability is refused 409 capability_retired; its file is "
             "unchanged."),
            ("FR-4", "task-5a7592c5b666", "test_result", RETIRE_TESTS,
             "The phase event carries reason and absorbed_by, GET /spec returns them, the index "
             "lists it archived and still loads as valid."),
            ("FR-5", "task-40cef1d4fea7", "manual_observation", RETIRE_DRIVE,
             "In Chromium on :8010: Retire with a reason and New as absorber; 0/7 before the "
             "build, 8/8 after on a restarted Hub (the index-validity check found the manifest "
             "rule). vitest specRetireCapability 4/4 red before."),
            ("FR-5", "task-9695e6dc92b4", "manual_observation", RETIRE_DRIVE,
             "The acceptance drive, written and run before the build: 0/7 on the unbuilt Hub."),
        ],
    },
    "f440": {
        "document": "spec/changes/a-decided-task-withdraws-its-waiting-reviews/spec.json",
        "tasks": ["task-3c0c22f24a44", "task-93f9df045c6a", "task-2035432af11f"],
        "evidence": [
            ("FR-1", "task-93f9df045c6a", "test_result", TESTS,
             "Approve, land and revision_needed withdraw the queued review entry in the move's "
             "transaction with the verdict as its reason (4 of 5 tests failed on HEAD 1dbff33..)."),
            ("FR-1", "task-2035432af11f", "manual_observation",
             "scripts/drive/d1007_verdict_withdraws_review.py",
             "Driven on :8010 with a real Haiku reviewer mid-turn: 4/8 before, 8/8 after; landing "
             "withdrew the entry and no delivery was attempted at the reviewer's run end."),
            ("FR-2", "task-93f9df045c6a", "test_result", TESTS,
             "Each withdrawal is announced as queue_entry_withdrawn naming entry, agent, task and "
             "verdict."),
            ("FR-3", "task-93f9df045c6a", "test_result", TESTS,
             "A delivered entry, another task's entry and a work entry's queued state are left "
             "unchanged by an approval."),
        ],
    },
    "f450": {
        "document": "spec/changes/a-run-claims-only-its-agents-or-nobodys-work/spec.json",
        "tasks": ["task-151291e8d5a9", "task-e13de03d6ec0", "task-c89c9d9b17d6"],
        "evidence": [
            ("FR-1", "task-e13de03d6ec0", "test_result", CLAIM_TESTS,
             "An unbound run's claim of another agent's task is refused 403 naming the assignee "
             "and the operator's remedy; task, assignee and binding unchanged (failed on HEAD)."),
            ("FR-1", "task-c89c9d9b17d6", "manual_observation",
             "scripts/drive/d1007_claim_boundary_drive.py",
             "Driven on :8010 with real Haiku beta: 0/3 before (beta took alpha's task to "
             "completed), 3/3 after."),
            ("FR-2", "task-e13de03d6ec0", "test_result", CLAIM_TESTS,
             "A run's claim of an unassigned task makes its agent the assignee in the same "
             "transaction (failed on HEAD); also driven 3/3."),
            ("FR-3", "task-e13de03d6ec0", "test_result", CLAIM_TESTS,
             "Own-task claim, bound run and operator move behave as before (3 control tests), and "
             "test_run_task_binding.py stays green."),
        ],
    },
    "f425": {
        "document": "spec/changes/a-read-only-agent-holds-no-task-work/spec.json",
        "tasks": ["task-e12f21e11f3b", "task-e1bf77c9375a", "task-707ba7cd531f"],
        "evidence": [
            ("FR-1", "task-e1bf77c9375a", "test_result", READ_ONLY_TESTS,
             "A read-only agent's task-work turn is refused 409 before any workspace, naming the "
             "agent, task and remedy; no run; a review turn and a writing agent's turn are unchanged."),
            ("FR-1", "task-707ba7cd531f", "manual_observation",
             "scripts/drive/d1007_read_only_drive.py",
             "Driven on :8010 with real Haiku: 1/6 before (the turn wrote NOTES.md into the project "
             "checkout), 6/6 after."),
            ("FR-2", "task-e1bf77c9375a", "test_result", READ_ONLY_TESTS,
             "Create and PATCH naming a read-only assignee answer 422 (the under_review handover "
             "stays allowed); its run's claim answers 403; nothing changes."),
            ("FR-3", "task-e1bf77c9375a", "test_result", READ_ONLY_TESTS,
             "A flow gives the pending task to the writing agent, both when the read-only agent is "
             "free in the pool and when it is the job's own agent."),
        ],
    },
    "f462": {
        "document": "spec/changes/a-codex-app-server-spec-turn-keeps-no-write-tools/spec.json",
        "tasks": ["task-a329084987ed", "task-c5e910f735b3", "task-b263ff986238"],
        "evidence": [
            ("FR-1", "task-c5e910f735b3", "test_result", CODEX_SPEC_TESTS,
             "The dispatch hands restrict_spec_writes to run_turn (it reached it as False before); "
             "a spec turn's thread starts read-only, on-request or untrusted, in every posture "
             "(20 of 20 failed before the build; Codex is not drivable here)."),
            ("FR-2", "task-c5e910f735b3", "test_result", CODEX_SPEC_TESTS,
             "A file change and a command the posture would allow are declined on a spec turn; "
             "under Ask me a file change shows no card and a command still asks; Full access "
             "grants no permissions."),
            ("FR-3", "task-c5e910f735b3", "test_result", CODEX_SPEC_TESTS,
             "A calls-root .json file change and one aw-tool invocation are accepted in every "
             "posture; a change mixing a calls file with a workspace file is declined."),
            ("FR-4", "task-b263ff986238", "test_result", CODEX_SPEC_TESTS,
             "With no document open Full access starts danger-full-access/never and Workspace only "
             "accepts the command (the controls); MCP elicitation is accepted on a spec turn."),
        ],
    },
    "f531": {
        "document": "spec/changes/a-hub-claude-run-gets-only-the-hubs-tool-server/spec.json",
        "tasks": ["task-c657e94471f5", "task-91d8626ddfe7"],
        "evidence": [
            ("FR-1", "task-91d8626ddfe7", "test_result", STRICT_MCP_TESTS,
             "Every Claude agent argv (Hub server, none, yolo, resume, spec turn) carries "
             "--strict-mcp-config exactly once, the Hub's --mcp-config unchanged, Codex untouched "
             "(6 red before the build); the 52 Claude argv goldens differ by that flag alone."),
            ("FR-1", "task-c657e94471f5", "manual_observation",
             "scripts/drive/d1008_f531_no_connectors_drive.py",
             "Driven on :8010 with a real Haiku turn: 1/3 before (no flag; the agent named eight "
             "mcp__claude_ai_Claude_Docs__* tools), 3/3 after (flag in the spawned argv; 'NONE'); "
             "the Hub's own server still connected."),
            ("FR-2", "task-91d8626ddfe7", "test_result", STRICT_MCP_TESTS,
             "A runner's own --mcp-config flag stays in the argv beside the Hub's; a runner that "
             "already passes --strict-mcp-config is not given it twice. Live read-out of the built "
             "argv with alwaysLoad: system/init lists exactly agentweave and the runner's server."),
        ],
    },
    "f508": {
        "document": "spec/changes/a-document-names-its-default-reviewer/spec.json",
        "tasks": [
            "task-ca5e972926f9",
            "task-3a09c1140b1b",
            "task-cbb027b3387f",
            "task-80ffa8e8b03d",
            "task-f0925c46d9dd",
        ],
        "evidence": [
            ("FR-1", "task-3a09c1140b1b", "test_result", DEFAULT_REVIEWER_TESTS,
             "A task naming no reviewer is staffed from delivery.reviewer (rung declared) over a "
             "free agent sorting first; an unknown or archived default is unresolved with a reason "
             "naming the document's default, never substituted (red before the build)."),
            ("FR-1", "task-f0925c46d9dd", "manual_observation",
             "scripts/drive/d1008_default_reviewer_drive.py",
             "Driven on :8010 with real Haiku agents: 0/3 before (the review went to aaa-stub), "
             "3/3 after (queued to critic, task under_review held by critic)."),
            ("FR-2", "task-3a09c1140b1b", "test_result", DEFAULT_REVIEWER_TESTS,
             "A task's own reviewer wins over delivery.reviewer; with neither, rung 2 is unchanged."),
            ("FR-3", "task-80ffa8e8b03d", "manual_observation",
             "scripts/drive/d1008_default_reviewer_bar.py",
             "delivery_status carries reviewer and reviewer_state; in Chromium on the served bundle "
             "the bar reads 'Reviewed by @critic.' and, for an unknown name, amber with 'its "
             "reviews will come to you' (4/4); vitest 'who reviews' red before."),
            ("FR-4", "task-cbb027b3387f", "test_result", DEFAULT_REVIEWER_TESTS,
             "The exploring duty and submit_spec_document name delivery.reviewer; "
             "reviewer_undeclared is quiet when it is set and names it otherwise."),
        ],
    },
    "fold": {
        "document": "spec/changes/a-finished-change-is-folded-into-its-capability/spec.json",
        "tasks": ["task-e7c8a583c45c", "task-8a9f0b76ae27", "task-880b8e79d65a"],
        "evidence": [
            ("FR-1", "task-8a9f0b76ae27", "test_result", FOLD_TESTS,
             "The draft appends the change's requirements and criteria under <slug>-<key> (<= 64, "
             "valid keys), reports a key the capability holds as a collision and leaves its text "
             "and the file untouched (red before the build)."),
            ("FR-2", "task-8a9f0b76ae27", "test_result", FOLD_TESTS,
             "A fold writes edited and replacing requirements through the merge (one row, one "
             "merged event) and archives; folded twice across two capabilities it archives on the "
             "second; seven refusals each write nothing (red before the build)."),
            ("FR-3", "task-8a9f0b76ae27", "test_result", FOLD_TESTS,
             "Archiving an approved change with an open task is refused naming it; unfolded it is "
             "refused until no_capability_change comes with a non-blank reason; folded it archives."),
            ("FR-4", "task-8a9f0b76ae27", "test_result", FOLD_TESTS,
             "PUT .../content on a capability is 409 capability_written_through_merge naming the "
             "merge route; a merge naming no change writes it and records an edit event."),
            ("FR-5", "task-880b8e79d65a", "manual_observation",
             "scripts/drive/d1008_fold_change_drive.py",
             "In Chromium on :8010's served bundle: 0/4 before the build (no fold action), 6/6 "
             "after: the bar reads shipped-but-not-in-a-capability, the dialog drafts "
             "widgets-glow-glow, confirm leaves the key in the capability file, one merge row, and "
             "the change archived. vitest specFold 8/8."),
            ("FR-5", "task-e7c8a583c45c", "manual_observation",
             "scripts/drive/d1008_fold_change_drive.py",
             "The acceptance drive, written and run before the build: 0/4 on today's Hub."),
        ],
    },
    "f533": {
        "document": "spec/changes/a-fold-can-retire-what-the-change-supersedes/spec.json",
        "tasks": ["task-85b425296f6f", "task-036912f44f18", "task-e103703a8f9a"],
        "evidence": [
            ("FR-1", "task-036912f44f18", "test_result",
             "hub/tests/test_a_fold_can_retire_what_the_change_supersedes.py",
             "A fold retiring a requirement drops it with its criteria and a retired criterion "
             "alone, in one merge; an unknown key and a requirement both replaced and retired are "
             "refused with the capability's digest unchanged (all red before the build)."),
            ("FR-2", "task-036912f44f18", "test_result",
             "hub/tests/test_a_fold_can_retire_what_the_change_supersedes.py",
             "The draft lists the capability's requirements (key, statement) and criteria (key, "
             "requirement, then) in the capability's order."),
            ("FR-3", "task-e103703a8f9a", "manual_observation",
             "scripts/drive/d1008_fold_retire_drive.py",
             "In Chromium on :8010: 2/7 before (no retire section), 7/7 after: old-rule, its "
             "criterion and widgets-exist-c gone, the folded requirement and widgets-exist-d kept. "
             "vitest specFold: retire and filter cases red before, 10/10 after."),
            ("FR-3", "task-85b425296f6f", "manual_observation",
             "scripts/drive/d1008_fold_retire_drive.py",
             "The acceptance drive, written and run before the build: 2/7 on today's Hub."),
        ],
    },
    "f535": {
        "document": "spec/changes/re-approving-an-amended-document-refreshes-its-open-tasks/spec.json",
        "tasks": ["task-d89b47b08bed", "task-eb792ba57e58", "task-c0ebc563e02d"],
        "evidence": [
            ("FR-1", "task-eb792ba57e58", "test_result", REFRESH_TESTS,
             "An open, assigned, in-progress task follows the amended document: title, description, "
             "criteria, and its links to this document's requirements (retired one unlinked, new "
             "ones linked); status, assignee, priority and another document's link unchanged (red "
             "before the build)."),
            ("FR-2", "task-eb792ba57e58", "test_result", REFRESH_TESTS,
             "An approved and a rejected task keep title, description, criteria, status and links "
             "when their entries change."),
            ("FR-3", "task-eb792ba57e58", "test_result", REFRESH_TESTS,
             "approval_outcome lists refreshed (fields, linked, unlinked), closed_linking_retired "
             "and no_longer_declared, an unchanged open task is not listed, and GET /spec serves "
             "the same stored report (red before the build)."),
            ("FR-4", "task-c0ebc563e02d", "manual_observation",
             "scripts/drive/d1008_reapproval_refresh_drive.py",
             "In Chromium on :8010: 4/10 before (t1 kept 'Old title' and its link to retired FR-1; "
             "no report lines), 10/10 after on a restarted Hub. vitest: the new report case red "
             "before, 25/25 after."),
            ("FR-4", "task-d89b47b08bed", "manual_observation",
             "scripts/drive/d1008_reapproval_refresh_drive.py",
             "The acceptance drive, written and run before the build: 4/10 on today's Hub."),
        ],
    },
    "f532": {
        "document": "spec/changes/the-operator-can-delete-a-document-a-task-or-an-archived-agent/spec.json",
        "tasks": ["task-590f10b700ce", "task-2b6be2d03939", "task-f383ec86c0dc"],
        "evidence": [
            ("FR-1", "task-2b6be2d03939", "test_result", DELETE_TESTS,
             "A document delete leaves no row naming it, its requirements, tasks, evidence, loop "
             "or job; runs, conversations and delivered entries keep their row with the pointer "
             "cleared; the file and its spec/index.json entry are gone; capability, archived, "
             "folded, running-flow and active-run cases are refused unchanged."),
            ("FR-2", "task-2b6be2d03939", "test_result", DELETE_TESTS,
             "A task delete takes its dependency, transition, evidence, footprint and queued "
             "entry, clears the run and the delivered entry, keeps the dependent task; a task with "
             "a running run is refused; the reference-coverage guard passes."),
            ("FR-5", "task-2b6be2d03939", "test_result", DELETE_TESTS,
             "A runner held only by an archived agent deletes, the agent stays archived with no "
             "runner and its run intact; an open holder is still refused by name (and "
             "hub/tests/test_runners_api.py's two archived-holder tests, moved to this rule)."),
            ("FR-4", "task-f383ec86c0dc", "manual_observation", "scripts/drive/d1008_delete_drive.py",
             "In Chromium on :8010: 1/9 before (neither Delete control existed, the runner was "
             "refused), 9/9 after: the task deleted from its drawer, the change from its phase bar "
             "with its file and task, the runner deleted and the archived agent kept. vitest: the "
             "four new delete cases red before; 1920/1920 after."),
            ("FR-4", "task-590f10b700ce", "manual_observation", "scripts/drive/d1008_delete_drive.py",
             "The acceptance drive, written and run before the build: 1/9 on today's Hub."),
        ],
    },
    "fstorage": {
        "document": 'spec/changes/a-spec-document-is-stored-as-its-payload/spec.json',
        "commit": '3b7663d',
        "tasks": ['task-824bfa945a0a', 'task-3173c0f6ef88', 'task-55c62bc9c6d0', 'task-e7eec913ea2b'],
        "evidence": [
            ('FR-1', 'task-3173c0f6ef88', 'test_result', 'hub/tests/test_spec_json_storage.py',
             'test_a_submitted_document_is_stored_as_its_payload_and_the_hub_block and '
             'test_the_hub_block_is_not_part_of_the_payload assert the saved spec.json holds the '
             'payload verbatim plus a hub block (phase, rigor, step, size); '
             'test_a_payload_may_not_carry_the_hub_block asserts the refusal.'),
            ('FR-2', 'task-3173c0f6ef88', 'test_result', 'hub/tests/test_spec_json_storage.py',
             'test_get_spec_renders_the_page_from_the_stored_payload asserts GET /spec returns HTML '
             'rendered from the stored spec.json; d1010 checks 4 and 6 compare the page, statement and '
             'phase chip before and after conversion.'),
            ('FR-3', 'task-3173c0f6ef88', 'test_result', 'hub/tests/test_spec_json_storage.py',
             'test_the_same_payload_is_written_to_the_same_bytes asserts deterministic bytes; '
             'test_rewording_one_requirement_changes_only_its_line asserts a one-requirement reword '
             "changes only that requirement's lines."),
            ('FR-3', 'task-55c62bc9c6d0', 'manual_observation', 'scripts/drive/d1010_spec_json.py',
             'd1010 check 7b rewords one requirement on the converted corpus and asserts the diff '
             "holds only that requirement's statement and digest lines."),
            ('FR-4', 'task-3173c0f6ef88', 'test_result', 'hub/tests/test_spec_storage_seam.py',
             'test_only_the_seam_parses_a_stored_file is an AST guard failing if any module other than '
             'spec_documents calls extract_payload (mutation-checked); '
             'test_the_seam_reads_what_a_save_wrote asserts the seam reads a saved file.'),
            ('FR-5', 'task-3173c0f6ef88', 'test_result', 'hub/tests/test_spec_json_storage.py',
             'test_creating_a_document_at_an_html_path_names_the_json_path asserts the refusal names '
             'the .json path; test_the_index_is_not_a_document_path and '
             'test_a_minted_path_is_a_json_path assert path validation and naming.'),
            ('FR-6', 'task-3173c0f6ef88', 'test_result', 'hub/tests/test_spec_json_storage.py',
             'test_a_legacy_html_document_is_reported_not_listed asserts discovery reports a legacy '
             '.html file as a legacy_html_document diagnostic and does not list it as a document.'),
            ('FR-6', 'task-55c62bc9c6d0', 'manual_observation', 'scripts/drive/d1010_spec_json.py',
             'd1010 check 3 asserts that after conversion the document list holds the same ids at '
             '.json paths with no legacy diagnostic.'),
            ('FR-7', 'task-55c62bc9c6d0', 'manual_observation', 'scripts/drive/d1010_spec_json.py',
             'd1010 checks 1-5 (11/11 green) convert a legacy .html corpus to spec.json over HTTP and '
             'assert ids, rendered pages, requirement identifiers and evidence are unchanged.'),
            ('FR-7', 'task-55c62bc9c6d0', 'test_result', 'hub/tests/test_spec_conversion.py',
             'test_converting_to_html_writes_the_page_and_rewrites_every_path asserts rewrites of '
             'spec_documents.path, index.json, embedded roadmap.document and task from.document; '
             'test_undelivered_queue_entries_follow_the_document_and_delivered_ones_keep_history '
             'asserts queue rewrites.'),
            ('FR-7', 'task-e7eec913ea2b', 'manual_observation', 'scripts/drive/d1010b_real_corpus.py',
             'd1010b converted the real corpus on a Hub: every .html document converted, none skipped, '
             "and GET /spec rendered every converted document (78/78). On 2026-10-09 this repo's spec/ "
             'converted the same way: 82 converted, 0 skipped, payloads identical.'),
            ('FR-8', 'task-55c62bc9c6d0', 'test_result', 'hub/tests/test_spec_conversion.py',
             'test_converting_back_restores_the_stored_files_byte_for_byte and '
             'test_a_second_conversion_changes_nothing assert the reverse conversion restores the '
             'files and is idempotent.'),
            ('FR-8', 'task-e7eec913ea2b', 'manual_observation', 'scripts/drive/d1010b_real_corpus.py',
             'd1010b converted the real corpus to json and back and asserted the reverse restored the '
             'same .html set with no .json documents.'),
            ('FR-9', 'task-55c62bc9c6d0', 'test_result', 'hub/tests/test_spec_conversion.py',
             'test_the_conversion_is_refused_while_a_run_is_active_and_changes_nothing asserts 409 '
             'conversion_run_active naming run-busy, with the file tree and rows unchanged.'),
            ('FR-10', 'task-3173c0f6ef88', 'test_result', 'hub/tests/test_spec_json_storage.py',
             'test_an_operator_journey_move_rewrites_the_hub_block, '
             'test_an_agent_journey_move_rewrites_the_hub_block and '
             "test_a_phase_move_rewrites_the_hub_block assert the file's hub block is rewritten in the "
             'same request.'),
            ('FR-10', 'task-55c62bc9c6d0', 'manual_observation', 'scripts/drive/d1010_spec_json.py',
             "d1010 check 8 asserts a journey move rewrites the converted file's hub block."),
            ('FR-1', 'task-824bfa945a0a', 'manual_observation', 'scripts/drive/d1010_spec_json.py',
             'Acceptance drive d1010, committed in bc76323 failing at check 1 (conversion route '
             'answered 405) before the build; green 11/11 at f8041ee.'),
        ],
    },
    "fsteps": {
        "document": 'spec/changes/a-project-orders-its-own-spec-steps/spec.json',
        "commit": '9a73e23',
        "tasks": ['task-09f97da0049e', 'task-847b1c1b7810', 'task-2800a1609906', 'task-80a919c0cc4c'],
        "evidence": [
            ('FR-1', 'task-847b1c1b7810', 'test_result', 'hub/tests/test_project_spec_steps.py',
             'test_with_no_file_every_journey_and_duty_is_the_built_in_table and the broken-file '
             'parametrized test read steps from spec/journey.json; with no file the built-in table is '
             'served and a bad file yields journey_file_invalid with built-ins used.'),
            ('FR-1', 'task-847b1c1b7810', 'manual_observation', 'scripts/drive/d1011b_project_steps_fallback.py',
             'Drive d1011b 4/4: with no spec/journey.json GET /project/journey returned the seven '
             'built-ins and no diagnostics, and the briefing preview held the built-in requirements '
             'duty.'),
            ('FR-2', 'task-847b1c1b7810', 'test_result', 'hub/tests/test_project_spec_steps.py',
             'Parametrized test_a_broken_file_is_a_diagnostic... asserted a missing built-in, '
             'reordered built-ins and a custom key colliding with a built-in were diagnosed; custom- '
             'step size tests showed a custom step joins small/large and not fix, per-size membership '
             'unchanged.'),
            ('FR-3', 'task-847b1c1b7810', 'test_result', 'hub/tests/test_project_spec_steps.py',
             'test_a_custom_step_is_entered_by_advance_and_briefed_with_its_markdown asserted advance '
             'moved requirements to threat-model and the briefing held the [step: key] marker, title, '
             'Markdown, a tell-the-operator-where line and the journey line.'),
            ('FR-3', 'task-09f97da0049e', 'manual_observation', 'scripts/drive/d1011_project_steps.py',
             'Drive d1011 checks 4 and 5a/5b: a real agent turn advanced onto the custom threat-model '
             'step; its preview named the step and held its Markdown; the documents view listed it '
             'after requirements.'),
            ('FR-4', 'task-847b1c1b7810', 'test_result', 'hub/tests/test_project_spec_steps.py',
             'test_an_appended_instruction_reaches_only_its_own_step asserted the appended sentence '
             "appeared in its step's briefing and advance instructions and in no other step's; d1011 "
             'checks 3a/3b repeated this through the live Hub.'),
            ('FR-5', 'task-2800a1609906', 'test_result', 'hub/tests/test_project_spec_steps.py',
             'test_put_refuses_an_over_long_text_naming_the_step_and_the_cap_and_writes_nothing '
             'asserted PUT refused over-2,000-character instructions or appended text, named the step '
             'and the cap, and wrote no file; the parametrized file test also covered the 2,000 cases.'),
            ('FR-6', 'task-2800a1609906', 'test_result', 'hub/tests/test_project_spec_steps.py',
             'test_get_answers_the_built_ins..., '
             'test_put_saves_the_steps_and_get_returns_them_in_that_order, '
             'test_put_writes_the_same_bytes_for_the_same_journey_however_the_body_is_ordered and '
             'test_put_names_the_field_it_cannot_honour covered GET/PUT /project/journey.'),
            ('FR-6', 'task-80a919c0cc4c', 'test_result', 'hub/ui/src/__tests__/specStepsSection.test.tsx',
             'Vitest specs for SpecStepsSection: lists steps in file order, inserts pasted Markdown '
             'after a chosen step, appends an instruction, removes custom (not built-in) steps, moves '
             'custom steps, shows diagnostics, refuses empty or duplicate-key steps.'),
            ('FR-6', 'task-09f97da0049e', 'manual_observation', 'scripts/drive/d1011_project_steps.py',
             'Drive d1011 checks 1, 2, 6 and 7: GET answered built-ins, PUT wrote spec/journey.json '
             "with the PUT body's steps, and the project page showed the step and a pasted Markdown "
             'step landed right after requirements.'),
            ('FR-7', 'task-847b1c1b7810', 'test_result', 'hub/tests/test_project_spec_steps.py',
             'test_a_broken_file_is_a_diagnostic_and_the_built_in_table_is_used (13 broken-file cases) '
             'asserted journey_file_invalid with the reason and built-ins used; '
             'test_a_broken_file_never_refuses_a_turn asserted turns still ran.'),
            ('FR-7', 'task-09f97da0049e', 'manual_observation', 'scripts/drive/d1011b_project_steps_fallback.py',
             "Drive d1011b: with spec/journey.json set to '{ this is not json' GET returned only "
             'journey_file_invalid with the built-ins served, and the briefing preview was still the '
             'built-in requirements duty.'),
            ('FR-8', 'task-847b1c1b7810', 'test_result', 'hub/tests/test_project_spec_steps.py',
             'test_a_removed_step_is_briefed_as_removed_and_bare_advance_is_refused asserted a '
             'document on a removed step was told it was removed and to ask_user, and advance with no '
             'target answered 422 step_not_in_journey.'),
            ('FR-8', 'task-847b1c1b7810', 'test_result', 'hub/tests/test_project_spec_steps.py',
             'test_the_operator_moves_a_document_onto_a_custom_step_and_not_an_unknown_one asserted '
             'the operator can move onto a custom step and an unknown step is refused.'),
            ('FR-9', 'task-847b1c1b7810', 'test_result', 'hub/tests/test_project_spec_steps.py',
             'test_the_documents_view_lists_the_projects_journey asserted the documents view journey '
             "field held the project's steps for the document's size, custom steps included, in file "
             'order.'),
            ('FR-9', 'task-09f97da0049e', 'manual_observation', 'scripts/drive/d1011_project_steps.py',
             'Drive d1011 checks 5b and 6: the documents view listed threat-model after requirements, '
             'and the phase bar and project page showed it between requirements and acceptance in a '
             'real browser.'),
            ('FR-6', 'task-09f97da0049e', 'manual_observation', 'scripts/drive/d1011_project_steps.py',
             'Acceptance drive d1011 was written first (commit 3eac20d) and failed at check 1 on the '
             'then-current Hub (no /project/journey route); it passed after the build, with d1011b as '
             'the fallback 4/4 (9a73e23).'),
        ],
    },
    "fwarn": {
        "document": 'spec/changes/approve-lists-what-is-missing-and-can-approve-anyway/spec.json',
        "commit": 'c9e94ed',
        "tasks": ['task-c63101dbca2d', 'task-8888aa20b760', 'task-810c13a6c629', 'task-7740673542f3'],
        "evidence": [
            ('FR-1', 'task-810c13a6c629', 'test_result', 'hub/tests/test_approval_warnings_routes.py',
             'test_approve_lists_the_gaps_and_stays_proposed_until_approve_anyway: plain approve '
             'answered 409 approval_warnings with the gap list and left the document proposed; '
             'approve_anyway=true then returned 200, phase approved, one task created.'),
            ('FR-1', 'task-c63101dbca2d', 'manual_observation', 'scripts/drive/d1012_approval_warnings.py',
             'Acceptance drive d1012 on a scratch Hub (:8101): check 2 asserted 409 approval_warnings '
             'listing the gap and the document still proposed; check 3 asserted approve_anyway '
             'approved. Recorded failing at check 1 in a978af2, 7/7 in c9e94ed.'),
            ('FR-2', 'task-8888aa20b760', 'test_result', 'hub/tests/test_approval_gaps.py',
             'Tests for requirement_without_criterion (MUST/SHALL gap, SHOULD/MAY not a gap), '
             'criterion_without_check, no_acceptance_drive (including a drive reached through another '
             'task), and steps_skipped naming the journey steps (and none when the document has no '
             'step).'),
            ('FR-2', 'task-810c13a6c629', 'test_result', 'hub/tests/test_approval_warnings_routes.py',
             'test_skipped_journey_steps_are_listed_at_approval: at the route, approval answered 409 '
             'with exactly one warning, steps_skipped, for a large change placed at the requirements '
             'step.'),
            ('FR-3', 'task-8888aa20b760', 'test_result', 'hub/tests/test_approval_gaps.py',
             'test_what_makes_approval_wrong_is_a_refusal_and_completeness_is_a_gap: dependency_cycle, '
             'depends_on_unresolved and unknown_field were refusals; unresolved_question and '
             'non_goals_empty were gaps; no gap code was in REFUSAL_CODES.'),
            ('FR-3', 'task-810c13a6c629', 'test_result', 'hub/tests/test_approval_warnings_routes.py',
             'test_a_refusal_holds_against_approve_anyway: with a dependency cycle, approve with '
             'approve_anyway=true answered 409 document_incomplete naming dependency_cycle, left the '
             'document proposed and recorded no approval event.'),
            ('FR-4', 'task-810c13a6c629', 'test_result', 'hub/tests/test_approval_warnings_routes.py',
             'test_propose_passes_a_gap_and_lists_it_under_warnings (phase proposed, blocking empty, '
             'warnings criterion_without_check) and '
             'test_propose_still_holds_a_refusal_and_lists_the_gaps_beside_it (cycle stayed in '
             'blocking, gap in warnings).'),
            ('FR-4', 'task-c63101dbca2d', 'manual_observation', 'scripts/drive/d1012_approval_warnings.py',
             'Drive check 1: propose returned 200, proposed true, blocking empty and the gap under '
             'warnings.'),
            ('FR-5', 'task-810c13a6c629', 'test_result', 'hub/tests/test_approval_warnings_routes.py',
             'test_approve_lists_..._until_approve_anyway asserted warnings_overridden on the approval '
             'event and approval_warnings_overridden in the listing; '
             'test_a_clean_approval_records_that_it_overrode_nothing_and_a_reopen_forgets asserted [] '
             'when clean and the field gone after reopening; '
             'test_approve_anyway_with_no_gap_still_records_an_empty_list.'),
            ('FR-5', 'task-c63101dbca2d', 'manual_observation', 'scripts/drive/d1012_approval_warnings.py',
             "Drive check 4 read the view's approval_warnings_overridden and the spec_document_events "
             'row from the database: both carried the overridden gaps, exactly one event.'),
            ('FR-6', 'task-810c13a6c629', 'test_result', 'hub/tests/test_approval_warnings_routes.py',
             'test_approve_anyway_on_any_other_move_is_a_400_before_anything_moves, parametrised over '
             'proposed, exploring and archived: each answered 400 naming approve_anyway and the '
             'document stayed proposed.'),
            ('FR-7', 'task-7740673542f3', 'test_result', 'hub/ui/src/__tests__/specApprovalWarnings.test.tsx',
             'Vitest: gaps grouped by code, one line per code with count and up to three places; '
             'Approve anyway resent with approve_anyway; plain Approve never sent it; incomplete '
             'refusal offered no button; approved document showed the overridden block, absent when '
             'empty.'),
            ('FR-7', 'task-c63101dbca2d', 'manual_observation', 'scripts/drive/d1012_approval_warnings.py',
             'Drive checks 5, 5a, 5b ran in Chromium: Approve showed the gaps grouped by code with the '
             'document still proposed; Approve anyway approved and the phase bar showed what was '
             'overridden.'),
            ('FR-1', 'task-c63101dbca2d', 'manual_observation', 'scripts/drive/d1012_approval_warnings.py',
             'Acceptance drive written before the build (a978af2): it failed at check 1 on the then- '
             'current Hub because propose answered blocking requirement_without_criterion; passed 7/7 '
             'after c9e94ed.'),
        ],
    },
    "ftester": {
        "document": 'spec/changes/a-tester-drives-the-built-product-and-keeps-the-spec-true/spec.json',
        "commit": '2367622',
        "tasks": ['task-36601c1e6a66', 'task-86c06ee69d17', 'task-9bcf48c030b9', 'task-9b392e629ebb', 'task-2a8589108daf'],
        "evidence": [
            ('FR-1', 'task-9b392e629ebb', 'test_result', 'hub/tests/test_tester_amendments.py',
             'test_a_named_tester_reviews_before_the_default_reviewer_and_after_the_task_s_own '
             'resolved t1 to the named tester tess and t2 to its own reviewer rev. '
             'test_a_flow_review_is_a_test_turn_by_default and test_tester_false_leaves_a_plain_review '
             'covered default-on and tester false.'),
            ('FR-1', 'task-9b392e629ebb', 'manual_observation', 'scripts/drive/d1013_tester_amends.py',
             'Drive d1013 check 4 asserted the review of the README task was queued to the named '
             'tester tess; the drive passed 9/9 against a live Hub with a real Haiku tester and '
             'builder.'),
            ('FR-2', 'task-9b392e629ebb', 'test_result', 'hub/tests/test_tester_amendments.py',
             "test_a_flow_review_is_a_test_turn_by_default asserted the duty text holds 'Drive the "
             "running product', the amend_spec_document call for the path, the side finding "
             'instruction and report_cannot_satisfy. test_tester_false_leaves_a_plain_review asserted '
             'the duty is empty with testing off.'),
            ('FR-3', 'task-86c06ee69d17', 'test_result', 'hub/tests/test_tester_amendments.py',
             'test_the_builder_is_refused_and_the_tester_amends asserted the builder run got 403 '
             'amend_not_tester with the stored document unchanged and the tester run got 201. '
             'test_testing_off_refuses_even_the_test_turn and '
             'test_a_document_not_approved_is_not_amended covered the other refusals.'),
            ('FR-4', 'task-86c06ee69d17', 'test_result', 'hub/tests/test_tester_amendments.py',
             'test_an_amendment_names_only_what_the_document_holds_and_says_how_to_check asserted '
             'unknown targets and a missing how_to_check were refused. '
             'test_an_added_task_joins_the_live_flow_at_once asserted an added task was materialised '
             'into the flow; test_the_builder_is_refused_and_the_tester_amends asserted add_criterion '
             'applied to the stored document.'),
            ('FR-4', 'task-86c06ee69d17', 'manual_observation', 'scripts/drive/d1013_tester_amends.py',
             "Drive d1013 checks 5-7: tess's real test turn recorded an add_task amendment, the task "
             'appeared pending on the flow board, and alice took it and produced a calc.py printing 1 '
             'for -2 3.'),
            ('FR-5', 'task-86c06ee69d17', 'test_result', 'hub/tests/test_tester_amendments.py',
             'test_each_amendment_records_author_and_run_and_is_not_reviewed asserted op, author, run '
             'and reviewed false. test_the_operator_marks_reviewed_per_item_then_for_the_document '
             'asserted marking by id then for the whole document; '
             'test_marking_an_amendment_the_document_does_not_hold_is_refused covered an unknown id.'),
            ('FR-6', 'task-9bcf48c030b9', 'test_result', 'hub/tests/test_tester_amendments.py',
             'test_a_changed_criterion_holds_its_requirement_until_reviewed asserted a requirement '
             'with accepted evidence and a not-reviewed change_criterion read amendment_unreviewed and '
             'read verified after the operator marked it reviewed. '
             'test_an_added_criterion_alone_never_holds_its_requirement covered the non-relaxing case.'),
            ('FR-6', 'task-9bcf48c030b9', 'manual_observation', 'scripts/drive/d1013_tester_amends.py',
             'Drive d1013 checks 8-9 asserted accepted evidence with a not-reviewed relaxing amendment '
             'read amendment_unreviewed and verified once marked reviewed. The relaxing amendment was '
             'inserted by the drive, not chosen by a Haiku turn.'),
            ('FR-7', 'task-86c06ee69d17', 'test_result', 'hub/tests/test_tester_amendments.py',
             'test_the_builder_reports_a_criterion_it_cannot_satisfy asserted a 201 with task_blocked, '
             "the in-progress task moved to blocked with 'cannot satisfy criterion c1', and a not- "
             'reviewed relaxing cannot_satisfy amendment by dev. '
             'test_a_run_on_no_task_of_the_document_cannot_report covered the refusal.'),
            ('FR-8', 'task-9bcf48c030b9', 'test_result', 'hub/tests/test_tester_amendments.py',
             'test_a_reapproval_with_unreviewed_amendments_lists_the_gap asserted approval returned '
             '409 approval_warnings listing amendments_unreviewed. '
             'test_the_documents_view_counts_the_amendments_not_reviewed covered the document view '
             'counts.'),
            ('FR-9', 'task-2a8589108daf', 'test_result', 'hub/ui/src/__tests__/specAmendmentsPanel.test.tsx',
             "specAmendmentsPanel tests (5): 'lists each amendment with author, run, reason and how to "
             "check', 'offers Mark reviewed only on the one not reviewed, and sends its id', 'marks "
             "every amendment reviewed for the document', the relaxing-hold notice, and empty render."),
            ('FR-1', 'task-36601c1e6a66', 'manual_observation', 'scripts/drive/d1013_tester_amends.py',
             'Acceptance drive d1013 was written in 477e69e and failed at check 1 (405) on the Hub '
             'before the build; after 2367622 and a747907 it passed 9/9 with a real Haiku tester and '
             'builder.'),
        ],
    },
    "freconcile": {
        "document": 'spec/changes/a-change-is-reconciled-with-its-code-before-it-is-folded/spec.json',
        "commit": 'e2ca744',
        "tasks": ['task-c5f6051efb4b', 'task-87647dce826b', 'task-1d686b0b8b41', 'task-21c0580dbd0f'],
        "evidence": [
            ('FR-1', 'task-87647dce826b', 'test_result', 'hub/tests/test_reconcile_and_defects.py',
             'test_a_reconcile_result_is_checked_and_recorded_with_its_run: an unknown class and a '
             'non-unrequested gap with no requirement were refused 422 (naming gaps[0].class / '
             'gaps[0].requirement); an empty-gap result was accepted 201 with author rex, run run-rex '
             'and zero counts. test_an_exploring_change_is_not_reconciled: 409.'),
            ('FR-1', 'task-87647dce826b', 'manual_observation', 'scripts/drive/d1014_reconcile.py',
             'Drive d1014 check 2: a real Haiku agent (rex) recorded a reconcile result through '
             'record_reconcile with a missing and an unrequested gap; the drive passed 4/4 at e2ca744.'),
            ('FR-2', 'task-87647dce826b', 'test_result', 'hub/tests/test_reconcile_and_defects.py',
             'test_asking_an_agent_to_reconcile_starts_its_turn_with_the_brief: the operator POST '
             'returned 202; the queued request named agent rex and the change path, and its message '
             'contained each brief word the test checks.'),
            ('FR-2', 'task-87647dce826b', 'manual_observation', 'scripts/drive/d1014_reconcile.py',
             "Drive d1014 check 1: the operator's POST .../reconcile returned 202 and started rex's "
             'real Haiku turn (it returned 405 on the pre-build Hub).'),
            ('FR-3', 'task-87647dce826b', 'test_result', 'hub/tests/test_reconcile_and_defects.py',
             'test_the_fold_state_carries_the_latest_result_and_fold_is_not_refused: '
             'fold_state.reconcile was {state: none} before any result; after two results it carried '
             'the second (summary, counts missing 1 / unrequested 1, gaps, requirement stored as its '
             'key).'),
            ('FR-3', 'task-87647dce826b', 'test_result', 'hub/tests/test_a_finished_change_is_folded_into_its_capability.py',
             'test_fold_state_reads_tasks_open_then_ready_then_folded: the ready fold_state was '
             'updated to include reconcile {state: none}, and the folded and tasks_open states still '
             'held.'),
            ('FR-3', 'task-21c0580dbd0f', 'test_result', 'hub/ui/src/__tests__/specReconcile.test.tsx',
             "'the phase bar says what reconciling found' and 'the fold dialog shows the counts and "
             "every gap' asserted the reconcile-result testid with author, counts and gaps; 'a change "
             "never reconciled says so' asserted reconcile-none and the ask call. Written after the "
             'components.'),
            ('FR-3', 'task-21c0580dbd0f', 'manual_observation', 'scripts/drive/d1014_reconcile.py',
             'Drive d1014 check 4: in Chromium the phase bar and the fold dialog showed the reconcile '
             'result once both tasks were decided.'),
            ('FR-4', 'task-1d686b0b8b41', 'test_result', 'hub/tests/test_reconcile_and_defects.py',
             'test_a_change_s_defects_are_derived_each_with_the_step_that_caught_it: an add_task '
             'amendment, a cannot_satisfy report, a task moved to revision_needed and a reconcile gap '
             'were listed with by_step test 1, build 1, review 1, reconcile 1; the operator-record '
             'source is covered under FR-6.'),
            ('FR-4', 'task-1d686b0b8b41', 'manual_observation', 'scripts/drive/d1014_reconcile.py',
             'Drive d1014 check 3: the defects report listed the change with a reconcile defect, a '
             'review send-back and an after-fold defect.'),
            ('FR-5', 'task-1d686b0b8b41', 'test_result', 'hub/tests/test_reconcile_and_defects.py',
             'test_a_change_s_defects_are_derived_each_with_the_step_that_caught_it: GET '
             '/project/spec/defects returned 200 with the change entry (path, defects, by_step counts '
             'per step).'),
            ('FR-5', 'task-21c0580dbd0f', 'test_result', 'hub/ui/src/__tests__/specReconcile.test.tsx',
             "'lists each change with its count per step, and opens it' and 'is absent while no change "
             "has a defect' asserted the spec-defects section rows. Written after the component."),
            ('FR-5', 'task-21c0580dbd0f', 'manual_observation', 'scripts/drive/d1014_reconcile.py',
             "Drive d1014 check 4: the spec page's defects section counted the change's defects by "
             'step in Chromium.'),
            ('FR-6', 'task-1d686b0b8b41', 'test_result', 'hub/tests/test_reconcile_and_defects.py',
             'test_the_operator_records_a_defect_at_a_step: the operator POST .../defects returned 201 '
             'with caught_by after-fold, an unknown step was refused 422 on caught_by, and the defect '
             'listed under by_step after-fold with its summary. '
             "test_a_journey_step_is_a_step_a_defect_can_be_caught_at: caught_by 'acceptance' returned "
             '201.'),
            ('FR-6', 'task-21c0580dbd0f', 'test_result', 'hub/ui/src/__tests__/specReconcile.test.tsx',
             "'records one against the open change with the step that caught it' asserted the record- "
             'a-defect form call. Written after the component.'),
            ('FR-6', 'task-c5f6051efb4b', 'manual_observation', 'scripts/drive/d1014_reconcile.py',
             'Drive d1014 check 3 recorded an after-fold operator defect through the route and saw it '
             'in the report.'),
            ('FR-1', 'task-c5f6051efb4b', 'manual_observation', 'scripts/drive/d1014_reconcile.py',
             'Acceptance drive d1014 was committed in 174bf2a before the build and failed at check 1 '
             'with 405 on the then-current Hub; after e2ca744 it passed 4/4 (reconcile ask, real Haiku '
             'result, defects report, Chromium page).'),
        ],
    },
    "fmanager": {
        "document": "spec/changes/the-hubs-background-jobs-are-configured-on-a-manager-page/spec.json",
        "commit": "1b73e84",
        "tasks": ["task-305e02593119", "task-d0ebb045d2d4", "task-402d75406e76", "task-7e3f1410556f"],
        "evidence": [
            ("FR-1", "task-d0ebb045d2d4", "test_result", MANAGER_TESTS,
             "test_a_project_with_no_rows_lists_the_title_job_disabled: conversation-titles listed in "
             "registry order, enabled false, runner_id and model null. Red at collection before 9db8fe6."),
            ("FR-2", "task-d0ebb045d2d4", "test_result", MANAGER_TESTS,
             "test_patching_refuses_unknown_jobs_and_foreign_runners: 404 for an unknown job, 400 for a "
             "foreign runner with the job unchanged, 200 with the job as listed; a patch changes only "
             "the fields it sends."),
            ("FR-3", "task-402d75406e76", "manual_observation", MANAGER_DRIVE,
             "Drive d1012 (scratch Hub, real Haiku turn): with the job on the Sonnet runner and model "
             "Haiku, the conversation was titled 'Sourdough bakery naming suggestions' by a Haiku spawn; "
             "disabled, the second kept its message. 0/1 before the build, 13/13 after."),
            ("FR-4", "task-402d75406e76", "test_result", MANAGER_TESTS,
             "test_each_spawn_records_one_firing_and_no_run: written and empty firings with every field, "
             "none for the excerpt already titled; test_a_failed_spawn_is_recorded_as_failed."),
            ("FR-5", "task-d0ebb045d2d4", "test_result", MANAGER_TESTS,
             "test_activity_is_newest_first_bounded_and_filterable: newest first, limit 2, filtered by "
             "job; a limit over 200 refused 422."),
            ("FR-6", "task-402d75406e76", "test_result", MANAGER_TESTS,
             "test_each_spawn_records_one_firing_and_no_run: Run count unchanged by titling; the "
             "firing's agent column is null and its payload holds no agent. Drive check 3c: one Run row."),
            ("FR-7", "task-d0ebb045d2d4", "test_result", MANAGER_TESTS,
             "test_the_settings_fields_read_and_write_the_job and "
             "test_a_settings_save_that_omits_the_title_fields_leaves_the_job_alone; drive check 2b."),
            ("FR-8", "task-d0ebb045d2d4", "test_result", "hub/tests/test_migrations.py",
             "-k manager: generate/truncate-with-runner/plain projects give two rows (enabled, disabled) "
             "and none; downgrade restores the original columns and drops the table, and keeps what the "
             "job became after the upgrade."),
            ("FR-9", "task-7e3f1410556f", "test_result", "hub/ui/src/__tests__/managerSection.test.tsx",
             "A 404 from the routes reads 'This Hub has no manager yet' with no alert; jobs, selects and "
             "firings render with their testids; a control sends only its field. Settings shows no title "
             "control (projectSettingsPanel.test.tsx)."),
            ("FR-9", "task-7e3f1410556f", "manual_observation", MANAGER_DRIVE,
             "Drive d1012 check 5 in Chromium: Environment > Manager showed the job and the firing; "
             "Settings had no 'Conversation title runner' control. Screenshot "
             "testbed/drive1012-manager-framework/145608/shot_manager.png."),
            ("FR-3", "task-305e02593119", "manual_observation", MANAGER_DRIVE,
             "Acceptance drive d1012 was committed in e04403e before the build and failed at check 1 "
             "(GET /manager/jobs 404) at 14:27; after 1b73e84 it passed 13/13."),
        ],
    },
    "fvault": {
        "document": "spec/changes/a-vault-the-operator-fills-with-text-and-agents-can-read/spec.json",
        "commit": "d0b863a",
        "tasks": ["task-dc529944bb06", "task-9b5325764989", "task-c09ec5d256bb", "task-bb3538ce93f4"],
        "evidence": [
            ("FR-1", "task-9b5325764989", "test_result", VAULT_TESTS,
             "test_settings_refuse_locations_in_the_project_and_bad_values: a relative path, the project, "
             "a path inside it, inside its worktrees, through '..', and under a file, plus a bad "
             "visibility, all 400 with nothing stored; a valid outside path is stored and created. "
             "Drive d1015 check 2a/2b."),
            ("FR-2", "task-9b5325764989", "test_result", VAULT_TESTS,
             "test_a_tracked_source_is_written_under_knowledge_byte_for_byte, "
             "test_a_private_source_leaves_only_a_stub_in_the_project, "
             "test_invalid_uploads_are_refused_and_write_nothing (400s, 413), default visibility. "
             "Drive checks 3 and 4: the CANARY text appears nowhere in the repository."),
            ("FR-3", "task-9b5325764989", "test_result", VAULT_TESTS,
             "test_the_map_is_built_from_the_files_newest_first: three entries newest first, a private "
             "entry listed once, a foreign stub available false with opening null, opening cut at 300; "
             "non-record files skipped."),
            ("FR-4", "task-9b5325764989", "test_result", VAULT_TESTS,
             "test_a_long_source_is_read_in_pages: 120,000 characters in three pages, rebuilt exactly; "
             "test_a_stub_held_elsewhere_and_unknown_ids: available false naming the holder, 404s."),
            ("FR-5", "task-c09ec5d256bb", "test_result", VAULT_TESTS,
             "test_an_agent_reads_the_map_and_an_entry_with_its_run_credential, "
             "test_no_agent_route_writes_to_the_vault, test_the_two_tools_are_on_every_runners_surface "
             "(MCP, call mode, Copilot's allowlist)."),
            ("FR-6", "task-c09ec5d256bb", "manual_observation", VAULT_DRIVE,
             "Drive d1015 check 6 (scratch Hub, real Haiku turn): the agent called vault_read with the "
             "transcript's id taken from its per-turn index, without vault_map, and answered 437 euros. "
             "Unit: empty vault adds nothing; 200 entries cut within 2,000 characters with a count."),
            ("FR-7", "task-9b5325764989", "test_result", VAULT_TESTS,
             "test_the_routes_work_unchanged_on_another_storage: an in-memory storage substituted for "
             "vault.storage serves upload, map and read, and nothing reaches the disk."),
            ("FR-8", "task-9b5325764989", "test_result", "hub/tests/test_migrations.py",
             "-k vault: 0123 -> head creates vault_settings with default tracked; the downgrade drops "
             "it and leaves projects untouched."),
            ("FR-9", "task-bb3538ce93f4", "test_result", "hub/ui/src/__tests__/vaultTab.test.tsx",
             "404 reads 'This Hub has no vault yet' with no alert; entries in route order; paged text; "
             "a stub's holder note; upload sends the default visibility; a refused location shows the "
             "Hub's reason."),
            ("FR-9", "task-bb3538ce93f4", "manual_observation", VAULT_DRIVE,
             "Drive d1015 check 7 in Chromium: the Vault tab listed both entries and showed the "
             "transcript's text. Screenshot testbed/drive1015-vault-text-sources/181809/shot_vault_entry.png."),
            ("FR-6", "task-dc529944bb06", "manual_observation", VAULT_DRIVE,
             "Acceptance drive d1015 was committed in 910c1f1 before the build and failed at check 1 "
             "(GET /vault/settings 404); after d0b863a it passed 10/10."),
        ],
    },
    "fdistil": {
        "document": "spec/changes/the-manager-distils-vault-sources-into-cited-facts/spec.json",
        "commit": "71de7c4",
        "tasks": ["task-1dc132c1b6f7", "task-d74f390256fd", "task-c067b98297d3"],
        "evidence": [
            ("FR-1", "task-d74f390256fd", "test_result", DISTIL_TESTS,
             "test_the_job_is_listed_disabled_with_nothing_chosen (trigger source_uploaded), "
             "test_the_jobs_model_wins_over_the_runners, "
             "test_with_no_runner_nothing_is_spawned_or_recorded (409 naming the runner, no spawn, "
             "no firing). Drive d1016 check 1 enables it on a Haiku runner."),
            ("FR-2", "task-d74f390256fd", "test_result", DISTIL_TESTS,
             "test_a_disabled_job_spawns_nothing_on_upload; every enabled test distils through the "
             "upload's background task. Drive d1016 check 2: the upload answered 201 in 0.0 s while "
             "Haiku ran after it; check 7: disabled, no fact and no firing."),
            ("FR-3", "task-d74f390256fd", "test_result", DISTIL_TESTS,
             "test_the_route_refuses_what_it_cannot_distil (404 unknown, 409 naming the holder of a "
             "foreign stub), test_a_disabled_job_spawns_nothing_on_upload (409 disabled), "
             "test_a_run_that_stores_nothing_keeps_the_facts_and_one_that_stores_replaces "
             "(written, empty, written: the empty run kept the first fact, the third replaced it)."),
            ("FR-4", "task-d74f390256fd", "test_result", DISTIL_TESTS,
             "test_quotes_are_found_in_the_source_and_unfound_ones_drop_the_fact (exact, "
             "whitespace-collapsed across two lines, and an unfound quote dropped; detail '2 facts "
             "stored, 1 dropped'), test_locate_spans_and_misses."),
            ("FR-4", "task-d74f390256fd", "manual_observation", DISTIL_DRIVE,
             "Drive d1016 check 3 with real Haiku (21:29 and 21:34): the 30-day fact cited line 6 and "
             "the 437-euro fact line 8, the lines that say them; every quote Haiku gave was found "
             "(0 dropped in both runs)."),
            ("FR-5", "task-d74f390256fd", "test_result", DISTIL_TESTS,
             "test_pieces_are_at_most_the_limit_and_end_at_a_line_break (120,000 chars, 3 pieces "
             "rejoining exactly), test_each_piece_is_one_spawn_and_one_firing (written, failed, "
             "written). Drive check 5: a written firing on claude-haiku-4-5 in the activity log."),
            ("FR-6", "task-d74f390256fd", "test_result", DISTIL_TESTS,
             "test_a_private_sources_facts_stay_private (record at the private location, a claimless "
             "stub in knowledge/facts, the canary nowhere in the project), "
             "test_a_tracked_fact_never_cites_a_private_source. Drive check 6 with real Haiku."),
            ("FR-7", "task-d74f390256fd", "test_result", DISTIL_TESTS,
             "test_facts_are_in_the_map_and_read_as_cards: kind on every entry, a fact right after "
             "its source with its claim as opening, a foreign stub available false, the card through "
             "the operator route and the agent-actions route. Drive check 4."),
            ("FR-8", "task-c067b98297d3", "test_result", "hub/ui/src/__tests__/vaultTab.test.tsx",
             "lists a source's facts under it and highlights a fact's cited lines; distils a source "
             "on request and shows why the Hub refused (409 reason in an alert)."),
            ("FR-8", "task-c067b98297d3", "manual_observation", DISTIL_DRIVE,
             "Drive d1016 checks 8 and 9 in Chromium: Distil on a source added while the job was off "
             "produced its fact; the refund fact's link highlighted line 8. Screenshots "
             "testbed/drive1016-distillation/<stamp>/shot_citation.png."),
            ("FR-4", "task-1dc132c1b6f7", "manual_observation", DISTIL_DRIVE,
             "Acceptance drive d1016 was committed in 6f86506 before the build and failed at check 1 "
             "(404, no vault-distillation job); after the build it passed 9/9."),
        ],
    },
    "fcontra": {
        "document": "spec/changes/sources-that-disagree-are-pointed-out/spec.json",
        "commit": "eb9190f",
        "tasks": ["task-df31c5b231e6", "task-7c1da4f4e71a", "task-112636985de8"],
        "evidence": [
            ("FR-1", "task-7c1da4f4e71a", "test_result", CONTRA_TESTS,
             "test_a_source_carries_its_date_and_a_bad_one_is_refused (metadata, stub and map carry "
             "dated; 400 for a bad format and an impossible day), "
             "test_a_private_sources_stub_carries_its_date. Drive d1017 check 1."),
            ("FR-2", "task-7c1da4f4e71a", "test_result", CONTRA_TESTS,
             "test_each_storing_distillation_is_followed_by_one_check (one more spawn, one "
             "facts_written firing with subject source), test_a_decision_source_is_not_distilled. "
             "Drive d1017 check 5: a written facts_written firing on claude-haiku-4-5."),
            ("FR-3", "task-7c1da4f4e71a", "test_result", CONTRA_TESTS,
             "test_the_compared_claims_are_capped_latest_dated_first (50,000-char cap, latest dated "
             "first, 'N left out' in the firing's detail)."),
            ("FR-4", "task-7c1da4f4e71a", "test_result", CONTRA_TESTS,
             "test_only_a_pair_of_one_new_and_one_sent_fact_is_kept_once, "
             "test_without_dates_the_later_upload_is_presumed. Drive d1017 check 3 with real Haiku: "
             "an open contradiction pairs the 437 fact with the 300 fact, the 300 one presumed "
             "although uploaded first (dated later)."),
            ("FR-4", "task-df31c5b231e6", "manual_observation", CONTRA_DRIVE,
             "Acceptance drive d1017 was committed before the build and failed at check 1; on the "
             "committed tree (831683d) it passed 9/9 on a scratch Hub with real Haiku "
             "(testbed/drive1017-contradictions/111419)."),
            ("FR-5", "task-7c1da4f4e71a", "test_result", CONTRA_TESTS,
             "test_a_contradiction_with_a_private_fact_is_private: the record at the private "
             "location, a stub in knowledge/contradictions holding no claim and no explanation."),
            ("FR-6", "task-7c1da4f4e71a", "test_result", CONTRA_TESTS,
             "test_disputed_facts_are_marked_in_the_map_the_cards_and_the_list (disputed, presumed, "
             "the card says DISPUTED and names the other fact). Drive d1017 checks 4 and 6c: a Haiku "
             "agent read the vault, answered 300 euros and said it was disputed."),
            ("FR-7", "task-7c1da4f4e71a", "test_result", CONTRA_TESTS,
             "test_resolving_writes_a_decision_and_supersedes_the_other_fact (decision source, record "
             "resolved, 404/409/400), test_resolving_for_neither_supersedes_both."),
            ("FR-8", "task-7c1da4f4e71a", "test_result", CONTRA_TESTS,
             "test_redistilling_drops_open_contradictions_and_keeps_resolved_ones."),
            ("FR-9", "task-112636985de8", "test_result", "hub/ui/src/__tests__/vaultTab.test.tsx",
             "Seven cases: lists an open contradiction with both claims, dates and the presumed side; "
             "resolves for one fact with a note; null for neither and the Hub's refusal shown; no "
             "form for one held elsewhere; a 404 is no section; disputed and superseded marks; the "
             "upload date. Drive d1017 check 7 in Chromium: resolved in the tab, a decision source "
             "written, the 437 fact superseded, nothing disputed."),
        ],
    },
    "freports": {
        "document": "spec/changes/a-working-agent-tells-the-manager-an-entry-is-wrong/spec.json",
        "commit": "eafb767",
        "tasks": ["task-c47364686c9b", "task-1ce508bb4520", "task-036f05924ff6"],
        "evidence": [
            ("FR-1", "task-1ce508bb4520", "test_result", REPORTS_TESTS,
             "test_the_job_is_listed_disabled_with_nothing_chosen. Drive d1024 check 1."),
            ("FR-2", "task-1ce508bb4520", "test_result", REPORTS_TESTS,
             "test_a_report_is_filed_by_the_runs_agent and test_a_report_is_refused_for_what_is_not_here_or_not_a_message: filed 201 with the reporter from the credential, a reporter in the body refused 422 "
             "(RequestModel, F116: the criterion said ignored; the Hub refuses, nothing is written), "
             "one open report per entry, the tool on every surface. Drive d1024 checks 3c and 5c."),
            ("FR-3", "task-1ce508bb4520", "test_result", REPORTS_TESTS,
             "test_a_report_on_a_private_fact_stays_at_the_private_location: a private one only at the private location with no stub."),
            ("FR-4", "task-1ce508bb4520", "test_result", REPORTS_TESTS,
             "test_each_report_is_one_firing_and_a_disabled_job_spawns_nothing: one spawn per report, one manager_job_fired firing. Drive d1024 check 7: two "
             "report_filed firings, one written, naming helper."),
            ("FR-5", "task-1ce508bb4520", "test_result", REPORTS_TESTS,
             "test_a_correction_is_stored_only_when_its_quotes_are_in_the_source: a correction stored only when every quote is located in "
             "the cited source, else referred; an unchanged claim referred (found by the drive)."),
            ("FR-5", "task-c47364686c9b", "manual_observation", REPORTS_DRIVE,
             "d1024 was committed before the build and failed at check 1 (no vault-reports job); on "
             "the committed tree (eafb767) it passed 13/13 with real Haiku "
             "(testbed/drive1024-reports/123525). The 3,000 fact was corrected to a new 300 fact "
             "citing line 4; a colleague's 500 was answered, not applied."),
            ("FR-6", "task-1ce508bb4520", "test_result", REPORTS_TESTS,
             "test_corrected_and_referred_reports_mark_their_facts: corrected supersedes by the new fact, referred disputes, in the map, the "
             "card and the list. Drive d1024 check 4: superseded_by the new fact and the card says so."),
            ("FR-7", "task-1ce508bb4520", "test_result", REPORTS_TESTS,
             "test_reports_are_listed_open_first_and_only_a_referred_one_closes: open first, close with a note, 409 once closed."),
            ("FR-8", "task-036f05924ff6", "test_result", "hub/ui/src/__tests__/vaultTab.test.tsx",
             "Four cases: the list with message, reporter, status and answer and a form only on a "
             "referred one; close sends the note and shows the 409 reason; a 404 is no section; a "
             "fact superseded by a corrected fact says so. Drive d1024 check 8 in Chromium."),
        ],
    },
}

# Where each roadmap change folds (2026-10-09): one capability, or {capability: [keys]} split.
CHANGE_FOLDS = {
    "fstorage": {'spec-document-authority': ['stored-as-json', 'rendered-on-open', 'diff-clean', 'one-seam', 'journey-written', 'conversion', 'reversible', 'refuses-while-busy'], 'spec-corpus-map': ['json-paths', 'legacy-reported']},
    "fsteps": {'spec-document-authority': ['journey-file', 'builtins-fixed', 'size-cap', 'operator-edits', 'invalid-reported', 'step-gone', 'bar-shows-journey'], 'spec-chat-session': ['custom-step-runs', 'append-own-step']},
    "fwarn": 'spec-document-authority',
    "ftester": {'agent-flows': ['tester-default', 'test-brief'], 'spec-document-authority': ['amend-who', 'amend-ops', 'amend-record', 'cannot-satisfy', 'unreviewed-gap', 'page'], 'requirement-traceability': ['relax-blocks']},
    "freconcile": 'spec-document-authority',
    "fvault": 'knowledge-vault',
    "fdistil": 'knowledge-vault',
    "fcontra": 'knowledge-vault',
    "freports": 'knowledge-vault',
    "fmanager": {
        'conversation-lifecycle': ['title-is-a-job'],
        'project-environment-settings': [
            'jobs-listed', 'job-configured', 'firing-recorded', 'activity-listed', 'not-an-agent',
            'settings-compatible', 'migration-keeps-behaviour', 'manager-section',
        ],
    },
}


def close(name: str) -> None:
    change = CHANGES[name]
    for identifier, task_id, kind, locator, summary in change["evidence"]:
        body = {
            "identifier": identifier, "kind": kind, "locator": locator, "summary": summary,
            "task_id": task_id, "document": change["document"],
        }
        if change.get("commit"):
            # The commit that built the change (F529); without it the evidence pins today's HEAD.
            body["commit"] = change["commit"]
        code, res = api("POST", f"/projects/{P}/project/spec/evidence", body)
        footprint = (res.get("footprint") or {}) if isinstance(res, dict) else {}
        print(name, "evidence", identifier, task_id, code,
              footprint.get("commit_sha", "")[:12] if code == 201 else json.dumps(res)[:300])
    for task_id in change["tasks"]:
        code, task = api("GET", f"/projects/{P}/tasks/{task_id}")
        if task["status"] == "approved":
            print(name, task_id, "already approved")
            continue
        for step in ("in_progress", "completed"):
            # A task already completed goes straight to landing; walking it back is refused.
            if task["status"] in (step, "completed"):
                continue
            code, task = api("PATCH", f"/projects/{P}/tasks/{task_id}", {"status": step})
            if code != 200:
                raise SystemExit(f"{name} {task_id} -> {step}: {code} {json.dumps(task)[:400]}")
        code, task = api("POST", f"/projects/{P}/tasks/{task_id}/land")
        print(name, task_id, "land", code, task.get("status") if code == 200 else json.dumps(task)[:400])


def fold(name: str, capability: str) -> None:
    """Fold the change into `capability` through the Hub, archiving it (the close-out's last step)."""
    path = CHANGES[name]["document"]
    code, res = api("POST", f"/projects/{P}/project/documents/{path}/fold", {"into": capability})
    print(name, "fold", code, res.get("phase") if code == 200 else json.dumps(res)[:400])


def fold_split(name: str, split: dict) -> None:
    """Fold each capability's share of the change's requirements; the last fold archives it."""
    path = CHANGES[name]["document"]
    targets = list(split.items())
    for index, (capability, keys) in enumerate(targets):
        body = {
            "into": capability,
            "requirements": [{"key": key} for key in keys],
            "archive": index == len(targets) - 1,
        }
        code, res = api("POST", f"/projects/{P}/project/documents/{path}/fold", body)
        print(name, "fold", capability, code, res.get("phase") if code == 200 else json.dumps(res)[:400])
        if code != 200:
            raise SystemExit(1)


if sys.argv[1:2] == ["--fold"]:
    fold(sys.argv[2], sys.argv[3])
elif sys.argv[1:] == ["--fold-journey"]:
    fold_split("fjourney", JOURNEY_FOLD)
elif sys.argv[1:2] == ["--fold-change"]:
    target = CHANGE_FOLDS[sys.argv[2]]

    def cap(name: str) -> str:
        return f"spec/capabilities/{name}/spec.json"

    if isinstance(target, dict):
        fold_split(sys.argv[2], {cap(name): keys for name, keys in target.items()})
    else:
        fold(sys.argv[2], cap(target))
else:
    for arg in sys.argv[1:]:
        close(arg)
