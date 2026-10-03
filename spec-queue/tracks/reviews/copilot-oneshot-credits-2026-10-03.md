# Adversarial Opus review — `a-copilot-one-shot-records-its-credits`, 2026-10-03 night (iter 24)

An Opus subagent reviewed the change at `0b784b1`, after R1, R2 and R3. It had read-only access to
the repo and measured under `py -3.11` in a temporary directory. It was asked to attack four
things:

- R3's ceiling helper;
- R3's claim that a run is relabelled `failed`;
- Open question 1 (F486);
- the agreement between the spec delta, the tasks and the design.

**Result:** seven problems confirmed and eight concerns refuted. All seven fixes are applied in
the change; `design.md`'s round log lists them. `openspec validate --strict` still passes.

## Confirmed, and what was done

| # | Finding | Fix applied |
|---|---|---|
| 1 | R3's ceiling was a row's limit, not a sum's. `func.sum(TurnUsage.ai_nano_aiu)` (`usage_accounting.py:304`) raises `OperationalError: integer overflow` once a row near `2**63 - 1` meets any other row. `accounting_snapshot`, `conversation_usage` and `PATCH budget` have no handler, so the result is a lasting 500. Re-measured this round with `sqlite3`. | D2's ceiling is now `2**53 - 1` for both figures. The residual is 1025 rows at the ceiling (MEASURED). |
| 2 | Five "passes today" labels were wrong. Test 5, and test 6's 400-digit, ledger-`2**63` and bound-row cases, fail today. | Relabelled in `design.md` and in tasks 1.1/1.3. |
| 3 | The spec delta covered a non-zero exit's checkpoint, which D4 deliberately leaves out. | The requirement is scoped to a process that exited successfully, with a scenario for non-zero, timeout and spawn failure, and a D4 table row. |
| 4 | The run-side behaviour changed with no spec delta. | A MODIFIED delta for the Copilot-turn credits requirement, with a scenario. |
| 5 | No test pinned D1's rule that a later unusable checkpoint makes the figure unknown. | A test 3 case, `(10, 1)` then `(-1, 2)` → `(None, 2.0)`, plus a scenario. |
| 6 | D3 cited migration `0106`'s backfill, which covers claude/codex only, as the sibling's rule. | Cited the sibling's D1 via `_accounting_from_dimensions` instead. The conclusion is unchanged. |
| 7 | Wrong file references. | `checkpoints.py:107`/`:208`, `hub/hub/db/models.py`, `hub/hub/api/v1/agent_trigger.py`. |

## Refuted (the change was right)

- **The ceiling comparison never raises** for any value `json.loads` produces: every JSON type,
  `true`/`false`, `null`, the infinities, `NaN`, `1e400`, and integers of 400 and 4300 digits.
- **Premium requests up to the float maximum are storable.** SQLAlchemy's `Float` coerces them on
  insert.
- **R3's relabel-to-failed trace holds line by line** (`agent_trigger.py:3954`, `:3985`, `:4018`,
  `:4093`, `:2348`), and nothing guards against it today.
- **Open question 1 is framed correctly.** The operator decides only whether the sibling's next
  round gains a task, a test and a delta line. Their D7 answer does not affect it.
- **D1 holds:** there is no resume flag.
- **D4 matches `_interpret`.**
- **There is no import cycle.**
- **The SHALL is on the first line, and `--strict` passes.**
