# The specification tool reaches the agent it was written for

## Why

**`submit_spec_document` had never once been callable by an agent, and three sessions recorded that
as verification pending rather than as a defect.** Found by driving the exploration flow end to end
on 2026-08-13, after two other causes had been fixed and cleared out of the way.

The tool is defined at line 791 of `hub/hub/mcp_server.py`. The `if __name__ == "__main__": main()`
guard was at line 775. `main()` calls `mcp.run()`, which does not return. **So when the server is
spawned as a script — which is exactly and only how the Hub spawns it — execution stops at line 776
and the tool is never registered.**

Every test imports the module. An import sets `__name__` to the module name, the guard is false, the
whole file executes, and all sixteen tools register. So `test_mcp_tool_schemas.py` asserted the
tool's schema, its refusal to accept a phase, and its refusal to accept an identity — four passing
tests about a tool no agent could see. Listing the server's registry in-process showed sixteen tools;
listing it over stdio, spawned the way the Hub spawns it, showed **fifteen**.

What it cost, from the run that found it: an agent interviewed the operator across three turns,
established the entire scope, and finished with *"I could not submit the specification because the
required `submit_spec_document` tool is not available in this session — only AgentWeave messaging,
task, and checkpoint tools are exposed."* That enumeration was correct. It was reading its real
inventory.

This was the third of three independent causes stacked on the same symptom, each hiding the next:
the document was created after the trigger (fixed), the tool was missing from the described surface
(fixed), and the tool was not served at all. Each fix revealed the next, and each time the
verification that would have caught it was recorded as "not yet observed".

**A second defect, found the same way.** The turn context's precedence statement, conversational
floor and tool list were all verified present in the delivered file, and the agent announced *"I'll
use the OpenSpec exploration workflow"* anyway, ran the questionnaire the floor forbade, and invented
answers to its own unanswered questions. Standing context is read once, before the operator's
message exists; a skill description is matched against that message. The countermeasure has to arrive
in the same channel as the thing it competes with.

## What Changes

- **The `__main__` guard moves to the end of the file**, with a comment stating why nothing may
  follow it. This is the whole fix for the tool.
- **A test spawns the server as a subprocess and lists its tools over stdio**, and asserts the
  spawned surface equals the imported one. No test could previously see this class of mistake,
  because every test imported.
- **A specification turn announces itself in the turn prompt**, beside the operator's message: this
  overrides any other specification workflow, interview in this reply, do not answer your own
  questions, write only with `submit_spec_document`. The canonical context keeps everything it has;
  this is a second delivery in the channel that competes with a skill trigger.

## Capabilities

### Modified Capabilities

- `agent-tool-surface`: the tool surface an agent receives SHALL be verified as the surface the
  server actually serves when spawned, not as the surface it registers when imported.
- `spec-document-authority`: the phase directive SHALL travel with the turn as well as in the
  canonical context.

## Impact

**Behaviour** — agents can write specification documents. Verified: an agent called the tool and
produced a 30 KB document with nine minted identifiers, acceptance criteria, tasks and non-goals.

**Tests** — one new file spawning the real process. It is the only test in the suite that does not
trust an import.

**No migration, no schema, no UI.**

## Non-Goals

- **Not restructuring the module.** The tool ordering is fine; the guard's position was the defect.
- **Not moving tool definitions into the Hub package.** The server is deliberately stdlib+fastmcp
  only, spawned from an arbitrary working directory, and that constraint is unchanged.
- **Not claiming the prompt notice guarantees obedience.** It is evidence, not a guarantee — but
  unlike the previous two attempts it was observed working on the run that followed it.
