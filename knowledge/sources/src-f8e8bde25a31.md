Decision on contradiction ctr-def93b2378f6, between two facts of the vault:
- fct-484ac6046b5b: "When check failures are judged not the task's, the Hub approves over them and opens a follow-up task to fix them."
- fct-a67f412137e5: "If a check fails on both the task's run and master's re-run, the Hub holds the approval for the operator, as implemented in hub/hub/requirement_gate.py."

The fact that stands is fct-a67f412137e5: "If a check fails on both the task's run and master's re-run, the Hub holds the approval for the operator, as implemented in hub/hub/requirement_gate.py.".

Note: Both are true in different cases. A failure that passes when rerun alone (flaky) is approved over and a follow-up task opened (what the measured re-run saw, F1054's decision); a failure that also fails on master holds the approval for the operator. fct-484ac6046b5b says 'not the task's' for both, which is too broad, so the precise fact stands.
