# The first turn has its tools

**2026-09-14, day window, I-1 brief 5 of 11.** This is an improvement brief, not a proposal: there
is no change directory and no tasks. Source: `spec-queue/observations/2026-09-14-LoopEngine.md`,
`## Improvements` item 5 and `### Architect` item 8. The figures come from that file, from the
`:8000` database read `mode=ro`, and from the agents' transcripts.

**Half of this is already decided.** The denial at the heart of it is **F302** (B, open). The
operator decided it on 2026-09-09: `DECISIONS.md` `#### DAY-2 / F302 — the notice stops asserting,
and does not start trusting`. It has not been built. O-3 filed item 5 as an improvement without
finding F302. This brief corrects that, and F302 gets a dated note. The part that is new is what
the verdict assumed about turn two.

## What we saw

All four of LoopEngine's agents opened their first turn with *"[AgentWeave] Tool access: no MCP
tools this turn — but the AgentWeave capability plane is reachable over HTTP"*:
- the Architect at 20:39 (`run-2445bbbe1d6d`);
- `dev_2` at 16:35;
- `dev` at 16:45;
- `tester` at 18:50.

In every case the server had been injected and was working. The Architect's adapter reported online
five seconds after that line. This is by design: `described_access_path` describes MCP only once
some earlier run of the same agent has an `mcp_adapter_online_at` (`hub/hub/launchability.py:232-260`,
`:263-295`). Its docstring prices the cost at *"convenience for one turn"* (`:285-289`).

**The notice healed on turn two. The agent did not.** The Architect's first turn opened the spec
conversation, which resumed one harness session for ten runs, 20:39 to 23:44. Its session carries
the denial once, at 20:39:53. Each of the nine later runs carries *"the `agentweave` MCP tools are
available"*: I re-checked this `mode=ro` for this brief, one prompt per run. Even so, the Architect
kept to the path its first turn had set:
- It had no tool schema, so it learned the payload shape from two 422s. Then it read
  `hub/hub/spec_payload.py` in a sibling checkout.
- It submitted every draft for the rest of the session with `curl` and a payload file.
- In the same session it used the MCP `ask_user`, so the tools were there throughout.
- Writing the payload files to `/tmp` and `%TEMP%` accounts for 9 of its 21
  `agent_wrote_outside_workspace` warnings.

The model believed its own earlier history over the later notice.

## What would change

There are two parts.

**First, build F302's verdict as decided.** The no-grounds branch stops saying *"no MCP tools this
turn"*. It still describes the HTTP form in full, and it still does not claim the tools.

**Second, the new part.** A session whose first run was described without MCP, and whose later run
now has grounds, gets one line on that later run. The line says the tools are confirmed present, so
the earlier description is out of date.

Neither part grants anything on trust. The verdict rejected that, and the second part only corrects
a statement the Hub itself knows it made.

## Why it matters

A fresh agent's first turn is usually its most consequential one: a spec interview, or a first task
claim. The F302 verdict called the defect *"bounded — one turn per agent, healing on the second"*.
On LoopEngine it was not bounded. In a conversation that resumes its session, one false first line
set how the Architect worked for an evening, through a surface with no schema whose mistakes come
back as 422s. Dropping the sentence would have prevented it. The follow-up line covers a session
already started under the HTTP form, which is every session opened before this ships and every
session opened on a harness whose grounds arrive late.

## Rough cost — a code-read estimate

- **Files:**
  - `hub/hub/launchability.py`: `access_path_notice` (`:365-401`) is a one-sentence change.
  - The follow-up line needs the prompt builder in `hub/hub/api/v1/agent_trigger.py` (the call is
    at `:999-1005`) to know how the session's earlier runs were described. That is either a query
    on `runs` by `session_id` and `mcp_adapter_online_at`, or a stored field.
- **Capability:** `openspec/specs/agent-capability-plane`, requirement *"A run is told the access
  path it actually has"*. F302's part fits its existing scenario *"No grounds means no assertion"*,
  and the follow-up line adds a scenario.
- **Migration:** none, unless the description is stored rather than derived.
- **API shape and UI:** none.
- **Not in `mcp_server.py`,** so F354 does not stop it. F302's half could be built on a build day.

## Risks and open questions

- **It borders an OPEN operator question.** The access path on a harness that blocks MCP (F299,
  F301, F339, F340) is undecided in `DECISIONS.md`. F302's verdict was made separately and does not
  depend on it. The follow-up line does not either, because it adds no permission and changes no
  spawn. The scenario *"A truer description does not silently widen permission"* holds.
- **F340 weakens the grounds the line would rest on.** They are positive-only and permanent. A line
  saying "confirmed present" on a harness that has since started refusing the server would repeat
  F340's error. Reading `init.mcp_servers` per run, as F340 proposes, would be better grounds. It
  can only reach the second run, which is exactly where this line goes.
- **Unmeasured:**
  - whether the other three agents' first sessions also stayed on HTTP after turn one, since O-2
    read only the Architect's this closely;
  - whether dropping the denial alone would have been enough. A model with no tool schema in its
    prompt, told only the HTTP form, may still choose `curl`.

## The decision, in one line

Queue F302's decided wording as a fix on the next build day, and approve a spec loop for *a session
is told when the tools it was not told of are present*. The loop can run with F302's build or after
F340 is decided.
