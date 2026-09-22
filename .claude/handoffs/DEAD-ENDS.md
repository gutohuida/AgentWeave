# Dead ends — the durable ledger

Things that do not work on this machine, in this repository, or with these tools, and the symptom
you will see when you hit one. **Append-only.** An entry is never deleted; when it stops being
true it is marked `RESOLVED` with the date and what changed, because "we used to believe this"
is itself worth knowing.

## Why this file exists

Until 2026-09-04 these facts lived only in each handoff's `## Dead ends` section, carried forward
by whichever session happened to write the next handoff. That made survival a coin flip, and the
cost was measured across the 108-handoff chain:

| Fact | Appears in handoff |
|---|---|
| Bash-tool `cd` persists between calls | 0003, 0020, 0024–0027, 0055, 0059, 0068, 0081, 0095–0098, 0106 — **then dropped** |
| `openspec --strict` reads only the first physical line | 0042–0046, **46-handoff gap**, 0093, 0096–0108 |
| `git merge -F -` does not read stdin | 0064, **40-handoff gap**, 0105–0108 |
| `pytest --timeout=` unavailable in `hub/tests/` | 0044, 0052, 0068, 0081, 0087–0088, gap, 0102–0108 |

Every one of those was paid for more than once. The `cd` entry was written down at handoff 0003,
re-learned at least seven times, dropped before 0107 — and cost three failed tool calls on
2026-09-04, during the session that built this file.

Compiled from 1,387 dead-end bullets across 193 handoffs (1,241 unique after dedupe). The same
fact recurred in up to five different phrasings — `npm run lint does not work` alone appears 19
times across 4 wordings. What follows is the deduped set, with the canonical phrasing.

## How to use it

- `/resume` reads this file. `/handoff` appends to it rather than re-copying the list forward.
- **Verify before trusting an entry older than a few weeks.** Entries carry the date they were
  last confirmed. Two facts in the founding set were already false when this file was compiled —
  see `RESOLVED` below — and an inherited-but-stale entry is worse than no entry, because it is
  believed.
- Add an entry the moment something costs you a second attempt. One line, the symptom, the date.

---

## Shell — the Bash tool

- **`cd` persists between calls.** A later call inherits the previous call's working directory.
  A background `pytest hub/tests/` once inherited a `hub/ui` cwd, collected nothing, and
  **exited 0** with "no tests ran". Use absolute paths after any `cd`, and never trust a
  background run's exit code alone — read the tail. *(Confirmed 2026-09-04, three times.)*
- **Long heredocs mangle content.** A ~180-line `cat > file <<'EOF'` through the Bash tool fails.
  Backticks, apostrophes inside Python string literals, and `\n` escapes are all eaten. Use the
  Write/Edit tools for anything longer than a few lines, and `git commit -F <file>` for commit
  messages. *(Confirmed 2026-09-04 — this file was written with Write for exactly this reason.)*
- **A doubled backslash reaches bash as a single one, at any length, even inside single quotes.**
  *Measured 2026-09-12 (day window, F324):* `printf '%s\n' 'a\\b' | od -c` prints `a \ b`, and a
  three-line quoted heredoc carrying `x\\fy` delivers `x\fy`. So `b"\\f"` in Python source sent
  through a heredoc arrives as `b"\f"`, a **form feed**, and a repair meant to put a backslash
  back into `FINDINGS.md` silently rewrote the same U+000C (the file came out byte-identical).
  A single backslash survives, which is why `"\n"` in a commit message looks fine. Anything
  whose meaning depends on a backslash goes in a file written with Write, and a byte-level
  change is spelled as `bytes([0x5C, 0x66])`, not as an escape.
- **Backticks in a double-quoted commit message execute.** `git commit -m "... `foo` ..."` runs
  `foo`. Use `git commit -F <file>`.
- **`git merge -F -` does not read stdin.** Write the message to a file first.
- **`grep -c` returning 0 exits 1**, which kills a `&&` chain. Use `;` or `|| true`.
- **`grep -oE` truncates at the em-dash** in files that use them as separators (`FINDINGS.md`
  headings).
- **A foreground `sleep` is blocked** by the harness, chained before or after another command.
- **A background shell dies at session teardown.** Anything that must outlive the session needs
  WMI (`Invoke-CimMethod Win32_Process Create`), not a backgrounded Bash job.
- **The Bash tool caps at 600s.** `pytest hub/tests/` exceeds it — see below.
- **A piped run reports the last command's exit code.** Use `${PIPESTATUS[0]}` when piping through
  `tail`.
- **`strings` is not available** in this Git Bash. Use `grep -ao`.
- **`grep -P` cannot scan for non-ASCII here.** *(2026-09-13)* It fails with *"-P supports only
  unibyte and UTF-8 locales"* and, in a loop, prints counts of 0 that look like a clean result.
  Scan for Unicode in Python with `PYTHONIOENCODING=utf-8`. Without that variable, printing a
  non-cp1252 character raises `UnicodeEncodeError`.
- **This Git Bash (5.2.37, msys2) forces `LC_CTYPE=C.UTF-8` and cannot be put in a plain C locale.**
  *Measured 2026-09-13 by F332's pre-approval review:* `LC_ALL=C`, `LANG=C`, `LC_CTYPE=C` and
  `POSIX` all leave it in `C.UTF-8`, so the four-hex escape for U+0100 inside `$'…'`
  (backslash, `u`, `0100`) decodes to the UTF-8 bytes `c4 80`. *(Aside: writing that escape
  through Claude Code's Edit tool stored the decoded character `Ā` instead, twice. Spell such
  escapes out in words, or build them from bytes.)* A probe that runs
  `LANG= LC_ALL=` in a hand-built environment shows the C-locale behaviour (the escape kept
  literal) that a spawned agent's bash here does not have. R3 of `a-quote-can-spell-a-slash` drew
  a false "Windows escape" from exactly that probe. Before arguing from bash locale behaviour on
  this machine, check `locale` inside the shell the product actually spawns.
- **`grep -rn ... hub/` times out** — it walks `hub/ui/node_modules`. Scope the path or use the
  Grep tool.

## Python and interpreters

- **Use `py -3.11`, never bare `python`.** `python` resolves to
  `~/AppData/Local/hermes/hermes-agent/venv/Scripts/python` — a different environment that yields
  3 phantom `pty_runner` failures on a tree that is actually green. *(Confirmed 2026-09-04.)*
- **`python` now *has* pytest (9.1.1), which makes this worse, not better.** The old entry read
  "the default python on PATH has no pytest" — it fails loudly no more. It runs, and lies.
  *(Updated 2026-09-04.)*
- **Only Python 3.11 exists on this machine**; 3.12 is CI-only. `black` therefore needs
  `--target-version py311` or it refuses with a safety-check warning.
- **`py -3.11 -c` printing `→` or `—` dies with `UnicodeEncodeError`** — stdout is cp1252. Set
  `PYTHONIOENCODING=utf-8` or avoid the characters.
- **A PowerShell mutate-and-restore corrupts every non-ASCII character in the file** *(2026-09-12,
  u2-reader)*. `Get-Content -Raw` in Windows PowerShell 5.1 reads a BOM-less UTF-8 file as cp1252,
  and `[IO.File]::WriteAllText` writes UTF-8 back: each `—` became `â€"`, 92 characters in
  `mcp_server.py`, the tests still passed, and only `git diff --stat` (586 lines for a ~330-line
  change) showed it. Mutate with `py -3.11` (`open(..., encoding="utf-8")`), and restore with
  `git checkout -- <file>` **only** when the working copy is committed. If it happens anyway,
  `testbed/scratch/night0912/enc_fix.py <file>` reverses the round trip exactly.
- **A `py -3.11` mutate-and-restore with `Path.write_text` turns every file it touches CRLF**
  *(2026-09-15, night iteration 5)*. Text mode on Windows writes `\n` as `\r\n`, so the restore
  is not byte-identical: `git status` then shows a file the change never edited as modified (it was
  `agents.py`, mutated and restored by M12), and `file` reports *with CRLF line terminators*. Git
  normalises at commit, so nothing reaches history, but the tree lies about what changed. Write with
  `write_text(..., newline="\n")` (or `write_bytes`). If it happens anyway: `git checkout -- <file>`
  for a file with no real edit, `sed -i 's/\r$//' <file>` for one with.
- **`py -3.11` cannot open a Git Bash `/tmp/...` path.** Use a Windows path.
- **`py -3.11 -c "import hub.main"` from the repo root fails** with an ImportError — this repo's
  `hub/` directory shadows the installed `hub` package. See the Hub section.
- **`shutil.rmtree(..., ignore_errors=True)` is a lie on Windows** — it silently leaves the tree.
- **`sqlite3` is not on PATH.** Use `py -3.11 -c "import sqlite3; ..."`. *(Confirmed 2026-09-04.)*
- **`ruff` and `mypy` are not on PATH in Git Bash.** Use `py -3.11 -m ruff`, `py -3.11 -m mypy`.
  *(Confirmed 2026-09-04.)* **And the failure is silent, which is why this entry keeps being
  re-learned** *(2026-09-09)*: `ruff check src/ hub/ tests/ 2>&1 | tail -5` prints
  `command not found` and then reports **exit 0**, because `$?` is the pipeline's last stage. A
  lint gate written that way reads as a pass while nothing ran. `black` *is* on PATH, so two of
  the three commands in the documented gate work and only the other two lie.
- **`pip` warns about two invalid distributions** in Python311 site-packages (`~gentweave-ai`,
  `~nteragent-framework`) — leftover partial uninstalls. Harmless noise, not a failure.
  *(Observed 2026-09-04.)*
- **The global Python resolves `import hub` to THIS CHECKOUT from any directory**, not only from the
  repo root — `C:\Users\huida\Documents\projects\AgentWeave\hub\hub\__init__.py`, confirmed with cwd
  set to `C:\Users\huida`. The repo-root shadowing entry above understates it. Consequence, found
  live: a `python -m uvicorn hub.main:app` started by the *global* interpreter serves the
  development checkout's code, whatever database it is pointed at. *(Confirmed 2026-09-07.)*
- **A Windows venv `python.exe` re-execs the base interpreter, so process listings name the WRONG
  interpreter.** `Get-CimInstance Win32_Process` reported
  `AppData\Local\Programs\Python\Python311\python.exe` for a server actually launched from
  `agentweave-live\venv\Scripts\python.exe`; `sys.executable` inside the process correctly reported
  the venv. Do not conclude "the wrong Python is running" from a command line alone. Check the
  **parent** process, or `(Get-Process -Id N).Modules` for paths under the venv. *(Confirmed
  2026-09-07, cost one false diagnosis.)*

## pytest

- **`pytest --timeout=` does not work in `hub/tests/`** — `pytest-timeout` is not installed;
  collection fails with exit 4. Use an external timeout. *(Confirmed 2026-09-04.)*
- **`pytest hub/tests/ tests/` in one invocation fails collection.** Both trees contain a
  `test_mcp_server.py`. Run them separately.
- **The Hub suite takes 20–24 minutes** and exceeds the Bash tool's 600s cap. Run it in the
  background or in chunks, and do not poll it.
- **`pytest -q` buffers everything**, so a redirected background run's file lags reality badly.
  A `[ NN%]` marker read from that file is meaningless — measure elapsed time from the process
  (`Get-Process | StartTime`) instead.
- **`pytest <nonexistent_file.py>` runs nothing and reports success-shaped output.** Check the
  collected count, not just the exit code.
- **`gh run view <id> --log-failed | grep -i failed` matches *passing* tests** *(2026-09-12)*: the
  Hub suite has dozens of tests whose names contain `failed`
  (`test_spawn_failure_marks_run_failed PASSED`), so the grep returns twelve green lines and hides
  the red one. Grep for the summary instead: `grep -E "(FAILED|ERROR) tests/|=+ .*(passed|failed).* =+"`.
- **Classify a red `hub-test` by its signature before blaming a commit** *(2026-09-12: 4 of ~11
  runs red that day, every one on a doc-only commit)*. There are **two** known intermittents with
  different signatures:
  - **F292:** a setup `ERROR` with `sqlite3.OperationalError: database is locked`.
  - **F314:** `FAILED test_flow_holds_the_loop_requirements.py::test_a_wide_flows_state_is_still_one_call`,
    `RuntimeError: <asyncio.locks.Lock …> is bound to a different event loop`.

  A red with either signature on a commit that touched no Python is not that commit's.

## git

- **`git worktree add` into the scratchpad fails** with "Filename too long".
  To test or collect an old tree, export only what you need instead: `git archive <sha> hub | tar -x -C <scratch>/h`, then run from there with `PYTHONPATH=<scratch>/h/hub` (used for F382, 2026-09-22).
- **Stage explicit paths.** `git add -A` sweeps in scratch files.
- **CI triggers only on push to `master` and PRs to it.** ~~A feature branch push runs
  nothing.~~ **RESOLVED 2026-09-06 — false as of the merge-gate work.** `ci.yml` now builds
  `autonomous/**` too (a prerequisite for the day window's merge gate, landed circa
  2026-09-04). Confirmed directly: every push to `autonomous/2026-09-04-daily` this session
  (six of them) triggered its own CI run, checkable with
  `gh run list --branch <branch> --limit N --json headSha,conclusion,status,databaseId`.
- **`gh run view --log` and the REST job-logs endpoint both refuse a still-running job.**
  `gh run view <id> --log` prints `run <id> is still in progress; logs will be available when
  it is complete` (exit 0, no content); `gh api repos/<o>/<r>/actions/jobs/<jobid>/logs`
  404s with `BlobNotFound`. There is no CLI-accessible live tail. The only thing you can read
  from an in-progress run is job/step *status* and timestamps —
  `gh run view <id> --json jobs --jq '.jobs[]|{name,status,conclusion}'`, or per-step
  `startedAt`/`completedAt` — which is enough to notice a job has been running far longer
  than its historical ceiling, just not to see why. *(Hit 2026-09-06, diagnosing a 3.5-hour
  `hub-test` hang — F292/F295.)*
