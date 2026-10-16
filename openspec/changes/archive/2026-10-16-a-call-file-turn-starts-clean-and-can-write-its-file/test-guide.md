# Test guide — A call-mode turn starts with an empty calls directory and is told to name each file afresh

## Agent-verifiable

1. Run `py -3.11 -m pytest hub/tests/test_calls_dir_starts_clean.py -q`. Every test passes. Before
   §2 is implemented, 1.1, 1.2, 1.3, 1.4, 1.6 and 1.8 fail (1.2 only on the keyword). The
   parametrized link tests of 1.5, in
   `test_agent_trigger.py`, fail too, because the `empty` keyword does not exist yet. 1.7 passes
   before and after, and must restore the real workspace resolver as 1.6 does, or it proves
   nothing (R3). Run 1.3 and
   the held-file variant of 1.4 on Windows. On Linux, `_link_dir` makes a symlink, so the junction
   case cannot fail there.
2. Run the regression set named in task 2.4. It passes unchanged. In particular,
   `test_copilot_context_split.py` needs no snapshot regeneration, because its fixture is the mcp
   rendering.
3. Read the trial database read-only after the drive in task 3.1. Run:

   ```sql
   SELECT sequence, kind FROM agent_outputs
   WHERE run_id = :second_run
     AND ((content || COALESCE(payload, '')) LIKE '%Path already exists%'
          OR (content || COALESCE(payload, '')) LIKE '%No match found%')
   ```

   It returns no rows.
4. In the same database, `turn_usage.total_tokens` for the second run is within about 20% of the first run's
   total, not about 150k.
5. Run `npx openspec validate a-call-file-turn-starts-clean-and-can-write-its-file --strict`. It
   passes.

## Human-only

1. Watch the live Copilot shim turns in the dashboard transcript. The agent writes `1.json`, or a new
   name, without a failed write and without reading an old file.
2. Judge whether the D2 sentence reads naturally in the turn-start notice, and whether the model
   follows it when it makes several calls.
