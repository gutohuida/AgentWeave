# Handoff: Agent capability plane closed out; next successor to select

**Date:** 2026-08-03T02:45:00+01:00 · **Branch:** hub-native-experience · **HEAD:** 9c00c15
**Agent:** Claude Sonnet 5 (Claude Code)
**Previous handoff:** .claude/handoffs/2026-08-03-0213-agent-capability-parity.md
**Status:** successor complete and archived; umbrella needs its next successor selected

## Goal

Complete the entire Hub-native-experience umbrella, one independently-proposed successor at a
time, per the slice table in
`openspec/changes/archive/2026-08-02-agent-conversation-workspace/design.md`.

## Current state

`agent-capability-plane` (phases 0–4) is fully implemented, live-verified, spec-synced, and
archived at `openspec/changes/archive/2026-08-03-agent-capability-plane/`. This was the successor
covering phases 9's identity work: one least-privilege run-token-authenticated application API
shared identically by HTTP, MCP, and CLI commands.

`openspec/specs/agent-capability-plane/spec.md` (new) and `openspec/specs/agent-tool-surface/spec.md`
(new — the umbrella's six unmodified requirements plus this change's revised identity requirement)
now exist as authoritative main specs. `openspec/changes/2026-07-30-hub-native-experience/tasks.md`
16.2 is annotated as partially done: `agent-tool-surface` is synced, the other nine delta specs
under that umbrella are not.

**The umbrella itself is not done.** Per its own closeout note, it archives only once every
successor re-cut from phases 9–16 is complete. Per the slice table, with capability plane done,
these are now unblocked and "ready to propose" / "needs its own proposal":

- **Single runtime** — was explicitly blocked on agent capability plane "for replacement of the CLI
  fallback"; now unblocked. Deletes the watchdog, local/git transports, CLI-only collaboration
  modes. Matches prior strategic direction already recorded in memory
  (`project_hub_owns_execution.md`, `project_local_only_vision.md`): Hub becomes the only way to use
  AgentWeave.
- **Composer intelligence** — `@path`/`/command`/`$skill` triggers, keyboard menu, in-place agent
  selector. Depends only on the (already-archived) conversation workspace change.
- **Accounting and budgets** — per-turn token usage, aggregation, project budget pausing autonomous
  turns. Independent.
- **Runner/agent/charter separation** — reusable execution capability vs. addressable identity vs.
  behaviour. Independent. CLAUDE.md flags the multi-role system as slated for replacement by this;
  don't build new role-system work without checking it first.

Not yet ready: "Local multi-project workspace" and "Specification program" are only at "ready for
technical exploration" (not proposal); "Approval gates" is blocked; "Retire the Hub name" is
deferred until "Single runtime" lands.

**Recommendation for the next successor: Single runtime.** It was the one item on the list whose
blocking dependency (capability plane) *just* closed, and it's the direction the user and I have
already discussed and recorded (see memory). Not yet started — no proposal exists for it.

