# Design — A call-mode turn starts with an empty calls directory and is told to name each file afresh

Round 1, 2026-10-12, HEAD `6208e9a5`, verified by Rounds 2 and 3 on the same day. The evidence is in
`proposal.md`. Line numbers are as of this HEAD.

## What the calls directory is, and who stands in it

- **It belongs to the workspace, not to an agent, a run or a task.** The path is
  `<effective_work_dir>/.agentweave/calls/` (`agent_trigger.py:262`; `mcp_server.py:3277` and `:4402`).
  The context file beside it is per agent (`.agentweave/context/{agent}.md`, `:1431`), but the calls
  directory is not.
- **Which workspace a turn gets** (`agent_trigger.py:1217-1325`, `worktrees.py:906-975`):

  | Turn | Workspace | `isolated_workspace` | Who else can stand in it while this turn runs |
  |---|---|---|---|
  | Writing agent, unbound or grandfathered task | the agent's own worktree (`worktrees.py:162`) | set (`:1318`) | nobody: one running run per agent (`:1000-1006`), serialised as described below |
  | Writing agent, task-bound, repository | the task's checkout (`worktrees.py:190-194`) | set (`:1318`) | another agent's writing turn on the same task, serially by D8 (`:1274-1286`); concurrently only through the D8 race below |
  | Review turn | that reviewer's review checkout (`worktrees.py:216`, keyed by the reviewer) | set (`:1238`) | nobody: one running run per agent |
  | Read-only agent, or a project that is not a repository | the project directory | `None` (`:1318`, `workspace == repo_root`) | any other read-only or non-repo agent |
  | Explicit `work_dir` | a project subdirectory | `None` (`:1229`) | any agent given the same `work_dir` |

  **R3: the `work_dir` row reaches into the "nobody" rows.** The refusal at `:1210-1215` covers only
  a writing agent in a repository project. `ProjectWorkspace.resolve_relative`
  (`project_workspace.py:61-81`) accepts any in-project path, including
  `.agentweave/worktrees/<agent>`, `.agentweave/tasks/<id>` and `.agentweave/reviews/<agent>`
  (`worktrees.py:158-220`). So the operator can trigger a read-only agent with `work_dir` naming
  `cop-1`'s worktree. That turn gets `isolated_workspace=None` and empties nothing, but `cop-1`'s
  next turn, which is isolated, empties the reader's in-flight arguments file. The same two runs can
  already overwrite each other's same-named file today. This is open question wpc4-e.

  The three set values are assigned before the calls directory is prepared (`:1444`), and nothing
  reassigns `isolated_workspace` in between (its other reads are `:1384`, `:1472-1479` and `:1759`).
  So the classification D1 needs is available, from the same value the snapshot and
  dependency-link code already trust, at the moment the directory would be emptied.

- **Why "nobody" holds for an agent's own worktree and review checkout (R2).** The guard at
  `:1000-1006` is a check-then-act: it reads for a `running` Run, and the Run is inserted and
  committed later (`:1658`, `:1728`). It is atomic only because
  `turn_scheduler.schedule_agent` (`turn_scheduler.py:259-271`) holds `_lock_for(project_id,
  agent)`, an `asyncio.Lock` per (project, agent) (`:66-67`), across the whole of
  `trigger_agent_directly`, which commits before it returns. `turn_scheduler.py:379` is that
  function's only caller, pinned by
  `test_a_refused_review_leaves_nothing_behind.py::test_trigger_agent_directly_has_one_caller`.
  `POST /agent/trigger` (`:1836-1837`) and the reconcile route (`spec.py:880`, importing
  `trigger_agent` at `:868`) both call
  `trigger_agent`, which goes through `schedule_agent`. Two Hub processes serving one database
  are not serialised. That would already put two processes in one worktree, which is far worse
  than an emptied directory, and is out of scope here. `stop_agent_run` (`:2121`) leaves the Run
  `running` until the process exits, so the guard holds through a stop.
