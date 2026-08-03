# Implementation plan

## Working protocol

1. Re-read proposal, design, and delta spec before every phase.
2. Tests precede implementation within each phase.
3. Commit and hand off every verified phase.
4. Never mark work complete from a plan alone.

## 0. Run-scoped authentication

- [x] 0.1 Add migration/model/auth tests for hashed per-run tokens, active-run resolution, project
      key refusal on agent routes, run-token refusal on operator routes, and terminal revocation.
- [x] 0.2 Mint/inject run credentials without exposing them in output, events, args, or responses.
- [x] 0.3 Implement the authenticated `AgentActor` dependency and empty agent-action namespace.
- [x] 0.4 Verify authentication scenarios; hand off and commit.

## 1. Messaging, tasks, and questions

- [x] 1.1 Add actor-derived API tests whose payload signatures contain no identity/run/project.
- [x] 1.2 Extract actor-aware services and implement message, task, and question agent routes.
- [x] 1.3 Persist create/update run attribution and enforce same-agent question-answer reads.
- [x] 1.4 Verify allowed intent and prohibited coordination/configuration reads; hand off and commit.

## 2. Governed agent and job actions

- [x] 2.1 Add tests for request-agent and job operations through the run credential.
- [x] 2.2 Route both through existing template/agent-budget and job-allowance governance services.
- [x] 2.3 Persist request/job attribution and prove headers/payloads cannot override the actor.
- [x] 2.4 Verify governance scenarios; hand off and commit.

## 3. MCP and command parity

- [x] 3.1 Add parity tests for every allowed capability and representative validation, denied,
      conflict, and not-found failures.
- [x] 3.2 Make the canonical MCP server a thin run-token adapter; stop swallowing typed failures.
- [x] 3.3 Move bound CLI/HttpTransport commands to the same agent-action API.
- [x] 3.4 Remove project API credentials and caller identity headers from spawned-agent environments.
- [x] 3.5 Verify HTTP/MCP/command parity and absence of duplicate business rules; hand off and commit.

## 4. Integration and closeout

- [x] 4.1 Run full CLI, Hub, and frontend regressions plus focused security checks.
- [x] 4.2 Live-verify one real spawned run using the injected plane with no project credential.
- [x] 4.3 Sync authoritative specs, archive the successor, annotate the umbrella/tool-surface
      reconciliation, write final handoff, and commit.
