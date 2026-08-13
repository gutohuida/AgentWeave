# Tasks — The list of tools an agent reads matches the tools it has

Two entries and a test. The test is the change; the entries are what it would have caught.

## 1. Establish the defect

- [x] 1.1 Confirm the tool is served. Listing the canonical server's own registry: **16 tools,
      `submit_spec_document` among them.** The same for `src/agentweave/mcp/server.py`, which
      re-exports it.
- [x] 1.2 Confirm the agent had a working MCP connection, so this is not a transport failure.
      `run-93ec79be` called `agentweave.ask_user` three times over it.
- [x] 1.3 Confirm the tool is absent from the described surface. `## Your tools` in the delivered
      context file lists twelve entries; `submit_spec_document` is not one.
- [x] 1.4 Confirm the same context also *instructs* its use — the phase block's *"Write the document
      with `submit_spec_document`"*. The contradiction is the defect; either alone would be milder.
- [x] 1.5 Diff served against described:
      `served but NOT described: approve_tool_call, recall, submit_checkpoint_notes,
      submit_spec_document`; `described but NOT served: (none)`.
- [x] 1.6 Classify each omission rather than adding all four.
      `approve_tool_call` — deliberate, reason already in the code. `submit_checkpoint_notes` —
      named in the checkpoint prompt (`checkpoint_trigger.py:65`, `agents.py:1863`), where it
      applies. `recall` and `submit_spec_document` — **unexplained omissions.**

## 2. Describe the missing tools

- [ ] 2.1 Add `submit_spec_document` with its arguments, taking constrained values from the server's
      own `Literal` aliases as the neighbouring entries do, so it cannot drift from the schema.
- [ ] 2.2 Add `recall`.
- [ ] 2.3 Say what the tool is *for*, not only its signature. The section's value over a generated
      schema is prose an agent can act on.

## 3. Make the agreement enforced (the actual change)

- [ ] 3.1 A test that lists the served tools and the described ones and asserts every served tool is
      described or explicitly excluded.
- [ ] 3.2 The exclusion list carries a reason per entry, in the code, so an omission is a decision
      someone recorded rather than a line nobody wrote.
- [ ] 3.3 Fail on the reverse too — a described tool the server does not serve. An agent told it has
      a tool it does not have wastes a turn discovering that.
- [ ] 3.4 Do not generate the descriptions from the schema. The test enforces coverage, not
      authorship (proposal Non-Goals).

## 4. Tests — agent-verifiable

- [ ] 4.1 Served ⊆ described ∪ excluded (3.1).
- [ ] 4.2 Described ⊆ served (3.3).
- [ ] 4.3 Every exclusion carries a non-empty reason (3.2).
- [ ] 4.4 `submit_spec_document` specifically appears in the rendered context of a spec turn,
      alongside the phase-block instruction that names it — the two must agree, which is the failure
      that occurred.
- [ ] 4.5 `pytest hub/tests/ -q` and `pytest tests/ -q` run separately.
- [ ] 4.6 `ruff check hub/ src/`, `black` on every file touched.
- [ ] 4.7 `npx openspec validate --changes --strict` and `--specs --strict`.

## 5. Verification — human-only

- [ ] 5.1 **Run the exploration flow to the end and watch an agent call `submit_spec_document`.**
      This closes `2026-08-12-hub-owns-the-spec-document` task 17.6, which has never been observed —
      and now the reason it was never observed is known. The interview in `run-93ec79be` reached a
      settled scope and stopped at the write; the same run with this fix should write.
- [ ] 5.2 Read the resulting document. 17.2 asks whether the renderer's output is as readable as the
      old skill-written ones, and there has still never been an agent-authored document to judge.
- [ ] 5.3 Confirm an agent with no document open is not told about `submit_spec_document` in a way
      that invites it to invent one.

## 6. User test guide

1. **Start an exploration and let the agent interview you.** Answer its questions promptly — the
   turn budget is ten minutes and an interview of three rounds can exhaust it while it waits.
2. **When it has enough, it should write the document** rather than summarising the scope in chat
   and stopping. That stop is the defect this fixes.
3. **Open the document in the Spec view.** It should hold what you agreed, with minted requirement
   identifiers.
4. **If it summarises and stops again**, read its last message: if it says the capability is not
   available, the surface and the server have drifted again and the test in section 3 did not hold.
