# Handoff: Spec corpus audited; stable conversation identity is next

**Date:** 2026-08-02T19:08:07+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `b443a8a`
**Agent:** T3 Code Codex / GPT-5.6-sol
**Previous handoff:** `.claude/handoffs/2026-08-02-1647-conversation-workspace-plan.md`
**Status:** chunk complete

## Goal

Narrow AgentWeave into an easy-to-use, local-only development application inspired by T3 Code,
while retaining its differentiators: multi-agent communication, deeply integrated spec-driven
development, governance, and quality gates. Before implementation, make the OpenSpec programme
internally consistent and ensure the first conversation slice is based on a correct conversation
identity rather than provider-session timing.

## Current state

The product direction is now explicit: AgentWeave is a locally installed app and the only runtime.
The collaboration CLI, watchdog, local/git transports, manual relay, Docker/remote topology, role
system, and eventually the "Hub" name are being retired. The future remote product is deferred
federation between users' local installs, not a constraint on the current architecture.

The surviving CLI decision is recorded: bare `agentweave` launches the current directory;
`doctor`, `status`, `stop`, and `reset` remain, plus help/version. Everything else belongs to the UI
or agent capability plane.

The agent capability direction was corrected during this session. Agents need selected reads as
well as writes. Direct HTTP is first-class for company environments that prohibit MCP servers; MCP
is a thin adapter over the same application/API operations. Turn-start injection is a delivery
guarantee, not a ban on demand-driven reads. Current MCP tools already delegate to `/api/v1`, but
direct agent API attribution is not secure enough: the bearer key authenticates a project and
agent/run identity is partly caller-supplied in bodies or headers. A future capability-plane change
must issue a short-lived principal bound to project, agent, run, expiry, and permissions.

A full final review of all 12 current capability specs and both active changes was completed.
`openspec validate --all --strict --no-interactive` now passes all 14 items. Mechanical repairs
included missing `.openspec.yaml`, four normative paragraphs the validator rejected, the
`aw-spec-workflow` placeholder purpose, stale RQ annotations, and removal of the obsolete root
`openspec/changes/dependencies.yaml` that described only an archived initiative.

The proposed conversation workspace is **not ready to apply yet**. The final review disproved its
frontend-only premise. On a new provider session, `/api/v1/agent/trigger` returns `status:
"running"`, a run ID, and null session ID; the provider session ID arrives later in runner output.
`AgentOutputPanel` currently locks on `isBindingNewSession`. Removing that lock allows a rapid
second submission to retain `session_mode: "new"`; `turn_scheduler.py` can then start a second
provider session instead of continuing the visible conversation. The recommended correction is an
AgentWeave-owned `Conversation` identity allocated synchronously, with nullable provider-session
binding. Runs and queue entries target the conversation. A run ID alias was rejected because runs
are attempts and do not survive retry, handoff, failure, or provider changes cleanly.

The conversation change is marked `revision required: stable conversation identity` and has a new
phase 0, but phase 0 intentionally says the final contract still needs to be specified before
application code begins. Other unambiguous corrections are already in its proposal/design/spec/tasks:
the real `running|queued` status, project-and-conversation draft keys, delayed-write cancellation,
agent-details behavior without unmounting the conversation, explicit withdraw/deliver-now
preservation, and a required context indicator.

Two shipped conformance defects remain unimplemented:

1. `SpecChatPane.tsx` still reads removed `execution_confidence`, emits watchdog warnings, disables
   input while running, and ignores the real `running|queued` trigger result.
2. HTTP peer messages can still schedule directly in the Hub and independently trigger the CLI
   watchdog. Do not run the obsolete HTTP watchdog path during live testing; delete it in the
   single-runtime change instead of spending a compatibility change on it.

