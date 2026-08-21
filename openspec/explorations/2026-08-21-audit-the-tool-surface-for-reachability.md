# Exploration — Audit the agent tool surface for reachability (2026-08-21)

**Status:** PARKED. Operator: *"There should be some that are not reachable anymore... that are
legacy. Maybe we can check that latter."* Not scheduled. This file exists so that "later" starts
from a method instead of another accident.

## Why it is open

`request_agent` was found to be **unreachable** — advertised to every agent, and guaranteed to fail
with a 400 because the table its template comes from has had no writer since the watchdog was
deleted (see `2026-08-21-request-agent-cannot-succeed.md`). It was found while sweeping
`new_conversation` call sites for an unrelated change. Nothing was looking for it.

The operator's expectation is that it is not alone. That is plausible on the evidence: the product
deleted a whole subsystem (`watchdog.py`, `messaging.py`, `runner.py`, `transport/local.py`,
`transport/git.py`, the role subsystem) and went from 56 CLI commands to 5. A tool whose backing
path went with one of those would look exactly like `request_agent` does.

## The inventory

23 `@mcp.tool()` decorators today, 22 agent-callable (`approve_tool_call` is a harness endpoint):

```
messaging     send_message
tasks         create_task  list_tasks  get_task  update_task
operator      ask_user  get_answer  approve_tool_call*
checkpoints   submit_checkpoint_notes  recall
agents        request_agent                          ← confirmed unreachable
jobs/loops    create_job  create_loop  archive_job  toggle_job  run_job
spec          create_spec_document  submit_spec_document  rename_spec_document
              read_spec_document
evidence      record_evidence  list_evidence  decide_evidence
                                                     * harness, not a capability
```

**`CLAUDE.md:252` says "21 @mcp.tool(), 20 agent-callable".** Measured: 23 and 22. The count has
drifted by two, which is itself a small finding — that line is the only place the surface is
inventoried, and it is stale.

## What "unreachable" means, precisely

`request_agent` sets the shape. A tool is unreachable when a **precondition it cannot influence** is
unsatisfiable in the current product:

1. it reads state from a table or file with no remaining writer (`ProjectSession`);
2. it requires configuration through a surface that no longer exists (template pre-approval);
3. it calls into a module that was deleted;
4. it is gated on a setting that cannot be turned on from anywhere.

Not unreachable, and out of scope: a tool that fails because the operator has not set something
they *could* set, or that is merely unused. Dormant is fine. Impossible is not.

## A method, since the last one was luck

Cheap signals first, in rough order of cost:

1. **Follow every tool to its endpoint**, then to the state it reads. Any read of a table whose
   writers are gone is the `request_agent` pattern exactly. `ProjectSession` is the known-dead one;
   check whether any other table has readers but no writer.
2. **Grep each handler for imports of deleted modules** — `watchdog`, `messaging`, `runner`,
   `transport.local`, `transport.git`, and the role subsystem.
3. **Check the failure text of each guard clause.** `request_agent`'s tell was that its 400 reads
   like a permissions problem an operator could fix, when no surface exists to fix it. A refusal
   naming a thing the product cannot produce is the signature.
4. **Cross-check against the tests.** A tool with only unit tests that construct their own fixture
   state can be green forever while being unreachable in a real project — `request_agent` presumably
   is. A tool exercised end to end through a real project is reachable by construction.
5. **Ask the running Hub.** Call each tool against the trial instance with a plausible argument and
   read the refusals. Crude, but it would have caught this one in a minute, and it tests the thing
   an agent actually experiences.

Step 4 is the one that predicts where the rot is. Step 5 is the one that finds it fastest.

## Open questions

1. Which of the 22 are exercised end to end anywhere, versus only in unit tests with hand-built
   state?
2. Is `ProjectSession` the only readers-but-no-writers table, or are there others? That query
   generalises beyond the tool surface.
3. What is the disposition for an unreachable tool — delete, or repair? It differs per tool and is
   the operator's call. `request_agent` in particular overlaps `operator-agent-creation`, which
   already works.
4. Should the count in `CLAUDE.md:252` be replaced by something that cannot drift — a test that
   asserts the number, or a generated list? It has been wrong by two for some time and nothing
   noticed.
