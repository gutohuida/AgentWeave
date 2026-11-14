# Contributing to AgentWeave

Thanks for your interest. Bug reports, questions and pull requests are all welcome.

## Questions and ideas

Ask in [GitHub Discussions](https://github.com/gutohuida/AgentWeave/discussions). Answers there are
public and searchable, so the next person with the same question finds them.

## Reporting a bug

Open an [issue](https://github.com/gutohuida/AgentWeave/issues/new/choose) and include:

- your AgentWeave version (`agentweave --version`), Python version and operating system
- which agent CLIs you use (Claude Code, Codex, GitHub Copilot) and their versions
- what you did, what you expected, and what happened instead
- any error output, and the Hub log if the app misbehaved

Security problems are not reported in issues: see [SECURITY.md](SECURITY.md).

## Development setup

The full guide is [Development](https://gutohuida.github.io/AgentWeave/contributing/development/)
in the docs. The short version, from a fork:

```bash
git clone https://github.com/<you>/AgentWeave.git
cd AgentWeave
pip install -c constraints-dev.txt -e ./hub
pip install -c constraints-dev.txt -e ".[dev,mcp]"
cd hub/ui && npm install
```

Install the Hub first and always through `constraints-dev.txt`: it pins what CI resolves. Exercise
the product in `testbed/`, never at the repository root, which would register the repository
itself as a project.

## Before you open a pull request

Run what CI runs:

```bash
ruff check src/ hub/ tests/
black --check src/ hub/hub/ hub/tests/ tests/
mypy src/
pytest tests/ -q
pytest hub/tests/ -q -n auto
cd hub/ui && npm run lint && npm run test
```

Then:

- add a test that fails without your change
- update the docs if behaviour changed, and `CHANGELOG.md` under `[Unreleased]`
- if you touched `hub/ui/src`, rebuild the committed bundle (`make ui`) and commit both
- keep the pull request to one change, and say in its description what it fixes and how you
  checked it

## How this repository is built

AgentWeave is developed with AgentWeave. Its specifications live in `spec/`, written and approved
through the app, and many commits come from agents working in their own worktrees. Larger changes
start as a specification there; an issue or discussion first is the easiest way in.

## License

By contributing you agree that your contribution is licensed under the
[Apache License 2.0](LICENSE), as section 5 of that license states. There is no separate CLA.

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
