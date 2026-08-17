# The list of tools an agent reads matches the tools it has

## Why

**A Codex agent interviewed the operator for three rounds, settled the whole scope, and then could
not write the document.** Its closing words, from `run-93ec79be` on 2026-08-13:

> *"I did not implement anything because this workspace is explicitly in AgentWeave's exploration
> phase. I also couldn't save the specification because the required `submit_spec_document`
> capability was not exposed in this session."*

**The tool was exposed.** The Hub's MCP server advertises 16 tools and `submit_spec_document` is one
of them, verified by listing the live server's own registry. The agent had a working MCP connection
— it called `agentweave.ask_user` three times over that connection.

What it did not have was permission to believe the tool existed. The canonical turn context contains
a section headed `## Your tools` that enumerates the surface, and `submit_spec_document` is **not in
it**. The same context also contains the phase block saying *"Write the document with
`submit_spec_document`"*. The agent was handed a direct contradiction — an instruction to use a tool,
and an authoritative list saying that tool is not part of its surface — and resolved it in favour of
the list, which is the more specific claim and the one that reads as an inventory.

Diffing the served tools against the described ones:

```
served but NOT described: approve_tool_call, recall, submit_checkpoint_notes, submit_spec_document
described but NOT served: (none)
```

`approve_tool_call` is deliberately absent and the code says why. `submit_checkpoint_notes` is named
in the checkpoint prompt, where it is actually needed. **`submit_spec_document` and `recall` are
simply missing.**

The list is hand-maintained, and its own docstring records the last time this happened: *"the turn
preamble listed four tool names and nothing else, so agents guessed `message_type="text"` and were
rejected. Four job tools were never mentioned at all."* The fix then was to write the missing tools
in by hand. Nothing was added to stop it recurring, and it recurred — on the tool that
`2026-08-12-hub-owns-the-spec-document` was built around.

**This is why task 17.6 was never observed.** That change recorded *"No agent has been observed using
`submit_spec_document`"* and treated it as verification not yet done. It was not merely unobserved:
no agent could have used it, because every agent was told it did not have it. The deletion of the
`aw-spec-*` skills rests on that tool being delivered, and it was delivered everywhere except the
one place the agent reads.

## What Changes

- **`submit_spec_document` and `recall` are described** in the tool surface, with their arguments and
  constrained values, like every other tool.
- **A test asserts the surface and the server cannot disagree.** Every tool the MCP server advertises
  is either described in `## Your tools` or named in an explicit exclusion list carrying the reason
  it is delivered elsewhere. A tool added to the server without a decision about how the agent learns
  of it fails the suite.
- **The exclusions become explicit rather than accidental.** `approve_tool_call` is a harness
  endpoint, not a capability; `submit_checkpoint_notes` is named in the checkpoint prompt at the
  moment it applies. Both are recorded as decisions with reasons, so the next omission is a choice
  someone made rather than a line nobody wrote.

## Capabilities

### Modified Capabilities

- `agent-tool-surface`: the description an agent is given SHALL enumerate every tool it can use, and
  a tool the server serves SHALL be either described or explicitly excluded with a stated reason.

## Impact

**Behaviour** — two entries added to the generated context. An agent with a document open can now act
on the instruction it was already being given.

**Tests** — one new drift test. It is the substance of this change; the two entries would otherwise
be a fix that lasts until the next tool is added.

**No migration, no schema, no UI.**

## Non-Goals

- **Not generating the descriptions from the schema.** The value of this section is prose an agent
  can act on — when to ask, what a good `description` looks like, why `options` are offered — and
  FastMCP's generated schema carries none of it. The test enforces *coverage*, not *authorship*.
- **Not describing `approve_tool_call`.** It is registered for the harness to invoke; calling it
  accomplishes nothing and grants nothing.
- **Not moving `submit_checkpoint_notes` into the general list.** It is named where it applies, which
  is better than naming it on every turn.
- **Not re-verifying 17.6 here.** That needs a live run in which an agent actually calls the tool.
  This change makes it possible; it does not make it observed.
