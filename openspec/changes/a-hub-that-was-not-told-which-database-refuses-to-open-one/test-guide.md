# Test guide — a Hub that was not told which database refuses to open one

Written by **R1, 2026-09-20**, alongside `tasks.md`. Split the way this repo requires: what an agent
can verify on its own, and what only the operator can judge. Nothing here is a plan for ticking a
task — a task closes on a test that fails with its mutation applied, not on this guide.

**The peculiar hazard of testing this change:** the thing it protects is the operator's live
database, and the obvious way to test the protection is to try to open it. **Do not.** Every check
below is either a refusal (nothing opens) or a throwaway profile in the 8090s. There is no check here
that needs `~/.agentweave/hub/data/agentweave.db` to be touched, and if one appears to, it is wrong.

## Agent-verifiable (run by IMPL and by the drive)

| # | check | how |
|---|---|---|
| A1 | With no `DATABASE_URL` anywhere, `Settings()` raises rather than returning a path | Task 1.5 — `monkeypatch.delenv`, `Settings(_env_file=None)`, `pytest.raises(HubNotToldWhichDatabase)` |
| A2 | The refusal is usable, not just correct | Task 1.5 — the message contains the absolute default path, the string `DATABASE_URL`, and bare `agentweave`. Assert the three facts, not the whole string |
| A3 | Every told path still works and the factory never runs | Task 1.6 — env var wins; a value from an env *file* alone also satisfies it (D3, the judgement call R2 should attack) |
| A4 | The CLI/Hub path seam is still guarded | Task 1.7 — `test_hub_default_matches_cli_hub_dir` still compares `_default_database_url()` against `agentweave.cli.HUB_DIR`. **If this test was deleted rather than repointed, the change is wrong**: D4's rejection of the stronger guard rests on that seam existing |
| A5 | The startup line exists **and is at a level that shows** | Tasks 2.6, 2.7 — assert on the `caplog` record's `levelno >= logging.WARNING`. A test asserting only the text passes on an invisible line, which is the exact defect D5 found in `engine.py:228` |
| A6 | The "existed before" flag is computed before anything creates it | Task 2.1 — assert the line says `did not exist` on a path that does not exist, in a process where `init_db` then runs and creates it. Capturing it after `init_db` inverts the answer and still passes a naive test |
| A7 | No port is printed | Task 2.3 — grep the emitted line for `aw_port` / a port number. `bound_address.get()` is `None` during `lifespan()`, so any port on that line is `settings.aw_port`, i.e. wrong whenever `--port` was used |
| A8 | Non-sqlite URLs neither crash the line nor leak a password | Task 2.5 |
| A9 | `make ui` still works | Task 3.1/3.3 — `make ui-check` exits 0. Measured 2026-09-20 that it exits non-zero with a raw `pydantic_core.ValidationError` under a naive version of group 1 |
| A10 | The CLI surfaces are untouched | Task 3.3 — `agentweave --help` and `agentweave doctor` (from `testbed/scratch`) both still run. Neither imports `hub`; **re-measure, do not trust this line** |
| A11 | Nothing that held stopped holding | Task 5.4 — `py -3.11 -m pytest hub/tests/ -q` in full, count written into `tasks.md`. Not `test_config.py` alone: group 2 edits `lifespan()`, which every API test starts |
| A12 | No UI bundle is involved | `git status --short` shows nothing under `hub/ui/src` or `hub/hub/static/ui` |
| A13 | The spec no longer contradicts the code | Task 5.1 — `grep -n "with no" openspec/specs/app-lifecycle/spec.md` after `openspec-sync-specs`: the scenario requiring a no-`DATABASE_URL` `uvicorn` to resolve to the home path is gone |

## The drive (task group 6) — and why the unit tests are not enough here

A1–A13 can all pass on a change that does not work, because every one of them runs inside `pytest`,
where `conftest.py` has already assigned `DATABASE_URL` and already configured logging. **The two
things this change actually claims happen in a process `pytest` never creates:** a bare `uvicorn
hub.main:app` with no variable, and the same command with one.

| # | check | how |
|---|---|---|
| D1 | The refusal fires in the real launcher | Task 6.1 — from a directory with **no `.env`**, `DATABASE_URL` unset: `py -3.11 -m uvicorn hub.main:app --port 8093`. It must not start |
| D2 | And it created nothing | Task 6.1 — record the default path's `mtime` and size **before and after**. Read them; do not infer from the absence of a log line, which is the practice D10 is correcting |
| D3 | The line is visible under uvicorn's real logging | Task 6.2 — against a **new** throwaway profile. D5's entire claim is that an `INFO` line would not appear here; this is where that is settled |
| D4 | The "existed" flag flips | Task 6.2 — stop, start again on the same file, the line now says it existed |
| D5 | The PID on the line is the process that must be killed | Task 6.3 — kill exactly it. uvicorn's reload/spawn means the launching shell's PID is not the listening one, and `DEAD-ENDS.md` already records that trap |

Port in the 8090s, profile directory created for the drive and deleted after, **never `8000`,
`8010`, `~/.agentweave/hub/data/`, `proj-5e960453` or `proj-18e5d4e0`** (task 6.4). No real agent
turn is needed by this change at all; if one is taken anyway it binds `claude-haiku-4-5-20251001`.

## Human-only (for the operator, on their own machine)

These need judgement, not an assertion.

1. **Does your own app still start?** This is the one question that matters. Bare `agentweave`
   supplies `DATABASE_URL` itself (`src/agentweave/cli.py:1028`), so it should be untouched — but
   that is a measurement on *this* checkout's CLI. **If you have an older `agentweave-ai` installed
   than the `agentweave-hub` this change ships in, start it once deliberately and check.** D4 rejects
   a stronger guard specifically because that version skew is real and undetectable from inside the
   Hub; this change does not depend on the CLI, but it is the assumption worth testing by hand.
2. **Is the refusal message one you would want to receive at 2am?** Start `uvicorn hub.main:app`
   with no `DATABASE_URL` and read it as a message, not as a test fixture. It is written for an agent
   and for you, which are not the same reader.
3. **Is the startup warning noise?** It appears on every start of every Hub, forever, at `WARNING`.
   That is deliberate (D5: at `INFO` it would not appear at all), but you are the one who will read
   it a thousand times. If it reads as an alarm rather than a receipt, the wording is wrong.
4. **Do you want the `.env` route to count as being told?** D3 says yes. It means a `.env` in a
   working directory you did not look at can still point a Hub at a database — the refusal catches
   *silence*, not *someone else's file*.
5. **Is losing the fallback acceptable for anything you run that is not `agentweave` or Docker?**
   The change assumes there is no such thing. If you have a shortcut, a scheduled task or a script
   that starts the Hub some third way, it will stop working, loudly, on the first start after this
   lands.
