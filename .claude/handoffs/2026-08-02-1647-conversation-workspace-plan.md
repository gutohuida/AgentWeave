# Handoff: Full Hub mock completed and conversation-first implementation plan agreed

**Date:** 2026-08-02T16:47:45+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `fc17d79`
**Agent:** Codex / GPT-5.6-sol
**Previous handoff:** `.claude/handoffs/2026-08-02-1330-waiting-reason-fix-and-phase9-next.md`
**Status:** chunk complete

## Goal

Turn the Hub from its current section-heavy dashboard into the project-native experience represented
by `mock-full.html`, prioritising the agent conversation as the first real implementation slice. The
long-term differentiator is a specification workspace that connects requirements, tasks, runs,
evidence, and AI-assisted authoring, but that system must receive its own deeper design pass rather
than being implemented from the visual mock alone.

## Current state

The visual mock iteration is complete for this chunk. `mock-full.html` now presents a projects-and-
agents rail, a project overview whose modules link to deep views, a direct full-height agent
conversation, a taller/narrower composer, and a document-dominant Spec workspace with contextual AI
proposals instead of a permanent static right-hand chat panel. The final layout fix made all primary
containers explicitly full width, raised their shared maximum to 1180px, and changed the agent roster
to `auto-fit` 160px columns. At a 1280x800 preview the overview occupied the available 1028px content
width, all five agents fit in one row, and the overview modules fit above the fold. Commit: `fc17d79`.

A read-only technical audit then inspected all ten active delta specs, the active change proposal,
design, and task ledger, the canonical HTML spec index/system map/roadmap, and the relevant Hub
backend and React components. Phases 1-8 of the active change are complete. There are 69 unchecked
task items remaining (including verification and handoff tasks): Phase 9 accounting/budgets (5),
Phase 10 projects/navigation (8), Phases 11-12 composer (14), Phase 13 identity/charters/skills (15),
Phase 14 spec traceability/authoring (19), Phase 15 approvals (4), and Phase 16 closeout (4).

The audit found that the conversation's hard backend foundation already exists: direct execution,
SSE output, durable inbound queue, typed merged timeline, peer-message integration, stable agent
colours, stop, and withdrawal. The visible application still uses the old flow
`AgentsPage -> AgentDetailPanel tabs -> Output -> AgentOutputPanel`, with duplicate headers, a
separate Messages surface, raw session controls, and an undersized composer. Critically,
`AgentOutputPanel.interactionLocked` includes `isRunning`, so the textarea is disabled during a run.
That contradicts `agent-inbound-queue`, which requires operator messages submitted during a running
turn to enter the queue and appear immediately as undelivered.

The audit also found that Phase 10 is understated. Current authentication maps each bearer API key
to exactly one `Project` in `hub/hub/auth.py`; the local setup endpoint returns the first non-revoked
project key. A genuine project list/switcher therefore requires an operator-level selection/session
contract, project-key switching, SSE resubscription, and project-scoped React Query invalidation. It
cannot be completed as a sidebar-only frontend task.

The agreed strategic direction is:

1. Do not finish current phases 9-16 in their existing order before improving the conversation.
2. Do not add the whole mock and all remaining capabilities to one giant active change.
3. Treat phases 1-8 as the stable completed foundation.
4. Turn the remaining work into a roadmap of focused, independently approvable change specs.
5. Create and implement an **Agent Conversation Workspace** change spec next.
6. Follow with separate changes for multi-project/auth, composer intelligence, accounting, runner/
   agent/charter separation, and then the specification program.

The first focused conversation spec should include direct project/agent navigation, direct overview
links, back-to-project, removal of the Agents master-detail and Output/Messages tab structure, the
unified timeline as the message surface, queueable input during a running turn, a taller autosizing
composer, per-conversation drafts, banner stack, consolidated controls/overflow, and preservation of
session continuity and handoff. It should use a current-project rail adapter designed to accept a
multi-project collection later, but must not claim to implement project creation/switching.

