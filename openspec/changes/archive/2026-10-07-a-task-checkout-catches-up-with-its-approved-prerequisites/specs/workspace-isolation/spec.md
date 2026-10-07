## MODIFIED Requirements

### Requirement: Provisioning a task checkout is idempotent, and all-or-nothing when it is not

Provisioning SHALL return an existing checkout correctly registered for the expected branch without rebuilding it, and SHALL then bring in the commits of the task's **approved** prerequisites that its branch lacks, so that repeated turns on one task do not repeatedly rebuild it and a dependent started before its prerequisite was approved does not go on without that work.

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

At branch creation, prerequisite work is merged as before (including a prerequisite's accepted
evidence). On an existing branch, only the commits of prerequisites that are `approved` and not
already ancestors of the branch SHALL be merged, each as a merge commit, never by rewriting the
branch. Where there is nothing to merge, nothing SHALL change.

On an existing branch, a merge that cannot be made cleanly SHALL be aborted and the turn refused,
leaving the branch tip and the files exactly as they were; so SHALL a checkout with uncommitted
changes when there is something to merge, and so SHALL a merge that git does not finish in time. The
refusal SHALL name the prerequisite task, the commit, the checkout and the command that merges it,
so that a person can reconcile it; and the refused work SHALL be reported as unstaffed with that
sentence rather than retried silently.

If a prerequisite cannot be brought in at branch creation, provisioning SHALL leave **no checkout and
no branch** behind, and SHALL refuse the turn. A half-provisioned workspace is worse than none: the
next turn would find a registered checkout and adopt it as correct.

When the branch already exists — a task released and worked again — the checkout SHALL be
re-provisioned from that branch, so the task resumes with its own prior work present.

#### Scenario: A second turn on the same task reuses the checkout

- **WHEN** a task that already has a correctly registered checkout is provisioned again, and no newly approved prerequisite commit is missing from its branch
- **THEN** the same directory is returned
- **AND** no branch is re-created and nothing is merged

#### Scenario: A prerequisite approved after the branch was cut is brought in

- **GIVEN** task B depends on task A, and B's branch was cut while A was still being worked
- **WHEN** A is approved and B is provisioned for its next turn
- **THEN** A's commit is an ancestor of B's branch
- **AND** B's own earlier commits are still on it

#### Scenario: A prerequisite that conflicts with the dependent's own work is refused, not forced

- **WHEN** an approved prerequisite's commit conflicts with commits already on the dependent's branch
- **THEN** the turn is refused naming the prerequisite task, the commit, the checkout and the merge command
- **AND** the branch tip and the working files are byte-identical to before

#### Scenario: A merge git does not finish in time leaves nothing half-done

- **WHEN** merging an approved prerequisite into an existing branch times out
- **THEN** the merge is aborted and the turn refused
- **AND** the checkout is not left in an unfinished merge

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
