## 1. Dev hub

- [ ] 1.1 Add a `docker-compose.dev.yml` (or equivalent) that starts the Hub
  on port 8001 with its own `hub-data-dev` volume and a separate SQLite file.
- [ ] 1.2 Document the env vars (`AW_PORT=8001`, `DATABASE_URL=...`) and any
  other knobs.
- [ ] 1.3 Verify the dev Hub starts cleanly and the healthcheck passes.

## 2. Per-agent worktrees

- [ ] 2.1 Create three worktrees (`AgentWeave.opencode`, `AgentWeave.kimi`,
  `AgentWeave.codex`) on long-lived branches `agent/opencode`, `agent/kimi`,
  `agent/codex`.
- [ ] 2.2 Configure each worktree's `.agentweave/transport.json` to point
  at the dev Hub on port 8001.
- [ ] 2.3 Verify each agent can register with the dev Hub.

## 3. Role and runner setup

- [ ] 3.1 Add an `autonomous_dev` role template whose guide describes the
  wakeup workflow, research flow, ground rules, commit conventions, and
  context-pressure response.
- [ ] 3.2 Assign `autonomous_dev` to each of opencode, kimi, codex in the
  dev Hub's session config.
- [ ] 3.3 Confirm each agent's `runner` is set correctly (`opencode`, `kimi`,
  `codex`).

## 4. Kickoff message template

- [ ] 4.1 Define a shared kickoff message template that encodes the
  wakeup workflow, collaboration rules, ground rules, and end-of-session
  checklist.
- [ ] 4.2 Wire the template into the kickoff job for each agent so that
  every wake delivers a fresh kickoff body to the long-lived session.

## 5. Jobs and schedule

- [ ] 5.1 Create the kickoff job per agent with `session_mode=resume`.
- [ ] 5.2 Once the kickoff jobs run cleanly, replace them with the
  steady-state jobs (research tick, work tick, peer review tick) on a
  staggered cron schedule.
- [ ] 5.3 Document the pause/resume commands (`aw jobs disable --all`,
  `aw jobs enable <name>`).

## 6. Coordination layer

- [ ] 6.1 Stand up Hub task templates for: feature implementation, peer
  review, research proposal, escalation question.
- [ ] 6.2 Define the reviewer-assignment rule (round-robin among agents
  who did not author).
- [ ] 6.3 Document the two-of-three consensus and third-agent tie-break
  protocol in the role guide.

## 7. Tests

- [ ] 7.1 Integration test: a single topic's full lifecycle — research →
  user-pick → feature branch → implementation → peer review → approval →
  branch ready for human merge.

## 8. Operator runbook

- [ ] 8.1 Write a short runbook under `docs/guides/`: stand up dev hub,
  create worktrees, schedule jobs, observe one day, leave unattended.
- [ ] 8.2 Document the red-flag interventions (task stuck >3 days,
  force-push detected, three-way disagreement unresolved, sustained test
  failure rate).

## 9. Documentation

- [ ] 9.1 Update `AGENTS.md` and `CLAUDE.md` with the dev-loop ground
  rules.
- [ ] 9.2 Update `ROADMAP.md` to record this change as the entry point
  for the autonomous dev loop.