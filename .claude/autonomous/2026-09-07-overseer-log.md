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

---

## Iteration 2 — T-2, spec loop R2

**Done:** an independent re-derivation of the Witness proposal against AgentWeave's real recording
layer and against the real transcript corpus. Not a re-read of R1. Committed to
`C:\Users\huida\Documents\projects\witness` at `3d75aaa` (no remote, clean tree); findings in
`openspec/explorations/2026-09-07-r2-what-the-transcript-actually-contains.md`.

### R1's separation argument: re-derived, and it holds

All three measurements were re-taken against the checkout rather than copied. 32 route decorators in
`agent_actions.py`, 32 `Depends(get_agent_actor)`, no third dependency but `get_session`.
`TurnUsage.run_id` is `ForeignKey("runs.id"), unique=True, nullable=False` with 6 call sites in 2
modules, none of them a route. `post_agent_output` and `post_context_usage` both take
`Depends(get_project)` under a `/projects/{project_id}` prefix. **D1 survives R2 intact.** The value
of this round is everywhere else.

### The assignment R1 set for R2, answered by running the code

R1 wrote its own weak point into design.md: *the transcript file and `--output-format stream-json`
are not the same format, and R1 did not verify how different they are.* R2 ran `parse_claude_line`
unmodified over a real 2,070-line transcript instead of reading it.

- 859 of 2,070 lines produced an event; 636 usage samples; **0 accounting samples**.
- Session id resolved on 1,337 of 2,070 lines: the file writes `sessionId` (2,022 lines), the parser
  reads `session_id` (1,337). Eleven record types carry the camelCase key alone.
- It maps **2 of the file's 16 record types**. The other 14 are 1,050 lines, 51% of the file, and
  include `permission-mode` (89) and `file-history-delta`/`-snapshot` (48) — governance evidence by
  any reading.
- Its `user` branch emits events only for `tool_result` blocks, so **the operator's prompt produces
  nothing**: 24 event-less `user` records, of which 14 meta, 4 command wrappers and **6 genuine
  operator prose prompts**.

The verdict is "half". The event vocabulary transfers; the parser does not — and the parts that
transfer cleanly are the parts Witness needs least. For a Hub-spawned run the prompt is redundant
because the Hub sent it. Witness never sent it, and the transcript is its only source.

### Three defects, two of them spec-level

1. **The capability matrix's key was wrong.** Every `thinking` block on disk is
   `{type, thinking, signature}`, and the text is present for `claude-haiku-4-5` (398 of 421 blocks)
   and absent for `claude-opus-5` (0 of 1,987) and `claude-sonnet-5` (0 of 848). Corpus-wide the
   split is per-session and clean: 625 files with non-empty thinking, 1,302 with empty, **0 in
   both**. Version and entrypoint do not separate the groups; the model does. A per-surface matrix
   has one answer and **both answers are wrong for most of the corpus** — and since the completeness
   report is *derived* from the matrix, that is a false completeness statement produced by the
   mechanism built to prevent them. Entries are now `always` / `never` / `conditional`, resolved per
   record, yielding `unavailable` rather than a guess when the condition cannot be read.
2. **The provenance state set could not express a computed value.** No transcript in the 2,095-file
   corpus contains a `result` record, and `total_cost_usd` appears as a JSON key in **0 files**
   (both re-checked with whitespace-tolerant patterns). Cost is unobservable on the only implemented
   surface. It is computable: `usage.input_tokens` is present on **11,581 of 11,581** assistant
   messages across a 150-file sample. With three states the design could only report nothing about
   spend or store a computed figure as `measured` and lie — and AgentWeave takes the second path in
   `output_recording.resolve_usage_limit`, which fills `percent` from a catalog into the same field
   shape a runner's self-report uses, indistinguishable downstream. Added `derived`: measured-only
   inputs, names its rule, counted separately everywhere, refused on derived-on-derived.
3. **The record did not require the instruction.** New requirement, with the reason it is easy to
   miss written into it.

### Two claims falsified, one of them the proposal's strongest sentence

**"On disk the content is already there, complete and unredacted."** False for the reasoning of the
two models the operator actually uses. Two consequences: OV-1 is a decision about a *smaller*
disclosure than R1 described, and the operator is entitled to decide against the true description;
and the proposal made a completeness claim about its own corpus that measurement falsified, inside
the document arguing that you cannot do that. That is the strongest available evidence *for*
building it.

