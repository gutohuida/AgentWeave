# Autonomous run — Archive, the Hub app, and what's next

**Branch:** `autonomous/2026-08-17-archive-and-hub-app` from `master` @ `5e63004`
**Window:** 19:35 → 22:00, 2026-08-17
**Driver:** Windows Scheduled Task running headless `claude -p`, one iteration per firing.

Newest entry at the bottom.

---

## 19:35 — Set up, by the interactive session

The operator left at ~19:08 asking for a run to 22:00 with four objectives, in order: push a
version with the session's changes, implement the Archive change, work on the Hub app, and if time
allows draft a roadmap.

**Objective 1 was done here, on `master`, not handed to the loop.** Two reasons, and the second is
the important one:

1. It is outward-facing and irreversible — a PyPI publish cannot be taken back — and this skill's
   own limits forbid exactly that unattended. The operator's instruction overrode the limit, but
   the safer reading of "be careful" is to keep the irreversible step attended rather than to hand
   a release to a headless process.
2. It needed the context. The five pieces of work in 1.0.1 were built over the afternoon with the
   operator; the commit messages explaining *why* each exists could not have been written from the
   diff alone.

What landed on master, four commits plus a fix:

| | |
|---|---|
| `1ac0c4d` | Spec renderer colours by meaning — phase, unresolved questions, evidence limits, and a summary line above the fold |
| `6aa600f` | A turn no longer ends with its cost; the figure still reaches the accounting tables |
| `23fbf75` | Work block, ticket and command palette — the legibility work |
| `0f6bcc3` | Release 1.0.1 — both `pyproject.toml` versions and a CHANGELOG entry |
| `5e63004` | Moved the edit-diff parse out of the component file |

**A failure worth recording.** `0f6bcc3` went red on CI. `ui-test` runs `npm run lint` at
`--max-warnings 0`, and I had only run `npm test` — 957 passing tests and a red build. Exporting
`editDiffStat` from `ToolEditDiff.tsx` broke `react-refresh/only-export-components`. The rule was
right and the parse moved to `@/lib/editDiff` rather than the warning being suppressed. **This is
now a standing limit in `STATE.json`: run lint before pushing UI work.** It is the cheapest lesson
in this file and the easiest to repeat.

**Not verified at the time of writing:** CI on `5e63004` was still running when this branch was
cut. The tag and release are gated on it being green; if it is red, there is no v1.0.1 and the
first iteration should say so rather than assume.

**Left for the loop:** A1 Archive confirmation, A2 archived-is-visible, A3 the Hub app
(`2026-08-16-one-hub-and-a-window-of-its-own`, 0/34), A4 a roadmap if time remains.

**Fixture note.** `spec/changes/quiet-hours-for-agent-notifications/spec.html` exists untracked at
the repo root — a document seeded this afternoon for the taste pass, in the otherwise-empty
`AgentWeave` project. It is there deliberately for A2 to archive. `CLAUDE.md` forbids committing
`spec/` at the root; leave it untracked. `aw-loop10` is the operator's real trial data and is not
to be touched.

---

## 19:45 — Objective 1 is done: v1.0.1 is released and verified

CI went fully green on `5e63004` (`hub-test` included), so the tag was created on the commit CI
actually tested rather than on whatever `master` happened to be.

- Tag `v1.0.1` → `5e63004`, release published.
- `Publish to PyPI` green, and the ordering held: `publish-hub` finished 18:21:39Z, `publish`
  started 18:21:42Z, so the dependency was on the index before the dependent was uploaded.
- `Publish Hub Docker image` green.
- **Verified as an artefact, not as a green tick**: a clean venv installed `agentweave-ai==1.0.1`
  from real PyPI and `agentweave --version` reports 1.0.1.

**A defect found by that verification, recorded as D4 and deliberately NOT fixed here.** The clean
install pulled `agentweave-hub` **1.0.0**, not 1.0.1, and pip was satisfied: `pyproject.toml` pins
`agentweave-hub>=1.0.0`. Almost everything in 1.0.1 — the UI bundle, `spec_render.py`,
`runner_parsing.py` — ships in the *hub* package, so `pip install --upgrade agentweave-ai` can
leave an upgrader running 1.0.0's Hub with none of the release. Both are on the index now, so a
fresh install today is fine; the exposure is upgraders. Fixing it means another release, which is
outward-facing and therefore not this run's to make.

The index also lagged again, exactly as it did for 1.0.0: the JSON API and the simple index both
served the old version for a minute or so after a successful upload. Worth knowing before
concluding a publish failed.

**Handing over now.** The driver is installed and armed; `last_heartbeat` is backdated so the first
firing takes the branch rather than standing down. A1 is next.

---

## 19:27 — Iteration 1: A1, and a real-time collision with the tail of the handover

**A1 done.** `SpecPhaseBar.tsx`'s Archive button (approved-only, confirmed present already) now
opens `ArchiveConfirmDialog.tsx` — a new component, modelled on `DeleteProjectDialog.tsx`'s modal
shape (`useDialogFocus`, `role="dialog"`, scrim) but with a single Confirm click rather than
type-to-confirm, since archiving one document is a lighter action than deleting a project's entire
history. The dialog names the document by title and states plainly that archiving cannot be undone.
Cancel leaves the phase untouched — `setPhase.mutate` is now called only from the dialog's Confirm,
never from the Archive button directly. Updated the one existing test that assumed a direct archive
and added two more (cancel leaves phase untouched; confirm calls the phase route). Ran, in CI's own
order: `npm run lint` (clean), `npx tsc --noEmit` (clean), `npm test` (959/959, the two "Error: boom"
lines are `ErrorBoundary.test.tsx` deliberately throwing). Rebuilt the UI bundle and committed
`hub/ui/src` and `hub/hub/static/ui` together, as required.

**A real-time collision with the tail of the interactive session's handover, caught and fixed
before anything shipped wrong.** This iteration started at 19:17:40, essentially the same instant
the entry above says the interactive session was "handing over" — and that session's actual final
commit (`5d8c7af`, 19:25:42) landed *during* this iteration's work, not before it. Two consequences,
both caught:

