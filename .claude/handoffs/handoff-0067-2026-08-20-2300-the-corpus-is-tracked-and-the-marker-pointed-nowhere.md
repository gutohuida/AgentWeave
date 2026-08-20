# Handoff: this repository's corpus is really adopted, and the project marker pointed at a database nothing was serving

**Date:** 2026-08-20T23:00:18+01:00 · **Branch:** `master` · **HEAD:** `a029892`
**Agent:** Claude Opus 5 (1M context) (Claude Code, interactive)
**Previous handoff:** `.claude/handoffs/handoff-0066-2026-08-20-2221-document-adoption-shipped-and-the-ports-were-backwards.md`
**Status:** chunk complete. Working tree clean. **14 commits unpushed** — 1 mine this session,
the rest split between my previous session and a concurrent session still working in this tree.

## Goal

Execute handoff 0066's next-step 1: run `openspec/changes/document-adoption` §9 for real, against a
live Hub and this repository's actual `spec/` corpus, rather than against the copy the previous
session rehearsed on.

The *why*: a specification document is a file plus a database row. The file is committed and
travels; the row is machine-local and does not. Every capability except the read path keys on the
row, so this repository's own 35 documents were **readable and completely inert** — no phase, no
requirements, no coverage. `document-adoption` mints rows for files that already exist without
writing to disk. It had been proven on a copy; it had never put a row in a real database.

**That is now done.** This repository's corpus is tracked: 35 documents, 461 requirements.

## Current state

### §9 ran end to end and every check passed

Against the trial Hub on **8010** and this repository as **`proj-5e960453`**:

| §9 step | Result |
|---|---|
| 1 — nothing is written | `git status --short spec/` and `git diff --stat spec/` both empty; sha256 of all 36 files identical before and after |
| 2 — the corpus arrived | 35 documents, 35 adopted, 0 skipped, 0 diagnostics; kinds `{capability: 34, system-map: 1}`; phases `{current: 34, exploring: 1}`; all 35 `phase_source: read`, none defaulted; 452 requirements created |
| 3 — running it twice is safe | `adopted` empty, all 35 skipped with `code: document_exists`, zero non-empty `differences` |
| 4, 6 — Spec tab and coverage | the 9 Playwright tests in `hub/tests/browser/test_adopted_corpus.py`, all pass |
| 5 — `unfiled` is gone | reindex: 35 documents, home `spec/agentweave.html`, 0 diagnostics; `spec/index.json` gained `project-instructions` and `quiet-hours` with real titles |
| 7 — the refusal explains itself | HTTP 409, `document_exists`, names the path and says adoption does not update an existing record from its file |
| 8 — a payload-less file is refused | HTTP 422, `payload_absent`, file byte-identical, test file deleted afterwards |

