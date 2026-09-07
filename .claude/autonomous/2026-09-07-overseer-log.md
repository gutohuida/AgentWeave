# Overseer run — 2026-09-07

A third spec loop, asked for after the day's first two completed: *"a system to connect to the
harness that stores every single metric that we can… kinda of an overseer and we generate metrics
and governance on any AI harness."*

Runs in the same worktree and on the same branch as the sidequest run (`AgentWeave-sidequest`,
`autonomous/2026-09-07-sidequest`), with its own state file `STATE-overseer.json`, its own driver
log `driver-overseer.log`, and its own queue. It proposes inside a **new sibling repository** and
does not implement anything in AgentWeave.

Seed: `openspec/explorations/2026-09-07-an-overseer-for-any-harness.md`.

---

## Iteration 1 — T-1, spec loop R1

**Started 16:54, branch `autonomous/2026-09-07-sidequest` at `63b946a`.** State file and git agreed;
no reconciliation needed. No log file existed yet, so this is the chain's first entry.

### What was done

The inventory the queue demanded first, then a new repository at
`C:\Users\huida\Documents\projects\witness` — `git init`, no remote — holding the exploration, an
openspec config, and one change with a proposal, a design, tasks and three spec deltas.
`openspec validate --changes --strict` passes.

### The question the round existed to settle, and how it was settled

The seed's framing question was *is this a new product, or AgentWeave's Hub with the orchestration
removed?* It offered a distinction to test — *AgentWeave governs agents it spawns; an overseer
governs agents it does not control* — and told R1 to test it rather than accept it.

Tested: **true, but it is a restatement rather than evidence.** It names the difference; it does not
show the difference is load-bearing. Three measurements do:

1. **`hub/hub/api/v1/agent_actions.py` mounts 32 routes and all 32 depend on `get_agent_actor`.**
   The only two `Depends(...)` symbols in the file are `get_session` (32) and `get_agent_actor`
   (32). That dependency (`agent_auth.py:40-79`) resolves an `aw_run_`-prefixed bearer against
   `Run.capability_token_hash` where `Run.status == "running"`, and additionally rejects a token
   whose `Run.instance_id` is not this process. The plaintext *"exists only in run memory."* A
   harness the Hub did not spawn cannot obtain one — not by policy, by construction.
2. **`TurnUsage.run_id` is `ForeignKey("runs.id")`, `unique=True`, `nullable=False`
   (`models.py:1193-1195`).** One constructor (`usage_accounting.py:37`), two callers — the spawn
   loop (`agent_trigger.py`, 5 sites) and crash reconciliation. **No HTTP route writes it.** So
   AgentWeave can record a foreign agent's text but not its tokens. Cost is structurally
   unreachable without first spawning.
3. **The four routes that *do* accept unspawned-agent records all require the instance-operator
   credential.** `agents/{name}/output`, `.../context-usage`, `.../heartbeat` and `POST .../logs`
   all depend on `get_project` (`auth.py:134-159`), which authenticates through
   `_operator_from_credential` and demands an explicit `project_id` path param. Letting a foreign
   harness self-report today means giving it the keys to every project on the instance.

Generalised, and this is the finding the round turns on: CLAUDE.md states the Hub's security
property as *identity is never accepted from a request body or header.* **An overseer's entire job
is to relax exactly that.** Building it into the Hub means adding a second, weaker identity tier to
the system whose strength is having one. That is a security argument, and it is stronger than the
seed's taxonomy argument.

### Two places the seed was wrong, measured

- It gave the compatibility endpoints as `/api/v1/agents/{name}/output` and `.../context-usage`.
  They are mounted under `project_resources_router`'s `prefix="/projects/{project_id}"`
  (`api/v1/__init__.py:43,52`), so the real paths carry a project segment.
- It described them as *"authenticated by a project key."* There is no per-project ingestion key in
  this design; it is the instance-operator credential. That difference is the whole of measurement 3
  above, so it was not a cosmetic error.

### Two things the seed did not have

**The gap is not normalisation.** The seed's proposed reframing was *"the gap is not collection, it
is normalisation and governance."* Half wrong: `hub/hub/runner_parsing.py` already normalises three
harnesses (`parse_claude_line`, `parse_codex_line`, `parse_opencode_line`) into one
`RunEvent`/`ContextUsageSample`/`AccountingSample` model, with secret redaction
(`runner_events.py:63`) and UTF-8-safe truncation (`:88`), verified against live output. It is a
reference implementation to borrow from, not a gap. What it normalises is stdout from a process the
Hub spawned — a transport an overseer does not have.

