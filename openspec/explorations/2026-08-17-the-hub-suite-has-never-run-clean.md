# The Hub test suite has never run in a clean environment

**Date:** 2026-08-17 · **Found by:** the 1.0.0 release run, PR #1
**Status:** finding, blocking the 1.0.0 release. Needs an operator decision before it becomes a change.

## What happened

`hub-test` in CI has been failing since 2026-07-29 with
`ModuleNotFoundError: No module named 'agentweave'` — an *install-step* failure. It never reached
`pytest`. Fixing that (this run's R1) let the Hub suite run in CI for the first time, and it
reported:

    37 failed, 2093 passed, 11 skipped, in 290s

The same suite is **2130 passed / 11 skipped** on the developer machine. Nothing regressed: 37 tests
have simply never been executed anywhere except a Windows box with `claude` and `codex` installed.

## The 37, by root cause

| Count | Cause | Files |
|---|---|---|
| 17 | **A runner binary is not on PATH.** `FileNotFoundError: 'codex' was not found in PATH` (16), and one `claude` equivalent asserting on the wrong error string. | `test_codex_appserver_run_turn.py`, `test_agent_trigger.py` |
| 12 | **Starlette changed how included routers appear in `app.routes`.** Tests walk the routing table looking for `APIRoute` instances and now meet `_IncludedRouter` wrappers instead. | `test_mcp_body_contract.py` (11), `test_spec_documents_api.py` (1) |
| 4 | **Windows-only behaviour, unguarded on Linux.** `ctypes.windll`; `.cmd`/`.exe` shim resolution; two process-tree kills that report success where the assertion expects failure. | `test_fs_browse.py`, `test_pty_runner.py` (2), `test_lifespan_shutdown.py` |
| 2 | **`NoResultFound`** — not yet diagnosed; plausibly workspace-path dependent. | `test_project_workspace_unavailable.py` |
| 1 | **Model catalog** expects `gpt-5.4-mini` alongside `gpt-5.6-sol`; only the latter is present. | `test_agent_trigger_overrides.py` |

## The part that is not a test problem

CI resolved **starlette 1.6.0** and **fastapi 0.141.1**. The developer machine has **starlette
0.52.1** and **fastapi 0.136.3**. That is a *major* version boundary, and it happened silently
because `hub/pyproject.toml` declares:

    "fastapi>=0.110",

with **no upper bound**. So today, `pip install agentweave-ai` gives a user a Starlette major
version this codebase has never been tested against end to end.

**How bad is it?** Weaker than it first looks, and worth stating precisely rather than dramatically:

- Every `_IncludedRouter` failure is in **test** code introspecting `app.routes`, not in
  `hub/hub/**`. Route *introspection* changed; route *resolution* did not.
- **2093 tests passed on starlette 1.6**, including the API tests that drive real requests through
  httpx. That is meaningful evidence the application itself works there.

So the honest reading is: no product breakage is demonstrated, and no product compatibility is
demonstrated either. The suite that would tell us is the one that has never run clean.

## Why this blocked the release rather than being fixed in place

The run was authorised to publish 1.0.0 "full auto, but only on green CI", and pre-authorised to
stop if CI surfaced something that was not small and understood. This is understood but not small —
37 tests, five root causes, across six files — and two properties make fixing it inside the release
change a bad trade:

1. **The Linux failures cannot be reproduced on the developer machine.** Fixing them means guessing
   and iterating through 5–25 minute CI rounds, blind, with the changes landing unreviewed in a
   1.0.0.
2. **Fixing all 37 would still not settle the release question.** The dependency bound is a product
   decision: either 1.0.0 pins an upper bound — changing what every user gets — or it ships
   unbounded and users get a combination nobody has tested. That is the operator's call, not a
   mechanical repair.

An unreleased 1.0.0 costs a few hours. A 1.0.0 on PyPI whose test suite has never passed in a clean
environment cannot be withdrawn.

## What to decide

1. **Does 1.0.0 pin `fastapi`/`starlette` to the tested range?** Pinning ships what has actually
   been verified and can be relaxed later once the suite passes on starlette 1.x. Not pinning ships
   an untested major version to every user.
2. **Which of the 37 are "skip when the environment lacks X" and which are real coverage gaps?** The
   17 PATH-dependent ones are integration tests needing a runtime — `skipif` is honest for those.
   The 4 Windows-only ones want a platform marker. The 12 introspection ones want a helper that
   understands both routing shapes, which is a genuine improvement. The remaining 3 need diagnosis
   before anyone can say.
3. **Should CI gain a "clean environment" guarantee** so this cannot silently recur — e.g. failing
   the build if a test is skipped for a missing binary that CI was supposed to provide.

## What is already done

`hub-test` installs correctly now, so the suite runs in CI at all. That is the change that made this
visible and it is committed. Everything above is what the visibility revealed.
