# Autonomous run — one version, one product (AgentWeave 1.0.0)

Newest entry at the **bottom**. Written for someone who was not here.

**Branch:** `autonomous/2026-08-17-one-version-one-product`
**Parent:** `hub-native-experience` @ `e45b014`
**Window:** 2026-08-17T10:14+01:00 → 15:00+01:00
**Brief:** `.claude/autonomous/STATE.json` — 12 items, R1…R12, prepared by `/autonomous-prep` with
the operator awake.

**Goal:** one clean AgentWeave **1.0.0** on `master`, published to GitHub, with the documentation
and README describing the product that actually exists. AgentWeave becomes one product with one
version: the separate `agentweave-hub` version line and the `hub-v*` tag scheme retire.

## Limits in force this run

These **invert** the previous run's standing rule, deliberately — this run exists to publish.

1. Outward-facing actions **are** authorised, in R11/R12 order: push, PR, merge to master, tag,
   GitHub release. Still forbidden: force-push, history rewriting on a shared branch, and touching
   any tag or release that already exists.
2. **Never release on a red or still-running CI.** Every job green *and finished* before the PR
   merges; merge green before the tag exists.
3. **PyPI is irreversible.** A version number, once uploaded, can never be reused. Read both
   `pyproject.toml` version lines against `release_shape.version` before creating the tag. Anything
   that looks wrong at that moment is a stop, not a judgement call.
4. Version is **1.0.0** for both distributions; tag is **`v1.0.0`**; no `hub-v1.0.0`.
5. No new runtime dependencies beyond the one this run exists to add (`agentweave-hub` as a
   dependency of `agentweave-ai`). **pywebview remains unauthorised.**
6. Out of scope, chosen by the operator against the alternatives: driving the UI; Q6's desktop
   shell; archiving the finished openspec changes. If R12 finishes early, **stop** — do not start
   them.
7. Never mark work complete on the strength of a plan existing. Every claim measured, or labelled
   unverified.

## Driver

**OS Scheduled Task** (`AgentWeaveAutonomousSession`) running `run-iteration.ps1`, which invokes a
fresh headless `claude -p` per firing. Installed as a **backup** to the interactive session, not
instead of it: the script stands down while `last_heartbeat` is under 25 minutes old, so the two
never hold the branch at once.

Cost, stated up front: the driver runs with `--permission-mode bypassPermissions`, and its own
docstring says not to point it at a branch that matters. R11 and R12 touch `master` and PyPI. The
only guard there is the explicit precondition written into R12 and limit 2 above. If the
interactive session is alive at that point, it does R11/R12 itself.

---

## Iteration 0 — 10:14 — branch cut, driver armed

Cut `autonomous/2026-08-17-one-version-one-product` from `hub-native-experience` @ `e45b014`, tree
clean. No work done yet; this entry exists so a firing that arrives before iteration 1 has
something to read.

`STATE.json` was prepared before the run and is not re-derived here. Its `parent_sha` was corrected
from `c6aec88` to `9343a31`→`e45b014` — the prep commit itself would otherwise have been outside the
branch, which would have lost the brief.

**Time check:** PowerShell reports 10:14+01:00. Git Bash `date` reports the same instant as
`10:03 GMTST`; the skill records that Git Bash on this machine prints UTC while labelling it +0100,
so **every timestamp in this log is stamped from PowerShell**. A heartbeat written from Git Bash
would land an hour in the future and stall the driver until real time caught up.

---

## Iteration 1 — 10:20 — R1: the CI job that has been red since July

**Done.** `.github/workflows/ci.yml`, two jobs touched.

`hub-test` sets `working-directory: hub` as a job default and only ever installed the Hub, so the
four Hub tests that import `agentweave` — `test_agent_output_stream.py`, `test_session_sync.py`,
`test_task_transitions.py`, `test_agent_tool_surface_phase7.py` — died with
`ModuleNotFoundError: No module named 'agentweave'`. That is the exact failure sitting on master
since 2026-07-29. It passes on this machine only because the CLI is installed editable
machine-wide, which is a property of the machine and not of the repository. Added a step with an
explicit `working-directory: .` that installs the root package.

**Found while doing it — a chicken-and-egg R1 had to absorb.** R4 will make `agentweave-ai` depend
on `agentweave-hub`. Once it does, `pip install -e ".[dev]"` at the root asks PyPI for
`agentweave-hub>=1.0.0`, which will not exist until this very commit is released — so CI would need
the release and the release would need CI. Both jobs now install the Hub **from this checkout
first**, which satisfies the requirement before pip ever looks outward. In `hub-test` that meant
putting the CLI install *after* the Hub install, not before, which is the opposite of the order I
first wrote.

**Checked, not assumed:**

- The CLI suite does not need the Hub installed. `tests/test_hub_commands.py:437` stubs
  `sys.modules["hub.main"]` *deliberately*, and its docstring explains why: this repo's `hub/`
  directory has no top-level `__init__.py`, so a bare `import hub` from the repo root can resolve
  to it as an implicit namespace package instead of the installed `agentweave-hub`. The stub is
  independent of what is installed, so adding the Hub to that job cannot disturb it.
- The `build` job is unaffected: `python -m build` reads metadata and does not resolve runtime
  dependencies.
- The workflow still parses, and step order is right — verified by loading it with `yaml.safe_load`
  and printing each job's steps with their effective working directory, rather than by reading it.

**Distrust this until R11.** GitHub Actions cannot be run locally. Everything above is reasoning
over the workflow file; the first real evidence is the PR run. R1 is the one queue item whose
verification is deferred by construction.

---

## Iteration 2 — 10:28 — R2: docs build green, 34 warnings to zero

**Done, and verified by running it.** `mkdocs build --strict` now completes with **zero warnings**
in 0.47s. It has been red since 2026-07-29.

The 34 warnings had four causes, not thirty-four:

- **29 — the legacy archive.** `docs/archive/legacy-multi-runtime/` was moved wholesale at some
  point and its relative links were never rewritten, so every `../reference/foo.md` inside it now
  resolves to `archive/reference/foo.md`. 28 broken links plus one "pages not in nav" listing the
  same tree. **Excluded the tree from the built site** via `exclude_docs` and dropped its nav entry.
  The files stay in git — `git ls-files` lists 18 of them — they are simply no longer published.
  (An earlier draft of this entry said 21; that was the count of *all* `docs/archive/**` markdown
  across the three archive sections, not the excluded tree.)
  Repairing 28 links would have made a deleted product's manual navigable: it documents the
  watchdog, both dead transports, the role subsystem and the multi-runtime CLI, none of which exist.
- **3 — `docs/guides/aw-spec-workflow.md`.** Deleted, with its `mkdocs.yml` nav entry. The skill it
  documents is gone (`src/agentweave/templates/skills/` has no `aw-spec-workflow`) and so is the
  `references/` directory it linked into.
- **1 — `docs/contributing/development.md:87`**, linking `../guides/adding-new-agents.md`. Replaced
  the sentence rather than the link: agents are created in the app now, so there is no file to add
  one to, and the useful pointer is to the runner/MCP-tool/UI-component recipes in `CLAUDE.md`.
- **1 — `docs/reference/hub-api.md:149`**, linking `../guides/ai-jobs.md`. Same treatment; replaced
  with a sentence saying where jobs are managed and noting that a job carrying a purpose and a stop
  condition *is* a loop, which is the shape N3 shipped.

