# Handoff: AgentWeave 1.0.0 is merged to master and not tagged

**Date:** 2026-08-17T13:00+01:00, **amended 15:00** · **Branch:** `master` · **HEAD:** `b9eee31`

> ## Amendment, 15:00 — the driver kept running after I said I had stopped it
>
> This handoff was written at 13:00 with HEAD at `ec25ca5`. **Master is now `b9eee31`.** Four more
> commits landed between 13:46 and 14:19 from the Scheduled Task driver, which I reported as
> unregistered and had not been.
>
> **The mistake was mine and it is worth naming.** I ran
> `Unregister-ScheduledTask ... -ErrorAction SilentlyContinue` followed by an *unconditional*
> `Write-Output 'driver unregistered'`. The unregister did not take effect; the message printed
> regardless. A success message that is not conditioned on success is exactly the failure mode this
> run spent the day finding in other people's code. The task is genuinely gone now, verified by
> querying for it rather than by asserting it.
>
> **What the driver did, reviewed independently just now:**
>
> - `897ebec` / `66e1cbc` — **product changes** to `hub/hub/api/v1/agent_trigger.py` (+57 lines):
>   `_execute_run` now catches `(Exception, asyncio.CancelledError)` around its whole body and marks
>   the `Run` row `failed` instead of leaving it at `running` forever. This is a genuine reliability
>   fix independent of the flake — a stuck `running` row makes `schedule_agent` queue every
>   subsequent trigger for that agent, an unbounded silent outage. It re-raises `CancelledError`
>   after marking, and its comment is honest that the cancellation theory is unproven.
> - `0c4b87d` / `b9eee31` — log and `STATE.json`, adding decision `D6`.
>
> **Checked, not taken on trust:** `ruff` clean and **2130 passed / 11 skipped** on this tree. The
> one line that looked risky — `returned` referenced on a path where it is unassigned — is safe by
> short-circuit (`not already_terminal and returned`).
>
> **The conclusion is unchanged:** the driver also declined to tag, for the same reason. Six
> theories, all disproven, master red on the one flaky test. **No `v1.0.0` tag, no release, no PyPI
> upload.** Read `D6` in `STATE.json` alongside `D5`.

**Agent:** Claude Opus 5 (1M context) (Claude Code, `/autonomous-session`, operator present at start)
**Previous handoff:** `.claude/handoffs/handoff-0052-2026-08-17-0925-night-run-reviewed-not-merged.md`
**Status:** **paused, not finished.** Everything for 1.0.0 is on master. The tag is not created,
because master's CI is red on a flaky test.

## What the run was asked to do

> *"fixing anything that needs fixing, merging and guarantee that there is a new agentweave version
> on master published to github"* — and, mid-run:
> *"a clean agentweave version pushed on master, update the documentation and readme. We can stop
> the old hub and old versions where it is. Now agentweave is one thing"*

## What landed

**Merged.** `master` went `f6663a9 → 89384cd`, 794 commits, linear, no merge commit. PR #1 MERGED.

| | |
|---|---|
| **One product, one install** | `agentweave-ai` now depends on `agentweave-hub`. `pip install agentweave-ai` used to give a CLI that could not start the Hub. |
| **One version, one tag** | Both `pyproject.toml` files at `1.0.0`; `publish.yml`'s two jobs re-gated onto `v*`; `hub-image.yml` tag trigger `hub-v*` → `v*`. The `hub-v*` scheme is retired. |
| **Python 3.11 floor** | The old `>=3.8` was unsatisfiable once the CLI depended on the Hub, and was already untrue. |
| **Docker install repaired** | `image:` defaulted to `agentweave-hub:audit`, unpullable. Now the GHCR image. Added `name: agentweave` so the `hub-data` volume — and which database you get — stops depending on the launch directory. |
| **Docs + README** | `mkdocs build --strict` green for the first time since 2026-07-29 (34 broken links). `mcp-tools.md` documented 12 of 21 tools and denied one that ships. `task-lifecycle.md` documented a deleted command. Install instructions in three places said to install two packages. |
| **CHANGELOG** | A 1.0.0 entry, every figure measured from git. |
| **13.9** | A single-agent project is no longer told about a team on every turn. |

**Verified in the world, not as green ticks:** GHCR image digest moved `ab4c7436…` → `7db9605e…`;
docs site returns 200 with "Python 3.11" and 404s the retired page; both wheels build at 1.0.0 and a
clean venv install of `agentweave-ai==1.0.0` pulled `agentweave-hub` 1.0.0 with
`agentweave --version` reporting 1.0.0.

## The finding that consumed the second half

