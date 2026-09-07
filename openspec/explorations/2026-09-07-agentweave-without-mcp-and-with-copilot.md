# Exploration — AgentWeave where MCP is blocked and Copilot is the house CLI

**Date:** 2026-09-07
**Status:** Seed for a spec loop. Not a proposal. R1 owns every decision below.
**Origin:** The operator's own constraint, stated 2026-09-07: *"Expanding AgentWeave for GitHub
Copilot and using with API because there is a MCP block in the company. GitHub Copilot is the go to
tool in the company and I would like to use AgentWeave here."*

This is not a market idea and not a finding from a drive. It is a deployment the operator wants and
cannot currently have. Two constraints, and they are independent:

1. **MCP servers are prohibited by company policy.** Ordinary local HTTP calls are not.
2. **GitHub Copilot CLI is the sanctioned agent**, not Claude and not Codex.

Either one alone blocks AgentWeave today. Both together are the real case.

---

## What was measured before this seed was written

A survey read the code on 2026-09-07 and reported the following. **Every claim here carries a
citation and was reported as measured. R1 must re-measure any claim it leans on** — this file is
evidence to check, not a conclusion to inherit. Two of the surveyed claims in the sibling seed were
already found wrong on spot-check (see "Instrument note" at the end), so the base rate is not zero.

### The HTTP plane is complete, and parity is already a shipped requirement

- All 26 MCP tools resolve to `/api/v1/agent-actions/*` through one helper,
  `mcp_server._hub_request` (`hub/hub/mcp_server.py:151-183`). No tool was found calling a route
  that does not exist, and no tool implements state locally.
- HTTP is reported as a **superset** — five routes with no MCP tool over them.
- **`openspec/specs/agent-capability-plane/spec.md:107-118` already requires this parity and names
  this exact deployment**: environments that forbid MCP servers while still allowing ordinary local
  API calls. So the company constraint is not a new requirement. It is a shipped requirement whose
  agent-facing half was never built.

That last point is the argument's centre of gravity, and it changes what the change *is*: not
"add an HTTP mode", but "make the adapter the spec already promises actually reachable by the agent
running inside it."

### Three gaps, none of which is a missing capability

- **(a) The run credential is never disclosed to the model.** It exists in the spawned process's
  environment (`hub/hub/api/v1/agent_trigger.py:1071`) and is mentioned in no context text, no
  charter, and no doc. An agent holding a working credential is not told it holds one.
- **(b) The non-MCP branch actively tells the agent to give up.** `access_path_notice`
  (`hub/hub/launchability.py:325-330`) informs an agent without MCP that it has *no* tool surface.
  A Copilot run would hold a valid credential and be instructed that it has nothing.
  `hub/hub/launchability.py:321` carries the deletion in a comment — *"No CLI equivalents are
  offered any more"* — so this branch was **emptied, not repointed**.
- **(c) The workspace permission boundary lives in `mcp_server._decide`**
  (`hub/hub/mcp_server.py:901-953`) and is unreachable without MCP. There is no server-side
  equivalent. **This is the one that is a genuine design question rather than a wiring job**, and
  R1 must not treat it as an oversight until it has established whether the boundary can be moved
  server-side without weakening it.

### Copilot is blocked four layers deep, before any of the above matters

| Layer | Site | Effect |
|---|---|---|
| Model | `RUNNER_CLIS = ("claude","codex")`, `hub/hub/db/models.py:300` | the Runner row cannot be created |
| UI | `RunnerCli`, `hub/ui/src/api/runners.ts:5` | no third option is offerable |
| Spawn | `SUPPORTED_RUNNERS`, `hub/hub/api/v1/agent_trigger.py:654` | 501 |
| Parsing | dispatch at `hub/hub/api/v1/agent_trigger.py:2043` | claude/else binary — Copilot output would be fed to `parse_codex_line` |

The only Copilot code that exists today is an auth probe
(`hub/hub/launchability.py:108-118`), a `doctor` warning
(`src/agentweave/diagnostics.py:873-948`), and a CLI-name table entry.

**`.claude/skills/copilot-test-setup/SKILL.md` describes a watchdog architecture deleted on
2026-08-03.** It is a fossil. Do not cite it as evidence of anything current, and consider whether
the change should delete or rewrite it — a skill that documents a deleted architecture is worse
than no skill.

### The historical precedent, and why it is not an argument against this

