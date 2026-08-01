# Handoff: Phase 3 audit findings closed — ready to start Phase 4

**Date:** 2026-08-01T19:38:00+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `69ac47b`
**Agent:** Claude (Sonnet 5)
**Previous handoff:** `.claude/handoffs/2026-08-01-1917-codex-integration-session-close.md`
**Status:** chunk complete

## Goal

Ship the `hub-native-experience` OpenSpec change (`openspec/changes/2026-07-30-hub-native-experience/`):
move the Hub to owning agent execution directly (native runtime, no Docker dependency, no watchdog
polling), then build identity/queue/tool-surface governance on top. The user confirmed the prior
session's Codex integration fix ("It's working nicely") and asked to finish Phase 3 before starting
Phase 4.

## Current state

**Phase 3 (native runtime, packaging, and crash recovery) is now fully closed — 0 unchecked items
remain in that section of `tasks.md`.** This session closed the three audit findings that were left
over from a prior review, fixing real defects in each case (not just checking boxes):

1. **DNS-rebinding vulnerability in `GET /api/v1/setup/token`** (`hub/hub/api/v1/setup.py`) — the
   endpoint validated only the client's socket IP, so a page served from a public hostname that
   later resolves to `127.0.0.1` could still pass and exfiltrate the live bootstrap API key. Fixed
   by also requiring `Host` to resolve to a loopback/Docker-internal allowlist entry and `Origin`
   (if present) to match `Host`.
2. **Silently stale UI bundle** — `hub/hub/static/ui/` is a committed build artefact nothing
   rebuilds automatically in a source checkout, so a contributor editing `hub/ui/src` without
   rebuilding gets an old UI silently served. Fixed by comparing git commit history of `hub/ui/src`
   vs `hub/hub/static/ui` at Hub startup (logged warning) and on every `GET /health`
   (`ui_stale`/`ui_stale_detail` fields), surfaced by `agentweave hub status`.
3. **Unreachable Hub showed the API-key prompt** — `bootstrapState === 'failed'` collapsed both "Hub
   didn't respond at all" and "Hub responded but declined" into the same state, so a Hub that simply
   wasn't running still showed "please paste your API key" — which cannot fix that. Fixed by making
   `fetchSetupToken()` return a discriminated result (`ok`/`unreachable`/`unavailable`) and adding a
   distinct `unreachable` bootstrap state with its own "Can't reach the Hub" + Retry screen.

All three were originally numbered 3.20/3.21/3.22 in `tasks.md`, but those numbers were already used
by a *different*, already-completed pair of follow-ups (Codex resume-grammar fix and a BOLA fix) a
few lines further down the same file — a pre-existing numbering collision, not something introduced
this session. Renumbered the three findings closed this session to **3.23/3.24/3.25** to make them
unique, with a note on each pointing at the collision.

The Codex integration itself (hidden `PipeSession` for `exec --json` on Windows) is unchanged this
session — that work was already verified and accepted by the user in the previous handoff/turn.

## Files touched

- `hub/hub/api/v1/setup.py` — added `_hostname_from_host_header`, `_is_allowed_host`,
  `_origin_is_same_or_absent`; wired both checks into `get_setup_token` before the existing
  client-IP check. Finished.
- `hub/hub/main.py` — added `_git_last_commit_iso`, `_compute_ui_staleness_warning`,
  `_ui_staleness_warning` (module-level `lru_cache`, computed lazily on first `/health` hit or at
  lifespan startup); `/health` now returns `ui_stale`/`ui_stale_detail` when stale; lifespan logs the
  warning too. `UI_SRC = Path(__file__).parent.parent / "ui" / "src"` added as a module constant.
  Finished.
- `hub/tests/test_setup.py` — updated the two existing localhost tests to pass an explicit
  `Host: localhost` header (the `ASGITransport` test fixture's `base_url` is `http://test`, which
  now fails the new Host check without it); added 3 new tests for rebound Host, cross-origin
  rejection, and same-origin acceptance. Finished.
