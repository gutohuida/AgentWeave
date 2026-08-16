# Tasks — One Hub, wherever it's launched from — and a window of its own

No database migration in this change — `config.py`'s default and `docker-compose.yml`'s project
name are both process/config-level, not schema.

## 1. Global instance state (D1, D2)

- [ ] 1.1 `hub/hub/config.py`'s `database_url` default becomes
      `f"sqlite+aiosqlite:///{(Path.home() / '.agentweave' / 'hub' / 'data' / 'agentweave.db').as_posix()}"`,
      computed inline (`design.md` D1 — no cross-package import). Keep it a `pydantic-settings`
      field default so `DATABASE_URL` (native mode, Docker's `environment:` block) still overrides
      it exactly as today.
- [ ] 1.2 Add a top-level `name: agentweave` to `hub/docker-compose.yml` (`design.md` D2).
- [ ] 1.3 Do not touch `_hub_native_start` (`src/agentweave/cli.py:664`) — it already computes the
      same absolute path independently and sets `DATABASE_URL` before `hub.main` is imported.
      Confirm by reading, not by assumption, that this task does not need to change that function.

## 2. Backend tests — agent-verifiable

- [ ] 2.1 A drift test asserting `hub.config.Settings().database_url` (with `DATABASE_URL` unset in
      the test's environment) and `HUB_DIR / "data" / "agentweave.db"` from
      `src/agentweave/cli.py` resolve to the identical path on the same interpreter — the test
      `design.md` D1 names to guard the two independently-computed constants against drifting apart.
      Import both modules directly in the test (no subprocess needed for this comparison); if
      `agentweave-hub`'s test environment cannot import `agentweave` (separate distributions —
      confirm which is true in this repo's actual test setup before writing this), express the same
      assertion as two hardcoded-path-shape checks compared against each other instead, and say so
      in the test's own docstring rather than silently changing what it proves.
- [ ] 2.2 A test that constructs `Settings` with `DATABASE_URL` unset in the environment and asserts
      the resulting `database_url` is an **absolute** path under `Path.home() / ".agentweave"`, not
      the old `data/agentweave.db` relative default — this is the regression test for the bug itself
      (direct `uvicorn hub.main:app`, no CLI involved).
      Mutation-check it: temporarily revert `config.py`'s default to the old relative string, confirm
      this test fails, then restore.
- [ ] 2.3 A test (plain YAML parse, not a live `docker compose` invocation, unless the CI/test
      environment already has Compose available — check first) asserting
      `hub/docker-compose.yml` declares a top-level `name:` key equal to `"agentweave"`.
      Mutation-check by temporarily removing the key and confirming the test fails.
- [ ] 2.4 Confirm (rerun, not just re-read) that `hub/tests/test_migrations.py` and
      `hub/tests/test_project_persistence.py` still pass unmodified — no migration in this change,
      so their head assertions do not move. Record the actual pass/fail counts, not an assumption.

## 3. Desktop window (D3, D5)

- [ ] 3.1 Add `pywebview` to `pyproject.toml` as `[project.optional-dependencies] app =
      ["pywebview>=5.0"]` — additive to the existing optional-dependency groups, `dependencies = []`
      unchanged.
- [ ] 3.2 A new `_open_app_window_native(url: str) -> bool` (or similarly named) in `cli.py`: tries
      `import webview`, and if present, calls `webview.create_window("AgentWeave", url)` then
      `webview.start()`. Returns `True` if it ran the pywebview path, `False` if `pywebview` is not
      importable (caller falls back to `_open_app_window`). Any exception raised while creating or
      starting the window (e.g. no WebView2/WebKitGTK/Qt backend present) is caught, a message is
      printed naming what's missing, and the function returns `False` so the caller falls back —
      per `design.md` D5, app mode stays best-effort.
- [ ] 3.3 Wire **four of the five** real `_open_app_window` call sites through 3.2 first, falling back
      to `_open_app_window` only on `False`: `_hub_native_start`'s two (`cli.py:692`, `:789`), and
      `cmd_hub_start`'s Docker branch's two — `cli.py:850` (the "already running" early return) and
      `cli.py:942` (after `docker compose up` succeeds), reachable because `main()` forces `app=True`
      for bare invocation regardless of `--docker`/`--local`. Missing these two would leave a
      Docker-launched instance silently on the old browser fallback even with `pywebview` installed,
      contradicting the ADDED requirement's "SHALL open... when a native webview backend is installed"
      (round-1 review, Objection 2). **The fifth call site, `_wait_and_open_app` (`cli.py:661`, used
      only by the `--no-detach` foreground path), is explicitly excluded from this wiring — it keeps
      calling `_open_app_window` unconditionally, whether or not `pywebview` is installed.**
      `pywebview` requires `webview.start()` to run on the main thread, and `--no-detach`'s main thread
      is already committed to blocking in `uvicorn.run()` until Ctrl+C; `design.md` D3's named
      exception explains why this is a deliberate scope boundary, not an oversight, and why inverting
      the thread model to accommodate it was rejected. Do not change
      `_find_app_mode_browser`/`_open_app_window` themselves — they stay the exact fallback path
      (`design.md` D3's "byte-identical when pywebview is absent"), which is also what `--no-detach`
      keeps using permanently now.
- [ ] 3.4 Confirm by reading (this is a process-model change, not something a unit test proves) that
      the detached-Hub-plus-blocking-window composition described in `design.md` D3 is what actually
      happens: with `pywebview` installed, running bare `agentweave` (default detach; app mode is
      always on) now blocks in `webview.start()` after the Hub is confirmed healthy, and only that
      invocation's exit is delayed — the detached uvicorn process is unaffected and keeps running
      after the window closes, exactly as today's browser-window close does not stop the Hub. Also
      confirm `agentweave --no-detach` (with or without `pywebview` installed) is **unchanged** by this
      task — it still calls `_wait_and_open_app` on a worker thread, still opens the existing
      non-blocking browser fallback, and Ctrl+C on the foreground `uvicorn.run()` remains the only stop
      mechanism, exactly as today.

## 4. CLI tests — agent-verifiable

**`tests/test_cli.py` does not exist yet.** Confirmed by listing `tests/` and grepping every file in
it for `agentweave.cli`, `_open_app_window`, `_hub_native_start`, and `cmd_hub_start` — zero hits
(round-1 review, non-blocking finding). The CLI has no test coverage of any kind today. Tasks 4.1-4.4
create this file from scratch, including whatever fixtures/imports it needs — this is a new suite,
not an extension of an existing one.

- [ ] 4.1 In the new `tests/test_cli.py`: a test that with `pywebview` NOT installed (or
      monkeypatched to raise `ImportError` on `import webview`), app mode's behavior is byte-identical
      to today: same call into `_open_app_window`, same arguments, no new branch taken. This is the
      test that makes D3's "nothing silently degrades" claim checkable rather than asserted.
- [ ] 4.2 A test that with `webview` importable (mock the module — do not require a real
      `pywebview` install in the CLI test environment, which is a separate, zero-dependency
      distribution from the Hub's), `create_window` and `start` are called with the URL
      `_hub_resolve_launch_url` resolves, and `_open_app_window` (the fallback) is NOT called.
- [ ] 4.3 A test that a `webview.start()` exception (simulated via the mock) is caught, and the
      function falls back to calling `_open_app_window` — proving 3.2's "best-effort" contract
      rather than letting a missing backend crash the invocation.
- [ ] 4.4 The new `tests/test_cli.py` suite passes. Since no prior suite existed, there is no old
      assertion of the always-browser behavior to have broken — this task is "the new suite is green,"
      not "nothing regressed in an existing one." Note this plainly in the PR/commit rather than
      implying continuity with a suite that was never there (round-1 review, non-blocking finding).

## 5. Migration decision — no code, a documented non-action (D4)

- [ ] 5.1 State in the CLI's install docs (wherever bare `agentweave`/`--docker`/`--local` are already
      documented — `docs/` or `README.md`, whichever currently covers it) that anyone who has been
      running the Hub via direct `uvicorn hub.main:app` or `docker compose up` from varying
      directories may find their data at the pre-fix location after upgrading, and that copying the
      database file to the new global path is a manual, one-line step, not something the CLI does
      for them. No code task — `design.md` D4 explicitly decided against writing a migration tool.

## 6. Human-only verification

- [ ] 6.1 **Confirm the same Hub/database is reached from two different launch directories**, for
      each of the three launch paths in scope: bare `agentweave` (native — should already pass,
      unchanged by this proposal; run as a control), direct `uvicorn hub.main:app` (should now match
      native, where it did not before), and `docker compose up` from two different directories
      (should now produce the same named volume). This is the actual bug report; task 2's tests
      prove the mechanism, this proves the outcome.
- [ ] 6.2 **Try bare `agentweave` with `pywebview` installed** and judge whether a CLI command that
      now blocks until the window closes, where it used to return in seconds, is the experience
      wanted — `design.md` D3 names this a genuine UX judgment call, not something a test can validate
      as correct. Also try `agentweave --docker` (or `--local`) with `pywebview` installed, since
      task 3.3 wires the Docker branch through the same native-window path — confirm it opens a
      native window too, not the old browser fallback.
- [ ] 6.3 **Try bare `agentweave` with `pywebview` NOT installed** (a clean venv, or uninstall it) and
      confirm the fallback browser window still opens and nothing looks broken or half-migrated.
- [ ] 6.4 **Try app mode with no compatible webview backend present** (hardest to stage — e.g. a
      Windows install with WebView2 genuinely absent, or Linux with neither WebKitGTK nor Qt) and
      confirm the fallback message is legible rather than a raw traceback.
- [ ] 6.5 If Q4a's screenshot harness (`scripts/uishot.py`) is available, it screenshots a browser
      page, not a native OS window — pywebview's own window is out of its reach. Confirm this
      limitation before expecting a screenshot of the desktop window itself.

## 7. User test guide

**Setup.** AgentWeave installed via `pip install agentweave-ai[app]` (for the desktop-window steps)
or `pip install agentweave-ai` (for the global-state steps, no extra needed).

1. **Start the Hub from one directory, then a different one.**
   Run bare `agentweave` from directory A, note the port and any projects listed by
   `agentweave status`. Stop it (`agentweave stop`), then run bare `agentweave` again from an
   unrelated directory B.
   - *Expect:* the same Hub, the same projects (directory B is added as a new project, not a new
     Hub) — not a fresh, empty instance.
2. **Open the app.** Run bare `agentweave` (having installed the `[app]` extra first if you want the
   native window; otherwise this opens a browser window as before — app mode is always on, there is
   no flag to pass).
   - *Expect, with `pywebview` installed:* a single window titled "AgentWeave," no browser
     chrome (no address bar, no tabs), with its own entry in your OS taskbar/dock — not a browser
     tab. The terminal command does not return until you close that window.
   - *Expect, without it:* exactly what app mode did before this change — a chromeless browser
     window or a new tab, and the command returns right away.
3. **Close the window and check the Hub is still running.** After closing the app window from
   step 2, run `agentweave status`.
   - *Expect:* the Hub is still reported as running — closing the window does not stop it, the same
     way closing a browser tab never did.

**Where it would go wrong:** if step 1 shows a different project list or a fresh empty state after
switching directories, the global-state fix did not take. If step 2's window has browser chrome
(tabs, an address bar) despite `pywebview` being installed, the native-window path silently fell
back without saying so — that is a defect, not a taste call.