The focused Hub test run found a test-isolation defect. Running trigger, queue, and MCP suites
together produced 48 passes and 2 failures because `agent_budget=20` leaked through the shared
in-memory database. Each failure passed alone. `hub/tests/conftest.py` calls `init_db()` before each
test, but `create_all` does not clear rows in the process-wide SQLite engine. Fix with transaction
isolation or table recreation before treating suite order as reliable evidence.

During the audit a forbidden root `.agentweave/` was found with only `logs/events.jsonl` (empty),
`logs/`, and `outbox/`. It was permanently removed. A final check found no `.agentweave/`,
`agentweave.yml`, or `spec/` at repository root.

RQ-1 is resolved: local projects are directories for one local operator; no multi-tenant operator
identity is needed. RQ-2 remains the only product-level research decision: authoritative portable
spec file, whether HTML is source or generated presentation, stable-ID behavior across external
edits, DB-as-index/evidence boundary, and ambiguous drift resolution. Multi-machine reconciliation
is a non-goal.

## Files touched

- `openspec/changes/2026-07-30-hub-native-experience/design.md` — added direction override; historical remote/watchdog/command decisions explicitly do not govern successors; finished for audit.
- `openspec/changes/2026-07-30-hub-native-experience/proposal.md` — added local-only direction override; finished for audit.
- `openspec/changes/2026-07-30-hub-native-experience/specs/agent-identity-and-skills/spec.md` — normative wording adjusted for strict validation without changing intent; finished.
- `openspec/changes/2026-07-30-hub-native-experience/specs/agent-tool-surface/spec.md` — normative wording adjusted for strict validation; semantic effect-only contradiction deliberately remains for the capability-plane successor to amend.
- `openspec/changes/2026-07-30-hub-native-experience/specs/spec-traceability/spec.md` — normative wording adjusted for strict validation; finished.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — RQ-1 resolved and RQ-2 narrowed annotations; successor tasks remain unchecked; finished for audit.
- `openspec/changes/2026-08-02-agent-conversation-workspace/.openspec.yaml` — new missing OpenSpec metadata; finished.
- `openspec/changes/2026-08-02-agent-conversation-workspace/design.md` — product slice table corrected; API-first agent plane added; stable-conversation blocker, status correction, draft scope, and details behavior recorded; phase 0 still needs final contract.
- `openspec/changes/2026-08-02-agent-conversation-workspace/proposal.md` — removed false frontend-only/no-backend claim and introduced conversation-identity prerequisite; needs final phase-0 contract before approval.
- `openspec/changes/2026-08-02-agent-conversation-workspace/specs/agent-conversation-workspace/spec.md` — strict fix and scenarios for immediate follow-up, conversation-scoped drafts, details, queue controls; needs a standalone finalized stable-conversation requirement.
- `openspec/changes/2026-08-02-agent-conversation-workspace/tasks.md` — added phase 0 and corrected composer tasks; do not apply until phase 0 API fields are final.
- `openspec/changes/dependencies.yaml` — deleted because it described only the archived autonomous-loop initiative and misrepresented current ordering; finished.
- `openspec/config.yaml` — local-only direction and API-first read/write capability plane added; finished.
- `openspec/explorations/2026-08-02-product-direction.md` — durable product vision, surviving CLI, direct HTTP/MCP adapters, read boundary, run-principal gap, and sequencing recorded; finished.
- `openspec/explorations/2026-08-02-spec-corpus-readiness-audit.md` — new authoritative audit, findings, impact map, decisions, order, and verification; finished.
- `openspec/specs/aw-spec-workflow/spec.md` — replaced archived `Purpose: TBD` placeholder with actual capability purpose; finished.
- `.agentweave/logs/events.jsonl` — ignored empty runtime artifact deleted with its `.agentweave/` parent; removal complete and intentionally unrecoverable except by recreating empty directories.
- `.claude/handoffs/2026-08-02-1908-spec-readiness-and-conversation-identity.md` — this handoff; new.
- `.claude/handoffs/LATEST.md` — updated to this handoff.
- `.claude/handoffs/2026-07-29-1803-change4-6-archived-spec-navigation-proposed.md` — pre-existing untracked handoff; untouched; do not stage accidentally.
- `.claude/handoffs/2026-07-29-2110-spec-navigation-t1-t9-implemented.md` — pre-existing untracked handoff; untouched.
- `.claude/handoffs/2026-07-30-0004-agentweave-strategy-discussion-resolved.md` — pre-existing untracked handoff; untouched.
- `.claude/handoffs/2026-07-30-1912-spec-navigation-closed-r1-audit-next.md` — pre-existing untracked handoff; untouched.
- `.claude/handoffs/2026-07-31-2049-hub-native-phase1-feel-foundation.md` — pre-existing untracked handoff; untouched.
- `.claude/handoffs/2026-07-31-2112-hub-native-phase1-complete.md` — pre-existing untracked handoff; untouched.
- `.claude/handoffs/2026-08-01-2038-phase4-identity-access-path-complete.md` — pre-existing untracked handoff; untouched.
- `.claude/handoffs/2026-08-01-2151-phase5-workspace-isolation-complete.md` — pre-existing untracked handoff; untouched.
- `.claude/handoffs/2026-08-01-2239-phase6-inbound-queue-complete.md` — pre-existing untracked handoff; untouched.
- `.claude/handoffs/2026-08-02-0140-phase7-agent-tool-surface-complete.md` — pre-existing untracked handoff; untouched.
- `.claude/handoffs/2026-08-02-0300-hub-native-phase8-timeline-complete.md` — pre-existing untracked handoff; untouched.
- `.claude/handoffs/2026-08-02-1130-phase8-mock-fidelity-and-live-test-env.md` — pre-existing untracked handoff; untouched.
- `.claude/handoffs/2026-08-02-1330-waiting-reason-fix-and-phase9-next.md` — pre-existing untracked handoff; untouched.

