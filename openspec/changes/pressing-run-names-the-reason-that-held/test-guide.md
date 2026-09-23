# Test guide — pressing Run names the reason that held

## Agent-verifiable

Each of these can be checked with no person watching.

1. **The false roster clause is gone for a documentless loop.** Tasks 1.1, 1.2 and 1.6 fail before
   the fix and pass after. The assertion that matters is the **absence** of
   `no other agent is free`. All three sentences sound plausible, which is how F127's survived.
2. **A flow's two sentences did not move.** Controls 1.4 and 1.5 pass before and after, byte for byte.
3. **An in-flight press is not answered with an old stall.** Task 1.7 fails before and passes after.
   The earlier row's `tick_count` and requester are unchanged.
4. **A continuing stall still answers from its own row.** Control 1.8 passes before and after, and
   1.9 pins the gate that skips the busy re-ask for a counted stall.
5. **One derivation.** `grep -n "_loop_has_open_task" hub/hub/api/v1/jobs.py` finds nothing after
   the fix. The route reads `refusal.held`.
6. **Nothing else moved.** Full `hub/tests/` count recorded in 2.5, with only 1.6's two assertions
   changed on purpose.
7. **The real route and the real MCP tool**, on a trial Hub (3.1, 3.2). Record the detail strings
   verbatim.

## Human-only

The app does not show this answer today (F411: the Run button has no error handler). Until F411 is
fixed, a person pressing **Run** on the Jobs page sees nothing either way. That is not this change's
regression.

1. If F411 was folded in (Open Question 1): on the Jobs page, press **Run** on a documentless loop
   whose agent is mid-turn, while another agent is idle. You should read that the loop's work goes
   only to its own agent, and nothing telling you to free someone.
2. Otherwise: nothing to check by eye. Read the two 409 details recorded in task 3.1 and ask of each,
   *"if I did what this sentence implies, would the loop start?"* For the scope clause the honest
   answer is *"no, wait for the turn"*, and the sentence should leave you there.
