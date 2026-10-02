# Handoff 0160: the work-PC checks for `a-run-reaches-the-hub-without-mcp` (slice 3, task 10.1)

**Date:** 2026-10-02T12:30+01:00 · **Branch:** master · **HEAD:** the commit that adds this file (see `## Git state`)
**Agent:** claude-opus-5-5[1m] · Claude Code · interactive (home machine)
**Previous handoff:** handoff-0159-2026-10-02-1035-copilot-credits-implemented-drive-next.md (home machine only;
`.claude/handoffs/` is untracked, so it is not in this clone)
**Status:** written to be resumed **on the work PC**: `/resume .claude/work-pc/handoff-0160-2026-10-02-work-pc-checks.md`

> **Why this file is here and not in `.claude/handoffs/`:** that directory is gitignored on purpose (it once
> carried `aw_live_` keys). This file is tracked so a `git pull` brings it to the work PC. It holds no key. Do not
> write a key into it, and do not move it into `.claude/handoffs/`.

## Goal

Run the human-only checks of openspec change `a-run-reaches-the-hub-without-mcp` (Copilot slice 3) on the work PC,
the only machine where company policy blocks MCP. Then record the answers so task **10.1** can be ticked. The change
is at 55 of 58 tasks, and its decision row `a-run-reaches-hub-10.1` in `spec-queue/DECISIONS.md` is OPEN waiting on
exactly this. Its question is: on a machine where Copilot cannot load the `agentweave` MCP server, does a Copilot
agent still reach the Hub through the `aw-tool` command (the "shim"), with no permission card and no credential
typed anywhere?

## Current state

- `master` holds slices 1–4 of the Copilot work: slice 1 (adapter seam), slice 2 (Copilot over ACP), slice 3 (the
  shim; built and driven at home but not archived) and slice 4 (credits; archived 2026-10-02). Everything below
  needs only a pull.
- At home, slice 3's drive (group 9) passed, **with MCP disabled by a flag**, which only stands in for policy. The
  real policy block has never been tried. That is the point of this visit.
- **Known to fail here, do not chase it:** human-only item 6 (a specification turn over the shim). At home (task
  9.10) Copilot wrote its args file with PowerShell `Set-Content`, and the Hub's workspace judge misread
  `"path":"spec/..."` inside the command as a URL outside the workspace and refused it. That is **F478**, whose fix
  (`openspec/changes/an-arguments-file-written-from-powershell-is-the-hubs-own`) is proposed and waiting for
  approval (`F478-approve`), not built. Run item 6 only to record what this machine does. A refusal that quotes a
  `spec/...` path is F478, not a new defect.

## What the operator does on the work PC

The agent resuming here can do the setup, the no-model checks and the recording. The operator types the prompts,
reads the app and answers the questions. Keep every prompt to one sentence: the work PC's Copilot plan is the
company's.

### 0. Setup (no model call)

1. `git pull` on `master`. Confirm `git log --oneline -1` shows this file's commit or later.
2. Install from source, through the constraints file (CLAUDE.md, "Development Setup"), with Python 3.11:
   `py -3.11 -m pip install -c constraints-dev.txt -e ./hub` and
   `py -3.11 -m pip install -c constraints-dev.txt -e ".[dev,mcp]"`. The UI bundle is committed
   (`hub/hub/static/ui`), so Node is not needed.
3. Copilot CLI: `copilot --version` must be **1.0.88 or newer** (managed policy applies under ACP only from 1.0.88;
   home ran 1.0.90). Signed in with the work account.