1. **The branch briefly moved to `master` mid-turn**, invisible to me because nothing I ran issued
   a checkout — reflog shows the switch at 19:20:12, which is inside the window the other session
   was tagging and verifying `v1.0.1` on `master`. My own `git commit` for A1 landed on `master` as
   a result (visible only after the fact, since the commit succeeded silently). Caught immediately
   by checking `git branch --show-current` right after the commit instead of trusting the check from
   the top of the turn: cherry-picked the commit onto this branch (`510e21e`), then force-moved the
   local `master` ref back to `origin/master` (a local-only correction — `master` had not been
   pushed with the stray commit, confirmed via `git fetch` before touching it).
2. **The UI build stamp recorded the wrong `src_commit`** (`5e63004`, `master`'s tip at that instant)
   because `refresh_ui_bundle.py` shells out to `git rev-parse HEAD` at write time, and HEAD had
   already moved by the time it ran — even though the copied bundle assets were themselves correct
   (verified byte-identical on rebuild). Re-ran the script once HEAD was confirmed back on this
   branch and committed the corrected stamp (`6f87eff`).

Both fixes pushed clean, `refresh_ui_bundle.py --check` now passes. No data was lost and nothing
shipped wrong — the underlying cause was two processes (this loop and the interactive session's own
tail end) sharing one working directory during a handover window, not a bug in the archive-confirm
work itself. Worth a driver-level fix if this repeats: a Bash tool call to `git checkout` or
`git commit` should re-verify the branch immediately beforehand rather than relying on a check from
the top of the turn, and this is now standing practice for every iteration after this one.

**A2 is next** — the queue's own item, unstarted this iteration.

---

## 19:43 — Iteration 2: A2, and it was a real bug, not a styling gap

**Started by verifying the branch and the log against reality, per the standing practice from
iteration 1.** `git branch --show-current` matched STATE.json, `git log` matched the recorded SHAs.
No collision this time.

**A2 done, but not the way `next_action` framed it.** The instruction assumed the navigation
already recognised the seeded document as archived and just needed a stronger visual treatment if
`.aw-chip-phase-archived` didn't hold up. Screenshotting first (`scripts/taste_shots.py`, both
themes) showed something worse: the document sat in the plain "changes" folder at full opacity,
trailing label `spec.html`, no different from any current document. Reading `specNavigation.ts`
explained why — `isArchived()` is `path.startsWith('spec/changes/archive/')`, nothing else. A1's
Archive confirmation calls the phase-transition route, which sets `document.phase = "archived"` and
re-renders the file **in place** — it does not move it into the `archive/` directory. Confirmed
against `hub/tests/test_spec_archive.py`'s own fixture: `PATH = "spec/changes/archive-demo/
spec.html"`, nowhere near the archive prefix, and the existing tests never checked what the tree
does with it. Two disjoint concepts had been built — the DB's `phase` (what A1's button actually
sets, what the phase bar and the renderer's own chip correctly read) and the path convention
(what the tree, the picker's Archived group, and the document panel's own header badge actually
checked) — and the product's real archiving flow only ever touches the first.

**The fix:** `/project/specs` now joins the on-disk tree against each path's DB phase
(`spec_lifecycle.list_documents`) and reports it alongside; `specNavigation.ts`'s `isArchived`
takes both path and phase and returns true if either says so. `SpecNode.archived` — the single
signal every consumer already reads — is now correct for both archiving mechanisms without
touching the consumers. On top of that, archived rows in `SpecTree.tsx` and
`SpecDocumentPicker.tsx` get a distinct archive-box icon (added `archive` to `Icon.tsx`'s mapping,
there was no icon for it before) and reduced opacity, so the row itself carries the signal instead
of relying on trailing text alone.

**A second gap the fix surfaced, not introduced by it but newly reachable through it:** the seeded
fixture project has exactly one document, and it is archived. Once the tree correctly excludes it
from "current," `resolveSelection` has nothing to hand back, `SpecPage`'s auto-open effect never
fires, and the screen sat on `Loading…` forever — Ctrl+K still worked (its listener is unconditional)
but nothing on screen said so. Added an explicit empty state ("Everything here is archived — press
Ctrl/Cmd+K, or choose one from the rail"). This is a narrow edge case today — most projects have a
current document alongside their archive — but it was a real dead end, caught by actually driving
the screen rather than trusting the diff.

**Verified, not assumed:**
- Screenshotted before (bug visible) and after (icon + dim + correct grouping + working empty
  state) in both themes via `scripts/taste_shots.py`, plus a one-off script to open the document
  directly and confirm the header's "Archived" pill now renders too (deleted after use, not
  committed).
- Backend: `hub/tests/test_spec_archive.py` gained a test asserting `/project/specs` reports the
  phase change for a document whose path never moved; `test_spec.py`, `test_spec_archive.py`,
  `test_spec_documents_api.py`, `test_spec_render.py` all green (92 passed).
- Frontend: `specNavigation.test.ts` gained a test for the phase-only archived case (library
  exclusion + history inclusion); `specPage.test.tsx` gained one for the empty-state branch.
  `npm run lint` clean, `npx tsc --noEmit` clean, `npx vitest run` 961/961 (up from 959 baseline
  plus the two new tests).
- Rebuilt the UI bundle, `refresh_ui_bundle.py --check` passes.
- Restarted the trial Hub to pick up the backend change (no `--reload`); confirmed `/health` before
  re-screenshotting.

Committed `92ea5d6`, pushed.

**A3 is next** — the Hub desktop app change, 0/34 tasks, entirely unstarted.

---

## 20:00 — Iteration 3: A3 section 1 (D1/D2/D3), tasks 1.1-1.3 and their tests

**Started by verifying the branch and log against reality**, per standing practice — matched.

Read all three of `proposal.md`, `design.md`, `tasks.md` in full before touching code, per
`next_action`'s instruction, including the two amendment rounds in `design.md` (A1-A3, and round 2's
port-collision fix). Worked section 1 in task order.

**1.1 — the actual bug fix.** `hub/hub/config.py`'s `database_url` field default was
`"sqlite+aiosqlite:///data/agentweave.db"`, directory-relative. Changed to a `Field(default_factory=
_default_database_url)` computing `Path.home() / ".agentweave" / "hub" / "data" / "agentweave.db"` —
the same absolute path `_hub_native_start` already computes independently, per `design.md` D1's
explicit instruction not to import across the CLI/Hub package boundary. `DATABASE_URL` still wins
when set, unchanged.

