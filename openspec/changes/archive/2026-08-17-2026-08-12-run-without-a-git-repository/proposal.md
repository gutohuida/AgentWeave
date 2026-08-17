# A project without a git repository still runs its agents

## Why

**A new project cannot run an agent until someone runs `git init` in it, and nothing about creating
the project says so.** The Hub will happily open or create any directory —
`hub/hub/project_workspace.py` has no git awareness at all, and `local-project-workspace` states that
registration *"SHALL NOT initialize git … or otherwise modify project source"*. The refusal arrives
much later, at the first turn, from a module the operator never chose to involve.

The mechanics: isolation is the default and is expressed negatively. `worktrees.is_writing_agent`
(`hub/hub/worktrees.py:117-121`) returns `True` for any config without `read_only`, and every
creation path produces exactly that — `config={}` from the operator UI (`api/v1/agents.py:682`),
`NULL` from session sync (`api/v1/session_sync.py:98`). **No UI control can set `read_only`**, by
deliberate decision (`AgentSettingsPage.tsx:247-251`). So every agent an operator can create is a
writing agent, and `resolve_agent_workspace` (`worktrees.py:219-226`) raises
`IsolationUnavailableError` for all of them when the root is not a repository.

That surfaces as a turn that never starts. `turn_scheduler.py:115` converts the trigger error into a
`waiting_reason`, so the operator sees a queued message and, until commit `6140666` added the probe
in `inbound_queue.py:176-192`, no reason at all. **This cost two debugging sessions on two separate
testbeds** — both diagnosed as something else first.

The fail-closed choice was right for the case it was written for. Its justification
(`worktrees.py:216-217`) is that *"spawning one in the primary checkout would reintroduce silent lost
updates"* — true when a repository exists and isolation is genuinely available. It does not hold when
there is no repository: there is no isolation to lose, no primary checkout to damage, and no branch
anyone could have merged. The Hub is refusing to do the only thing it could do.

Nothing in `openspec/specs/` requires the refusal. The governing requirement
(`operator-agent-creation/spec.md:63-78`) says only that creation must not provision a worktree and
that the scheduler provisions one at the first writing turn. Being unable to is unspecified
behaviour that was resolved by refusing.

## What Changes

- **A writing agent in a directory that is not a git repository runs in that directory.** The
  workspace resolver returns the project root instead of raising. This is the whole change; the rest
  is telling the truth about it.
- **Failing closed is kept where it still means something.** A project that *is* a repository and
  whose worktree cannot be provisioned still refuses. Silently dropping isolation for a project that
  has it would strand the agent on the primary checkout, which is the failure the fail-closed rule
  was written to prevent.
- **The queue stops reporting a blocker that no longer blocks.** The git-repo waiting reason added in
  `6140666` is removed.
- **The degradation is stated, not hidden.** The agent's per-turn context says it is working in the
  project's shared directory with no isolation available; the workspace endpoint reports the same as
  information rather than as a pending refusal; the agent settings panel stops presenting it as an
  alert.
- **`work_dir` stops being refused for a reason that does not apply.** A writing agent cannot
  override isolation — but in a project with no repository there is none to override.

## Capabilities

### Modified Capabilities

- `operator-agent-creation`: the requirement that the scheduler provisions an isolated worktree at
  the first writing turn gains the case where it cannot, and a new requirement states that a project
  without a repository runs its agents in place, visibly.

## Impact

**Behaviour** — `worktrees.resolve_agent_workspace` returns `repo_root` for a writing agent in a
non-repository. `IsolationUnavailableError` survives for the provisioning failures it was really
about.

**Removed** — the git-repo branch of `inbound_queue.queue_status`, and the "Its turns will be refused
until it is one" wording in `api/v1/worktrees.py:137-140`.

**Tests** — four existing tests assert the current refusal and are inverted rather than deleted:
`test_worktrees.py:105`, `test_agent_trigger.py:444`, `test_inbound_queue.py:429`, and the UI's
`agentWorkspaceSection.test.tsx:113`. The test that must **not** change is
`test_worktrees.py:112`, which pins that a git failure does not fall back.

**No migration.** Isolation has no column; it is `Agent.config["read_only"]`, and this change adds
no field.

**One unrelated defect fixed because this change exposed it** — `ProjectWorkspace.resolve_relative`
accepted a project-relative path beginning with `~`. It was unreachable while every writing agent's
`work_dir` was refused earlier; making `work_dir` reachable made it reachable. See design.md D6.

## Non-Goals

- **Not making projects git repositories.** `local-project-workspace` is explicit that registration
  does not modify project source, and this change makes that position affordable rather than
  contradicting it. Whether project *creation* should offer `git init` is a separate question.
- **Not adding an isolation control to the UI.** `AgentSettingsPage.tsx:247-251` gives a real reason
  it is absent — flipping an agent with uncommitted work in its worktree to the shared checkout
  would strand that work — and two tests assert the absence.
- **Not protecting concurrent writers in a non-repository project.** Two writing agents in one
  directory can lose each other's updates. That is the risk worktrees exist to convert into a visible
  conflict, and without a repository there is no mechanism to convert it. The Hub says so; it does
  not serialize, lock, or refuse. **Accepted by the operator** — *"It's acceptable. The user has to
  deal with this."* — which makes the saying-so the requirement rather than a mitigation that could
  be tidied away later.
- **Not giving a non-repository project checkpoints with file lists.** A checkpoint's changed-file
  list is read from per-run snapshot commits (`checkpoints.py:128-137`); with no repository there are
  no commits and the list is empty. `checkpoints.py:125` already guards this.
- **Not changing what a read-only agent does.** It shared the project checkout before and after.