4. Start a Hub **on its own test profile**, so nothing the work PC already uses is touched. Run it from `hub/`,
   from source (`agentweave` from the repo root dies: the repo's `hub/` shadows the package). It refuses to start
   without `DATABASE_URL`:
   ```bash
   cd hub
   DATABASE_URL="sqlite+aiosqlite:///C:/Users/<you>/.agentweave/hub/profiles/workpc/agentweave.db" \
   AW_BOOTSTRAP_API_KEY="aw_live_<32 random letters/digits>" \
   py -3.11 -m uvicorn hub.main:app --port 8010 --host 127.0.0.1
   ```
   Create the `profiles/workpc` directory first. Read the startup line `Hub database: opening …` to confirm the
   file. Open `http://127.0.0.1:8010` and use that key if the app asks for one. Do not write the key here.
5. In the app: open a **throwaway** project, a new directory with `git init` and one commit. **Never this
   repository** (CLAUDE.md: never point a Hub you are editing at this repo, and a run inside it loads the
   operator's own local-scope `agentweave` server). Add a Copilot runner with **no model** (Auto), and a Copilot
   agent bound to it. Leave the permission mode at **Ask me** unless an item says otherwise.

### 1. Before any turn (no model call): test-guide item 1, plus the exploration's probes

In an interactive `copilot` session (not through the Hub):
- `/env` and `/mcp list`: what do they say about MCP policy, which source is named, and would `agentweave` be
  allowed?
- `%LOCALAPPDATA%\copilot\copilot-user-cache.json`: the values of `is_mcp_enabled` and the plan/SKU.
- `reg query "HKCU\Software\Microsoft\Command Processor" /v AutoRun` and the same under `HKLM`: is an `AutoRun`
  set, and what does it print (design D3: anything it prints lands ahead of `aw-tool`'s JSON)?

### 2. One tiny turn: test-guide item 2

To the Copilot agent: *"Create an AgentWeave task titled WORKPC-1, then stop."* In the app, check:
- the task WORKPC-1 exists;
- the run's activity has **one** line saying the MCP server did not start and the run was told to use `aw-tool`,
  quoting Copilot's own words about the server;
- no permission card asked about `aw-tool` or about a file under `.agentweave/calls/`.

### 3. Only if WORKPC-1 was not created: test-guide item 3

Open the run's activity and copy the **first refusal verbatim**. Then say which of these it looks like:
AppLocker/WDAC blocking a `.cmd` in the user profile; PowerShell execution policy; a Copilot permission question the
Hub did not recognise; the `AutoRun` output from step 1 corrupting the JSON; or a bare `Set-Content` args file with
non-ASCII text (the command then says to use `-Encoding utf8`).

### 4. A question through the command: test-guide item 4

*"Ask me, with ask_user, whether to proceed; then stop."* Answer it in the app within the wait. Did the agent
receive the answer? Did Copilot's shell cut the command off before you answered (design D7)?

### 5. Reading the notice: test-guide item 5

After a turn, open `<throwaway project>/.agentweave/context/<agent>.md` and read its "Your tools" section. Then, in a
second tiny turn, ask the agent to quote the "Tool access" section it received. Judge: would a colleague understand
from those alone how the agent reaches the Hub, and that no credential needs typing anywhere?

### 6. A specification turn: test-guide item 6 (expected to be refused, F478)

Open a specification document with the Copilot agent and ask, in one turn, *"Submit this document unchanged, then
stop."* The design expects an args file, a submission and no card. **Today expect a refusal** if Copilot writes the
file with `Set-Content` (F478). Record what happened, the refusal text and the tool used. Skip it if the plan's
budget is tight.

### 7. Not needed

Test-guide item 7 (a Claude agent with `hub_client: cli`) was done at home in task 9.8.

### 8. Persistent shell sessions: test-guide item 8, **the answer task 10.1 names**

Under "Ask me", two tiny turns in one conversation, approving the first command's card:
1. *"Run `$env:AWPROBE='1'` in PowerShell, then stop."*
2. *"Run `echo $env:AWPROBE` in PowerShell and tell me what it printed, then stop."*

Record whether the second printed `1`, which would mean Copilot's shell sessions persist between commands. Also
record whether any run so far, unprompted, activated a venv, ran `Import-Module`, defined an `aw-tool`
function or alias, or set `ComSpec` before calling `aw-tool`. **If sessions persist and such commands occur, that
triggers the detect-and-degrade follow-up change** (design open question 7: (a) now, (c) as a follow-up). Raise it
with the operator; do not build it in this visit.

### Optional, cheap: what the credits feature shows on a paid plan

Slice 4 was driven only on Copilot Free. After item 2, open Environment > Budgets and note the allowance line: the
plan, the percentage, the reset date and whether it reads sensibly. If any turn is ever **refused for quota** on
this machine, the Hub's log has a line starting `Copilot session.error errorType=`. Copy it into **F482**
(`scripts/drive/FINDINGS.md`); it confirms or corrects how the Hub recognises a refusal (design D8 of the archived
`a-copilot-run-shows-its-credits`).

## Recording the results (the resuming agent does this)

1. Append a Round log entry **"Work PC, task 10.1 (<date>)"** to
   `openspec/changes/a-run-reaches-the-hub-without-mcp/design.md`. Give each item's answer verbatim where a quote
   was asked for: the `copilot --version`, the `/env` and `/mcp list` policy lines, the `AutoRun` values, the run ids,
   the refusal texts, and step 8's answer.
2. Tick task 10.1 in that change's `tasks.md` with a `**Done <date> (operator, work PC).**` note that points to the
   Round log. Keep the note free of `<n> failed` counts (`tests/test_openspec_task_evidence.py` rejects them), and run
   `py -3.11 -m pytest tests/test_openspec_task_evidence.py -q`.
3. Move `a-run-reaches-hub-10.1` in `spec-queue/DECISIONS.md` from OPEN to DECIDED/DONE with one line of outcome.
4. Any new defect becomes a new finding at the end of `scripts/drive/FINDINGS.md` (the next free number is F483).
   F478 reproducing is not new; add a line to F478 instead.
5. **Do not archive (10.2) on your own.** Task 9.10 is still open, blocked on F478, so the archive needs the
   operator's word: wait for F478, or archive with 9.10 carried as F478.
6. Commit with explicit paths (never `git add -A`) on `master`, and push (CLAUDE.md, "Session continuity").
7. Stop the test Hub you started.

## Constraints and user directives

- Operator, 2026-10-02: *"Merge and switch to work on master. Write a document of what I need to check on the work
  PC so I can pull it there and test it, write it on a handoff file that Ill just resume there after you push."*
- CLAUDE.md applies here unchanged. Use `py -3.11`, never bare `python`. Stage paths explicitly. Commit each
  completed checkpoint and push, and open no PRs. Interactive sessions work on `master` (memory rule, 2026-09-24).
- Never point the Hub at this repository. Use a throwaway project.
- Keep real model turns few and one sentence long. Not every item needs the model: items 1 and 5 (reading the
  file) and the setup need none.
- `.claude/handoffs/DEAD-ENDS.md` (tracked) records this **home** machine. Its path and tool facts may not hold on
  the work PC. Verify before trusting one, and append any new work-PC trap there, marked "(work PC)".

## Environment left running

None on the work PC. At home, the trial Hub `:8010` was stopped after the slice-4 drive, and `AgentWeaveArmNight`
(the home machine's night window) is armed for 22:55. It works on its own branch; it neither reaches the work PC
nor writes this file.

## Verification

At home, before this file: CI green on `6b3f306` (hub-test, ui-test, the six CLI jobs); `master` fast-forwarded
to it. Slice 3's group 9 drive passed at home with MCP disabled by flag, except 9.10 (F478). Nothing in this
document has been run on the work PC yet. That is its purpose.

## Git state

- Branch `master`, at the commit that adds this file (on top of `6b3f306`, the archive of
  `a-copilot-run-shows-its-credits`), pushed to `origin/master`.
- `autonomous/2026-10-01-daily` equals `6b3f306`; the home night window keeps using it.

## Open questions for the user

- At home, still open: `F478-approve`, `F478-oq1-bash`, `F478-oq2-location` (in `spec-queue/DECISIONS.md`).
  Approving F478 is what lets item 6 and task 9.10 pass.

## Read on resume

- `openspec/changes/a-run-reaches-the-hub-without-mcp/test-guide.md`, the "Human-only" section, the source of
  every item above.
- `openspec/changes/a-run-reaches-the-hub-without-mcp/tasks.md`, tasks 9.10, 10.1 and 10.2.
- `spec-queue/DECISIONS.md`, the `a-run-reaches-hub-10.1` row.
- `openspec/explorations/2026-09-27-copilot-as-a-full-runner.md`, "Probes to run on the work PC".
