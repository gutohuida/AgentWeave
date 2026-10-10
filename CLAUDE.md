# CLAUDE.md

Guidance for Claude Code when working on the **AgentWeave Framework** codebase itself. This file is
re-read on every request of every session, so it holds rules and pointers; runbooks and recipes
live in `.claude/reference/` (read on demand) and `.claude/rules/` (loaded automatically when you
read a file they cover). Slimmed from 33 KB on 2026-09-15 for the weekly usage budget — nothing
that constrains a change was dropped.

## You develop AgentWeave here — and you are starting to use it here

This repository is the framework's **source code** first. Since 2026-08-16 the operator is
migrating slowly to developing AgentWeave with AgentWeave — a **staged migration, not a switch**;
expect the tables below to move. (The old blanket "this repo must not acquire a session" rule is
retired, deliberately: the Hub-owned spec flow shipped 2026-08-12/13 and has been driven end to end.)

| Permitted now | Notes |
|---|---|
| Register this repo as a project in a **trial Hub** | Creates `.agentweave/project.json` at the root — gitignored at any depth; leave it that way. |
| Author specification documents under `spec/` | Work product: track and commit them. |
| Use the Hub-owned spec flow (documents, requirements, tasks, evidence, coverage) | Via the app and its MCP tools. |
| Throwaway experiments in `testbed/` | See `testbed/README.md`. |