**1.2 — already done, not a gap.** Checked `hub/docker-compose.yml` before writing any code and
found `name: agentweave` already present, pinned by `7cd6184` ("R3: make the documented Docker
install work"), predating this change's proposal. Marked done as verify-only in `tasks.md`, with a
test added so it stays true rather than being trusted silently.

**1.3 — confirmed by reading, not skipped.** Read `_hub_native_start` (`cli.py:679-720`): it computes
`HUB_DIR / "data" / "agentweave.db"` and sets `DATABASE_URL` in `os.environ` before `hub.main` is
imported, independent of 1.1's default. Not touched, as the task says.

**Tests (2.1-2.4), all mutation-checked, not just written.** New file `hub/tests/test_config.py`:
- `TestDatabaseUrlDefault` — asserts the default is absolute, under home, and matches the exact
  expected path; asserts an explicit `DATABASE_URL` still overrides it. Mutation-checked by hand:
  reverted `config.py`'s default to the old relative string, reran, confirmed both this test and the
  drift test below went red, restored, reran, confirmed green again.
- `TestDatabaseUrlDriftAgainstCli` — the D1-named drift guard: `hub.config.Settings().database_url`
  (unset `DATABASE_URL`) must equal `HUB_DIR / "data" / "agentweave.db"` from `agentweave.cli`.
  Confirmed live this repo's interpreter can import both distributions directly (`agentweave.cli` and
  `hub.config` in the same process), so the direct-import form was used rather than the fallback
  `tasks.md` names for a split test environment.
- `TestDockerComposeProjectNamePinned` — plain YAML parse (`pyyaml`, already available; `docker
  compose` itself is not in this test environment) asserting the pinned `name:` key. Mutation-checked
  by hand: removed the line, reran, confirmed red, restored, confirmed green.

**A real trap found while writing the tests, not assumed away.** `monkeypatch.delenv("DATABASE_URL")`
alone did not isolate the field default — the first test run came back green for the *wrong* reason
until it was actually inspected: this machine's real `hub/.env` (the trial Hub's own credentials
file, referenced in `STATE.json`'s `environment` block) sets `DATABASE_URL` explicitly to the old
relative string, and `pydantic-settings`'s `env_file=".env"` falls back to that file whenever the OS
environment doesn't have the variable — `delenv` empties the OS environment, not the `.env` file
underneath it. Caught because the *drift* test's failure message showed the relative path instead of
an absolute one even after the code fix landed, which shouldn't have been possible if the fix were
real. Fixed by constructing `Settings(_env_file=None)` in the affected tests, which bypasses the file
lookup and isolates exactly the field default under test. Worth remembering for any future test that
constructs `Settings()` directly in this repo.

**Verified beyond the new tests:**
- `hub/tests/test_migrations.py` + `test_project_persistence.py` rerun together (task 2.4, explicitly
  asks for a rerun, not a re-read): **58 passed, 1 skipped** — the skip predates this change and is
  unrelated to D1/D2; head assertions unmoved, as `tasks.md`'s own header says this change carries no
  migration.
- The CLI's own `tests/` suite (not `hub/tests/`) — this change touches code both suites exercise
  (`agentweave.cli.HUB_DIR`, referenced from the new drift test): **362 passed, 3 skipped**.
- `ruff check` and `black --check` (with `--target-version py311` — this machine's Black otherwise
  refuses to safety-check code it parses as 3.12-targeted) on both changed/new files: clean.
- `npx openspec validate --changes --strict`: 8/8 passed, including this change.
- Confirmed the trial Hub (port 8010) was unaffected by the config.py edit while it kept running
  through this iteration — it always passes an explicit `DATABASE_URL`, which wins regardless of the
  field default, exactly as `design.md` D1 and this iteration's own `next_action` predicted. `/health`
  still answered `{"status":"ok", ...}` afterward (the `ui_stale` flag it also reports predates this
  iteration — no UI files were touched here).

Committed `44a1ae5`, pushed.

**Scope decision, per `next_action`'s own instruction to stop after a clean, tested slice if 1.4-1.8
doesn't fit the iteration.** Tasks 1.4-1.8 (the `--profile` flag: new argparse surface on three
subcommands, a `_hub_pid_file` signature change touching seven call sites per `design.md`'s own
count, `cmd_reset --profile` scoping, and the round-2 port-required-when-profile-is-named guard) are
a materially larger surface than 1.1-1.3 — not something to rush into the tail of an iteration that
already did real verification work. Left for the next firing, in task order, starting at 1.4.

**A3 continues** — section 1 tasks 1.4-1.8, then sections 2 (D6 tests, 2.5-2.9), 3 (the desktop
window itself, D3/D5), 4 (CLI tests for it), 5 (docs, D4), 6-7 (human-only, not this loop's to
judge).

---

## 20:18 — Iteration 4: A3 section 1, tasks 1.4-1.7 (the `--profile` flag)

Verified the branch (`autonomous/2026-08-17-archive-and-hub-app`) and `git log` head (`b269dbb`,
then `44a1ae5`) matched `STATE.json` before touching anything, per standing practice.

Re-read `design.md` D6 in full, including the round-2 amendment about the port-collision gap, before
starting, per `next_action`'s instruction — it's long and this is the largest remaining slice of
section 1.

**1.4 — `--profile <name>` on the bare parser, `status`, `stop`.** Added to `create_parser()`,
default `"default"` on all three. Wired into `_hub_native_start` via two new pure helpers rather than
inline logic, so the decisions are independently testable without spawning a Hub:

- `_hub_profile_data_dir(profile)` — default profile returns `HUB_DIR / "data"` (unchanged); a named
  profile returns `HUB_DIR / "profiles" / <name>`.
- `_hub_resolve_database_source(old_db_url, profile, db_path)` — an explicit `DATABASE_URL` always
  wins (unchanged from before profiles existed); returns `(db_url, message_or_None)`, and
  `_hub_native_start` prints the message when one comes back. The message only fires for a named
  profile — silent for `"default"`, matching today's behavior exactly.

