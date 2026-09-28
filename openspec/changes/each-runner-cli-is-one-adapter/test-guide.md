# Test guide — each runner CLI is one adapter

This change is a refactor. Nothing should look or behave differently. Every check below asks one question: is it
still the same?

## Agent-verifiable

1. **The goldens are older than the code.** The files in `hub/tests/fixtures/runner_adapters/` (`argv_golden.json`,
   `stream_events_golden.json`, `one_shot_golden.json`, `rpc_kwargs_golden.json`, `drive_before.json`) were committed
   before any file under `hub/hub/` changed. `rpc_kwargs_golden.json` was captured by driving the executor, and its
   test drives `_execute_rpc_run`, not only `CodexAppServerTransport.run_turn` (review 1). `git log --format=%h -- hub/tests/fixtures/runner_adapters/` shows their
   commit before the first commit touching `hub/hub/runner_adapters/`, and no later commit edits them.
2. **Tasks 1.2–1.6 failed before group 2 and pass after it.** Record both results in the commit messages.
3. **The whole Hub suite passes, twice.** Run `py -3.11 -m pytest hub/tests/ -q` as usual, then again with `claude`
   removed from `PATH` (CI has no `claude`).
4. **No runner-name branch is left outside the adapters.** `hub/tests/test_no_runner_literals.py` passes. Also run
   `grep -rnE '(==|!=) "(claude|codex)"|in \("claude"' hub/hub --include=*.py | grep -v runner_adapters/`: it finds
   nothing. On `ef55e6f` it finds 16 lines (design D5 lists them).
5. **The dead registries are gone.** `grep -rn "SUPPORTED_RUNNERS\|_CATALOG_PROVIDER_BY_RUNNER\|catalog_provider_for_runner\|MCP_INJECTABLE_RUNNERS\|resolve_access_path\|SUPPORTED_CLIS\|uses_app_server" hub/hub`
   finds nothing. `LEGACY_RUNNER_CLI` still has its `copilot` row, which slice 2 deletes.
6. **The drive responses match.** In task 5.4, `GET …/runners/launchability-by-provider`, `GET …/agents/launchability`
   and `GET …/agents` (`runner`, `display_model`, posture fields) equal `drive_before.json`, key order included, once ids
   and timestamps are removed.
7. **The Haiku drive's turn (5.2) looks like any Claude turn before this change.** Check:
   - `run_started` carries `runner: "claude"`
   - `mcp_adapter_online_at` is set
   - the `send_message` reached the operator
   - the write inside the worktree was allowed with no card
   - the outside-write record is `[]`
8. **Row 2 of D4 still holds (5.3).** With `hub_client: "cli"`, the turn notice is the HTTP form, no tool server is
   injected, and the default posture is `acceptEdits`.
9. **The binary-check patch seam moved cleanly.** `grep -rn "hub.launchability.shutil" hub/tests` finds nothing, and
   `ruff check hub/` passes with no `noqa` on a `shutil` import (review 4).
10. **No migration was added.** `ls hub/hub/migrations/versions/` shows the same head as before, and
   `test_migrations.py`'s head assertion is unchanged.

## Human-only

1. **Open the app** (the trial Hub `:8010`, or the Vite dev server pointed at it). Check the agent settings, the
   runner picker, the Runners page and the composer's Permissions pill. Do they read exactly as they did yesterday for
   a Claude agent and for a Codex agent? Nothing on screen should have moved.
2. **Talk to a Claude agent for a turn or two, the way you normally do.** Include one tool call that needs approval
   under "Ask me". Did anything feel different: the card, the timing, the timeline's tool rows?
3. **Read design D3 as the contract slices 2–5 will build on.** Is anything there shaped in a way you would not want
   Copilot to inherit? The two to look at are the choice to key everything on the transport rather than the runner
   (D1), and D16's list of members that are deliberately not added yet.
4. **One decision is yours if you want it:** D5 keeps the legacy `copilot` launchability row until slice 2 replaces it,
   rather than deleting it now. Deleting it now would make a session-configured `runner: copilot` agent report a
   binary named after itself. Say so if you would rather it went now anyway.
