## Context

The three blocker fixes have shipped:

- `fix-context-tracking` makes the Hub UI show a trustworthy context percentage for every active agent session.
- `add-auto-reset-mode` gives the watchdog a safe path to force-checkpoint and reset a busy agent at high context, including a force-kill path for uncooperative agents.
- `add-durable-trigger-retry` guarantees that no trigger message is silently lost to spawn failures, quick-failure subprocesses, or watchdog downtime.

With those in place the dev loop has the substrate it needs. This change captures the architectural shape, the ground rules, and the operator workflow for the loop itself. The agents handle the implementation details once the user approves this design.

## Goals / Non-Goals

**Goals:**

- Stand up a Hub on port 8001 with its own database.
- Give each of opencode, kimi, codex a git worktree and a long-lived CLI session pointed at the dev Hub.
- Make the agents research, propose, implement, review, and document changes on feature branches.
- Let the user pause the loop at night trivially and resume the next day.
- Establish the ground rules agents follow: never touch `main`, strict peer review, two-of-three consensus with third-agent tie-break, idle→research flow.

**Non-Goals:**

- Push to `main` automatically. Only the human merges.
- Run the loop without the user. The user is in the loop for topic selection and merges.
- Replace the existing interactive Hub on port 8000. The dev Hub on 8001 is additive.
- Replace the existing scheduler, watchdog, or transport layer. Changes are additive.

## Decisions

### Decision: Per-agent git worktree with a long-lived session

The three agents work in three separate worktrees on three long-lived branches (`agent/opencode`, `agent/kimi`, `agent/codex`). When the lead agent on a topic creates the implementation branch (`feature/<topic>`), the helpers rebase or cherry-pick as needed. The session ID for each agent (`agentweave-<agent>`) is stable across job fires.

Rationale: per-agent worktrees prevent session file races and let three agents work concurrently on the same repo. Stable session IDs let the watchdog's resume-mode jobs preserve context across cron ticks.

### Decision: Strict peer review on every feature branch

Every `feature/<topic>` branch requires a peer-review task in the Hub before the lead marks it ready for the human to merge. The reviewer is deterministically assigned to an agent that did not author the branch (round-robin among the other two).

Rationale: the user wants strict review so a single agent cannot ship code that nobody else has read.

### Decision: Two-of-three consensus with third-agent tie-break

When agents disagree on a research direction, a code-review resolution, or an architecture choice, two agreeing agents decide. If the three agents form three different positions, the third agent casts the deciding vote. If the tie-breaker disagrees with both sides, the dispute is escalated to the user via a Hub question.

Rationale: in autonomous mode the loop cannot block on every disagreement. A deterministic rule keeps progress flowing while preserving a clean escalation path.

### Decision: Idle behaviour is research, then a question to the user

When an agent wakes with no assigned task, no claimable pending task, and no inbox question to answer, it enters research mode. Research reads `openspec/changes/*`, `openspec/specs/*`, `ROADMAP.md`, recent `git log`, recent task history, and TODO/FIXME markers. The agent synthesises two to four candidate topics and posts them to the user as a blocking multiple-choice Hub question.

Rationale: the human is rarely at the keyboard in autonomous mode, but the human still chooses direction. Agents mine the codebase and the spec folder for candidates so the user only has to choose, not ideate.

### Decision: Night-mode pause is just job disable

Pausing the loop is a single command (`aw jobs disable --all`) on the dev Hub. The watchdog can stay running (it polls and finds nothing) or be stopped. Resuming is `aw jobs enable <name>` for each job.

Rationale: keeps the operational model trivial. The user wants to leave at the end of the day and pick up the next morning without state-management ceremony.

### Decision: autonomous_dev role is methodology-focused

The existing per-domain role guides (`backend_dev`, `code_reviewer`, etc.) remain available as methodology references. The default role assigned to each agent in the dev Hub is `autonomous_dev`, whose guide describes the wakeup workflow, the research-mode flow, the ground rules, the commit conventions, and the context-pressure response. Domain-specific roles are loaded via skills on demand.

Rationale: roles currently bundle identity, methodology, defaults, and capability. The first three still matter in autonomous mode even when the job prompt sets the capability. A single methodology-focused role keeps per-agent configuration simple.

### Decision: Kickoff message is the canonical per-wake brief

Every job that wakes an agent in the dev loop sends a kickoff message whose body is generated from a shared template. The template encodes the wakeup workflow, the collaboration rules, the ground rules, and the end-of-session checklist.

Rationale: the agents cannot be briefed interactively every time. The kickoff message is the per-session stand-in for the human operator.

## Risks / Trade-offs

- The dev loop depends on the three blocker fixes being shipped. Without them the loop would silently lose messages, double-spawn agents, and never reset context. Mitigation: this change ships only after the three blockers.
- Worktrees increase disk usage and require disciplined branch management. Mitigation: each agent's session is bound to one worktree; the feature branch is the only place commits for a topic accumulate.
- Strict peer review adds latency. Every topic needs two agents' worth of work, not one. Mitigation: peer review is what catches mistakes before the user is involved.
- Two-of-three consensus can produce stale compromises when two agents share a blind spot. Mitigation: the third agent is the tie-breaker by construction, and the user has the final say.
- Idle research could propose topics the user does not care about. Mitigation: the user picks one; rejected topics can be left in `openspec/changes/archive/` with a one-line reason so the next research pass avoids them.

## Migration Plan

1. Create the three worktrees on the three long-lived agent branches and configure each agent's `agentweave.yml` to point at the dev Hub on port 8001.
2. Stand up the dev Hub (Docker container on port 8001 with its own database volume).
3. Register the three agents with the dev Hub. Each agent has `pilot=false`, `yolo=true`, and `contact_mode=poll`.
4. Schedule the kickoff job for each agent with `session_mode=resume`.
5. Observe one full day before leaving the loop unattended.
6. Rollback at any step is "stop the watchdog and disable the jobs". The dev Hub is additive to the interactive Hub.

## Open Questions

- Should the kickoff message be parameterised per agent or shared?
- Should the third-agent tie-break require that the third agent be the lead on the disputed topic, or be explicitly excluded from the lead role?
- Should the loop auto-pause when the Hub detects a sustained test failure rate?
- Should the user be able to inject a topic directly via a Hub message without going through the research→question flow?