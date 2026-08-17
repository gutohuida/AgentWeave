# Tasks — The list of tools an agent reads matches the tools it has

Two entries and a test. The test is the change; the entries are what it would have caught.

**Reopened 2026-08-15.** Sections 2–4 were implemented but never ticked, so the board read
6 done / 17 open against a change that was largely built. Checking the code rather than the boxes
turned up the thing the change was written to prevent, still present: `submit_spec_document` was
described with a signature it has never had. The name matched, so the test passed. See 2.1 and 3.5.

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

- [x] 2.1 Add `submit_spec_document` with its arguments, taking constrained values from the server's
      own `Literal` aliases as the neighbouring entries do, so it cannot drift from the schema.
      **This was half-done, and the missing half was the whole point.** The entry existed, but read
      `submit_spec_document(path, document)` — a signature the tool has never had. The real one is
      `(path, title, kind, summary, problem, design, lifecycle, scope, requirements,
      acceptance_criteria, tasks, algorithms, evidence, open_questions)`, with no `document`
      parameter at all, so an agent following its own tool list would have been rejected for an
      unexpected keyword argument on top of two missing required ones — `title` and `kind`. It now
      describes the real arguments, and `kind` takes its values from the `SpecKind` alias as this
      task asked. Found by comparing every described signature against `mcp.list_tools()`:
      **18 of 19 entries were correct and this was the only one that drifted** — the same tool,
      again.
- [x] 2.2 Add `recall`. `agents.py` — "`recall(observation_id)` — read back one observation by its
      identifier."
- [x] 2.3 Say what the tool is *for*, not only its signature. Every entry carries prose on what the
      tool accomplishes and when to reach for it; `ask_user` and `record_evidence` are the longest
      because their cost is the least obvious.

## 3. Make the agreement enforced (the actual change)

- [x] 3.1 A test that lists the served tools and the described ones and asserts every served tool is
      described or explicitly excluded. `test_every_served_tool_is_described_or_deliberately_excluded`.
- [x] 3.2 The exclusion list carries a reason per entry, in the code, so an omission is a decision
      someone recorded rather than a line nobody wrote. `UNDESCRIBED_TOOLS` at `agents.py:844`,
      carrying `approve_tool_call` and `submit_checkpoint_notes` with a sentence each.
- [x] 3.3 Fail on the reverse too — a described tool the server does not serve. An agent told it has
      a tool it does not have wastes a turn discovering that.
      `test_no_tool_is_described_that_the_server_does_not_serve`.
- [x] 3.4 Do not generate the descriptions from the schema. The test enforces coverage, not
      authorship (proposal Non-Goals). Every entry is hand-written; nothing reads a schema to
      produce prose. Only the constrained *values* come from the `Literal` aliases, which is the
      part that must not drift.
- [x] 3.5 **Check the arguments, not just the name.** Added after 2.1 found the surface naming the
      right tool with the wrong signature. The name-only check passed for two days across a
      description that would have failed every call, because the name was never the part that
      drifted. Two tests now compare each described argument list against the tool's real schema.

## 4. Tests — agent-verifiable

- [x] 4.1 Served ⊆ described ∪ excluded (3.1).
- [x] 4.2 Described ⊆ served (3.3).
- [x] 4.3 Every exclusion carries a non-empty reason (3.2). Also asserts the reason is at least
      eight words, since a one-word reason silences the check without recording a decision.
- [x] 4.4 `submit_spec_document` specifically appears in the rendered context of a spec turn,
      alongside the phase-block instruction that names it — the two must agree, which is the failure
      that occurred. `test_spec_procedure_precedence.py::test_the_instruction_and_the_tool_list_agree_in_one_rendered_context`
      renders the real context and asserts both halves of it.