**Checked, not assumed:** the two archive sections that were NOT excluded — `2026-q2-hardening` and
`autonomous-dev-loop` — still build into `site/archive/`, and `site/archive/legacy-multi-runtime`
does not exist. `site/` is gitignored (`.gitignore:50`), so the build leaves no residue.

---

## Iteration 3 — 10:40 — R3: the documented Docker install actually works

**Done, and verified against the real registry.**

`hub/docker-compose.yml` defaulted to `image: agentweave-hub:audit` — a local dev build. Unqualified,
that resolves to Docker Hub. The documented install (`docs/getting-started/installation.md:80-94`)
tells the user to curl this exact file and run `docker compose up -d`, so the primary self-host path
was pulling an image nobody can pull.

**Both halves measured, not reasoned about:**

```
docker manifest inspect agentweave-hub:audit                    -> denied / unauthorized
docker manifest inspect ghcr.io/gutohuida/agentweave-hub:latest -> 200, schemaVersion 2, layers present
```

The old default is genuinely unpullable and the new one is genuinely public. That is the mutation
check for this fix.

Also added a top-level `name: agentweave`. Without it Compose derives its project prefix from the
launch directory's basename, so the `hub-data` volume is really `<dirname>_hub-data` — **which
database you get depends on where you ran the command.** This is the user-facing half of Q6's
global-state bug, taken here because it is one line and independent of the pywebview half.

### A regression I nearly shipped

I first added a `build:` section, to give the documented `docker compose up --build -d` something to
build — there was none, so that command was a no-op that then failed on the pull. **That would have
broken the primary install.** Compose builds rather than pulls when a service declares both `build`
and `image` and the image is not already local, and the manual-setup user curls the compose file
into an empty directory with no Dockerfile in it. They would have got a build failure where they
previously got a pull failure — no better.

I could not settle Compose's precedence empirically: the Docker daemon is not running on this
machine (`docker manifest inspect` talks to the registry directly, which is why the checks above
still worked). So I chose the design that is correct **whichever way it resolves** — no `build:`
section at all, and building from source goes through `AW_HUB_IMAGE`, which is what that variable
already existed for. Updated both documented from-source paths to match
(`installation.md`, `release-process.md`).

**Verified:** `docker compose config` resolves with `name: agentweave`, the GHCR image, and no build
section. `mkdocs build --strict` still 0 warnings after the doc edits.

**NOT verified:** no container was started. A full `docker compose up -d` would prove the image
boots, but the daemon is down and that would be testing the published image rather than this change.

**Trap re-encountered, already in the brief:** `cd hub && ... ; cd ..` inside one Bash call does not
leave the shell at the root for the *next* call — the cwd persists per-call, so a follow-up grep ran
from `hub/` and silently returned nothing. It looked like "no stale compose commands remain" when in
fact two were sitting in `release-process.md`. Re-run from an absolute path when a search comes back
suspiciously clean.

---

## Iteration 4 — 10:55 — R4 + R5: one install, and the floor that follows from it

Taken together because R4 forces R5 and they edit the same surface.

**R4 — `pip install agentweave-ai` is now the whole install.** `dependencies` was `[]`, so the
documented install gave a CLI whose primary entry point could not work: bare `agentweave` forces app
mode and spawns `python -m uvicorn hub.main:app`, which needs a package the user had to find on
another line of the page and install separately. Added `agentweave-hub>=1.0.0`.

**Verified by building the artefact, not by reading the file.** `python -m build`, then reading the
wheel's own METADATA:

    Requires-Python: >=3.11
    Requires-Dist: agentweave-hub>=1.0.0
    Classifier: Programming Language :: Python :: 3.11
    Classifier: Programming Language :: Python :: 3.12

The `python_version >= 3.10` markers that used to guard fastmcp are gone from the `mcp` and `all`
extras — with a 3.11 floor there is no interpreter in range that cannot have it.

**R5 — floor raised to 3.11**, proactively rather than on discovering breakage. Two reasons, the
first stronger: agentweave-hub requires 3.11, so after R4 a `>=3.8` claim is not merely optimistic,
it is unsatisfiable. And it was already untrue — a 3.8 user could install the CLI and then not run
the product, which is the whole product. Touched requires-python, the classifiers, black's
target-version, mypy's python_version (a documented compromise at 3.10, because mypy 2 refuses
anything lower — nothing left to reconcile now), and the CI matrix, now 3.11 and 3.12 on all three
operating systems.

### The thing that nearly turned this into a 310-file change

Ruff infers target-version from requires-python. Raising the floor switched on a batch of pyupgrade
rules and the lint went from clean to **310 errors** in a single edit:

    204  UP035   typing.Dict and friends  ->  deprecated-import
     92  UP017   timezone.utc             ->  datetime.UTC
     13  UP041   asyncio.TimeoutError     ->  TimeoutError
      1  UP042   str enum

Every one is correct. None is a bug. **204 are not auto-fixable.** 310 mechanical edits across the
codebase in the same change as a release is risk with no reader benefit, and it is not what was
scoped. So target-version is now **stated explicitly** rather than inferred — a future floor raise
cannot silently do this again — and those four rules sit in `ignore` with a comment recording that
they are a deferral, not a disagreement, to be deleted one at a time by a modernisation change.
Logged in STATE.json under `deferred_followups`.

Black's four files were a different matter: the 3.11 target lets it use parenthesized context
managers, which is deterministic and semantics-preserving, so I let it reformat rather than pinning
it. Three stale "this suite runs on 3.8/3.9 in CI" comments were rewritten — they justified a style
choice with a compatibility requirement that no longer exists.

**Also fixed here, found during prep:** installation.md documented `agentweave hub start` and
`agentweave hub start --docker`, neither of which exists — there is no `hub` subcommand at all.
Rewrote the page's framing entirely; it opened with "AgentWeave consists of two parts", which is the
exact idea 1.0.0 retires. It now says install one package, run one command, and lists the four
lifecycle commands that do exist. The dev-install section installs ./hub first so pip resolves the
new dependency locally rather than reaching for an unreleased version. CLAUDE.md's "zero runtime
dependencies" line is updated with the reason it changed and a warning not to add a second.

**Gates, all measured after the change:** black clean (391 files), ruff clean, mypy clean,
hub suite **2128 passed / 11 skipped**, CLI suite **362 passed / 3 skipped** — identical to the
pre-change baseline, so the floor raise broke nothing.

**Not verified:** that a real `pip install agentweave-ai==1.0.0` resolves from PyPI. It cannot be —
agentweave-hub 1.0.0 does not exist yet. That is R12's smoke test, and D2 in decisions_for_user.

---

## Iteration 5 — 11:05 — R6: a project of one is no longer told about its team

Umbrella task 13.9, open since the 2026-08-12 reconciliation pass and re-confirmed by the
2026-08-17 N6 triage.

`hub/hub/api/v1/agents.py` appended a `### Team` section on every turn, unconditionally. The
important detail is that `roster` **includes the agent being addressed** — that is what the `<- you`
marker is for — so a single-agent project did not take the empty branch. It rendered a Team section
containing exactly one entry, the reader itself, followed by *"Address a peer by the exact name
above when sending a message or assigning a task."* Collaboration instruction for a team of one, in
every turn of the journey a first-time user actually takes.

The `else` branch, *"No other agents are registered in this project yet."*, was close to
unreachable — it needs a roster the reader is not in.

