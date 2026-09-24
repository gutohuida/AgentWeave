# Test guide — a loop that is gone lets go of its document

## Agent-verifiable

1. **A successor gets the unfinished work** (F53). Tasks 1.1 and 1.2 fail today and pass after; the
   approved task stays with its old loop.
2. **A live loop's claim is untouched.** Controls 1.3 and 1.8.
3. **New tasks never go to a dead loop.** Tasks 1.4 and 1.5; 1.4 seeds both insertion orders so a
   row-order pick cannot pass by luck.
4. **A document on a plain job is refused, not dropped** (F157). Task 1.6 fails today (201).
5. **Every real way to make a flow still works.** Control 1.7.
6. **The old loop's history survives the move** (D6). Task 1.9: a `loop_tasks_adopted` event is on
   both loops' records, and a rolled-back claim leaves none.
7. **An archived holder is named, not briefed** (D7). Task 1.10.
8. **An ended loop that is not archived still holds its document.** Control 1.11.
9. **Live** (3.1): F53's own three-call reproduction ends with a populated queue.

## Human-only

1. On the Loops screen, archive a flow that has unfinished tasks, create a new flow on the same
   document, and confirm its queue shows them. Open the archived flow's detail and confirm that its
   history names the new flow and the moved tasks.
