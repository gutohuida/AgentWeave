# Test guide — an estimate that misses turns says so

## Agent-verifiable

1. Tasks 1.1 and 1.2 fail before group 2 and pass after it.
2. On any project, `unpriced_turns` equals
   `select count(*) from turn_usage where project_id=? and api_equivalent_usd_micros is null`,
   read `mode=ro`.
3. `grep -rn "price" hub/hub/model_catalog.py` finds nothing. No price table was introduced.

## Human-only

1. On a project with some unpriced turns, open Settings, then Budgets. Does the figure's caveat
   read as *"this number is incomplete"* rather than as an error?
2. On a project where every turn is priced, the label is unchanged from today.
