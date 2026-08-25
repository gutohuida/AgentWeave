# Group 11 — the live state, and what each check now costs

Written 2026-08-25. Companion to `test-guide.md`, which says *what* to judge; this says **where the
trial Hub already stands**, so each of the seven checks is one action rather than a setup.

Everything below is measured against the trial Hub on **port 8010**, project **`ledger-stress`**
(`proj-18e5d4e0`), workspace `C:\Users\huida\Documents\aw-stress`, flow **`job-bdea22bb0308`** /
`loop-e4b864459808`, currently **disabled**.

## Read this first: do not re-enable the flow yet

**Finding F45 blocks it.** `critic` has already reviewed `task-23a0986e7fe9` and left it in
`completed`, which is the only status the flow treats as reviewable. The board already shows the
next firing's decision — `{"id": "task-23a0986e7fe9", "agent": "critic", "agent_role": "next"}` —
so re-enabling re-runs a review that has been done, changes nothing, and repeats every five
minutes. `stop_when_queue_empties` cannot end it, because the task never becomes terminal, and the
project has no token budget set.

Two ways past it, both cheap:

- **Clear the way by hand** — accept `ev-6e7f3bc72c24` and approve `task-23a0986e7fe9`, which is
  the decision `critic` deferred to you anyway. The task leaves the pool and the flow moves on.
- **Or leave it exactly as it is** and use it as F45's reproduction, judging 11.5 from the one
  firing described under that check below.

Nothing else here needs the flow enabled.

## The three checks that cost nothing — do these first

### 11.6 — the spend is visible · **ready now**

`GET /api/v1/projects/proj-18e5d4e0/accounting` answers it in one call, with no reconstruction from
runs:

```
project: 12,976,857 tokens over 36 measured turns, $2.71 api-equivalent
builder:  9,563,229   critic: 3,276,251   relay: 137,377
```

Judge whether that arrives early enough to act on. **One thing to weigh:** `relay` reports tokens
but `api_equivalent_usd_micros: null`. That is not a gap in the Hub — the dollar figure comes from
the CLI's own report (`total_cost_usd` for Claude, `cost` for Codex), and the Codex CLI does not
send one. So a mixed-CLI flow can tell you its tokens in full but its money only in part. Whether
that is honest-and-fine or a hole in "what did that cost" is your call, and it is the kind of thing
worth deciding before leaving a flow running.

### 11.3b — the reviewer is looking at the work · **on disk now, nothing to run**

The checkout from the last drive is still there and still detached at the right commit:

```
git -C C:\Users\huida\Documents\aw-stress worktree list
  .agentweave/reviews/critic     f10d198 (detached HEAD)
```

`f10d198` is `builder`'s commit for `task-23a0986e7fe9`, on branch `agentweave/builder`, with
`reachable_from_main: false` — so `master` does not contain it and only the reviewer's checkout
does. Open that directory and confirm builder's change is in it. This is the human half of 4b.2 and
the check that would have caught F10; the tasks table already marks it confirmed, so this is
seeing it once yourself.

### 11.2 — the handover is legible · **already happened, read the record**

The handover to judge is `entry-bdbff2b6d33b`: agent `critic`, `review_task_id`
`task-23a0986e7fe9`, delivered into conversation `conv-200965bb8a64`. `builder` finished the task
and did nothing else; nobody sent a message; the next firing queued `critic` a review turn carrying
the task.

Open the conversation list and judge whether that is **obvious** from it — that a handover
happened, and to whom.

**One thing that will look wrong and is not.** The flow's history shows two `failed` rows at
2026-08-24 22:45. Those are the Hub restart, not the flow: `run-144b3084c4d7` and
`run-324e1c9fe1e4` both end at `22:47:00.3`, the same second, because the process went down under
them. Judge the handover's legibility, not those rows.

## The checks that need a firing

### 11.5 — concurrent work is comprehensible · one firing

The queue is staged for it: two completed tasks, two different reviewers, two different authors.

| Task | Author | Commit | Reviewer the ladder picks |
|---|---|---|---|
| `task-23a0986e7fe9` Refuse an entry with no postings | `builder` | `f10d198` | `critic` |
| `task-3cd54c17faa6` Make Book.accounts() ordering stable | `critic` | `d8c4355` | `relay` |

