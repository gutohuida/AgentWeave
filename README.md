<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/gutohuida/AgentWeave/master/docs/assets/agentweave-loop-on-dark.svg">
    <img src="https://raw.githubusercontent.com/gutohuida/AgentWeave/master/docs/assets/agentweave-loop.svg" alt="The AgentWeave loop" width="84">
  </picture>
</p>

<h1 align="center">AgentWeave</h1>

<p align="center"><strong>Run your AI factory in the open.</strong></p>

<p align="center">
  <a href="https://pypi.org/project/agentweave-ai/"><img src="https://badge.fury.io/py/agentweave-ai.svg" alt="PyPI version"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-yellow.svg" alt="MIT License"></a>
  <a href="https://gutohuida.github.io/AgentWeave/"><img src="https://img.shields.io/badge/docs-gutohuida.github.io-1d6b6e" alt="Documentation"></a>
</p>

**Nothing appears out of thin air.** AgentWeave started as a way to get agents from different
companies working together, each doing what it does best. Then the problem showed: work appeared out
of thin air, and no one could say who made it, or why. So AgentWeave grew into the place where you
run your AI factory in the open: every artifact cared for, every step visible, every decision
traceable.

AgentWeave is a **local app** where AI coding agents (Claude Code, Codex and GitHub Copilot) work
on your projects together, **against specifications you approve**. Each task runs in its own git
worktree, a different agent reviews it, and approving it merges it. Every requirement, task, run,
piece of evidence and merge is recorded and connected.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/gutohuida/AgentWeave/master/docs/assets/screenshots/task-story-dark.webp">
    <img src="https://raw.githubusercontent.com/gutohuida/AgentWeave/master/docs/assets/screenshots/task-story-light.webp" alt="A task's story in AgentWeave: created by the planner, built by the builder, evidence accepted by the reviewer, merged into main" width="860">
  </picture>
</p>

## Quick start

```bash
pip install agentweave-ai
cd ~/code/my-project
agentweave
```

That is the whole install. `agentweave-ai` brings the Hub (the local server and the app it serves)
with it. The first launch creates `~/.agentweave/hub/`, starts the app on `http://localhost:8000`,
registers the directory you ran it from as a project, and opens it. You need Python 3.11+ and at
least one agent CLI signed in: [Claude Code](https://docs.anthropic.com/en/docs/claude-code),
[Codex](https://github.com/openai/codex) or [GitHub Copilot CLI](https://github.com/github/copilot-cli).

Then follow [Your first project](https://gutohuida.github.io/AgentWeave/getting-started/quickstart/):
three agents, one specification, one merged change.

## How it works

1. **You ask for a change.** An agent drafts a specification: requirements with stable ids
   (`FR-1`, `FR-2`, …), scenarios, and the tasks to deliver them.
2. **You approve it.** The Hub lists any gaps first. Approving creates the tasks, with their
   dependencies.
3. **Agents build.** Each task gets its own worktree and branch. The agent implements it, runs the
   tests, commits, and records **evidence** against the requirement: the command, its output, and
   the commit.
4. **Someone else reviews.** An agent can never approve its own work. The reviewer runs the checks,
   decides the evidence, and approves or sends the task back.
5. **Approval merges.** The evidenced commit is merged into your main branch, locally. Nothing is
   pushed.

Every step is attributed, so for any line in your repository you can open the task's story, the
requirement's history, the run's transcript and trace, and the reviewer's reasoning.

## What's inside

- **Specifications you approve**: drafted with an agent in conversation, with phases, rigor, coverage, drift and folding into current behaviour.
- **Isolated, reviewed work**: per-task worktrees, dependencies, evidence, quality checks, and approval as a merge.
- **Agents with a charter**: Claude Code, Codex and Copilot agents, each with a runner, a model and a charter, and permission postures that decide what an agent may do before it asks you.
- **You in the loop**: agents ask you questions and wait for the answer. Permission requests come to you as cards.
- **Jobs, loops and flows**: scheduled work with a purpose and a stop condition. Flows build an approved specification task by task, each reviewed by a different agent.
- **Knowledge vault**: transcripts, rules, decisions and documents your agents read, with facts that cite their sources.
- **Traceability**: task stories, requirement stories, per-turn traces (exportable over OTLP), and a spend ledger.

## The CLI

The CLI manages only the local instance. Everything else happens in the app.

```bash
agentweave                 # start or open the app, and register this directory
agentweave doctor          # check installation and readiness (starts nothing)
agentweave status          # is it running, where, which projects
agentweave stop            # stop it
agentweave reset           # delete local Hub state (asks first; never touches your projects)
agentweave vault add PATH  # add files to a project's knowledge vault
```

`aw` is an alias. `--port` and `--profile` run separate instances side by side. See the
[CLI reference](https://gutohuida.github.io/AgentWeave/reference/cli-commands/).

## Security model

- **One local process** owns execution, state and identity. It binds to `127.0.0.1` by default.
- **Operators** use one instance key. Project identity is in the URL, never in the credential.
- **Each agent run** gets its own short-lived token. Identity comes from that token alone, never
  from a request body or header, so an agent cannot act as another or approve its own work.
- Agents reach the Hub through one governed tool surface, over MCP or the `aw-tool` command.
- Provider credentials stay with the agent CLIs. Secret values are never returned by diagnostics
  and are redacted from everything the Hub records.

## Development

```bash
git clone https://github.com/gutohuida/AgentWeave.git && cd AgentWeave
pip install -c constraints-dev.txt -e ./hub          # the Hub first
pip install -c constraints-dev.txt -e ".[dev,mcp]"
py -3.11 -m pytest tests/ -q && py -3.11 -m pytest hub/tests/ -q -n auto
cd hub/ui && npm install && npm run test && npm run build
```

Exercise the product in `testbed/`, not at the repository root. See the
[development guide](https://gutohuida.github.io/AgentWeave/contributing/development/).

```text
src/agentweave/   the CLI
hub/hub/          the Hub: API, scheduler, execution, runner adapters, migrations
hub/ui/           the React app (built into hub/hub/static/ui)
spec/             AgentWeave's own specifications, managed through AgentWeave
docs/             the documentation site
```

## Links

[Documentation](https://gutohuida.github.io/AgentWeave/) ·
[PyPI](https://pypi.org/project/agentweave-ai/) ·
[Changelog](CHANGELOG.md) ·
[Issues](https://github.com/gutohuida/AgentWeave/issues)

*Why the red thread? In Goethe's* Elective Affinities, *every rope of the Royal Navy is spun with a
red thread, so any piece of it can be traced back to where it was made. Madder is the classic red
dye. The loop is that thread drawing a W, and looping back on itself at the centre, where the human
stays in the loop.*
