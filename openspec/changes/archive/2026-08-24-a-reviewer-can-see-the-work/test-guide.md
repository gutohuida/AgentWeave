# User test guide — a reviewer can see the work

Task 7.1. What an operator does, what they should see, and what it looks like when it goes wrong.

This is the half of verification a person has to do. The suite already proves the mechanism; what
it cannot prove is that a reviewing agent, reading its turn context, understands it is reviewing
rather than building. That judgement is yours, and design D4 names it as the most likely failure.

## Before you start

- The trial Hub on port **8010**, started **from `hub/`** so the source package is what runs:

  ```bash
  cd hub
  DATABASE_URL="sqlite+aiosqlite:///$HOME/.agentweave/hub/profiles/beta/agentweave.db" \
    py -3.11 -m uvicorn hub.main:app --port 8010 --host 127.0.0.1
  ```

  **Not `agentweave --port 8010`.** The console script is the *installed* `agentweave-hub`, whose
  migrations stop short of this branch's head — it refuses a database migrated from source with
  `Can't locate revision identified by '0085'`. Running uvicorn from `hub/` puts the working
  directory on `sys.path`, so the source package is what serves and what migrates.

- A project that is a **git repository** with at least one task whose work an agent has finished
  and recorded evidence for. A project with no repository cannot be reviewed this way and says so.
- Two agents on the roster: the one that did the work, and a different one to review it.

## Requesting a review

There is one operator-initiated path, deliberately. Automatic dispatch — a `completed` task
firing a reviewer without being asked — belongs to `loop-becomes-a-flow`, and this change exists so
that when it lands the reviewer it fires can actually read code.

```bash
curl -X POST http://127.0.0.1:8010/api/v1/projects/<project>/agent/trigger \
  -H "Authorization: Bearer $AW_KEY" -H "Content-Type: application/json" \
  -d '{"agent": "critic",
       "message": "Review this task and report what you find. Do not fix anything.",
       "review_task_id": "task-e6b05093"}'
```

`review_task_id` names the task whose finished work is being reviewed. It is **not** `task_id`:
that one binds the run to a task it is working on, and a reviewer is not the author.

## What you should see

**A new directory, one per reviewing agent.**

```
<project>/.agentweave/reviews/critic
```

Not one per review. The second review by the same agent re-points this same directory at the new
commit. If you see a directory per task or per commit, something is wrong.

**Detached, and saying so.** Inside that directory:

```bash
$ git status
HEAD detached at cad5d74
```

That is correct and expected, not a problem to fix. It is how git itself states the reviewing role
without depending on the prompt to.

**The reviewer can read work that is not on your main branch.** This is the whole point. Open the
review checkout and confirm a file the author changed on its own branch is there in its changed
form, while your own checkout still has the old one.

**The reviewer can run your tests — with one measured caveat.** `node_modules`, `.venv` and `venv`
are symlinked in from the project the same way they are for a working checkout.

**On this machine they are not.** Measured 2026-08-24: `Path.symlink_to` fails with
`WinError 1314, A required privilege is not held by the client` — Windows without Developer Mode or
admin rights. `_symlink_shared_dependencies` degrades silently by design rather than failing
provisioning, so the checkout is still created and simply has no dependencies in it.

That matters more here than it does for a working checkout, because design D1's entire
justification for giving the reviewer a *checkout* rather than a *diff* is that it can run the
suite. A Python project whose tools are on `PATH` is unaffected — that is why the `ledger-stress`
drive could run pytest. **A Node project reviewed on this machine cannot run its tests without
installing its own copy first.** Turning on Windows Developer Mode fixes it for every worktree,
not just reviews.

## The judgement only you can make

Read the turn context the reviewer was given — `<review checkout>/.agentweave/context/<agent>.md`,
the `### Your workspace` section. Then answer one question:

> **Would an agent reading this understand it is reviewing rather than building?**

It should say, in this order: that this is a review turn; which task and commit; that
`HEAD detached` is expected; that it should read, search and **run the test suite**; that it must
**not** fix what it finds, because the author does that through `revision_needed`; and that its own
working checkout is outside this turn's boundary.

If a reviewer comes back having *fixed* the bug and reported the work verified, this text is what
failed — not the boundary. Say so, because no test catches it.

## When it refuses, and what each refusal means

Every one of these is a stated refusal with a reason, never a guess or a nearby commit.

| What you see | What it means |
|---|---|
| `task … has no recorded evidence, so there is no commit to review` | The work was never recorded. There is nothing to check out. Have the author record evidence first. |
| `task … has recorded evidence, but none of it names a commit` | The project is not a git repository, so evidence names changed paths instead. This kind of review is unavailable here. |
| `commit … is not present in this repository` | The evidence names a commit this checkout does not contain — an author branch pruned, or evidence carried over from a different clone. **Not** worked around: putting the reviewer on a nearby commit would produce a verdict about code nobody wrote. |
| `critic is archived and cannot be triggered` | Nothing runs an archived agent, reviews included. |
| `work_dir cannot be combined with a review turn` | A review turn's workspace is the checkout of the commit under review; there is nothing for `work_dir` to mean. |
| `this turn batches requests to review more than one task` | Two queued entries named different tasks. One turn has one workspace, so this is refused rather than silently resolved to one of them. |

## Two evidence rows naming different commits

If the task's work moved — evidence recorded twice, at two commits — the reviewer gets the **most
recent** one and is **told** the earlier one existed, by id and sha. Check the context says so. A
reviewer that knows the work moved can ask why; one that does not cannot.

## What this change deliberately does not do

- It does not decide **who dispatches** a reviewer. That is `loop-becomes-a-flow`.
- It does not decide **who may approve**, and therefore whether an agent may write to your main
  branch. Still open.
- It does not read a per-task review policy. That is a later change of its own.

`Task.reviewer` — the `reviewer` field on a task in a specification document — is now read, by
`resolve_declared_reviewer`. If it names an agent that is not on your roster, or one that is
archived, review **falls back to you** and the reason is carried with it. It never silently becomes
a different agent: an operator reading "reviewed by critic" when `critic` does not exist and
somebody else reviewed it has been told something false about who checked the work.

## Cleaning up

Removing an agent removes its review checkout too, including for an agent that only ever reviewed
and never had a working worktree of its own. After a few reviews, confirm:

```bash
ls <project>/.agentweave/reviews/
```

should list at most one directory per agent that has reviewed — never one per review.