- **A backgrounded `gh run watch <id> --exit-status` loses its exit code if anything is
  chained after it.** `Bash({..., run_in_background: true})` reports the exit code of the
  **last command in the string**, not of `gh run watch` specifically — `gh run watch $ID
  --exit-status; echo "DONE=$?"` always notifies "exit code 0" because `echo` always
  succeeds, even when the run actually failed. This is the `run_in_background`/task-
  notification-specific case of the general piping trap two entries up; it cost a session a
  wrong "CI is green" report to the operator on 2026-09-06 (the run had actually failed on an
  unrelated lint error). Run `gh run watch ... --exit-status` **alone**, as the entire
  backgrounded command, so the notification's exit code is the real one.
- **A `.gitignore` entry ending in `/` cannot be un-ignored by a later `!` negation.** Git does
  not descend into an excluded *directory*, so the negation is unreachable and the file stays
  ignored with no error. Exclude the contents instead — `dir/*` plus `!dir/keepme` — which
  leaves the directory itself visible. *(Hit 2026-09-04 adding `.claude/handoffs/*` with an
  exception for `DEAD-ENDS.md`.)*
- **`git check-ignore -v` cannot answer "is this ignored?" when a negation matches.** It prints
  the matching rule — including a `!` rule — and its exit code does not distinguish "ignored"
  from "explicitly un-ignored", so the obvious `&& echo ignored || echo not` test reports the
  opposite of the truth. Verify with `git add <path>` (does it get staged?) or
  `git status --short --untracked-files=all`. *(Hit 2026-09-04.)*
- **A commit made while an unattended window owns the tree must stage explicit paths and land
  immediately.** The window's agent is instructed to "never end an iteration with a dirty
  tree" (`.claude/skills/autonomous-session/scripts/run-iteration.ps1:196`), so any stray
  modified file left sitting will be swept into *its* commit. *(2026-09-04.)*
- **`git branch -d` refuses a branch that IS merged to master when its remote-tracking ref has
  diverged.** The message says so explicitly — "not deleting branch X that is not yet merged to
  `refs/remotes/origin/X`, **even though it is merged to HEAD**" — and is easy to misread as "this
  branch has unmerged work". Before reaching for `-D`, check the remote side directly:
  `git rev-list --count master..origin/<branch>`. Two branches reported this on 2026-09-07 and both
  returned **0**, i.e. nothing was at risk. *(Confirmed 2026-09-07.)*
- **`git worktree remove` needs the worktree's own path, and the branch stays behind.** Removing the
  directory does not delete the branch; run `git worktree prune` afterwards, then delete branches
  separately. Seven worktrees were removed this way on 2026-09-07 (six `agentweave/*` roster
  leftovers under `.agentweave/worktrees/`, plus the sidequest worktree). *(2026-09-07.)*

## openspec

- **`openspec` is on PATH directly** — `npx` is no longer required. *(Updated 2026-09-04; earlier
  entries all said `npx openspec`.)*
- **`openspec validate --strict` reads only a requirement's FIRST PHYSICAL LINE** when looking for
  `SHALL`/`MUST`. A requirement whose keyword is on line 2 is invalid and the message does not say
  why.
- **`openspec` rejects change names starting with a digit**, including date-prefixed ones
  (`2026-08-07-foo`) — and `status --change` rejects them too, not just `new`.
- **`openspec validate` with no target exits "Nothing to validate"** rather than failing. Pass
  `--all --strict` or a named change.
- **There is no `openspec sync` command** — the skill applies deltas by hand.
- **`openspec archive` prefixes the archive directory with the *UTC* date** when the change name
  does not already start with it, so a change archived after local midnight but before UTC midnight
  gets a **double date**. *(2026-09-10.)* `2026-09-07-clearing-instructions-asks-first` archived at
  00:59 local / 23:59 UTC and landed as
  `openspec/changes/archive/2026-09-09-2026-09-07-clearing-instructions-asks-first`. Left as the tool
  produced it — renaming by hand makes the result unreproducible — but do not read the leading date as
  the day the work was done.
- **`openspec archive` updates main specs by default; `--skip-specs` is how a hand-merged sync
  survives it.** *(2026-09-10.)* The bare command advertises "archive a completed change **and update
  main specs**", which would put a mechanical update on top of a file whose value is the judgement
  hand-merged into it. `--skip-specs` and `--no-validate` are **separate** flags, so skipping the spec
  step still validates. Verified by `md5sum` either side of the archive: byte-identical.
- **Clearing `testbed/` deletes evidence that live openspec changes cite.** *(2026-09-08.)* The
  2026-09-07 clean slate emptied `testbed/` to its two tracked files; the still-unapproved change
  `2026-09-07-a-dead-connection-is-never-handed-back-out` cites
  `testbed/scratch/f295/probe_pool.py` in `tasks.md:16` as the measurement that established which
  attributes its guard reads. The probe is gone and the citation is dead. **Before clearing the
  testbed, grep `openspec/changes/` for `testbed/`** — or accept that a proposal's evidence becomes
  unreproducible. (The specific probe was re-derived on 2026-09-08; see the SQLAlchemy section.)

## Node and the Hub UI

- **`cd hub/ui` first.** `npx vitest` from the repo root resolves a different project and picks up
  the wrong config.
- **`scripts/refresh_ui_bundle.py` must be run from the repo root**, not from `hub/`.
- **`cp -r dist/ static/ui/` merges rather than replaces.** Use the script, which is what records
  `ui-build-stamp.json`.
- **`npm test -- --runInBand` is invalid for Vitest.** Use `npm test`.
- **vitest full-suite runs flake on `chartersUi` / `runnersUi`** under a 5s timeout.
- **Adding a hook to a component breaks every test that mocks that component's module.** Nine UI
  test files mock `@/api/questions`; seven mock `@/api/permissions`.

## The Hub at runtime

- **`agentweave --port 8010` cannot start the trial Hub.** The console script is the *installed*
  `agentweave-hub`, whose bundled migrations lag this checkout — it dies with
  `Migration failed: Can't locate revision identified by '00NN'`. Start from `hub/` with uvicorn
  from source. This cost two sessions on 2026-08-24.
- **The Hub cannot be started from this repo's root.** `-m` puts the cwd on `sys.path[0]`, so this
  repo's `hub/` shadows the installed `hub` package and the child dies with
  `ImportError: cannot import name '__version__' from 'hub'` — 60 seconds later, with its output
  already sent to `DEVNULL`. Start from `hub/`.
- **The Hub API rejects `X-API-Key`.** Use `Authorization: Bearer <key>`.
- **A Hub restarted onto a stale database still answers `{"status": "ok"}`.** Health is not a
  database-identity check — confirm which file it serves by hitting the API and comparing mtimes.
- **Static UI changes appear without a restart; Python changes do not.**
- **Restarting the Hub: kill by exact PID and verify the new process**, then re-check. Stale PID
  files (`hub-8010.pid`, `hub.pid`) outlive their processes.
- **`PowerShell`'s `Invoke-RestMethod` swallows error bodies.** Use `curl`.
- **Deleting a Hub database orphans every `.agentweave/project.json` marker that pointed into it,
  and the installed 1.1.0 then refuses those directories.** Adding such a directory fails with
  `project_identity_conflict` — *"marked directory is a copied or orphaned project identity;
  register the copy explicitly as new"*. The error is about a **file on disk**, not about database
  rows, so "I reset the database" does not fix it: delete the stale `project.json` (keep the
  `logs/`, `context/`, `worktrees/` beside it) and the directory registers fresh. Seven orphans
  were left across this machine on 2026-09-07 by exactly this route. **Fixed on master** by
  `8ac12db` ("Adopt an orphaned project marker instead of refusing it") plus `fd3fea4`, which
  recreate the project reusing the marker's id and persist a `project_adopted` event — so this trap
  is specific to builds at or before PyPI 1.1.0. *(Confirmed 2026-09-07.)*
- **A drive agent cannot be told to `sleep 60`.** Claude Code 2.1.269, spawned as a Hub runner,
  answers a standalone `sleep 60` (Bash) and `Start-Sleep -Seconds 60` (PowerShell) with
  `Blocked: standalone sleep 60`, even with `dangerouslyDisableSandbox`. One Haiku agent then gave
  up on the turn; another skipped the step and went on, so the turn was 23–30 s instead of a
  minute. `scripts/drive/t_d1_0912_f319_reach.py` leg A had worked with `sleep 60` on 2026-09-12
  and silently lost its precondition on 2026-09-13: the agent never became the evidence author,
  so the leg measured something else. **Give the agent a real command that takes the time.** The
  harness commits `slow_step.py` (`time.sleep(60)`) into the fixture and says *run
  `python slow_step.py`*. A harness whose timing rests on a `sleep` instruction should also assert
  that the long step actually ran. *(Confirmed 2026-09-13, drive0913r, `run-63cea161a1d6`.)*