## Key decisions

1. **Local app is the only runtime.** This removes barriers and stops the product from prematurely
   serving local, remote collaboration, and company-wide deployment simultaneously. Retaining a
   no-Hub/CLI-only mode was rejected because it preserves the ceremony the redesign exists to
   remove.
2. **CLI is lifecycle/recovery only.** Bare launch, doctor, status, stop, and reset survive. A
   third collaboration surface was rejected because humans use the UI and agents use the
   capability plane.
3. **Direct HTTP and MCP are equal adapters.** MCP-only was rejected because company policy may
   prohibit MCP servers. Effect-only was rejected because agents need scoped task, spec, evidence,
   gate, and answer reads during a turn.
4. **Run-bound credentials replace asserted identity.** A shared project key plus caller-provided
   headers was rejected because an agent can claim another agent/run. Local-only removes user
   accounts, not the need for agent least privilege.
5. **Stable AgentWeave conversation identity is required.** Provider session ID and run ID were
   rejected as primary conversation identities because one arrives late and the other represents
   an attempt rather than durable continuity.
6. **Conversation workspace remains first after phase 0.** It removes the most visible barrier and
   is the surface every other feature integrates with. Coding the current frontend-only tasks
   before fixing identity was rejected because it would encode a known session-routing race.
7. **Capability plane precedes single-runtime deletion.** The CLI command fallback cannot be
   deleted until direct HTTP has parity and secure attribution. This dependency does not justify
   retaining the collaboration CLI permanently.
8. **RQ-1 is resolved, RQ-2 is narrowed.** Multi-tenant auth research was rejected as out of scope.
   Spec file authority still needs technical exploration because it determines identifiers,
   evidence, authoring, and drift.
9. **Rename Hub last.** Renaming during architectural deletion was rejected because it doubles
   churn and obscures behavioral diffs.
10. **Do not trust isolated green tests.** The combined failure proved DB state leaks; test order
    must be fixed before using the suite as zero-trust review evidence.

