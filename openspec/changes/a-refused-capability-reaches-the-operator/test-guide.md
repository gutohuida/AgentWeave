# Test guide — a refused capability reaches the operator

**R1, 2026-09-18.** Written with the change, per `feedback_specs_must_carry_test_guides`. Nothing here
has been run; this is what IMPL and the operator each owe.

## Agent-verifiable (run by IMPL and by the drive)

Under `py -3.11`. A pass on this list alone does **not** close F376 — task 5.2 does.

1. `pytest hub/tests/test_refused_capability.py -v` — the new file. Every case goes through the route
   with real agent attribution; a case without it proves nothing (design D9.2).
2. `pytest hub/tests/test_agent_actions_governed.py -v` — `archive_job` with the allowance off gets the
   new refusal and opens no permission request.
3. `pytest hub/tests/test_mcp_server.py hub/tests/test_agent_tool_surface_phase7.py -v` — the tool and
   contract descriptions still agree with each other.
4. `pytest hub/tests/ -q` — whole Hub suite, for the sweep interaction in task 4.2.
5. `ruff check hub/`, `black --check --target-version py311 hub/hub/ hub/tests/`, `mypy src/`.
6. **The drive** (`scripts/drive/`): a fresh project on the trial Hub `:8010` from source, one
   `claude-haiku-4-5-20251001` agent, one real turn calling `create_flow`. Asserts, from the database
   and the transcript: exactly one `questions` row for the project, zero `permission_requests` rows,
   and the new sentence in the agent's transcript.
7. The second half of the drive: enable `allow_agent_jobs` through `PATCH /queue/settings`, answer the
   question, and assert an inbound queue entry reaches the agent and its retry of `create_flow`
   succeeds.

## Human-only (the operator, on their own Hub, after a restart)

The things no agent can judge:

1. **(R4 — corrected.)** **Is the card legible on its own?** R1 wrote *"open it from the Questions
   destination alone"*. **There is no Questions destination to open** (design D1's R4 paragraph):
   the route is the project's **Overview** tab → the amber question card → *Answer*. Go that way,
   without reading the agent's transcript. Does it say what is blocked, what enabling it allows,
   and where to enable it, well enough to act on in the ten seconds before leaving the room? That
   is the situation it was built for.
2. **Is it one card and not a pile?** Over a real flow attempt with several agents, the inbox should
   carry one, not one per attempt — including when several agents are refused in the same instant
   (design D15).
3. **Does answering feel finished, or does it feel like homework?** The answer does not flip the
   setting (design D4) — the operator still visits Environment › Settings. If that reads as a broken
   promise rather than as an instruction, D4 is wrong and F379's change should take the one-click
   enable sooner rather than later. This is the judgement the loop cannot make for them.
4. **Does the agent pick the work back up?** After answering and enabling, the refused agent should
   resume without being messaged by hand. **(R4)** Expect that it may not, and that this is not a
   failure of the fix: what it is woken with is the question and the answer, and the question is
   forbidden from naming what it was trying to schedule. Record what it actually does — that
   observation is the finding, either way.
5. **(R4 — new; design D17.)** **Is being asked a second time right, or is it nagging?** Answer the
   first record, leave the setting off, and let an agent be refused again. The Hub opens one further
   record quoting your own answer back and saying it is the last. Read it as the person who just
   answered: does it feel like a useful catch of a mis-click, or like being asked the same thing
   twice? If the latter, D17's bound of two is wrong and should go back to one. Only the operator
   can judge this; the Hub cannot read whether an answer meant yes.

## Not covered by this change

- **F378** (`request_agent`'s empty template table). The helper is shaped so its repair can reuse it;
  no caller is added here.
- **F379** (the settings' invisibility) and **F377** (no operator surface creates a flow). Separate
  changes, no shared file.
- **(R4) `F386` and `F387`** — the Overview card's *"is waiting"* copy, its blindness to `declined`,
  and its one-at-a-time oldest-first ordering. Filed separately; `F386` is a **prerequisite** of
  this change (design **D18**), not something it repairs.
- **(R4)** What a woken agent is actually told. `_batch_delivery_text` delivers the question and the
  answer and nothing else, and task 1.2 forbids the question from naming the call's arguments — so
  the agent wakes with a decision and no record of what it wanted the decision for. Shipped code,
  outside this change; task 5.2 measures it rather than asserting a retry.
- One-click enable from the card. Deliberately deferred — design D4.
- The stale `agent-capability-plane` requirement about unasked questions (design D9.1). Flagged, not
  repaired.