- `hub/tests/test_ui_staleness.py` — new file, 5 tests exercising the git-history comparison against
  throwaway temp git repos (deterministic — does not depend on this repo's own commit history).
  Finished.
- `src/agentweave/cli.py` — `cmd_hub_status` now parses the `/health` JSON body and prints a
  `print_warning` line if `ui_stale` is set. Finished.
- `hub/ui/src/api/setup.ts` — `fetchSetupToken` return type changed from `SetupConfig | null` to a
  new discriminated union `SetupTokenResult` (`{status:'ok',...} | {status:'unreachable'} |
  {status:'unavailable'}`). Only call site was `configStore.ts`, updated in the same commit. Finished.
- `hub/ui/src/store/configStore.ts` — `BootstrapState` gained `'unreachable'`; `bootstrap()` now
  branches on `SetupTokenResult.status` instead of truthiness. Finished.
- `hub/ui/src/App.tsx` — added a render branch for `bootstrapState === 'unreachable'`: a centered
  "Can't reach the Hub" message with a Retry button that re-calls `useConfigStore.getState().bootstrap()`.
  Finished.
- `hub/ui/src/__tests__/configStore-bootstrap.test.ts` — new file, 3 tests covering
  unreachable/declined/ok bootstrap outcomes via a mocked `globalThis.fetch`. Finished.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — renumbered and checked off
  3.20→3.23, 3.21→3.24, 3.22→3.25 with implementation notes on each. Finished.

All committed in `69ac47b Close Phase 3 audit findings: stale UI, DNS rebinding, unreachable Hub`.

## Key decisions

1. **Host/Origin check reuses `_is_local_address`** rather than a separate allowlist, so Docker
   bridge ranges stay consistent between the socket-IP check and the new Host check. Rejected a
   stricter "must be exactly `localhost`" rule because it would break the existing Docker
   port-forwarding support this endpoint already documents.
2. **UI staleness uses git commit history, not filesystem mtimes.** mtimes get reset to checkout
   time on `git clone`/`git checkout`, which would produce false staleness signals (or mask real
   ones) independent of actual edit recency. `git log -1 --format=%cI -- .` run from within each
   directory is stable regardless of when the tree was checked out. Rejected a build-stamp JSON file
   approach (writing a timestamp at build time) as heavier — it would require touching the Makefile,
   the Dockerfile, and `publish.yml` (which already rebuilds fresh in CI, so it isn't the affected
   path) for no benefit over comparing commit history directly.
3. **Staleness check is lazy + cached (`functools.lru_cache`), not eager at every `create_app()`.**
   The Hub test fixture calls `create_app()` once per test; eager computation would add two
   `subprocess` calls (git log ×2) to every single test in the 345-test suite. Computing only on
   first `/health` call (and caching the result for the process lifetime, since git history doesn't
   change mid-run) keeps this to at most one extra subprocess pair for the whole suite.
4. **Renumbered the three findings to 3.23–3.25** rather than leaving the 3.20/3.21 collision in
   place, since resolving it was directly adjacent to closing the tasks and cheap to do now — not
   scope creep, just cleanup of the exact section being edited.
5. **`SetupTokenResult` fully replaces the old `SetupConfig | null` return type** rather than adding
   a second function or an out-of-band reachability flag, since `configStore.ts` was the only caller
   — confirmed via grep before making the breaking change.

## Constraints and user directives (verbatim)

- "Ok, finish phase 3 then" — this session's directive; scope was the three open Phase 3 items
  (3.20–3.22 as numbered at the time), not Phase 4.
- "It's working nicely." — confirms the Codex `PipeSession` integration is accepted; no more work
  needed there barring new evidence.
- "Yeah and always commit the changes." (from prior session, still binding) — committed without
  asking, per this and the `[[always-commit-checkpoints]]` memory.
- "After every threshold of implementation you must run the skill `/handoff`" (from prior session,
  still binding) — this file.
- Repository rule: never commit runtime `.agentweave/` state; stage explicitly rather than using
  `git add -A`. Followed — staged files by exact path in this session's commit.
- `openspec/changes/.../tasks.md` working protocol (documents itself): re-read `proposal.md`,
  `design.md`, and touched `specs/*/spec.md` before starting a phase; `/handoff` at every threshold;
  verify against scenarios, not intent.

## Dead ends

- None encountered this session. (The Codex/PTY dead ends from the prior handoff still apply and are
  unchanged — see that handoff if resuming Codex-runner work specifically.)

## Verification

Ran and passed, this session:

- `cd hub && py -m pytest tests/test_setup.py -v` — 9 passed (includes the 4 new/updated tests).
- `cd hub && py -m pytest tests/test_ui_staleness.py -v` — 5 passed.
- `cd hub && py -m pytest -q` (full Hub suite) — **345 passed, 4 skipped**, same 4 pre-existing
  Alembic deprecation warnings as before (up from 337 passed before this session — 8 new tests).
- `cd hub/ui && npm run build` (`tsc && vite build`) — clean; the one esbuild "duplicate case clause"
  warning in `eventSummary.ts` is pre-existing and unrelated.
- `cd hub/ui && npx vitest run` (full UI suite) — **199 passed** (196 before + 3 new
  `configStore-bootstrap.test.ts` tests). The `ErrorBoundary.test.tsx` console "Error: boom" output
  is intentional test noise, not a failure.
- `py -m ruff check hub/hub/main.py hub/hub/api/v1/setup.py hub/tests/test_setup.py
  hub/tests/test_ui_staleness.py src/agentweave/cli.py` — all clean.
- `py -m black --check` on the same file set — clean after one `black` reformat of
  `test_ui_staleness.py` (line-wrapping only, re-ran tests after — still 14/14 passed for that pair
  of files).
- `py -m ruff check hub/ tests/` (repo-wide) — 1 pre-existing unrelated finding in
  `tests/test_cli_watch.py` (import ordering), not touched this session, not introduced by it.
- `py -m mypy hub/hub/main.py hub/hub/api/v1/setup.py` — 108 pre-existing errors across 18 files
  (missing return-type annotations on FastAPI route handlers throughout the whole `hub/` package,
  untyped third-party stubs for `apscheduler`/`croniter`, etc.). Confirmed by reading the flagged
  lines that none of my new functions (`_git_last_commit_iso`, `_compute_ui_staleness_warning`,
  `_ui_staleness_warning`, `_is_allowed_host`, `_origin_is_same_or_absent`) are among them — all have
  explicit return type annotations. `mypy` is evidently not a clean/enforced gate in this repo's
  current state; did not attempt to fix pre-existing debt, out of scope.

Not tested this session:

- No manual browser verification of the new "Can't reach the Hub" screen — only unit/component-level
  (`configStore-bootstrap.test.ts`) and `tsc`/build verification. If continuing UI polish, worth a
  quick manual check: stop the Hub process, load the dashboard fresh (no cached key), confirm the
  Retry screen appears instead of `SetupModal`, and confirm Retry works once the Hub is restarted.
- Did not re-run the Codex manual verification steps from the prior handoff (window/Stop testing) —
  out of scope for this session, already accepted by the user.
- `hub/Dockerfile`'s UI staleness path is a non-issue by design (it always rebuilds fresh) and was
  not touched or tested.

## Git state

- Branch: `hub-native-experience`.
- HEAD: `69ac47b Close Phase 3 audit findings: stale UI, DNS rebinding, unreachable Hub`.
- No upstream configured; all commits local and unpushed.
- Working tree clean except the same 7 pre-existing untouched untracked paths as every prior handoff
  in this chain (six older handoff files plus `.claude/skills/aw-spec-reindex/`) — none of this
  session's business, left alone.

## Next steps

1. Re-read `openspec/changes/2026-07-30-hub-native-experience/proposal.md`, `design.md`, and every
   `specs/*/spec.md` touched by Phase 4 — the working protocol at the top of `tasks.md` requires this
   before starting a phase, and it was not done yet this session (Phase 3's leftover work didn't need
   it, but Phase 4 is new).
2. Start Phase 4 — "Identity, runner capability, and surface split"
   (`openspec/changes/2026-07-30-hub-native-experience/tasks.md:1023`, 7 tasks: 4.1–4.7). First task:
   4.1, inject a per-run agent identity at spawn and bind it to the connection on the tool-protocol
   path. This phase was deliberately moved ahead of the queue phase (see the "Ordering revision"
   note near the top of `tasks.md`) because every future queue entry stamps an origin, and building
   that on today's self-declared `--from-agent` field means reworking the queue's core record later.
3. Task 4.2 specifically calls out `cli.py:1519` (`sender=args.from_agent or "unknown"`) as the field
   to remove — check current line number first, since this session's edits shifted some line numbers
   elsewhere in `cli.py` (the `cmd_hub_status` addition was much earlier in the file, around line
   3463, so 4.2's target is likely still close to 1519 but worth confirming with a fresh grep rather
   than trusting the stale line number).
4. Run `/handoff` again after Phase 4 completes (task 4.7 is explicitly a `/handoff` checkpoint in
   the plan itself).

## Open questions for the user

None currently blocking. (The previous handoff's open question — Codex `exec --json` vs
`app-server` — was resolved this turn: user confirmed the current integration "is working nicely,"
so no app-server work is authorized.)

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — authoritative phase ledger; Phase 3
  fully closed, Phase 4 starts at line 1023.
- `openspec/changes/2026-07-30-hub-native-experience/design.md` — required reading before Phase 4
  per the working protocol; carries the reasoning behind the identity-before-queue ordering decision.
- `openspec/changes/2026-07-30-hub-native-experience/specs/agent-tool-surface/spec.md` (or wherever
  the tool-surface spec lives — confirm exact path; task 4.6 names scenario group
  `agent-tool-surface`) — the scenarios Phase 4 must satisfy.
- `src/agentweave/cli.py` — around the `args.from_agent` usage task 4.2 targets; re-grep for
  `from_agent` rather than trusting the line number above.
- `hub/hub/api/v1/agent_trigger.py` — where the Hub currently spawns agent processes; task 4.1's
  "inject a per-run agent identity at spawn" almost certainly lands here.