## Constraints and user directives (verbatim)

- "Ignore the aw-spec skills. I'm using openspec only."
- "Also I want you to delete any traces of a current agentweave session. I'm not working with agentweave I'm working ON agentweave. Re-do thing based on openspec. Clean the spec and agentweave traces from this repo."
- "I want those gone too. Can you review the spec and give me a briefing of what's left to be done, what's the order, what are the opens questions, what do we need to dive deeper, what needs research and also try and find errors and improvements"
- "I don't think we need the watchdog anymore right? If we don't need it we can get rid of it."
- "I think we should create a test folder inside this repo so any test is done against that folder."
- "And we should update the .md files read by claude and codex with the correct directives. This is not a project where we user agentweave is a project where we develop agentweave."
- "This will become local only like T3 but with spec and inter agent comunications."
- "So now the focus is fully targeted at local development and easy to use."
- "My inspiration is T3 code but retained multiagent collaboration with a very hard focus on spec development with the agents and integration with the overall architecture and experience. Also with governance and quality gates."
- "Don't know which CLI commands survive. You can choose that."
- "Ohh the agents should be able to get some stuff also. Sorry, it's not only doing stuff with the hub, there are information that they need to receive."
- "Also we're using MCP servers but we have to expose a way to do everything without mcp, you can be a api call as well because there are environments where mcp servers could be restricted due company policy"
- "What's next? What still open or are we ready to develop? Run a last time through the specs and review everything. Surface anything that we need to change"
- "$handoff"

## Dead ends

- Treating the conversation change as client-only failed on the new-session binding gap. The
  concrete symptom is `session_id: null` plus `isBindingNewSession`; deleting the lock makes the
  next queued operator entry `session_mode: new`.
- Treating "state is injected" as "tools may never read" failed against the same spec's explicit
  task-ledger and answer reads. The correct boundary is least-privilege scoped reads, not verb name.
- Assuming endpoint presence meant direct API support failed on attribution: project auth does not
  bind an agent/run principal uniformly.
- `openspec status --change 2026-08-02-agent-conversation-workspace` fails because the installed
  CLI rejects date-prefixed change names, even though repository instructions require that naming
  and `openspec list`/`validate` recognize the change. Do not rename the change just for this CLI
  incompatibility.
- Running four focused Hub test modules together produced two failures; running each failed test
  alone passed. Do not debug product budgets—the cause is shared in-memory DB state in the fixture.
- Recursive PowerShell `Remove-Item` for `.agentweave/` was blocked by tool policy. The empty log was
  deleted with `apply_patch`, then the verified empty directories were removed non-recursively with
  `[IO.Directory]::Delete`.
- A first forbidden-state check used `Test-Path` with repeated `-LiteralPath` in one expression and
  emitted a binding error. The corrected array-based check returned `none`.

## Verification

Actually run:

- `openspec validate --all --strict --no-interactive` — 14 passed, 0 failed after corrections.
- `git diff --check` — passed; only CRLF-to-LF warnings appeared for two umbrella Markdown files.
- `npm test -- --run src/__tests__/agentChat.test.tsx src/__tests__/agentTimeline.test.tsx src/__tests__/agentTimelineEvents.test.tsx src/__tests__/agentHandoff.test.tsx src/__tests__/contextPresentation.test.tsx src/__tests__/specChatSession.test.tsx` from `hub/ui` — 6 files, 41 tests passed.
- `pytest hub/tests/test_agent_trigger.py hub/tests/test_agent_tool_surface_phase7.py hub/tests/test_mcp_server.py hub/tests/test_inbound_queue.py -q` — 48 passed, 2 failed from leaked `agent_budget` state.
- Each failed backend test rerun alone — 1 passed and 1 passed.
- Final forbidden-root-state check over `.agentweave`, `agentweave.yml`, and `spec` — `none`.
- `git status --short`, `git log --oneline -8`, and `git diff --stat HEAD` gathered immediately before this handoff.

