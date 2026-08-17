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
