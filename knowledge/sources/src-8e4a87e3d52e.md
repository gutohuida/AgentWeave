Decision on contradiction ctr-845c224ea45c, between two facts of the vault:
- fct-484ac6046b5b: "When check failures are judged not the task's, the Hub approves over them and opens a follow-up task to fix them."
- fct-fe9f4e045fda: "When a check fails on a task and also fails on master, the Hub neither passes nor blames the task but holds the approval for the operator (the PREEXISTING_CHECKS hold)."

The fact that stands is fct-fe9f4e045fda: "When a check fails on a task and also fails on master, the Hub neither passes nor blames the task but holds the approval for the operator (the PREEXISTING_CHECKS hold).".

Note: Both are true in different cases. A failure that passes when rerun alone (flaky) is approved over and a follow-up task opened (what the measured re-run saw, F1054's decision); a failure that also fails on master holds the approval for the operator. fct-484ac6046b5b says 'not the task's' for both, which is too broad, so the precise fact stands.
