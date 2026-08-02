# Exploration — Specification corpus readiness audit

**Date:** 2026-08-02
**Status:** Final review after the local-only product-direction decision
**Scope:** Current capability specs, both active changes, their task ledgers, and critical code
claims that determine whether implementation may begin

## Verdict

The corpus is structurally valid, but the conversation change is not yet ready to apply and the
remaining programme is not ready for unsequenced implementation.

The next implementable work is to finish the stable-conversation amendment in phase 0 of
`2026-08-02-agent-conversation-workspace`. After that amendment is reviewed, the conversation
workspace is the first development slice. The agent capability plane may be proposed in parallel
and must land before the single-runtime change removes the command fallback.

## Blocking findings

### 1. A new conversation has no stable identity when immediate follow-up input arrives

Evidence:

- `hub/hub/api/v1/agent_trigger.py::trigger_agent_directly` returns `status: "running"`, a
  `run_id`, and a null `session_id` for a new provider session.
- `_execute_run` learns and persists the provider session ID only after parsing runner output.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx` uses `isBindingNewSession` to lock the
  composer during that gap.
- `hub/hub/turn_scheduler.py` treats a queued operator entry carrying `session_mode: "new"` as the
  controlling entry for the next turn.

Therefore simply removing the UI lock can turn a rapid second message into another new provider
session. The target model needs an AgentWeave conversation ID allocated before provider session
binding. This changes persistence, trigger/queue/chat contracts, and frontend routing. The original
"no backend change" claim was false and has been removed.

### 2. Direct HTTP agent access lacks a uniform run principal

Every current MCP tool delegates to `/api/v1`, which is the correct adapter direction. However,
`hub/hub/auth.py::_project_from_api_key` authenticates only a project. Agent and run attribution is
then carried in request fields or `X-AgentWeave-*` headers. Job mutations validate those headers
against a live run, but messaging, task, and question effects do not share one run-principal
dependency.

The capability-plane proposal must introduce a short-lived credential bound to project, agent,
run, expiry, and permitted capabilities. Direct HTTP and MCP must use the same principal and the
same application operations. The operator/UI principal remains distinct.

### 3. Active umbrella requirements conflict with the decided target

`2026-07-30-hub-native-experience` remains active because 69 tasks are unchecked. Its completed
phases and current baseline specs still describe retained watchdog duties, local/git transports,
CLI command parity, role guides, `agentweave.yml`, and remote/multi-source reconciliation. Those
describe current or historical behavior, not the target product.

The umbrella now carries a direction-override banner. Successor changes must amend affected
baseline capabilities explicitly; checked umbrella tasks must not be treated as evidence that the
new direction is already implemented.

## Defects found in shipped code

### Spec chat still consumes the removed trigger contract

`hub/ui/src/components/spec/SpecChatPane.tsx` branches on
`triggerResponse.execution_confidence`, still mentions the watchdog in warnings, and ignores the
actual `status: "running" | "queued"` response. It therefore reports the wrong state and preserves
removed runtime language. This is a conformance bug against the already implemented direct-trigger
runtime and should be fixed before or alongside the conversation workspace.

### HTTP-mode peer messages still have two launch paths

`hub/hub/api/v1/messages.py` schedules the recipient directly while the CLI watchdog can also react
to the same pending message. The double-spawn is real. A targeted compatibility fix is lower value
than removing the watchdog, but development and live testing must not run that obsolete HTTP
watchdog path in the meantime.

### Hub tests leak database state between test cases

A focused combined run of trigger, queue, and tool-surface suites produced two order-dependent
failures: a project `agent_budget` remained `20` instead of the default `8`, and a later
agent-request test saw an exhausted budget. Each failed test passed when run alone.

`hub/tests/conftest.py` uses one process-wide in-memory SQLite engine and calls `init_db()` before
each test, but `create_all` does not clear existing rows. Tests that mutate the bootstrap project
therefore affect later tests. The fixture must isolate transactions or drop/recreate tables before
each case. Until fixed, a green test run can depend on file/order selection and is not zero-trust
evidence.

## Conversation-spec corrections made in this audit

- Corrected the trigger outcome from `started` to the implemented `running`.
- Changed context-indicator behavior from optional `SHOULD` to required `SHALL`.
- Scoped drafts by project and conversation rather than agent, including isolation between two
  conversations for one agent and cancellation of delayed writes on successful submission.
- Defined agent details as a non-navigating panel that preserves the mounted conversation.
- Made preservation of withdraw and deliver-now controls explicit.
- Added phase 0 for stable conversation identity and marked the change revision-required.
- Added the missing `.openspec.yaml` metadata file.

## Corpus maintenance corrections made in this audit

- Removed `openspec/changes/dependencies.yaml`; it described only the already archived autonomous
  development loop and was actively misleading about current order.
- Replaced the archived placeholder purpose in `openspec/specs/aw-spec-workflow/spec.md`.
- Updated stale RQ-1/RQ-2 annotations in the umbrella task ledger.
- Added direction overrides to the umbrella proposal and design.
- Reworded four normative paragraphs so strict OpenSpec validation recognizes them.
- Removed the forbidden root `.agentweave/` artifact found during the review.

## Successor-change impact map

| Successor | Must amend or reconcile |
|---|---|
| Stable conversation / conversation workspace | `agent-conversation-handoff`, active `agent-inbound-queue`, active `agent-conversation-timeline`, trigger/queue/chat/session contracts |
| Agent capability plane | active `agent-tool-surface`, `agent-context-onboarding`, agent-facing task/question/message/job operations |
| Single runtime | `runtime-diagnostics`, `agent-stream-events`, `agent-context-usage`, `agent-context-onboarding`, `opencode-config`, `opencode-runner`, `project-instructions` |
| Runner / agent / charter separation | active `agent-identity-and-skills`, `agent-context-onboarding`, `aw-spec-workflow`, every role-guide consumer |
| Specification program | `aw-spec-workflow`, `spec-manifest-sync`, active `spec-authoring`, active `spec-traceability`, `spec-chat-session` |
| Retire the Hub name | All public docs/spec language and package/UI labels, after architecture settles |

## Remaining decisions and research

### Decision needed now: stable conversation identity

Recommended: create an AgentWeave-owned conversation record with a stable ID, project and agent
scope, and nullable provider-session binding. Queue entries and runs reference it. Do not use a
run ID as the long-term conversation identity; runs are attempts within a conversation and do not
survive retry, handoff, or provider changes cleanly.

### Technical exploration needed: specification authority

RQ-2 is the only remaining product-level research question. Decide:

1. which portable file is authoritative for a user's specification;
2. whether rendered HTML is source or generated presentation;
3. how stable requirement IDs survive rewording, reordering, and external-editor changes;
4. which database records are indexes/evidence rather than competing sources of truth; and
5. how a user resolves ambiguous drift.

Multi-machine and multi-user reconciliation are non-goals. Existing `spec-manifest-sync`
requirements for multiple active machines must not dictate the local design.

### Design work, not external research: capability plane

Define a capability matrix (resource, read/write operation, principal, scope, approval rule), the
run credential, direct HTTP discovery/error contracts, and parity tests proving MCP and HTTP reach
the same operation. No market or protocol research is required to begin that proposal.

## Recommended order

1. Approve the stable-conversation model and complete phase 0 of the conversation change.
2. Fix the stale Spec Chat trigger contract.
3. Implement the conversation workspace.
4. Propose and implement the agent capability plane.
5. Implement the single-runtime deletion after direct HTTP parity exists.
6. Implement runner/agent/charter separation to remove setup ceremony.
7. Complete the specification-authority technical exploration, then propose the specification
   program.
8. Add approval gates on top of stable conversation and specification identities.
9. Follow with composer intelligence, local multi-project workspaces, and accounting as their
   dependencies permit.
10. Retire the Hub name last.

Accounting is independently implementable but lower priority than the barriers and differentiators
above. Local multi-project work no longer needs identity research, but should follow single runtime
so it is designed around directories rather than project-scoped remote credentials.

## Validation

- `openspec validate --all --strict --no-interactive`: 14 passed, 0 failed.
- `git diff --check`: passed.
- Focused UI conversation/context/spec-chat suite: 41 passed across 6 files.
- Focused Hub trigger/queue/MCP run: 48 passed and 2 order-dependent failures; each failure passed
  alone. Recorded above as a test-isolation defect, not a product behavior failure.
- `openspec status --change 2026-08-02-agent-conversation-workspace` currently fails because this
  OpenSpec CLI rejects date-prefixed change names even though the repository convention explicitly
  requires them and `openspec list` / `validate` recognize them. This is a tooling incompatibility,
  not a spec-content failure.
