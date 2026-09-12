# User test guide — a refused review leaves nothing behind

Task 9.1. What an operator does, what they should see, and what it looks like when it goes wrong.

**What the suite and the drive already prove (agent-verifiable).** An agent can check all of these
from the database and the API, and tasks §1 and §5 do:
- After a refused review, the task's status, holder and history equal what they were before the
  request. That holds for a pruned commit, an obstructed review checkout, a project that is not a
  repository, a reviewer that became the author while its request waited, and a deferral.
- The refusal's own sentence is still recorded: as the `409` answer, as the waiting input's reason,
  and in the give-up notice.
- A second reviewer is no longer refused as *"already under review"* after the first was refused,
  where you dispatched the first. A review a flow staffed still is (F327, below).
- When the system gives up on refused input, the input queued behind it starts in the same pass,
  unless that input is refused too. Then it waits, as input behind any refused request does.

**What only you can judge (human-only)** is whether the board and the dispatch control tell you the
truth where you actually look. Checks 1 and 3 below are those. Check 2 is a quick confirmation of
what the drive proved.

## Before you start

- The trial Hub on port **8010**, started **from `hub/`** so the source package is what runs. The
  command is in `CLAUDE.md`, *The trial Hub*. Do not use `agentweave --port 8010`.
- **A project whose working directory is a git repository.**
- **Two agents with a `claude` runner on Haiku**, for example `critic` and `critic2`. Neither has
  worked on the task below.
- **One completed task with evidence naming a commit that you then delete.**
  1. On a side branch, make a commit and note its sha.
  2. Record operator evidence for the task naming that sha. `POST
     /api/v1/projects/<id>/project/spec/evidence` with `locator` set to the sha does it. It needs a
     requirement identifier from an approved document. `completed_task()` in
     `scripts/drive/t_d1_0912_f319_reach.py` is the working recipe.
  3. Move the task `in_progress` and then `completed` yourself.
  4. Delete the branch, then run `git reflog expire --expire=now --all && git gc --prune=now`.
  5. `git cat-file -e <sha>` must now fail.

## 1. Ask for a review that cannot happen (human-only)

From the task's card, dispatch a review naming `critic`.

**You should see** a refusal that says the commit *is not present in this repository, so there is
nothing to check out for review*. On the Tasks board the task stays in **Completed**, with the holder
it had before. It does not move to **Under Review**, and it does not show `@critic`.

**Judge it.** Did the reason reach you where you pressed the button? The `409` has always been sent.
Nobody has yet recorded what the UI shows for it (F319, *"What the operator sees"*). Is the board's
silence now the truth? That is task 6.1.

**It has gone wrong if** the card moves to **Under Review · Idle** with `@critic` on it. That is
F319, the defect this change removes. Check which commit the Hub was started from.

## 2. A second reviewer is not blocked by the first refusal

Dispatch a review of the same task naming `critic2`.

**You should see** the same commit refusal as in check 1.

**It has gone wrong if** it says the task *is already under review by 'critic'*. That means the
first refusal left `critic` holding the task.

## 3. A review refused after it was accepted (human-only)

This is leg A. It needs an agent to become the task's author while your request waits.
1. Create a fresh completed task whose evidence names a commit that exists.
2. Send `critic` a message asking it to run `sleep 60` and then record evidence for that task.
3. **While it is still running**, dispatch a review of that task naming `critic`.

**You should see** the dispatch answered as queued: nothing is refusable yet. When `critic`'s turn
ends, the queued review is refused, because `critic` is now the task's author. The task stays in
**Completed**, and does not show `@critic`. The waiting input's reason reads *"… recorded evidence
for this task …"*. After the third attempt, you are told the system gave up on it. Continuing the
conversation twice gets you there quickly.

**Judge it.** You asked for a review and were told *queued*. The only news that it will not happen
is that reason, and then the give-up notice. Is that enough? This change does not alter it. Task
6.2 asks you to decide.

**It has gone wrong if** the task reads `@critic` after `critic`'s turn ends.

## 4. Input behind a given-up request is delivered

This continues from check 3, before the third attempt.
1. Send `critic` a plain one-line message in a **new** conversation. It queues behind the refused
   review.
2. Continue the review's conversation until the system gives up on it. That is the third attempt.

**You should see** `critic` start a turn on your one-line message straight away, in the pass that
gave up. You did nothing else.

**It has gone wrong if** the message sits queued with no reason given and `critic` idle. That is
F320.

## What this does not show

- **Flows (F327, open).** A flow records its reviewer when it selects the review, before any turn
  is sent. If that turn is then refused, the task stays **Under Review** with the flow's reviewer on
  it, which is F319's end state. Three things tell you:
  1. The job's run fails at once, with the refusal's words.
  2. The flow then calls the task *in flight* for as long as the refused input is still queued.
  3. It names *"a review nobody is doing"* only after the input is given up.

  Meanwhile, sending another reviewer is refused with *"let the review in flight finish"*. This
  change does not alter any of that unless the operator's answer to the question at the top of
  `proposal.md` brings it in (task 6.3). R2 measured it at unit level (`design.md` D7).
- **The review checkout directory.** A refusal raised *after* the reviewer's checkout was prepared
  can leave `.agentweave/reviews/<agent>` behind. That is F326, which is open and not fixed here.
- **A faster answer for check 3.** The request is still answered *queued* at first. Nothing about
  when you are told has changed.
