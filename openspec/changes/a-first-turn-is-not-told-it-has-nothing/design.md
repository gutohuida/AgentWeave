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

> **R2 (2026-09-20) — this Context paragraph is right and incomplete.** `access_path_notice` is one
> of **two** places the no-grounds branch asserts absence. The other is `_tool_surface_lines` in
> `hub/hub/api/v1/agents.py`, whose non-MCP preamble opens *"No AgentWeave tools are injected this
> turn"* — fed by the same `described_path`, in the same turn, reaching the model through
> `--append-system-prompt-file` / `model_instructions_file`. R1 explored `launchability.py` and
> `agent_trigger.py` and stopped at the notice; the context renderer is one `access_path=` argument
> further down the same call and carries the stronger falsehood. See **D6**. The 2026-09-14
> exploration this change cites did not notice it either, so this is new to R2 rather than a
> re-finding.

## Goals / Non-Goals

**Goals:**

- The first turn of a new agent contains no false statement about its tool surface. **R2: this goal
  is the reason `agents.py` had to come into scope. With only the notice edited, the first turn
  still contains one — in the tool section rather than the first line.**
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

> **R2 dissent, recorded and not acted on.** Asked to judge the declined alternative on its merits,
> R2 thinks it is the better change, and that D2's reasoning is sound about *authority* but weak
> about *sufficiency*. Removing the denial is necessary; the evidence this change cites does not
> show it is sufficient. The Architect had the tools, was not blocked from using them, used
> `ask_user` through MCP in the same session — and still kept to `curl` and payload files for ten
> runs *after the notice healed*, when nothing false remained in front of it. What persisted was
> the positive HTTP steer, which this change deliberately keeps. A text of the form "the
> `agentweave` tools are available if they appear in your tool list; otherwise the same operations
> are HTTP requests" asserts nothing the system cannot know — it is a conditional, not a claim —
> and it is the only wording that both stops the falsehood and stops pointing a tool-holding agent
> at `curl`. It also makes D3's "unless it has grounds" hedge unnecessary and retires the grounds
> mechanism's only consumer.
>
> **R2 is not making that change.** The verdict is the operator's and it chose otherwise; R2's
> mandate is to correct the proposal against the code, not to overrule a decision. But the honest
> statement of this change's expected effect is: *it removes two falsehoods from every agent's
> first turn, and it is not established that it changes what the agent then does.* The tasks must
> not claim more than that, and 4.3 has been narrowed accordingly. If the operator wants the
> measured behaviour fixed rather than the falsehood removed, this is the decision to revisit —
> before implementation, since the two changes touch the same two strings.

> **DECIDED by the operator, 2026-09-20, in session: ship this shape, then measure — and the
> measurement is group 7, not an intention.** R2's dissent was put to the operator with its
> argument intact. The decision is **neither** "keep the decided shape and close the question"
> **nor** "switch to the conditional text": it is to land the falsehood removal, then find out
> empirically whether a fresh agent still reaches for `curl` when nothing false is in front of it.
>
> **What decided it: R2's evidence is confounded, and the confound is not resolvable from the
> observation it rests on.** The Architect kept to `curl` for ten runs after the notice healed —
> but by then it had *already learned a working method*, deriving its payload shapes from two 422s
> and building a file-plus-`curl` routine that worked. Two explanations fit that record equally:
> (a) the positive HTTP steer kept pointing it at `curl` on every later turn, which is R2's reading
> and would mean this change is insufficient; or (b) it kept a method it had already paid for,
> which is ordinary and would mean this change is sufficient for an agent that never pays that cost
> in the first place. **One agent that had already invested cannot distinguish them.**
>
> **Only a fresh agent's first turn separates the two**, because that is the single moment where
> the steer acts with no learned method behind it. That measurement does not exist yet and cannot
> be taken before this change lands — the falsehood is a competing cause that has to be removed
> first. So the order is: ship, then measure, then decide whether the conditional text is still
> wanted.
>
> **This does not reopen the 2026-09-09 verdict**, and the conditional text is not approved. It is
> held open pending group 7's result, and D2's reasoning above stands unless that result contradicts
> it.

### D3 — "Unless it has grounds" is written into the requirement even though grounds never exist today

The new clause forbids asserting absence *unless the system has grounds*. Today it never does: the
one place the truth appears is the harness's first `system`/`init` line carrying `mcp_servers`, and
`parse_claude_line` has no branch for it (**F340**).

*Why word it conditionally rather than as a flat prohibition:* grounds for absence are obtainable,
and F340 is the change that would obtain them. A flat "never say absent" would have to be amended
the day that ships; the conditional form is already correct for both worlds, and it keeps the
requirement symmetric with the presence clause directly beside it, which is the point.

> **R2 verified D3's premise in the code and it holds.** Nothing reads the harness's reported MCP
> state. `parse_claude_line` (`hub/hub/runner_parsing.py`) branches on exactly four message types —
> `assistant`, `user`, `result`, `rate_limit_event` — and has no `system`/`init` branch at all, so
> the line carrying `mcp_servers` is parsed as nothing. Grepping `mcp_servers` across `hub/hub/`
> returns only *outbound* config construction (`runner_commands.py`, `codex_appserver.py`); there is
> no inbound reader anywhere. The only ground that exists today is the positive one,
> `Run.mcp_adapter_online_at`, set by the adapter announcing itself — a different mechanism, and
> one with no negative form. D3's conditional wording is correct as written.
>
> **R2 also had to fix what the conditional did to the rest of the SHALL** — see the spec delta's
> R2 note. R1 rewrote the surviving third clause from *"SHALL describe the plane's direct HTTP form
> instead when it has no such grounds"* to *"when it has grounds for neither"*, which quietly
> removes the obligation to describe the HTTP form in precisely the world D3 is anticipating: once
> F340 ships and the system has grounds for **absence**, "grounds for neither" is false and the
> clause stops applying — in the one case where HTTP is the run's only path. The delta now keeps the
> live breadth.

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