Both resolve a real commit through `EvidenceFootprint`, so both review turns will get their
checkout rather than refusing. One firing staffs both at once — that is the two-line board to
judge: whether "task — agent" twice is comprehension or noise.

If you cleared F45's task first, this becomes a one-line board instead; the check still works, and
the last drive already produced the three-agent version (three `JobRun` rows, three conversations,
three turns) if you want the wider one.

### 11.4 — rung 3 reads as staffing, not breakage · one firing

Archive `critic` and `relay`, leaving only `builder`. `task-3cd54c17faa6`'s author is `critic`, so
with `critic` archived the ladder has nobody: `builder` is not excluded for that task, so to force
rung 3 use `task-23a0986e7fe9` instead, whose author **is** `builder` — the author is excluded,
rung 2's list comes back empty, and rung 3 surfaces.

The wording the last drive produced was:

> could not staff this step: no agent is free to take it. Every agent on the roster is either
> running a turn, already holding active work, or is the one that completed this task.

Judge whether that reads as *the flow needs somebody* or as *the flow failed*. It names all three
causes rather than only the one you can act on, which is the specific thing to have an opinion
about.

### 11.1 — a flow with one agent is a loop · two or three firings

The one check needing real setup, and the guide says lead with it. It is placed last here only
because the current state is a staged handover that cost 3.5M tokens to reach, and 11.1 requires
dismantling the conditions that make 11.2/11.5 readable.

Setup: archive `critic` and `relay`; give `builder` two independent pending tasks with no
dependency between them and no finished work waiting (or the flow reviews before it starts new
work, by design, and you will be judging the wrong thing). Candidates already in the project:
`task-3292072f63c3`, `task-bb86d53a94d5`, `task-948637265cb0`.

Then watch two or three firings and confirm everything reads as it did before the change: one task
claimed per firing, one run per firing, one current item, one name, consecutive firings collapsed
into a single conversation row.

Un-archive both agents afterwards; the handover state above survives archiving and returns.

## 11.3 — blocked, and the check has changed shape

**Do not run this one; it cannot pass, and finding F43 explains why.**

The flow instructs every agent to record what a reviewer will need via `submit_checkpoint_notes`.
All three agents complied. The notes are consumed only by checkpoint generation for the author's
own conversation, and generation fires only on a context-usage threshold or an operator button —
neither of which a flow firing reaches, because it is `session_mode: new` on one small task and
then that conversation never runs again. Measured: **3 of 3 notes unconsumed, 0 of 6 checkpoints
carrying a `loop_id`**, so `## Prior checkpoint` has never rendered in any briefing.

**The check inverts.** 11.3 was framed as *"if the implementer's checkpoint reads as notes-to-self,
task 6.5 did not work."* The note exists and is not notes-to-self — `note-e8cf4afcb4b1`, written by
`builder` about the exact task `critic` was queued to review:

> Task task-23a0986e7fe9 "Refuse an entry with no postings": The code implementation is already
> correct. Entry.balances() on line 20-21 of ledger/book.py already returns False for empty
> postings…

It names the task, the file, the line and the finding, for a reader who is not its author. **Task
6.5 worked.** What fails is delivery, and that is a defect rather than a judgement — so 11.3 is not
yours to close until F43 is decided.

F44 has to be decided with it: `latest_checkpoint_for_loop` selects by recency within the loop, not
by the author of the task under review. In a one-agent loop those are the same row; in this
three-agent flow they are not, and the live notes already show the collision — three notes, three
authors, one of which matches the queued review.

## What is unchanged and still true

- The trial Hub on 8010 serves `~/.agentweave/hub/profiles/beta/agentweave.db` and is running the
  fully fixed code (`/health` reports `{"status":"ok","runtime":"native"}`).
- Runners are cheap: `builder`/`critic` on `claude-haiku-4-5`, `relay` on `gpt-5.4-mini`. A firing
  here is not the 3.5M-token event the first drive was.
- `aw-sweep` (`proj-bacb623ca9ba`) was deleted 2026-08-25 at the operator's direction. Its
  directory `C:\Users\huida\Documents\aw-sweep` is untouched — the delete endpoint never touches
  the filesystem — and can go by hand if wanted.
