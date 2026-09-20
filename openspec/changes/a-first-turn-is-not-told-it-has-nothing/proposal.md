## Why

The first turn of **every agent ever created** opens with a sentence that is false:
*"[AgentWeave] Tool access: no MCP tools this turn"* — delivered while the Hub's MCP server is
injected and its tools are in the model's tool list. The notice is composed from `described_path`
(`hub/hub/api/v1/agent_trigger.py`, the `notices = [access_path_notice(described_path)]` line), which
takes the no-grounds branch because `harness_has_honoured_mcp` can only be true once a *previous*
run of the same agent has reported an adapter online. The injection beside it keys on `access_path`
instead, and is unconditional for a `claude` runner. So the two disagree exactly once per agent, and
the run is told it is empty while holding the tools.

**This was decided on 2026-09-09 and never built** (`spec-queue/DECISIONS.md`,
`#### DAY-2 / F302 — the notice stops asserting, and does not start trusting`). That verdict made
itself conditional: it said the fix became cheap only once the workspace approver learned to
recognise the run's own Hub URL, *"so the HTTP form the notice steers a fresh agent toward is one
the agent can actually use."* **That precondition is now satisfied and was measured on 2026-09-20**
at `d7f2694`, by calling `_decide` directly with `AW_WORKSPACE_DIR` and `HUB_URL` set as the Hub
sets them: the notice's own instructed shape
(`curl -H "Authorization: Bearer $AW_RUN_TOKEN" $HUB_URL/api/v1/agent-actions/tasks`) is **allowed**
in both the Bash and PowerShell renderings, while a foreign address is still refused as a network
address and `../outside.txt` still as outside the workspace (`_HUB_REFERENCE_RE` and `_judge_word`
in `hub/hub/mcp_server.py`).

The cost is measured, not theoretical. `openspec/explorations/2026-09-14-the-first-turn-has-its-tools.md`
records all four LoopEngine agents opening on the false sentence, and the Architect keeping to
`curl` and payload files for **ten runs after the notice healed** — it learned its payload shape from
two 422s, and 9 of its 21 `agent_wrote_outside_workspace` warnings came from writing payload files to
`/tmp` and `%TEMP%`. It used the MCP `ask_user` in the same session, so the tools were demonstrably
there throughout. **The notice heals on turn two; the agent does not.**

## What Changes

- **The no-MCP branch of `access_path_notice` (`hub/hub/launchability.py`) stops asserting the
  absence of a tool surface.** It keeps everything the plane requirement asks for — that the plane is
  reachable over HTTP, the base address, the credential's variable name, how the credential is
  presented, and where the operations are described — and drops only the clause claiming the run has
  no MCP tools this turn.
- **The `agent-capability-plane` requirement gains the symmetric prohibition it never had.** Today it
  forbids asserting a tool surface is *present* without grounds; it says nothing about asserting one
  is *absent*, which is why the false sentence was spec-compliant. The delta makes both directions
  unassertable without grounds.
- **The same requirement's false mechanism is corrected, as a separate and already-mandated edit.**
  Its prose states *"the `cli` path's `acceptEdits` has no approver to overrule a harness that
  **statically refuses** an interpolated credential (F301)."* `DECISIONS.md` 1c measured that false —
  with the approval gate removed, that exact command executes, and a bare literal `curl` with no
  variable is denied identically — and 1d requires the correction to ride *"in the same delta that
  carries the notice change"*. The requirement's **conclusion** (unreachable on `cli`) holds; only
  the stated reason is wrong.
- **The two tests that pin the denial are restaged** to assert what the notice must now contain
  rather than what it must say: `hub/tests/test_agent_trigger.py` asserts `"no MCP tools this turn"`
  in a built prompt in two places.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-capability-plane`: **`A run is told the access path it actually has`** gains a normative
  clause and a scenario forbidding assertion of a tool surface's *absence* without grounds, matching
  the existing prohibition on asserting its presence. **`A run whose harness cannot use MCP is told
  how to reach the plane`** has its F301 mechanism sentence corrected; its normative SHALL is
  unchanged.

## Impact

- `hub/hub/launchability.py` — `access_path_notice`, the no-MCP branch's returned string only. The
  comment above that branch already explains the credential-naming prohibition and must survive.
- `hub/tests/test_agent_trigger.py` — two assertions on the denial text.
- `hub/tests/test_agent_facing_text.py`, `hub/tests/test_launchability.py`,
  `hub/tests/test_tool_surface_matches_server.py` — all reference `access_path_notice`; each must be
  read, and any that pins the removed clause restaged.
- `openspec/specs/agent-capability-plane/spec.md` — two requirements, via the delta.
- **No migration. No route. Nothing under `hub/ui/`, so no `make ui` and nothing reaches the
  operator's live app on reload.**

## Non-Goals

Stated explicitly, because three of these are the ways this change could quietly become a different
one:

- **The MCP branch is not granted on trust.** A fresh agent still reads the HTTP form. The decision
  is explicit that granting the MCP rendering without grounds is *"the same disease pointed the other
  way"*, and would be wrong on precisely the harness the notice exists for. `described_access_path`'s
  grounds logic is untouched.
- **Containment does not move.** The requirement's own scenario — *"A truer description does not
  silently widen permission"* — governs this change directly. `resolve_access_path`, `mcp_command`
  and the permission posture are untouched; only the text changes.
- **The two branches are not merged into one always-true notice.** A single text saying "use the
  MCP tools if they are in your tool list, otherwise HTTP" was considered and is **rejected here**:
  it is a larger behavioural change to the grounds mechanism than the verdict authorised, and the
  verdict deliberately chose "describe without claiming" over "describe both". Recorded so a later
  round does not mistake it for an oversight.
- **`harness_has_honoured_mcp`'s permanent-positive latch is not fixed.** It can never return to
  false once true (`hub/hub/launchability.py`, a `.limit(1)` existence check with no recency, whose
  only writer only ever sets the column). That is **F340**, open, and belongs to its own change.
- **`hub_client` is not given a UI control**, and the legacy runner registries are not cleaned up
  (**F393**).
