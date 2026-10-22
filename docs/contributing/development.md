---
description: Setting up a development checkout, running exactly what CI runs, and working on the Hub and the app.
---

# Development

## Repository layout

```text
AgentWeave/
├── src/agentweave/      the CLI (agentweave-ai)
├── hub/hub/             the Hub: FastAPI, scheduler, execution, runner adapters, migrations
├── hub/hub/static/ui/   the app's committed production build
├── hub/ui/              the React app (Vite)
├── hub/tests/  tests/   Hub tests, CLI tests
├── spec/                AgentWeave's own specifications, managed through AgentWeave
├── docs/  mkdocs.yml    this site
├── scripts/             drive and maintenance scripts
├── testbed/             throwaway projects for exercising the product (ignored by git)
├── constraints-dev.txt  development pins, matching CI
└── Makefile
```

## Install

Install the Hub first, so that pip resolves `agentweave-ai`'s dependency on it from your checkout
and does not fetch a release. Always install through `constraints-dev.txt`, which pins what CI
resolves:

```bash
pip install -c constraints-dev.txt -e ./hub
pip install -c constraints-dev.txt -e ".[dev,mcp]"
```

Exercise the product in `testbed/`, never at the repository root. Running `agentweave` at the root
would register the repository itself as a project.

## Run what CI runs

```bash
ruff check src/ hub/ tests/
ruff check scripts/ --select E9,F63,F7,F82,F401,F841
black --check src/ hub/hub/ hub/tests/ tests/
mypy src/
pytest tests/ -q                     # CLI
pytest hub/tests/ -q -n auto         # Hub
cd hub/ui && npm run lint && npm run test
```

`make lint`, `make format-check`, `make test-hub` and `make test-all` wrap most of these.

## The app

```bash
cd hub/ui
npm install
npm run dev        # http://localhost:5173, proxying /api to AW_DEV_HUB (default http://localhost:8000)
```

The Hub serves the committed build in `hub/hub/static/ui/`, not the source. After changing the app:

```bash
npm run build
make ui            # refreshes hub/hub/static/ui and its build stamp
```

Commit `hub/ui/src` and `hub/hub/static/ui` **together**. `make ui-check` fails if they disagree.

## A Hub of your own

Run a development Hub from source with its own database, on its own port, so you never touch a
real instance:

```bash
cd hub
DATABASE_URL="sqlite+aiosqlite:///$PWD/../testbed/dev.db" \
  python -m uvicorn hub.main:app --port 8010
```

A Hub started without `DATABASE_URL` refuses to start rather than guess which database to open.

## Code style

- Python 3.11+, line length 100, formatted by black, linted by ruff, typed (mypy on `src/`).
- The CLI's own code imports only the standard library. Its one runtime dependency is
  `agentweave-hub`.
- A test for code that consumes an API response uses the ordering that route actually returns.

## Where things go

- **A runner CLI**: an adapter in `hub/hub/runner_adapters/`, plus the CLI name in `RUNNER_CLIS`.
- **An agent tool**: `hub/hub/mcp_server.py` and its HTTP route in `hub/hub/api/v1/agent_actions.py`.
  The tool's description is generated once for both MCP and `aw-tool`.
- **A database change**: an Alembic migration in `hub/hub/migrations/`.
- **An app surface**: `hub/ui/src/components/`.

The repository's `.claude/rules/` carry the detailed checklists for each of these.

## Pull request checklist

- [ ] Everything under *Run what CI runs* passes
- [ ] A test fails without the change and passes with it
- [ ] The app's build is refreshed and committed, if the app changed
- [ ] Documentation updated if behaviour changed