**There is a fourth capture surface, and the seed's table omits it.** The seed tabulates OTel per
harness and calls hooks the richest local capture point. Measured on this machine, the harness's own
on-disk session transcript is richer: `~/.claude/projects/**/*.jsonl` is **2,069 files, 985 MB**,
and the largest single file under the AgentWeave project carries **2,070 lines across 17 distinct
record types** with zero unparseable lines. It needs no configuration, no administrator and no
consent dialog, and — uniquely — it is **retroactive**: it covers sessions that ran before any
overseer existed, which on this machine is all 2,069 of them.

AgentWeave already reads a harness's own file for this reason: `read_codex_rollout_accounting`
(`runner_parsing.py:669-706`) goes to `~/.codex/sessions/rollout-*.jsonl` because Codex's stdout
could not give a clean turn boundary. **The proposal is that technique with the spawn removed** —
a much smaller leap than "a new observability product", and it is said that way in the proposal
rather than dressed up.

The danger of that surface is the mirror image of OTel's, and the proposal leads with it. In OTel,
content is off until five flags are set. On disk, the content is **already there, complete and
unredacted** — prompts, file contents, tool arguments. Reading a transcript is not "enabling content
logging"; it is reading a file that already contains everything. That asymmetry is why the four
data-policy questions go to the operator rather than to a settings page, and why `corpus/`,
`*.transcript.jsonl` and `drive-output/` are in the new repository's `.gitignore` from commit one.

### What the proposal commits to

Named **witness**, and the name is the commitment: a witness testifies to what it saw and is
expected to say what it did not see.

- **Enforcement: the passive lever, exclusively** (design D3). The gateway is rejected because it
  sits in the critical path of every model request and because an organisation blunt enough to ban
  MCP wholesale will not approve a proxy faster. The tool boundary is rejected because it exists on
  Claude Code and is **NOT CONFIRMED** on Copilot CLI, and a product whose enforcement works on one
  harness of three must lie about two. The cost is stated: Witness cannot stop anything.
- **No scoring, grading or judging** (design D4), because AgentWeave retired its unasked-question
  backstop on 2026-08-20 for exactly this reason, and a product that grades conduct makes a larger
  version of that judgement on weaker evidence.
- **The deliverable is the completeness statement**, not the record. Precedent measured in-repo:
  `turn_usage`'s CheckConstraint forces every token column to NULL when `status = 'unavailable'`
  (`models.py:1214-1221`), so a row cannot claim ignorance and carry numbers. The proposal
  generalises that constraint to the whole record, and distinguishes `unavailable` from `redacted`
  on purpose — "could not see" and "saw and did not keep" are different facts.
- **Three capabilities:** `turn-record`, `capture-surfaces`, `completeness-report`. Surfaces are a
  closed named list with a per-field capability matrix, never "pluggable"; the completeness report
  is *derived* from those matrices rather than authored.

### R1's own recommendation

**Propose, then shelve.** Every requirement is downstream of four data-policy questions only the
operator can answer, and building before the answers is building the wrong thing carefully. This is
the day's third proposal and second new repository, against three unarchived AgentWeave changes with
zero tasks implemented and six open severity-A findings. The proposal says this in a "What this
displaces" section rather than leaving it to be noticed.

### Verification

- `openspec validate --changes --strict` → `1 passed, 0 failed`.
- Every count in the exploration re-measured after writing: 32 routes / 32 `get_agent_actor` deps,
  5 `record_turn_usage` call sites, 2,069 transcript files, 985 MB, 17 record types.
- One count was **wrong on the first write and corrected**: the exploration said 46 model classes;
  `grep -c '^class .*(Base):'` gives **44**, and the derived "other 37" became "other 35".
- Both new-repository invariants checked: `git remote -v` is empty, `.gitattributes` sets
  `* text=auto eol=lf` before any file was written.

### What could not be established

- **Copilot CLI, entirely.** Nothing in AgentWeave targets it. Its OTel environment variables, its
  event schema, and whether it offers any hook seam are NOT CONFIRMED, as the seed also says. Design
  D3 depends on the hook-seam gap, so it is labelled at the point of use rather than in a footnote.
- **Whether `gen_ai.*` conventions have moved** since the seed's browsing session. Design D5 treats
  them as a moving target on the seed's word, and task 1.7 is explicitly assigned to a session that
  can browse.
- **Whether the name `witness` collides** with an existing project. The repository has no remote, so
  nothing is claimed by using it.
- **How different the transcript format is from `--output-format stream-json`.** R1 did not verify
  this, and it is exactly where the "normalisation is a reference implementation, not a gap"
  argument could be wrong. It is written into design.md as R2's assignment rather than left as a
  quiet assumption.

### Repository state

`C:\Users\huida\Documents\projects\witness` at `6b0a135`, 11 files, no remote, clean tree.