The first conversation spec should explicitly exclude real multi-project switching, project
creation, runner records/model reassignment, charters/templates, full trigger suggestions if they
make the slice too large, specification authoring, requirement traceability, and approval gates.

The future Spec program should be split into: (1) portable stable requirement model and rigor,
(2) task/evidence/run traceability, (3) document reading workspace with inline verification state,
(4) contextual AI authoring with in-position proposals and individual accept/reject/discuss, and
(5) stale evidence, implementation drift, gates, and approvals. Before implementation it must
resolve the coexistence of Markdown under `openspec/` and authoritative portable HTML under `spec/`.
The recommended architecture is that portable files remain authoritative while the database acts as
an indexed read model for requirement identity, links, evidence, proposals, and live state.

## Files touched

- `openspec/changes/2026-07-30-hub-native-experience/mock-full.html` — revised throughout the mock
  iteration; final width/roster fix committed in `fc17d79`; finished for this chunk.
- `.claude/handoffs/2026-08-02-1647-conversation-workspace-plan.md` — this handoff; new.
- `.claude/handoffs/LATEST.md` — updated to this handoff; tracked.
- `.claude/handoffs/2026-07-29-1803-change4-6-archived-spec-navigation-proposed.md` — pre-existing
  untracked handoff; not touched; do not stage as part of application work.
- `.claude/handoffs/2026-07-29-2110-spec-navigation-t1-t9-implemented.md` — pre-existing untracked;
  not touched.
- `.claude/handoffs/2026-07-30-0004-agentweave-strategy-discussion-resolved.md` — pre-existing
  untracked; not touched.
- `.claude/handoffs/2026-07-30-1912-spec-navigation-closed-r1-audit-next.md` — pre-existing untracked;
  not touched.
- `.claude/handoffs/2026-07-31-2049-hub-native-phase1-feel-foundation.md` — pre-existing untracked;
  not touched.
- `.claude/handoffs/2026-07-31-2112-hub-native-phase1-complete.md` — pre-existing untracked; not
  touched.
- `.claude/handoffs/2026-08-01-2038-phase4-identity-access-path-complete.md` — pre-existing untracked;
  not touched.
- `.claude/handoffs/2026-08-01-2151-phase5-workspace-isolation-complete.md` — pre-existing untracked;
  not touched.
- `.claude/handoffs/2026-08-01-2239-phase6-inbound-queue-complete.md` — pre-existing untracked; not
  touched.
- `.claude/handoffs/2026-08-02-0140-phase7-agent-tool-surface-complete.md` — pre-existing untracked;
  not touched.
- `.claude/handoffs/2026-08-02-0300-hub-native-phase8-timeline-complete.md` — pre-existing untracked;
  not touched.
- `.claude/handoffs/2026-08-02-1130-phase8-mock-fidelity-and-live-test-env.md` — pre-existing
  untracked; not touched.
- `.claude/handoffs/2026-08-02-1330-waiting-reason-fix-and-phase9-next.md` — previous handoff,
  pre-existing untracked; read but not modified.
- `.claude/skills/aw-spec-reindex/` — pre-existing untracked skill directory; not touched.

## Key decisions

1. **Conversation workspace is next, ahead of accounting.** The user identified it as the most
   important surface, and the backend foundations are already complete. Waiting for all current
   phases would postpone the largest user-facing improvement while continuing to build around an
   interaction model already scheduled for removal.
2. **Use a new focused change spec, not one new spec for the entire remaining epic.** The active
   `hub-native-experience` change has become an umbrella with 69 remaining checklist items. Adding
   more implementation detail to it would make approval, testing, and completion ambiguous. The
   conversation spec must own its extracted tasks; the umbrella task plan should link to the child
   spec and must not leave duplicate active tasks.
3. **Do not implement true multi-project switching in the conversation slice.** A current-project
   rail adapter provides the intended shell immediately and can later consume a list. Pretending the
   sidebar alone is multi-project support was rejected because project-scoped authentication and SSE
   make that unsafe and incomplete.
