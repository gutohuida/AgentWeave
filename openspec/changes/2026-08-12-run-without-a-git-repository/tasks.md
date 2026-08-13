# Tasks — A project without a git repository still runs its agents

Small change, one decision point. Section 1 exists because the same refusal is restated in four
places, and fixing the resolver while leaving the other three tells the operator a project is blocked
after it stops being blocked.

## 1. Confirm the blast radius before changing the resolver

- [x] 1.1 Confirm `worktrees.resolve_agent_workspace` is the **only** production caller of
      `ensure_worktree`, and that `agent_trigger.py` is its only production caller. If either is
      wrong, a second path can still refuse and section 2 is incomplete.
      **Confirmed:** `worktrees.py:226` is the sole call of `ensure_worktree`; `agent_trigger.py:364`
      the sole call of `resolve_agent_workspace`. The two other mentions are comments in
      `api/v1/worktrees.py:103` and `checkpoints.py:249`, both explaining why they *do not* call it.
- [x] 1.2 Confirm nothing outside `worktrees.py` raises or constructs `IsolationUnavailableError`,
      so the two remaining raise sites are the whole surface.
      **Confirmed:** raised at `worktrees.py:178` and `:222` only, caught at `agent_trigger.py:365`.
      After 2.1 only `:178` — the provisioning failure — remains.
- [x] 1.3 Confirm `checkpoints.files_changed_in` is unreachable with a `None` worktree and that
      `checkpoints.py:125` is the guard. A run with no snapshot must produce an empty changed-file
      list, not an exception.
      **Confirmed:** called only at `checkpoints.py:132`, inside `_files_from_runs`, which returns
      `[]` at `:125-126` for a `None` or absent worktree.

## 2. The resolver (D1, D2)

- [x] 2.1 `resolve_agent_workspace` returns `repo_root` for a writing agent when
      `is_git_repo(repo_root)` is false. Update the docstring: fail-closed now describes
      provisioning failure, not the absence of a repository.
- [x] 2.2 Leave `ensure_worktree`'s `IsolationUnavailableError` raise site untouched.
      **`test_resolve_agent_workspace_does_not_fall_back_after_git_failure`
      (`test_worktrees.py:112`) must keep passing without edit.** If it needs editing, stop — the
      change has gone wrong.
      **It passed unedited.** Only its docstring gained a note saying why it must stay that way.
- [x] 2.3 Update the module docstring (`worktrees.py:1-21`), which states isolation as unconditional.

## 3. Everywhere the refusal is restated

- [x] 3.1 `api/v1/worktrees.py:129-141` — report `isolated=False`, `provisioned=True`,
      `working_dir=repo_root`, and a reason describing the absent repository rather than a refusal
      to come (D5).
- [x] 3.2 `api/v1/inbound_queue.py:176-192` — delete the git-repo branch. Keep the
      launchable-is-not-startable comment above it (D4).
      **Deviation from this task as written:** it also said to delete the `project_workspace`
      import. Kept, along with the workspace-unavailable reason it serves — that one describes a
      real block (`turn_scheduler.py:93-114` pauses the queue for it), unlike the git-repo reason.
      Only the `worktrees` import and the git branch went.
- [x] 3.3 `agents.py:1000-1015` — when the working directory is the project root and no repository
      exists, say so in the `### Your workspace` block. A read-only agent's wording must not change
      (D3).
      Threaded as a new `isolation_unavailable` parameter rather than recomputed in the renderer:
      `agent_trigger.py` already knows, and a second `git rev-parse` per turn to re-derive a fact
      the caller holds is a subprocess spent on nothing.
- [x] 3.4 `agent_trigger.py:346-350` and the HTTP-layer copy at `:658-662` — refuse `work_dir` for a
      writing agent only where the project is a repository (D6). Check both; they are duplicated
      deliberately and drift silently.
      Both updated. The direct path computes `project_is_repo` once and reuses it for 3.3.
- [x] 3.5 `AgentSettingsPage.tsx:296-300` — the reason is information, not an alert. Drop
      `role="alert"` and the amber treatment for this case; keep them if a genuine failure reason is
      ever reported through the same field.
      **The conditional half was not built:** `unavailable_reason` has no discriminator, and the
      endpoint sets it in exactly one case — the absent repository. A branch on a distinction the
      data does not carry would be dead code. If a real failure reason is ever reported through
      this field it needs one, and that is where the alert comes back.

## 4. Tests — agent-verifiable

