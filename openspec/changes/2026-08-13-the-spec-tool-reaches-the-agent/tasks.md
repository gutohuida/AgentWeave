# Tasks — The specification tool reaches the agent it was written for

Found by running the flow rather than by reading it. Both defects were invisible to a suite of 1600
tests and obvious within four live turns.

## 1. The loop that found them

- [x] 1.1 Build a harness that drives the flow from outside the UI: create project, agent, document,
      turn; reply; answer questions; inspect the document. `testbed/scratch/spec_loop.py`, gitignored.
- [x] 1.2 Iteration 1 — agent announced OpenSpec, created an OpenSpec scaffold, then found the
      governing instruction and cleaned it up. Precedence worked, late.
- [x] 1.3 Iteration 2 — with the conversational floor deployed and verified present in the delivered
      context: announced OpenSpec, ran a questionnaire anyway, and **invented answers** when its
      questions went unanswered. Guidance delivered and losing, for the third time.
- [x] 1.4 Ruled out a delivery failure before blaming the model. A probe confirmed
      `model_instructions_file` reaches Codex: the model returned a passphrase that existed only in
      that file, under a read-only sandbox, without reading anything.
- [x] 1.5 Iteration 3, after the prompt notice — no OpenSpec; it said *"I also found an OpenSpec
      workflow installed on the machine; per this project's instructions, I have not used it"*; four
      open questions in prose; four directions with trade-offs; an ASCII flow sketch; and it stopped.
- [x] 1.6 Iteration 3, second turn — picked up the dormancy constraint the operator volunteered and
      made it the central question. **That is the thing a multiple-choice form cannot collect**, and
      the reason the interview change exists.
- [x] 1.7 Iteration 3, third turn — *"I could not submit the specification because the required
      `submit_spec_document` tool is not available in this session"*, with the tool present in the
      described surface. The agent was reading its real inventory.
- [x] 1.8 Listed the server's tools over stdio, spawned as the Hub spawns it: **15, without
      `submit_spec_document`**. In-process import: 16, with it.
- [x] 1.9 Found the cause: `if __name__ == "__main__": main()` at line 775, the tool defined at 791,
      and `mcp.run()` never returns.
- [x] 1.10 Found a harness defect of my own while reading the runs: `say` opened a new conversation
      each turn, so every turn was a cold start. It reads as continuity because a reply quotes the
      message it was just sent. Fixed by passing `conversation_id`, which the UI's composer always
      does.

## 2. Serve the tool (D1)

- [x] 2.1 Move the `__main__` guard to the end of `hub/hub/mcp_server.py`.
- [x] 2.2 Comment stating that nothing may follow it, and what it cost when something did.

## 3. Announce a specification turn with the turn

- [x] 3.1 `spec_turn_notice(phase)` in `launchability.py`, returning `None` when no document is open.
- [x] 3.2 Prepended to the prompt beside `access_path_notice`, never merged into the recorded
      message.
- [x] 3.3 Exploring gets: interview in this reply and stop; do not answer your own questions; write
      only with `submit_spec_document`. Later phases get the write rule only.
- [x] 3.4 Names no product.
- [x] 3.5 Phase lookup fails silently — a turn must not be refused because a phase could not be read.

## 4. Tests — agent-verifiable

- [x] 4.1 `test_mcp_server_stdio_surface.py` spawns the server and lists tools over the wire:
      `submit_spec_document` served; spawned surface equals imported surface; the tool's schema
      carries its arguments. Spawned from a directory that is not the package root.
- [x] 4.2 `test_spec_turn_notice.py` — nothing without a document; overrides other workflows; asks
      for the reply interview; forbids self-answering; names the write tool in every phase; does not
      ask a later phase to interview.
- [x] 4.3 `pytest hub/tests/ -q` and `pytest tests/ -q` run separately.
- [x] 4.4 `ruff check hub/ src/`, `black` on every file touched.
- [x] 4.5 `npx openspec validate --changes --strict` and `--specs --strict`.

## 5. Driven against the running Hub — the flow completed for the first time

`aw-loop-4`, agent `spec-4`, Codex `gpt-5.6-sol`, Spec Author charter, one conversation across two
turns.

**Turn 1** — prose interview: four directions with trade-offs, a flow sketch, four open questions,
grounded in the repository, and it stopped. No `ask_user`. No OpenSpec.

**Turn 2** — the operator's answers, including a constraint nobody asked about. The agent called
`agentweave.submit_spec_document`, which **completed**.

**The document**, `spec/changes/amber-griffin/spec.html`, 29,997 bytes:

- title minted `Personal Houseplant Watering Tracker`
- **nine** requirements, identifiers `FR-1` … `FR-9`
- `<meta name="aw-spec-status" content="exploring">`, kind `change-spec`, schema version 1
- the `aw-spec-payload` block present
- **zero** external resource references
- phase left at `exploring`, and the agent said proposal and approval are the operator's

**This closes `2026-08-12-hub-owns-the-spec-document` task 17.6**, recorded across three sessions as
"no agent has been observed using `submit_spec_document`". It was never a matter of observation.

## 6. Still open for the operator

- [ ] 6.1 **Read the document and judge it** — 17.2 asks whether the renderer's output is as readable
      as the skill-written ones, and this is the first agent-authored document to judge. Evidence:
      `.claude/autonomous/2026-08-15-judgement-evidence.md`, `the-spec-tool-reaches-the-agent` 6.1 —
      the operator's own read, not the loop's.
- [x] 6.2 Run the same flow with a **Claude** agent. Everything here was Codex. Done by `speccer`
      (Claude, Spec Author charter) in the `aw-loop10` drive, `run-d3b6f7c5`/`run-462fb78e` —
      write-up: judgement-evidence.md 6.2.
- [x] 6.3 Take a document through `propose` and `approve` from the UI now that one exists with real
      content. Done in the same `aw-loop10` drive, all the way to a real merge — via the API the UI
      calls, not the rendered browser screen; see judgement-evidence.md 6.3 for that caveat.
- [ ] 6.4 **The ten-minute turn timeout.** An interview of several rounds plus operator thinking time
      exceeds it; one loop run died that way. Not touched by this change and worth its own look,
      because the exploration flow is the feature that produces long turns.
- [x] 6.5 Decide whether a turn triggered with no `conversation_id` should open a new conversation
      every time. The UI always sends one, so this is not reached from the app — but jobs and peer
      messages do not, and 1.10 shows how convincingly a cold start imitates continuity.
      **Decided by the operator, 2026-08-16: yes, a new conversation each time — current behaviour
      stands.** Predictable and stateless: a job or a peer message gets a clean thread rather than
      landing in the middle of one the operator was having, with its context and its cost. Rejected
      reusing the agent's most recent open conversation for exactly that reason. The known cost is
      thread sprawl, and it is why runtime overrides need `inherit_runtime_overrides` to carry the
      operator's chosen posture across the hop — that mechanism exists precisely because this
      decision went this way.