- **Why it does not fully hold for a task checkout (R2).** D8's refusal (`:1274-1286`) reads
  `tasks_held_by_a_running_turn` (`run_task_binding.py:430`). The holder's Run is inserted at
  `:1658` and committed at `:1728`, and between the two lie awaits at `:1355`, `:1364`, `:1366`,
  `:1411`, `:1498` and `:1537`. Two *different* agents hold different `_lock_for` locks. So
  `builder-1` and `builder-2`, triggered on task T at the same moment, can both pass the D8 read
  and share T's checkout. This is pre-existing, and two live processes in one checkout is exactly
  the hazard D8 exists to prevent. What D1 adds is small. A's process is spawned only after
  `:1728`. B's emptying at `:1444` deletes A's arguments file only if A's model has written one
  before B reaches `:1444`, and B gets there within the same handful of awaits. This is open
  question wpc4-d.

- **Nothing reads an earlier turn's files.** The Hub's only readers are the call command's
  `_read_call_args` (`mcp_server.py:4429-4470`) and the approver's calls-root helpers (`:3269-3310`).
  Both act on a file the current turn just named. Nothing in `hub/ui/src` or `src/` reads them, no
  audit or debug path reads them, and `repo_hygiene.py:76` git-excludes the directory, so they are
  never committed or snapshotted. One development script reads them:
  `scripts/drive/d1001_shim_drive.py:126` lists `.agentweave/calls/*.json` after a run, as a report
  (R2). D1 empties at the *next* turn's start, so that report still sees the run's own files.

## D1 — Empty the directory at turn start, only in a workspace no other run can be standing in

`prepare_calls_dir(work_dir, *, empty: bool)`. `empty` is keyword-only and has no default, so a call
site that forgets it fails at once rather than silently keeping today's behaviour. When `empty` is
true, after the existing link handling and `makedirs`, remove every entry of `calls`:

- **A link or junction is removed as a link, never followed, and is detected the way the function
  already detects one**: `normcase(realpath(entry)) != normcase(entry)` (as at `:269`), then
  `os.rmdir` on `nt` when it `isdir`, otherwise `os.unlink` (`:271-274`). `calls` itself is already
  canonical at that point, because `root` is `realpath(work_dir)` (`:260`) and a linked `calls` has
  just been replaced, so an ordinary entry compares equal.
- A file is unlinked.
- A real subdirectory is removed with `shutil.rmtree`.

**The detection is not optional (R2).** A junction is not a link to `os.path.islink`. The naive
order `islink → unlink; isdir → rmtree; else unlink` sends a junction that sits directly in `calls`
to `rmtree`, and on Python 3.11 that raises `OSError("Cannot call rmtree on a symbolic link")`. D3
then catches the error and only warns, so the junction survives every turn. Its target's contents
are not harmed, but the turn is not cleaned either, and the test for it would pass on POSIX.

R2 measured on this machine (Python 3.11.16, Windows, `mklink /J`):

- `os.path.islink(junction)` is `False`, and `os.path.isjunction` does not exist in 3.11.
- `lstat(junction).st_reparse_tag` is `0xA0000003`. `isdir` is `True`, and `realpath` differs from
  the path.
- `shutil.rmtree(junction)` raises as above and leaves the junction.
- `os.unlink(junction)` and `os.rmdir(junction)` each remove the link only.
- `shutil.rmtree` over a real subdirectory that *holds* a junction removes the junction and leaves
  the target's file intact. This is the case R1 measured, and it holds.

Tasks 1.3 and 2.1 carry both cases. The call site passes `empty=isolated_workspace is not None`.

**Why not empty every workspace?** In the project directory, two read-only agents (or two agents on a
non-repo project) can run at once. Emptying at B's turn start could delete the file A wrote a moment
before running `aw-tool`, and A's call would fail with a missing file. Today those two agents can
already overwrite each other's `1.json`. That race predates this change and has not been observed.
This change neither causes nor fixes it, and records it as open question wpc4-c.

**This reverses D14's "the agent may reuse them".** Reuse only helps within one conversation that
remembers what it wrote. A new conversation cannot see the file and is misled by it (WPC-4). A
resumed conversation that tries to reuse `1.json` sees "file not found" and writes it again, which
costs one call. That is less than what the leftover cost in `run-a8245d9b1a1b`.

Alternatives considered:

| Option | What it fixes | Cost |
|---|---|---|
| (a) Empty every workspace every turn | WPC-4 everywhere | Can delete a concurrent agent's in-flight file in the shared project directory |
| **(a2) Empty only isolated workspaces** (recommended) | WPC-4 for every writing, task and review turn, which is every turn the drive ran | Shared-directory turns keep leftovers; D2 covers them |
| (b) Per-agent subdirectory `calls/<agent>/`, emptied each turn | WPC-4 everywhere, and the shared-directory race | The told path changes in `NOTICE_FORM`, both shim texts, the `agent-run-sandboxing` scenario "The Hub's notice spells the write out", and about six test files. `access_path_notice` and `_tool_surface_lines` take no agent name today. The approver needs no change, because `_inside_hub_calls_root` already admits subdirectories |
| (b2) Per-run subdirectory | Same as (b) | Needs the run id when the text is rendered, and subdirectories accumulate unless they are swept |
| (c) Prompt-only | Names reused within one turn | Not the cross-turn case: a new conversation still cannot know `1.json` exists |

## D2 — Tell the run to use a new file name for each call

Add one sentence to both shim texts, after the example: *"Use a new file name for each call
(`1.json`, `2.json`, …); if a call fails, write the corrected arguments to a new file rather than
editing the old one — your file-writing tool may refuse to overwrite."*