- [x] 4.1 `test_worktrees.py:105` — invert
      `test_resolve_agent_workspace_refuses_writer_when_not_a_git_repo` into
      `..._runs_writer_in_place_when_not_a_git_repo`: returns `repo_root`, creates nothing on disk.
- [x] 4.2 Assert the negative in the same file: running in place creates no `.git`, no
      `.agentweave/worktrees`, and no branch.
      `test_running_in_place_creates_no_repository_and_no_worktree` also asserts the directory is
      still empty afterwards — the strongest available statement that the Hub did not "help".
- [x] 4.3 `test_agent_trigger.py:444` — invert
      `test_writing_agent_is_not_spawned_when_isolation_cannot_be_prepared`: the turn now starts,
      with the project root as its working directory and no `waiting_reason`. Add a sibling that
      keeps the refusal for a **real repository** whose provisioning raises.
      Both exist. The sibling stubs `ensure_worktree` to raise and asserts the turn stays queued
      with the provisioning failure named — the half of fail-closed that survives.
- [x] 4.4 `test_inbound_queue.py:429` — `test_queue_status_names_a_missing_git_repository` becomes an
      assertion that no waiting reason mentions a repository for that project.
      Asserts neither "git" nor "repository" appears in the reason, so a reworded version of the
      same advice cannot creep back.
- [x] 4.5 A turn context test: a writing agent in a non-repository project is told it has no isolated
      checkout; a read-only agent's block is unchanged.
      `hub/tests/test_workspace_posture_context.py` — four cases, including the isolated one, which
      is pinned because the new branch sits directly above it.
- [x] 4.6 A workspace-endpoint test covering both ways of sharing (D5) — configuration versus no
      repository — asserting they are distinguishable.
- [x] 4.7 `work_dir` accepted for a writing agent in a non-repository project and still refused in a
      repository (D6).
- [x] 4.8 A checkpoint over a run with no snapshot reports an empty changed-file list and does not
      raise (1.3).
      **Already covered, so no test was added.**
      `test_turns_predating_the_snapshot_column_report_no_files_rather_than_a_guess` exercises
      exactly this state (`worktree=None`, `sha=None`) — a non-repository run is mechanically
      identical to a pre-0043 one. Its docstring now names this as the second producer, so the
      coverage is findable from here.
- [x] 4.9 UI: `agentWorkspaceSection.test.tsx:113` — the no-repository case is reported without
      `role="alert"`. The two tests asserting no isolation control (`:124`,
      `agentCreationUi.test.tsx:89`) must keep passing unchanged.
      Both passed unedited.
- [x] 4.10 `pytest hub/tests/ -q` and `pytest tests/ -q` **run separately** — together they fail
      collection. `npx vitest run` and `npx tsc --noEmit` from `hub/ui`.
- [x] 4.11 `ruff check hub/ src/`, `black` on every file touched.
- [x] 4.12 Rebuild `hub/ui/dist`, copy over `hub/hub/static/ui`, confirm with `diff -rq`.
- [x] 4.13 `npx openspec validate --changes --strict` and `--specs --strict`.

## 4b. Found by the full suite — a containment check that was never being reached

Not anticipated by any task above, and the reason the full suite is run rather than the
directly-affected files.

**`test_agents.py::test_agent_trigger_rejects_work_dir_with_tilde` failed**: `work_dir` of
`~/projects/secret` came back `200` where it had always been `400`. The test was not wrong and the
new behaviour was not wrong either — **the test had been passing for the wrong reason since it was
written.** A writing agent was refused a `work_dir` outright, so the tilde never reached
`ProjectWorkspace.resolve_relative`. Task 3.4 removed that refusal for non-repository projects, the
path reached the validator for the first time, and the validator accepted it.

It accepted it because Python does not expand `~`: `~/projects/secret` is a relative path with no
`..`, so it resolves to a literal `~` directory under the project root and every containment check
passes. Contained here; not contained wherever something expands it — and this value becomes a
spawned process's working directory.

- [x] 4b.1 `project_workspace.resolve_relative` refuses a path whose first component starts with
      `~`. First component only: expansion applies there, and `backup~` is a real directory name.
      Fixed at the containment chokepoint rather than in the `work_dir` guard, so every caller
      gets it rather than the one that happened to expose it.
- [x] 4b.2 Add `~/projects/secret` and `~root/projects/secret` to the `resolve_relative` rejection
      parametrize in `test_project_workspace.py`, so the rule holds on its own rather than as a
      side effect of an unrelated guard.

## 4c. Driven against the running Hub

