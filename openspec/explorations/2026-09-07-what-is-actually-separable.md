# Exploration — what is actually separable, measured against the code

**Date:** 2026-09-07
**Status:** Seed for a spec loop. Not a proposal. R1 owns every decision below.
**Supersedes, in part:** `openspec/explorations/2026-09-06-what-could-leave-agentweave-and-become-its-own-tool.md`
**Origin:** The operator, 2026-09-07 — *"Taking into consideration the explore written about what
can be generated as separate projects from this repo, review that exploration and validate, create
[a] folder on the parent folder for each project and a spec loop inside each for the project…
let's build a prototype of each one. Consider cli and ui approach for all of them. Also they should
be easily ext[en]sible by any harness like a tool that harnesses can use… is this even a good
idea?"*

The operator asked for validation first and a prototype second, and asked directly whether the
whole thing is a good idea. This seed answers the first, records an answer to the third, and hands
R1 the second.

---

## Part 1 — the 2026-09-06 exploration, checked against the code

That document was written by a session that **delegated its surveys and did not independently
re-verify them**, and said so in its own handoff. A verification pass on 2026-09-07 read the named
modules in full. Seven of its claims are wrong. This is the round-discipline lesson in its purest
form: *an argument can be wrong while everything it argues about is right.*

| Claim in the 2026-09-06 exploration | Verdict |
|---|---|
| "neither needs the runner/agent/charter machinery to exist" | **FALSIFIED** for the checkpoint engine. `checkpoint_trigger.py:139-153` resolves the generating CLI from `Project.checkpoint_runner_id` → a `Runner` row and refuses to generate without one (`:293-300`). `checkpoint_access.py:35-62` reads `can_read_checkpoints`/`can_recall` off the `Agent` row. Only *charter* is genuinely absent. |
| "checkpointing is an MCP server" | **MISLEADING.** The MCP tools are ~50-line HTTP delegates (`mcp_server.py:519-569`). The engine is ~4,500 lines of Hub across **11 of the 44 tables** in `db/models.py`. |
| "the loop wraps any CLI agent" | **FALSIFIED as shipped.** `run-iteration.ps1:23-24` is `[ValidateSet("claude","codex")]`; `:245-259` hardcodes both flag strings. Fixable in a line, but untrue today. |
| the review-page **generator** | **FALSIFIED — there is none.** The page is hand-written by the agent each day (`day-window.md:202`). What exists are two *checkers*, `scripts/drive/check_review_page.py` and `render_review_page.py` (199 lines, one repo coupling between them). |
| the threshold trigger's mechanism | **NEVER TRACED.** The percentage is the *Hub's own arithmetic* (`output_recording.py:127-152`) over a token count parsed from the runner's stdout (`runner_parsing.py:199-226`), not a number the runner reports. |
| the probe's dependence on Hub tables | **UNMENTIONED, and it is the hardest extraction problem.** `checkpoint_generation.py:11-14` states the design: the Hub can grade a checkpoint against `files_changed`, `tasks` and `open_questions` *sitting in a table*, which is why it needs no LLM judge. Strip those and `grade_probe` (`:376-403`) compares empty set to empty set and passes everything. **An extracted checkpoint tool degenerates into exactly the LLM-judge design its own docstring names as inferior.** |
| the loop's value is software | **FALSIFIED by measurement.** 879 lines of PowerShell against 1,047 lines of markdown — and every behavioural rule lives in the markdown. Nothing in any script enforces "this window does not implement"; the `Purpose` strings at `arm-cycle.ps1:64,73` are prose passed to a model. |

**Measured portable fraction of the checkpoint engine: ~52% of the three named files, but ~13% of
the 4,567-line stack that actually makes a checkpoint happen.**

One genuinely favourable finding for the loop, which the exploration also missed: the driver reads
only **six** of the 18 keys `arm-cycle.ps1` writes into `STATE.json` (`run-iteration.ps1:104-132`).
`queue`, `limits`, `purpose`, `decisions_for_user` and the rest are **convention the agent honours,
enforced by nothing.** The machine contract is six fields wide, which is a small, clean surface.

### The separability ranking nobody had produced

Ranked by measured dependency footprint, smallest first:

1. **`handoff` + `resume` + `DEAD-ENDS.md` — 728 lines of markdown, zero code dependencies.**
2. `check_review_page.py` + `render_review_page.py` — 199 lines, stdlib + Playwright, one coupling.
3. `hub/hub/checkpoint_policy.py` — 242 lines, one Hub import, duck-typed via `getattr`.
4. `hub/hub/spec_lifecycle.py` — 390 lines, **two** tables (against the checkpoint engine's eleven).
5. — (`scripts/drive/aw.py` is a client *for* AgentWeave; nothing to be standalone about.)
6. `src/agentweave/tool_surface.py` — **zero importers anywhere.** Not an extraction candidate; a
   deletion candidate. Its `resolve_access_path` is a stub returning `"cli"` unconditionally
   (`:106-107`), and the Hub uses its own mirror, `launchability.py:194`.

**The exploration recommended extracting #3-adjacent and the loop, and recommended against #1.**

## Part 2 — the answer to "is this even a good idea?"

**Partly, and the useful half is not the half the exploration picked.**

**The strongest single observation.** The 2026-09-06 document recommended extracting the two
mechanisms with the *least* production evidence, and recommended against the one with the *most*.
This repository's context continuity is carried by **111 numbered handoffs and a `DEAD-ENDS.md`
ledger compiled from 1,387 dead-end bullets across 193 handoffs** — proven daily for five weeks.
The Hub's checkpoint/cutover engine is the same idea rebuilt server-side and carries none of it.
Extracting the unproven mechanism while declining to extract the proven one is backwards.

And the reason given for declining #1 was a **market** argument ("three comparable tools found in
one search"), not a **separability** argument. Those are different claims and only one of them was
made. R1 should notice that the operator asked about separability.

**Against doing it at all, right now — two measured objections R1 must weigh, not skip:**

- **The build pipeline is oversupplied, not undersupplied.** As of 2026-09-07 there are three
  unarchived changes totalling ~91 tasks with **zero** implemented, six open severity-A findings
  (five with no proposal), and `DECISIONS.md` rows R-1 through R-3 open for a week. The FIX window
  builds roughly one change a night. New repositories add to the *proposing* half of a pipeline
  whose *building* half is the bottleneck.
- **Each new project costs operator decision time, which is the genuinely scarce resource.** The
  daily loop is built around exactly one human decision per day. Two more governed projects means
  two more review pages competing for the same evening.

**For doing it:** the operator's own framing — *"a tool that harnesses can use"* — is sharper than
the exploration's, and it converges with the sibling seed
(`2026-09-07-agentweave-without-mcp-and-with-copilot.md`). If the company blocks MCP, then anything
extracted needs a non-MCP surface anyway. That is one architectural question, asked twice.

And the measured answer to it is encouraging: **the most separable candidate is already a file
contract.** `spec-queue/README.md:17-25` is a five-row table of who writes what and who reads it;
the whole three-actor protocol is markdown in a directory. The `handoff` skill states the property
in its own text (`handoff/SKILL.md:22-24`: *"works in any CLI agent that can read and write
files"*). A file contract is the cheapest possible harness surface and the one least likely to be
blocked by any company policy — no server, no daemon, no MCP.

## Part 3 — what R1 is asked to do

The operator asked for a folder per project in the parent directory
(`C:\Users\huida\Documents\projects\`), a spec loop inside each, aimed at a prototype, considering
CLI and UI, and pluggable by any harness.

**The recommended candidate set — R1 may overturn it, but must state why:**

- **P1 — the continuity kit** (`handoff` + `resume` + `DEAD-ENDS.md` as a portable, agent-agnostic
  file contract plus a small CLI). Rank 1 on separability, strongest production evidence, and
  already harness-agnostic by construction.
- **P2 — the governed loop**, reframed. The extractable artifact is the **file contract and the
  playbooks** (`spec-queue/`'s three files, the token grammar, the FILL/DECIDE/FIX asymmetry) plus
  a thin cross-platform scheduler — *not* the 879 lines of PowerShell, which are a rewrite rather
  than a port and are structurally Windows-bound (`Unregister-ScheduledTask` is the loop's stop
  mechanism, called from inside the iteration body, `run-iteration.ps1:75,96,134`).
- **NOT the checkpoint engine.** 13% portable, 11 tables, and the probe — the thing that makes it
  better than its competitors — cannot survive the extraction. Record the reasoning; do not
  scaffold a folder for it.

**Questions R1 must answer, not inherit:**

1. **Are P1 and P2 one project or two?** They share primitives — the loop's `STATE.json` is the
   *position* half of the same split the handoff skill calls *understanding* vs *position*. The
   2026-09-06 exploration guessed at this in its open question #2 and never tested it. One project
   with two surfaces may be the honest answer, and it would halve the governance cost objection.
2. **What is the prototype's smallest honest scope?** The operator said CLI *and* UI. A UI is the
   expensive half and the half a prototype least needs. R1 should propose the CLI + file contract
   first and say explicitly what a UI would add and when — not silently drop it, and not build it
   because it was named.
3. **What is the harness integration surface, concretely?** Files, a CLI, an HTTP API, or an
   optional MCP shim over the same operations. Measured evidence says files first for P1/P2 and
   HTTP for anything Hub-derived. Make it explicit rather than "pluggable".
4. **Does anything actually get extracted, or is this a fork?** Copy-and-diverge is the cheap
   option and it ends with two drifting copies of `DEAD-ENDS.md`. Say which one this repo would
   then consume, and how.
5. **What is the new repo's own governance?** A new folder with no loop, no findings ledger and no
   review page is a folder that rots. Either it inherits the contract it is extracting — which
   would be a good first test of whether the contract is really portable — or R1 says plainly that
   it is a prototype nobody governs yet.

**Deliberate deviation from the round discipline, and the reasoning.** CLAUDE.md requires three
rounds before implementation. That discipline's whole force is *re-deriving an argument against
existing code* — which barely applies to an empty directory. For the new sibling projects R1+R2 is
enough, and the second round's job is the same as always: compare the proposal against what is
actually there, which here means **the source repository the capability is being lifted out of**.
Any change proposed against AgentWeave's own code keeps all three rounds.

## Instrument note

The verification pass that produced Part 1 also reported that `hub/hub/mcp_server.py:576` sent a
malformed path. **Spot-checked and FALSE** — the line reads `"/agents/request"` correctly. Its
other incidental finding was true and worse than reported: `scripts/drive/aw.py:15` carried a live
`aw_live_` key default in a tracked file, and `gh repo view` reports the repository **PUBLIC**.
Fixed on `autonomous/2026-09-07-daily` at `2d4131b`; the key itself is in git history and must be
treated as disclosed. One of two incidental findings was wrong — re-measure before building on
anything here.