Every figure reproduced the rehearsal exactly. Database now holds 35 `spec_documents` rows for
`proj-5e960453` and 461 `spec_requirements` (461, not 452 — the extra 9 predate this session and
belong to `proj-ff695d96`'s `notify-window` document, which was already in that database).

### The finding: `proj-5e960453` was not in the database 8010 was serving

**This is the thing to carry forward.** Handoff 0066 and CLAUDE.md both state this repository is
registered on the trial Hub as `proj-5e960453`. Before this session it was not reachable there:

- PID 26700 served 8010, launched via `cmd /c cd /d <repo>\hub && python -m uvicorn hub.main:app
  --host 127.0.0.1 --port 8010` with **no `DATABASE_URL`**, so it fell to `config.py`'s relative
  default and served `<repo>/hub/data/agentweave.db`.
- `GET /api/v1/projects` on it returned three projects — `aw-loop10`, `Throwaway (taste pass)`,
  `13.2 briefing check`. **No `proj-5e960453`.**
- `proj-5e960453` existed only in `~/.agentweave/hub/profiles/beta/agentweave.db`, which CLAUDE.md
  dismisses as "earlier or divergent copies, not the live one".
- Handoff 0066 inferred registration from `.agentweave/project.json` alone. That marker holds
  `proj-5e960453` and always did — but a marker is a claim about a database, not evidence one
  exists. It pointed into a file nothing was serving.

CLAUDE.md's own instruction is what caught this: *"Confirm which database a running instance
actually serves with `GET /api/v1/projects` before trusting any doc, this one included."*

**The operator's resolution, chosen via AskUserQuestion: point 8010 at the beta database.**
Rejected: registering the repo fresh on the live database (the operator had deferred that decision
the previous session), and skipping the real run.

### Machine state changed — read this before starting a Hub

| Port | What it is | State now |
|---|---|---|
| **8000** | The operator's real usage. **Leave alone.** | running, untouched this session |
| **8010** | The **test** Hub. Safe to drive, including restarting. | **restarted by this session, now serving `~/.agentweave/hub/profiles/beta/agentweave.db`** |
| **8021** | Previous session's throwaway rehearsal Hub | **killed** (PID 21212), and `%TEMP%\aw-adopt-check` / `aw-adopt-control` removed |

8010 is running as a **backgrounded process owned by this session's shell** (bash task `bztgs1148`,
log at `%TEMP%\agentweave-hub-8010.log`). It may or may not survive the session ending — check
before assuming. The exact command that started it:

```bash
cd <repo>/hub && DATABASE_URL="sqlite+aiosqlite:///C:/Users/huida/.agentweave/hub/profiles/beta/agentweave.db" \
  py -3.11 -m uvicorn hub.main:app --host 127.0.0.1 --port 8010
```

**Operator credential for 8010 (and for the repo database):**
`aw_live_58ab7d84a1bf7b34eb2d1b424875bacd`. It lives in the `operator_credentials` table, not
`api_keys` — `api_keys` is empty in both databases and has no hash column. The
`AW_BOOTSTRAP_API_KEY` in `~/.agentweave/hub/.env` (`aw_live_71b05608...`) is a **different** key
and 8010 rejects it; that `.env` belongs to the 8000 instance.

Startup migrated the beta database **0075 → 0082** (spec_edit_proposals, the five loop migrations,
and `0082` retiring the unasked-question backstop). It was backed up first to
`~/.agentweave/hub/profiles/beta/agentweave.db.pre-8010-2026-08-20`.

**The swap is reversible and destroyed nothing.** `<repo>/hub/data/agentweave.db` is untouched and
still holds `aw-loop10` plus the two testbed projects; restarting 8010 from `hub/` without
`DATABASE_URL` goes back to it.

### CLAUDE.md is now wrong in two rows, deliberately left alone

The trial-Hub table says the database is `<repo>/hub/data/agentweave.db` and that this repo is
registered there as `proj-5e960453`. After this session the first is wrong (8010 serves beta) and
the second was already wrong (it was only ever true of beta). **The operator was offered the fix
and did not select it**, so it stands uncorrected. Flagged here because the next session will read
that table and be misled exactly as this one nearly was.

## Files touched

`git status --short` is empty and `git diff --stat HEAD` is empty — everything is committed.

**`733af84` — Adopt this repository's own corpus, for real this time** (2 files, +25/-9), the only
commit of mine this session:

- `spec/index.json` — **+16 lines, pure insertion, nothing removed.** Adds
  `spec/capabilities/project-instructions/spec.html` ("Project instructions") and
  `spec/capabilities/quiet-hours/spec.html` ("Quiet hours"), both `kind: capability`,
  `status: current`. These are the two documents `document-adoption`'s proposal named as
  permanently `unfiled`, because `build_index` files only documents that have a row. Written by
  the reindex route, not by hand. Finished.
- `openspec/changes/document-adoption/tasks.md` — rewrote §8's header note (rehearsal *then* real
  run, with the database correction stated) and struck "Left for the operator" item 1, which is now
  done. The three taste judgements remain. Finished.

