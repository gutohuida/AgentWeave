# AGENTS.md — guide for any AI coding agent working on AgentWeave

**The full guide is [`CLAUDE.md`](CLAUDE.md). Read it. It is not Claude-specific despite the name;
it is simply the file this repository's own tooling loads automatically.**

This file exists because Codex, Kimi, OpenCode and others look for `AGENTS.md` rather than
`CLAUDE.md`. It deliberately does **not** restate the guide. Two 500-line documents describing the
same repository is how both of them ended up wrong: this one spent weeks documenting a watchdog
daemon, a Git transport and a role system that had all been deleted.

Below is only what you need before you have read `CLAUDE.md`.

## The one thing that catches everybody

**This repository is AgentWeave's source code, not a project that runs AgentWeave.**

Do not run the product against this checkout. Do not create `.agentweave/`, `agentweave.yml`, or
`spec/` at the repository root — they read as project state and were deleted once already for that
reason. If you need to exercise the product, do it in `testbed/`.

Do not invoke `aw-*` skills here. They are a feature AgentWeave ships to its users. This repository
plans its own work in `openspec/`.

## Where planning lives

- `openspec/specs/<capability>/spec.md` — current behaviour of shipped capabilities
- `openspec/changes/<date>-<name>/` — one in-flight change: `proposal.md`, `design.md`, `tasks.md`,
  and `specs/<capability>/spec.md` deltas
- `openspec/changes/archive/` — completed changes
- `openspec/explorations/2026-08-02-product-direction.md` — **why the architecture is what it is.**
  Read this before proposing anything structural; it exists specifically so the scope that was
  removed is not quietly restored.

Never mark a task complete because a plan exists. Only working, verified implementation closes one.

## Deleted, and not to be recreated

`watchdog.py`, `messaging.py`, `runner.py`, `transport/local.py`, `transport/git.py`, the role
subsystem, and the collaboration CLI. The Hub owns execution; there is no second runtime, no
filesystem or git collaboration substrate, and the CLI does only what cannot be done from inside the
app.

## Verifying your work

```bash
pytest tests/ -q                       # CLI
pytest hub/tests/ -q                   # Hub
cd hub/ui && npx vitest run            # dashboard
cd hub/ui && npx tsc --noEmit
npx openspec validate --specs --strict
```

`hub/hub/static/ui` is a committed build artefact. If you changed the dashboard, rebuild it and copy
`hub/ui/dist` over that directory, then confirm with `diff -rq`.

## Skills

Hand-written skills live in `.claude/skills/`. Claude Code and OpenCode read them there. Kimi reads
`.agents/skills/`, and Codex reads `~/.codex/skills/` only — it has no project-level discovery at
all, so no arrangement of files inside this repository can reach it. Run `make sync-skills` to
mirror them out.
