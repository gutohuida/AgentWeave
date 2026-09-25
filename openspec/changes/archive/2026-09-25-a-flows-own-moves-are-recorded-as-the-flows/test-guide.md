# Test guide — a flow's own moves are recorded as the flow's

## Agent-verifiable

1. **The flow's staging is no longer the operator's request.** Tasks 1.1 and 1.2 fail before, pass after.
2. **The operator's own dispatch is unchanged.** Control 1.3. A divergence restaff's late review
   stays the operator's request (control 1.3d; operator decision 2026-09-24).
3. **Nothing can record a job move without a job, or as an agent.** Task 1.4.
4. **No future scheduler staging forgets the job.** Task 1.5's source scan.
5. **The route and the drawer agree, in the route's order.** Tasks 1.6 and 1.7.
6. **No guard moved.** `test_task_transitions.py`'s `ACTOR_KINDS == {"run","operator"}` assertion and the whole transition suite pass unchanged.

## Human-only

1. Open a flow-worked task's History on a trial Hub: the claim and review-staging lines read
   "Flow <name> moved …"; a move you made by hand still reads "You moved …".
2. Old rows on `:8000` (after the operator's own restart) still read "You moved" — by design, history
   is not rewritten. **Accepted by the operator 2026-09-24** (design, *Operator review*); confirm
   only that it is so.
3. Press Run on a loop by hand: the claim it stages reads "Loop <name> moved …", not "You moved"
   (operator decision 2026-09-24).
