## Context

`access_path_notice` (`hub/hub/launchability.py`) renders two mutually exclusive texts. The MCP
branch names the tools; the no-MCP branch opens with *"no MCP tools this turn"* and then describes
the HTTP contract. Which branch runs is decided by `described_access_path`, whose only observable
ground is `harness_has_honoured_mcp` — an existence check for a *previous* run of the same agent
carrying `Run.mcp_adapter_online_at`. A brand-new agent has no previous run, so its first turn always
takes the no-MCP branch, while `resolve_access_path` has unconditionally injected the server.

The verdict is already made (`DECISIONS.md`, `#### DAY-2 / F302`): drop the denial, and do not grant
the MCP rendering on trust in the other direction. This design covers only *how*, and records what
must not drift.

**A note for the verification rounds:** an annotation pass over legacy code was running in this tree
on 2026-09-20 and is shifting line numbers in `hub/hub/launchability.py`. Cite symbols, not lines.

## Goals / Non-Goals

**Goals:**

- The first turn of a new agent contains no false statement about its tool surface.
- The requirement forbids the denial as clearly as it already forbids the unfounded claim.
- The F301 mechanism sentence in the requirement's prose stops being false.

**Non-Goals:**

- Granting MCP on trust. Explicitly rejected by the verdict as *"the same disease pointed the other
  way"*.
- Any change to containment, posture, `resolve_access_path`, or `mcp_command`.
- Fixing `harness_has_honoured_mcp`'s inability to return to false (**F340**).
- Merging the two branches into a single always-true text (see D2).

## Decisions

### D1 — Delete the clause; keep the rest of the sentence intact

The no-MCP branch's opening becomes a statement about the plane rather than about the tool list. The
minimum edit is to drop *"no MCP tools this turn — but"* and keep *"the AgentWeave capability plane
is reachable over HTTP, and this run is already authenticated for it"*, with the remainder of the
text unchanged.

*Why:* every other clause in that branch is required by `A run whose harness cannot use MCP is told
how to reach the plane` — base address, credential variable, presentation, where operations are
described. Only the opening clause is the unfounded claim. A larger rewrite would put required
content at risk for no gain.

*Rejected:* rewording the whole branch, which re-opens four spec scenarios for a one-clause defect.

### D2 — Two branches stay two branches

*Rejected alternative, recorded because it is the obvious idea and was actually proposed in session
on 2026-09-20:* one text saying "use the `agentweave` tools if they are in your tool list, otherwise
HTTP", which is true on every path and every turn and would make the grounds mechanism irrelevant to
the notice entirely.

*Why rejected here:* it is a behavioural change to what the system asserts, not a removal of a false
claim, and the 2026-09-09 verdict chose "describe without claiming" over "describe both" after
considering the trust direction. Changing that is a new decision for the operator, not a detail of
this one. **It remains a reasonable future change** and is named here so a later round recognises it
as declined rather than missed.

### D3 — "Unless it has grounds" is written into the requirement even though grounds never exist today

The new clause forbids asserting absence *unless the system has grounds*. Today it never does: the
one place the truth appears is the harness's first `system`/`init` line carrying `mcp_servers`, and
`parse_claude_line` has no branch for it (**F340**).

*Why word it conditionally rather than as a flat prohibition:* grounds for absence are obtainable,
and F340 is the change that would obtain them. A flat "never say absent" would have to be amended
the day that ships; the conditional form is already correct for both worlds, and it keeps the
requirement symmetric with the presence clause directly beside it, which is the point.

### D4 — The F301 prose correction rides in this delta, and only the prose moves

`DECISIONS.md` 1d requires it *"in the same delta that carries the notice change"*, and that delta is
this one. The requirement's normative SHALL is untouched; its **conclusion** (unreachable by the
agent's own tools on `cli`) stands, and only the stated reason changes.

*Rejected:* a separate change for the correction, which would leave a known-false mechanism in the
corpus for another cycle to satisfy a tidiness preference; and re-opening the conclusion, which the
measurement supports rather than undermines.

### D5 — Tests assert the absence of a claim, not the presence of a wording

The two assertions in `hub/tests/test_agent_trigger.py` currently read
`assert "no MCP tools this turn" in prompt`. They become assertions that the built prompt carries
the required plane content **and makes no availability claim**.

*Why this shape:* an assertion that pins exact prose re-breaks on every future wording change
without protecting the behaviour. What the requirement cares about is that a claim is absent, and
that is directly testable.

*Trap to avoid:* a test asserting only `"no MCP tools this turn" not in prompt` would pass against
an empty prompt. Each restaged assertion must pair the negative with the positive content the
requirement demands.

## Risks / Trade-offs

- **A test elsewhere pins the exact string and is missed** → three further files reference
  `access_path_notice` (`test_agent_facing_text.py`, `test_launchability.py`,
  `test_tool_surface_matches_server.py`). Each is read and named in tasks, not grepped once.
- **The removed clause was load-bearing for a reader somewhere** (docs, a skill template, a charter)
  → grep the clause across the whole repo, not just `hub/`, before deleting it.
- **A fresh agent now reads an HTTP instruction with no stated reason** → acceptable, and better
  than the false reason: the text still positively describes the reachable path, and where the tools
  *are* present the model can see them in its own tool list. The measured failure this change exists
  to stop (an agent adopting `curl` permanently because its first turn said it had nothing) is
  caused by the denial, not by the HTTP description.
- **Stored turn text changes shape between old and new runs** → no migration; the notice is composed
  per turn and old prompts are historical records that stay as they were.

## Migration Plan

None. No schema, no data, no route. The change takes effect on the next turn composed after deploy.
Rollback is reverting the string.

## Open Questions

None for the operator. The one decision this change could have carried — trust versus description —
was answered on 2026-09-09, and D2 records the alternative it declines.
