# Testbed

Scratch space for exercising AgentWeave **as a user would**, without polluting the repository.

This repo is where AgentWeave is *developed*, not a project that *uses* it. Running
`agentweave init`, starting a Hub, connecting agents, or generating spec documents at the repo root
creates artifacts — `.agentweave/`, `agentweave.yml`, `spec/`, `.claude/skills/aw-*` — that look
like project state but are really test output. They were removed on 2026-08-02 for exactly that
reason. Do that work in here instead.

## Use it

```bash
mkdir -p testbed/scratch && cd testbed/scratch

# Now behave like a user of the tool
agentweave init
agentweave agent configure ...
agentweave watch
```

Anything under `testbed/` except this README is ignored by git, so you can create as many
throwaway projects as you like and delete them freely.

## Rules

- **Never run `agentweave init` (or any command that writes project state) at the repository root.**
  If you find `.agentweave/`, `agentweave.yml`, or `spec/` there, something was run in the wrong
  directory — delete them.
- **Automated tests do not belong here.** `pytest` suites live in `tests/` (CLI) and `hub/tests/`
  (Hub), and they use `tmp_path` fixtures rather than a checked-in directory. This folder is for
  manual and exploratory runs only.
- **Nothing here is a fixture.** No test, script, or CI job may depend on a path under `testbed/`.
  Treat it as disposable.