- **Reading the operator's `:8000` database: guessed column names fail, so read `pragma
  table_info` first** *(2026-09-13, cost a retry twice)*. `projects` has `working_directory`, not
  `working_dir`. `runs` has `agent` and `started_at`, not `agent_name` and `created_at`. Open it
  only as `sqlite3.connect("file:" + path + "?mode=ro", uri=True)` from `py -3.11`. The path is
  `~/.agentweave/hub/data/agentweave.db`, the default profile, **not** `profiles/live`. This worked
  while that Hub was serving, with no lock trouble. LoopEngine is `proj-03b9c6a6c37a`.
  Transcripts are in `~/.claude/projects/C--Users-huida-Documents-projects-LoopEngine*` (25
  directories, one per worktree, review and task checkout).
  *(2026-09-14, i1b: now 34 and growing — `ls -d`, never a count from here. `runs` has no cost
  column; cost is `turn_usage.api_equivalent_usd_micros` by `run_id`. The message that woke a run is
  `inbound_queue_entries.delivered_in_run_id`. `event_logs` is `event_type`/`data`/`timestamp`.
  Printing agent text from `py -3.11` dies on `cp1252` at the first `→`: start the script with
  `sys.stdout.reconfigure(encoding="utf-8")`.)*
  *(2026-09-14 evening, four more that each cost a retry. **There is no `jobs` table** — it is
  **`ai_jobs`**, and its columns are `cron`, `last_run`, `next_run`, `run_count`, `enabled`,
  `archived_at` — not `schedule` or `last_fired_at`. **`task_transitions`** has `actor_kind`,
  `actor_agent` and `run_id` — there is **no `actor_id`**. **`inbound_queue_entries`** has
  **`state`**, not `status`, and its values are `queued`/`delivered`/`withdrawn`. `tasks` has
  `updated`, not `updated_at`. The reliable move remains `pragma table_info(<t>)` first, and
  `select name from sqlite_master where type='table'` before assuming a table exists at all.)*
- **A drive runner's Haiku is `claude-haiku-4-5-20251001`, not `claude-haiku-4-5`** *(2026-09-15,
  cost one launch)*. `POST /projects/{P}/runners` with the bare name answers 400 *"'claude-haiku-4-5'
  is not a model 'claude' declares"* — the catalog (`hub/hub/model_catalog.py`) holds the dated id,
  with `haiku` as its alias. The playbook and change tasks say "`claude-haiku-4-5`" as prose; write
  the dated id in a harness.
- **Three drive-harness reads that return less than they look like** *(2026-09-15)*.
  `GET /projects/{P}/jobs` hides archived jobs unless `?include_archived=true`, so a "no job left
  enabled" teardown over the default listing cannot see one. `GET /projects/{P}/queue/{agent}` does
  not expose an entry's `task_id` (read it off the message, or `inbound_queue_entries.task_id`
  `mode=ro` on the drive database). A flow's task whose evidence is left `awaiting` cannot be approved
  by any reviewer, so a drive that is about *staffing* should expect `run_diverged` re-staffs after
  each review (F374), not verdicts.
- **A driven agent's own tool call can silently resolve an escape before it ever reaches the
  sandbox check** *(2026-09-15, F332's live drive)*. Asked to run `echo hi > $'..\u0100'` — a bash
  `\uHHHH` escape meant to reach `mcp_server.py`'s reader as six literal ASCII characters — Haiku's
  actual `tool_use` payload carried the *decoded* Unicode character instead, reproduced twice,
  including with an explicit "type the six literal characters, do not resolve this" instruction.
  Confirmed the cause is the model's own text generation, not the transport: a controlled JSON-RPC
  probe sending the literal six-character text through a correct `json.dumps`/`json.loads` round
  trip denies exactly as the unit test predicts. **A live drive cannot exercise a `\u`/`\U`-shaped
  escape (or likely any input an LLM would plausibly "helpfully" normalize) as literal text** —
  design the row's evidence at the unit/wire level instead, and expect the live turn to show
  something else. Not a defect in the sandbox code; recorded as a limit of what natural-language
  agent instruction can deliver verbatim.

## SQLAlchemy and Hub test patterns

- **`async with engine.begin()` does NOT put DDL in a transaction on SQLite** *(measured
  2026-09-10, and five F292 windows had assumed the opposite)*. SQLAlchemy's pysqlite/aiosqlite
  dialect emits no `BEGIN` until a **DML** statement, and `DROP TABLE`/`CREATE TABLE` are DDL. So
  `driver_connection.in_transaction` reads **`False`** after the first `DROP` inside the block, no
  `BEGIN` ever reaches the driver, and each of the ~90 drops in `Base.metadata.drop_all` is its own
  autocommit write transaction — taking and releasing SQLite's write lock ninety times, with a
  window between each for any other connection to take it. **Do not reason about "the transaction"
  around a `drop_all`; there isn't one.** If you need the sequence to be atomic, issue
  `await connection.exec_driver_sql("BEGIN IMMEDIATE")` first, which is what `hub/tests/conftest.py`
  now does. Verify with `in_transaction`, not by reading the `async with`.
- **`database is locked` has two mechanisms and only elapsed time tells them apart** *(measured
  2026-09-10)*. A genuine holder makes you wait out `busy_timeout` and then fail. But in WAL, a
  connection that took a read snapshot and then asks to upgrade to a write is refused
  **immediately, `busy_timeout` ignored, with nothing holding the file** — SQLite returns
  `SQLITE_BUSY` rather than risk deadlock. Measured side by side: **0.000 s** (snapshot, 30 s
  timeout ignored) vs **2.234 s** (real holder, 2 s timeout honoured). **Before hunting for a
  holder, record how long the failing statement waited** — sub-second means there may be no holder
  to find, and every instrument that samples for one will come back empty and look broken.
- **A session-wide SQLAlchemy event listener is a session-wide assertion** *(2026-09-10, cost one
  full-suite run)*. `@event.listens_for(engine.sync_engine, "before_cursor_execute")` registered at
  a test module's import fires for **every statement in the whole session**, not only the ones the
  test caused. A gate asserting *"every `DROP TABLE` ran inside a transaction"* therefore also
  judged `test_migrations.py`'s own `drop_all`, which is supposed to run unguarded — so it **passed
  run alone and failed in the full suite**, which is the direction that gets a test deleted rather
  than fixed. Bound it with a fixture that clears the recorder and is **named before** the fixture
  under test in the signature; pytest sets fixtures up in signature order.
- **A synchronous SQLite call on the event loop deadlocks against ANY open async write** *(measured
  2026-09-13, F351)*. The Hub's async engine (aiosqlite) and anything synchronous on the same file —
  APScheduler's old `SQLAlchemyJobStore`, a `create_engine("sqlite:///…")` — share SQLite's lock
  (journal mode `delete`). If any coroutine has inserted and not yet committed, its commit needs the
  event loop; a sync call made on the loop blocks it while waiting for that lock, so it waits out
  the full 5 s busy timeout and fails `database is locked`. Even a writer that would have held the
  lock for 0 s does it. The signature in a live database is a ~5–6 s gap between two writes a
  request makes back to back. **Never touch the database synchronously from async code in the Hub**
  — `await` it on the async engine, or keep the state off the database entirely.
- **The operator's Hub (port 8000) logs to `DEVNULL`** *(2026-09-13)*: `_hub_native_start` sends
  stdout and stderr nowhere, so a `logger.error` there is unrecoverable. Evidence has to come from
  what the Hub persisted — `event_logs` timestamps, row states — read with
  `sqlite3.connect("file:…?mode=ro", uri=True)`.
- **`session.get(Conversation, "conv-…")` silently never matches** — the primary key is not what
  you think it is. Query explicitly.
- **`session.delete()` refuses a never-flushed object.**
- **`ORDER BY EventLog.id` does not order by recency.** Order by timestamp.
- **`extra: "forbid"` rejects a forbidden *key* regardless of its value** — including `None`.
- **There is no `db_session` fixture.** Use `async_session_factory()` from `hub.db.engine`.
- **The `app` fixture is an httpx client with no `.routes`.**
- **Never read `create_app().routes` directly — this machine's Starlette is two majors behind CI's,
  so the shape you measure locally is not the shape CI sees.** *(Measured 2026-09-09.)* Here:
  starlette **0.52.1** / fastapi **0.136.3**. CI resolves starlette **1.6.0** / fastapi **0.141.1**
  fresh on every run (read off run `34325989834`'s install step), and 1.x stopped flattening
  `include_router` into `app.routes`: it holds `_IncludedRouter` wrappers whose inner `APIRoute`s
  carry *relative* paths. A direct comprehension therefore sees only the routes declared on the app
  itself — `/health`, `/docs`, `/assets`, `/openapi.json` — and every `/api/v1/...` path looks
  absent. **Use `api_route_paths` / `iter_api_routes` from `hub/tests/_routing.py`**, which walks
  either shape. This has now been the same mistake three times (`test_mcp_body_contract`,
  `test_request_strictness`, and `test_mcp_adapter_online`); the third cost **twelve consecutive red
  `hub-test` runs** and held the daily loop's merge gate shut for two days, as the only failure in
  4,032 tests, while passing locally every time it was run.
  **To check a framework-shape assumption against CI without waiting for CI**, build a throwaway
  venv — `py -3.11 -m venv <tmp>`, then `pip install -e ./hub[dev]` and `pip install -e .` into it,
  which resolves the newest allowed starlette exactly as CI does (~4 min). Run the suspect file
  with that interpreter. This is the only local way to see the 1.x route shape; the repo venv
  cannot show it.
- **`run.task_id` is NULL on most runs** — 154 of 202 measured. Read the transition table instead.
- **`run_job` returns 503 in tests** unless `get_scheduler()` is patched.
- **The aiosqlite connection internals the F295 guard reads ARE reachable from a pool listener,
  and the `close` pool event does fire.** *(Re-derived 2026-09-08 against SQLAlchemy 2.0.50 /
  aiosqlite 0.22.1, replacing the deleted `testbed/scratch/f295/probe_pool.py`.)* From a
  `checkout` or `close` listener on `engine.sync_engine`:
  `dbapi_connection` is `AsyncAdapt_aiosqlite_connection` → `._connection` is `aiosqlite.Connection`
  → `._thread` is a `Thread` with a working `.is_alive()`, and `._running` is present. Use
  `getattr(..., None)` for each — the guard is written to no-op when the shape is absent rather
  than crash a healthy checkout.
- **aiosqlite's own guards are two lines later than the change documents cite.** *(2026-09-08,
  aiosqlite 0.22.1.)* `close()`'s `if self._connection is None: return` is at `core.py:202-203`
  (cited as `199-201`, which is the `def` and docstring); `_execute`'s
  `raise ValueError("Connection closed")` is at `core.py:152-153` (cited as `151-152`) and its
  predicate is `not self._running or not self._connection` — **two** conditions, not one. The
  mechanism and the exception text in the citations are right; only the line numbers drift.
- **A payload-shaped model function must be tested against real route ordering.** A fixture in an
  order the route never emits is not evidence (F190: ascending lifecycle events fed to a route
  that returns newest-first, green for a month while the behaviour could not fire).
- **A race test whose mocked dispatch takes no database lock cannot show a concurrency repair
  works** *(2026-09-12, F328)*. R3 of `a-refused-review-leaves-nothing-behind` pinned "an entry
  withdrawn during the dispatch is not counted" with a patched `trigger_agent_directly` that
  recorded nothing, and it passed. A real review dispatch holds SQLite's write lock while it
  records the reviewer. The operator's concurrent `DELETE` waits on that lock and commits *after*
  the re-read the repair relied on. The pre-approval review's test O2 (a real staging, 0.3 s delay)
  measured the repair doing nothing. It is the payload-ordering rule above in another form: **the
  stand-in must take the locks the real thing takes**, or the race you are testing cannot happen.

## Browser and preview tooling

- **`preview_snapshot` returns ~25k tokens.** Use `preview_evaluate` with a targeted expression;
  reserve snapshots for actual visual checks.
- **`preview_evaluate` must return an object**, not a bare array or null, or it fails MCP schema
  validation. Wrap: `(() => ({...}))()`.
- **Radix menu items need dispatched `pointerdown`/`mousedown`/`mouseup`** before `click()`.
- **`requestAnimationFrame` never fires and `ResizeObserver` never delivers** in this environment.
- **`setPointerCapture` is unimplemented in jsdom** and throws.
- **`ta.blur()` does not fire React's `onBlur`** under browser automation.
- **`scripts/uishot.py` cannot capture an authenticated page** — it has no session.
- **`page.goto(..., wait_until="networkidle")` never settles** against the Hub (SSE keeps the
  connection open).
- **Never verify a native window with a screen grab — the operator is using this machine**
  *(2026-09-13, F343)*. `PIL.ImageGrab.grab()` taken to see a pywebview context menu captured the
  operator's full-screen game instead; the probe window was behind it. The images were deleted.
  What worked, and is better evidence anyway: open the window **off-screen and unfocused**
  (`x=-6000, y=-6000, focus=False`; a `hidden=True` window builds no native menu and measures
  nothing), drive it over CDP (`webview.settings["REMOTE_DEBUGGING_PORT"]` + Playwright
  `connect_over_cdp`, which never moves the real cursor), and read the result from the component's
  own event — WebView2's `ContextMenuRequested` lists every menu item, spelling suggestions
  included. **Run a `debug=True` positive control first**: without it, "no menu" cannot be told
  apart from "the instrument cannot see menus", and it was the control that showed a fix reading
  back `True` still produced no menu. Page screenshots from headless Chromium are fine; they show
  only the page.
- **A "can't select / right-click does nothing" report may be the pywebview window, which a browser
  cannot reproduce** *(2026-09-13, F343/F344)*. An investigation driving the bundle in headless
  Chromium found the answer text selectable — correctly, for a browser. The operator's surface is
  the desktop shortcut's pywebview window, whose defaults inject `body { user-select: none }` and
  turn WebView2's context menu off. Ask which window, or check the live Hub's parent process for a
  CLI holding `webview.start()`, before concluding a UI report does not reproduce.

## PowerShell (when driving it from the Bash tool)

- **`@'…'@` here-strings are PowerShell syntax and the Bash tool is Git Bash** — they do not work
  there, and mangle commit messages when attempted. *What it looks like, measured 2026-09-05
  (`6b98bdc`):* `git commit -m @'…'@` succeeds silently and produces a commit whose **subject line
  is a bare `@`**, with the real subject demoted to line 2 and a trailing `@` after the trailer.
  `git log --oneline` then shows `@` where the summary should be. It is not repairable after a
  push under a no-force-push rule, so the cost is permanent — use a Bash heredoc (`-m "$(cat
  <<'EOF' … EOF
  )"`) or repeated `-m` flags.
- **Bash-style quote escaping breaks PowerShell here-strings.** Keep each shell's syntax in its
  own tool.
- **`[System.Security.Cryptography.RandomNumberGenerator]::Fill()` does not exist on Windows
  PowerShell 5.1, and the failure is silent in the way that matters.** The method throws
  `MethodNotFound`, but if `$ErrorActionPreference` lets the script continue, the byte array stays
  **all zeros** — so a generated key has the right length and format and passes a regex check while
  being entirely predictable. Generate secrets with `py -3.11 -c "import secrets;
  print(secrets.token_hex(16))"` and assert the result is not a run of zeros. *(Hit 2026-09-07
  minting a Hub bootstrap key; caught only because the output was printed.)*