`src/agentweave/templates/collab_protocol.md:17-18,66-73` is a full command reference for a
non-MCP agent path — `agentweave msg send`, `task create`, `question ask`, `agent request`. **None
of those commands exist** in `src/agentweave/cli.py`.

The product has therefore already shipped a second, non-MCP capability adapter for agents once, and
deleted it. `openspec/specs/agent-capability-plane/spec.md:7-11` records the reconciliation: it was
removed because **the CLI was reduced to instance management**, not because a second adapter was
judged wrong. R1 should cite this deliberately — the precedent supports the change and a careless
reading of it would look like it opposes it.

Two related facts the survey turned up, both worth a decision rather than a silent fix:

- `docs/architecture/overview.md:18` claims **three** adapters (HTTP, MCP, agent CLI). Only two
  exist. The HTTP half of that sentence is true and elaborated nowhere.
- `get_template` / `get_skill_template` (`src/agentweave/templates/__init__.py:12,39`) have **zero
  call sites** in `src/` or `hub/`. The whole templates package is dead code, which contradicts
  CLAUDE.md's standing rule *"Templates via `get_template("name")` — never hardcode in `cli.py`"*.
  **Out of scope for this change** unless R1 finds it load-bearing; recorded here so it is not
  rediscovered as a surprise mid-round.

---

## Questions R1 must answer, not inherit

1. **Is this one change or two?** A `copilot` runner and a documented no-MCP HTTP path are
   independent: either ships without the other, and the HTTP path benefits every runner including
   the two already supported. The default assumption should be **two changes, HTTP first**, because
   the HTTP path is what makes a Copilot runner worth having and because gap (b) is a live defect
   for any agent whose harness lacks MCP — not just Copilot's. R1 may overturn this, but must say
   why in `design.md`.
2. **How does an agent that cannot use MCP learn what it can do?** Enumerate the options against
   the code before choosing: the rendered context text (`_render_hub_agent_context`,
   `hub/hub/api/v1/agents.py:1073`), a charter, a fetched discovery route, an injected skill file.
   `src/agentweave/tool_surface.py` describes a capability surface and — per the sibling seed — has
   **zero importers**; establish whether it is the right home or a corpse before reusing it.
3. **What replaces the permission boundary when MCP is absent?** Gap (c). Do not ship a change that
   silently drops a safety boundary for one adapter. If the boundary cannot be reproduced
   server-side, that is a finding and possibly a reason to scope the change smaller, not a reason
   to proceed quietly.
4. **How is the run credential disclosed without leaking it?** It is deliberately server-derived
   and never accepted from a request (`hub/hub/agent_auth.py`). Telling the model its own token is
   a real trade-off with a real precedent to check: this repository published an `aw_live_` key in
   a tracked file for weeks (`scripts/drive/aw.py:15`, fixed 2026-09-07). An agent that can print
   its credential into a transcript is a disclosure path.
5. **What does Copilot's CLI actually emit, and does anything parse it?** Layer 4 above is the one
   that cannot be answered from AgentWeave's code alone. **The window may not browse the open web**
   — so either the operator supplies a transcript, or the change is scoped to the three layers that
   *can* be settled and says plainly that parsing is unresolved. Do not invent a parser against an
   imagined format; that is precisely the failure mode this repository is worst at.
6. **Does a Copilot runner need permission-prompt support to be useful at all**, or is a
   read-mostly participant genuinely valuable first? `--permission-prompt-tool` (Claude) and
   `codex_appserver.decide_approval` (Codex) have no third analogue.

## What would make this change wrong

- Claiming parity that was measured on the tool list rather than on behaviour. The 26-tool mapping
  is a claim about *routes*, not about whether a route behaves identically when reached without a
  run credential. **Check `ask_user` first** — a blocking call is the one whose HTTP form is least
  likely to be equivalent.
- Adding `"copilot"` to four tuples, shipping green tests, and never having run Copilot. This
  repository's dominant failure mode is a fix that passes its tests and cannot fire in production.
- Treating `.claude/skills/copilot-test-setup/SKILL.md` as a specification.

## Instrument note

The survey that produced this seed also reported that `hub/hub/mcp_server.py:576` sent a malformed
path (`"\agents\request"` in a non-raw string). **Spot-checked and FALSE** — line 576 reads
`"/agents/request"` with forward slashes. One of two incidental findings from that survey was
wrong. Re-measure anything here before building an argument on it.