- In `launchability.access_path_notice`, it goes after "for example `aw-tool create_task
  .agentweave/calls/1.json`".
- In `agents._tool_surface_lines`'s shim preamble, it goes after the `Set-Content` parenthesis.

This covers the residual D1 leaves: a name reused within one turn, and any turn in a shared workspace.
The sentence goes in both renderings, and every runner can be told the shim path:
`described_access_path` (`launchability.py:301`) returns `shim` unless MCP has grounds. How each
runner's writing tool treats an existing path (R2):

| Runner | Tool | Existing file | Source |
|---|---|---|---|
| Copilot | `create` | Refuses: "Path already exists" | `run-6a6a40f3ae69` seq 6–7, `run-a8245d9b1a1b` seq 4–5 |
| Claude Code | `Write` | Opus 4.6, Haiku 4.5 and older require a prior `Read` of that file, so `Write` to an unread leftover fails. Newer models, from v2.1.228, may overwrite without one | Claude Code tools reference, "Write tool behavior". The shim spec turn keeps `Write` and drops only `Edit,MultiEdit,NotebookEdit` (`runner_commands.py:187-210`) |
| Codex | `apply_patch` `*** Add File` | Overwrites: `Hunk::AddFile` reads the old text only for the delta, then writes | `openai/codex` `codex-rs/apply-patch/src/lib.rs` |
| Kimi | `WriteFile` | Overwrites: `mode` is `overwrite` (the default) or `append`, with no prior-read check. Each write asks approval, which yolo grants | `MoonshotAI/kimi-cli` `src/kimi_cli/tools/file/write.py` (R3) |
| OpenCode | `write` | Version-dependent. Current `dev` overwrites ("overwriting if one exists"). Before about v1.17.9, an existing file not read this session was refused ("You must read file … before overwriting it") unless `OPENCODE_DISABLE_FILETIME_CHECK` was set | `anomalyco/opencode` (was `sst/opencode`) `packages/core/src/tool/plugin/write.ts`; the older `packages/opencode/src/tool/write.ts` `FileTime.assert` (R3) |

So the tool-level failure WPC-4 observed applies to Copilot, to older Claude models and to older
OpenCode. On a runner
that overwrites, a leftover does no harm *if the model writes before it calls*. It can still mislead
a model that sees `1.json` and runs `aw-tool` on it without writing. In `run-a8245d9b1a1b` the
leftover held a different call's arguments (title `WORKPC-SHIM`, seq 9–10). D1 removes that hazard
for every runner. D2's "may refuse" is therefore accurate wording, not a hedge.

The sentence avoids every phrase the existing pins assert. `test_launchability.py:594-606` checks
"with your file-writing tool", ".agentweave/calls/", "-Encoding utf8", "on its own", "unquoted" and
"last line". `test_hub_own_call.py:521-541` checks `NOTICE_FORM` verbatim. Both still hold. The
`mcp_server` usage text (`:4436`) concerns a missing file and does not change.

## D3 — Emptying is best effort; making the directory is not

Removing a leftover file can fail. A Windows file may be held open by a scanner or an editor. The
consequence of a leftover is the WPC-4 cost, not a safety problem: the approver and the call command
judge each path on its own merits, whatever else is in the directory. So `prepare_calls_dir` catches
`OSError` from each removal, logs one warning naming the path, and continues. The existing failures
still raise, and the call site still turns them into
`409 "Could not materialize canonical context for {agent}: …"`. Those are a link that cannot be
removed and a directory that cannot be made.

R2 measured the failures on this machine:

- Unlinking a file another handle holds open without `FILE_SHARE_DELETE` (as Python's `open()` does)
  raises `PermissionError` WinError 32.
- Unlinking a read-only file raises `PermissionError` WinError 5. Copilot's `create` does not make
  one, but a model's `Set-Content` into an existing read-only file would fail on its own first.
- `shutil.rmtree` over a subdirectory whose first file is held open stops at that error and leaves
  the whole subdirectory, not just the held file.

The catch is per entry, so one held entry does not keep the others. A surviving `1.json` means WPC-4
can recur for that one turn, and only D2 mitigates it. Clearing the read-only bit and retrying would
recover the WinError 5 case. It is left out, because no producer makes such a file.

The alternative, where any emptying failure refuses the turn, would turn a cosmetic leftover into a
blocked agent. This is open question wpc4-b.

## D4 — WPC-5: the spec turn keeps its exclusions

`SPEC_TURN_EXCLUDED_TOOLS = ("apply_patch", "edit", "str_replace_editor")` stays. `create` is already
kept for exactly this purpose (`copilot_acp.py:136-142`). `_standing_rules` (`:558-590`) allows a
calls-root `.json` edit before the spec-turn refusal (`:683-686`). With D1 the first `create` of a
turn finds no leftover, and with D2 later calls use new names. That leaves `Set-Content` as the
fallback, and it already has standing in every posture.

Why spec turns exclude write tools is set out in the archived design D16 (`:991-1030`) and in
`spec-document-authority` "Authoring assistance is scoped away from performing discovered
implementation work" (`spec.md:1297`). A spec turn submits documents through the document tools and
writes no project file. The exclusion is "a nudge, not a sandbox", backed by the permission refusal.
Claude's equivalent (`runner_commands.py:187-210`) keeps `Write` because Claude has no separate
create-only tool.

| Option | Effect |
|---|---|
| **Keep the exclusion; rely on D1 and D2** (recommended) | No change to the spec-turn tool surface |
| (a) Drop `edit` from the exclusion on shim spec turns | The permission half already exists: `_standing_rules` confines edits to calls-root `.json`, and every other edit is refused. But the model is shown a tool it will be refused for every other file, and the argv pins in `test_copilot_acp_run_turn.py:1613-1657` and `:3905-3907` and `test_copilot_acp_decide.py:925` change |
| (b) A runner-specific prompt naming `Set-Content` first | Already allowed by the judge, but a second rendering per runner, and it reorders the "file-writing tool first" advice that the pins assert |
| (c) `aw-tool` takes arguments inline or on stdin | Rejected. `agent-capability-plane` "The call command carries the run's authority without showing it" (`spec.md:1368`) requires arguments from a file the run names. A pipe is not "exactly one invocation", so the approver would ask. The archived design measured inline JSON losing its quotes in PowerShell 5.1 |

## What each route returns when what it calls raises

| Route or caller | Call | Raises | Returns |
|---|---|---|---|
| `POST /agent/trigger` (`:1836`), the reconcile route (`spec.py:880`) and the queue drain, all through `turn_scheduler.schedule_agent` → `trigger_agent_directly` (`turn_scheduler.py:379`) | `prepare_calls_dir(..., empty=True)`, removing an entry | `OSError` (e.g. `PermissionError` WinError 32 or 5) | Caught inside: one warning, the turn proceeds. **New** |
| same | `prepare_calls_dir`, link removal or `makedirs` | `OSError` or `ValueError` | `409 "Could not materialize canonical context for {agent}: …"`, as today |
| same | `.agentweave` is itself a link | none | Warning, no emptying, the turn proceeds, as today |
| `aw-tool <tool> <file>` after emptying | `_read_call_args` on a name the run has not written this turn | none | `{"ok": false, "error": {"kind": "usage", …}}`. This is today's missing-file answer, now reachable by a resumed conversation that reuses a name |

## Tests that can fail

Each test in `tasks.md` §1 names what would make it fail on today's code. The controls guard the
behaviour D1 must not disturb:

- links are handled as today;
- a shared workspace keeps its files;
- `NOTICE_FORM` keeps its standing;
- Copilot's spec-turn argv is unchanged;
- a `create` of a calls file on a spec turn is allowed and a `create` anywhere else is refused, using
  the permission request the drive's `create` makes: `kind` `edit`, `rawInput{path, file_text}`,
  `locations[{path}]`, `content[{type: "diff", path, oldText: "", newText}]`. (`changes[…]` is the
  mapper's derived `input_data` field, `copilot_acp.py:1002` and `test_copilot_acp_mapper.py:494-518`,
  not part of the request `decide_permission` reads; R3.)

A route-level test seeds a leftover `1.json` in an agent's own worktree and triggers through
`trigger_agent_directly`, not by calling `prepare_calls_dir` directly. That way a call site that forgets
`empty=` fails the test. It must restore the real workspace resolver: the autouse fixture
`_no_real_worktree_provision` (`hub/tests/conftest.py:1034-1064`) stubs `resolve_agent_workspace`,
`ensure_review_checkout` and `ensure_task_worktree` to return the repository root, so under it every
trigger sees `isolated_workspace=None` and a test of the isolated case would pass vacuously or not at
all (R3).

## Round log

- **R1 (2026-10-12)**: Read the code at `6208e9a5`, the archived D14 and D16, and the four shim runs
  in the trial database. Reframed WPC-5 as WPC-4 plus a name reused within a turn. Found the
  shared-workspace hazard that rules out option (a). Found that the parent brief's snapshot claim does
  not hold: the snapshot is mcp-only. Measured `rmtree` over a junction on this machine.
- **R2 (2026-10-12, work PC)**: Re-derived the argument from `6208e9a5` without trusting R1:
  `prepare_calls_dir` and its call site, where `isolated_workspace` is assigned, the per-agent
  guard and its lock, D8, the three workspace paths, the Copilot exclusion and decide path, both
  shim texts and every pin, the four shim runs in the trial database, and how the Claude and Codex
  writing tools treat an existing path.
  - **Confirmed.**
    - The classification is computed before `:1444` from data the trigger already holds.
    - Agent, task and review workspaces are disjoint by path.
    - WPC-5's reframing holds: in `run-6a6a40f3ae69` the permission layer allowed the `create` and
      the tool itself refused it (seq 6–7).
    - Keeping the `edit` exclusion (D4) is sound.
    - No pin asserts a phrase that D2's sentence would split.
  - **Wrong or missing, now fixed.**
    - **High.** D1 did not say how a link is detected. The naive `islink`/`rmtree` order leaves a
      junction sitting directly in `calls`, and D3's catch hides it. R1 had measured only the
      nested case. D1 now prescribes the function's own realpath test, and 1.3 covers both cases.
    - **Medium.** The table's "nobody" rows rested on a check-then-act. It holds within one Hub
      process through `turn_scheduler`'s per-agent lock. D8 is racy across *different* agents, so
      two agents can share a task checkout. This is pre-existing, and D1 adds a sub-second window
      to it. Recorded as wpc4-d.
    - **Medium.** The runner scope. Claude's `Write` refuses an unread existing file on older
      models, and Codex's add-file overwrites. D2 and the proposal now state this, and 0.2's
      sub-item is answered.
    - **Low.** Lock facts measured (WinError 32 and 5, partial `rmtree`). 1.4 gains a real held-file
      variant on `nt`.
    - **Low.** Fixed citations: the trigger route, `spec.py:879`, and the seq numbers of
      `run-6a6a40f3ae69`. Added the missed reader `scripts/drive/d1001_shim_drive.py:126` and the
      missed pin `test_agent_trigger.py:933`. Task 1.5 cannot pass "unchanged" once `empty` is
      required, so it now parametrizes the existing link tests.
    - **Low.** Hub tests run on Windows CI only in `hub-judge-windows`, for two named files. So 1.3's
      junction case would never fail on CI. Added task 2.6 to add the new file to that job.
    - The sandboxing requirement is renamed from "only this turn can stand in" to "in an isolated
      workspace", because of the D8 race. It gains a scenario for a link nested in a subdirectory.
- **R3 (2026-10-12, work PC)**: Re-derived from `6208e9a5` without trusting R1 or R2: the lock,
  every caller of the trigger, the classification, `prepare_calls_dir`'s link test measured on this
  machine, the Copilot decide path run directly, the trial database, every runner's writing tool
  from its source, and each §1 test against today's code.
  - **Confirmed.**
    - **The clear step is inside the per-agent lock.** `schedule_agent` (`turn_scheduler.py:259`)
      holds `_lock_for` (`:271`, `:66-67`) across `_attempt_turn` → `trigger_agent_directly`
      (`:379`). That span contains `prepare_calls_dir` (`agent_trigger.py:1444`), the Run commit
      (`:1727-1728`) and `create_task(_execute_run)` (`:1737`).
    - **Every path that ends in a turn reaches the one clear step.** `:1444` is
      `prepare_calls_dir`'s only call site, inside `_trigger_agent_directly`, reached only through
      `schedule_agent`. Callers: the trigger route (`:1837`, `:2039`), the reconcile route
      (`spec.py:880`), the ask_user answer resume (`questions.py:216`), scheduled and retried firings
      (`scheduler.py:3941`, `:4084`), and the message, inbound-queue, checkpoint, reconciliation,
      divergence, slice-drafting, project, agent and accounting triggers. Task and review dispatch are
      decided inside `_trigger_agent_directly`, before `:1444`. Nothing bypasses it.
    - **R2's link test holds** (Python 3.11.16, Windows, `mklink /J`, in a scratch directory since
      removed). A junction directly in `calls`: `islink` is `False`, `isdir` is `True`, the reparse
      tag is `0xA0000003`, and `realpath` differs, so it is detected; `os.rmdir` removes the link
      and keeps the target. `shutil.rmtree(junction)` raises "Cannot call rmtree on a symbolic link"
      and leaves it. A junction inside a real subdirectory: the subdirectory's `realpath` is equal,
      so it goes to `rmtree`, which removes the subdirectory and the junction and keeps the target's
      `keep.txt`, so `rmtree` does not follow it. A dangling junction: `isdir` is `False`, `realpath`
      differs, and `os.unlink` removes it. A regular file, and a file held open both by Python's
      `open()` and by `CreateFileW` with no sharing, compare equal; unlinking the held file raises
      WinError 32, which D3 catches. Symlinks could not be made (WinError 1314, no privilege), so
      they are unmeasured here. `realpath` resolves them the same way, and on POSIX `_link_dir`
      makes one.
    - A linked `.agentweave` returns early (`:263-271`), before `makedirs`, so emptying never runs
      through it.
    - **WPC-5's reframing.** `decide_permission` run on the drive's `create` request (`kind` `edit`,
      `rawInput{path, file_text}`, `locations`, diff `content`) with `spec_turn=True` returns ALLOW
      "the Hub's own tools" for `<ws>/.agentweave/calls/2.json` and REJECT "a specification turn
      writes no file" for `<ws>/spec/x.html`, in the workspace, `manual`, `acceptEdits` and
      `bypassPermissions` postures. The trial database's `run-6a6a40f3ae69` seq 6–7 is the tool's own
      "Path already exists".
    - D2's Claude row (tools reference, "Write tool behavior") and Codex row (`Hunk::AddFile` at
      `lib.rs:473` reads the old text for the delta, then writes) re-checked against their sources.
    - No string "new file name" exists in `hub/hub` today, so 1.8 fails.
  - **Wrong or missing, now fixed.**
    - **Medium.** Task 1.6 as written could not test the isolated case. The conftest autouse stub
      makes every workspace the repository root, and the cited `:3499` is an assertion under that
      stub. 1.6 and 1.7 now restore the real resolver, following
      `test_writing_agent_worktree_exists_before_first_spawn` (`test_agent_trigger.py:396-427`).
    - **Low/medium, new open question wpc4-e.** An explicit `work_dir` can name another agent's
      worktree or checkout, so a "nobody" row is not quite true. See the table note above.
    - **Low.** 1.11 described the request with the mapper's derived `changes` field. It now uses
      the request's own shape, notes that `test_copilot_acp_decide.py:1153-1171` already covers
      most of it, and is marked as passing today (measured).
    - **Low.** Controls 1.2 and 1.5 pass `empty=`, so like 1.4 they fail today on the keyword. They
      are behavioural controls, not tests that pass today; the tasks now say so.
    - **Low.** D2 and the proposal gain Kimi (overwrites) and OpenCode (overwrites now; refused an
      unread file before about v1.17.9). Which OpenCode and Claude versions the Hub targets is not
      pinned in this repository, so "may refuse" stays.
    - **Low.** Citation `spec.py:879` is `:880` (the import is `:868`).

## Open questions for the operator

- **wpc4-a: how a turn starts clean.**
  - Recommended: (a2) plus D2.
  - With (b), a per-agent subdirectory, the told path becomes `.agentweave/calls/<agent>/<file>.json`.
    `NOTICE_FORM`, the `agent-run-sandboxing` notice scenario and about six test files change, and
    wpc4-c is closed as well.
  - With (c), prompt only, D1 is dropped and WPC-4 is only mitigated.
- **wpc4-b: what an emptying failure does.**
  - Recommended: warn and proceed (D3).
  - Choosing "refuse" makes the new test 3 assert a 409 instead.
- **wpc4-c: the shared-directory race between agents.** Two read-only agents in the project directory
  can overwrite each other's same-named file today.
  - Recommended: record it as a finding and do not fix it here.
  - If you want it fixed now, that is option (b) of wpc4-a.
- **wpc4-d (new, R2): D8 does not serialise two different agents on one task.** D8's read
  (`:1274-1286`) and the holder's commit (`:1728`) are separated by awaits, and the scheduler's lock
  is per agent. So two agents triggered together on one task can both start in its checkout. This
  is pre-existing and far worse than anything D1 does. D1 adds only that B's emptying could remove a
  file A's model wrote in the moment between A's spawn and B reaching `:1444`.
  - Recommended: record a separate finding (WPC-n) for the D8 race and keep (a2) as it stands. The
    risk is a symptom of the race, and closing the race closes it.
  - Alternatively, extend the scheduler's lock to a per-task lock for task-bound turns in this
    change. That is out of this change's scope and touches `turn_scheduler`.
  - Or narrow D1 to agent worktrees and review checkouts, skipping task checkouts. That loses WPC-4
    coverage for every task turn and does not fix the race.
- **wpc4-e (new, R3): an explicit `work_dir` can stand in an isolated workspace.** The trigger
  refuses `work_dir` only for a writing agent in a repository project (`agent_trigger.py:1210-1215`),
  and `resolve_relative` accepts `.agentweave/worktrees/<agent>`, `.agentweave/tasks/<id>` and
  `.agentweave/reviews/<agent>`. A read-only agent sent there by the operator shares that workspace's
  calls directory, and the owner's next turn empties it under the reader.
  - Recommended: record a separate finding, and in that change refuse a `work_dir` that resolves
    under `.agentweave/`. Reason: it is operator-chosen, it already allows today's same-name
    overwrite between the two runs, and no drive has used it; refusing it closes both.
  - Alternatively, add that refusal here, as one more 400 at `:1210-1215` with a failing test. It is
    small, but it is a new refusal on a route, outside WPC-4 and WPC-5.
  - Or accept it, and narrow the sandboxing requirement's "SHALL NOT empty a workspace other agents'
    runs may be using" to the workspaces the Hub itself assigns.
- **wpc5-a: Copilot spec-turn writes.**
  - Recommended: keep `edit` excluded (D4).
  - Choosing (a) adds a task that drops `edit` from `SPEC_TURN_EXCLUDED_TOOLS` on shim spec turns and
    updates the three argv pins.
