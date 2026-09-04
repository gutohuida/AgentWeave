# workspace-isolation Specification

## Purpose

The Hub gives concurrent work its own place on disk. This document owns the **mechanism**: what a
workspace is, the namespaces it comes in, where each one lives, how it is provisioned, how it is
given back, and how it is reported to an operator.

It deliberately does not own *who gets which workspace for a given turn* — that is
`run-task-binding` (the task is resolved before the workspace is chosen) and
`operator-agent-creation` (a turn about a task works in that task's checkout). Nor does it own
*when* a release is triggered, which is `task-lifecycle-governance`. Those documents answer
"which one, and when"; this one answers "what it is, and what it guarantees".

Written as a current-behaviour record on 2026-08-27, after the change
`2026-08-27-work-is-isolated-per-task` shipped per-task isolation and renamed a public API response
shape (`ConflictInfo.agents` to `.workspaces`, `WorktreeInfo` to `WorkspaceInfo`) with no
requirement of record constraining it. Implemented in `hub/hub/worktrees.py`,
`hub/hub/task_workspace.py` and `hub/hub/api/v1/worktrees.py`.

## Requirements

### Requirement: The Hub owns two workspace namespaces that cannot collide

The Hub SHALL provision isolated checkouts in two namespaces: one keyed by **agent**, one keyed by
**task**. An agent's checkout SHALL live at `.agentweave/worktrees/<agent>` on branch
`agentweave/<agent>`. A task's checkout SHALL live at `.agentweave/tasks/<task-id>` on branch
`agentweave/task/<task-id>`.

The two namespaces SHALL be disjoint **by construction rather than by convention**. An agent name is
drawn from a character class that excludes `/`, so the extra `task/` segment in a task branch is a
shape no agent branch can take. Without that segment the branch `agentweave/task-ab12cd34ef56` would
be simultaneously a valid task branch and the branch of an agent legitimately named
`task-ab12cd34ef56`, and the system would have no way to tell which of the two a ref belonged to.

A task id SHALL be accepted only in the form the product itself mints: `task-` followed by 1 to 64
**lowercase** hexadecimal digits. Lowercase is required rather than normalised: two ids differing
only in case are two distinct git refs but a single directory on Windows and macOS, so accepting
both would let one task's checkout be handed to another.

An agent name SHALL be validated before it is used as either a path component or a ref suffix.

#### Scenario: A task and an agent that share a name do not share a workspace

- **WHEN** an agent is named identically to a valid task id and both have checkouts
- **THEN** the two occupy different directories
- **AND** the two are on different branches

#### Scenario: An id the product could not have minted is refused

- **WHEN** a task checkout is requested for an id that is not `task-` followed by lowercase hex
- **THEN** the request is refused
- **AND** no directory and no branch are created

#### Scenario: The same id in a different case is not the same task

- **WHEN** a task checkout is requested for an id containing uppercase hexadecimal digits
- **THEN** the request is refused rather than folded onto the lowercase id's checkout

### Requirement: Asking where work happens never causes it to happen

Deriving a workspace path or a branch name SHALL provision nothing. These SHALL be pure
computations, so that the answer for a workspace that does not exist yet is where it *will* be
rather than an error or a newly created directory.

An operator reading a configuration surface must not thereby write to the repository. Were
derivation and provisioning the same operation, opening a panel would create checkouts, and the
number of checkouts a project carries would be a function of who looked at what.

#### Scenario: An agent that has never run reports where it will work

- **WHEN** the workspace of an agent with no checkout is queried
- **THEN** the path and branch it would use are reported
- **AND** it is reported as not provisioned
- **AND** no directory is created

### Requirement: Provisioning a task checkout is idempotent, and all-or-nothing when it is not

Provisioning SHALL return the existing checkout unchanged when one is already correctly registered
for the expected branch, so that repeated turns on one task do not repeatedly rebuild it.

Provisioning SHALL refuse, rather than adopt, a path that exists but is not the registered git
worktree for the expected ref — including a symbolic link. Adopting an unknown directory would hand
an agent a tree whose contents the system cannot account for.

Provisioning SHALL refuse a checkout left in an unfinished merge, and SHALL say so. That is the one
state a process killed mid-provision can leave, and handing it over asks an agent to reconstruct
what happened to it from a tree full of conflict markers.

When the branch does not yet exist, the checkout SHALL be cut from a supplied integration base, and
SHALL NOT be cut from wherever the project checkout currently sits. The base SHALL be supplied by
the caller; a task checkout requested without one is an error rather than an occasion to substitute
`HEAD`.

Prerequisite work SHALL be merged **only at branch creation**. On any later call the branch already
carries the task's own commits, which the unwind below would destroy.

If a prerequisite cannot be brought in, provisioning SHALL leave **no checkout and no branch**
behind, and SHALL refuse the turn. A half-provisioned workspace is worse than none: the next turn
would find a registered checkout and adopt it as correct.

When the branch already exists — a task released and worked again — the checkout SHALL be
re-provisioned from that branch, so the task resumes with its own prior work present.

#### Scenario: A second turn on the same task reuses the checkout

- **WHEN** a task that already has a correctly registered checkout is provisioned again
- **THEN** the same directory is returned
- **AND** no branch is re-created and no prerequisite is re-merged

#### Scenario: An unrecognised directory in the way is refused

- **WHEN** a task's checkout path exists but is not the registered worktree for that task's branch
- **THEN** provisioning is refused with a reason naming the path

#### Scenario: A failed prerequisite leaves nothing behind

- **WHEN** provisioning a new task checkout and a prerequisite cannot be merged
- **THEN** the turn is refused
- **AND** neither the checkout directory nor the task branch exists afterwards

#### Scenario: A task worked again resumes its own history

- **WHEN** a task whose checkout was released, and whose branch carries commits, is provisioned again
- **THEN** the checkout is restored on that branch with those commits present

### Requirement: A release gives back the directory and never the work

Releasing a checkout SHALL remove the directory and SHALL NOT remove the branch. What bounds a
repository's size is the checkout; the branch is the record of what was done and is what an operator
reads afterwards.

Any uncommitted change in the checkout SHALL be committed onto its branch before the directory is
removed. Any commit the branch carries beyond the primary checkout's HEAD SHALL be **reported**
rather than discarded.

A release SHALL report what it did: whether a checkout was actually released, the branch retained,
whether uncommitted work was snapshotted and under which commit, and which commits remain
unintegrated.

Releasing a task's checkout SHALL NOT release any review checkout, which is keyed by the reviewing
agent rather than by a task and therefore has none to release.

#### Scenario: Uncommitted work survives a release

- **WHEN** a checkout with uncommitted changes is released
- **THEN** those changes are committed onto its branch first
- **AND** the release names the commit it created

#### Scenario: The branch outlives the checkout

- **WHEN** a checkout is released
- **THEN** its directory no longer exists
- **AND** its branch still does

#### Scenario: Work not yet integrated is reported, not dropped

- **WHEN** a checkout whose branch carries commits absent from the primary checkout is released
- **THEN** those commits are reported by the release

### Requirement: The Hub commits under its own identity

The Hub SHALL supply an explicit author identity on every commit it creates itself — a release
snapshot, or the merge that integrates approved work — and SHALL NOT rely on the repository's
configured identity.

A project in which the operator has never configured a git identity is an ordinary project, and git
refuses to commit there at all. Relying on configuration means the Hub can snapshot an agent's work
and then fail to merge it, which is a state in which work exists but cannot be shipped.

#### Scenario: A project with no configured identity can still be committed to

- **WHEN** the Hub snapshots or integrates work in a repository with no configured user identity
- **THEN** the commit succeeds
- **AND** it is attributed to the Hub's own identity

### Requirement: Expensive shared dependency directories are linked, not rebuilt

A fresh checkout SHALL have a small, explicit set of dependency directories linked into it from the
project checkout, rather than reinstalled.

The set SHALL stay explicit, and SHALL be extended only for directories that are both expensive to
regenerate and safe to share read-only across concurrent checkouts. Provisioning a checkout is on
the path of an agent's first writing turn, so a full dependency install there is a per-task cost
paid at the least convenient moment.

#### Scenario: A fresh checkout does not reinstall shared dependencies

- **WHEN** a checkout is provisioned in a project that has a shared dependency directory
- **THEN** that directory is reachable from the new checkout without being reinstalled

### Requirement: A reported workspace says which namespace it belongs to

Every API response describing a checkout SHALL identify **which kind** of workspace it is and what
it belongs to, as two fields — a kind and a name — rather than as an agent name alone.

A single name field carrying two namespaces is not sufficient: a task id is not an oddly named
agent, and a consumer given only a name cannot tell which of the two it holds.

Listing the checkouts of a project SHALL read git's own registration, and SHALL NOT compose an
answer from the derived paths. A checkout registered somewhere unexpected SHALL then be **absent**
from the listing rather than reported at a location it does not occupy.

Listing SHALL provision nothing.

The listing SHALL exclude retained branches that have no checkout, and review checkouts, which are
detached and carry no branch record.

An agent's workspace response SHALL enumerate the task checkouts of that agent's live tasks, and
SHALL distinguish a task that has no checkout of its own because its work predates per-task
isolation from one whose checkout is merely not provisioned yet. Without that distinction an
operator looking for a task's directory and finding none would reasonably conclude the work was
lost.

#### Scenario: Both namespaces appear in one listing

- **WHEN** a project has both an agent checkout and a task checkout
- **THEN** both are listed
- **AND** each states which kind it is

#### Scenario: Listing creates nothing

- **WHEN** the checkouts of a project with no provisioned workspaces are listed
- **THEN** the listing is empty
- **AND** no directory has been created

#### Scenario: A checkout in an unexpected location is not misreported

- **WHEN** a branch in the Hub's namespace is registered at a path other than the one its namespace
  predicts
- **THEN** it is omitted from the listing rather than reported at the predicted path

#### Scenario: A task without its own checkout is distinguishable from one not yet provisioned

- **WHEN** an agent holds a task whose work began before per-task isolation
- **THEN** that task is reported as working in the agent's checkout
- **AND** it is distinguished from a task whose own checkout simply does not exist yet

### Requirement: A conflict is reported between workspaces, not between agents

A report of two diverging checkouts SHALL name each side as a workspace — its kind and its name —
and SHALL NOT name each side as an agent.

Since per-task isolation, a diverging branch may belong to a task rather than to an agent, and **two
tasks held by the same agent can diverge from each other**. A pair of agent names cannot express
that: it would report the agent as conflicting with itself, or drop the report for want of a second
distinct name.

Conflict detection SHALL be performed without touching the working tree or the index of any
checkout, so that asking whether two branches conflict never disturbs work in progress.

#### Scenario: Two tasks of one agent can conflict with each other

- **WHEN** two task branches held by the same agent modify the same paths divergently
- **THEN** a conflict is reported between the two task workspaces
- **AND** each side is identified by its own task

#### Scenario: Detection disturbs no checkout

- **WHEN** conflicts are detected in a project with provisioned checkouts
- **THEN** no checkout's working tree or index is modified

### Requirement: A refusal to provision names the workspace it is about and what would clear it

A refusal to provision a workspace SHALL identify which workspace could not be prepared — the
agent's own, or a named task's — and SHALL state what the operator would have to do to clear it.

Which workspace it is about is not a detail of the wording. It decides what is blocked: an agent's
own workspace carries every turn of that agent that is not about a task, and a task's checkout
carries one task's work. A refusal that names the agent for both sends the reader to the wrong
directory in one of the two cases, and leaves anything downstream deciding what is blocked to guess
from the sentence.

Stating the repair is required because the input is held. Where the system holds the operator's
input until they perform a repair, a refusal that names the obstruction but not the remedy asks them
to work it out from outside the product — and the wait continues until they do.

The remedy SHALL be stated per obstruction rather than as one sentence covering all of them. A
directory that is not the expected checkout, a link where a directory was expected, and a checkout
left mid-merge are cleared by different actions, and a single message covering all three sends the
operator looking for the wrong thing.

#### Scenario: The agent's own workspace is refused

- **WHEN** an agent's own workspace cannot be prepared
- **THEN** the refusal identifies it as that agent's workspace
- **AND** it states what would clear the obstruction it found

#### Scenario: A task's checkout is refused

- **WHEN** the checkout for a task cannot be prepared
- **THEN** the refusal names the task rather than the agent whose turn it was
- **AND** it states what would clear the obstruction it found

#### Scenario: Each obstruction states its own remedy

- **WHEN** provisioning is refused because a path exists that is not the expected registered checkout
- **THEN** the remedy stated is the one for that obstruction
- **AND** a different obstruction at the same path states a different remedy
