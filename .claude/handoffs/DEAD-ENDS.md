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
- **`py -3.11` cannot open a Git Bash `/tmp/...` path.** Use a Windows path.
- **`py -3.11 -c "import hub.main"` from the repo root fails** with an ImportError — this repo's
  `hub/` directory shadows the installed `hub` package. See the Hub section.
- **`shutil.rmtree(..., ignore_errors=True)` is a lie on Windows** — it silently leaves the tree.
- **`sqlite3` is not on PATH.** Use `py -3.11 -c "import sqlite3; ..."`. *(Confirmed 2026-09-04.)*
- **`ruff` and `mypy` are not on PATH in Git Bash.** Use `py -3.11 -m ruff`, `py -3.11 -m mypy`.
  *(Confirmed 2026-09-04.)*
- **`pip` warns about two invalid distributions** in Python311 site-packages (`~gentweave-ai`,
  `~nteragent-framework`) — leftover partial uninstalls. Harmless noise, not a failure.
  *(Observed 2026-09-04.)*

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

## git

- **`git worktree add` into the scratchpad fails** with "Filename too long".
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

## SQLAlchemy and Hub test patterns

- **`session.get(Conversation, "conv-…")` silently never matches** — the primary key is not what
  you think it is. Query explicitly.
- **`session.delete()` refuses a never-flushed object.**
- **`ORDER BY EventLog.id` does not order by recency.** Order by timestamp.
- **`extra: "forbid"` rejects a forbidden *key* regardless of its value** — including `None`.
- **There is no `db_session` fixture.** Use `async_session_factory()` from `hub.db.engine`.
- **The `app` fixture is an httpx client with no `.routes`.**
- **`run.task_id` is NULL on most runs** — 154 of 202 measured. Read the transition table instead.
- **`run_job` returns 503 in tests** unless `get_scheduler()` is patched.
- **A payload-shaped model function must be tested against real route ordering.** A fixture in an
  order the route never emits is not evidence (F190: ascending lifecycle events fed to a route
  that returns newest-first, green for a month while the behaviour could not fire).

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

---

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