> **R2 — D5 is right and the tasks that implement it were aimed at the wrong files.** R2 read all
> four test files. **None of the other three pins the removed clause**, so R1's task 3.2 ("restage
> anything 1.2 found pinning the removed clause in the other three test files") would have found
> nothing and ticked green having proved nothing — the shape of failure this repo's discipline
> exists to catch. The substantive gap is the opposite one:
> `hub/tests/test_launchability.py::test_a_run_without_mcp_is_not_told_it_cannot_act` is a test
> written to stop exactly this class of sentence, and the current clause walked past it, because it
> only checks the *previous* denial wordings (`"no AgentWeave tool surface is available"`,
> `"cannot send messages"`). Extending that test is the edit; finding nothing to restage is the
> correct outcome of 3.2 and is now stated as such.

### D6 — The canonical context's preamble is fixed in the same change (R2, added 2026-09-20)

`_tool_surface_lines` (`hub/hub/api/v1/agents.py`) renders the tool inventory in one of two idioms,
chosen by the same `described_path` the notice uses. Its non-MCP preamble begins *"No AgentWeave
tools are injected this turn, so each capability below is one HTTP request instead."*

*Why it is in scope rather than a follow-up:* it is the same defect, not a related one — an
unfounded assertion of absence, in the same turn, to the same agent, from the same value — and it is
the **stronger** of the two, since "no AgentWeave tools are injected" is unambiguously false when
injection is what `agent_trigger.py` just did. It reaches the model as text ahead of the operator's
message (`--append-system-prompt-file` for `claude`, `-c model_instructions_file=` for `codex`), so
the delta's new scenarios reach it: a shipped product with this sentence still in it fails *"No
grounds means no denial either"* and *"A run holding the tools is not told it is empty"* on the day
the notice change lands. A change cannot be allowed to violate the requirement it is writing.

> **R3 (2026-09-20) — D6 had an argument and no specimen; there is one, and it is unusually
> direct.** R2 argued the `agents.py` sentence is *stronger* than the notice's but cited no agent
> acting on it. `testbed/scratch/c2verify/driveA.json` is a captured drive in which a real agent
> reads it and reasons about it aloud, twice:
>
> > *"I notice the system message says \"No AgentWeave tools are injected this turn\" but then lists
> > the tools I can use. … This seems like a contradiction or the tools have overly strict
> > sandboxing."*
>
> > *"in the AgentWeave context, the system said \"No AgentWeave tools are injected this turn, so
> > each capability below is one HTTP request instead.\" This tells me I need to make HTTP requests.
> > The curl approach is the right one."*
>
> The agent then spent its turn fighting the approver to `curl`, while holding the tools. This is
> the change's causal claim — an unfounded denial steering an agent to HTTP — observed at the
> `agents.py` site specifically, which is the half with no test pinning it. **Note the contrast with
> the LoopEngine record**: that one is about the *notice*, and its behavioural half is one agent
> (see tasks 7.5). This one is about the *context preamble*. Two sites, one specimen each.
>
> *This file is evidence, not a fixture: task 1.1b is right that nothing under `testbed/scratch/`
> gets edited. It is cited here so the next round does not re-derive it — or, worse, conclude D6
> rests on reasoning alone.*

*The edit, in D1's shape:* drop the absence claim and keep every load-bearing part — the `HUB_URL`
address, the `Authorization: Bearer $AW_RUN_TOKEN` header, the read-from-your-own-environment
instruction, the `*`-means-required and `{...}`-means-substitute conventions, and the
JSON/`detail`-refusal sentence. The clause cannot simply be deleted: *"so each capability below is
one HTTP request instead"* dangles without its subject, so the sentence is restated positively
(for example, "Each capability below is described as one HTTP request.") rather than truncated.

*What must not move:* the `access_path: str = "mcp"` default, the `over_mcp` branch, `_http_lines`,
`_mcp_lines`, `_operations()`, and the one-source-two-renderings invariant that
`test_tool_surface_matches_server.py` enforces. The comment above the `else` branch explaining why
credential values are never interpolated must survive, for the same reason D1 keeps its counterpart.

*Rejected:* leaving it to its own change, which would ship a requirement its own product violates;
and rewriting the whole preamble, which risks content four scenarios depend on for no gain.

## Risks / Trade-offs

- **A test elsewhere pins the exact string and is missed** → three further files reference
  `access_path_notice` (`test_agent_facing_text.py`, `test_launchability.py`,
  `test_tool_surface_matches_server.py`). Each is read and named in tasks, not grepped once.
  **R2 has already done this read and the answer is recorded in the proposal's Impact list: none of
  the three pins the clause.** The risk that remains is the inverse — a test that *should* have
  caught it and did not.
- **A non-test consumer of the changed strings goes quietly stale** (R2) → `scripts/drive/
  t_d1_0909_together.py` detects the access path with
  `injected = "No AgentWeave tools are injected this turn" in text`. Nothing fails if it is missed;
  it just answers `False` forever, and a future drive reports the opposite of the truth. Named in
  Impact and in task 1.1.
- **The change removes the falsehood without changing the behaviour it was filed for** (R2) → see
  the dissent under D2. This is accepted, and the tasks must not tick as though the measured harm
  were closed. F302's ledger entry says the notice stopped lying, not that the agent stopped
  reaching for `curl`.
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