**"Copilot CLI, entirely. Nothing in AgentWeave targets it."** Wrong, and correctable offline.
`COPILOT_OTEL_DIR` still sits in `src/agentweave/constants.py:29`; `git log -S` finds commit
`1c6970d` (2026-07-29), a live-probed Copilot OTel collector against CLI 1.0.75, deleted with the
watchdog. From it: Copilot's stdout carries no usage field at all; its OTel file exporter writes only
when `COPILOT_OTEL_FILE_EXPORTER_PATH` is set **before spawn**; it emits `gen_ai.usage.input_tokens`
(so D5's mapping is confirmed in practice for a second harness); content is gated by
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`, pinned off by the collector; the root
`invoke_agent` span aggregates every call, so summing chat spans double-counts.

The consequence that matters is the one that looks like a footnote: **Copilot's file surface is
neither passive nor retroactive.** A passive overseer gets nothing from it for any session already
run. Surfaces now declare both properties, and the report must state them.

### The question T-2 asked plainly

*How much of the proposed overseer is AgentWeave already?* **Most of it.** `agent_outputs`,
`event_logs`, `turn_usage`, `permission_requests`, `questions`, `runs` and `conversations` already
store text, tool calls and results, context readings, tokens, cost, permission decisions with the
tool input and who decided, operator Q&A, turn boundaries and thread identity. Witness's data model
is those tables with the foreign keys to `runs` removed. That is a finding, not a failure, and it
narrows what is genuinely novel to two things: the inverted identity requirement (D1), and the
completeness statement, which AgentWeave has for one field group and nowhere else. Written into the
proposal in those words.

### R2 broke the proposal's own corpus rule, and left the evidence in

The first draft of §2.2 quoted eleven words of a real operator prompt to prove the prompts were
genuine. The proposal three files away says a drive may report counts and *"may not paste a line."*
The round that drove the corpus broke the corpus rule in its own write-up, on its first attempt,
with the rule in a file it had read that hour. Removed and recorded rather than quietly fixed: it is
the cheapest available argument that OV-2's redaction posture cannot rest on the reader's
discipline.

### Corrections R2 made to its own numbers before committing

Two figures were wrong in draft and were re-measured rather than shipped. "11,583 of 11,583
assistant messages carry usage" had a filtered denominator — only lines already containing `"usage"`
were counted, which made it near-tautological; re-run over every assistant message it is 11,581 of
11,581. And "the other 14 types are 1,211 lines, 58%" conflated two different counts: the 14 types
are 1,050 lines (51%), while 1,211 lines (58%) produce no event once the 137 empty-thinking
assistant records and 24 prompt-carrying user records are added.

### Verification

- `openspec validate --changes --strict` → `1 passed, 0 failed`, run after every edit round.
- Every number above came from code run this iteration, not from R1's document.
- The corpus greps were repeated with whitespace-tolerant patterns so the zero results do not rest
  on the corpus happening to be written compactly.
- `git status` clean in both repositories; `git remote -v` still empty in witness.

### What R2 could not establish

- Whether Opus/Sonnet thinking is empty because the API returns it encrypted or because Claude Code
  declines to persist it. The signature is present, the text is not; both fit. It does not change
  the matrix — unavailable either way — but it changes whether the gap could ever close.
- Whether any field other than reasoning varies by model. Only `thinking` was measured that way.
- Anything about Copilot after 1.0.75 / 2026-07-29, or about Gemini CLI and Cursor at all.
- Whether the 14 unmapped record types are stable across Claude Code versions. `atis-latch`,
  `bridge-session` and `frame-link` are undocumented.

### One thing worth carrying to T-4

The corpus is live and it observes the observer: 2,069 files / 985 MB at R1 this morning, 2,095 /
1.1 GB at R2 this evening, part of the growth being these rounds' own sessions — and one file in
R2's own sample no longer existed by the time the sampler opened it, minutes after the listing that
named it. Any corpus size in a task or a spec is an output of a measurement, never a fixture.

### Repository state

`C:\Users\huida\Documents\projects\witness` at `3d75aaa`, 12 files, no remote, clean tree.


## Iteration 3 — T-3, spec loop R3

**Started 19:34, finished 19:52.** Branch `autonomous/2026-09-07-sidequest` at `91eefd6` on entry,
matching STATE. Witness at `3d75aaa`, clean. R3's assigned job: settle the enforcement question and
test D3/D4 against the requirements *as written*.

### The assigned question, and the measurement that reframed it

R3 was told to establish which of three levers the proposal commits to — a gateway that can refuse, a
tool-boundary hook that can refuse, or an after-the-fact report — and make `design.md` say so.

D3 already said "after the fact, exclusively". The finding is that **the phrase was covering two
different products**, and the measurement that shows it took two commands. The transcript is not a
retrospective artefact: on R3's own live session file, a `tool_use` record was readable on disk
**0.114 s** after its own timestamp, by the very Bash command that record describes, before that
command produced output; repeated one call later, **0.202 s**, with the preceding `thinking` and
`tool_result` records already present. The surface is a live append log.

So "after the fact" spans a batch reader the operator runs and a resident tailer that watches, and
those differ in deployment, in what they can see, in latency, and in disclosure. **New decision D8:
the first cut is a command, not a daemon.** Three reasons, strongest first: OV-1 asks permission to
read the corpus *when the operator runs it* and would be answered by a process reading it unattended
— using a consent answer for a larger action than it described is exactly the failure this product
exists to prevent; a forward-only tailer is the collector-shaped design D2 already rejected, coming
back through another door; and the resident version has failure modes the batch one lacks entirely,
including a crash whose silence is indistinguishable from inactivity.

The cost is written next to the decision rather than left implied: **a batch reader cannot keep a
record past the harness's deletion window**, so D8 and OV-3 are one decision wearing two hats. That
is now a fifth item in `decisions_for_user`.

One thing the latency measurement takes away: Witness can no longer say it is passive because it
arrives too late to intervene. At 0.2 s it arrives in time. It is passive because the seam is
deliberately not built — a position, now stated as one.

### D4 tested as written, and it was intention rather than fence — twice

**The report permitted the number D4 forbids.** `completeness-report` said a report MAY state each
agent's *completeness percentage* while forbidding any ranking. Measured over a 220-file random
sample, 14,701 assistant messages: every field the surface can fill is filled on **100%** of messages
for every model — tokens, cache fields, service tier, session, cwd, branch, version, stop reason —
with exactly one exception, reasoning text: **407 of 1,022 blocks on haiku-4.5, 0 of 8,572 on
opus-5, 0 of 5,094 on sonnet-5**. The only field that varies, varies by model. A per-agent
completeness percentage is therefore a ranking of model choice, handed to the reader by the page that
forbids ranking. Completeness is now a property of a surface and a record, reported per surface and
per model, and may not be attached to an agent identity.

**D4's rules sentence had no requirement behind it, and the surface supplies a ready-made verdict.**
Nothing said rules are operator-authored, that Witness ships none, or that a rule may not be
evaluated by asking a model — so a default set named `unsafe-tool-use` would have violated nothing,
which is AgentWeave's retired unasked-question backstop with a config file in front of it.
Separately, a 250-file sample (37,837 records, 17 types) carries **1,535 `ai-title` records** and 44
`classifierMetaLines` annotations: model-authored characterisations of a session that a reader would
store as `measured` — the strongest claim this product can make — and a report would republish in
Witness's own voice. The fix is not a provenance state, because the value genuinely was measured; it
is a new **author** axis on every field, with model-authored values counted apart and never reported.

### Two measurement corrections, one of which R3 committed itself first

**Retroactivity has a floor, and it is the harness's.** R1: *"it covers sessions that ran before
Witness existed — on this machine that is all 2,069 of them."* Measured: **2,084 files, 1.09 GB,
spanning 2026-08-09 to today — 29 days**, 44 files on the oldest day and **zero before it**, a cliff
with no taper, while at least **51 sessions ran earlier** (handoff files committed 2026-07-28 to
08-07, one session minimum each, none of their transcripts surviving). Retroactive means *to the
harness's retention window*. Neither settings file names a retention period, so the span is measured
and the policy behind it is unverified — stated that way rather than rounded to "30 days".

**169 delegated-agent transcripts sit one directory deeper, wearing the parent's name.**
`<project>/<session>/subagents/agent-*.jsonl`: 5 project directories, 42 parent sessions, 13,632
lines, 8,073 assistant messages, 2.77M output tokens — duplicated into the session file nowhere (0
`isSidechain`-true records across a 23,433-line sample). R3's own first glob was one level deep and
returned **1,915** files against a true 2,084: an 8% undercount that looked exactly like a
measurement, caught only because the number was checked against a recursive count.

The serious half is identity. A subagent record carries the **parent's** `sessionId`, so the existing
requirement — *store that value as the session identifier* — is satisfied exactly while crediting the
work to the wrong actor. Driven rather than argued, over one real session and its 8 delegated
transcripts: keying on `sessionId` gives **1 actor holding 545 turns**; keying on the acting agent
gives **9 actors**, of which **370 turns (68%) belong to delegated agents**. The requirement did not
fail to prevent that failure — it prescribed it.

### What changed in the change

- `design.md`: new **D8**; `[R3]` amendments inside D2 (the floor), D3 (the two products), D4 (both
  holes) and D6 (discovery depth); the closing section rewritten to record what each round attacked
  and what a fourth should attack first.
- `turn-record`: new requirement *a value a model authored is never stored as an observation*; new
  scenario for delegated-agent records; the stale `11,583` figure replaced with R3's own
  re-measurement (14,701 of 14,701).
- `capture-surfaces`: new scenario for reporting past a surface's oldest observable record; new
  scenario for enumeration depth, requiring per-depth counts so "found none" differs from "did not
  look".
- `completeness-report`: per-agent completeness forbidden, per-surface-per-model required; new
  requirement *rules are the operator's, and no rule is evaluated by a model*.
- `tasks.md`: 0.2 closed; eight tasks added (1.11, 1.12, 2.8, 2.9, 3.9, 4.5, 4.6, 5.5), 0.3 widened
  to five decisions, 3.4 rewritten for enumeration depth, and "no resident process" added to the
  non-goals.

### R3's answer to the question R2 left it

OV-1 and OV-2 remain the right questions and remain one question each: "everything except the
frontier models' reasoning" is still every prompt, every tool argument and every file the agents
read, so the corrected shape does not split them. Two things did change around OV-1 — its scope
silently includes 169 delegated-agent transcripts an operator picturing "my sessions" would not
picture, and it is now **time-sensitive**, because the corpus deletes on a rolling window and "yes,
later" is not the same answer as "yes".

### Verification

- `openspec validate --changes --strict` → `1 passed, 0 failed`, run after the spec edits and again
  after the last amendment.
- Every number in this entry was produced by code run this iteration. R2's model split was re-derived
  independently at corpus scale **and** observed live: this session (Opus 5) wrote 9 `thinking`
  blocks, all `{signature, thinking, type}` with zero-length text.
- The misattribution finding was driven, not reasoned: both keying strategies were run over real
  files and the numbers above are that run's output.
- Both repositories clean; `git remote -v` still empty in witness.

### What R3 could not establish

- The retention policy value. The 29-day span and the cliff are measured; no `cleanupPeriodDays`
  appears in either settings file this session can read, and the default is not verifiable offline.
- Whether `ai-title` and `classifierMetaLines` are produced locally or server-side. Either way they
  are model-authored, which is all the requirement needs.
- A live tailer's robustness in practice. F3 measured write latency, not the difficulty of following
  the file; that is deferred with the resident mode D8 declines.

### Repository state

`C:\Users\huida\Documents\projects\witness` at `e2bb331`, 13 files, no remote, clean tree.

---

## Iteration 4 — T-4, the overseer section on the review page

### What was done

Appended §7 to the existing `.claude/autonomous/2026-09-07-sidequest-review.html` rather than writing
a second page, per the queue item: the operator reads one page. 49,524 bytes → 68,386. No second file
was created; `_ov_section.html` was a scratch file spliced in and deleted in the same iteration.

### The four stale claims in the wrapper, and what they were replaced with

The queue named two; there were four, and the extra two were found by reading the header and lede as
a stranger would rather than by searching for the two strings the queue quoted.

| Was | Now | Why it was wrong |
|---|---|---|
| `six iterations` | `eight sidequest iterations + four overseer iterations` | The sidequest run ended at iteration 8 (`STATE-sidequest.json`); this is the overseer run's 4th. |
| `Eleven decisions … in §6` | `Eighteen decisions — twelve in §6, six more in §7.4` | S-10 added SQ-12; loop 3 adds SQ-13…SQ-18. |
| `two spec loops` / `one new sibling repository (continuity-kit)` | `three spec loops, all complete` / `two new sibling repositories (continuity-kit, witness)` | **Not in the queue item.** The header described the page before loop 3 existed. |
| `nothing implemented in AgentWeave and nothing driven` | `nothing implemented in AgentWeave; one prototype built and driven, outside it` | **Not in the queue item, and it contradicted the page's own S-10 addendum**, which is 60 lines about a prototype that was driven against a real clone. The header said the opposite of a section already on the page. |

Also corrected: the lede's *"two proposals and one new local repository"* (three and two), and §5's
opening *"Two changes"*, which is now scoped — *"Two changes from loops 1 and 2"* — with a pointer to
§7's own table, so the section is not read as the page's complete spec inventory.

### What §7 says

Six blocks, following §2's shape so the page reads as one document:

- **The question the loop existed to settle**, with the three separation measurements as a table
  (32/32 routes on `get_agent_actor`; `TurnUsage.run_id` a non-null unique FK with no HTTP writer; the
  ingestion routes on the instance-operator credential) and the framing stated as what it is — settled
  *against* the seed's taxonomy reason and *for* the identity-model one.
- **What each round changed about the one before it**, R1/R2/R3, in the same table markup §2 uses.
  Each row is what that round *moved*, not what it read. The queue asked that a round which changed
  nothing be said to have changed nothing; none did, so a note says that explicitly and names the
  reason a third round earned its cost — **R2 and R3 each corrected a number the previous round had
  stated as a measurement.**
- **What loop 3 specced** — one change, 17 requirements / 43 scenarios across three capabilities,
  2 of 45 tasks done and both of them round-discipline tasks in phase 0, so the "0 implementation"
  claim is on the page rather than implied by a ratio.
- **What could not be established**, split by cause as the queue asked: the open web (the seed's
  telemetry facts, the name collision), a running harness (tailer robustness, whether `ai-title` is
  local or server-side), the retention *policy* behind the measured 29-day span, and the one that
  applies to both sibling repositories — nobody but the author has read either.
- **The corpus observes the observer** — 2,069 / 2,095 / 2,084 across the three rounds, part of the
  growth being these rounds' own sessions.
- **SQ-13…SQ-18**, continuing the series, each carrying its `OV-n` id from `STATE-overseer.json` so
  the page and the state file can be matched. SQ-13 is marked as blocking every phase but phase 0;
  SQ-15 and SQ-18 are marked as one decision wearing two hats.

### Verification

- `py -3.11 scripts/drive/check_review_page.py .claude/autonomous/2026-09-07-sidequest-review.html`
  read rather than trusted for exit code: **10 checks, all ok** — no stray CR, full wrapper, bare
  `:root`, dark scheme, body background, zero external references, tag-balance walk clean, nothing
  left unclosed.
- `findings on the page: 0` is **not a regression.** Checked by running the same script over
  `git show HEAD:` of the page: it printed `0` before this iteration too. That check greps
  `class="fid">F\d+<` inside section 3's slice, and this page's §4 uses different markup for its
  finding rows. Recorded rather than fixed — the checker is scoped for the daily loop's pages.
- The script slices between `"What today's drive found"` and the **first** `"What was specced"`
  occurrence, so the new section's own heading was deliberately titled *What loop 3 specced* to avoid
  ever becoming that first occurrence if the sections are reordered.
- SQ ids counted by script: 18 distinct, SQ-1…SQ-18, no gaps and no duplicate `<h4>` definitions —
  the repeated counts are cross-references (SQ-1 ×3, SQ-13 ×3, SQ-18 ×3).
- Every number in §7 is copied from a round that produced it by running code; nothing was re-derived
  from prose. The witness change was re-validated while writing:
  `openspec validate --changes --strict` → `1 passed, 0 failed`.

### What this iteration did not do

No AgentWeave product code, no Hub, no agent turn, no web, nothing under `spec-queue/`, and no write
to `STATE-sidequest.json` or `STATE-day.json`/`STATE-night.json`. The witness repository was read
(commit ids, spec counts, validation) and not modified; it stays at `e2bb331`, clean, no remote.

### Repository state

Worktree `AgentWeave-sidequest` on `autonomous/2026-09-07-sidequest`, clean after commit. Review page
68,386 bytes, one file, self-contained.

---

## Iteration 5 — T-5: the skeleton runs, and the rule that protects the report makes the actor unprintable

**2026-09-07, ~20:04–21:55 +01:00.** Branch `autonomous/2026-09-07-sidequest`, worktree
`AgentWeave-sidequest`. State verified against `git log` before starting: `4a7cd93` matched
`iteration: 4`, `next_action: T-5`. Nothing to reconcile.

T-5 was conditional on more than 60 minutes remaining before `stop_at`. 116 remained, so it ran.

### The gate that would have made this a no-op — and why it was wrong

`witness/openspec/changes/.../tasks.md` said, in R1's words and unamended by R2 or R3:
**"Every phase below is blocked on 0.3."** 0.3 is the operator's permission to read
`~/.claude/projects/**/*.jsonl`. Taken literally, T-5 had nothing to build.

**That gate is too coarse, and it is finding W-7.** 0.3 asks *may Witness read your sessions?* and
the tasks file generalised the answer to *may Witness read anything?* A repository's own commit
history is data the operator has already published — reading it discloses nothing that was not
already pushed — and it is nonetheless a record of turns performed by **agents Witness did not
spawn**, which is the product's entire subject. The block belongs to the **surface**, not the
product. The queue item had already pointed at this corpus ("git history"); the finding is that the
specs could not say why that was allowed.

Acted on it. `tasks.md` now marks per-item `[gated: claude-transcript]` where 0.3 genuinely blocks,
and the old sentence is replaced with the reason it was wrong.

### What was built — `witness` at `c09dd08`

`src/witness/`, stdlib only, ~700 lines: `provenance.py` (four states, construction-time checks,
`derive()`), `record.py` (ten fields, mapping identifiers, JSONL round trip), `matrix.py`
(always/never/conditional, per-record resolution, load-time completeness), `surfaces.py` (the
closed list), `surface_git.py` (the one reader), `report.py`, `__main__.py`. 44 tests, each named
for the `tasks.md` item it closes, `py -3.11 -m unittest tests.test_witness`.

Stdlib is not a decision about the stack — task 0.4 is undecided and zero dependencies is the only
choice that pre-commits nothing.

**The transcript surface has no reader compiled in at all.** `witness report --surface
claude-transcript` exits 2 naming decision 0.3. The block is an absence, not a flag.

### The drive

`witness report --surface git-commit` over this worktree's real history — **2,829 commits,
2026-03-07 to 2026-09-07** — plus the witness repo's own three commits as a contrast case.
Full write-up in `witness/DRIVE.md`; new phase 6 in `tasks.md` carries the nine follow-ups.

**Eight findings. Five are defects in the specs R1–R3 wrote, not in the code.**

- **W-1, the one that matters.** The only agent identity a commit carries is the `Co-Authored-By`
  trailer — **1,699 of 2,829, five distinct values** — and *the model wrote it*. Declared honestly,
  `actor` and `model` are model-authored, and R3's rule that a model-authored value **"SHALL NOT
  appear in any emitted report"** then makes both unprintable: the per-model breakdown comes out as
  five buckets named `model-authored-value-<hash>`. Implemented that way deliberately so the
  collision shows in the output rather than in a comment. **The axis conflates a model's
  *characterisation* of a turn (`ai-title`, a commit subject — must not be republished) with a
  model's *self-identification* (a trailer naming the actor — is the record's subject).** R3 could
  not have found it: on the transcript surface the `model` field is instrumented, so the two jobs
  never collide there.
- **W-2.** `measured_fraction` came out **0.4 on all five model buckets, identically**, and 0.2 on
  `model-unavailable` — which differs *because* the model is unavailable, so the figure partly
  restates its own grouping key. R3 forbade a per-agent figure for ranking model choice and replaced
  it with one it did not check for the same class of defect.
- **W-3.** `measured` does not mean trustworthy. Provenance says how Witness got a value, author says
  who wrote it, **neither says whether the observed party could choose it.** `GIT_AUTHOR_DATE` sets
  `started_at` to anything — and the proof is that this repository's own regression test forges two
  timestamps to build its fixture. Not fixed: a third axis on the record type is a spec decision.
- **W-4.** Found by the *second half* of requirement 4.1's test: changing a matrix entry's reason and
  nothing else produced a **byte-identical report**. The report read `entry.capability` and nothing
  else from the matrix; every reason in the output came from records built under the old matrix. A
  report claiming to derive from "records plus matrices" that was a function of records alone — this
  repo's dominant failure mode in miniature. **Fixed**, and the fix produced `matrix_disagreement`,
  a check no round reasoned its way to: the report now states where a surface's own declaration and
  its records disagree. **Zero disagreements over the real corpus**, which is the right answer.
- **W-5.** `oldest_observable` — the whole content of requirement 2.9 — used `min()` over ISO-8601
  **strings**, and the corpus carries **two offsets in one history (2,761 at `+01:00`, 68 at `Z`)**.
  Measured: lexical and temporal answers agree here. Latent, not live. **Fixed anyway**, with a
  regression test built from a two-commit history git itself normalises into mixed offsets.
- **W-6.** **A commit is not a turn**, and the capability matrix has no slot in which to say so. The
  surface passes every structural check while counting the wrong noun; every completeness ratio has
  an unvalidated denominator.
- **W-7.** Above.
- **W-8, self-inflicted and recorded as evidence about the rounds.** The reader's first draft emitted
  `"unmapped_types": 0` where the truth is *not applicable* — the exact "found none vs did not look"
  error task 3.9 forbids, **committed by the session that wrote task 3.9, three hours later, in the
  first surface it built.** Now `null`, with a test asserting the null rather than the note.

**What the drive did not falsify**, stated because a drive that falsifies nothing was not looked at
hard enough: the four provenance states held; `derived` earned its place on first contact
(`cost_usd` ran, found inputs unmeasured, returned unavailable naming the input on all 2,829
records, never partially derived); the closed surface list held on all three negative paths, with
the no-surface case checked on **both** halves — non-zero exit *and* the output file not created;
and `conditional` was right — 1,699 one way, 1,130 the other, in one surface in one repository.

### Verification

- `py -3.11 -m unittest tests.test_witness` → **44 tests, OK**. Two failures were hit and fixed
  during the run, not worked around: W-4 (caught by its own test) and the W-5 test's expectation,
  where git normalises the `+00:00` it was given back out as `Z` — the mixed-offset history the test
  exists for, produced by git itself.
- `openspec validate --changes --strict` in witness → **1 passed, 0 failed**, after the tasks.md
  amendment.
- Drive re-run after both fixes: 2,829 records, 0 unparseable, 0 matrix disagreements,
  `oldest_observable` 2026-03-07T18:05:04Z.
- Task 5.4's check, run: `git log --stat -1` on the witness commit contains no path under
  `corpus/`, `drive-output/` or `*.transcript.jsonl`. `drive-output/` holds the run's records and
  stays gitignored.
- `scripts/drive/check_review_page.py` **read, not trusted**: 10 checks all ok. `findings on the
  page: 0` remains the known non-regression recorded in iteration 4 — it greps §3's markup.

### The review page

**Section 8 appended to the same page** (68,386 → 76,340 bytes); no second page. §7's lede is
corrected rather than left standing: it said *"three commits"* and *"zero implementation tasks
done"* and *"propose-then-shelve"*, all three of which this iteration falsified, so it now points
forward to §8 and says what changed. The footer's *"four overseer iterations"* → five, and
*"`witness` (proposed only)"* → both siblings driven.

### What this iteration did not do

No AgentWeave product code, no Hub, no agent turn, no web, nothing under `spec-queue/`, no write to
`STATE-sidequest.json` / `STATE-day.json` / `STATE-night.json`, and **no transcript read by any code
in the skeleton**. The witness repository still has no remote.

**Nothing in `decisions_for_user` is answered by this**, and none was added — the six OV questions
stand exactly as R3 left them.

### Queue state

**T-5 was the last item. The queue is finished and `next_action` is `null`**, which unregisters the
driver rather than spending a model invocation per firing to rediscover there is nothing to do.