**No Hub or CLI source was modified this session.** `hub/hub/spec_adoption.py`, `spec.py`,
`spec_lifecycle.py` and the test files are exactly as the previous session left them — this
session ran the change, it did not alter it.

**Created and deleted within the session:** `spec/step8-no-payload.html` (§9 step 8's fixture),
removed immediately after; `git status --short spec/` confirmed empty afterwards.

## Key decisions

1. **Ask before running §9, rather than proceeding on the marker.** Discovering `proj-5e960453`
   was absent turned next-step 1 into a decision the operator had explicitly deferred the previous
   session ("register this repo" — answered "leave open"). *Rejected:* registering the repo myself
   to unblock, which would have silently reversed a deferral, and rewritten
   `.agentweave/project.json` with a new ID.
2. **Point 8010 at beta — the operator's choice, not mine.** I recommended registering on the live
   database instead. The operator chose beta, which preserves the recorded project ID and the
   marker. *Consequence accepted:* 8010 no longer serves the database CLAUDE.md names.
3. **Back the beta database up before starting against it.** It is the only home of
   `proj-5e960453`, and startup would run seven migrations against it unattended.
4. **Take a whole-tree sha256 snapshot as well as `git status`.** `git status` cannot see a
   change to a file whose content is rewritten identically, nor cleanly show a file added and
   removed within one command. 36 hashes before, 36 after.
5. **Ran the browser tests rather than eyeballing the Spec tab.** They were built specifically to
   fail on an un-adopted project, so they measure adoption rather than the app rendering. Standing
   directive from the previous session: *"Any test that you can do with playwright do it."*
6. **Amended the mangled commit message rather than leaving it or adding a fix-up commit.** The
   commit was unpushed and at the tip, and no concurrent work sat on top of it at that moment.

## Constraints and user directives (verbatim)

From this session:

- Chosen via AskUserQuestion: **"Point 8010 at the beta database"** on how to give §9 a target, and
  **"Kill the 8021 rehearsal Hub"** as the only side item. Explicitly *not* selected: pushing the
  unpushed commits, and fixing CLAUDE.md's trial-Hub facts.

Standing, carried forward from handoff 0066 and **still in force**:

- *"8010 is a test environment. 8000 is real usage."*
- *"Any test that you can do with playwright do it. Just leave the tests that I need to do and
  guide me with what I need to test"*
- Never `git add -A`; stage paths explicitly. **Load-bearing again this session** — a concurrent
  session committed four times into this tree while I worked.
- Never mark a task complete on the strength of a plan existing.
- `hub/hub/static/ui` is a committed build artefact — after `cd hub/ui && npm run build`, run
  `python scripts/refresh_ui_bundle.py` (`make` is not on PATH in Git Bash here).
- Keep the two `spec_manifest.py` twins (`hub/hub/` and `src/agentweave/`) in sync by hand.
- `hub/hub/mcp_server.py` may import **only** stdlib + fastmcp.
- `approve_tool_call` has **no return annotation** — do not add one.
- From memory: commit each completed checkpoint without asking first; specs must carry test guides
  split into agent-verifiable and human-only.

**Superseded and still superseded:** *"Never touch the Hub on port 8010"* from handoffs 0064/0065.

## Dead ends

- **PowerShell here-string syntax (`-m @'...'@`) in the Bash tool silently mangles a commit
  message.** It committed with `@` as the subject line and the real subject on line 2. Fixed by
  `git log -1 --format=%B | tail -n +2 > /tmp/msg.txt && git commit --amend -F /tmp/msg.txt`. In
  the **Bash** tool use a real heredoc; `@'...'@` is PowerShell only.
- **`py -3.11` cannot open a Git Bash `/tmp/...` path.** `curl -o /tmp/x.json` writes to
  `C:\Users\huida\AppData\Local\Temp\x.json`, and Windows Python raises `FileNotFoundError` on the
  `/tmp` form. Use `cygpath -w` or the `C:\...\Temp\` path in Python; bash tools like `diff` handle
  `/tmp` fine.
- **A relative sqlite path in a Python one-liner resolved somewhere unexpected**, producing a
  contradiction — `sqlite_master` listed `api_keys`, then `pragma table_info` returned empty and
  `select` said "no such table". Always pass an absolute database path.
- **`api_keys` is the wrong table to look for a Hub credential in.** It is empty and has no hash
  column (`id, project_id, label, revoked, created_at`). Credentials live in
  `operator_credentials`; see `hub/hub/db/engine.py:171` `_seed_operator_credential`.
- **`py -3.11 -m openspec` fails** with "No module named openspec.__main__". Use the `openspec`
  console script directly.
- **The stale PID files mislead.** `~/.agentweave/hub/hub-8010.pid` said 12496; the real listener
  was 26700. `Get-CimInstance Win32_Process -Filter "ProcessId=N"` is what actually resolves a
  port's owner, after `netstat -ano | grep LISTEN`.

Carried forward from handoff 0066, not re-encountered but still true:

- **`git checkout <file>` to undo a scratch mutation reverts uncommitted work.** Copy the file
  aside first and restore from the copy.
- **Playwright's Python `get_by_role(name=...)` does not accept a callable** — use `re.compile(...)`.
- **`page.get_by_text` does not reach the rendered spec document** — it renders inside an `iframe`;
  use `page.frame_locator("iframe").first`.
- **Deleting a registered project's directory breaks it until `.agentweave/project.json` is
  restored with the same `project_id`.**

## Verification

**Ran, and passed:**

- All eight §9 steps, exact commands and outputs recorded in the table under "Current state".
- Corpus adoption twice against `proj-5e960453`, with `git status --short spec/` and a 36-file
  sha256 snapshot taken around each. `ALL 36 FILES BYTE-IDENTICAL`.
- `cd hub && AW_HUB_URL=http://127.0.0.1:8010 AW_HUB_API_KEY=aw_live_58ab7d84a1bf7b34eb2d1b424875bacd
  AW_HUB_PROJECT_ID=proj-5e960453 py -3.11 -m pytest tests/browser/test_adopted_corpus.py -v`
  → **9 passed in 3.16s**.
- `openspec validate document-adoption` → valid. `openspec list` → `document-adoption ✓ Complete`.
- Post-run database read: 35 `spec_documents` for `proj-5e960453`, 461 `spec_requirements`.

**NOT run this session — do not claim otherwise:**

- **The Python test suites were not run.** No `pytest hub/tests/` and no `pytest tests/`. Justified
  only because no source file was modified — the sole code-bearing change is `spec/index.json`,
  written by the product itself. The last full figure is **2580 passed** from handoff 0066, and it
  does **not** include the concurrent session's four newest commits.
- **`ruff` / `black` / `mypy` were not run**, same reason.
- **CI has not been checked** for any of the 14 unpushed commits.
- **The three taste judgements in §8 remain open** and are explicitly the operator's.
- **The 9 browser tests were not re-run against an un-adopted control this session.** That
  falsification was done last session on 8021, which no longer exists.
- **The concurrent session's work is entirely unverified by me.** I did not read
  `loop-notices-and-reacts` or the `task-dependencies` revisions.
- **No UI exists for adoption**, so none was tested. Every operator path here was curl.

## Git state

- **Branch:** `master`. **HEAD:** `a029892`. **Working tree clean.**
- **14 commits unpushed.** Mine this session: `733af84` only. Mine from the previous session:
  `54ca5b5`, `5130d7f`, `0dcc1a2`, `85f70ba`, `f07c2db`, `4ad72ca`. The concurrent session's:
  `7d4ff6e`, `a0f7ef4`, `9d9b20e`, `824d843`, `9a79392`, `1c47005`, `32deef4`, `a029892`.
- Not pushed because the operator was offered the push and did not select it, and because half the
  commits are not mine.

## A second session is still working in this tree

It committed **four more times during this session**, all on top of my `733af84`:

- `9a79392` Settle the firing cadence, and what a no-op tick should record
- `1c47005` Propose loop-notices-and-reacts — a **new proposal**, 6 files, +704
- `32deef4` Close the four open loop questions
- `a029892` Settle the tick interval at five minutes, and label a re-briefing loop

They touch only `openspec/changes/loop-notices-and-reacts/`, `openspec/changes/task-dependencies/`,
and two files in `openspec/explorations/`. **No overlap with anything I touched.** Staging explicit
paths is the only reason that stayed true.

## Next steps

1. **Decide what to build next, then start it.** `openspec list` right now:
   `loop-notices-and-reacts` 0/64 (new, the concurrent session's), `task-dependencies` 0/80,
   `agent-created-documents` 0/35, `corpus-aware-documents` 0/55, and three complete-and-unarchived
   (`document-adoption`, `writable-spec-index`, `operator-authored-documents`). If picking one to
   implement, `agent-created-documents` is the smallest fully-unblocked option and all three of its
   open questions carry recommendations: `/openspec-apply-change agent-created-documents`.
   **Check with the operator first if the concurrent session is still live** — it is now holding
   two of the six proposals.
2. **Archive `document-adoption`.** Its §9 blocker is gone: the change ran for real, on the real
   corpus, and `tasks.md` §8 now records it. `/openspec-archive-change document-adoption`. The
   other two complete changes have been unarchived since handoff 0065 and could go with it.
3. **Confirm 8010 is still up before using it** — `curl -s http://127.0.0.1:8010/health` — since it
   was started as a background process of this session. Restart command and credential are under
   "Machine state changed" above.

## Open questions for the user

- **The three taste judgements** in `document-adoption` §8: does the populated phase bar read as
  informative or as clutter; is the coverage summary ("7 no work linked") useful at a glance; is
  *"adoption does not update an existing record from its file"* the right thing to say to someone
  who expected it to update.
- **Should adoption have a UI?** The only operator path is curl, which for the "I just cloned this
  repo" case is arguably the wrong shape. Raised last session, still unrecorded as a finding.
- **Should CLAUDE.md's trial-Hub table be corrected?** Offered this session and not selected. It
  now misstates both the database and the registration.
- **Should 8010 stay on beta**, or go back to `<repo>/hub/data/agentweave.db` once the adoption
  work is done? The two testbed projects and `aw-loop10`'s newer state live in the latter.
- **Push the 14 commits?** Including the concurrent session's 8.
- **Retire `openspec/specs/`?** Open since handoff 0062 — and materially changed now that this
  repository's `spec/` corpus is actually tracked in a database rather than inert.
- **Delete `proj-adf8a200`** (the operator's home directory registered as a project on 8000)? Open
  since handoff 0063; "leave open" as of last session.
- **Adoption's own three deferred questions:** re-adoption / refresh-from-file; whether adoption
  should set `rigor`; whether corpus adoption should run reindex itself.

## Read on resume

- `openspec/changes/document-adoption/tasks.md` — §8 now records the real run and what is left;
  §9 is the operator procedure, and every step in it has a known-good outcome to compare against.
- `CLAUDE.md` — the trial-Hub section, read **against** the "Machine state changed" table above.
  The two disagree, and this handoff is the accurate one.
- `hub/hub/db/engine.py` around line 171 (`_seed_operator_credential`) — where a Hub credential
  actually lives, if authentication against 8010 ever fails.
- `openspec/changes/loop-notices-and-reacts/proposal.md` — the concurrent session's new proposal,
  unread by me, and the largest single thing added to this repo today.
- `openspec/explorations/2026-08-20-who-guarantees-the-review-handoff.md` — revised three times
  this session by that other session; the reasoning behind the loop proposals.
- `hub/tests/browser/test_adopted_corpus.py` — its docstring carries the exact invocation for
  running browser tests against a live Hub.