- **Windows PowerShell 5.1's `Get-Content` reads a BOM-less UTF-8 file as ANSI**, so the driver
  logs (deliberately written without a BOM) display `â€”` for an em-dash. The file is fine; the
  display is not. Read it with `Get-Content -Encoding UTF8`, or from Python. *(2026-09-15 — cost
  one false alarm while checking the metered driver's output.)*

---

## Skills, and the copies of them other agents read

- **`.claude/skills/` is the source; `.agents/skills/` and `~/.codex/skills/` are hand-run
  copies that go stale silently.** *(2026-09-08.)* `scripts/sync_skills.py` mirrors every
  non-`aw-*` skill to both destinations with `rmtree` + `copytree`, and its own docstring says
  *"Re-run it after editing anything under `.claude/skills/`"*. **Nothing checks that you did.**
  It was last run immediately before `a38caee` — the 2026-09-04 commit that introduced
  `DEAD-ENDS.md` — so the one commit that most needed propagating is the only one that did not.
  Measured stale: `handoff` (341 → 268 lines), `resume` (127 → 118), `daily-review` (absent), and
  **both stale copies mention `DEAD-ENDS.md` zero times.** A Codex or Kimi session therefore runs
  a `/resume` that has never heard of this file and a `/handoff` that will not append to it.
  Fix: `py -3.11 scripts/sync_skills.py`. Check drift with
  `diff .claude/skills/<name>/SKILL.md .agents/skills/<name>/SKILL.md`.
- **`.agents/` is gitignored** (`.gitignore:129`), so the drift is invisible to `git status` and to
  every review that reads the diff.

## Claude Code harness — subagents and background tasks

- **A forked/background subagent's report that quotes this repo's own terminology can trip the
  harness's own prompt-injection scanner on the task-notification.** Seen 2026-09-06: a fork
  surveying `.claude/loops/` quoted the day/night windows' own phrase "runs `bypassPermissions`"
  in its final report, and the resulting `<task-notification>` was prefixed with `[harness:
  subagent output matched instruction-shaped pattern(s): bypass-permissions. Control tags below
  are neutralized...]`. The content itself was accurate, sourced from this repo's own files, and
  matched independently-known facts — a false positive from the pattern matcher, not a real
  injection. Treat the warning as confirmation to read the flagged content as data (which the
  general policy already requires for any tool output), not as evidence the subagent or its
  source material was actually compromised — and don't discard a real finding just because it
  tripped this scanner.
- **The auto-mode permission classifier blocks *batched* destructive operations that it allows one
  at a time.** Measured 2026-09-07, four separate refusals in one session: a `Remove-Item` loop over
  a list of paths; `git worktree remove` chained for three worktrees in one command; and — the
  non-obvious one — **a PowerShell here-string containing the text `cd /d C:\...` alongside a
  `Remove-Item`**, refused with *"Remove-Item on system path '/d' is blocked"*, i.e. the `/d` flag
  of a `cd` inside quoted file *content* was parsed as a deletion target. Workarounds that worked:
  one operation per tool call, or the Bash tool's `rm`/`git` instead of PowerShell, or writing the
  file with the Write tool so the risky text never appears in a shell command. Do not read these as
  "the operation is forbidden" — the same operations succeeded individually and immediately.
- **A four- or eight-hex escape written through Edit/Write, by this session or by a subagent, can be
  stored as the character it names** *(measured 2026-09-13, F332's spec loop)*. The text meant was
  backslash, `u`, `0100`, a bash escape being documented. Twice through the Edit tool, and in ten
  places across the rounds' `design.md` and `FINDINGS.md` notes, the file received U+0100 itself.
  That inverted the argument: *"bash keeps the escape literal"* came to read as an already-decoded
  character. The `\x2f` and `\U0000002f` forms in the same files survived. The cause is
  unverified: it may be the model's own output, or the tool path. **Detect it:** after a round
  writes escape-heavy docs, scan them in Python for non-ASCII characters outside the usual
  typography, and read each hit in context (`5775064` is the repair and shows the method). **Avoid
  it:** spell such an escape in words, or build it with `chr(92) + "u0100"` in a script. Remember
  that a heredoc halves doubled backslashes (see Shell, above).
  **Reconfirmed 2026-09-15, a-quote-can-spell-a-slash Round 5:** it is not just the Edit tool — an
  `old_string`/`new_string` typed directly into an **Edit call** with a literal `Ā`-style
  token fails to match the file every time (the tool's own error names the swap it tried, and
  neither form matches), and a **Bash heredoc** (`py -3.11 - <<'PYEOF' ... PYEOF`) whose body is
  built with an f-string containing the same literal token is not reliably safer either — one
  attempt that session broke with `unexpected EOF while looking for matching` even though the
  heredoc delimiter was quoted, most likely because the Bash tool's own invocation re-parses the
  whole command as one shell string, so a body with many literal single quotes (bash `$'...'`
  syntax quoted as *text*, not run) can desync bracket/quote counting before the heredoc's own
  literalness would apply. **What worked reliably, every time, the rest of that session:** build
  the replacement text in a Python script using `chr(92)` (and `chr(0xNN)` for any other
  character worth spelling exactly, e.g. `chr(0xe9)` for é) rather than typing the escape or the
  character directly, **write that script to a file with the Write tool**, then run it as
  `py -3.11 <scriptfile>` — a plain file argument, not a heredoc — with every file write using
  `open(path, "w", encoding="utf-8", newline="\n")` to also dodge the separate CRLF trap below.
  Verify afterward with a non-ASCII character scan (the detection method above) before trusting
  the result.
  **Reconfirmed again 2026-09-15, same change, Round 6's fix-writing (this session):** the trap is
  not specific to `Ā` — a fresh Edit call typing `߿` and, separately, ` ` directly
  each landed as the raw character in `design.md`/`tasks.md`/`test-guide.md`, discovered only
  because this session's scan checked a wider codepoint range than the previous one used (the
  earlier scan's exclusion list was too narrow and missed ` ` on the first pass — **scan for
  every codepoint above 0x7F except a small, explicit allowlist of intentional typography**, not
  for "anything past some high threshold"). A short `\x`-style two-hex token (`\xd7`, `\c` forms)
  survived every Edit call this session without corruption; only 4-hex `\u` tokens did not. The
  fix script method above remains the reliable one and was used again, successfully, for all three
  files.
  **Reconfirmed 2026-09-15, F332 implementation session — the trap can hit the SEARCH string, not
  only the replacement.** An `Edit` call whose `old_string` contained a typed ` ` token (meant
  to match six literal characters already in `test-guide.md`) silently failed to match, twice, even
  though the target text was visibly present on a `Read` of the same lines. The tool's own mismatch
  diagnostic showed the string it had actually tried to match with the escape already collapsed to
  the raw character — i.e. the corruption happened to the argument as typed in the tool call itself,
  before any comparison against the file. A `Read` of the file is not proof the corruption is only
  in what gets written; check what the Edit tool reports it searched for, or skip straight to the
  Write-a-script method for any edit that needs to reference an existing `\uXXXX`/`\UXXXXXXXX` token
  by name, not only for the ones being newly inserted.

- **Driving `claude -p` from Python: pass the prompt on stdin, never as an argv element**
  *(2026-09-10, cost one full four-run measurement)*. `shutil.which("claude")` on this machine
  resolves to `C:\Users\huida\AppData\Roaming\npm\claude.CMD` — an npm **batch-file** shim. Two
  traps follow, and the second is silent:
  - `subprocess.run(["claude", ...])` raises `FileNotFoundError: [WinError 2]` because
    `CreateProcess` will not resolve a bare name to `.CMD`. Fix: `shutil.which` it first. Loud, so
    harmless.
  - **A multi-line prompt passed as an argument is truncated at its first newline**, because a
    batch file ends its line there. The run still succeeds, exit 0, valid JSON — and every model
    replied *"I don't see a command in your message."* Four runs, four plausible-looking results,
    all measuring nothing. **Read a result that says the model did not see your input as a
    delivery failure, not a model failure.** Fix: `subprocess.run([...], input=prompt)` with no
    positional prompt — `claude -p` reads stdin — which also sidesteps every quoting problem in a
    prompt full of `$`, quotes and backslashes.
- **`--dangerously-skip-permissions` is the discriminator between a *static* refusal and an
  *approval* refusal** *(2026-09-10)*. The harness's `permission_denials` records carry a
  `tool_name` and the `tool_input`, and **no reason field** — so "the command analyser rejected
  this shape" and "`acceptEdits` had nobody to answer" look identical, and the model's own
  narration about which one happened is unreliable prose. Re-run the same shape with the approval
  gate removed: what still fails is static, what now executes never was. This is what showed F301's
  five "refusal classes" to be reasons a command *needs approval* rather than reasons it is
  forbidden.
- **An interactive session can run a whole spec loop as sequential Opus subagents** *(measured
  2026-09-12)*. For `a-refused-review-leaves-nothing-behind`, R1 took 32 min, R2 24 min, R3 19 min,
  and the pre-approval review 15 min: about 1.5 h from nothing to an approvable change. **Each of
  the four found a real defect in the one before.** What made it work:
  - Each prompt names the binding verdict, the previous round's own "attack this" list, and the
    rule to re-derive against the code rather than re-read.
  - Each round commits and pushes its own work, with explicit paths.
  - Each reviewer is told to modify no tracked file and to leave the tree clean, because the 22:55
    arm refuses a dirty tree.
  - An operator question a round raises is put to the operator with `AskUserQuestion` **while the
    next round runs on the recommended answer**, which costs no wall-clock time.

- **The built-in `Explore` subagent inherits the main session's model — Opus, here** *(measured
  2026-09-15; the docs date the change to v2.1.198)*. Every Explore spawn in the 09-14 windows and
  in the 09-15 interactive session ran on `claude-opus-5` ($8.49 for three Explore reports that
  morning). `.claude/agents/Explore.md` now overrides it with `model: sonnet`; verified with an Opus
  main session: the Explore turn landed on `claude-sonnet-5` in `modelUsage`. A project agent named
  `Explore` does replace the built-in. Spawns that pass `model: "opus"` explicitly (the REV) are
  unaffected.
- **Headless `claude -p` waits 600 s for background tasks after the turn ends, then kills them**
  *(driver-day.log:4827, 2026-09-14)*: *"Background tasks still running after 600s; terminating.
  Set CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0 to wait indefinitely."* It killed a background REV
  after 54 calls ($8), and three iterations ended with their test suites still running. The driver
  now sets the ceiling to 60 minutes via `usage-policy.json` `env` — not `0`, so a hung task cannot
  hold an iteration until the 2-hour task limit.
