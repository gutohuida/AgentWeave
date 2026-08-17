# The Hub test suite has never run in a clean environment

**Date:** 2026-08-17 · **Found by:** the 1.0.0 release run, PR #1
**Status:** 29 of 37 fixed and verified. The remainder needs an operator decision, and one of them
is probably not a test problem.

## What happened

`hub-test` in CI had been failing since 2026-07-29 with
`ModuleNotFoundError: No module named 'agentweave'` — an *install-step* failure. It never reached
`pytest`. Fixing that let the Hub suite run in CI for the first time, and it reported:

    37 failed, 2093 passed, 11 skipped

The same suite is **2130 passed / 11 skipped** on the developer machine. Nothing regressed. 37 tests
had simply never executed anywhere except a Windows box with `claude` and `codex` installed.

## Resolved: the product is compatible with starlette 1.x

This was the frightening part, and it is now answered with evidence rather than left open.

CI resolved **fastapi 0.141.1 / starlette 1.6.0**; the developer machine had **0.136.3 / 0.52.1**. A
major version boundary, crossed silently, because `hub/pyproject.toml` declares `"fastapi>=0.110"`
with no upper bound.

A venv pinned to CI's exact resolution ran the whole suite: **16 failed, 2114 passed** — and 3 of
those 16 failed only because that venv had no `agentweave` in it. Every genuine failure was the same
message, `no <METHOD> <path> route with a body model`, from two tests that walk `app.routes`.
**Nothing under `hub/hub/**` failed.** Route *introspection* changed; route *resolution* did not.

Starlette 1.x keeps included routers as `_IncludedRouter` wrappers rather than flattening them into
`app.routes`; the real `APIRoute`s nest inside, and each carries a **relative** path.

The sharp edge: `test_spec_documents_api`'s check proves an **absence** — that no route can mutate a
spec document event. A scan finding zero routes returns "nothing found", which is what that test
wants to see. It failed only because it went on to touch `route.path` on a wrapper. **One
assertion-shape away, it would have passed vacuously**, and the guarantee would have quietly stopped
being checked.

`hub/tests/_routing.py` now walks either shape, verified by producing an **identical set of 140
paths on both starlette versions**.

**So the dependency bound is no longer urgent.** It remains worth deciding — see below — but not as
a release blocker.

## Fixed: the PATH cluster (17)

Reproduced locally by stripping `claude` and `codex` from PATH, which produced exactly the 17 CI
failures. Two causes:

- **16** — `run_turn` resolves the executable *before* it spawns, and the fixture patched only
  `spawn`. Binary resolution belongs to `test_pty_runner`; this file's subject is the
  notification-handling loop.
- **1** — one test omitted the `hub.launchability.shutil.which` patch that its **33 siblings in the
  same file** all carry, so it failed on a missing binary instead of asserting the error it exists
  to pin.

Both verified with the binaries hidden and present.

## Fixed: two platform skips

`ctypes.windll` cannot be patched into existence on POSIX, and there are no `.cmd` shims to unwrap
there. Those tests describe Windows behaviour and now say so.

## Open, and probably not a test problem

**`pid_alive()` reports a killed process as alive on POSIX.** It uses `os.kill(pid, 0)`, which
succeeds for a **zombie** — a SIGKILLed child remains present until reaped. So after
`terminate_process_tree()`, the process still reads as alive. That is
`test_pty_runner::test_kills_a_long_running_process` and
`test_lifespan_shutdown::test_hub_shutdown_kills_a_real_tracked_process`, both failing
`assert True is False`.

This matters because **the Docker image is Linux**. A Hub shutting down there would believe its
children are still running.

The counter-argument, from `pid_alive`'s own docstring, is that it exists for *crash reconciliation*
— a **restarted** Hub checking a pid it did not spawn, where the orphan has been re-parented to init
and reaped, so no zombie exists. If that is the only caller, the impact is nil and the tests are
asserting something the product never does. **That is the thing to check**, and it cannot be checked
from Windows.

Two further failures — `test_project_workspace_unavailable`'s `NoResultFound` ×2 — and one
model-catalog assertion are undiagnosed for the same reason.

## What to decide

1. **Is `pid_alive` on POSIX a real defect?** Trace its callers. If anything checks liveness of a
   process the same Hub just killed, it needs reaping (`waitpid(WNOHANG)`) or a `/proc/<pid>/stat`
   zombie check. If only the restart path calls it, the tests are wrong, not the code.
2. **Does 1.0.0 pin `fastapi`/`starlette`?** No longer a blocker — the product works on 1.6 — but
   shipping an unbounded range still means users get versions nobody has run. A bound documents what
   was tested; leaving it open documents nothing.
3. **Should CI prove it is a clean environment?** This went unseen for three weeks because a green
   local run and a red CI job looked like a CI problem. A build that fails when a test is skipped for
   a missing binary CI was meant to provide would have caught it on day one.

## What is already done and committed

`hub-test` installs correctly and the suite runs in CI at all; 29 of the 37 are fixed with the
verification described above; the remaining failures are isolated and named.
