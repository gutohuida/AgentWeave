# Test guide — a flow stages its review in the dispatch

## Agent-verifiable

1. **A refused flow review leaves the task as it was** (F327, both legs). Tasks 1.1 and 1.2 fail
   before and pass after; they assert the status, the holder and the transition count.
2. **The operator can send another reviewer** (F327's 409 row). Task 1.4.
3. **The flow names the refusal and does not re-staff it.** Task 1.3; 1.6 shows the task returns to
   the pool once the refused input is gone.
4. **A waiting review keeps the task out of the pool and its reviewer busy.** Tasks 1.5 and 1.7.
5. **The restaff is staffed at its dispatch, and a refused one leaves the silent reviewer named.**
   Tasks 1.8 and 1.9; 1.10 is the control that a plain request is still refused by the holder check.
6. **F70's recovery still works without the firing's write.** Task 1.11.
7. **The reviewer is told the status it will find.** Task 1.12.
8. **Two reading-found shapes** (an operator's queued review on a loop and on a flow). Tasks 1.13,
   1.14.
9. **Nothing else moved by accident.** D8's list, produced by R2 from a prototype, each moved on
   purpose.

## Human-only

1. On a trial Hub, a flow with a completed task whose evidence names a commit; delete that commit's
   branch and run `git gc --prune=now` so the commit is gone. Let the flow fire. The task card
   still reads **Completed**, with its author; the flow card names the reviewer and says delivering
   the review was refused, quoting the missing commit. Send a different reviewer from the task: it
   is not refused as "already under review".
2. With a reviewer busy on another turn, let the flow staff it for a review. The card says the
   review is in flight, naming that reviewer, while the task still reads **Completed**. When the
   reviewer's turn ends, the review starts and the task moves to **Under Review**.