## Files touched (this run, phase 4 only)

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — 16.2 partial-completion annotation.
- `openspec/specs/agent-capability-plane/spec.md` — new main spec (created from the archived
  change's delta, unchanged content).
- `openspec/specs/agent-tool-surface/spec.md` — new main spec (umbrella's original six requirements
  + this change's revised identity requirement merged in).
- `openspec/changes/agent-capability-plane/` → moved to
  `openspec/changes/archive/2026-08-03-agent-capability-plane/` (git recorded as renames).

## Key decisions

- **`agent-tool-surface` had no main spec yet** (the umbrella that originated it, phases 1-8, was
  never synced — its own 16.2 is still open). Rather than skip the sync or block on syncing all nine
  other delta specs, I materialized `agent-tool-surface`'s main spec from the umbrella's original
  ADDED requirements (already shipped, per the umbrella's own closeout note that they "remain
  authoritative for behaviour implemented in phases 1–8") with this change's MODIFIED delta applied
  on top of just the identity requirement. This is a scoped, partial completion of 16.2 — annotated
  as such in the umbrella's tasks.md, not claimed as full 16.2.
- **Live verification used a real Hub process, not `TestClient` or the full `trigger_agent_directly`
  spawn path.** The full spawn path would have invoked a real `claude`/`codex` CLI (both are
  actually on PATH in this environment) — too heavy/risky for a wiring check (real API credits, an
  actual open-ended agentic session). Instead: real `uvicorn` process on a throwaway port with a
  temp SQLite DB, a `Run` row inserted directly via the Hub's own async engine (same mechanism
  `mint_run_token`/`hash_run_token` use), then a genuinely separate `py -3.11` subprocess whose env
  held only `AW_RUN_TOKEN`/`HUB_URL` driving the real `agentweave.transport.http.HttpTransport` code
  against that live server. This exercises the real network/auth boundary without an uncontrolled
  agent session.
- Verified both directions live, not just the happy path: project-key-only and no-auth both 401 on
  `/agent-actions`; a run token 401s on an operator route (`/api/v1/agents`); the token 401s again
  once its `Run.status` flips off `"running"` (terminal revocation).
- ESLint could not run (`hub/ui` has no `eslint.config.js` — confirmed absent on `master` too, so
  pre-existing, not a phase-4 regression). Ran `vitest run` and `tsc && vite build` instead as the
  frontend regression check.

## Constraints and user directives (verbatim, still binding)

> "I want you to work on the entire umbrella project with the same parameters that we discussed
> previously"

> "Ignore the aw-spec skills. I'm using openspec only."

> "At the end of every implementation run handoff aaand spawn a new run with the skill resume."

No root AgentWeave state; live product testing only in testbed (this run's live-verify used its own
throwaway temp-dir Hub instance instead, since testbed's existing project has no Hub/transport.json
wired up and starting one there would create persistent `.agentweave` state outside the point of the
check — the temp instance was fully torn down and deleted after use, nothing under testbed or repo
root was touched). Continue successors; never mark a task done from a plan alone.

## Dead ends

- Ruff remains unavailable.
- Mixing Hub and CLI files named `test_mcp_server.py` in one pytest process causes module-name
  collection collisions; run Hub and root suites as separate commands. (Carried from prior handoff,
  still true.)
- `hub/ui` has no ESLint flat config; `npm run lint` fails immediately on a missing
  `eslint.config.js`. Pre-existing on `master`, not something to fix as part of this umbrella unless
  separately scoped.

## Verification

- Hub: `py -3.11 -m pytest tests/ -q` from `hub/` → 453 passed, 4 skipped.
- CLI: `py -3.11 -m pytest tests/ -q` from repo root → 974 passed, 4 skipped.
- Frontend: `npm run test -- --run` → 289 passed (36 files). `npm run build` → `tsc` clean, Vite
  build succeeded (one pre-existing unrelated duplicate-case warning in `eventSummary.ts`).
- `openspec validate --all --strict` → 18/18 passed after archive.
- Live spawn: real Hub process + real subprocess + real HTTP, all outcomes matched design (see Key
  decisions). Evidence was captured in this conversation's transcript; the throwaway Hub instance,
  its temp DB, and all scratch scripts were deleted after the run — nothing persists to inspect
  later, so if this needs re-demonstrating, repeat the steps rather than looking for artifacts.

## Git state

Branch `hub-native-experience`, HEAD `9c00c15` ("capability phase 4: close out agent capability
plane"). Tree clean.

## Next steps

1. Decide the next umbrella successor to propose (recommendation above: Single runtime). If the
   user redirects, propose whichever they choose instead — all four unblocked candidates are listed
   above with their state.
2. Run `openspec-propose` for that successor: read the relevant slice-table row and any linked
   design context first (for Single runtime: re-read the umbrella's own single-runtime-related task
   phases, and the "delete the watchdog and local/git transports" framing in
   `project_hub_owns_execution.md`/`project_local_only_vision.md` memory — verify those memories
   against current code before trusting them, since they may be stale).
3. Work the new successor's phases the same way as capability plane: tests precede implementation,
   commit and hand off every verified phase, verify against spec scenarios not intent.
4. Eventually, once every phase-9–16 successor is done, return to
   `openspec/changes/2026-07-30-hub-native-experience/tasks.md` 16.1–16.4 to finish syncing the
   remaining nine delta specs and archive the umbrella itself.

## Open questions for the user

None — proceeding with the recommended successor unless redirected.

## Read on resume

- openspec/changes/2026-07-30-hub-native-experience/tasks.md (section 16, and the "Ordering
  revision" near the top for how phases were resequenced)
- openspec/changes/archive/2026-08-02-agent-conversation-workspace/design.md (the slice table, near
  the top)
- openspec/changes/archive/2026-08-03-agent-capability-plane/ (what "done" looked like for the
  previous successor, as a template)
- CLAUDE.md (the roles-system deprecation note, if picking runner/agent/charter separation instead)