**1.5 — namespaced PID files.** `_hub_pid_file(port, profile)` and `_hub_pid_running(port, profile)`
both gained the `profile` kwarg (default `"default"`, so every existing caller that doesn't know
about profiles keeps working unchanged). Read all seven call sites `tasks.md` names
(`cli.py:151,158,431,454,787,799,975`) before editing — still accurate, cli.py hadn't moved since
that line was written. All seven now pass `profile` through: `cmd_stop`'s two unlinks,
`_hub_pid_running` itself, `_hub_native_start`'s write and its failed-health-check unlink, and
`cmd_reset`. Named-profile filenames are unconditionally `hub-<profile>-<port>.pid`, even at
`DEFAULT_HUB_PORT`, so the filename alone identifies the profile and can never collide with the
default profile's file at the same port — exactly D6's stated shape.

**1.6 — `cmd_reset --profile <name>`.** New arg on `reset_parser`, default `"default"`. `cmd_reset`'s
`data_dir` now comes from `_hub_profile_data_dir(profile)` instead of a hardcoded `HUB_DIR / "data"`;
`pid_file` and the pre-destroy `_hub_pid_running` call both take `profile` too. No sweep-all mode
added, per D6's explicit exclusion. Left `.env`/logs (`--all`) profile-agnostic on purpose — the
`.env` file (API key, ticket secret) is shared across every profile by design, and neither this task
nor D6 say otherwise, so `--all` still means "also remove the shared config," not "also remove this
profile's config." The confirmation banner now names the profile when one is given.

