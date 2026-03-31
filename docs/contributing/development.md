# Development Guide

This guide covers how to set up your development environment and contribute to AgentWeave.

## Repository Structure

```
AgentWeave/
├── src/agentweave/     CLI package
├── hub/                Hub server (FastAPI + React)
├── docs/               Documentation
├── tests/              CLI tests
└── Makefile            Convenience commands
```

## CLI Development

### Install

```bash
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest tests/ -v
pytest tests/ -v --cov=agentweave --cov-report=term-missing
```

### Lint and Format

```bash
ruff check src/
black src/
mypy src/
```

Or use the Makefile:

```bash
make lint
make format
```

## Hub Development

### Install

```bash
pip install -e "hub/[dev]"
```

### Run Tests

```bash
cd hub
pytest tests/ -v
```

### UI Hot-Reload

```bash
cd hub/ui
npm install
npm run dev
```

The dashboard will be at **http://localhost:5173** and proxies `/api` to the Hub at localhost:8000.

## Code Style

- **Line length**: 100 characters
- **Formatter**: black
- **Linter**: ruff
- **Type hints**: required (enforced by mypy)

## Naming Conventions

- Modules: `snake_case.py`
- Classes: `PascalCase`
- Functions/Variables: `snake_case`
- Constants: `UPPER_CASE`

## Adding a New Feature

See [Adding New Agents](../guides/adding-new-agents.md) for a concrete example of extending AgentWeave.

## Pull Request Checklist

- [ ] Tests pass (`make test-all`)
- [ ] Lint passes (`make lint`)
- [ ] Type check passes (`mypy src/`)
- [ ] Documentation updated if needed