4. **Messages disappear as a UI destination, not as a persistence model.** Peer and operator traffic
   already belongs in the unified timeline. Deleting message storage/API prematurely was rejected
   because those records are still source data for routing, attribution, and history.
5. **Keep only high-frequency controls visible.** Visible composer controls: add context/files,
   commands/skills, active agent, context usage, send/queue, and stop while running. New conversation,
   history/session identity, handoff, fold-all, and agent details move to overflow. Pause-scroll and
   duplicate header/status controls are removed. Permission mode remains out until behavior exists.
6. **Spec work gets a dedicated discovery/design pass.** Implementing the mock's Accept/Reject/
   Discuss UI before deciding file authority, stable IDs, revisions, proposal concurrency, and
   external reconciliation was rejected because it would force a second migration later.
7. **Do not fake overview data.** Agents, questions/input, task counts, jobs, and activity can be real
   now. Specification-health percentages must wait until requirement traceability derives them.

## Constraints and user directives (verbatim)

- "Yeah and always commit the changes."
- "Chat box taller and a bit narrower. What other controls can we put inside the chatbox?"
- "I also want to get rid of the control box at the top.  Another things. I don't think will need all this controls for the future, what are we keeping? We don't need messages anymore for example since all the messages will be enbeded on the conversarions"
- "The navigation is not intuitive. For example, once I go into tasks I have to go back clicking on the folder to see the navigations again and the overview page seems too empty. Should we fold everything inside the overview and if the user wants to deep dive he clicks on the screen and also a back buton. Also we need to work better on the spec page. Since one of the strong suits of the agentweave will be building the specs and it's connections to the agents. Review the specs."
- "No need to follow spec-explore. Let's mock these changes on the mock-full. The idea is the overview not have everything detailed, but a overview of the information of the other tabs. And then we can deep dive from there with a back button, what do you think?"
- "The overview screen still kind of empty. The sides we have nothings we need to better use the space. Also I don't know If I'm a fan of the things in boxes. Should we try to have something that only highlights when we hover over? Also the spec screen we have to find a way to integrate better the AI on the spec. The right box feels to static and hard"
- "It's still very bad utilized the space. Can you take a look? Also search for best UI practices for this kind of things. And better arrange the information"
- "Okay, this is all mock. Based on what we still have to implement how can we fit this mock on things? I think first and the most important is to transform the agent conversation screen. At some point I want do really deep dive on the solution for the spec page, because that will be the big differentiator. Look at all the specs, what we have to develop yet and come up with a plan on how to proceed"
- "Should all of this be a new spec? Should we first finish all the things that we're building, the current phases and then move to this? Or should we just add this in?"

## Dead ends

- The overview initially remained only 569px wide inside a roughly 1018px main content area. The
  cause was flex-item shrink-wrapping: `.overview-grid` and related containers had `max-width` and
  auto margins but no explicit width. Adding `width:100%` fixed it. Do not try to solve this again by
  adding more cards or padding.
- The agent roster originally wrapped four-plus-one at the inspected desktop width because
  `auto-fill,minmax(200px,1fr)` required too much minimum width. `auto-fit,minmax(160px,1fr)` placed
  all five in one row.
- The T3 preview intermittently failed or briefly returned a stale-looking screenshot during Spec
  navigation. Retrying the preview and checking DOM geometry/visible text showed the correct Spec
  page. Do not infer a mock navigation bug from one stale preview frame.
- The existing canonical reconstruction roadmap reports R1-R4 as planned even though substantial
  implementation exists. It is stale and should not be used as the current task ledger without
  reconciliation.

## Verification

Actually run and passed during the final mock change:

- `git diff --check` — passed before commit `fc17d79`.
- T3 collaborative preview at 1280x800 — overview visually inspected; full 1028px content width,
  five agent tiles in one row, overview grid visible above the fold.