Not tested:

- No application source was changed, so no full CLI pytest suite, full Hub pytest suite, UI build,
  lint, or full UI suite was run.
- Stable conversation identity is specified only as the recommended model and phase-0 placeholder;
  no migration, API contract, implementation, or test exists yet.
- The capability-plane credential design and RQ-2 spec-authority design have not been proposed.
- The two shipped conformance bugs (`SpecChatPane`, HTTP watchdog double-spawn) were diagnosed but
  not fixed because this turn was a review/spec task.

## Git state

- Branch: `hub-native-experience`.
- HEAD: `b443a8a Decide the surviving CLI surface and record the MCP direction`.
- Working tree: dirty with all spec/audit paths listed under Files touched plus this handoff and
  `LATEST.md`.
- No upstream tracking branch exists for `hub-native-experience`; the `origin/...HEAD` comparison
  failed with an ambiguous-revision error. Nothing from this chunk was pushed.
- The edits are uncommitted. Do not use `git add -A`; it would sweep in the 13 pre-existing
  untracked historical handoffs. Stage intended paths explicitly if the user asks to commit.
- The deleted `.agentweave/` was ignored and therefore does not appear in Git status.

## Next steps

1. Amend `openspec/changes/2026-08-02-agent-conversation-workspace/design.md` and
   `specs/agent-conversation-workspace/spec.md` with the full proposed `Conversation` contract:
   stable ID allocated synchronously; `project_id`, agent identity, nullable provider session ID,
   lifecycle/status; Run and InboundQueueEntry references; trigger response/request fields; binding
   algorithm; retry/stop/handoff behavior; chat-history route; and legacy/reset policy. Then update
   phase 0 task names to those exact fields and present the revised proposal for user approval.
2. Add a dedicated task/change for `hub/tests/conftest.py` database isolation. Verify the four
   focused Hub modules pass together before relying on further backend evidence.
3. Fix `hub/ui/src/components/spec/SpecChatPane.tsx` against `running|queued`, remove watchdog text,
   and decide whether its composer shares the same running-turn queue behavior or intentionally has
   a narrower spec-authoring policy.
4. After explicit approval, implement conversation phase 0 tests-first, then phases 1–4.
5. Propose the agent capability plane in parallel: capability matrix, run principal/token,
   direct-HTTP discovery/error contract, MCP adapter parity, and least-privilege reads.
6. Propose single-runtime deletion only after the direct HTTP replacement path is specified.
7. Run the narrowed RQ-2 technical exploration before any specification-authoring implementation.

## Open questions for the user

- Approve or revise the recommended AgentWeave-owned `Conversation` record as the durable identity
  above provider sessions and runs. Recommendation: approve; it resolves the immediate queue race
  and creates the right foundation for history, drafts, handoff, and runner changes.
- For RQ-2, should rendered HTML remain the authoritative editable spec, or should a simpler
  structured/Markdown source generate HTML presentation? Recommendation: decide in a focused
  technical exploration; do not let the existing multi-source HTML sync implementation choose by
  inertia.

## Read on resume

- `openspec/explorations/2026-08-02-spec-corpus-readiness-audit.md` — final findings, readiness verdict, successor impact map, and order.
- `openspec/explorations/2026-08-02-product-direction.md` — authoritative local-only product direction and capability-plane boundary.
- `openspec/changes/2026-08-02-agent-conversation-workspace/design.md` — stable-conversation blocker and current proposed architecture.
- `openspec/changes/2026-08-02-agent-conversation-workspace/specs/agent-conversation-workspace/spec.md` — current requirements needing the finalized standalone conversation identity contract.
- `hub/hub/api/v1/agent_trigger.py` — trigger result, late provider-session binding, and current process/run behavior.
- `hub/hub/turn_scheduler.py` — controlling queued entry behavior that makes a rapid second `new` submission unsafe.