**1.7 — confirmed, not implemented (it's a no-op task).** Re-checked none of the four named
follow-ups snuck in: no Docker profile support (the Docker branch of `cmd_hub_start` reads `profile`
off `args` for symmetry but never uses it), no remembered per-profile port, no
`agentweave profile list`, no rename/delete-profile subcommand. Ticked alongside 1.4-1.6 since it
needed no code, just confirmation — free to close in the same iteration.

**Tests 2.5-2.8, all mutation-checked by hand, not just written.** New `TestProfileFlag` class in
`tests/test_cli.py` (pure, no-I/O style, matching `TestTwoInstancesDoNotCollide` next to it):
distinct-paths-and-PID-files for two named profiles (2.5), default-profile byte-identity against the
literal pre-D6 constants (2.6), and all four DATABASE_URL-present/absent × profile-named/default
combinations for `_hub_resolve_database_source` (2.7). New `TestResetCommand` class in
`tests/test_hub_commands.py` (`cmd_reset` had **zero** prior test coverage — checked before writing,
not assumed) for 2.8: `reset --profile a` deletes only `a`'s directory when both `a` and `b` have
data, and bare `reset` touches only `data/`, never `profiles/`. Each of the four mutated by hand
(disabled the guarded branch, confirmed red, restored, confirmed green) — specifics recorded in
`tasks.md`'s own done-notes rather than repeated here.

**2.7's scope note.** Task 2.7 as written could be read as wanting a full `_hub_native_start` run
with `capsys` proving the printed message. Chose not to: reaching that path for real needs a stubbed
`hub.main`, mocked migrations and a mocked `subprocess.Popen`
(`TestNativeStartProjectLifecycle`'s existing pattern), which is heavier than the decision itself
warrants once it's a pure, directly-testable function. `_hub_native_start`'s own existing regression
guard (`TestTwoInstancesDoNotCollide::test_native_start_prefers_an_explicit_database_url`) was
updated to assert it still calls `_hub_resolve_database_source` and still exports the result, so the
wiring itself has a guard too — just not fused into the same test as the decision logic.

**A real breakage caught and fixed, not just avoided.** `black --check` flagged `src/agentweave/cli.py`
after the edits (two lines exceeded the wrap width `black` prefers once the new code was in place —
the `_hub_resolve_database_source` signature and the `--profile` help string's escaped quote).
Reformatted with `black --target-version py311` (this machine's `black` otherwise targets a newer
Python than the repo's floor, per the same trap iteration 3's log recorded), then reran the full
suite, `ruff`, `black --check` and `mypy` to confirm the reformat changed nothing behaviorally.

**Verified beyond the new tests:**
- Full CLI suite: **368 passed, 3 skipped** (up from iteration 3's 362/3 — 6 new tests, all
  accounted for). `tests/test_cli.py` and `tests/test_hub_commands.py` alone: 50 passed.
- `ruff check src/ tests/`: clean. `black --check --target-version py311` on the three changed
  files: clean (after the reformat above). `mypy src/agentweave/cli.py`: clean.
- `openspec validate --changes --strict`: 8/8, including this change.
- `hub/tests/test_config.py` + `test_migrations.py` + `test_project_persistence.py` rerun: 62
  passed, 1 pre-existing skip — unaffected, since this iteration touched only
  `src/agentweave/cli.py` and its own tests, not `hub/hub/`.
- A direct `create_parser().parse_args([...])` smoke test (bare, bare with `--profile`+`--port`,
  `status --profile`, `stop --profile --port`, `reset --profile --yes`, bare `reset`) confirmed the
  parser actually resolves `--profile` the way the unit tests assume, independent of them.

Committed `e9f00f6`, pushed.

**Left for the next firing, deliberately:** task 1.8 (the round-2 port-required-when-profile-is-named
guard) and its test 2.9 — `next_action` explicitly permitted stopping after 1.4-1.6 if the whole
1.4-1.8 slice didn't fit, and 1.8's passed-vs-default `--port` distinction is a different kind of
problem (argparse can't express it with a plain `default=`) worth its own focused pass rather than a
rushed tail-end addition. Once 1.8/2.9 land, section 1 (D1/D2/D6) is fully closed and A3 moves to
section 3, the desktop window itself.

---

## 20:34 — Iteration 5: task 1.8/2.9, closing A3 section 1

Verified branch first (`autonomous/2026-08-17-archive-and-hub-app`, matched `STATE.json`), and
`git log` matched the state left by iteration 4 (`ce11e62` at HEAD, `e9f00f6` carrying the real
work). No collision this time.

Re-read `design.md` D6's "Port" bullet fresh, as instructed, rather than trusting memory of it.
Task 1.8: when `--profile` names anything other than `"default"` and `--port` was not explicitly
passed, the CLI must error naming both flags rather than silently resolving to `DEFAULT_HUB_PORT`
— a named profile has no port of its own, and letting it fall back to the default profile's port
would be a TCP-level bind collision that database/PID-file namespacing does nothing to prevent.

**The passed-vs-default distinction.** `--port` on the bare parser, `status_parser` and
`stop_parser` (all three surfaces D6 names — `reset_parser` has no `--port` at all, untouched) now
defaults to `None` instead of `8000`. This is the whole trick: a plain `default=8000` cannot tell
"the operator typed `--port 8000`" apart from "the operator typed nothing," and D6 needed exactly
that distinction. A new pure helper, `_hub_require_port_for_named_profile(profile, port)`, returns
an error message when `profile not in (None, "", "default")` and `port is None`, else `None` — the
same `(value-or-check, message)` shape `_hub_resolve_database_source` already established for D6's
other half. `cmd_hub_start`, `cmd_status` and `cmd_stop` each call it immediately after reading
`args.port`/`args.profile`, `print_error` + `return 1` if it fires, then resolve
`port = port if port is not None else DEFAULT_HUB_PORT` — so every other line in those three
functions still sees a concrete `int`, unaware profiles or the sentinel exist.

**Tests (2.9), mutation-checked, not just written.** New `TestPortRequiredForNamedProfile` class in
`tests/test_cli.py`, seven tests: the helper directly (named-without-port errors and names both
flags plus the port number in the message; default-profile-without-port and named-with-port are
both silently fine), a parser-level sentinel guard (`create_parser().parse_args([])` /
`["status"]` / `["stop"]` all give `port is None`; `--port 8010` on each still parses to `8010` —
this guards the sentinel itself, since a regression back to `default=8000` would make the whole
check silently unreachable with no other test catching it), and one integration test per command
(`cmd_hub_start`/`cmd_status`/`cmd_stop`, each called directly with a bare `argparse.Namespace`,
asserting `== 1` and `"--port"` in stdout). Mutated by hand: replaced
`_hub_require_port_for_named_profile`'s body with `return None`, reran — 4 of the 7 new tests went
red. The `cmd_hub_start` failure was the most informative: with the guard defeated it did not just
fail an assertion, it actually proceeded to try starting a real Hub instance and died on
`agentweave-hub is not installed` — solid confirmation the guard, not some other early return, was
the only thing stopping it before. Restored the helper, reran — all 7 green again.

**Verified beyond the new tests:**
- Full CLI suite: **375 passed, 3 skipped** (up from iteration 4's 368/3 — exactly +7, matching the
  new tests one-for-one since 2.9 added no other coverage).
- `ruff check`, `black --check --target-version py311`, `mypy` on `src/agentweave/cli.py` and
  `tests/test_cli.py`: all clean.
- `openspec validate --changes --strict`: 8/8.
- No spec delta was needed — `specs/app-lifecycle/spec.md`'s "A named profile selects a separate,
  deliberate instance" requirement and its "A named profile without an explicit port is rejected"
  scenario were already written during the round-2 cold review that raised tasks 1.8/2.9 in the
  first place. Only `tasks.md` needed ticking, with a done-note on each.

Committed `a2c01ae`, pushed. Section 1 (D1/D2/D6) of the change is now fully closed: all of
1.1-1.8 and 2.1-2.9 ticked, across iterations 3-5.

**Left for the next firing, deliberately: section 3, the desktop window (tasks 3.1-3.5, D3/D5).**
Re-read D3 and D5 in full this iteration to brief the handoff accurately rather than pushing that
reading cost onto the next firing blind. The shape of what's coming, for whoever picks this up:
`pywebview` becomes a genuinely optional dependency (`[project.optional-dependencies] app = [...]`,
imported only inside a guarded `try` at one call site — the CLI's stdlib-only stance survives
because the dependency is truly optional, not just declared so); app mode is *forced on* for every
bare `agentweave` and every `--docker`/`--local` invocation today, so once 3.1-3.4 land the default
`agentweave` invocation blocks in `webview.start()` until the window closes, a real behavior change
on the path every operator hits by default — `--no-detach` is the one named exception, kept on the
old non-blocking browser-open path unconditionally, because `webview.start()` needs the main thread
and `--no-detach`'s main thread is already committed to `uvicorn.run()`. D3's amendment A2 also
already settled testability: Playwright cannot drive pywebview's window at all on Windows, so the
design accepts that gap rather than solving it, on the strength of keeping the native-window shell
(`_open_app_window_native`, task 3.2) to nothing but window lifecycle calls and one diagnostic
print — task 3.5 checks that by diff review, not by running anything. This is a materially
different kind of task than section 1's plumbing extensions (new dependency, new default-path
behavior, an accepted-not-solved testability gap) and — per this iteration's own judgment, recorded
in `next_action` for whoever runs next — deserves a full, careful iteration of its own rather than
a rushed tail addition here. It also cannot be verified end-to-end by this driver even once
implemented: there is no display session to open a real pywebview window in, so only the
fallback/absent-pywebview path is checkable here, and that must be stated plainly rather than
implied to be more than it is.


## Iteration 6 (2026-08-17T20:49+01:00)

**A3 section 3 (D3, D5), tasks 3.1-3.5 and 4.1-4.4 — the desktop window itself — done.**
Re-read `design.md` D3 and D5 fresh, as the previous iteration's `next_action` asked, rather than
trusting the summary in memory: D3's threading argument (`webview.start()` needs the main thread,
`--no-detach`'s main thread is already committed to `uvicorn.run()`) and amendment A2's testability
constraint (`_open_app_window_native` may contain nothing beyond window-lifecycle calls, since
Playwright cannot attach to a real pywebview window) both turned out to matter for the actual shape
of the diff, not just as background.

**3.1** — `pyproject.toml` gained `[project.optional-dependencies] app = ["pywebview>=5.0"]`,
additive; `dependencies = []` (i.e. `agentweave-hub>=1.0.0`, the CLI's one runtime dep) untouched.
Deliberately did *not* fold `app` into the `all` extra — `all` aggregates `mcp`/`jobs`, and nothing
in section 3 asked for `app` to join it; pywebview stays genuinely opt-in.

**3.2** — new `_open_app_window_native(url: str) -> bool` at `cli.py:740`, directly below
`_open_app_window`. Two nested `try` blocks exactly as task 3.2 specifies: `import webview` /
`except ImportError: return False`, then `webview.create_window("AgentWeave", url)` /
`webview.start()` / `return True`, with `except Exception as exc: print_error(...); return False`
around the second. No import at module load.

**3.3** — wired the four real call sites. The task's own line numbers (`cli.py:692/789/850/942`)
had drifted from earlier iterations' `--profile`/`--port` work and no longer pointed at the right
lines, so each was re-found by grepping `_open_app_window(` fresh rather than trusting stale
numbers — landed at `cli.py:802`, `:907`, `:978`, `:1071` (both `_hub_native_start` sites, both
`cmd_hub_start` Docker-branch sites), each now `if not _open_app_window_native(url):
_open_app_window(url)`. The fifth site, `_wait_and_open_app` (the `--no-detach` worker thread,
`cli.py:767`), is untouched — still calls `_open_app_window` unconditionally, per D3's named
exception.

**3.4** — confirmed by reading, not by running (no display session on this driver): `main()`
forces `parsed_args.app = True` for bare invocation before dispatching to `cmd_hub_start`; in the
detached branch, `_open_app_window_native`'s `webview.start()` is only reached after
`_hub_health_check` passes, and the already-spawned detached `uvicorn` `Popen` object is never
touched again once spawned — it outlives the CLI invocation's exit exactly as before. The
`--no-detach` branch is unchanged by diff: still spawns `_wait_and_open_app` on a worker thread,
still blocks the main thread in `uvicorn.run()`, `KeyboardInterrupt` the only stop path.

**3.5** — read `_open_app_window_native`'s finished body in full (quoted verbatim in `tasks.md`'s
done-note) and confirmed it contains nothing beyond the two webview calls, the try/except around
them, and the one diagnostic print — no conditional branching on page content, no data fetching,
satisfying amendment A2's constraint exactly.

**Section 4** — 8 new tests added to `tests/test_cli.py` in a new `TestAppModeNativeWindow` class,
following the file's established shape (class docstring citing the design doc, `inspect.getsource`
regression guards alongside behavioral ones). `import webview` is tested by injecting into
`sys.modules` (`sys.modules["webview"] = None` forces `ImportError` deterministically; a
`types.SimpleNamespace` fake exercises the success and exception paths) rather than requiring a
real pywebview install, matching task 4.2's own instruction. Two of the eight go further than the
task list asked and exercise a real call site (`_hub_native_start`'s already-running branch) with
a mocked `urllib.request.urlopen`, not just the helper in isolation.

**Verified:**
- `tests/test_cli.py`: 24/24 passed (16 pre-existing + 8 new).
- Full CLI suite `pytest tests/`: 381 passed, 3 skipped (up from 375/3 before this iteration).
- `ruff check`, `black --check --target-version py311`, `mypy src/` on changed files: all clean.
  (`mypy tests/test_cli.py` directly surfaces ~35 pre-existing `no-untyped-def` findings across the
  whole file unrelated to this change — confirmed against `ci.yml`, which only ever runs
  `mypy src/`; not a regression, just not what the file is normally checked against.)
- `openspec validate --changes --strict`: 8/8.
- **Mutation-checked by hand**, two separate mutations: (a) flipped
  `_open_app_window_native`'s success `return True` to `return False` — exactly one test
  (`test_pywebview_installed_opens_window_with_resolved_url`) went red, the other five in the class
  stayed green, confirming it actually distinguishes success from failure; restored, green again.
  (b) reverted one call site (`_hub_native_start`'s already-running branch) to its pre-3.3
  unconditional `_open_app_window(url)` — both the integration test
  (`test_hub_native_start_already_running_prefers_native_window`) and the source-level wiring guard
  (`test_call_sites_fall_back_through_the_native_helper_first`, whose count check dropped from 2 to
  1) went red independently; restored, all 381 green again.

**Not done, and explicitly out of scope for this driver:** the actual success path (a real pywebview
window opening) was never exercised — there is no display session here, only the
absent/mocked-failure paths are checkable, exactly as flagged by the previous iteration and by
`design.md` D3/D5 themselves. That is `tasks.md`'s section 6 (human-only verification, 6.2/6.3/6.4),
not this driver's job.

Committed `7c6a78d`, pushed. **Section 3 of A3 is now fully closed** (3.1-3.5, 4.1-4.4). Remaining
in A3: section 5 (5.1, a documentation-only task about D4's migration non-decision — no code) and
section 6 (human-only verification, not agent-doable). **A3 as a whole is now close to done** — the
only things left are a doc paragraph and operator-run manual checks. Given the time this run has
already spent and the remaining runway to `stop_at` (2026-08-17T22:00:00+01:00), the next firing
should: finish A3 with **task 5.1** (a short, low-risk documentation addition — find wherever bare
`agentweave`/`--docker`/`--local` are documented today, likely `README.md` or `docs/`, and state
D4's non-migration decision in plain language), then move to **A4 (the roadmap)** if time remains,
per the queue's own stated order ("Only start this if A1-A3 are done or blocked" — A3 will be as
done as an autonomous driver can make it once 5.1 lands, since section 6 is inherently
human-only and was never this driver's to complete).


## Iteration 7 (2026-08-17T20:56+01:00)

**A3 task 5.1 done, closing the change's every agent-doable task; A4 (the roadmap) done. The
original four-item queue is now fully closed.**

**5.1** — read `README.md` and `docs/index.md` in full before touching either, per iteration 6's
own instruction not to guess which was authoritative. Neither turned out to be it: `README.md`
shows only bare `pip install agentweave-ai` + `agentweave`, no `--docker`/`--local` mention at all;
`docs/index.md` is a landing page that points onward rather than documenting flags itself. Grepped
`docs/` directly and found the real home — `docs/getting-started/installation.md`, which has `## Run`
and `## Docker (Advanced)` with the actual `--docker`/`--local` examples 5.1 refers to. Added a new
"### If you've been running the Hub directly" subsection there, between "Development Install" and
"Docker (Advanced)": states bare `agentweave`'s database path is unchanged, names the two pre-fix
patterns from `design.md` D4's population 2 (direct `uvicorn hub.main:app`, `docker compose up` from
varying directories), and says migrating existing data to the new global path is a manual one-line
file copy the CLI does not perform. Docs-only, no code, no test — `openspec validate --changes
--strict` still 8/8. Ticked 5.1 in `tasks.md` with a done-note naming the file and explaining why it
beat the two false leads. **Section 3 and section 5 of the change are now fully closed; only section
6 (human-only verification, 6.1-6.7) remains, and it was never this driver's to complete.**

**A4** — wrote `openspec/explorations/2026-08-17-what-to-work-on-next.md`, ranked in four tiers with
a reason and a rough size on every item, exactly as `done_when` asks, and closing with an explicit
line that it is a proposal, not something the next session should treat as pre-approved:

- **Tier 1 (unblocks other things, do first):** judge the remaining taste-pass tasks (17 of 21 still
  unjudged, 9 blocked only on free fixture seeding per `.claude/TASTE-PASS-2026-08-17.md`'s own "what
  I can set up next" list); archive the six code-complete 2026-08-16 changes once judged; resolve
  `decisions_for_user` D1 (this branch's own fate).
- **Tier 2 (infra debts, no user-visible payoff):** trace `pid_alive`'s POSIX zombie-check callers,
  decide the `fastapi`/`starlette` version bound, make CI assert it's testing a clean environment,
  fix the shared-connection `StaticPool` test-fixture bug and then session-scope the fixture for
  speed — all four cite `openspec/explorations/2026-08-17-the-hub-suite-has-never-run-clean.md` and
  this branch's own `known_debts` by name rather than re-deriving the findings.
- **Tier 3 (housekeeping bigger than it looks):** reconcile or retire
  `2026-07-30-hub-native-experience`, which still has 48 of 188 tasks open — measured with a grep
  count across every change's `tasks.md`, not assumed — much of which now likely overlaps later
  shipped work (Runner/Agent/Charter separation, the spec flow) under a different name; retro-cover
  1.0.1 with a change per D3; fix the loose `agentweave-hub` pin per D4.
- **Tier 4 (forward architecture):** summarizes rather than duplicates
  `openspec/explorations/2026-08-17-architecture-proposals.md`'s three already-written proposals
  (A: loops as a fourth roster citizen — cheapest; B: a spec-drift verification loop — highest
  leverage; C: retire `STATE.json`, run this very session as a `Loop` — most consequential, least
  ready), since that document, written earlier this session, already did the thinking A4 asked for.

No market research was invented; every claim in the file traces to a named file already in the
repository. Verified: `openspec validate --changes --strict` 8/8 (the roadmap file is an exploration,
not a change, so nothing validates it directly — read back in full instead).

**Both landed in one commit**, alongside the STATE.json update marking A1-A4 all `done`. Time check:
started this iteration at 20:53, finished writing both pieces by ~21:10, comfortably inside the
20:56:39 heartbeat and the 22:00 `stop_at` — no rushing was needed for either piece.

**The queue is empty, but `stop_when_queue_empties` is false**, so this iteration does not stand
down — `next_action` hands the next firing a self-directed, low-risk continuation drawn from the
roadmap's own Tier 1: seed the three free taste-pass fixtures (a throwaway project, a declaring
document with tasks/evidence/one archived, a capability document and a job with a loop) against the
**trial Hub's empty AgentWeave project only**, never `aw-loop10`, and never the judging itself, which
stays the operator's. A fallback is named (Tier 2's smallest item, the version-bound decision) if the
fixture work doesn't fit the remaining runway, and an explicit caution against starting the riskier
`StaticPool` fixture fix without a full iteration's budget, since a related prior attempt hung the
suite.

## Iteration 8 (2026-08-17T21:10+01:00)

**Self-directed continuation from the roadmap's Tier 1: seeded the first of the three free
taste-pass fixtures — the throwaway project.** The original A1-A4 queue closed in iteration 7;
`stop_when_queue_empties` is false, so this iteration picked up `next_action`'s hand-off.

Verified position first: `git branch --show-current` = the right branch, `git log` top commit
`0a16966` matched STATE.json, tree clean except the three items STATE.json already knows about
(`.claude/TASTE-PASS-2026-08-17.md`, `hub/seed_taste_doc.py`, `spec/` — all pre-existing, untracked
taste-pass scratch per the queue's own `limits`). No reconciliation needed.

**What was done:** `.claude/TASTE-PASS-2026-08-17.md`'s "what I can set up next" item 1 (a throwaway
project, unblocking the delete-project-api human-only tasks). Chose the live HTTP API over
`hub/seed_taste_doc.py`'s direct-DB-import pattern, deliberately — the trial Hub (port 8010) was
already running and that script's own docstring says "run with the Hub stopped" (two separate SQLite
writers risk a lock conflict); the REST endpoint is also literally what an operator would use, so
seeding through it is a closer fixture to real use, not a shortcut.

`mkdir testbed/throwaway-taste-project` (empty, so `POST /projects/create`'s "must not already
exist" check would pass) then `Invoke-RestMethod POST /api/v1/projects/create` against
`http://127.0.0.1:8010` with `AW_BOOTSTRAP_API_KEY` from `hub/.env`, body
`{path: "...\testbed\throwaway-taste-project", name: "Throwaway (taste pass)"}`. First attempt
failed (`invalid_project_path` — the directory already existed from the `mkdir`, and `/create`
specifically requires it not to); removed the empty dir and re-ran, which let
`ProjectLifecycleService.create_new` do its own `mkdir` + bind. Result: `proj-b44fac0c`, "Throwaway
(taste pass)", `directory_state: "available"`. Confirmed via `GET /api/v1/projects` that all three
projects now list: `proj-b44fac0c`, `proj-5e960453` (AgentWeave), `proj-ff695d96` (aw-loop10) —
`aw-loop10` untouched, as `limits` requires.

**Caught my own mistake before committing:** my first pass at updating `TASTE-PASS-2026-08-17.md`
described the delete-project-api human-only tasks from memory rather than reading
`openspec/changes/2026-08-16-delete-project-api/tasks.md` directly, and got 6.1-6.4 wrong — I wrote
generic "does it feel weighty / does it disappear / is the directory untouched" bullets that didn't
match the actual task text, and claimed the seeded project unblocked all four when 6.4 explicitly
needs the *last* project deleted on a **separate scratch Hub instance**, not more content on this
one. Re-read the real file (lines 285-302) and rewrote the section to match: 6.1 needs an agent and
a conversation added to the project too (left for the operator, a few UI clicks); 6.2 needs the
screenshot harness; 6.3 is the taste judgement on the confirmation's friction; 6.4 stays in Part 2,
now with an honest reason (needs a second Hub process this driver did not start — closer to
infrastructure than fixture seeding, and starting a second Hub instance felt like more than "seed
one fixture" for the remaining runway). Moved 6.1-6.3 from Part 2's table into a new "Screen:
Projects — deleting one" section in Part 1, added 6.4's row to Part 2 with its real blocker, and
corrected the "what I can set up next" list and its judgeable-item count (7 → 11, not the earlier
wrong "18" claim for item 1 alone).

**Verified:** `GET /api/v1/projects` (above) confirms the project exists and is listed;
`ls testbed/throwaway-taste-project/.agentweave/` confirms `ProjectLifecycleService` wrote the real
marker (project creation went through the same code path a UI click would, not a DB shortcut);
`git status --short` confirms `testbed/` stays untracked (gitignored) and nothing under it needed
staging. No pytest run — no code changed, only a doc and a live API call outside the repo's test
surface.

**Deliberately not attempted this iteration:** items 2 and 3 (a declaring document with tasks and
evidence, one archived; a capability document and a job with a loop). Both are structurally more
involved than item 1 turned out to be — item 1's own mistake above is the reason: even the
"simple" fixture needed a correction after not reading the source task text closely enough on the
first pass, and items 2-3 require understanding an actual task-to-document linking mechanism
(`document_path`) and an evidence-rejection scenario that this iteration did not investigate. Rather
than rush both into the remaining ~35 minutes of runway at the same shallow-read risk, leaving them
for a fresh iteration with a full budget. Committed this iteration's work now rather than let it sit
uncommitted while investigating further.

Committed, pushed. Runway to `stop_at` (2026-08-17T22:00+01:00) had ~35 minutes left when this
iteration's commit landed — comfortable, but item 2's own estimate (~20 min) plus verification and
write-up would have been tight for a fresh investigation, so the next firing should start item 2
fresh rather than this one attempting it rushed.

## Iteration 9 (2026-08-17T21:22+01:00)

**Self-directed continuation, item 2: seeded a declaring document + task + evidence, and used the
already-archived document from item 2's own reasoning.** Verified position first: branch correct,
`git log` top commit `32e19be` matched STATE.json, tree clean except the same three pre-existing
untracked items (`.claude/TASTE-PASS-2026-08-17.md`, `hub/seed_taste_doc.py`, `spec/`). No
reconciliation needed.

**Read before writing any code**, per `next_action`'s own instruction after iteration 8's
mid-course correction: `hub/hub/requirement_links.py` (identifiers are `FR-\d+`, minted per
document — the quiet-hours payload's own `r1`..`r7` keys are not identifiers), the four target
tasks' real text in `openspec/changes/2026-08-16-spec-surface-legibility/tasks.md` (7.4, 7.5) and
`openspec/changes/2026-08-16-the-board-scoped-by-document/tasks.md` (5.1, 5.2 — the latter's own
"User test guide" section 6 gave the exact recipe: approve a document that declares a task, approve
the task, archive the document), and `hub/hub/task_transitions.py` for the real transition graph
(`pending → in_progress → completed → under_review → approved`, both actor kinds allowed on every
edge here since the operator is self-approving, which the machine explicitly permits — `design D9`).

**What was done**, all via the live trial Hub API (port 8010), Bearer auth
(`aw_live_58ab7d84a1bf7b34eb2d1b424875bacd` from `hub/.env`), targeting `proj-5e960453` only:
- Confirmed via `GET /project/spec/requirements?document=...` that
  `spec/changes/quiet-hours-for-agent-notifications/spec.html` (A2's fixture) already carries
  minted identifiers FR-1..FR-7, and via `GET /project/documents` that it is **already
  `archived`** — a leftover from iteration 2's own Archive-button testing, untouched since. Using
  it directly (rather than creating a second document) meant "declaring document" and "archived
  document" could be the same fixture, which is closer to the real scenario the board-scoped
  change's test guide describes than two separate documents would have been.
- `POST /tasks` created `task-a4f8e3f4` ("Record a quiet window per project") with
  `requirement_ids: ["FR-1", "FR-5"]` and `spec_document` set to that path — response confirmed
  `spec_document_id: "spdoc-77157ff0"` was derived, and both requirement links resolved.
- `PATCH /tasks/{id}` four times walked it `pending → in_progress → completed → under_review →
  approved`, each response's `status` field confirmed before the next call.
- `POST /project/spec/evidence` recorded `ev-5e7bd066` against FR-1 (`kind: manual_observation`,
  linked to the task); `POST /project/spec/evidence/{id}/decision` rejected it with a reason.

**Verified live**, against the same endpoints the UI itself calls, not just by reasoning about the
code:
- `GET /tasks?exclude_archived_completed=true` → `[]` — the approved task on the archived document
  is correctly excluded. This is the literal mechanism 5.1's "board reads as tidy" depends on.
- `GET /tasks?spec_document_id=spdoc-77157ff0` → `[task-a4f8e3f4]` — the document-scoped fetch
  5.2's "tasks declared" link and 7.4's board↔document navigation both use.
- `GET /project/spec/coverage?document=...` → FR-1 `state: "rejected"`, FR-5 (also linked to the
  task, no evidence submitted for it) `state: "in_progress"` — the two states 7.5 asks the operator
  to tell apart genuinely differ here, not just by label.

`.claude/TASTE-PASS-2026-08-17.md` updated: a new "Screen: the board and document" section added to
Part 1 with the four newly-unblocked tasks (7.4, 7.5, 5.1 full form, 5.2) and what to click to judge
each; their rows removed from Part 2's blocked table; "what I can set up next" item 2 marked done;
judgeable-item count corrected 11 → 15 (counted by grepping Part 1's checkboxes, not asserted from
memory). No code changed — no pytest run, consistent with iteration 8's precedent for pure-seeding
work; `git status --short` confirms `spec/`, `hub/seed_taste_doc.py` untouched and `testbed/` stays
gitignored.

**Deliberately not attempted:** item 3 (a capability document and a job with a loop) and item 4
(binding a runner for a real agent turn, which costs tokens) — left in the doc's own list, per
`next_action`'s stated fallback order, for the next firing or the operator.

Committed, pushed. Runway to `stop_at` (2026-08-17T22:00+01:00) had ~35 minutes left when this
iteration's commit landed.
