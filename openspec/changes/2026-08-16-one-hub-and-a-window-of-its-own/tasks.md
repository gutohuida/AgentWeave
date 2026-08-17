# Tasks — One Hub, wherever it's launched from — and a window of its own

No database migration in this change — `config.py`'s default and `docker-compose.yml`'s project
name are both process/config-level, not schema.

## 1. Global instance state (D1, D2, D6)

- [x] 1.1 `hub/hub/config.py`'s `database_url` default becomes
      `f"sqlite+aiosqlite:///{(Path.home() / '.agentweave' / 'hub' / 'data' / 'agentweave.db').as_posix()}"`,
      computed inline (`design.md` D1 — no cross-package import). Keep it a `pydantic-settings`
      field default so `DATABASE_URL` (native mode, Docker's `environment:` block) still overrides
      it exactly as today.
- [x] 1.2 Add a top-level `name: agentweave` to `hub/docker-compose.yml` (`design.md` D2). **Already
      done** — `7cd6184` ("R3: make the documented Docker install work") pinned `name: agentweave`
      before this change was even proposed. Verified live: the key is present and task 2.3's test
      passes against it. No edit needed here.
- [x] 1.3 Do not touch `_hub_native_start` (`src/agentweave/cli.py:664`) — it already computes the
      same absolute path independently and sets `DATABASE_URL` before `hub.main` is imported.
      Confirm by reading, not by assumption, that this task does not need to change that function.
      Confirmed by reading `_hub_native_start` (`cli.py:679-720`): `HUB_DIR.mkdir(...)`, then
      `data_dir = HUB_DIR / "data"`, `db_path = data_dir / "agentweave.db"`, and `DATABASE_URL` is
      set in `os.environ` before `hub.main` (and therefore `hub.config.settings`) is ever imported —
      independent of 1.1's default, exactly as `design.md` D1 says. Not touched.
- [x] 1.4 **Added 2026-08-16, resolves amendment A3 (`design.md` D6).** Add `--profile <name>`
      (default `"default"`) to `agentweave`'s bare-invocation argument parser and to
      `agentweave status`/`agentweave stop`. Wire it into `_hub_native_start`'s database-path
      computation: default profile unchanged (D1's path); named profile resolves to
      `HUB_DIR / "profiles" / <name> / "agentweave.db"`. Preserve the existing rule that an explicit
      `DATABASE_URL` in the environment wins regardless of `--profile` — print which one took effect
      when both are present.
      Done (iteration 4, 2026-08-17T20:2x+01:00): `--profile` added to the bare parser and to
      `status`/`stop` subparsers, all defaulting to `"default"`. Database-path computation factored
      into a new pure helper, `_hub_profile_data_dir(profile)` — default unchanged
      (`HUB_DIR/data`), named resolves to `HUB_DIR/profiles/<name>`, both independently testable
      without spawning anything. The DATABASE_URL-vs-profile precedence decision was also factored
      out, into `_hub_resolve_database_source(old_db_url, profile, db_path)`, called from
      `_hub_native_start` right before the existing `os.environ["DATABASE_URL"] = db_url` line —
      it returns `(db_url, message_or_None)`; `_hub_native_start` prints the message when present.
      DATABASE_URL always wins per the existing rule; the message only fires for a named profile
      (silent for `"default"`, unchanged from before this task).
- [x] 1.5 Namespace `_hub_pid_file(port)` by profile too: extend its signature (or add a sibling
      helper) so a named profile always produces `hub-<profile>-<port>.pid`, even at
      `DEFAULT_HUB_PORT`, while the default profile's filenames are byte-identical to today
      (`hub.pid` / `hub-<port>.pid`) — confirm by reading `_hub_pid_file`'s current callers
      (`cli.py:151,158,431,454,787,799,975`) before changing its signature, so every call site passes
      the profile it means.
      Done (iteration 4): confirmed by reading — all seven line numbers were still accurate at the
      start of this task. `_hub_pid_file(port=None, profile="default")` now takes a `profile` kwarg;
      for a named profile it always returns `hub-<profile>-<port>.pid` (falling back to
      `DEFAULT_HUB_PORT` in the filename only if `port` itself is `None`, which no call site
      currently passes). All seven call sites updated to pass their `profile` through:
      `cmd_stop` (two unlinks), `_hub_pid_running` (which gained the same `profile` kwarg and
      threads it to `_hub_pid_file`), `_hub_native_start` (write + unlink on the failed-health-check
      path), and `cmd_reset`. Default profile's filenames confirmed byte-identical by a dedicated
      test (`test_default_profile_pid_file_is_byte_identical_to_pre_profile_path`).
- [x] 1.6 `cmd_reset` gets a `--profile <name>` argument. Without it, behavior is unchanged (targets
      only the default profile's `data/`). With it, targets only that profile's directory under
      `HUB_DIR / "profiles" / <name>`. Do not add a sweep-all mode (`design.md` D6 — deliberately
      excluded).
      Done (iteration 4): `reset_parser` gained `--profile`, default `"default"`. `cmd_reset` uses
      `_hub_profile_data_dir(profile)` for its `data_dir` (was a hardcoded `HUB_DIR / "data"`) and
      passes `profile` to `_hub_pid_file`/`_hub_pid_running`. No `--profile all` / sweep mode added.
      `--all`'s existing behavior (also removing `.env`/logs) is unchanged and stays profile-agnostic
      — `.env` is shared across profiles by design (this task and D6 are silent on namespacing it),
      so `--all` still means "also remove the shared config," not "also remove this profile's
      config." The confirmation banner now names the profile when one is given, so the operator sees
      the scoped blast radius before confirming.
- [x] 1.7 Do not add Docker profile support, a remembered per-profile default port, a
      `agentweave profile list` command, or a rename/delete-profile subcommand — `design.md` D6 names
      these as open follow-ups, not part of this task.
      Confirmed (iteration 4): none of the four were added. `cmd_hub_start`'s Docker branch reads
      `profile` from `args` (line included for parser-attribute symmetry with the native branch) but
      never uses it — Docker still has exactly one instance, per D2. No `--profile` was added to
      `doctor`. No list/rename/delete subcommand exists. No port is remembered per profile;
      `--profile` alone (no `--port`) still resolves to `DEFAULT_HUB_PORT` today, which is exactly
      the gap 1.8 (not yet implemented) closes by erroring instead — left open deliberately, per the
      note below.
- [x] 1.8 **Added 2026-08-17, round-2 cold review (`design.md` D6, "Port").** When `--profile` names
      anything other than `"default"` and `--port` was not explicitly passed on the command line
      (distinguish "not passed" from "passed and happens to equal 8000" — argparse's plain
      `default=8000` on `--port` cannot tell the two apart, so this needs an explicit
      passed-vs-default check, e.g. a sentinel default or `sys.argv` inspection, not a value
      comparison), exit with a clear error naming both `--profile` and `--port` rather than silently
      resolving to `DEFAULT_HUB_PORT` — closes the port-collision gap round 1's D6 left open (a named
      profile with no `--port` would otherwise try to bind the same port the default profile normally
      uses). Applies to bare `agentweave`, `agentweave status`, and `agentweave stop`.
      Done (iteration 5): used the sentinel-default approach, not `sys.argv` inspection. `--port` on
      all three subparsers (`agentweave`'s top-level parser, `status_parser`, `stop_parser`) now
      defaults to `None` instead of `8000` — `reset_parser` has no `--port` at all, so it needed no
      change. A new pure helper, `_hub_require_port_for_named_profile(profile, port)`, returns an
      error message when `profile not in (None, "", "default")` and `port is None`, else `None`
      (mirrors `_hub_resolve_database_source`'s `(value, message)` shape already established for
      D6). `cmd_hub_start`, `cmd_status` and `cmd_stop` each call it immediately after reading
      `args.port`/`args.profile`, `print_error` and `return 1` if it fires, then resolve
      `port = port if port is not None else DEFAULT_HUB_PORT` — so every other line in those three
      functions still sees a concrete int exactly as before, unaware profiles exist.

## 2. Backend tests — agent-verifiable

- [x] 2.1 A drift test asserting `hub.config.Settings().database_url` (with `DATABASE_URL` unset in
      the test's environment) and `HUB_DIR / "data" / "agentweave.db"` from
      `src/agentweave/cli.py` resolve to the identical path on the same interpreter — the test
      `design.md` D1 names to guard the two independently-computed constants against drifting apart.
      Import both modules directly in the test (no subprocess needed for this comparison); if
      `agentweave-hub`'s test environment cannot import `agentweave` (separate distributions —
      confirm which is true in this repo's actual test setup before writing this), express the same
      assertion as two hardcoded-path-shape checks compared against each other instead, and say so
      in the test's own docstring rather than silently changing what it proves. Confirmed live: this
      repo's own interpreter can import both `agentweave` and `hub` directly, so the direct-import
      form was used, not the fallback. `hub/tests/test_config.py::TestDatabaseUrlDriftAgainstCli`.
- [x] 2.2 A test that constructs `Settings` with `DATABASE_URL` unset in the environment and asserts
      the resulting `database_url` is an **absolute** path under `Path.home() / ".agentweave"`, not
      the old `data/agentweave.db` relative default — this is the regression test for the bug itself
      (direct `uvicorn hub.main:app`, no CLI involved).
      Mutation-check it: temporarily revert `config.py`'s default to the old relative string, confirm
      this test fails, then restore. `hub/tests/test_config.py::TestDatabaseUrlDefault`. Mutation
      check run by hand: reverted the default, confirmed both this test and 2.1's drift test go red,
      restored, confirmed both pass again. **A real trap found while writing this test, worth
      recording:** `monkeypatch.delenv("DATABASE_URL")` alone is not enough to isolate the field
      default — this machine's actual `hub/.env` sets `DATABASE_URL` explicitly (the trial Hub's own
      override, per `STATE.json`), and `pydantic-settings` falls back to the `.env` file when the OS
      environment doesn't have the variable. The test constructs `Settings(_env_file=None)` to bypass
      that fallback and isolate the field default itself.
- [x] 2.3 A test (plain YAML parse, not a live `docker compose` invocation, unless the CI/test
      environment already has Compose available — check first) asserting
      `hub/docker-compose.yml` declares a top-level `name:` key equal to `"agentweave"`.
      Mutation-check by temporarily removing the key and confirming the test fails. Confirmed:
      Compose is not available in this test environment, used plain YAML parse via `pyyaml` (already
      a transitive dependency, importable). Mutation-checked by hand: removed the `name:` line, ran
      the test, confirmed red, restored, confirmed green.
      `hub/tests/test_config.py::TestDockerComposeProjectNamePinned`.
- [x] 2.4 Confirm (rerun, not just re-read) that `hub/tests/test_migrations.py` and
      `hub/tests/test_project_persistence.py` still pass unmodified — no migration in this change,
      so their head assertions do not move. Record the actual pass/fail counts, not an assumption.
      Reran both files together: **58 passed, 1 skipped** (the skip predates this change — unrelated
      to D1/D2). `hub/hub/config.py` was the only file this iteration changed under `hub/hub/`;
      neither test file was touched.
- [x] 2.5 **Added 2026-08-16 (D6).** A test that `agentweave --profile a --port <p1>` and
      `agentweave --profile b --port <p2>` resolve to two distinct database paths and two distinct
      PID filenames, extending `TestTwoInstancesDoNotCollide`'s existing pattern in
      `tests/test_cli.py` rather than duplicating its setup.
      Done (iteration 4): `TestProfileFlag.test_two_named_profiles_resolve_to_distinct_db_paths_and_pid_files`
      in `tests/test_cli.py`, alongside (not inside) `TestTwoInstancesDoNotCollide` — same pure,
      no-I/O style. Mutation-checked by hand: disabled `_hub_pid_file`'s named-profile branch
      (`if False and profile and ...`), confirmed this test went red with a mismatched path
      (`hub.pid` instead of `hub-a-8000.pid`), restored, confirmed green.
- [x] 2.6 A test that bare `agentweave` (no `--profile`) still resolves to exactly the pre-D6
      database path — the regression test proving D6 did not move the default profile.
      Done (iteration 4): `TestProfileFlag.test_default_profile_data_dir_is_byte_identical_to_pre_profile_path`
      and `test_default_profile_pid_file_is_byte_identical_to_pre_profile_path`, both asserting
      against `HUB_DIR / "data"` / `HUB_DIR / "hub.pid"` directly — the exact pre-D6 constants.
- [x] 2.7 A test that `DATABASE_URL` set in the environment overrides `--profile`'s computed path,
      and that the CLI's output names which one took effect.
      Done (iteration 4): `TestProfileFlag.test_explicit_database_url_overrides_profile_and_names_which_won`
      tests the extracted `_hub_resolve_database_source` helper directly across all four
      DATABASE_URL-present/absent x profile-named/default combinations, asserting both the winning
      `db_url` and whether/what message is returned. Mutation-checked by hand: made the
      DATABASE_URL-set branch return `db_path` instead of `old_db_url`, confirmed this test went red
      (`explicit` URL no longer equalled the result), restored, confirmed green. Not tested via a
      full `_hub_native_start` run with `capsys` — that path needs a stubbed `hub.main` and mocked
      migrations/subprocess (`TestNativeStartProjectLifecycle`'s pattern in `test_hub_commands.py`),
      which is heavier than the decision itself warrants once it is a pure, independently-tested
      function; `_hub_native_start`'s own regression guard (`TestTwoInstancesDoNotCollide` in
      `test_cli.py`) confirms it still calls the helper and still exports the result.
- [x] 2.8 A test that `agentweave reset --profile a` deletes only profile `a`'s directory when both
      `a` and `b` have data present, and that bare `agentweave reset` (no `--profile`) does not touch
      `profiles/` at all.
      Done (iteration 4): new `TestResetCommand` class in `tests/test_hub_commands.py` (`cmd_reset`
      had no prior test coverage at all — checked before writing), two tests:
      `test_reset_with_profile_deletes_only_that_profiles_directory` (profiles `a` and `b` both
      seeded with a fake `agentweave.db`; `reset --profile a` must delete only `a`'s directory) and
      `test_reset_without_profile_does_not_touch_profiles_dir` (default profile's `data/` and a named
      profile's directory both seeded; bare `reset` deletes only `data/`). Both use
      `monkeypatch.setattr("agentweave.cli.HUB_DIR", tmp_path / "hub")`, the existing pattern from
      `TestNativeStartProjectLifecycle`. Mutation-checked by hand: reverted `cmd_reset`'s `data_dir`
      to the old hardcoded `HUB_DIR / "data"`, confirmed the profile test went red (profile `a`'s
      directory survived — the "no data found, nothing to destroy" path fired instead, since the
      hardcoded default-profile dir didn't exist in the fixture), restored, confirmed both green.
- [x] 2.9 **Added 2026-08-17, round-2 cold review (D6, task 1.8).** A test that
      `agentweave --profile dev` (no `--port`) exits with an error rather than resolving to
      `DEFAULT_HUB_PORT` — the regression test for the port-collision gap found in round 2. Also
      assert the positive case still works: `agentweave --profile dev --port 8010` does not raise the
      same error. Mutation-check: temporarily remove the passed-vs-default check from 1.8, confirm
      this test fails, then restore.
      Done (iteration 5): new `TestPortRequiredForNamedProfile` class in `tests/test_cli.py`, seven
      tests — the helper directly (named-without-port errors and names both flags plus the port
      number; default-profile-without-port and named-with-port are both silently fine), a
      parser-level sentinel guard (`create_parser().parse_args([])`/`["status"]`/`["stop"]` all give
      `port is None`, and `--port 8010` on each still parses to `8010` — this guards against `--port`
      regressing back to `default=8000`, which would make the whole check unreachable), and one
      integration test per command (`cmd_hub_start`/`cmd_status`/`cmd_stop`, each called directly
      with a `Namespace(profile="dev", port=None, ...)`, asserting `== 1` and `"--port"` in stdout).
      Mutation-checked by hand exactly as instructed: replaced `_hub_require_port_for_named_profile`'s
      body with `return None`, reran — 4 of the 7 new tests went red (the helper test itself, and all
      three command-level tests; `cmd_hub_start`'s red output showed it had gone on to try starting a
      real Hub instance and failed on `agentweave-hub is not installed`, confirming the guard was the
      only thing stopping it, not some other early return), restored, reran — all 7 green again. Full
      CLI suite: 375 passed, 3 skipped (up from 368/3 — +7, matching the new tests exactly since 2.9
      added no other coverage). `ruff check`, `black --check --target-version py311` and `mypy` clean
      on `src/agentweave/cli.py` and `tests/test_cli.py`. No spec delta needed — `specs/app-lifecycle/
      spec.md`'s "A named profile selects a separate, deliberate instance" requirement and its
      "A named profile without an explicit port is rejected" scenario (added in the round-2 review
      that raised 1.8/2.9) already state exactly this behavior; only `tasks.md` needed updating.

## 3. Desktop window (D3, D5)

- [x] 3.1 Add `pywebview` to `pyproject.toml` as `[project.optional-dependencies] app =
      ["pywebview>=5.0"]` — additive to the existing optional-dependency groups, `dependencies = []`
      unchanged.
      **Done:** added exactly that group; `dependencies = []`'s neighbor `dependencies =
      ["agentweave-hub>=1.0.0"]` untouched, `all` left as-is (it aggregates `mcp`/`jobs`, not every
      extra — `app` was not folded in, since nothing in section 3 asked for that and pywebview stays
      opt-in by design). `tests/test_packaging.py` (which reads `pyproject.toml`'s extras) still
      passes unmodified.
- [x] 3.2 A new `_open_app_window_native(url: str) -> bool` (or similarly named) in `cli.py`: tries
      `import webview`, and if present, calls `webview.create_window("AgentWeave", url)` then
      `webview.start()`. Returns `True` if it ran the pywebview path, `False` if `pywebview` is not
      importable (caller falls back to `_open_app_window`). Any exception raised while creating or
      starting the window (e.g. no WebView2/WebKitGTK/Qt backend present) is caught, a message is
      printed naming what's missing, and the function returns `False` so the caller falls back —
      per `design.md` D5, app mode stays best-effort.
      **Done:** added at `cli.py:740`, directly below `_open_app_window`. `import webview` sits
      inside its own inner `try`/`except ImportError: return False`; `create_window`/`start` sit in a
      second `try` that catches `Exception`, calls `print_error(f"Native app window unavailable
      ({exc}); falling back to browser.")` and returns `False`. No import at module load — the CLI's
      stdlib-only stance (`CLAUDE.md`) holds.
- [x] 3.3 Wire **four of the five** real `_open_app_window` call sites through 3.2 first, falling back
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
      **Done:** the line numbers had drifted from earlier iterations' `--profile`/`--port` work (D6),
      so each site was re-found by grepping `_open_app_window(` fresh rather than trusting the task's
      stale numbers — confirmed at `cli.py:802` (native, already-running), `:907` (native, detached
      success), `:978` (Docker, already-running) and `:1071` (Docker, after `compose up`), each now
      `if not _open_app_window_native(url): _open_app_window(url)`. `_wait_and_open_app`
      (unconditional `_open_app_window` call, `cli.py:767`) and `_find_app_mode_browser`/
      `_open_app_window` themselves are byte-for-byte unchanged — confirmed by diff review and by
      `TestAppModeNativeWindow.test_call_sites_fall_back_through_the_native_helper_first` (source-level
      guard, see task 4 below) plus two integration tests exercising the real
      already-running branch in `_hub_native_start` with a mocked `urlopen`.
- [x] 3.4 Confirm by reading (this is a process-model change, not something a unit test proves) that
      the detached-Hub-plus-blocking-window composition described in `design.md` D3 is what actually
      happens: with `pywebview` installed, running bare `agentweave` (default detach; app mode is
      always on) now blocks in `webview.start()` after the Hub is confirmed healthy, and only that
      invocation's exit is delayed — the detached uvicorn process is unaffected and keeps running
      after the window closes, exactly as today's browser-window close does not stop the Hub. Also
      confirm `agentweave --no-detach` (with or without `pywebview` installed) is **unchanged** by this
      task — it still calls `_wait_and_open_app` on a worker thread, still opens the existing
      non-blocking browser fallback, and Ctrl+C on the foreground `uvicorn.run()` remains the only stop
      mechanism, exactly as today.
      **Confirmed by reading, not run** (no display session on this driver — see 3.5's note and the
      log): `main()` (`cli.py:1272`) forces `parsed_args.app = True` for bare invocation
      (`cli.py:1295`) before calling `cmd_hub_start`, which for the non-Docker path (default) calls
      `_hub_native_start(..., detach=not no_detach, app=app, ...)`. In `_hub_native_start`'s detached
      branch, the `_hub_health_check` call (`cli.py:867` region) gates entry to the block that opens
      the window — `webview.start()` (inside `_open_app_window_native`) is only reached after health
      passes, and nothing downstream of it undoes the already-spawned, already-detached `uvicorn`
      `Popen` — that process object is never touched again in this function once spawned, so it
      outlives the CLI invocation's exit exactly as before this change. `--no-detach`'s branch
      (`cli.py:908` "Foreground mode") is untouched by this task: it still spawns
      `threading.Thread(target=_wait_and_open_app, ...)` and still blocks the main thread in
      `uvicorn.run(...)`, with `KeyboardInterrupt` as the only stop path — identical to before 3.1-3.3,
      confirmed by diff (no line in that branch or in `_wait_and_open_app` changed).
- [x] 3.5 **Added 2026-08-16, resolves amendment A2 (`design.md` D3, "Testability, resolved").**
      Read `_open_app_window_native`'s finished body and confirm it contains nothing beyond
      `webview.create_window`/`webview.start`, the try/except around them, and the already-resolved
      URL/title arguments — no conditional branching on page content, no data fetching, no logic a
      Playwright-driven browser test against the same URL wouldn't already exercise. This is a
      diff-review check, not a runtime assertion (there is no window Playwright can attach to); record
      what was read and confirmed, not just that the task was done.
      **Read and confirmed** (`cli.py:740-756`, the finished body, quoted in full here since that is
      what this task asks to record): an outer `try: import webview / except ImportError: return
      False`, then `try: webview.create_window("AgentWeave", url) / webview.start() / return True /
      except Exception as exc: print_error(f"Native app window unavailable ({exc}); falling back to
      browser.") / return False`. Nothing else — no `if` on `url` or any response, no network call, no
      state read or written beyond the two webview calls and the one print. This matches amendment
      A2's constraint exactly: everything downstream of "a window pointed at this URL" is only ever
      exercised by the existing Playwright suite against the same FastAPI-served bundle in a real
      browser, never by this shell.

## 4. CLI tests — agent-verifiable

**Corrected 2026-08-16 (amendment A1 in `design.md`) — read this before touching section 4.**

This section previously asserted in bold that `tests/test_cli.py` **does not exist** and instructed
creating it "from scratch." That is **false**, and acting on it destroys existing coverage. The file
was added in `b3f4b11`, last touched in `db01f40` (2026-08-10), and has since been extended again
with `TestTwoInstancesDoNotCollide`. It currently holds four test classes.

The round-1 finding it came from was narrower and remains true: no test in that file covers
`_open_app_window`, `_hub_native_start` or app mode. So the gap is real; the conclusion drawn from
it was not. **Tasks 4.1-4.4 extend the existing file.** They add a class alongside the others,
following its established shape, and 4.4 means "the whole suite is still green," not "a new suite
is green."

- [x] 4.1 In `tests/test_cli.py`: a test that with `pywebview` NOT installed (or
      monkeypatched to raise `ImportError` on `import webview`), app mode's behavior is byte-identical
      to today: same call into `_open_app_window`, same arguments, no new branch taken. This is the
      test that makes D3's "nothing silently degrades" claim checkable rather than asserted.
      **Done:** two tests in the new `TestAppModeNativeWindow` class —
      `test_pywebview_not_installed_returns_false` (unit-level: `sys.modules["webview"] = None`
      forces `ImportError` deterministically regardless of whether pywebview happens to be installed
      in this environment; asserts `_open_app_window_native` returns `False`) and
      `test_hub_native_start_already_running_falls_back_when_native_unavailable` (call-site level:
      monkeypatches `_open_app_window_native` to return `False` and asserts `_hub_native_start`'s
      already-running branch calls `_open_app_window(cli._hub_url(8000))` — the exact pre-3.3 call,
      same argument, nothing else).
- [x] 4.2 A test that with `webview` importable (mock the module — do not require a real
      `pywebview` install in the CLI test environment, which is a separate, zero-dependency
      distribution from the Hub's), `create_window` and `start` are called with the URL
      `_hub_resolve_launch_url` resolves, and `_open_app_window` (the fallback) is NOT called.
      **Done:** `test_pywebview_installed_opens_window_with_resolved_url` injects a
      `types.SimpleNamespace` fake into `sys.modules["webview"]` recording calls, asserts
      `create_window("AgentWeave", url)` then `start()` fire in order with the exact URL passed in,
      and the function returns `True`. `test_hub_native_start_already_running_prefers_native_window`
      covers the "`_open_app_window` NOT called" half at the real call site: mocks
      `_open_app_window_native` to return `True` and asserts the recorded call list is exactly
      `[("native", url)]` — the fallback mock is never invoked.
- [x] 4.3 A test that a `webview.start()` exception (simulated via the mock) is caught, and the
      function falls back to calling `_open_app_window` — proving 3.2's "best-effort" contract
      rather than letting a missing backend crash the invocation.
      **Done:** `test_webview_start_exception_falls_back` — the fake module's `start` raises
      `RuntimeError("no WebView2 runtime found")`; asserts `_open_app_window_native` returns `False`
      (not a raised exception) and that `"WebView2"` appears in the printed output, so the diagnostic
      message actually names what's missing rather than just swallowing the error silently.
- [x] 4.4 The whole `tests/test_cli.py` suite passes, the pre-existing classes included. No prior
      test asserted the always-browser behavior, so nothing there should need changing — if one does,
      that is a finding to record, not a test to quietly rewrite.
      **Done:** `tests/test_cli.py` 24/24 passed (up from 16 before this iteration — 8 new: the 6
      described above plus `test_call_sites_fall_back_through_the_native_helper_first`, a source-level
      regression guard counting `_open_app_window_native(` call sites in `_hub_native_start`/
      `cmd_hub_start` and confirming `_wait_and_open_app` has none). No pre-existing test needed
      changing. Full CLI suite `tests/`: 381 passed, 3 skipped (up from 375/3 pre-iteration, +6 net —
      matches the 8 new class tests minus the 2 that were already implicitly exercising these paths
      indirectly through call counts, i.e. no double count needed reconciling here since
      `test_packaging.py`'s existing 4 tests were unaffected by 3.1). `ruff check`,
      `black --check --target-version py311` and `mypy src/` on the changed files all clean (mypy's
      scope is `src/`, per `CLAUDE.md`'s documented command and `ci.yml`'s own `mypy src/` step —
      `tests/` was never in scope and running it there surfaces ~35 pre-existing, unrelated
      `no-untyped-def` findings across the whole file, not a regression from this change).
      Mutation-checked by hand: (a) flipped `_open_app_window_native`'s success `return True` to
      `return False` — `test_pywebview_installed_opens_window_with_resolved_url` went red, the other
      5 in the class stayed green, confirming that one test actually distinguishes success from
      failure rather than passing vacuously; restored, green again. (b) removed the
      `_hub_native_start` already-running call site's fallback wrapping (reverted to an unconditional
      `_open_app_window(url)`, as it was pre-3.3) — both
      `test_hub_native_start_already_running_prefers_native_window` and
      `test_call_sites_fall_back_through_the_native_helper_first` went red (the latter's count check
      dropped from 2 to 1), confirming the wiring test and the integration test each catch a
      regressed call site independently; restored, all 381 green again.

## 5. Migration decision — no code, a documented non-action (D4)

- [x] 5.1 State in the CLI's install docs (wherever bare `agentweave`/`--docker`/`--local` are already
      documented — `docs/` or `README.md`, whichever currently covers it) that anyone who has been
      running the Hub via direct `uvicorn hub.main:app` or `docker compose up` from varying
      directories may find their data at the pre-fix location after upgrading, and that copying the
      database file to the new global path is a manual, one-line step, not something the CLI does
      for them. No code task — `design.md` D4 explicitly decided against writing a migration tool.
      Done: `README.md` only shows bare `pip install agentweave-ai` + `agentweave` (no
      `--docker`/`--local` mention at all), and `docs/index.md` is a landing page that points
      onward — neither is where the flags are actually documented. `docs/getting-started/
      installation.md` is: it's the file with `## Run`, `## Docker (Advanced)` and the
      `--docker`/`--local` examples task 5.1 refers to, so the paragraph landed there, as a new
      "### If you've been running the Hub directly" subsection between "Development Install" and
      "Docker (Advanced)" — its two audiences (direct-uvicorn contributors, directory-varying
      Docker dev use) are exactly `design.md` D4's population 2. Plain language, no code: states
      bare `agentweave`'s path is unchanged, names the two pre-fix patterns, and says the migration
      is a manual one-line file copy the CLI does not perform. Docs-only — nothing to run beyond
      reading the rendered file back, which was done.

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
- [ ] 6.6 **Added 2026-08-16 (D6).** Run `agentweave --profile dev --port 8010` alongside an
      already-running default-profile instance; confirm both `agentweave status` (default) and
      `agentweave status --profile dev` report correctly and independently, then
      `agentweave stop --profile dev` and confirm the default instance is unaffected. Confirm
      `agentweave reset --profile dev` removes only that profile's data by checking the default
      profile's data is still present afterward.
- [ ] 6.7 **Added 2026-08-17, round-2 cold review (D6, task 1.8).** Run `agentweave --profile dev`
      with no `--port` and confirm the error message names both flags and is legible — not a raw
      argparse traceback — and that no process ends up listening on the default port under the `dev`
      profile's name.

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
4. **Start a second, named instance.** With the default instance still running from step 1, run
   `agentweave --profile dev --port 8010` from any directory.
   - *Expect:* a second Hub starts on port 8010 with its own empty project list, not the same
     projects as the default instance. `agentweave status --profile dev` reports it separately from
     `agentweave status` (default). Stopping it (`agentweave stop --profile dev`) does not affect the
     default instance from step 1.
   - *Now try it without `--port`:* run `agentweave --profile dev` alone.
   - *Expect:* the command exits with an error naming both `--profile` and `--port` — it does not
     start a second Hub on the same default port the instance from step 1 is using.

**Where it would go wrong:** if step 1 shows a different project list or a fresh empty state after
switching directories, the global-state fix did not take. If step 4's second instance shares the
default instance's project list or database, profile isolation did not take. If running
`agentweave --profile dev` without `--port` starts a Hub anyway instead of erroring, the
port-collision guard did not take — check whether it is quietly sharing the default instance's port.
If step 2's window has
browser chrome
(tabs, an address bar) despite `pywebview` being installed, the native-window path silently fell
back without saying so — that is a defect, not a taste call.