**`hub-test` had been failing at its install step since 2026-07-29 and never reached pytest.** Fixing
that ran the Hub suite in CI for the first time: **37 failed, 2093 passed**, against 2130 locally.
Nothing regressed — 37 tests had never executed outside a Windows box with `claude` and `codex`
installed. See `openspec/explorations/2026-08-17-the-hub-suite-has-never-run-clean.md`.

**36 are fixed**, each verified in two configurations (a venv pinned to CI's fastapi/starlette, and
the runner binaries stripped from PATH). Notably: **the product is compatible with starlette 1.6** —
2114 tests pass there, every failure was two test helpers walking `app.routes`.

## Why there is no tag

`test_agent_trigger_overrides::test_a_conversation_whose_model_changed_attributes_usage_per_turn`
fails on CI roughly half the time and has never failed locally in ~30 runs.

**Six theories. Five wrong. Do not re-try these:**

| # | Theory | Killed by |
|---|---|---|
| 1 | `observed_at` clock collision suppresses the second reading | the same commit passing and failing; also predicts the wrong platform |
| 2 | SSE queue overflow (`maxsize=256`, drop-on-full) drops the tail | the per-turn drain landing and changing nothing |
| 3 | Delivery latency — the drain races the broadcast | the bounded wait landing and changing nothing |
| 4 | **The second turn is queued, not run** | **CONFIRMED** by a diagnostic assertion: `Input queued for model-switch`, `run_id: None` |
| 5 | `_fake_pty`'s finite `read.side_effect` hangs the loop on an extra read | the EOF-forever fix landing and changing nothing |
| 6 | *(unexamined)* something after the read loop — `read_codex_rollout_accounting` is the only codex-specific post-loop step | — |

**Where it actually stands:** the first run never leaves `running` on CI within 10s, which queues the
second trigger, which loses the broadcast. `agent_trigger.py:1407` breaks on an empty read and
`pty.wait()` is mocked, so the loop itself should terminate — the hang is after it, or in the Run
row's status commit. **Theory 6 is the next thing to look at.**

This test is the only one patching `PipeSession.spawn` with `_fake_pty`, which is shaped for
`PtySession`; `session.isalive()` therefore returns a truthy MagicMock. That did not matter for the
read loop, but it may matter elsewhere.

**Second, separate flake:** `test_spec_index::test_a_requirement_put_back_by_hand_is_restored`, ~2
runs in 6 under load, 12/12 in isolation. **Attribution checked** by stashing all my changes and
reproducing on the unmodified tree — pre-existing, not caused by this run, not diagnosed.

## Constraints and user directives (verbatim)

> *"Full auto, but only on green CI"* — with the stated hard rule: **never release on red or
> unfinished CI.** Honoured. Master's CI has not been green on a run I trust.

> *"We can stop the old hub and old versions where it is. Now agentweave is one thing"*

Version **1.0.0**, tag **`v1.0.0`**, no `hub-v1.0.0`. **PyPI is irreversible** — a version number
can never be reused. Out of scope by the operator's own selection: driving the UI, pywebview/Q6,
archiving the finished openspec changes.

## Dead ends

- Bare `python` is a hermes venv without `pytest_asyncio`. Use
  `C:/Users/huida/AppData/Local/Programs/Python/Python311/python.exe`.
- `cd` in one Bash call does not persist usefully — a follow-up search silently ran from `hub/` and
  returned "nothing found" twice today, once producing a false pass on `openspec validate`.
- Git Bash `date` prints UTC labelled `+0100`. Stamp from PowerShell. I also drifted ~50 minutes by
  estimating elapsed time instead of stamping it; `STATE.json`'s `last_heartbeat` is authoritative.
- The Windows interpreter cannot see Git Bash's `/tmp`.
- A name is not what you last checked: I nearly merged `hub-native-experience:master` (an untested
  log commit) instead of the tested SHA, and `refs/heads/master` was stale all session while
  `origin/master` had moved.

## Next steps

1. **Check CI on `89384cd`.** If green, the release is four commands — `release_runbook` in
   `.claude/autonomous/STATE.json`, from step 4. `.release-notes-1.0.0.md` is in the repo root,
   untracked, ready for `gh release create`.
2. **Otherwise pursue theory 6**: instrument what happens between the read loop breaking and the
   `Run` row reaching a terminal status, for the codex-exec path specifically.
3. **Diagnose `test_spec_index`** separately; it is pre-existing and unrelated.
4. **Do not tag on red.** The one rule worth keeping.

## Read on resume

- `.claude/autonomous/STATE.json` — `release_runbook` (7 steps) and `decisions_for_user` D5.
- `.claude/autonomous/2026-08-17-one-version-one-product-log.md` — 19 iterations, oldest first.
- `openspec/explorations/2026-08-17-the-hub-suite-has-never-run-clean.md` — the 37, by cause.
