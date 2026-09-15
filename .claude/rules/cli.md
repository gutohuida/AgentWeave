---
paths:
  - "src/agentweave/**"
  - "tests/test_cli.py"
---

# CLI rules (loaded when a file under `src/agentweave/` is read)

The CLI is not a collaboration surface: five `cmd_*` functions survive (status, doctor, stop,
hub_start, reset). Read `openspec/explorations/2026-08-02-product-direction.md` before adding a
sixth. Layout: `.claude/reference/architecture.md`.

- The CLI's own code imports nothing outside the stdlib; its one runtime dependency is
  `agentweave-hub`. Do not add a second. `HttpTransport` uses stdlib `urllib.request` only.
- Agent names are validated by `AGENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")` — any match
  accepted. `VALID_MODES = ["hierarchical", "peer", "review"]`.
- ALL saves pass through `validator.py` sanitize functions.
- ALL task modifications use `with lock("name"):`. `is_locked()` is read-only — never delete files.
- Templates via `get_template("name")` — never hardcode in `cli.py`.

## Adding a CLI command

1. Add a `cmd_<name>()` function in `cli.py`.
2. Add a subparser in `create_parser()`.
3. Add a routing branch in `main()`.
4. Add tests in `tests/test_cli.py`.