- [x] 4.5 `pytest hub/tests/ -q` and `pytest tests/ -q` run separately. Measured **both sides** of
      the change. Before: hub 631 + 686 + 712 passed, 11 skipped across three file chunks; CLI 360
      passed, 3 skipped. After: hub 631 + 686 + **714** passed, 11 skipped; CLI 360 passed, 3
      skipped — the +2 being 4.8 and 4.9. This also converts handoff 0047's outstanding
      *"the full suite has not been run since `55bfadb`"* into a measurement.
      **Re-run 2026-08-15 21:0x-21:11, post-session** (this measurement was recorded at 12:20/f31e90e,
      before the whole day's worth of q3/q4/q6 fixes to `hub/hub/` — b10b607, eda02cf, 60f0b3f,
      309fef4, fcedde6, 1b9233a and others — none of which had had the full suite re-run against
      them, only their own individual regression tests). Full clean run at HEAD (`3dd9b41`), same
      3-chunk split (alphabetical thirds of the then-current 147 files):
      chunk 1 656 passed 1 skipped (248.4s), chunk 2 671 passed 9 skipped (299.7s), chunk 3 719
      passed 1 skipped (219.8s) — **2046 passed, 11 skipped total**; CLI `pytest tests/ -q` 360
      passed, 3 skipped (17.9s), unchanged. No failures, no regressions from any of the day's fixes.
      Chunk boundaries differ from the original run (more test files exist now, including today's
      new regression tests) so the raw pass counts are not directly comparable line-for-line, but
      zero red is the fact that matters.
- [x] 4.6 `ruff check hub/ src/` — all checks passed. `black --check` on both files touched —
      unchanged.
- [x] 4.7 `npx openspec validate --changes --strict` — 14 passed. `--specs --strict` — 30 passed.
- [x] 4.8 **No described argument is one the tool does not take** (3.5). Mutation-checked: restoring
      `(path, document)` fails it with `described arguments that the tool does not accept:
      {'submit_spec_document': ['document']}`, while **all five pre-existing tests still pass** —
      which is the measurement of what the name-only check could not see.
- [x] 4.9 **Every required argument is described** (3.5). Mutation-checked: the same restoration
      fails it with `required arguments the surface never mentions: {'submit_spec_document':
      ['kind', 'title']}`.

## 5. Verification — human-only

- [x] 5.1 **Run the exploration flow to the end and watch an agent call `submit_spec_document`.**
      This closes `2026-08-12-hub-owns-the-spec-document` task 17.6, which has never been observed —
      and now the reason it was never observed is known. The interview in `run-93ec79be` reached a
      settled scope and stopped at the write; the same run with this fix should write.
      **Accepted by the operator, 2026-08-16**, on the live evidence recorded in `.claude/autonomous/2026-08-15-judgement-evidence.md` — run id, tool-call order and cost for each.
- [ ] 5.2 Read the resulting document. 17.2 asks whether the renderer's output is as readable as the
      old skill-written ones, and there has still never been an agent-authored document to judge.
      **WAIVED for archiving, 2026-08-17 (autonomous N6).**
      `.claude/autonomous/2026-08-15-judgement-evidence.md` § this change, 5.2: an agent-authored
      document now exists and has been read (this is the same document `the-spec-tool-reaches-the-
      agent` 6.1 asks about — waived there for the same reason). The final readability comparison
      against the old skill-written ones is the operator's own call.
- [x] 5.3 Confirm an agent with no document open is not told about `submit_spec_document` in a way
      that invites it to invent one.
      **Verified by code reading, 2026-08-17 (autonomous N6), not by a fresh live drive** — the
      judgement-evidence file called this "still open," but the concern is answerable structurally:
      `_tool_surface_lines()` (`hub/hub/api/v1/agents.py:857`) is included unconditionally for every
      registered agent, so the `submit_spec_document` description is always present — but its own
      wording states "write the specification document the operator has open," and the MCP tool's
      docstring (`hub/hub/mcp_server.py:818`) is explicit: "The document must already exist: the
      operator starts an exploration, and you fill it in." Both descriptions name a document that
      must already exist rather than presenting the tool as a way to create one from nothing, in any
      turn, document open or not. This is a text-invariant, not a behavioural one — ticked on that
      basis.

## 6. User test guide

1. **Start an exploration and let the agent interview you.** Answer its questions promptly — the
   turn budget is ten minutes and an interview of three rounds can exhaust it while it waits.
2. **When it has enough, it should write the document** rather than summarising the scope in chat
   and stopping. That stop is the defect this fixes.
3. **Open the document in the Spec view.** It should hold what you agreed, with minted requirement
   identifiers.
4. **If it summarises and stops again**, read its last message: if it says the capability is not
   available, the surface and the server have drifted again and the test in section 3 did not hold.