A temporary project was opened on `C:\Users\huida\Documents\aw-norepo-check` — a real directory
with a `README.md` and **no** `.git` — an agent registered and bound to the seeded Claude runner,
one turn triggered, and the project's rows and directory removed afterwards. The Hub was restarted
onto this commit first; the old process was serving the pre-change code.

**The original symptom is gone.** `POST /agent/trigger` returned `status: "running"` with
`waiting_reason: null` and run `run-32b962f8`. Before this change the same call returned
`status: "queued"` with *"… is not a git repository, so an isolated worktree cannot be prepared."*

**It ran where it stands.** After the turn, the project directory contained `README.md`,
`.agentweave/project.json` and `.agentweave/context/probe.md` — the context file is written into
the run's own working directory, so its presence there is the cwd. `\.git` absent,
`.agentweave/worktrees` absent: the Hub created no repository and no worktree to satisfy an
invariant.

**The agent was told.** The `### Your workspace` block it received, read back off disk:

> - This directory is not a git repository, so there is no isolated worktree and no branch of your
>   own. Do not expect git to work here, and do not offer to commit or branch.
> - Any other agent in this project works in this same directory. Your edits and theirs can
>   overwrite each other with no conflict to resolve …

**The workspace report** (`GET /worktrees/probe`): `isolated: false`, `provisioned: true`,
`branch: null`, `working_dir` the project directory, and the reason naming the absent repository.

**The queue** (`GET /queue/probe/status`): `waiting_reason: null`.

**The run record:** `completed`, exit code `0`, `snapshot_commit_sha` NULL — the snapshot-free run
D7 and 4.8 describe, reached in practice rather than only in a test.

## 5. Verification — human-only (the operator runs these)

Nothing below can be closed by an agent. Each needs a person looking at a running app. 5.1 was
observed via the API in 4c, but not with a person driving the UI, which is what it asks for.

- [ ] 5.1 **The original symptom is gone.** Create a project on a directory that is not a repository,
      create an agent, send a message. The turn should start, not queue.
- [ ] 5.2 Does the agent behave sensibly with no repository — does it avoid proposing branches and
      commits, and does it read a failed `git status` correctly rather than as a broken environment?
      This is what D3's sentence is for and no test can answer it.
- [ ] 5.3 Is the workspace panel's no-repository note legible as information rather than as a
      problem? It was an amber alert; confirm it no longer reads as one.
- [x] 5.4 Run two writing agents in the same non-repository project and see whether the shared
      directory is tolerable in practice, or whether D7's accepted risk needs revisiting.
      **Closed by operator decision, not by observation** — *"It's acceptable. The user has to deal
      with this."* The question this task asked was whether to accept the trade, and it is
      answered; nobody has yet watched two agents collide in practice, and this task no longer asks
      anyone to. If that observation is wanted later it is a new question, not this one reopened.
      Consequence: the Hub's whole obligation here is to **say so**. The sharing sentence in the
      turn context is load-bearing and is now pinned by a spec scenario as well as a test, so it
      cannot be dropped later as noise while the permission stands.
- [ ] 5.5 Confirm an existing repository-backed project is unchanged — its agents still get worktrees
      on their own branches.

## 6. User test guide

**Setup.** A directory that is not a git repository, and one that is. `C:\Users\huida\Documents\quicktest`
was made a repository during this session's resume — use a fresh directory, or remove its `.git`.

1. **Open the non-repository directory as a project.** Create an agent in it. Nothing should warn you
   about git.
2. **Send it a message.** It should start working. Before this change it queued with
   *"… is not a git repository, so an isolated worktree cannot be prepared."*
3. **Ask it where it is working.** It should name the project directory and know it has no isolated
   checkout and no branch.
4. **Open the agent's settings.** The workspace section should say it shares the project directory
   because there is no repository — as a note, not an amber alert, and with no branch named.
5. **Ask it to commit its work.** It should tell you there is no repository rather than trying and
   failing.
6. **Now open the repository-backed project.** Its agent should still get its own worktree on
   `agentweave/<agent>`, exactly as before.
7. **Optionally, run two agents at once in the non-repository project.** They share one directory,
   so they can overwrite each other. The Hub tells each of them so and does not stop them. This is
   the accepted arrangement, not an open question — it is worth doing only if you want to see what
   a collision looks like before you meet one.

**What is deliberately absent:** the Hub never runs `git init` for you; there is still no UI control
for isolation; and a non-repository project's checkpoints carry no changed-file list, because there
are no commits to read one from.
