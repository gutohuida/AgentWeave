# Exploration — an overseer: metrics and governance over any AI harness

**Date:** 2026-09-07
**Status:** Seed for a spec loop. Not a proposal. R1 owns every decision below.
**Origin:** The operator, 2026-09-07 — *"a system to connect to the harness that stores every single
metric that we can… kinda of an overseer and we generate metrics and governance on any AI harness.
We register everything AIs are doing."*

Third subject of the day, after the Copilot/no-MCP loop and the continuity kit. It shares their
central criterion — *work with any harness, including one where MCP is banned* — and it is the
first of the three with a large body of existing code, inside and outside this repository, that it
could accidentally duplicate.

---

## Part 1 — the fact that should reshape the idea before R1 writes a line

**The collection problem is largely solved, by the vendors, already.** A session that could browse
the open web established the following on 2026-09-07, with documentation citations. Re-read them if
you can do so offline; label anything you cannot confirm as unverified rather than asserting it.

| Harness | What it already emits |
|---|---|
| **Claude Code** | Full OTLP — **metrics, events/logs, and traces** (traces behind `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`). Enabled by `CLAUDE_CODE_ENABLE_TELEMETRY=1`, standard `OTEL_EXPORTER_OTLP_*` configuration, per-signal exporters and intervals. Documented metric and event lists, both substantial. Administrators can set org-wide endpoints, headers and redaction through managed policy settings; mTLS and a token-refresh headers helper are supported. |
| **GitHub Copilot CLI** | **Enterprise-managed OpenTelemetry export, announced 8 July 2026** — admins can direct telemetry to an approved OTLP collector. Plus enterprise audit logs filterable by `actor:Copilot`, 180-day retention. Audit logs do **not** carry client-side prompts or reasoning steps. Exact env vars and event schema **NOT CONFIRMED**. |
| **OpenAI Codex CLI** | OTel for traces, logs and metrics, configured in `~/.codex/config.toml` under `[otel]`, disabled by default. Signals differ by entrypoint: interactive gets metrics+logs+traces, `codex exec` gets logs+traces only, and **`codex mcp-server` emits nothing at all** — a documented gap. |

Three consequences R1 must absorb rather than argue around:

1. **Writing a collector is writing a commodity.** OTLP has many mature sinks already. A proposal
   whose centre of gravity is ingestion and storage is proposing to rebuild the least differentiated
   part of the stack.
2. **The interesting content is redacted by default, deliberately.** In Claude Code, prompt text,
   response text, tool parameters, tool input/output and raw API bodies are each off unless a
   specific flag is set (`OTEL_LOG_USER_PROMPTS`, `OTEL_LOG_ASSISTANT_RESPONSES`,
   `OTEL_LOG_TOOL_DETAILS`, `OTEL_LOG_TOOL_CONTENT`, `OTEL_LOG_RAW_API_BODIES`), with a 60 KB
   truncation default. So *"register everything AIs are doing"* is not a build decision. **It is an
   organisational policy decision that someone must be persuaded to make**, and the persuading is
   the hard part.
3. **The cross-harness schema does not exist yet.** OpenTelemetry's GenAI semantic conventions are
   at **Development** status — moved into their own repository in June 2026 with no releases or tags
   yet, last versioned snapshot v1.42.0. The attribute groups are real (`gen_ai.agent.*`,
   `gen_ai.tool.*`, `gen_ai.tool.call.*`, `gen_ai.request.*`, `gen_ai.usage.*`,
   `gen_ai.provider.name`) and should be adopted rather than reinvented — but **pinning to them is
   pinning to a moving target**, and every harness above currently emits its own custom shape.

**So the gap is not collection. It is normalisation and governance.** That is the honest reframing,
and R1 should either adopt it or refute it explicitly.

### The capture-completeness question, which decides how honest the product can be

Claude Code's hook system fires **33 events** — session lifecycle, every tool call, permission
decisions, compaction, subagents, config and file changes — with `session_id`, `transcript_path`,
`cwd`, `permission_mode`, `tool_name`, `tool_input`, `tool_use_id` and more on the payloads. It is
the richest local capture point available on any harness surveyed.

**And it is still incomplete.** Documented gaps include session-state reloads, the moment state
*should* be written during compaction, model fallback/retry decision points, retry attempts after
an initial denial, and silently-enforced deny rules that never prompt. Extended thinking is redacted.

This matters more than it looks. A product called an *overseer* that says it registers **everything**
will be believed, and a gap nobody documented becomes a false assurance. Any proposal here must
state what it cannot see, per harness, as a first-class output — the same discipline this repository
applies to a finding without a reproduction.

---

## Part 2 — the honest assessment, including what is wrong with the idea

### The framing risk, and it is the one to settle first

**Is this a new product, or is it AgentWeave's Hub with the orchestration removed?** The
2026-09-06 exploration's own market table judged that extracting the multi-agent HITL machinery
*"is unbundling the product, not a spinoff"* — and an overseer that records agent activity and
governs it is uncomfortably close to that description.

There is a real distinction available, and R1 must test it rather than accept it:

> **AgentWeave governs agents it spawns. An overseer governs agents it does not control.**

If that holds, they are different products with different centres: one owns execution and derives
observability from it; the other has no execution and must derive everything from what a foreign
harness volunteers. If it does not hold — if the honest answer is that the overseer is the Hub's
recording layer with a different label — that is a **finding, not a failure**, and it turns the
proposal into a boundary question about AgentWeave rather than a new repository.