| Still prohibited | Why |
|---|---|
| Pointing the Hub **you are editing** at this repo | A Hub code change restarts the process orchestrating the work and kills runs in flight. |
| Invoking the legacy `aw-*` collab skills | Product source in `src/agentweave/templates/skills/` — a feature you implement, not a workflow you run. |
| Delegating this repo's work through AgentWeave messaging | Do the work directly, or use Claude Code subagents. |
| Editing `openspec/specs/` | Frozen 2026-10-07: `spec/` is the source of truth (operator's call). |

## The Hubs on this machine

- **Trial Hub `:8010`** — the one you drive. Start it **from `hub/`, from source**
  (`py -3.11 -m uvicorn hub.main:app --port 8010`, with `DATABASE_URL` naming the trial profile);
  **never `agentweave --port 8010`** (the installed console script's migrations lag this checkout)
  and never `agentweave` from the repo root (its `hub/` shadows the package). This repo is
  registered there as `proj-d85a82bf4216`. Full runbook, paths and traps:
  `.claude/reference/hubs.md` — confirm which database a running instance serves before trusting it.
  A Hub with no `DATABASE_URL` reaching it now refuses to start rather than guessing, and names the
  file it opened in its startup log.
- **`:8000` is the operator's real instance, and it runs this checkout by intent.** Never restart
  it, migrate it, call it, or write to its database; read-only `mode=ro` SQLite reads are fine.
  Its restart runs this checkout's migrations on their real data, and **a committed UI bundle
  reaches their live app on their next reload.**

## Specifications — `spec/` owns the corpus (since 2026-10-07)

AgentWeave's lifecycle is `exploring → proposed → approved → archived` (`hub/hub/spec_lifecycle.py`)
plus `current`, reached only through `create_document` (a `capability`-kind document is created
there). The operator made `spec/` the source of truth on 2026-10-07, after re-importing all 45
capabilities (requirement counts verified equal to openspec's).

- **Current behaviour** lives in `spec/capabilities/<capability>/spec.json` (the payload plus a
  `hub` block; the HTML is rendered on read, converted 2026-10-09), owned by the Hub: change one
  through the app or the Hub's document routes (trial Hub `:8010`, `proj-d85a82bf4216`), **never
  by editing the file**. `spec/index.json` and `spec/agentweave.json` are the map. `openspec/specs/` is frozen (see its `README.md`); do not edit or re-sync it.
- **New changes** are authored in the app as `spec/changes/<name>/` documents, one at a time — prefer
  a self-contained slice with no Hub-restart hazard.
- **The changes still in `openspec/changes/` are moved across, not finished there** (operator,
  2026-10-08). When one comes up, re-author it as a short app change (tier rules below), then archive
  the openspec copy (`openspec archive <name> --skip-specs --yes`) with a note naming its successor.
  Before fixing any finding, grep `openspec/changes/` for it: an F330 fix landed beside its own
  unbuilt openspec change on 2026-10-08. Never carry one change in both.
- **Never mark a task complete on the strength of a plan existing.** Only real, verified
  implementation closes a task.
- The spec flow is both the thing you use and the thing you build: **when it frustrates you, record
  a finding** rather than working around it.

### Spec weight follows risk — drive harder, spec lighter (2026-10-04)

The operator reset this on 2026-10-04: spec stays integral but must not become waterfall; time moves
from authoring and re-reading specs to **driving the product and finding errors**. Why: this repo's
dominant failure mode is a fix that passes its tests and cannot fire in production. **Execution finds
that; re-reading prose mostly doesn't**: same-model review without running anything barely improves
the result, and our drives have repeatedly found in one request what three reading rounds missed.

Pick the tier **before** writing anything, and state it in the first commit:

| Tier | When | What it gets |
|---|---|---|
| **0 — fix** | A finding with a repro, or a diff you can say in one sentence | No openspec change. A test that fails before the fix at the seam the finding names → fix → drive → set the finding's `**Status:**` line in `scripts/drive/FINDINGS.md`. |
| **1 — change** | Normal feature or multi-file behaviour | A short proposal (requirements + scenarios + **acceptance drive**), **one grounded review round**, build, drive. |
| **2 — hazard** | Migrations, Hub-restart or live-data hazard, secrets/auth/security, cross-cutting contracts | A short proposal that names the hazard and the migration/rollback, the **acceptance drive written and failing before the build**, build, drive. No separate review rounds (operator, 2026-10-06). |

- **Acceptance drive first.** Every Tier 1/2 change names, before the build, the drive step or e2e
  test that fails while the behaviour cannot fire end to end, and passes only when it can. It is the
  "it really fires" check, and it replaces a third reading round. Also ask what each route *returns*
  when the function it calls raises.
- **A review round is grounded or it doesn't count:** every claim cites `file:line` or comes from
  something it ran (a test, a query, a route call). Ungrounded "this might…" findings are dropped.
- **Spike when the approach is unclear.** Build a throwaway tracer in a worktree or `testbed/`, drive
  it, then write the spec from what happened, not from guesses.
- **Keep the documents small.** `design.md` holds short decision records (aim ≤ ~10 KB); round-by-round
  re-derivations go in commit messages, not appended to the design; evidence lives in tests and
  commits, while `tasks.md` carries a one-line pointer. A change whose spec outgrows its code is a smell:
  stop and split, or build.
- **New problems found during review go to the backlog, not into the change.**
- **No R1/R2/R3 review rounds by default, at any tier** (operator, 2026-10-06: "we don't need more
  R1-R2-R3"). Run a review round only when the operator asks for one.
- **Trial until ~2026-10-18:** when a change or fix closes, append a row to `spec-queue/METRICS.md`
  (tier, spec/build/drive time, and which stage caught each real defect).

## Project context

- **CLI** (`src/agentweave/`) — Python 3.11+, `agentweave-ai` on PyPI; exactly one runtime
  dependency (`agentweave-hub`), and its own code imports only the stdlib.
- **Hub** (`hub/`) — FastAPI backend + React/Vite dashboard.
- **Docs** (`docs/`) — MkDocs Material, deployed to GitHub Pages.
- Versions: `pyproject.toml` and `hub/pyproject.toml` are the single source of truth.
- Layout and module map: `.claude/reference/architecture.md`.

## Quick commands

### Development Setup

**Install through `constraints-dev.txt`, always** — it pins `starlette`/`fastapi` to what CI
resolves (development-only; the published ranges stay loose). `tests/test_dev_constraints.py` fails
if a documented install or a CI step stops passing `-c`.

```bash
pip install -c constraints-dev.txt -e ./hub
pip install -c constraints-dev.txt -e ".[dev,mcp]"
agentweave --help            # safe at the root; reads no project state
cd testbed/scratch && agentweave doctor   # throwaway runs belong in the testbed, not the root
cd hub/ui && npm install && npm run dev   # http://localhost:5173
```

### Code quality — exactly what CI runs, over exactly CI's paths (`.github/workflows/ci.yml`)

```bash
ruff check src/ hub/ tests/
ruff check scripts/ --select E9,F63,F7,F82,F401,F841   # bug rules only, no style
black --check src/ hub/hub/ hub/tests/ tests/   # add --target-version py311 on this machine
mypy src/
cd hub/ui && npm run lint
```

### Testing — `py -3.11`, never bare `python`

```bash
pytest tests/ -v          # CLI
pytest hub/tests/ -v      # Hub
```

## Architecture rules

- **One local Hub owns many projects.** A project's database ID is durable; its working directory
  is a unique binding recorded by `.agentweave/project.json`. Operator APIs carry explicit project
  IDs, frontend server-state keys are project-prefixed, and the operator SSE stream stamps each
  event with its trusted project ID. **Resolve every project path through `ProjectWorkspace`; never
  use the Hub process's `Path.cwd()` as project identity.** Native mode can open valid local
  directories; Docker mode accepts only container-visible paths beneath `AW_WORKSPACE_ROOT`,
  mounted from `AW_WORKSPACE_HOST_ROOT`, without Docker-socket access or host-path guessing.
- **The Hub owns execution.** No second runtime, no filesystem or git collaboration substrate, no
  role subsystem — `watchdog.py`, `messaging.py`, `runner.py`, `transport/local.py`,
  `transport/git.py` are deleted and not to be recreated. Runners, agents and charters are separate
  project-scoped concepts (`.claude/reference/architecture.md`).
- **The CLI does only what cannot be done from the app**: five `cmd_*` functions survive. CLI rules
  load from `.claude/rules/cli.md`.
- **Operator-in-the-loop has deliberately no backstop.** An agent that needs an answer calls
  `ask_user`; a turn that ends without calling it has ended. The retired "trailing prose reads like a
  question" detector (dropped in migration `0082`, 2026-08-20) must not be reintroduced.

## Critical rules

- `.agentweave/` and `spec/` at the repository root are the migration's, not stray test output — do
  not delete them as cleanup. `.agentweave/` stays gitignored; `spec/` is tracked. An
  `agentweave.yml` at the root is a leftover: ask before keeping it.
- Agent names match `AGENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")` (`src/agentweave/constants.py`)
  — any match accepted except `RESERVED_AGENT_NAMES` (`user`, `operator`) — and the Hub restates
  both as `_AGENT_NAME_RE` (`hub/hub/api/v1/agents.py`, `hub/hub/worktrees.py`) and
  `_RESERVED_AGENT_NAMES` (`hub/hub/worktrees.py`); change them together. That set is checked at
  every use site, so never add a word to it that an existing agent could already hold. Words that
  only shadow a Hub route (`conflicts`, `settings`, `sessions`, and the task ids `board`, `boards`)
  are to be refused at creation only, by a Hub-only check built 2026-10-10
  (F248; `hub/hub/route_words.py`, spec `a-name-a-caller-chooses-reaches-its-own-resource`). They are not part of the
  shared set. `VALID_MODES = ["hierarchical", "peer", "review"]`.
- **Stage paths explicitly; `git add -A` sweeps in scratch.** NEVER commit `kimichanges.md`,
  `kimiwork.md`.
- A test for code that consumes an API payload uses **the ordering that route actually returns**,
  and some test fails if the route's order is reversed. A fixture in an order the route never emits
  is not evidence (F190: green for a month while the behaviour could not fire). Stated in full in
  `agent-stream-events`; only the instance it was learned from has been swept.
- Hub API keys are `aw_live_{random32}`; run credentials are minted per run (`agent_auth.py`), and
  identity is never accepted from a request body or header.
- Editing `hub/hub/mcp_server.py`, models/migrations, or anything under `hub/ui/` loads its own rules
  from `.claude/rules/` — read them; they carry the import restriction, the `approve_tool_call`
  annotation trap, the migration checklist, and the UI-bundle refresh (`make ui` /
  `scripts/refresh_ui_bundle.py`; commit `hub/ui/src` and `hub/hub/static/ui` together).

## Task status lifecycle

```
pending → assigned → in_progress → completed → under_review → approved
                                             ↘ revision_needed
                                             ↘ rejected
```

## When compacting

Keep: the change being implemented and **which system it lives in** (openspec or the trial Hub) with
its phase/task number; the CLI command, route or component being modified; test status (passed,
failing, not run); decisions not yet written down; uncommitted work; spec-flow friction not yet
recorded as a finding; trial-Hub state (project ID, document path, task/requirement IDs) when a trial
change is in flight. Do **not** carry the deleted CLI session vocabulary (session mode, principal
agent, transport type, pending messages).

## Session continuity — the handoff chain

- **Commit each completed checkpoint without asking, and push; do not open PRs.** Merging to
  `master` is the operator's decision, made awake.
- **`.claude/handoffs/` is untracked**, uniformly — do not re-track it (it once carried `aw_live_`
  keys, and a split chain made `/resume` load three-week-old state).
- **`.claude/handoffs/DEAD-ENDS.md` is the exception and stays tracked**: the durable ledger of what
  does not work on this machine. **Read it before debugging an environment problem, and append to it**
  rather than re-copying facts forward in each handoff. Verify an old-dated entry before believing it.

## Resources

GitHub https://github.com/gutohuida/AgentWeave · PyPI https://pypi.org/project/agentweave-ai/ ·
Docs https://gutohuida.github.io/AgentWeave/ · Issues https://github.com/gutohuida/AgentWeave/issues