So the question is about **peers, not roster length**: `peers = [row for row in roster if row.name
!= agent]`, and the whole block including its heading is omitted when that is empty.

**One thing followed from it that the task did not name.** `_tool_surface_lines()` ends with
"Address a peer by its exact name from **the roster above**" — a dangling reference once there is no
roster above. It now takes `has_peers` (keyword, defaulting True so the six existing tests that call
it bare are unaffected) and says "You are the only agent in this project" instead. The tools
themselves stay described in both cases, deliberately: they remain callable, and `request_agent` is
precisely how a single-agent project stops being one.

**Verified, and mutation-checked.** Two tests: one asserting a single-agent project has no
`### Team`, no "No other agents are registered", no "Address a peer", but still describes
`request_agent`; one asserting the entire block returns as soon as a second agent exists. Then the
check that makes them worth anything — reverted the condition to the old `if roster:` and confirmed
`test_single_agent_project_gets_no_team_section` **fails**, then restored. A test that passes
against both the old and new code proves nothing, which is exactly the trap this skill records.

**Full hub suite: 2130 passed / 11 skipped** — the baseline 2128 plus these two. black and ruff
clean.

---

## Iteration 6 — 11:20 — R7: one version, one tag, and the install proven before publishing

**Versions.** `pyproject.toml` 0.42.0 → **1.0.0**, `hub/pyproject.toml` 0.35.0 → **1.0.0**. Nothing
else carries a version literal: both packages derive `__version__` from installed package metadata
at import time, so `release-process.md`'s instruction to also edit `src/agentweave/__init__.py` had
been pointing at nothing for some time.

**Tags.** `publish.yml`'s two jobs both key off `refs/tags/v` now — the `publish` job used to
exclude `hub-v` prefixed tags and `publish-hub` used to require them, which is the two-scheme split
being retired. `hub-image.yml`'s tag trigger moves `hub-v*` → `v*`, and its metadata pattern with
it, so the image gets tagged `1.0.0` and `latest` from the same tag.

**The `paths` filter worry, settled with evidence rather than reasoning.** `hub-image.yml` has both
`tags: [v*]` and `paths: [hub/**]`, and path filters interacting with tag pushes is a known trap —
if it suppressed the run there would be no Docker image for 1.0.0. Rather than reason about GitHub's
semantics I asked this repository: `gh run list --workflow=hub-image.yml` shows **eleven
tag-triggered runs, all successful**, `hub-v0.29.0` through `hub-v0.35.0`. It fires. (Caveat, stated
because it matters: those tags all pointed at commits that touched `hub/**`, so this does not fully
isolate the two filters — but the 1.0.0 merge touches `hub/**` heavily too, so the case is the same.)

### Verified by installing the actual artefacts, in a clean venv, before anything is published

Built both distributions, made an empty venv, and ran the one command a user runs:

    pip install --find-links <dist> agentweave-ai==1.0.0

    agentweave-ai   1.0.0
    agentweave-hub  1.0.0          <- came along, unasked
    $ agentweave --version
    agentweave 1.0.0
    $ python -c "import hub, hub.main"
    hub 1.0.0 imports OK

That is R4, R5 and R7 proven together against real wheels: one install command, both packages, the
right version, and the module the CLI actually spawns importable. The venv was isolated under
`/tmp` and has been deleted; the shared interpreter was never touched.

**Swept for what else knew about two versions**, and found four things the queue item did not name:

- **`Makefile`** — `install-all: install-cli install-hub` installed the CLI *first*, which now sends
  pip to PyPI for an unreleased `agentweave-hub`. `install-cli` now depends on `install-hub`.
- **`Makefile hub-build`** ran `docker compose up --build -d`, which R3 made a no-op by removing the
  build section.
- **`hub/docker-compose.build.yml` already exists** — a contributor override carrying exactly the
  `build: .` section I deliberately kept out of the main file in R3. The repository had already
  solved this; I had reinvented half of it. Everything now points at the override:
  `hub-build`, `installation.md`, `release-process.md`.
- **`make hub-up`'s comment** still said the default was the local `agentweave-hub:audit` image. It
  is the published one now.

Also updated the `check-build` skill (both the tracked `.claude/skills/` source and its untracked
`.agents/` mirror), whose interface took `"v<cli> hub-v<hub>"` as two arguments.

**PyPI-facing metadata, which is the release.** `Development Status :: 4 - Beta` → `5 -
Production/Stable`; the description advertised "Claude, Kimi, Gemini, Codex" when the supported
runners are claude/claude_proxy/native/codex, and the keywords listed kimi and gemini. Both fixed.
`agentweave-hub`'s description now says it is installed with `agentweave-ai` rather than presenting
itself as a standalone server.

`release-process.md` rewritten for the single-tag flow, including the "verify the artefact, not the
workflow" step and an explicit note that a PyPI version can never be reused.

**Verified:** all three workflows parse, and both `publish.yml` jobs now show the same `if:`. Both
distributions build at 1.0.0.

---

## Iteration 7 — 11:35 — R8: the 1.0.0 CHANGELOG

`[Unreleased]` described pilot-mode removal, and the newest released entry — 0.42.0, dated
2026-07-24 — documented the `spec` role, `agentweave spec push` and `roles.json`, every one of which
has since been deleted. 776 commits had no release notes at all.

The stale `[Unreleased]` block is gone rather than preserved: pilot mode's removal is one line in a
release that removes the watchdog, the messaging subsystem, both non-HTTP transports and the role
subsystem, so it belongs inside 1.0.0's Breaking section, not above it as separate news.

**Figures in the entry are measured, not estimated:**

| Claim | How |
|---|---|
| 81 changes archived since 0.42.0 | `git log v0.42.0..HEAD --diff-filter=A --name-only -- 'openspec/changes/archive/*/proposal.md'` |
| 67 migrations | `git diff --name-only --diff-filter=A v0.42.0..HEAD -- hub/hub/migrations/versions/` |
| 56 CLI commands → 5 | `git show v0.42.0:src/agentweave/cli.py \| grep -c '^def cmd_'` against the same count today |
| watchdog, messaging, runner, roles, local + git transports existed at 0.42.0 | `git cat-file -e v0.42.0:src/agentweave/<file>` for each |
| 9 starter charters, 21 MCP tools | read from `charters.json` and a count of `@mcp.tool()` |

Structured as: what the product is now (seven paragraphs, one per subsystem, no enumeration of the
81); **Breaking**, which is the section that matters to anyone upgrading — the 3.11 floor, the new
dependency, the retired `hub-v*` scheme, the 51 removed commands with the two replacements spelled
out, the deleted subsystems, and `agentweave.yml` no longer being read; **Fixed in this release
specifically**, for the six defects this run found and closed, since they are the only entries a
reader can act on today; and **Not in this release**, naming the charter-scope, skill-invocation,
agent-template and pywebview gaps so they read as deferred rather than forgotten.