**AgentWeave already does a meaningful part of this**, which is why R2 is pointed at it
specifically. Known before this seed was written: `record_agent_output`
(`hub/hub/output_recording.py:80-93`) and `record_context_usage` (`:155-239`), an `EventLog` row
type `context_warning`, and — most relevant — **two compatibility self-report HTTP endpoints
explicitly built for agents the Hub did not spawn**: `POST /api/v1/agents/{name}/output`
(`hub/hub/api/v1/agents.py:2247-2266`) and `POST /api/v1/agents/{name}/context-usage`
(`:2269-2284`), both authenticated by a project key. That is already a partial overseer ingestion
path, and the context percentage it records is the Hub's own arithmetic
(`output_recording.py:127-152`) over a token count parsed from a runner's stdout, not a number the
runner reports. Inventory the rest properly; do not take this paragraph as the inventory.

### The strongest argument for it, which is not a market-research argument

The operator's own company bans MCP servers while permitting ordinary local API calls. **An MCP ban
is a governance posture** — implemented bluntly, because nothing finer-grained was available to the
people who made the rule. An organisation that bans a whole integration channel wholesale is an
organisation that would plausibly rather have visibility and policy than a ban.

That is first-hand evidence from inside a real enterprise, and it is worth more than anything a web
search returns. It also lands well against the table above: **Copilot CLI's enterprise OTel export
is a channel that is not MCP**, so an overseer can reach the operator's company through a door that
is already open, which is exactly the constraint the day's first spec loop is about.

### The hardest question, which R1 and R2 will both be tempted to defer

**Recording is passive. Governing is active.** On a harness you do not control there are only three
places to stand, and they are three different products:

| Lever | What it means | Cost |
|---|---|---|
| **Gateway** | Proxy the model API and refuse there | Strongest enforcement; requires sitting in the critical path of every request, and a proxy that is down stops all work |
| **Tool boundary** | A hook or permission-prompt integration that can refuse a specific action | Real enforcement, per-harness, only where the harness offers the seam (Claude Code hooks: yes; Copilot CLI: **NOT CONFIRMED**) |
| **After the fact** | Record, report, alert, and rely on people | Cheapest and works everywhere OTel does; enforces nothing |

A proposal that says "metrics **and** governance" without choosing is proposing all three. R3's
assigned job is to make the design commit and say which.

### The principle this idea can trip over, from this repository's own history

The unasked-question backstop was retired on 2026-08-20 at the operator's request, migration `0082`
dropped its table, and CLAUDE.md forbids reintroducing it — because *guessing whether trailing prose
is a question is a judgement the product should not make on the operator's behalf.* An overseer that
**scores** or **judges** agent behaviour runs directly into that principle. Reporting what happened
is not the same as ruling on whether it was acceptable, and the line between them is where this
product would earn or lose trust.

### And the objection that applies to all three of today's subjects

The build pipeline is oversupplied, not undersupplied: three unarchived AgentWeave changes with zero
tasks implemented, six open severity-A findings, and now two new sibling repositories from today
alone. This is the third proposal written today and the second new project. **Each new project costs
operator decision time, which is the scarce resource.** R1 should say plainly what this one displaces.

---

## Part 3 — questions R1 must answer, not inherit

1. **New product or unbundled Hub?** Settle it against the inventory, first, before any design.
2. **Given that every major harness already emits OTel, what is the thing being built?** If the
   answer is "a collector", the proposal is probably wrong. Candidate answers to weigh: a
   normalisation layer across harness-specific attribute shapes; a policy engine over a stream
   somebody else collects; a governance record with an evidence contract; a completeness reporter
   that states per harness what it cannot see.
3. **Which enforcement lever, and why not the other two?**
4. **What is the data policy, stated as a requirement rather than a setting?** Content is redacted
   by default on every harness surveyed. Turning it on means recording source code, prompts and
   possibly secrets — the most sensitive material in a company. Retention, redaction, and who can
   read what are product-defining, and they are the operator's decisions, not R1's: put them in
   `decisions_for_user` with the evidence beside them.
5. **Does it adopt `gen_ai.*` semantic conventions despite their instability, and what happens when
   they change?** State the drift plan rather than pinning silently to a snapshot.
6. **What can it be pointed at today, on this machine, and run?** The continuity kit's lesson from
   this morning is unambiguous: the skeleton that was **driven against real data** produced a sixth
   failure mode and a spec defect that no amount of reasoning had found. There is a real corpus here
   — `.claude/autonomous/*-log.md`, driver logs, git history, `scripts/drive/FINDINGS.md` — and a
   proposal that cannot name what it would run against is a proposal that cannot be falsified.

## What would make this change wrong

- A schema invented from scratch when `gen_ai.*` exists, however unstable.
- The word "pluggable" doing the work that a named integration surface should do. The continuity
  kit's answer was an exit-code contract plus `--json`; this one needs an equally concrete answer.
- Claiming to register *everything* while the documented gaps above go unstated.
- Proposing enforcement the surveyed harnesses provide no seam for, without saying so.

## Instrument note

The harness facts in Part 1 come from one browsing session against vendor documentation. Several
rows are explicitly **NOT CONFIRMED** — Copilot CLI's env vars and event schema, Codex's env vars,
and whether either offers a hook seam. Those gaps are load-bearing for question 3, so a proposal
that needs them must label them, not fill them in.