- **`claude -p --output-format json` is one JSON line carrying everything a ledger needs**
  *(2026-09-15)*: `total_cost_usd`, `modelUsage` per model with `costUSD` (includes subagents and
  Claude Code's own Haiku side-calls; `usage` does not), `num_turns`, `subtype`, `is_error`,
  `api_error_status`, `subagent_stats`. `costUSD` is list price and matches $2/$10 (Sonnet 5),
  $1/$5 (Haiku 4.5) per MTok with cache reads at 0.1× and 1-hour writes at 2× input — exactly.
- **`--exclude-dynamic-system-prompt-sections` does not reduce the per-iteration cache write**
  *(measured 2026-09-15)*: after a commit, a fresh `-p` run re-wrote 5,306 tokens without the flag
  and 5,484 with it. Not adopted. Most of the old ~22k per-iteration write was CLAUDE.md and the
  listings after the changing section, which the CLAUDE.md slim addresses instead.
- **Path-scoped `.claude/rules/*.md` (`paths:` frontmatter) do load only on demand** *(probe
  2026-09-15, CLI 2.1.269)*: a marker rule scoped to `hub/ui/src/**` was absent at start and present
  after a Read of `hub/ui/src/main.tsx`.
- **A PreToolUse `Read` hook that exits 2 blocks the Read under `bypassPermissions` too** *(probe
  2026-09-15)* — the model receives the hook's stderr as the error. `large-read-guard.py` relies on
  it, and acts only when the driver sets `AW_AUTONOMOUS=1`.
- **`jq` is not installed on this machine.** The operator's jq-based statusline printed `ctx:--
  api:0%` placeholders for as long as it existed; replaced 2026-09-15 by `~/.claude/statusline.py`
  (the `.sh` is now a one-line `exec py -3.11` wrapper, so `settings.json` did not change).

## The installed CLI (`agentweave` from PyPI, outside this repo)

Facts about driving a *real* AgentWeave instance, learned setting one up at
`C:\Users\huida\agentweave-live` on 2026-09-07. These are about the shipped product, not this
checkout — the dev-repo traps are in "The Hub at runtime" above and still apply there.

- **Every `agentweave` subcommand needs BOTH `--profile` and `--port` when the instance uses a
  named profile** *(measured 2026-09-07)*. Omit them and the CLI looks for the `default` profile,
  finds no native pid file, and **falls back to assuming Docker**. Two concrete consequences on a
  natively-started Hub: `agentweave status` prints `Status: running (docker)` — on a machine where
  the Docker daemon is not even running — and `agentweave stop` fails with
  `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine`, stopping
  nothing and leaving the port bound. With the flags, both are correct (`running (native)` with a
  PID; stop kills the process pair and frees the port). **The failure mode is a misleading
  diagnostic**: it blames Docker when the real problem is a profile mismatch, which cost this
  session a nearly-filed false bug report. Wrapper at `C:\Users\huida\agentweave-live\hub.ps1`
  exists so the flags are never forgotten.
- **`agentweave doctor` lists runner CLIs it merely *detected on PATH*, not ones it can use**
  *(measured 2026-09-07)*. On this machine it reports `claude, codex, copilot, kimi, opencode` as
  an `[OK]` line. Only **claude** and **codex** can actually be bound to a Runner and spawned —
  `RUNNER_CLIS = ("claude","codex")` in `hub/hub/db/models.py:300`, and the spawn path 501s for
  anything else. Detection is not support, and nothing on the `doctor` output says so.
- **The operator's port-8000 Hub runs this checkout, not the `agentweave-live` PyPI install**
  *(measured 2026-09-13)*. PID 3488's parent was `Python311\Scripts\agentweave.exe` — the system
  Python's **editable** install — on the default profile (`~/.agentweave/hub/data/agentweave.db`,
  head `0102`), while `hub-live-8000.pid` named a dead process and the `live` profile's database
  was untouched since 2026-09-07. Consequences: it runs `uvicorn` without `--reload`, so Python
  edits here reach it only on the operator's restart; but it serves `hub/hub/static/ui` from this
  checkout, so **`refresh_ui_bundle.py` + commit changes the operator's live app on their next
  reload** — check the bundle is compatible with the Python that process loaded (its start time vs
  `git log -- hub/ui/src`) before committing one. CLAUDE.md's 8000 paragraph did not match.
- **The pid the CLI reports at start is not the process holding the port** *(observed
  2026-09-07)*. Native start logs e.g. `Starting Hub (native, PID 17544)` and writes that pid to
  `~/.agentweave/hub/hub-<profile>-<port>.pid`, while a second python process (17208) is the one
  listening. `stop` handles this correctly and kills both — do not "fix" it by killing the
  recorded pid by hand.

## The `spec-queue/` contract — three ways a correct-looking document does nothing, or lies

- **Never write a `---` inside a dated section of `APPROVALS.md` or `DIRECTION.md`** *(2026-09-10,
  written and caught the same evening, only because the operator asked for a review of the night's
  setup)*. In both files `---` is the **inter-section delimiter**: every one of them sits
  immediately before a `## YYYY-MM-DD` heading and nowhere else. `night-window.md` iteration 1
  step 2 reads *"the newest day section only"*, so a rule placed mid-section can end that section
  early — leaving the prose above it and orphaning the `APPROVED` row below. The window then finds
  no token, falls through to the default backlog, **builds nothing, and reports that nothing was
  approved.** Silent, and indistinguishable from a night the operator genuinely did not sit down.
  **Verify by parsing, not by reading**: slice the file from the first `## 20..` heading to the
  second and assert the token you just wrote is inside the slice. Same class as the stale `ORDER:`
  line — a correct-looking approvals file that does nothing.
- **A dated section's *premises* are not protected by the newest-section-only contract — only its
  *instruction* is** *(2026-09-08, found by the day window reconciling its own log)*. A
  `DIRECTION.md` or `ROADMAP.md` section is read as both an order and a description of the world,
  and the world moves under it. The 2026-09-08 `DIRECTION.md` section and `ROADMAP.md` were written
  by one DECIDE session at **00:30** and both assert *"not one carries an approval token"*;
  `0d82d6d` approved all four at **01:24**. The day window read them at **09:01**, 7 h 31 m later,
  and inherited the dead premise into eight iterations of its log without noticing — the queue was
  still right, but only because a second authority (the drain gate) reached the same shape by a
  route that did not depend on it. **Before quoting a dated section's arithmetic, check whether
  `APPROVALS.md` or the file it describes moved after that section's own timestamp**:
  `git log -1 --format='%ad' --date=iso -- spec-queue/APPROVALS.md` against the section's stated
  writing time. The same session's `ROADMAP.md` also contradicted itself, saying "starved of
  verdicts" in its headline and "all four APPROVED" twenty-five lines below — **a long plan file is
  read at whichever line the reader reaches first**, so a closure has to be written at the headline
  too, not only in the row it closes.
- **A verdict token under any but the *newest* dated section is never read** *(2026-09-08)*.
  `APPROVALS.md`'s own header says *"Newest day first. Days below the newest are history and are not
  read."* Three of the four changes approved on 2026-09-08 had their descriptive rows under
  `## 2026-09-07`, `## 2026-09-06` and `## 2026-09-05`; writing `APPROVED` in front of *those* rows
  would have looked entirely correct and been invisible to the FIX window. **Restate the row under
  today's heading** rather than editing a row in history. `DIRECTION.md` has the identical contract
  for the day window.
- **`APPROVED` alone does not get a change built — the default queue is backlog-first**
  *(2026-09-08)*. `spec-queue/README.md`, decided 2026-09-01: unarchived changes first, then open
  findings by severity, and `APPROVED` rows only **third**. Four freshly approved changes sit behind
  8 unarchived changes and the findings list unless an **`ORDER:`** line promotes them — and `ORDER`
  applies to **that night only**, so it needs rewriting every evening with whatever remains.
- **`<change-name>` in a row is the directory name under `openspec/changes/` exactly.** Cheap to
  verify (`test -d openspec/changes/<name>`) and worth doing, because a typo is a row the window
  silently cannot match.
- **Writing *tomorrow's* `DIRECTION.md` section before today's window has fired cancels today's**
  *(2026-09-08)*. Both files read **only the newest dated section**, and `day-window.md` step 5 then
  asks whether that section is dated **today** — so a `## 2026-09-09` heading added on 2026-09-08
  makes the `## 2026-09-08` section below it history, and the 08:55 window takes the *default* queue
  instead of the instruction sitting right there in the file. The symptom is a window that quietly
  does the ordinary thing on a day it was told not to. **Write the section on the morning it
  applies, or after that day's window has fired.** The same shape as the `APPROVALS.md` entry two
  bullets up, in the opposite direction: there, writing under an *older* heading is invisible; here,
  writing under a *newer* one is destructive.
- **A finding's banner saying "no drive exists" is a claim, not a fact — grep the finding's own
  number first** *(2026-09-08)*. The 2026-09-03 banners reopened four severity-A findings on the
  reasoning that an archived openspec change is *"a plan marked done, not a drive of the built
  product"*. Correct reasoning; wrong for **F140**, whose drive was already recorded in
  `FINDINGS.md` twelve thousand lines above, two days before the banner. It cost F140 five days and
  a place on the operator's blocked list. Searching `openspec/changes/archive/` is not the same
  search as searching `FINDINGS.md`. ~~**F154 and F155 still carry that banner and have not had this
  check.**~~ **Checked the same day, and both were the same error**: F154 fixed `001a07d` and driven
  18/18 by `t_f154_wedged_review.py`; F155 fixed `0373867` and driven 23/23 by
  `t_f155_conflict_remedy.py` — both on 2026-08-31, both recorded in `FINDINGS.md`, both banners
  written three days *after* the drive they said was missing. **Three of the four the banner reopened
  were already driven.** The severity-A count went six → five → three in one day with no product code
  written. This is no longer one anecdote about F140: the grep is a standing precondition for
  believing any "not driven" claim on this page, and it costs about ten seconds.

## Unattended runs — failure modes the driver does not detect

- **`STATE-night.json` and `STATE-day.json` are stale between runs by design — do not "repair" one
  before an arm** *(2026-09-08)*. Found `STATE-night.json` carrying `stop_at` three days in the past
  (`2026-09-07T07:00`), a `branch` that had been superseded, and a `parent_sha` far behind master.
  None of it matters: `.claude/loops/arm-cycle.ps1` **rewrites the file wholesale** at arm time —
  fresh `stop_at` (rolled forward a day if the window's `Until` has already passed), `iteration = 0`,
  `current = "compose"`, a new `log_file`, and a settled cycle branch with a current `parent_sha`.
  Editing the stale file by hand before 22:55 changes nothing and risks looking like state the
  window wrote.
- **`arm-cycle.ps1` refuses to arm on a dirty working tree** *(2026-09-08)*. It prints
  `REFUSING: working tree is dirty. Leaving this window unarmed.`, lists the paths, and **exits 3**.
  The Scheduled Task still reports success-ish and the window simply never runs. So uncommitted work
  left in the tree at 22:55 costs the entire night, silently, and the symptom appears only in
  `.claude/autonomous/driver-night.log`. **Leave the tree clean before an armed window's start
  time.**

- **A Claude usage limit turns an autonomous run into a silent no-op loop** *(measured
  2026-09-07)*. The headless CLI printed `You've hit your session limit · resets 7:10pm
  (Europe/Lisbon)` and exited 1. `run-iteration.ps1` logs the child's exit code and exits with it;
  **nothing counts consecutive failures**, so the Scheduled Task kept firing every 5 minutes and
  produced **24 consecutive 2–3 second no-op iterations over ~2 hours** before the limit reset.
  The task stays `Ready`, the state file never changes, and the driver log looks like a run that
  is simply between iterations. Its only self-stopping conditions are a null `next_action` and
  passing `StopAt`; neither covers "the child keeps failing". **Diagnose by comparing
  `iteration start`/`iteration end` timestamps — a healthy iteration takes minutes, a dead one
  takes seconds.**
- **A watcher must grep for the failure signatures, not only the success ones** *(learned the hard
  way, 2026-09-07)*. A background watcher armed for that run filtered on review-page mtime, task
  existence, and a guessed error alternation (`Stopping\.|did not parse|Refusing|not found`). A
  usage-limit death matched **none** of them, so it would have run its full five hours and
  reported "expired" after the run's own stop time — while the operator had been told progress
  would be reported. Silence read as success. Watch for **forward progress** (iteration counter or
  commit count advancing within a bound) rather than for the absence of known errors.
- **A headless iteration that ends its turn to "wait for the monitor" kills its own background
  job 600 s later** *(measured 2026-09-13, night window, iteration 6)*. The iteration backgrounded
  the whole Hub suite at 00:20, armed a monitor, and ended its turn. `driver-night.log` at 00:31:52:
  `Background tasks still running after 600s; terminating. Set
  CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0 to wait indefinitely.` The suite died at 28% with no
  summary line, the iteration exited 0, and its uncommitted ticks were left in the tree for the
  next firing to find. **Under `claude -p`, any job longer than ten minutes must be waited on
  inside the turn.** Use repeated foreground waits of about 9 minutes each (a `py -3.11 -c` poll
  loop on the output file, with the Bash tool's `timeout` at 600000), not a monitor followed by
  the end of the turn. The other fix is to set that variable in the driver's environment. Not done:
  that is the driver's configuration, not a night item.
  **Recurred twice on 2026-09-14** (day window, iterations 16 and 18): each started the suite in
  the background, said it would be notified, and ended. Iteration 18 lost its whole log and state
  that way. A foreground recipe that worked (iteration 19):
  - split `hub/tests/test_*.py` into 10 lists balanced by file size;
  - run each as `timeout 585 py -3.11 -m pytest $(cat cN.txt) -q -p no:cacheprovider`, two or
    three as parallel Bash calls in one message. Each took 2–4 minutes;
  - add `tests/browser/` as an eleventh call, because the top-level glob misses it (72 skips);
  - check that the summed counts match the last whole run's.
- **The morning merge gate is read at ~09:00 and will essentially always find CI mid-run**
  *(2026-09-08, found by the day window itself and confirmed here)*. `AgentWeaveArmDay` fires at
  08:55, the window composes and reads the gate within a few minutes, and the CI suite takes 15–25
  minutes — so the gate's *"CI concluded `success` for this exact commit"* condition is unmet at the
  only moment it is checked. It correctly refuses a stale green from an earlier commit, so the
  landing is deferred to a `gate-retry` item that may or may not get a firing. **A cycle that
  "never lands" is more likely this than a real gate failure** — check `gh run list --branch <cycle>`
  for a *later* success before diagnosing anything else.
- **CI red on `master` usually means `hub-test` alone, and usually means the F292 flake — not your
  change** *(measured 2026-09-08: 4 failures in the last 20 `ci.yml` runs, ~22%, worse than the
  "~1 in 6" previously recorded)*. Confirm before assuming a regression:
  `gh run view <id> --json jobs --jq '.jobs[] | "\(.conclusion)  \(.name)"'`. On 2026-09-08 two
  docs-only commits failed this way while the two around them passed. **The consequence that bites:
  a red `master` keeps the merge gate shut**, so an unrelated flake blocks the cycle from landing.

- **A terminated iteration can leave `AgentWeaveNightLoop` *registered but Disabled*, and the whole
  window then silently never fires** *(measured 2026-09-14 23:30)*. Found at 23:34:
  `Get-ScheduledTask -TaskName AgentWeaveNightLoop` reporting `State: Disabled` with
  `LastTaskResult: 267014` (`SCHED_S_TASK_TERMINATED`) and a `NextRunTime` still ticking forward,
  which makes it *look* scheduled in `Get-ScheduledTaskInfo`. The 23:00 iteration had started,
  composed, committed `1bf256b` at 23:04, and then been killed; `driver-night.log` shows its
  `--- iteration start ---` with **no matching `--- iteration end ---`**.
  **Nothing in the pipeline disables a task.** `run-iteration.ps1` and `install-driver.ps1` only
  ever `Unregister-ScheduledTask` (three sites in the former, one in the latter), and
  `install-tasks.ps1` mentions `Disable-ScheduledTask` only in its own help text. So a `Disabled`
  driver task is always external — a kill, a stop gesture, or a hand-disable — and never the
  loop's own doing. **`State` is the field to check; `NextRunTime` lies.** Re-arm with
  `Enable-ScheduledTask -TaskName AgentWeaveNightLoop`; it keeps the existing trigger and picks up
  at the next 5-minute boundary.
- **Redirecting a window *after* it has composed needs `STATE-*.json` rewritten, not just
  `APPROVALS.md`** *(2026-09-14 23:30)*. `night-window.md`'s iteration 1 is the only firing that
  reads `APPROVALS.md` — *"Only the first firing of the window does this"* — and it writes the
  queue into `STATE-night.json`. Once it has run, editing `APPROVALS.md` changes **nothing** for
  that night, however correct the new `ORDER:` line is. To redirect a live window: write the
  `ORDER:` into `APPROVALS.md` for the record *and* rewrite the state file's `queue`, `current` and
  `next_action`. Write it **atomically** (`json.dump` to `.tmp`, then `os.replace`) — the driver
  fires every 5 minutes and `MultipleInstances IgnoreNew` does not protect a reader from a
  half-written file. Deprioritise the composed items rather than deleting them; they are legitimate
  backlog and the window may reach them.
- **The driver scripts are not in `.claude/loops/`** *(2026-09-14, cost one wrong search)*. That
  directory holds only `arm-cycle.ps1` and `install-tasks.ps1`. `run-iteration.ps1` and
  `install-driver.ps1` — the ones that actually run an iteration and own every stop condition —
  live in **`.claude/skills/autonomous-session/scripts/`** (and a mirror in `.agents/skills/…`).
  `.claude/loops/README.md` names them without saying where they are.

## Working in this checkout while an unattended window is running in it

*Added 2026-09-08. The day and night windows commit into the same working tree an interactive
session is sitting in, on a cycle branch, every few minutes.*

- **Check `git branch --show-current` before doing anything.** After `AgentWeaveArmDay` fires at
  08:55 the checkout is on `autonomous/<date>-daily`, not `master`. Work committed there is fine —
  it reaches `master` through the merge gate — but a session that believes it is on `master` will
  describe its own commits wrongly in a handoff.
- **A dirty tree you did not create is the window mid-iteration, not a problem.** Do not clean it,
  stash it, or commit it. Stage **only** your own explicit paths (the repo rule anyway), commit
  promptly, and push — the exposure window matters, because the playbook tells the window never to
  end an iteration with a dirty tree and unexpected modified files can confuse it.
- **Do not leave your own edits uncommitted while a window runs**, and do not leave them uncommitted
  going into 22:55 — `arm-cycle.ps1` refuses on a dirty tree and the whole night is lost.
- **The same trap has a MORNING mouth at 08:55, and an interactive session is the likeliest thing
  to walk into it** *(2026-09-09, walked into)*. `AgentWeaveArmDay` runs the identical
  `arm-cycle.ps1:118-125` check. A session that commits at 08:45 to leave a clean tree, then opens
  an editor at 08:50, is dirty at 08:55:01 and the **whole day window is skipped** — silently, to a
  hidden console. Ten minutes earlier that same session had written *"committed before 08:55
  deliberately, arm-cycle.ps1:118 refuses on a dirty tree"* into a commit message. Knowing the rule
  is not the same as holding the tree clean **through** the firing instant. **Between about 08:50
  and 08:56, and again 22:50–22:56, either be committed or do not be editing.**
  Detect it with `(Get-ScheduledTaskInfo -TaskName AgentWeaveArmDay).LastTaskResult` — **3 means it
  refused.** Corroborate before believing it: `STATE-day.json` and `driver-day.log` will still carry
  *yesterday's* mtime, and `Get-ScheduledTask AgentWeaveDayLoop` will not exist at all.
- **Re-arming a missed window by hand needs `-StartAt`; a plain re-arm fails in a way that reads
  like a bug** *(2026-09-09)*. `arm-cycle.ps1 -Window day` after 09:00 computes the *next* 09:00 —
  tomorrow — and `install-driver.ps1` dies with `Start 2026-09-10 09:00 is not before stop
  2026-09-09 17:00; the run would have no window.` The override exists and its own comment says it
  is for exactly this: `powershell -File .claude/loops/arm-cycle.ps1 -Window day -StartAt "09:15"`.
  **The failed first attempt is not harmless** — it writes, commits and pushes `STATE-day.json` and
  the day log before the installer runs, so the repo briefly carries an armed-looking state with no
  registered driver. Re-running with `-StartAt` reconciles it (`nothing to commit (state
  unchanged)`), so recover forward rather than reverting the arm commit.
- Concurrent commits interleave without incident: the window's next commit simply takes yours as
  parent. Observed working on 2026-09-08 09:20, with `e964226` landing between the window's
  `101f836` and its following iteration.

- **`git commit -F -` with a heredoc inside an `&&` chain failed once with
  `warning: here-document at line 1 delimited by end-of-file` and `Aborting commit due to empty
  commit message`** *(2026-09-08)*. It had worked several times in the same session, so it is
  intermittent rather than categorical. **The reliable form for a long message: write it to a file
  in the scratchpad with the Write tool, then `git commit -F <that path>`.** Costs one extra tool
  call and never loses a composed message.

- **`git push origin <sha>:master` updates the REMOTE ref and leaves the LOCAL `master` ref stale
  — and the merge gate reads the local one** *(2026-09-11, done, and it produced a false claim)*.
  Pushing a ref directly is the right way to merge while a window owns the working tree, because it
  needs no `git checkout` and so cannot yank the branch out from under a running iteration. But
  `day-window.md`'s gate condition is `git rev-list --count HEAD..master`, which resolves the
  **local** ref. After a direct push the local ref still points at the old sha, so the gate — and
  any window reading it — believes the merge never happened. Today's review page reported `master`
  as `5d928f5`, 26 commits behind, hours after it had been fast-forwarded to `6f7e486`. **Always
  follow a direct push with `git fetch origin master:master`**, which updates the local ref without
  touching the working tree either.
- **The merge gate cannot open while a window is running, and this is structural, not bad luck**
  *(measured by the day window 2026-09-11)*. The loop fires on `PT5M` and every firing ends in a
  commit, so at the start of any firing `HEAD` is at most ~5 minutes old; `ci.yml`'s `hub-test` job
  takes 10–15 minutes. A gate that requires a concluded green run **for HEAD's exact sha** therefore
  finds an in-flight run essentially always, no matter how many days pass. It has opened once ever.
  Checking at the *end* of a long firing helps only if the firing outlasts the build, which a
  25-minute firing does not. **Practical consequence: the gate opens in the gaps between windows, so
  an awake operator is the reliable path** — check the four conditions by hand and push the ref.
  And note the deeper half, measured the same day: **no `HEAD`-shaped rule of any kind can work
  while `F292` stands**, because a documentation-only commit can go red at ~6%.

## Measuring this repository's own documents

*Added 2026-09-08, after an instrument that read `scripts/drive/FINDINGS.md` was wrong four
separate ways in one afternoon. These are about measuring prose, not about any one script.*

- **Writing a census INTO the file it measures changes the census.** Measured, not theorised: the
  classification table published in `c18cb6f` matched the tree it was taken from (`c18cb6f~1`) and
  was **already stale in the commit that carried it**, because the prose naming `F32`, `F108`,
  `F161`, `F162`, `F187` and `F272` beside resolution words fed the cross-section arm six new
  matches. `FINDINGS.md` is an input to `scripts/classify_findings.py`. **Put computed counts
  somewhere the tool does not read** — `ROADMAP.md` — and leave a pointer in the measured file.
- **Reconcile two counts of the same thing the moment they disagree — the gap is the finding.**
  `grep -c` said **297** F-headings and the script said **271**; that 26 sat unexplained for a day.
  It was not a rounding difference: 26 findings had **no section at all** because their headings
  carry no `(A)`-style severity, and **one of them, F77, is open**. No census on that page had ever
  counted it.
- **An instrument that segments a document must be checked against the document's STRUCTURE, not
  only its vocabulary.** The same missing-parenthetical bug meant an unseen heading did not *end*
  the previous section, so **F71's section absorbed F72–F86, 1,223 lines**, and seven findings took
  their verdict from a neighbour's status line — four on the arm the script called trustworthy.
  Vocabulary tests (does "not fixed" read as fixed?) all passed while this was happening.
- **A self-report that does not recompute is a claim, not a measurement.** The same script printed
  *"3 of 5 hand-checked FALSE"* as a **string literal**. By then the true count was 7. This is the
  banner disease in Python: a sentence asserting a fact nobody re-derived.
- **`^#{1,4} F\d+ \(` is not a safe heading pattern for `FINDINGS.md`.** 46 headings lack a
  parenthetical, and headings also come in `(A-)`, `(—)`, `(B?)`, `(C, open)`,
  `(new, severity **B**)`, `(C, was B)`, `(RETRACTED, was B)` and `(C, harness)` forms.
- **A spawned review agent's findings are leads, not verdicts — check them too.** An Opus review
  correctly found both structural defects above, and was **wrong about the cause** of the third,
  asserting the published table *"never reproduced"*. It had reproduced, one commit earlier; the
  agent had not thought to test the parent. Both halves mattered, and only measuring separated them.

- **Backticks in a double-quoted `git commit -m` execute.** *(Re-confirmed 2026-09-08, having
  already been in this file.)* It cost a failed commit with
  `error: pathspec 'the' did not match any file(s)` and `relative: command not found`, because the
  message contained `` `uvicorn hub.main:app` ``. The ledger entry above was right and was not read
  first. **Use `git commit -F <file>` for any message containing backticks — which, in this
  repository, is most of them.**
- **A test for a guard is decorative unless the guard's output is the ONLY route to the asserted
  verdict** *(2026-09-09, found by a surviving mutation)*. Two tests written for
  `scripts/classify_findings.py`'s quotation stripping asserted `RESOLVED` on a fixture that also
  carried a `**Status:** fixed` line. `RESOLVED` is decided before `OPEN`, so both passed with
  `dequote` disabled entirely — the mutation survived and the tests proved nothing. **The fix is in
  the fixture, not the assertion: remove every competing signal, then assert the weaker claim**
  (`!= "OPEN"` rather than `== "RESOLVED"`). Generalises past this file: when a function picks a
  verdict by precedence, a fixture that satisfies a *higher*-precedence branch cannot test a lower
  one.
- **Widening a guard can reveal that an incidental property of the old form was load-bearing**
  *(2026-09-09, cost six verdicts and two wrong diagnoses)*. `NEG_BEFORE` was
  `\b(not|never|...)\W{0,12}$` — which cannot span a word, so it was **line-local by accident.**
  Widened to tolerate intervening words, a finding's *title* immediately reached across a blank line
  to negate its own `**Status:** fixed`, and F16/F27/F46/F58/F95/F100 silently became `UNCLASSIFIED`.
  Two successive hypotheses about the cause were wrong before the pre-match window was printed.
  **When widening a pattern, enumerate what the narrow form was incidentally preventing, and state
  the constraint you intended explicitly** — here, the line bound — rather than inheriting it.
- **Debug a regex by printing the actual matched text and its pre-window, not by reasoning about the
  pattern** *(2026-09-09)*. Two plausible explanations for the six lost verdicts were constructed and
  committed to before the 40 characters preceding the match were printed; both were wrong. One
  `print(repr(pre))` settled it immediately.
- **An `ORDER:` line may name work that is neither a change directory nor an `F<n>`, provided the
  same section defines it** *(2026-09-09, driven)*. Four items — `R1-ratchets`,
  `R2-archive-collision`, `R34-model-catalog`, `DAY1-constraints` — were appended to the line with a
  definition block below giving each a target, a done-condition and its source verdict. The night
  window resolved and completed all four. The format example in `spec-queue/README.md` shows only
  change names and finding numbers; it is an example, not the grammar. **What the window needs is
  resolvability, not a registered id.**
- **A merged branch stops being merged the moment you commit to it again, and
  `arm-cycle.ps1` reads that at firing time, not at merge time** *(2026-09-09, a prediction made and
  then falsified by the predictor)*. After fast-forwarding `master` to the cycle branch, the arm was
  expected to cut a fresh `autonomous/<today>-daily`. A later commit on the branch put it one ahead
  of `master`, so `git branch --merged master` no longer listed it, `$openCycle` found it, and the
  night **continued the old branch**. Both behaviours are correct; the state is read at 22:55.
- **`git rm --cached <path>` followed by `rm <path>` makes a later `git add <path>` fail**
  *(2026-09-09)*: `fatal: pathspec '<path>' did not match any files`, which aborts an `&&` chain. The
  deletion is already staged by the `git rm --cached`, so the `git add` is both unnecessary and
  fatal. To stage a deletion of a tracked file, `git rm <path>` alone is enough.

## Reading the live Hub's own data, and the traps in it

Added 2026-09-16 while measuring where a project's token budget actually went.

- **`turn_usage` in the operator's live database is the authoritative per-run token and cost
  record**, and reading it read-only is safe and sanctioned: open
  `~/.agentweave/hub/data/agentweave.db` as `file:<path>?mode=ro` with `uri=True`. One row per
  Hub-owned run, with `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`
  and `api_equivalent_usd_micros` as the runner reported them. A "turn" is one run, which is many
  provider API calls internally, so per-turn input routinely exceeds any context window - that is
  correct, not a bug in the data. *(verified 2026-09-16)*
- **23% of measured rows carry a NULL `model` and zero tokens.** They are skewed toward same-agent
  continuation turns. Averages over measured rows are sound; **totals are understated**, and any
  claim of the form "N of M turns" must say whether M is the measured population or the subset you
  could classify. Getting this wrong produced a wrong sentence in a proposal this session.
  *(verified 2026-09-16)*
- **`agent_outputs.payload` names the tool under the key `tool`, not `name`, and its `input` is a
  JSON string inside the JSON** - double-encoded. A parser that looks for `name` and reads `input`
  as a dict silently finds nothing, or worse, finds a fallback. This session drew a confident,
  wrong conclusion from exactly that mistake before checking a raw row. Dump one payload before
  trusting any aggregate over this table. *(verified 2026-09-16)*
- **`<project>/.agentweave/tasks/<task-id>/src` is PRODUCT SOURCE, not scratch.** Agents work in a
  per-task worktree under `.agentweave/`. A path classifier that treats everything under
  `.agentweave/` as temporary will report that developers never touched product code. Real scratch
  is `.tmp/`, `.aw_tmp/` and `reviews/<agent>/.scratch-*`. *(verified 2026-09-16)*
- **Agents write into Claude Code's own memory directory**
  (`~/.claude/projects/<mangled-project-path>/memory/`), out of band and invisible to the Hub. In
  one project a reviewing agent had put 60 writes across 16 files there, including per-task review
  notes. If you are auditing what an agent did, that directory is part of the evidence and no Hub
  query will show it to you. *(verified 2026-09-16)*

## Measurement methodology traps

Added 2026-09-16 after one of these reached a committed specification.

- **Never multiply independent marginal maxima and call the product an observed worst case.** A
  figure of "~13,032 characters, observed, from real documents" was written into a proposal and a
  design this session. It was `362 (max criterion length) x 12 (max criteria per requirement) x 3
  (max requirements per task)` - three maxima that co-occur in no document. The real measured worst
  case over the same corpus was 5,462, a 2.4x overstatement, and it had been used to justify adding
  a whole capability to a change. **If a number is a product of other numbers, say so, and measure
  the joint quantity directly.** *(2026-09-16)*
- **Check that the corpus contains an instance of the thing you are sizing.** The same measurement
  sampled 41 spec payloads to size what a *declared task* would carry - and none of those 41
  documents declared any tasks. *(2026-09-16)*
- **A subagent's finding is a claim, not a result.** Three adversarial reviews this session each
  found real blocking defects, and each also asserted at least one thing that did not survive
  checking. Verify a finding before acting on it, especially one you are about to write into a
  spec. *(2026-09-16)*

## Python stdout encoding when printing repository content

- **A `py -3.11` heredoc that prints text drawn from the repo or the database will die on cp1252**
  with `UnicodeEncodeError: 'charmap' codec can't encode character ...`, because the console
  encoding is not UTF-8. It kills the script mid-output, so you get a partial result that looks
  like a short answer. Start any such script with
  `import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")`. *(verified 2026-09-16)*

## Starting a Hub from source can land on the operator's real database

- **`hub/config.py:16` defaults `DATABASE_URL` to `Path.home() / ".agentweave" / "hub" / "data" /
  "agentweave.db"` — the operator's live `:8000` database.** There is no guard. Any Hub started
  from `hub/` whose `DATABASE_URL` fails to reach the process lands on it silently. The 2026-09-19
  day window hit this: it set the variable, backgrounded `py -3.11 -m uvicorn` with `&`, and the
  variable did not survive a `kill` + `rm` + restart sequence inside one Bash tool call. Export the
  variable in the same command as the server, and **verify from the server's own startup log** —
  a fresh throwaway file logs the whole `0065→0103` migration chain, an existing database logs only
  `Application startup complete`. That missing migration chain is the first sign you are on the
  wrong file. *(2026-09-19)*
- **Verify a claimed corruption before believing it.** That same window reported the file had "only
  18 tables, an empty `alembic_version`, and a schema predating migration 0065". **It does not.**
  Read `mode=ro` the same day: **46 tables, `alembic_version` = `0103`, `integrity_check` = ok, 3
  projects, 348 runs, 87 tasks, 12,500 event_logs.** Whatever produced the 18-table reading was not
  this file. A scary reading about the operator's data is exactly the kind of claim to re-derive
  before acting on it — or before telling them. *(2026-09-19)*
- **The trap fired a second, harmless time the same night, through a different syntax.** The night
  window's `unrh-drive` step used the Bash tool's inline-prefix form,
  `DATABASE_URL="..." AW_BOOTSTRAP_API_KEY="..." py -3.11 -m uvicorn hub.main:app --port 8092`, run
  from `hub/`. The server started and logged a full `0001→0104` migration chain — which looked like
  proof of a fresh file — but the intended profile directory (`~/.agentweave/hub/profiles/
  drive0919c/`) never existed afterward, and the operator's live file's `alembic_version` read
  `0103` both before and after, unchanged, while its `event_logs` count kept growing on its own.
  The env var did not reach the `py` launcher's child either way; the full migration log was real
  but for a database this session never located (most likely reclaimed or pointed at a location
  this session's tools could not see — not resolved). **The fix that worked:** set the env vars in
  PowerShell (`$env:DATABASE_URL = "..."`) before `Start-Process`, and pre-create the target
  directory with `New-Item -ItemType Directory -Force` first — `sqlite3`/`aiosqlite` will not create
  a missing parent directory, so a silent fallback to the default is also what a *correct* URL
  against a missing directory would look like from a crashed start, making directory-existence the
  cheap thing to check first. **Kill only the exact PID `netstat -ano` names as `LISTENING` on the
  target port** — never a blanket `taskkill /IM python.exe`, which is what turned the first
  occurrence into a real outage. *(2026-09-19, night window, `unrh-drive`)*

## Telling whether the operator's `:8000` app is running, without touching it

- **Read its scheduler's own heartbeat out of `event_logs`.** The operator's Hub fires a job every
  5 minutes and writes `job_fired` + `queue_entry_queued` rows (and `queue_entry_abandoned` when an
  entry ages out). The **last timestamp is when the process stopped.** This is the only way to
  establish a before/after without starting, probing or calling `:8000`, all of which the standing
  rule forbids. Used 2026-09-19 to establish that a `taskkill /IM python.exe /T` had almost
  certainly killed the operator's live app: events ran at exact 5-minute boundaries from
  `00:00:00` to `09:40:00.704` and then stopped dead. *(2026-09-19)*
- **Those timestamps are UTC; Windows file mtimes are local.** In September that is BST, `+1`. The
  database's mtime read `10:40` for a last event of `09:40` — the same instant, not an hour of
  unexplained activity. Getting this backwards invents a discrepancy that is not there.
  *(2026-09-19)*
- **`taskkill /IM python.exe` does not match `pythonw.exe`.** The operator's app is documented as a
  `pythonw`-hosted pywebview window, so "`Get-Process` finds no python running" is not evidence
  that it was not killed — check the event heartbeat above instead. *(2026-09-19)*

## `scripts/backlog_page.py`'s delta report covers findings only

- **`SINCE LAST GENERATION` reports finding counts and `newly filed: F<n>`, and says nothing about
  requests.** Adding `R4` and `R5` to `spec-queue/REQUESTS.md` on 2026-09-19 moved `requests` 1→3
  and `items` 205→207 in the page's embedded snapshot while the printed report mentioned neither.
  The page itself renders them correctly — only the delta block is blind. To confirm a request
  landed, read the `requests` field out of the `<script type="application/json"
  id="backlog-data">` block rather than trusting the console summary. *(2026-09-19)*

## Waiting for CI without restarting its own clock

- **`gh run watch <id> --exit-status` backgrounded is how you wait for the merge gate**
  *(2026-09-19)*. A full CI run on `autonomous/**` measures **~13-14 minutes**. The gate's problem
  was never the waiting — it was that the *next firing's own commit* moved `HEAD` to an unbuilt sha
  before the wait could pay off. Get the id with
  `gh run list --branch <b> --limit 5 --json databaseId,headSha,status,conclusion,workflowName --jq ...`,
  then `gh run watch <id> --exit-status --interval 30` as a background command. Measured green on
  `a435f48` after ~14 minutes.
- **The four gate conditions are cheap to check and worth checking separately** *(2026-09-19)*:
  `git rev-list --count HEAD..master` is 0; `git status --short` empty and
  `git rev-parse HEAD` == `git rev-parse @{u}`; CI `success` at HEAD's sha; no line-initial
  `HOLD MERGE` in `DIRECTION.md`'s newest section. On 2026-09-19 conditions 1, 2 and 4 had been
  holding for four days and only 3 failed.

## A machine reader needs the row, not the prose — `APPROVALS.md`

- **An approval written only as a `### APPROVED — <name>` heading is invisible** *(2026-09-19)*.
  `backlog_page.py`'s `approvals_rows()` matches `^-\s+(APPROVED|REVISING|REJECTED)\s+(\S+)`, so a
  heading plus an `ORDER:` line parses as **no token at all**, and the page renders an approved
  change as still waiting on the operator. That is how the 2026-09-19 omission was caught. `ORDER:`
  *does* still parse from inside a fenced block, because the regex is line-initial. **Write both the
  prose and the `- APPROVED <name>` row.**
- **`newest_section()` used to take the first `##` positionally** *(fixed 2026-09-19, `a435f48`)*.
  The spec-queue files declare "newest day first" and are hand-written, so the convention is a
  promise nobody enforced — and it had been broken: 09-18 and 09-19 were appended at the *bottom*,
  so every machine read of "the newest approvals section" returned **09-16** for three days. It now
  sorts by the date in the heading. **The night playbook matches on the armed date rather than
  position, so the windows were never at risk — the page was.**

## Exact-string edits on the large `openspec/changes/**` markdown files

- **Do not reconstruct the `old` string from memory for a Python `str.replace`** *(2026-09-19)*.
  These files run to 700-1000 lines with em-dashes, en-dashes and nested emphasis, and a
  reconstructed block silently drops a sentence — three `AssertionError`s this session from exactly
  that. **Grep for a unique first line, read the real block with `sed -n 'A,Bp'`, then replace by
  line index** (`lines[A-1:B] = new`), or copy the block verbatim from the `sed` output.
- **`assert old in t` before every replace.** It converts a silent no-op into a loud failure. Every
  one of this session's three misses was caught by it rather than by re-reading the output.
- **Measured runtime:** `py -3.11 -m pytest hub/tests/test_a_held_agent_is_busy.py
  hub/tests/test_a_task_nothing_will_move_holds_nobody.py -q` → **55 passed in 36.2s**
  (2026-09-19, `7d805df`). Cheap enough to run as a routine guard, unlike the full suite's 15-47
  minutes.

## A round you wrote yourself is not a check

- **2026-09-19, measured twice in one day.** R5 (written interactively) re-derived `D1` of
  `an-unstaffed-review-names-its-holders` against option (f) and found that D1 would revert
  `4b59ee0`. An independent adversarial Opus subagent then found D1 would **also** revert
  `a-spent-allowance-holds-the-queue`, via `agents_held` ORed into the running set **in the very
  expression R5 had quoted**. Measuring the character budget afterwards found a third defect
  (`.;` in the operator's own sentence) that five consecutive rounds had specified past.
- **The pattern to expect: one defect per pass, and each pass finds what the last missed.** Three
  consecutive passes over one change, each finding something new, is the observed rate. Treat "my
  own round says it is clean" as unevidenced, and prefer partial `ORDER:` lines that stop at the
  part whose correctness its own tests can prove.

## `openspec validate --strict` cannot see a contradiction between two requirements

*Measured 2026-09-19 evening.* It validates each requirement in isolation — shape, `SHALL` on the
first physical line, at least one scenario. **Nothing checks one requirement against another, and
nothing checks a requirement against its own scenario list.** A change can therefore pass `--strict`
six times running while:

- two requirements in the **same capability** govern the same operator-visible sentence and
  disagree about what it may say (`a-loop-staffs-the-agent-it-names`, R4-2: the delta's new rule
  needed a third clause in a 409 that `agent-loops:1471` says "SHALL say which of those **two**
  held");
- a requirement's own scenario list holds an unconditional scenario and a strict specialization of
  it with the **opposite** THEN (same change, R4-3);
- the proposal cites as its authority the design section that refutes it (R4-1).

**So a green `--strict` is evidence about form, never about consistency.** The only thing that finds
this class is a pass that reads the artifacts *against each other*. Budget for that explicitly; four
rounds on one change each found exactly one defect, and three of the four were this shape.

## Before working a `backlog_page.py` LEDGER WARNING, read the heuristic that produced it

*Measured 2026-09-19 evening.* The warning *"N findings read 'open' but name a commit sha — verify
before trusting the open count"* tested `state == open AND /[0-9a-f]{7,40}/ in status`. It flagged
**29 rows, of which 2 could possibly be stale.** The dominant shape in `FINDINGS.md` is
**provenance**, not a fix claim — *"Filed by the row-1 sweep (`3280f52`)"*, *"Found 2026-09-06
(`3142a91`)"*, *"measured at unit level on `87dfbf4`"* — all of which name the commit the finding
was **written** at, which is exactly what a correctly-open finding looks like.

**Fixed at `91a8ddf`**: the test now requires a fix verb (`fixed|closed|repaired|resolved|landed|
shipped`) attached to the sha, and reports 2. Both survivors (F53, F352) are correct partial-fix
rows, not stale ones. **The durable lesson outlives the fix:** these warnings are heuristics over
prose written by many sessions, the file says *"none of these is conclusive on its own"*, and an
afternoon can be spent verifying a list that was wrong about 27 of its 29 entries. Read the
generator before believing the count.

## A finding's file citation may not resolve from the repository root

*Measured 2026-09-19 evening.* F52's status line cited `agent_actions.py:940`. There is no such path
at the root — the file is `hub/hub/api/v1/agent_actions.py`, and the line number was right. A bare
filename in `FINDINGS.md` is often a shortened citation written by someone who had the file open,
not a path. **`find . -name "<basename>"` before concluding a finding is stale**, and note that
`.agentweave/tasks/*/` holds full copies of the tree, so a naive `find` returns three hits for one
real file.

## Reconstructing an exact-match `old` string fails on `spec-queue/` files too

*Measured 2026-09-19 evening; extends the `openspec/changes/**` entry above.* The same failure hit
`spec-queue/DIRECTION.md`: an `old` string typed from memory, including a line break placed where it
looked right, did not match and the edit asserted out. **The rule is not about `openspec/changes/`
specifically — it is about any prose file in this repo long enough that you are not looking at the
bytes.** `grep -n` the anchor, read the real line, and `assert old in t` before writing. This is the
fourth session to hit it.

## A second adversarial pass on an already-reviewed change still pays

*2026-09-19 evening, extending "A round you wrote yourself is not a check".* The change
`a-loop-staffs-the-agent-it-names` had R1, an adversarial R2 that returned DO NOT APPROVE with 5
blocking findings, and an R3 that applied all of them — **but R1 and R3 were the same session.** A
fresh adversarial pass (R4) returned DO NOT APPROVE with **eight** blocking findings, six of which
were re-verified at the source and all six held. Two of them were prior findings' own shapes
surviving into R3 in a *new place* (R2-4's "a spec promising an outcome the code does not make"
reappeared in a second paragraph; D9's "a requirement cannot say both" was fixed in prose and left
in the scenario list).

**Running tally across the two sibling changes: seven passes, seven defects, no pass yet finding
nothing.** Treat "the review already ran" as satisfied only if the applying round was a *different*
session from the one that wrote what was reviewed.


## 2026-09-20 (evening) — implementing a change, and probing the approver

- **`ruff`, `black` and `mypy` are NOT on PATH in the Bash tool.** `ruff check ...` returns
  `/usr/bin/bash: line 1: ruff: command not found`, and so do the other two. The CI commands in
  `CLAUDE.md` and in every change's quality-gate tasks are written in CI's spelling, which does not
  work in this shell. **Invoke them as `py -3.11 -m ruff` / `py -3.11 -m black` / `py -3.11 -m
  mypy`.** Measured 2026-09-20. This matters beyond convenience: a task that reads
  *"`ruff check src/ hub/ tests/` — clean"* will look like a **failed gate** to an agent that runs
  it literally, and the honest-looking response to a failed gate is to start changing code.

- **Probing `_decide` (`hub/hub/mcp_server.py`) without `HUB_URL` set gives a false `deny`, with a
  misleading reason.** `_judge_word`'s rule 2 trusts a `$HUB_URL` reference only when
  `trusted and base`, where `base` is `os.environ["HUB_URL"]` **in the approver's own process** —
  the Hub sets it for every run, so a bare probe does not reproduce a real run. Unset, a shape the
  Hub actually allows is refused as *"contains a variable, '~' or a command substitution that the
  shell expands when it runs"*, which reads like a real verdict about the command rather than a
  missing variable in the harness. Measured 2026-09-20 by getting it wrong first, then twice more
  by R2 and R3 independently. **Export `HUB_URL` and `AW_WORKSPACE_DIR` before any `_decide`
  probe.** Note `python -c` is unaffected — it names no `$HUB_URL` word, so rule 2 never fires on
  it, which is exactly why `DECISIONS.md` 1d once picked that shape.

- **A `grep -n` guard in a task compares line NUMBERS, not code, and any annotation pass breaks
  it.** A task guarding "the permission posture is unchanged" was written as
  `grep -n "acceptEdits\|permission-prompt-tool" ... byte-identical to master`. Commit `4bd966e`
  added comment blocks and moved all six matches (57→65, 63→71, 71→79, 73→81, 75→83, 254→269) while
  changing **no code at all**. Drop the `-n` and diff the matched lines' *text*, against **the sha
  the change is being implemented on top of** — not against `master`, which on a working branch
  also contains every unrelated commit since the branch point. Caught by R3 before implementation;
  it would otherwise have fired a false alarm and invited a "fix" to code that was correct.

- **Importing anything from the `hub` package in a scratch script opens the operator's live
  database unless `DATABASE_URL` is set FIRST** (open finding **F388**, fix decided a+b+d and not
  yet built). Set it to a throwaway path **before** the import, not after — `hub.config` reads it at
  import time. Every probe script this session did this deliberately; it is cheap and the failure
  mode is writing to `:8000`'s real data.

## 2026-09-20 — an interactive session sharing the tree with a live scheduled window

- **The unattended driver will commit your uncommitted working-tree edits, under its own message.**
  Commit `51b17bd` (*"chore: commit the operator DECIDE session's approval of item 1"*) is the day
  window's iteration sweeping in this session's in-flight edits to
  `openspec/changes/an-archived-agent-holds-nothing-and-is-offered-nowhere/` and
  `spec-queue/APPROVALS.md` while they were still being written. **`git log --format=%an` does not
  help** — the driver runs as the same git user, so its commits and yours are indistinguishable by
  author; only the message's `day(YYYY-MM-DD)` prefix tells them apart. Working with a window live
  in the same tree: commit in small units as you go, and expect a `Read`/`Edit` to report *"the file
  had been modified on disk"* mid-session. Confirmed 2026-09-20 16:0x.

- **To land a merge while a driver is live in the tree, push the ref — never check out `master`.**
  `git push origin <sha>:master` followed by `git fetch origin master:master` performs the
  fast-forward without the working tree ever leaving the branch, so a firing that runs `git status`
  or the test suite mid-merge sees nothing unusual. A `git checkout master` would have swapped the
  tree under a running iteration. Used 2026-09-20 to land 40 commits; `--is-ancestor` first, so the
  push is provably a fast-forward and not a force.

- **A green local `hub/tests/` run is not evidence that CI will pass, and this has cost real days.**
  F292's `sqlite3.OperationalError: database is locked` **does not reproduce on this machine at
  all**. Measured 2026-09-19/20: 16 consecutive red CI runs across 20 hours and 14 pushes, every one
  of them that signature alone, while the full local suite was green throughout (4459 passed at
  `09237f6`). `night-window.md` step 3 now reads CI's conclusion for the inherited sha for exactly
  this reason. **Never report "the tree is green" from a local run without saying which signal you
  checked.**

- **`tests/test_skill_sync.py` fails locally on a clean tree and passes in CI** — two cases
  (`Kimi + OpenCode (project)`, `Codex (user-level)`), over `autonomous-session/scripts/*.ps1`
  present in the source and absent from the mirrors, plus `backlog` absent from Codex. The
  2026-09-20 day log records this as *"a third reason `pytest tests/` is red and therefore bears on
  the merge gate"*. **That inference is wrong and should not be inherited:** CI concluded `success`
  on both `c6fccc5` and `3d8c02e` with those same local failures present, and on every red run the
  only failing job was `hub-test`. It is a local skill-mirror state artifact, not a gate blocker.

- **`backlog_page.py`'s "changes waiting on the operator" counts only the NEWEST `APPROVALS.md`
  dated section.** Writing a new `## <date>` section makes every approval in yesterday's section
  stop counting, so the figure jumps upward the moment you record today's decisions — 1 → 3 on
  2026-09-20. It is not a bug to go fix blindly: for partly-built changes whose remaining groups
  really are unapproved, the higher number is the honest one. But **the figure also drives
  `loops = 2 if awaiting == 0 else (1 if awaiting == 1 else 0)`**, so recording an approval can
  silently tell the next day window to run zero spec loops. Check that line before reading the
  count as good or bad news.

## 2026-09-21 (evening) — reading a change's state, and moving work out of one

- **A change's `tasks.md` banner can be days stale while its `proposal.md` banner is current.**
  `an-unstaffed-review-names-its-holders/tasks.md` opened with *"STOPPED AT REV, 2026-09-14. Do not
  build any task here"* while `proposal.md` said *"RESOLVED 2026-09-19 — the re-derivation is done"*.
  An interactive session read only `tasks.md`, told the operator the change was stale, and the
  operator answered "reject it" on that false premise (voided minutes later, recorded in
  `DECISIONS.md` `### 2026-09-21 evening`). **Before characterising a change's state to the
  operator, read the top of `proposal.md`, `design.md`'s round log, and `APPROVALS.md`'s rows for
  it — not one file's banner.** *(2026-09-21; that banner is now marked superseded, b065713.)*
- **Moving a task group out of a change is not a `tasks.md` edit — its spec delta has to be trimmed
  too.** A group's requirement text is woven into MODIFIED requirements; archiving the change with
  the text still there syncs SHALLs the code does not meet into `openspec/specs/`. `a-loop-staffs`
  §5 → F400 needed a trim of two requirements and three scenarios, each checked against
  `jobs.py:1349-1361` (07c6298). **Check the delta for every scenario the moved tasks were the only
  implementation of.** *(2026-09-21)*
- **A bash-style path in `DATABASE_URL` creates a stray database under `C:\c\Users\...`.**
  `sqlite+aiosqlite:////c/Users/...` resolves on Windows to a directory named `c` at the drive
  root. Use `C:/Users/...`. Found by the day window's D-2. *(2026-09-21)*
- **`GET /api/v1/events` is an SSE stream and blocks forever**; event history is
  `/events/history`. A drive script piped through `tail` hid that hang for 10 minutes (day window
  D-1). *(2026-09-21)*

## 2026-09-21 (late evening)

- **"No spec mentions it" needs a grep of `openspec/changes/`, not only `openspec/specs/`.** Handoff
  0135 told the operator F376 needed a spec from scratch; `a-refused-capability-reaches-the-operator`
  had been F376's approved, partly built change since 09-18. Before saying a finding has no spec:
  `grep -rln F<nnn> openspec/changes --include=*.md | grep -v archive/`. *(2026-09-21)*
- **A Python heredoc that rewrites a tracked file on Windows turns it CRLF.** `open(p,'w')` in text
  mode writes `
`; git then warns "CRLF will be replaced by LF". Open with `newline=''`, or
  `sed -i 's/
$//'` after. *(2026-09-21)*
- **A test command with an unbalanced quote passes the judge for the wrong reason.** `_lex` reads an
  unclosed quote to the end instead of refusing, so `.""."` lexes to `..` while bash will not run it
  at all. Run a sandbox test row's command in the real shell first (F375 R2-3). *(2026-09-21)*
- **Never add tomorrow's `## <date>` section to `APPROVALS.md` before tonight's night window has
  run.** The night reads the newest section **only if its date is the date it armed**
  (`night-window.md` step 2). A `## 2026-09-22` placed above `## 2026-09-21` at 21:30 would have made
  the 22:55 night read no approvals at all, and tonight's whole ORDER would have been dropped
  silently. Caught before commit. An approval for a future night goes in tonight's section as prose
  with **no** `- APPROVED` token at line start, plus a DECISIONS row, and the next DECIDE session
  copies it forward. *(2026-09-21)*

## 2026-09-22

- **A local lint pass over `src/ hub/ tests/` is not CI's lint.** CI's ubuntu-3.11 job also runs
  `ruff check scripts/ --select E9,F63,F7,F82,F401,F841`, and an unused variable in a new
  `scripts/drive/` harness failed three pushes in a row (`229a708`, `24f3655`, `a4d0976`) while
  everything local was green. Run both ruff lines from CLAUDE.md's "Code quality" block before
  pushing anything that adds a drive script. *(2026-09-22)*
- **`python - <<EOF ... assert ...; EOF; next-command` does not stop on the assert.** The `;` runs
  the next command anyway: `openspec archive -y` archived a change while the script meant to tick
  its last task and set its finding's Status had died on an assertion. Chain dependent steps with
  `&&`, or run them as separate calls. *(2026-09-22)*
- **A finding's `**Status:**` line can appear verbatim in other entries** (quoted in addenda). F376's
  appeared 3 times, so `s.count(old) == 1` failed. Anchor on the `## Fnnn` heading and edit the
  line after it. *(2026-09-22)*

- **`await task` on an already-finished task returns without yielding to the event loop.** A
  `while some_set: for t in list(some_set): await t` loop spins forever when a finished task is
  still in the set because its `set.discard` done-callback is queued behind the waiter. That was F394's
  six-hour CI hangs (fixed `f9e6dee`, shared helper `hub/tests/_background_runs.py`). **Tell a spin from
  a wait by the thread-dump shape:** a waiting coroutine leaves the main thread in the selector with no
  test frames; a spinning one shows `_run_once -> handle._run -> <test frame> -> await task`. Use
  `asyncio.gather` and remove what you awaited from the set yourself. *(2026-09-22)*
- **The hub suite fakes `project_workspace.resolve_project_workspace` in every test** (autouse
  `_default_project_workspace` in `hub/tests/conftest.py`). No test sees what the real resolver does to
  the session: F349's per-call `UPDATE projects SET last_seen_at` went unseen for weeks. Restore the
  real one with the `bind_project_workspace` fixture. *(2026-09-22)*
- **`pytest-randomly` is not installed for `py -3.11`, and CI has never used it.** Flake rates in
  FINDINGS measured "under random ordering" (F314's 1-in-8) came from an environment this machine no
  longer has; the same tests run in a fixed order today. To re-measure without randomising anyone else's
  runs (tonight's windows included): `py -3.11 -m pip install --no-deps --target <scratch>/rnd
  pytest-randomly`, then set `PYTHONPATH=<scratch>/rnd` for your runs only. **`-q` hides the
  `Using --randomly-seed=` line**, so drop `-q` if you need the seed. *(2026-09-22)*
- **Run black *after* writing a new file, not before.** `black` over the tree, followed by creating
  a test file, left that file unformatted and turned CI red (`bab861a`). Run CLAUDE.md's full lint
  block as the last step before each push. *(2026-09-22)*
- **`pathlib.Path.write_text` on Windows writes CRLF** into files this checkout keeps as LF in the
  working tree. Git normalises it on add, so it is only noise ("CRLF will be replaced by LF"), but
  edit scripts should use `read_bytes`/`write_bytes` and keep the file's own newline. *(2026-09-22)*
- **A finding whose cited call no longer exists is often already fixed under another finding's
  number.** F279's failing `db.refresh` was deleted by F287's repair; F314's lock error was cured by
  F383's. Check `git log -S'<cited snippet>'` before investigating. A sweep of 90 open B findings found
  only 3 more like that, so the ledger is mostly accurate. *(2026-09-22)*

- **A new hub test that creates an agent passes locally and fails on CI** because this machine has
  `claude` on PATH and CI's runners do not: `POST /agents` answers 409 `Runner CLI 'claude' was not
  found in PATH.` (F117's tests, red on `6c96d75`/`809fa14`/`fea83d8`; fixed by patching
  `hub.launchability.shutil.which` as the sibling tests do). Before pushing a new test, run it with
  `claude`'s dir stripped: `PATH=$(echo "$PATH" | tr ':' '
' | grep -vxF "$(dirname "$(which claude)")" | paste -sd:) py -3.11 -m pytest ...`. *(2026-09-22)*

- **`gh run list --commit <sha>` needs the full 40-character sha.** With a short one it matches
  nothing, the next `gh run watch` gets an empty id, and a background wait fails with "run or job
  ID required". Take the run id from `gh run list --json databaseId,headSha` filtered on
  `headSha|startswith(...)`. *(2026-09-22)*
- **Do not write Python source through a Python-in-heredoc string replacement.** Escapes such as
  `"
"` inside the replacement text reached the file as real newlines, which broke four string
  literals in `scripts/rounds_page.py`. Use the Write/Edit tools for code, and keep the heredoc
  scripts for data files such as the ledger. *(2026-09-22)*
- **F167 has no `## F167 ` heading in `FINDINGS.md`.** Its text sits under F154's write-up (`### F167`)
  and under a `## F167's bound is now measured` section, so any grep for `^## F167 ` misses it.
  Round 0 of `spec-queue/ROUNDS.md` gives it a heading. *(2026-09-22)*
- **`backlog_page.classify` reads only a Status line's first words, and one word is enough to close an entry.** `retired` anywhere in the first 80 characters makes it `retired`, and so does `not a defect` or `does not reproduce`. An open entry annotated "F399 is a duplicate, retired into this entry" read as closed, and the backlog count dropped by one it should not have (F234, fixed within minutes). When annotating an **open** entry, keep those words out of the first 80 characters, and check the regenerated page's "no longer open" list against what you actually closed. *(2026-09-22)*

## RESOLVED

Kept because "we used to believe this" is worth knowing, and because an entry that quietly
disappears is indistinguishable from one that was forgotten.

- **`npm run lint` does not work at all** *(believed 2026-08-08 → 2026-09-04)*. ESLint 9 needed a
  flat config and the repo had none, so it failed before linting anything; `npx tsc --noEmit` was
  the real check. **RESOLVED: `hub/ui/eslint.config.js` now exists** (verified 2026-09-04). CI
  lints for real again — treat a lint failure as a finding, not as this known breakage.
- **The default `python` on PATH has no pytest** *(believed 2026-08 → 2026-09-04)*. **RESOLVED,
  and replaced by a worse fact:** it now has pytest 9.1.1 and produces phantom failures instead of
  erroring. See the Python section — still use `py -3.11`.
- **`npx openspec …` is required** *(believed 2026-08)*. **RESOLVED:** `openspec` is on PATH
  directly (verified 2026-09-04).