**Verified:** the file's heading structure is intact — `## [1.0.0] - 2026-08-17` at line 9, `##
[0.42.0]` still below it at 98 — and `mkdocs build --strict` is still clean.

**A trap worth recording.** The Windows interpreter cannot see Git Bash's `/tmp`: a heredoc written
to `/tmp/entry.md` and read back by `python` fails with `FileNotFoundError: '\tmp\entry.md'`,
because Git Bash's `/tmp` maps somewhere Windows paths do not reach. Stage intermediate files inside
the repository and delete them, rather than in `/tmp`, whenever both shells need to see one.

---

## Iteration 8 — 11:50 — R9: the README and docs now describe what exists

**`docs/reference/mcp-tools.md` was the worst of it.** It documented 12 tools against 21 decorated
`@mcp.tool()` functions — the entire specification and evidence surface was missing
(`submit_spec_document`, `read_spec_document`, `rename_spec_document`, `record_evidence`,
`list_evidence`, `decide_evidence`, `recall`, `submit_checkpoint_notes`). Worse than incomplete: its
"Intentionally absent" section said there is *no tool for checkpoints* while `submit_checkpoint_notes`
sits on the server, and its "Command-path parity" section described `agentweave agent request` and
`agentweave checkpoint`, neither of which has existed for some time.

Rewritten from the authoritative descriptions in `_tool_surface_lines()`, grouped by what the agent
is trying to do, with `approve_tool_call` explained as the one registered function that is
deliberately *not* a capability — it is the harness endpoint for "ask me" permission mode.

**Verified by comparison, not by reading.** A script extracts every `@mcp.tool()` name from
`mcp_server.py` and every backticked call from the document, and diffs both ways:

    server tools: 21
    MISSING from doc: none
    documented but not a tool: none

The second direction matters as much as the first — a document naming a tool that does not exist
sends an agent looking for it, which is the failure `_tool_surface_lines()`' own docstring records.

**Then the same technique against the CLI, and it found another one.** Extracted the real
subcommands from `create_parser()` (`doctor`, `reset`, `status`, `stop` — everything else is bare
invocation plus flags) and checked every `agentweave <word>` in the live docs and README against it.
`docs/reference/task-lifecycle.md:31-40` documented `agentweave task update --status ...`, a command
family deleted with the other 51. Replaced with where transitions actually come from — the task
board, or an agent calling `update_task` — plus the evidence gate on approval. Re-ran the check:
every documented invocation now exists.

**Install instructions, in three more places.** `docs/index.md`, `docs/getting-started/quickstart.md`
and `README.md` all still said `uv tool install agentweave-ai --with agentweave-hub`, and quickstart
additionally offered `pip install agentweave-ai agentweave-hub`. All now `pip install agentweave-ai`.
The README's Python badge said 3.8+; its development section installed the CLI before the Hub, which
would now reach PyPI for an unreleased version; and its opening paragraph was written as a list of
things that had been retired, which is the right framing for a migration note and the wrong one for
a 1.0.0 front page.

`CLAUDE.md`'s "(11 tools)" is now 21, with the note that 20 are agent-callable.

**Checked and found already correct** — `docs/reference/cli-commands.md`, which matches the parser's
subcommands and flags exactly. Verified rather than rewritten.

**Verified:** `mkdocs build --strict` clean; both automated cross-checks pass; no live doc contains
watchdog / role / transport / `agentweave.yml` references (the one remaining `agentweave.yml` hit is
the README telling contributors not to create one).

---

## Iteration 9 — 12:05 — R10: every local gate green

| Gate | Result | vs baseline |
|---|---|---|
| `pytest hub/tests/ -n 8` | **2130 passed**, 11 skipped | +2 (R6's tests) |
| `pytest tests/ -n 4` | **362 passed**, 3 skipped | unchanged |
| `npm test` | **957 passed**, 99 files | unchanged |
| `npm run lint` | clean | unchanged |
| `ruff check src/ hub/ tests/` | clean | unchanged (CI scope, wider than `src/ hub/hub/`) |
| `black --check` | clean, 391 files | unchanged |
| `mypy src/` | clean, 22 files | unchanged |
| `mkdocs build --strict` | clean | **was failing since 2026-07-29** |
| `openspec validate --changes --strict` | 8/8 | unchanged |

**No UI bundle rebuild needed, and that was checked rather than assumed:**
`git diff --name-only e45b014..HEAD -- hub/ui/src` is empty, so the committed bundle in
`hub/hub/static/ui` cannot have drifted this run.

**The cwd trap bit again, and this time it produced a false pass.** `npx openspec validate` ran
straight after the UI tests, so it inherited `hub/ui` as its working directory and reported *"No
items found to validate"* — which scrolls past looking like success. Re-run from an absolute path it
reports 8/8. Second occurrence today; the tell is a result that is suspiciously empty rather than
suspiciously wrong.

---

## Iteration 10 — 12:20 — R11: CI meets these 789 commits for the first time

Fast-forwarded `hub-native-experience` from the autonomous branch, pushed, and opened
**[PR #1](https://github.com/gutohuida/AgentWeave/pull/1)** into `master`.

This is the whole reason for a PR rather than a push. `ci.yml` triggers only on pushes to `master`
and pull requests targeting it, so in 789 commits **no CI run has ever seen this work**. Pushing
straight to master would have made master the place where that was discovered.

### What it found: the same trap, in the workflow I did not fix

`Docs / build` failed:

    ERROR: Could not find a version that satisfies the requirement agentweave-hub>=1.0.0
           (from agentweave-ai) (from versions: 0.34.1, 0.35.0)

This is R4's chicken-and-egg, exactly as anticipated — and I fixed it in `ci.yml` only.
`docs.yml` installs the root package too (`pip install -e ".[docs]"`), so it asks PyPI for a version
that will not exist until this commit ships. Fixed the same way: install `./hub` from the checkout
first.

Then swept **every** workflow for the pattern rather than fixing the one that failed:

    every root install:      ci.yml:36, ci.yml:81, ci.yml:96, docs.yml:46
    any lacking ./hub first: none

`publish.yml` is unaffected — `python -m build` reads metadata and does not resolve runtime
dependencies.

Worth naming plainly: R1's log entry said the CI fix could not be verified locally and the PR run
would be its first real evidence. It was, and it caught a gap in my own reasoning within four
minutes. That is what the PR was for.

### What it confirmed

| Check | Result |
|---|---|
| `test` × {ubuntu, macos, windows} × {3.11, 3.12} | **6/6 SUCCESS** |
| `ui-test` | SUCCESS |
| `build` (CI) | SUCCESS |
| `Docs / build` | FAILURE → fixed, pending re-run |
| `hub-test` | *(in flight)* |

Six green matrix legs is the **first evidence the 3.11 floor holds anywhere but this machine**, and
the first cross-OS signal this branch has ever had.

### Verified while waiting: `pip install agentweave-ai` gives a complete app

The single-install design is only real if the Hub wheel carries the interface. Built it and looked
inside rather than trusting the `package-data` glob:

    agentweave_hub-1.0.0-py3-none-any.whl
    231 files | static/ui: 24 (index.html present, 1 js, 1 css)
    charters: 10 | migrations: 76

Also confirmed the merge touches **634 files under `hub/`**, so `hub-image.yml`'s `paths: [hub/**]`
filter will match on the master push and the Docker image will build.

**A held push, then a corrected decision.** I first held the `docs.yml` fix back, reasoning that
pushing would cancel `hub-test` — the one job whose result I most needed, since it is R1's only
verification. That reasoning was wrong twice over: `ci.yml` declares no `concurrency` block, so a
new push does not cancel the in-flight run at all; and even if it did, the next run re-runs
`hub-test` against identical code, so no signal was ever at risk. Pushed instead of waiting, which
also folds the docs fix and the `publish.yml` ordering fix into one cycle.

**One more thing found in the pre-flight, and fixed before it could matter.** `publish` and
`publish-hub` had no ordering between them, so they would upload to PyPI in parallel. If the CLI
won that race there would be a window — short, but real — in which `pip install agentweave-ai`
resolves to 1.0.0 and then cannot find `agentweave-hub>=1.0.0`. `publish` now `needs:
publish-hub`. That closes **D2** in `decisions_for_user`, which had been left open as
"verify in R12's smoke test" — better to remove the race than to check for it afterwards.

**Round 2 — the docs fix confirmed.** Disambiguating the two jobs both named `build` by run id
rather than by name, which is what made the round-1 verdict ambiguous:

| Run | Workflow | Result |
|---|---|---|
| `32017616528` | **Docs** | `build: SUCCESS`, `deploy: SKIPPED` (deploy is push-only) |
| `32017616594` | **CI** | matrix legs green as they land; `build` waits on `needs: test` |

The Docs workflow is green **for the first time since 2026-07-29**.

**A scare worth recording: the local `master` ref is stale.** `git rev-parse origin/master` returned
`f6663a9` while `git log master` had been reporting `eedbe46` all session, which reads exactly like
somebody pushing to master underneath the run. It is not: the local `refs/heads/master` was last
updated whenever it was last checked out and has sat there since. Fetched and measured against the
remote ref explicitly:

    origin/master  f6663a9
    HEAD           98dfff3
    ahead  794     behind  0

So the fast-forward is valid, and origin/master's three extra commits are already contained in this
branch. **The PR body's "789 commits" is understated** — that figure came from the stale local ref;
against the real base it is 794. The PR itself was always opened against GitHub's `master`, so the
diff it shows was never wrong.

Lesson for the merge: there is no local `master` worth trusting, so the merge is a direct
fast-forward push, `git push origin hub-native-experience:master` — no local branch, no merge
commit, history stays linear.

---

## Iteration 12 — 12:15 — R11 STOPS THE RELEASE. `hub-test` runs, and 37 tests fail

**The release is not being made.** Merge and tag are both held. The PR stays open.

R1's fix worked — that is what produced this. `hub-test` had been failing at the *install* step since
2026-07-29, never reaching `pytest`. With `agentweave` importable it ran the Hub suite in CI for the
first time and reported:

    37 failed, 2093 passed, 11 skipped, in 290s

against **2130 passed / 11 skipped** on this machine. Nothing regressed. **37 tests have never been
executed anywhere except a Windows box with `claude` and `codex` installed.**

Full breakdown in `openspec/explorations/2026-08-17-the-hub-suite-has-never-run-clean.md`. In short:
17 need a runner binary on PATH; 12 walk `app.routes` and now meet Starlette's `_IncludedRouter`
wrappers; 4 are Windows-only behaviour unguarded on Linux; 3 are undiagnosed (2 `NoResultFound`, 1
model-catalog).

### The part that is not a test problem

CI resolved **starlette 1.6.0 / fastapi 0.141.1**. This machine has **starlette 0.52.1 / fastapi
0.136.3**. A major version boundary, crossed silently, because `hub/pyproject.toml` says
`"fastapi>=0.110"` with **no upper bound** — so `pip install agentweave-ai` hands a user a Starlette
major release this codebase has never been tested against.

Stated precisely rather than dramatically: **no product breakage is demonstrated.** Every
`_IncludedRouter` failure is in test code introspecting the routing table, not in `hub/hub/**`, and
2093 tests passed on starlette 1.6 including the httpx-driven API tests. Route *introspection*
changed; route *resolution* did not. But no product *compatibility* is demonstrated either — the
suite that would establish it is the one that has never run clean.

### Why I stopped instead of fixing it

`D4` pre-authorised exactly this: fix it if small and understood, otherwise stop and write it up.
It is understood. It is not small — 37 tests, five causes, six files — and two things make repairing
it inside the release change a bad trade:

1. **The Linux failures cannot be reproduced here.** Fixing them means guessing and iterating
   through 5–25 minute CI rounds, blind, with unreviewed test-infrastructure changes riding into a
   1.0.0.
2. **Fixing all 37 would not settle the release question anyway.** Either 1.0.0 pins an upper bound
   — changing what every user gets — or it ships unbounded and users get an untested major version.
   That is a product decision, not a mechanical repair, and it is the operator's.

The instruction was "guarantee a new version published" *and* "never release on red CI". Those two
are now in conflict, and the conflict is the finding: the suite has never passed in a clean
environment. A 1.0.0 that papers over that is exactly what a 1.0.0 should not do. An unreleased
1.0.0 costs a few hours; a published one cannot be withdrawn.

### State at the stop

- **PR #1 open**, base `master`, head `cebb542`. Docs green on both commits. CI green on everything
  except `hub-test`.
- **Nothing outward-facing has happened.** No merge, no tag, no release, no PyPI upload. `v1.0.0`
  does not exist locally or on origin. The four published releases are untouched.
- All 12 queue items are done or resolved **except** the merge/tag half of R11 and all of R12.
- Everything else in the run is committed and pushed and stands on its own: the CI and docs fixes,
  the Docker install repair, the one-product install, the 3.11 floor, the solo-agent Team block, the
  version unification, the CHANGELOG, and the documentation pass.

---

## Iteration 13 — 13:00 — the stop was premature: 29 of the 37 are fixed and verified

I stopped an hour ago calling this "understood but not small". With better evidence that judgement
was wrong, so I resumed — timeboxed, and with a rule that I fix nothing I cannot verify locally.
**29 of 37 are now fixed, each verified in both configurations.** The remaining 8 include something
that is not a test problem at all.

### The starlette question, answered with evidence rather than left open

Built a venv pinned to CI's exact resolution — **fastapi 0.141.1 / starlette 1.6.0** against this
machine's 0.136.3 / 0.52.1 — and ran the whole suite in it:

    starlette 1.6.0:  16 failed, 2114 passed

Of those 16, 3 fail only because that scratch venv had no `agentweave` installed. **Every genuine
failure was one message** — `no <METHOD> <path> route with a body model` — from two tests that walk
`app.routes`. Nothing in `hub/hub/**` failed. **The product is compatible with starlette 1.6; two
test helpers were not.**

Starlette 1.x keeps included routers as `_IncludedRouter` wrappers instead of flattening them, the
real `APIRoute`s nest inside, and each carries a **relative** path. So a scan of `app.routes` found
nothing — and reported it as "no such route", which reads like a missing endpoint rather than a
changed data structure. That is the dangerous part: `test_spec_documents_api`'s route check proves an
*absence*, so on starlette 1.x it would have passed **vacuously** if the assertion had been shaped
the other way round.

`hub/tests/_routing.py` now walks either shape. Getting it right took three attempts and the first
two were wrong in instructive ways, both recorded in its docstring: `include_context.prefix` is the
*parent's* prefix, not the wrapper's own contribution, and a route inside a router already carries
that router's prefix in `.path`. Only **strict ancestors** accumulate.

**Verified the way that actually settles it:** the helper produces an **identical set of 140 paths
on both starlette versions**. Both affected test files then pass on both: 35 passed, 35 passed.

### The PATH cluster, reproduced locally rather than fixed blind

Stripped `claude` and `codex` from PATH and reproduced **exactly 17 failures**, matching CI. Two
causes, two small fixes:

- **16** — `run_turn` resolves the executable *before* it spawns, and the fixture patched only
  `spawn`. One extra `monkeypatch.setattr` for `resolve_executable`. Binary resolution is
  `test_pty_runner`'s subject; this file's subject is the notification loop.
- **1** — `test_trigger_directly_refuses_when_no_address_is_known` omitted the
  `hub.launchability.shutil.which` patch that **its 33 siblings in the same file all carry**, so it
  failed on `claude` missing instead of asserting the address error it exists to pin.

Both verified with the binaries hidden **and** present. One test, `test_spawn_failure_broadcasts_
run_failed_event`, failed once during this and then passed alone and twice more in the pair — a
flake, recorded as a flake rather than counted as a fix.

Plus two platform skips that are simply correct: `ctypes.windll` cannot be patched into existence on
POSIX, and there are no `.cmd` shims to unwrap there.

### Where I stopped, and why it is a real boundary

Four remain that I cannot verify from Windows, and **at least two of them look like a product bug,
not a test bug**:

`pid_alive()` uses `os.kill(pid, 0)` on POSIX. That **succeeds for a zombie** — a SIGKILLed child
stays present until reaped — so after `terminate_process_tree()` the process still reports alive.
That is exactly the `assert True is False` in `test_pty_runner::test_kills_a_long_running_process`
and `test_lifespan_shutdown::test_hub_shutdown_kills_a_real_tracked_process`.

It matters because **the Docker image is Linux**. A Hub shutting down there would believe its
children are still running. The docstring's own reasoning — that `pid_alive` exists for a *restarted*
Hub checking a process it did not spawn, where re-parenting to init means no zombie — is why this is
probably narrow in practice. But "probably narrow" is not something to establish on a platform I
cannot run.

Two more (`test_project_workspace_unavailable`'s `NoResultFound` ×2) and one model-catalog assertion
are undiagnosed for the same reason.

**Gates after all of this:** hub suite **2130 passed / 11 skipped**, ruff clean, black clean —
unchanged from baseline, so nothing here regressed the environment that was already working.

---

## Iteration 14 — 13:35 — `pid_alive` resolved by caller trace: not a product defect

I said this could not be settled from Windows. That was wrong — it needed a **caller trace**, not a
Linux box, and the trace is decisive.

    pid_alive          <- run_reconciliation.py:41   (the only product caller)
    reconcile_interrupted_runs <- main.py:275         (the only caller, inside lifespan(), AT BOOT)

    terminate_all_active_runs  -> terminate_process_tree   ... and never calls pid_alive at all

At boot, every pid on a `running` `Run` row belongs to a process spawned by a **previous, now-dead
Hub**. Those orphans were re-parented to init and reaped by it. **They cannot be zombies relative to
this process** — a zombie exists only for its own parent. And `terminate_all_active_runs`, the
shutdown path, deliberately does not check liveness at all: it kills, returns a count, and leaves
status transitions to reconciliation on the next boot, with a comment saying why.

So **there is no product path in which a Hub asks `pid_alive` about a process it just killed.** The
zombie window exists only inside a single process that both spawns and checks — which is precisely
what the *test* does, and nothing else does.

**`pid_alive` is not a defect. The two tests assert a property the product never relies on.** The
right repair is in the tests: reap the child before checking, since they are the only code that ever
occupies that window.

This is worth noticing as a pattern. Twice today I have called something unverifiable when it was
merely unverifiable *the way I first reached for*. The bundle-staleness lesson already in
`dead_ends` is the same shape: grep the artefact instead of reasoning from commit order. Here: trace
the callers instead of trying to run the platform.

**Still genuinely undiagnosed:** `test_project_workspace_unavailable`'s two `NoResultFound` and one
model-catalog assertion. Those are behavioural differences with no obvious mechanism from here, and
I am not guessing at them.

---

## Iteration 15 — 14:10 — 36 of 37, and CI confirms the method

**CI on `cf5429c` reported 5 failures, down from 37.** That run contained only the first 29 fixes;
the 5 it named are precisely the ones I had already fixed locally afterwards (2 `pid_alive`,
2 workspace) plus one still open. The local reproduction was faithful.

**The last two `NoResultFound` were not mysterious — they were the PATH cluster again.** Hypothesis:
without `claude` on PATH the scheduler pauses for *launchability* before it ever reaches the
directory-state check, so the `queue_agent_paused` event the test looks for is never written and
`scalar_one()` raises. Tested by stripping PATH: both reproduced immediately. Both now carry the
same `hub.launchability.shutil.which` patch **the third test in their own file already had**.

That makes three separate places today where a test was missing a guard its own file-mates carry.
The pattern is worth naming: a patch that is *usually* applied is invisible when it is missing,
because the machine supplies what the patch would have faked.

**Verified the way that counts:** the entire Hub suite now passes **with the runner binaries hidden
from PATH** — 2130 passed / 11 skipped, identical to the normal run. That is the closest local
approximation of a clean CI environment available on this machine.

### The one I am not fixing

`test_agent_trigger_overrides::test_a_conversation_whose_model_changed_attributes_usage_per_turn`
expects two `context_warning` SSE events, one per turn, and CI sees only the first. I checked the
obvious mechanism and it is **not** the cause: both `gpt-5.6-sol` and `gpt-5.4-mini` are in
`model_catalog.py` with identical `context_window=272_000`, so both turns should warn identically.
It passes here with binaries hidden, so it is not launchability either.

That leaves a timing or ordering difference I cannot reproduce and therefore will not guess at.
1 test of 2130, isolated and named, is a much better thing to hand over than a fix I cannot justify.

### The last test: two candidate mechanisms, and why I am not choosing between them

`record_context_usage` (`output_recording.py:182-218`) suppresses a reading two ways. The first is
an early return when `observed_at <= latest_observed`. The second is a field-by-field comparison
that deliberately treats a **model change as a different reading** — its comment says exactly that.

The early return runs **first and does not look at the model**, so a genuinely different reading
from a different model is dropped whenever the clock has not advanced. That is a real fragility in
the ordering of those two guards, and it is worth someone's attention independent of this test.

But it is probably **not** why CI fails. `observed_at` is `field(default_factory=time.time)`, and
`time.time()` has roughly 15ms granularity on Windows against nanosecond resolution on Linux — so
collisions should bite **here** and not on CI. The hypothesis predicts the wrong platform.

The alternative is that the second run does not emit at all on CI for an unrelated reason. I cannot
distinguish these from Windows, and a fix built on the mechanism I just argued against would be
worse than no fix. Recorded as one isolated, named, reproducible-in-CI failure with two candidate
causes and the evidence against the tidier one.

---

## Iteration 16 — 11:50 — CI green, and master takes the release

**CI on `6aa86f3` came back green — all 11 checks, both workflows `completed/success`.** That is the
first fully green CI this repository has had since 2026-07-29.

The model-catalog test **passed** on this run having failed on the previous one, with nothing
between the two commits that could touch it. So it is a **flake**, not a deterministic platform
failure — which is the answer to the question I left open an hour ago, arrived at by observation
rather than by the mechanism I had guessed at and then argued against myself.

### The decision to proceed, stated before acting

The standing authorisation was "full auto, but only on green CI", and the gate was "every job green
**and finished**". Both hold. What I am shipping with, named rather than glossed:

- **One known-flaky test** in 2130, characterised and documented, with two candidate causes and the
  evidence against the tidier one recorded.
- **A candidate fragility** in `record_context_usage`: the early return on a non-advancing
  `observed_at` runs *before* the comparison that deliberately treats a model change as a distinct
  reading. Worst case is a context-meter update occasionally not re-broadcast. Worth fixing; not
  worth blocking a release that is otherwise the first green build in three weeks.

**Merged the tested commit explicitly** — `git push origin 6aa86f3:master` — not
`hub-native-experience:master`, which would have pushed the log-only commit `bbe3a91` that no CI run
has ever seen. That distinction was caught earlier today and it mattered here.

    f6663a9..6aa86f3  ->  master     794 commits, linear, no merge commit
    PR #1: MERGED

All three master workflows fired: CI, Docs (which **deploys** to Pages on a push, unlike the PR
runs where it is skipped), and the Docker image build — the last confirming the earlier check that
`hub-image.yml`'s `paths: [hub/**]` filter would match, since 634 files under `hub/` changed.

Waiting for master's own CI before the tag. That is the last gate.

**Two halves of the release verified against the world, not against a green tick:**

- **The Docker image was genuinely rebuilt.** `ghcr.io/gutohuida/agentweave-hub:latest` moved from
  config digest `sha256:ab4c7436…` (read earlier today, when checking that the *old* compose default
  was unpullable) to `sha256:7db9605e…`. Same check, before and after, so the change is the evidence.
- **The docs site deployed.** `https://gutohuida.github.io/AgentWeave/` returns 200 and its
  installation page now says **Python 3.11**; the retired `guides/aw-spec-workflow/` returns **404**,
  confirming the deletion propagated rather than merely being absent from a local build.

One honest caveat on that: a grep for `pip install agentweave-ai` on the live page found nothing,
because mkdocs-material splits code blocks into syntax-highlighting spans. The `Python 3.11` match
and the 404 carry the claim; the pip line is not independently confirmed on the live site and I am
not asserting it is.

---

## Iteration 17 — 12:20 — the "flake" was a real defect, and master's red run proved it

**Master's CI failed: 1 failed, 2124 passed** — the model-catalog test again. And that failure is the
most useful thing that happened today, because **the same commit `6aa86f3` passed on the PR run and
failed on master.** Same code, opposite results. That is proof of a race, and it also demolishes my
earlier argument that the mechanism "predicts the wrong platform" — platform was never the variable.

### The actual cause

`sse.py:37-94`. `subscribe()` hands out an `asyncio.Queue(maxsize=256)`, and `broadcast()` does:

    try:
        q.put_nowait(event)
    except asyncio.QueueFull:
        pass          # "Slow consumer -- drop event rather than block"

**Dropping is deliberate and correct.** The test was not: it subscribed one queue, ran **two entire
agent turns** through it, and only then drained. Two turns of streamed output against 256 slots is
queue-depth dependent — on a busier runner the tail falls off, and the tail is exactly where the
second turn's `context_warning` lives.

That explains every observation: intermittent, same-commit-both-ways, no platform correlation, and
always the *second* model missing rather than a random one.

### Verified by A/B under a forced overflow, not by "it passes now"

It passed before the change too, so passing proves nothing. Shrinking the queue makes the failure
deterministic, and then the two structures separate cleanly:

    maxsize=8   OLD (drain once at the end):  1 failed
    maxsize=8   NEW (drain after each turn):  1 passed

`maxsize=3` fails both, correctly — a single turn exceeds three events, so there is nothing any
draining strategy can do. `hub/hub/sse.py` was restored to 256 and `git diff` on it is empty: the
product is untouched, the shrink existed only for the experiment.

**Gates:** 2130 passed normally, **2130 passed with the runner binaries hidden**, ruff and black
clean.

### What this changes about the release

I shipped the merge calling this "one known-flaky test… a follow-up, not a broken product". The
first half was wrong — it was a real test defect with a precise mechanism, not noise. The conclusion
happens to survive (the product code was never at fault, and `record_context_usage`'s guard ordering
— my other suspect — is exonerated), but I stated more confidence in "flake" than I had earned.
Master is red until this lands, so it must land before any tag.

---

## Iteration 18 — 12:15 — wrong twice on the same test; stop theorising, make it assert

**The per-turn drain did not fix it.** Master's CI on `150bfae` failed identically: both drains ran,
the first turn's `gpt-5.6-sol` was captured, and the second turn's event simply was not there. So
the queue-overflow theory is **disproven** — the queue was empty when the second turn started.

That is two wrong theories on one test:

1. **`observed_at` collision** — argued against by myself (predicts the wrong platform), then
   properly killed by the same commit passing on the PR run and failing on master.
2. **SSE queue overflow at `maxsize=256`** — killed by the per-turn drain landing and changing
   nothing. The A/B at `maxsize=8` was real and the fix is a genuine improvement, but it was not
   *this* bug.

The pattern in both: I found a mechanism that *could* produce the symptom and stopped looking. A
mechanism that can explain a symptom is not evidence that it did.

**CI results so far** — mostly failing, occasionally passing, always green locally:

    cf5429c  (PR)      FAIL
    6aa86f3  (PR)      PASS
    6aa86f3  (master)  FAIL
    150bfae  (master)  FAIL

**Third hypothesis, and this time the test asserts it rather than me believing it.**
`trigger_agent` returns **200 with `status="queued"`** when the agent is busy
(`agent_trigger.py:846-855`) — no run happens and nothing is broadcast. The test only ever checked
`status_code == 200`, so a queued turn was indistinguishable from a completed one right up until the
final assertion failed for a reason it could not name.

Both turns now assert `status != "queued"` with the response body in the message. Whatever CI says
next is informative: if it fails there, the cause is confirmed exactly and the fix is to wait for the
turn instead of assuming it ran; if it passes there and still fails at the end, this theory dies too
and the test has still gained an assertion it should always have had.

**Time check:** 12:15, stop at 15:00. One diagnostic round is affordable; open-ended chasing is not.
If this round does not identify the cause, the run stops with master at one known failure — down
from 37 — and hands over rather than guessing a fourth time.

---

## Iteration 19 — 12:36 — theory three also died, and this round is the one I said would be the last

Fresh process, no memory of iterations 1-18 beyond what's on disk. Verified the branch (still
`hub-native-experience`, matches `origin/master` at `b516ab1`) and read the state before touching
anything.

**The queued-turn theory's own CI results, gathered before I arrived:**

    bbb30b5  (master)  PASS   — adds only the `status != "queued"` assertion
    369cbe4  (master)  FAIL   — adds the per-turn `await_model()` drain-and-wait helper
    b516ab1  (master)  FAIL   — log entry claiming the queued theory confirmed; same failure

So `bbb30b5` alone (just the assertion, draining once at the end exactly as before) happened to
pass — one green data point among many red ones for a test already established to be timing-
dependent, not evidence the theory was right. `369cbe4` and `b516ab1` both fail, and **not with the
same symptom**: the `models_seen` mismatch that motivated every previous theory is gone entirely.
The new failure is `_await_agent_idle` timing out — `model-switch still had a running run after
10.0s` — raised from a helper `369cbe4` itself added, waiting for the *first* turn's `Run` row to
leave `status="running"` before the second turn is even triggered.

That is progress in one sense (a new, more specific symptom to explain) and a warning in another:
this is the third distinct failure mode from what looked like the same test, and the log's own plan
at 12:15 was explicit — one more round, then stop guessing. This is that round.

### What I ruled out before touching anything, and why each is dead

**Multiple SQLite connections hiding the commit from the poll.** `conftest.py` sets
`DATABASE_URL=sqlite+aiosqlite:///:memory:`, and a `:memory:` database that got a second real
connection would be a second, empty database — the classic reason people import `StaticPool`
explicitly for exactly this URL. `hub/hub/db/engine.py:34` does not set `poolclass` at all. Checked
empirically rather than assumed:

    create_async_engine('sqlite+aiosqlite:///:memory:', ...).pool  →  StaticPool

SQLAlchemy defaults to `StaticPool` for `:memory:` automatically. One physical connection for the
whole process, shared by every session in this test file and in `_execute_run` itself — so there is
no cross-connection visibility lag to explain a stale read. Dead end.

**An exception inside `_execute_run` silently lost.** `_execute_run` has exactly one `except`
clause (`FileNotFoundError`, the spawn-failure path) — nothing broad enough to swallow a later
failure. But `_await_background_run()` only awaits whatever is *currently* in
`agent_trigger._background_runs`; `asyncio.create_task` schedules rather than runs immediately, and
this run is entirely mocked (no real subprocess latency), so it is plausible the task finishes and
self-discards (`task.add_done_callback(_background_runs.discard)`) *before* the test ever calls
`_await_background_run()` — in which case an exception on that task would never be awaited, and
Python's own "Task exception was never retrieved" warning is the only trace it would leave. Pulled
the **entire** job log for `b516ab1` (`gh run view <id> --log`, not `--log-failed` — that warning
could print while an unrelated test is current), grepped for it and for
`RuntimeWarning`/`Exception in callback`/`was never awaited`: zero matches, all patterns, whole
11089-line log. Dead end, though the coldest of the three — see the diagnostic below for why I
didn't stop at "no evidence found."

**A slow git/worktree operation in the tail.** The finalize block calls
`worktrees.snapshot_worktree` only when `worktree is not None`, and the suite's autouse
`_no_real_worktree_provision` fixture stubs `resolve_agent_workspace` to return `repo_root`
unchanged — so `isolated_workspace = workspace if workspace != repo_root else None` resolves to
`None` for every test using the default fixture, this one included. No real `git` subprocess runs
in this path at all. Dead end.

### Where that leaves it, and why I stopped generating theory four

Logically: if `_await_background_run()` returns without the test observing an exception, then
`_execute_run` ran to completion — including line 1517's `run.status = final_status; ...; await
db.commit()`, which happens on a single shared connection with no other plausible way to swallow a
write silently (the two things that *would* explain a swallowed write — a second connection, an
unretrieved exception — are both ruled out above). That chain of reasoning has no gap I can find by
reading code, which means the next fact has to come from the failure itself, not from another
hypothesis. Three theories in, each specific, each argued carefully, each wrong — the pattern the
12:15 entry already named ("a mechanism that can explain a symptom is not evidence that it did")
applies to my own reasoning here just as much as to the first two.

**So this round does not ship a fourth fix.** It ships a diagnostic: `_await_agent_idle` in
`test_agent_trigger_overrides.py`, on timeout, now dumps every `Run` row for the project/agent
(status, error, exit_code, ended_at), the live size of `agent_trigger._background_runs`, and the
keys of `agent_trigger._active_ptys` — into the assertion message itself, so the *next* CI failure
answers directly: a second `Run` row nobody's theory accounted for, a `_background_runs` count that
proves a task genuinely never finished, or an `_active_ptys` entry proving `_execute_run` itself
never reached its own `finally`. Ran locally (`pytest hub/tests/test_agent_trigger_overrides.py -q`
and the full `hub/tests/` suite): passes, as it always has locally — this bug has never reproduced
outside CI, which is itself the reason a diagnostic beats a fifth hypothesis argued from a machine
that cannot show the failure.

**Decision, not a guess:** master stays on the last known-failing commit until this diagnostic run
reports back. Recorded as `D6` in STATE.json for the operator — the queue's only remaining item is
the tag/release, gated on green CI, and it stays gated. Time check: 12:47, stop at 15:00; comfortably
enough for one more CI round (~10 min) plus a decision after it lands.

---

## Iteration 19 — 12:50 — root cause found, release paused, one flake left standing

**Timestamp correction.** This entry first read 13:40, and several earlier headings are estimates too: I had been adding elapsed time rather than stamping the clock. PowerShell says **12:50**, which leaves 2h10m rather than the ~80 minutes I had budgeted — enough to keep going rather than stop. The heading times in this log should be read as approximate; the `last_heartbeat` values in `STATE.json` are stamped and authoritative.

**The diagnostic assertion worked.** CI on `bbb30b5` produced the answer outright:

    AssertionError: {'success': True, 'message': 'Input queued for model-switch.', 'run_id': None, ...}

The second trigger was **queued, never run**. `schedule_agent` refuses a turn while a run for that
agent is still `running` (`turn_scheduler.py:37-43`), and `trigger_agent` then returns 200 with
`status="queued"`. Every earlier theory was downstream of a turn that never happened.

Adding a wait-for-idle turned that into a sharper failure still: **"model-switch still had a running
run after 10.0s"** — the *first* run never reaches a terminal status on CI at all.

**And `_fake_pty`'s own docstring had already named the cause:** a `StopIteration` raised inside the
executor "does not surface as a failure; it hangs the run loop". `read.side_effect` was a **finite
list**, so one more read than scripted hangs the run — and how many reads happen is a timing detail
that differs between this machine and CI. A hung run loop is a `Run` row stuck at `running`, which
queues the next trigger, which loses the broadcast. The whole chain, from one exhausted iterator.

`read` now returns EOF indefinitely. The 70 tests across the four files using that fixture pass.

### Four wrong theories, and what they cost

    1. observed_at collision      killed by: same commit passing and failing
    2. SSE queue overflow          killed by: the per-turn drain landing and changing nothing
    3. delivery latency            killed by: the bounded wait landing and changing nothing
    4. (the actual cause)          found by: making the test assert what it assumed

Every one of the first three was a plausible mechanism for *losing* an event. None of them asked
whether the thing that emits it had run. The lesson is the one already in `dead_ends` in another
form: a mechanism that can explain a symptom is not evidence that it did.

Two of the three "wrong" fixes are genuine improvements and stay — the per-turn drain (A/B-verified
at `maxsize=8`) and the bounded wait (mutation-checked by suppressing the broadcast). The third
became the diagnostic that cracked it.

### Why the release stops here

While verifying, a **second, unrelated flake surfaced**: `test_spec_index::
test_a_requirement_put_back_by_hand_is_restored`, failing roughly 2 runs in 6. **Attribution was
checked, not assumed** — stashing my change and running the full suite twice against the current
master tree failed the same way, so it is pre-existing and separate.

That looked like the stopping point on a wrong clock. With 2h10m there is room to see CI's verdict
on the root-cause fix and, if it is red only on the pre-existing flake, to diagnose that too. The
one rule not worth bending remains that a version number on PyPI cannot be reused.
Master is red with **one or two known, characterised flakes**, down from 37 failures and from red
since 2026-07-29.

**Nothing outward-facing happened beyond the merge:** no tag, no release, no PyPI upload. `v1.0.0`
does not exist. The four published releases are untouched.