- T3 collaborative preview — Spec deep view inspected; project back button, document navigator,
  document body, inline proposal controls, and contextual AI composer were present.
- `git commit -m "Fix dashboard width and responsive roster layout"` — created `fc17d79` with 6
  insertions and 6 deletions in `mock-full.html`.

Read-only planning checks performed:

- Read all ten active delta specs under
  `openspec/changes/2026-07-30-hub-native-experience/specs/*/spec.md`.
- Read remaining task lines for phases 9-16 and counted 69 unchecked items.
- Inspected `spec/index.json`, `spec/system-map.html`, the canonical baseline headings, the
  reconstruction roadmap, and the archived Add Spec Navigation change.
- Inspected current conversation, navigation, overview, Spec workspace, authentication, project,
  run, and usage-parsing code.

Not tested:

- No application code was changed during the spec audit, so no Hub, CLI, TypeScript, Vitest, or
  pytest suite was run in this planning chunk.
- The focused Agent Conversation Workspace spec has not yet been written or approved.
- The current mock is static and does not prove backend integration.
- True multi-project authentication/switching remains undesigned and unimplemented.

## Git state

- Branch: `hub-native-experience`.
- HEAD before this handoff commit: `fc17d79 Fix dashboard width and responsive roster layout`.
- No upstream tracking branch is configured (`origin/hub-native-experience` unavailable); nothing
  was pushed.
- `mock-full.html` is clean and committed.
- The working tree contains the handoff/LATEST changes from this operation plus the pre-existing
  untracked handoffs and `.claude/skills/aw-spec-reindex/` listed under Files touched. Do not stage
  the pre-existing untracked files as part of the next application change.

## Next steps

1. Create `spec/changes/<timestamp>-agent-conversation-workspace/spec.html` using the approved HTML
   spec workflow. Its requirements and tasks must cover direct project/agent navigation, removal of
   the Agents master-detail/Output/Messages layers, unified timeline, queueable running-turn input,
   taller autosizing composer, per-conversation drafts, banner stack, consolidated controls, current-
   project rail adapter, session/handoff preservation, tests, and explicit non-goals listed above.
2. Update the active umbrella plan so tasks extracted into the conversation change link to that
   child spec and are not simultaneously active in two places. Do not mark unimplemented tasks done.
3. Present the focused spec for explicit user approval before application code changes.
4. After approval, implement the conversation slice tests-first. At minimum extend
   `agentChat.test.tsx`, `agentTimeline.test.tsx`, `App-mount.test.tsx`, and navigation UI tests; add
   dedicated composer/draft/queue-during-run tests.
5. After the conversation slice, technically explore and specify multi-project operator auth before
   building the real project switcher.
6. Keep the specification workspace as a separate later discovery/specification program; do not
   fold it into the conversation change.

## Open questions for the user

- Whether the full `@` path, `/` command, and `$` skill trigger system belongs in the first
  conversation change or in the immediately following composer-intelligence change. Recommendation:
  keep the first slice to the shell, queue behavior, draft persistence, and control consolidation;
  implement trigger menus in the next focused change.
- Whether to retain an optional project-level Agent Directory deep view after agents become directly
  reachable from the rail and overview. Recommendation: remove it initially; restore only if a real
  bulk-management workflow emerges.

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — completed phases and remaining
  umbrella tasks that need extraction/reordering.
- `openspec/changes/2026-07-30-hub-native-experience/mock-full.html` — approved visual direction for
  the conversation, project shell, overview, and provisional Spec workspace.
- `openspec/changes/2026-07-30-hub-native-experience/specs/agent-conversation-timeline/spec.md` —
  existing conversation behavior already implemented in phases 6-8.
- `openspec/changes/2026-07-30-hub-native-experience/specs/agent-composer/spec.md` — existing composer
  requirements to carry forward without duplication.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` — current conversation orchestration and the
  running-turn input lock that must be corrected.
- `hub/ui/src/App.tsx` — current flat Page enum/navigation model that the focused change must replace.
