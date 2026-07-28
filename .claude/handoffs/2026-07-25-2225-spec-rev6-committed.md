# Handoff: AgentWeave 1.0 spec rev. 6 — second review pass applied and committed

**Date:** 2026-07-25T22:25:25+01:00 · **Branch:** agentweave-1-0 · **HEAD:** 47ff679
**Previous handoff:** `.claude/handoffs/2026-07-25-1918-spec-rev5-review-pass.md` (and before it
`.claude/handoffs/2026-07-25-1624-agentweave-1.0-spec.md`, which holds the original v1.0 vision and the four
Kimi-session locked decisions)
**Status:** chunk complete (rev. 6 applied, validated, and committed; spec still an unapproved draft, still never
opened in a browser)

## Goal

Produce and refine `specs/agentweave-1.0-spec.html` — a single self-contained, "regeneration-grade" target-state
specification for **AgentWeave 1.0**, a hub-first re-architecture. The user demoed AgentWeave at their company's
tech summit ("everybody went nuts for it") but the v0.x local-first design is "hardly usable company wide". 1.0
moves state and control into the Hub, runs agents in Docker sandboxes, and is meant to be deployable company-wide
with real security.

The *why* behind the document's depth: the user intends to build 1.0 using **multiple AI agents across separate
token windows** (their plans run out), so the spec, its requirements index, and its task backlog are the shared
memory a successor agent reads instead of a previous agent's conversation. Depth and traceability beat brevity.

## Current state

`specs/agentweave-1.0-spec.html` is at **rev. 6**, **committed** as `47ff679`. It is 3,877 lines / ~400 KB:
18 sections (§0–§17), **118 requirement IDs**, **84 backlog tasks** (IDs run T-001…T-109 but numbering is *not*
contiguous — 25 IDs are unused because tasks were allocated in per-milestone blocks; do not treat a gap as a
missing task), 16 open questions, 43 sandbox security knobs, 6 changelog revisions.

The document's own status line still reads `Status: Draft — Target State`. §17 states approval requires Q-1…Q-4
and Q-6 resolved plus an explicit sign-off recorded in the changelog; until then **implementation beyond M0 must
not begin**. No code has been written in any session — the spec is a document, nothing in `src/` or `hub/` has
been touched.

### What happened this session

The user resumed, then delivered a batch of **16 review annotations** covering §3.3 through §4.6, ending with
"Feel free to disagree in some points and push back. But show me your resoning behind it." I read the relevant
spec sections, responded item by item with reasoning and explicit pushback on four of them, and asked three
decisions via AskUserQuestion. **All three took the recommended option:**

1. **Graph product name = "the Weave"** (data model keeps `graph`/`node`/`edge`).
2. **Subgraphs = named subset of the one graph** (not nested containers with their own edges).
3. **Apply all 16 items as a single rev. 6** (rather than splitting across two revisions).

Then rev. 6 was written via a patch script, validated, and committed.

### The single most important finding

The user's `is_admin` objection exposed a **genuine internal contradiction**: §8.2 `FR-AUTH-005` already
forbade branching on `is_admin` and `FR-AUTH-004` already mandated roles as mapping-table rows, while §4.2
simultaneously defined `User.is_admin` as a bool and `Membership.role` as an enum. §4 was the wrong one. Fixed
in rev. 6 — see Key decisions.

## What changed in rev. 6 (all in `specs/agentweave-1.0-spec.html`)

**15 new requirements** (103 → 118):

| ID | Subject |
|---|---|
| `FR-ARCH-007` | Four-layer instruction composition (platform → project → role → agent) with visible layer boundaries |
| `FR-AUTH-007` | Roles as data: `AccessRole` / `RolePermission` / `RoleAssignment`, nullable `project_id` |
| `FR-AUTH-008` | Fine-grained tokens: never exceed owner, intersected at use time, mandatory bounded expiry |
| `FR-AUTH-009` | Token lifecycle: issue, approve, display-once, inventory, rotate, revoke, expire |
| `FR-DOM-009` | Principal kinds (`human`/`agent`/`system`) on messages, events, audit records |
| `FR-DOM-010` | Job execution policies: catch-up, overlap, max concurrency, jitter |
| `FR-GRAPH-008` | Subgraphs as named node subsets |
| `FR-GRAPH-009` | Three-scope limits; node/edge clamps tighten but never loosen project values |
| `FR-HUB-012` | Operational telemetry: `trace_id` propagation, structured logs, OTLP, metric set |
| `FR-HUB-013` | Append-only audit log, never sampled, SIEM-exportable |
| `FR-HUB-014` | Single redaction filter on every write path, proven by a leak test |
| `FR-HANDOFF-005` | Approver sets, quorum, self-approval bar, deadline escalation, delegation, policy gating |
| `FR-SBX-010` | Externally-built image contract, digest pinning, provenance, conformance check |
| `FR-ROLE-005` | Role template name + short/long descriptions, roles management surface |
| `FR-UI-008` | The Weave surface naming and subgraph rendering/filtering/seed-work |

**4 new sections:** §1.3 Concepts & usage model · §4.4.5 Subgraphs · §8.8 Token administration ·
§8.9 Observability, logging & audit.

**Schema changes:** `User.is_admin` **removed**; `Membership.role` enum → `role_id` FK; `APIKey` gained
`project_ids`, `resource_grants`, `approval_state`, `revoked_at`/`revoked_by`, and `expires_at` became
**required**; `Message` gained `sender_kind` + `sender_ref`; edge attributes gained `hop_limit` + `max_depth`;
`RoleTemplate` gained `name`, `description_short`, `description_long`.

**Amended in place:** `FR-AUTH-005` (rewritten — it referenced `is_admin`, which no longer exists);
`FR-DOM-008` (job-fired messages now `sender_kind=system` / `sender_ref=job:<id>`, no longer the false
sender `user`); `FR-UI-007` admin-surface table gained "Access roles" and "API tokens" rows; §9.2 heading
renamed "Graph editor" → "The Weave (graph editor)".

**12 new tasks:** T-098 (RBAC schema), T-099 (tokens), T-100 (subgraphs), T-101 (graph clamps),
T-102 (observability), T-103 (approval policy), T-104 (principal kinds + job policies), T-105 (role
descriptions/UI), T-106 (instruction composition), T-107 (Weave UI), T-108 (external images),
T-109 (docs rework). All twelve slots T-098…T-109 are used; verified with a uniqueness scan.

## Files touched

- `specs/agentweave-1.0-spec.html` — rev. 6 applied (+55 KB, 3,285 → 3,877 lines). **COMMITTED** in `47ff679`.
  Clean in `git status`.
- `.claude/handoffs/2026-07-25-2225-spec-rev6-committed.md` — this file (new, untracked).
- `.claude/handoffs/LATEST.md` — overwritten to point at this file (untracked).

Scratchpad only (ephemeral, safe to lose):
`C:\Users\huida\AppData\Local\Temp\claude\C--Users-huida-Documents-projects-AgentWeave\fe30061c-b176-447a-a3ac-a3bdcf4dd25b\scratchpad\`
contains `patch_rev6.py` (the applied patch script, 53 edits) and `rev5_backup.html` (the pre-rev-6 spec).

**Dirty/untracked but NOT touched by this session** — do not attribute these to rev. 6:

- `specs/agentweave-spec.html` — ` M`, 306 insertions / 123 deletions. Pre-existing v0.x "rev. 2 exhaustiveness
  pass" dated 2026-07-24, made before any 1.0 session. Never reviewed in any of these sessions. **Still needs a
  decision.**
- `kimi-export-session_-20260725-135928.md` — `??`, pre-existing source material (1,141 lines). `CLAUDE.md`
  forbids committing `kimichanges.md`/`kimiwork.md`; this is the same category. Left uncommitted deliberately.
- `validate_spec.py` — `??`, created in the rev. 5 session, lives in the repo root. **Run it after every spec
  edit round:** `python validate_spec.py`. Not committed — see Open questions.
- `.claude/handoffs/` — `??`. Note **`.claude/` IS tracked in this repo** and handoffs are **not** gitignored
  (verified with `git check-ignore`), so they will keep appearing in `git status` until either committed or added
  to `.gitignore`.

## Key decisions

### Locked earlier, still binding (do not re-litigate)

From the Kimi session: opencode-only runner (native CLIs and `claude_proxy` dropped; forking opencode is a
non-goal); orchestrator interface with a Docker backend, Kubernetes designed-for but out of scope; single-user
mode is the same Hub via docker-compose, no divergent local path; graph = directed communication topology
enforced at send time, **no workflow engine**; stack stays Python/FastAPI + React/TS + Python CLI on PyPI,
SQLite default and PostgreSQL for company deployments; two auth roles now but an RBAC-ready granular model.

From rev. 5: Apache-2.0 replaces MIT for 1.0 artifacts (`FR-CORE-005`); per-project `open` (default) / `gated`
graph mode (`FR-GRAPH-007`); `provider_egress` per-profile knob with `direct` first (M2) and `hub_proxy` relay
later (T-087); PyPI name stays `agentweave-ai` shipping 1.0.0 as a semver major, with a `release/0.x`
maintenance branch (`FR-MIG-003`).

### Decided this session

1. **Product name "the Weave" for the UI surface only.** The data model, REST paths, MCP tools and this spec
   keep `graph`/`node`/`edge`. Rejected: renaming the data model (103 FRs and all test names use it; precision
   loss), "Workflow" (the exact word n8n/Temporal/CrewAI use for deterministic step execution — sets precisely
   the expectation the positioning rejects), "Weaver" (reads as an actor, colliding with agents).
   `FR-UI-008` also reserves *thread* for message conversations and forbids reusing it for graph concepts.
2. **Subgraph = a named subset of nodes in the one graph** (`FR-GRAPH-008`). Edges belong to the graph; a
   subgraph has no edge namespace, no ports, no execution boundary, and **must not** affect reachability or ACL
   evaluation. "Run a subgraph" means only: seed a task/message at member nodes. Rejected: nested containers with
   internal edges and an input/output interface — those are exactly the primitives a workflow engine is built
   from, and once they exist conditional routing between them is the obvious and reasonable next request, which
   would violate `FR-GRAPH-001`.
3. **`is_admin` removed entirely, not deprecated** (`FR-AUTH-007`). Three tables: `AccessRole` (nullable
   `project_id`), `RolePermission` (one row per permission — the role *is* these rows), `RoleAssignment`
   (nullable `project_id`, where `null` = Hub-wide). Effective permissions = union of Hub-wide and
   project-scoped grants, **recomputed per request**, never cached in a session or token. Rejected: keeping the
   bool with a migration path — a bool cannot express "admin of project A, member of project B", which the
   deployment target needs.
4. **Fine-grained tokens only; no classic broad PATs** (`FR-AUTH-008`). Rejected the GitHub two-tier model
   explicitly: it is a migration artifact, and shipping both means shipping the insecure default then deprecating
   it for years. Core rule: a token can never carry a permission its owner lacks, and the intersection is
   computed **at use time**, so revoking a role instantly defangs every token that user holds. Expiry is
   mandatory and bounded by `max_token_ttl_days`.
5. **Hop budget stays on the thread; the edge carries a stateless clamp** (`FR-GRAPH-009`). This *deviates from
   the user's annotation*, which asked for the hop budget to be an edge configuration. Reasoning given: an edge
   cannot know how far a message has already travelled, so a budget cannot live there; instead `hop_limit` is a
   predicate over the message's current `hop` evaluated at send time. Delivers the intent ("escalation edges only
   carry fresh threads") with no per-edge state, no ambiguity when a thread crosses several edges, and no way for
   an edge to grant *more* budget than the project allowed. **Flagged to the user as reversible** — it is
   `FR-GRAPH-009` plus two rows in the §4.4.2 edge attribute table.
6. **"Project" kept; NOT renamed to "workspace."** Pushed back: *workspace* is already the normative name for a
   sandbox's on-disk working copy of code (§6.6, `FR-WS-001…006`), and reusing it for the tenancy boundary would
   put two unrelated concepts behind one word in a document meant to be implemented literally. What was actually
   missing was the *concept*, not the name — hence new §1.3.
7. **No second datastore; JSON columns instead of NoSQL.** Pushed back on the user's suggestion. Reasoning: the
   candidates are not document workloads (`Checkpoint` is highly structured; `RoleTemplate` is a `content`
   string plus a `format` enum), and a second engine costs backup/restore/migration/security/monitoring plus
   loss of FKs and cross-store transactions, and complicates the locked single-user docker-compose story.
   Postgres JSONB and SQLite JSON1 give schemaless where it is genuinely wanted (knob objects, event `data`).
8. **Job-fired messages are `system`, not `user`** (`FR-DOM-009`). Rejected simply picking a different agent as
   sender: the issue is that recording automation as a human makes the audit trail state something false.
9. **Approval deadlines escalate; they never auto-decide** (`FR-HANDOFF-005`). Auto-approve converts an
   unattended queue into unreviewed production changes; auto-reject silently discards finished work. Same
   reasoning as the handoff default (`FR-HANDOFF-003`): when unsure, hold and tell a human.
10. **Externally-built images: frame now, build later** (`FR-SBX-010`). The contract, digest pinning and
    provenance record cost almost nothing now and are the hard-to-retrofit parts; signature verification and a
    registry allowlist are explicitly deferrable past 1.0.
11. **Two things called "role" stay separate.** `AccessRole` = authorization (what a human may do);
    `RoleTemplate` = behavior (how an agent works). Separate tables, separate permissions (`member:manage` vs
    `role:manage`), separate UI; implementations must not merge them.

### Working agreement on review cadence (established this session)

The user asked whether to send review findings one at a time or in bulk. Recommended and adopted: **batch at
section boundaries or every ~8–10 findings**, because per-round overhead (re-orientation, validation, changelog
row) is fixed and batching lets interacting findings be seen together — **except** structural findings that
invalidate a premise later sections depend on, which should be sent immediately so the user does not waste
reading time reviewing against a bad premise. Annotation format that works: section/FR-ID anchor, what is wrong,
what is wanted instead (and say explicitly when you don't know what you want — those get an AskUserQuestion
rather than a guess).

## Constraints and user directives (verbatim)

From this session:

- "commit this changes to the spec in this branch"
- "Feel free to disagree in some points and push back. But show me your resoning behind it."
- "We need to be aware of logging and traces of the entire project. What we're going to log, how, where?"
- "is_admin is a bad choice for the future. When we endup with multiple roles for each user this will bite us in
  the ass. Shouldn't we create a role_id column? Then a role table and maybe a permissions table or something
  like that if we don't already have it? This is future proofing the agentweave"
- "In the future I want project admin to manage tokens and permissions each token gives to what resources within
  agentweave. We should detail in the spec the token generation process and administration."
- "We need to make things thinking that in the future companies and users will generate their own secure images.
  So they can send use this image to run the agent. Not scoped for now but this will be a thing in the future so
  add this to the spec as well"
- "we only have 1 graph but we can have multiple subgraphs. You can execute them on their own for testing and
  what not but a graph can have multiple subgraphs inside it, basically making collaboration and oranization
  cleaner."
- "Multiple users in a project can each create their own graph for their necessities. Like devs and underwrites,
  or other different users responsible and knowledgeble in their own fields."
- "Agentweave base files and mds that are used today to explain how it works etc need to be completely reworked"
- "Maybe we should take a deeper look in the approval and user question to improve that. It feels lacking
  somewhat"

From earlier sessions (still binding):

- "we need a task to research everything from opencode to see every cli flag, how to use, anything that we can
  take advantage for implementation. We should also test all of those to see if they work and how they work in
  our environments. **Do not assume anything.**"
- "The same for coding we need to test things and not assume they just work, not only testing of wrinting test
  for code quality but also executing and seeing what happens"
- "I want to keep the nature of A2A communication and workflow I don't want it to become just another crewAI or
  n8n."
- "What kind of security knobs should we have? We should have a exhaustive list of those in the spec. Knobs for
  containers and users of the hub"
- "how to use machines from the main cloud services providers... this should be research for all the main cloud
  providers and **create a process for each one of those**"
- "I'll be using multiple agents to build this because I have token plans and they might run out and I need to
  delegate the work to other agents so we need a way to keep track of the work being done"
- "I want to be able to tune the security all sorts of ways of the images."
- "The company is very big. 800M in profits last year. But we can start small and expand but we will definetly
  need FULL RBAC in the future for sure. So we got prepare for that."

Project rules from `CLAUDE.md`: templates via `get_template()`, never hardcode in `cli.py`; all saves pass
through `validator.py`; all task modifications use `with lock("name"):`; never commit `.agentweave/tasks|
messages|agents`, `session.json`, `transport.json`, `kimichanges.md`, `kimiwork.md`.

Environment instruction: "Do not call the AgentTool unless the user requested it" — no subagents have been
spawned in any of these sessions, deliberately.

## Dead ends

- **Bash heredoc for large HTML payloads.** `cat >> file << 'AWEOF'` with a ~300-line HTML payload fails with
  `unexpected EOF while looking for matching` despite a quoted delimiter. Do not retry. Working approach, used
  for rev. 5 and rev. 6: write a Python patch script with `Write`, then run `python <script>.py`.
- **Python triple-quoted string bug in the patch script (cost ~2 failed runs).** In `patch_rev6.py` the
  `ui-admin-rows` block used *single*-quoted string literals that embedded `''' + MUST + '''`. Inside a
  single-quoted string, `'''` terminates it. The reported error was
  `SyntaxError: leading zeros in decimal integer literals are not permitted` pointing at `FR-ROLE-005`
  **~30 lines later** — the error location is nowhere near the cause. Rule: inside single-quoted string
  literals, concatenate with `' + MUST + '`, not `''' + MUST + '''`.
- **Entity vs literal character mismatch in patch anchors.** The spec contains **literal UTF-8 em dashes** (`—`,
  `M-bM-^@M-^T` under `cat -v`), not `&#8212;`, in prose rows. A `sub1()` anchor written with `&#8212;` matched
  zero times. Verify anchor text with `grep ... | cat -v` before assuming an entity.
- **Recurring RFC keyword/class inversion — bit again this session.** While hand-editing `FR-AUTH-005` outside
  the patch script, I wrote "and none `<span class="rfc must not">must not</span>` be reintroduced" — a double
  negative that inverts the requirement. Caught and fixed. The mechanical check
  (`grep -c 'must not">must<\|must">must not<'`) does **not** catch semantic double negatives like this, only
  class/text mismatches. Read hand-edited normative sentences aloud.
- **Two near-misses caught by review before running the patch** (both would have validated clean):
  inserting `FR-AUTH-007` before `FR-AUTH-006` (fixed by anchoring on `<h3 id="hub-secrets">` instead), and
  linking to `href="#graph-modes"`, an anchor that does not exist (changed to `#dom-graph`).
- **Kimi's approach of generating the whole document in one subagent call** produced a truncated file with no
  closing tags. Section-at-a-time authoring with a validator run between rounds is what works.

## Verification

**Ran and passed** — `python validate_spec.py`, after the patch and again after the `FR-AUTH-005` hand-edit:

```
OK
  tags balanced, 0 unclosed; anchors resolve; ids unique
  FRs: body=118 index=118 (match)
  h2 sections: [0, 1, ..., 17]
  tasks: 84 unique (T-001..T-109); Q rows: 16; knob-like rows: 167
```

Also ran: `grep -c 'must not">must<\|must">must not<' specs/agentweave-1.0-spec.html` → **1**, which is the
legitimate §0.2 RFC-2119 legend where the keywords are listed rather than used. Any value above 1 is a real bug.

`git log`/`git status` confirm `47ff679` contains exactly one file, 3,877 insertions.

**NOT tested — do not claim otherwise:**

- The file has **never been opened in a browser**, across any session. Rendering, the sticky TOC, scrollspy, the
  TOC filter box, the mobile drawer, dark mode, and specifically the four sections added this round
  (§1.3, §4.4.5, §8.8, §8.9 — the last two are dense multi-column tables) are all visually unverified.
- No test suite, `ruff`, `black`, `mypy`, or `pytest` was run — nothing in `src/` or `hub/` was touched in any
  session.
- The user has read and annotated roughly §0–§4.6. **§5 onward has never been reviewed by the user.**
- Every claim the spec makes about third-party behavior (opencode's CLI surface, Docker knob support, MCP
  streamable-HTTP details, cloud provider procedures) is **unverified by design** — that is what M0 and
  `FR-DEV-002` exist to fix. These are marked `[NEEDS CLARIFICATION]` / Open Issue in the document.

## Git state

- Branch: `agentweave-1-0` (main branch for PRs is `master`).
- HEAD: `47ff679` "Add AgentWeave 1.0 target-state specification (draft, rev. 6)".
- **No upstream configured** — `git log origin/agentweave-1-0..HEAD` returns "no upstream". Nothing pushed.
- Working tree dirty with three pre-existing items, none from this session:
  - ` M specs/agentweave-spec.html` (306 insertions / 123 deletions, v0.x spec, pre-existing)
  - `?? kimi-export-session_-20260725-135928.md` (source material, deliberately uncommitted)
  - `?? validate_spec.py` (the checker, undecided)
  - `?? .claude/handoffs/` (handoffs; `.claude/` is tracked and these are not gitignored)

## Next steps

1. **Open `specs/agentweave-1.0-spec.html` in a browser and read the four new sections**: §1.3 Concepts & usage
   model, §4.4.5 Subgraphs, §8.8 Token administration, §8.9 Observability/logging/audit. §8.8 and §8.9 are dense
   multi-column tables and are the most likely to render badly. Also confirm the §9.2 heading now reads "The
   Weave (graph editor)" and that the four new TOC entries indent at the right level (§4.4.5 is `lvl-3`, the
   rest `lvl-2`). This is the one thing the validator cannot check.
2. **Decide `validate_spec.py`** — commit it (ideally moved to `specs/validate_spec.py`), or delete it. It is
   currently an untracked loose script in the repo root and it is the only mechanical check on the spec.
3. **Decide the pre-existing `specs/agentweave-spec.html` edits** (306+/123−, v0.x spec, made before any 1.0
   session and never reviewed here) — commit separately, revert, or leave.
4. **Continue the review from §5 onward.** The user has annotated through ~§4.6 across two rounds. §5 (Runner),
   §6 (Sandbox), §7 (Gateway), §8 (Hub backend), §9 (UI), §10–§17 have had no approver review. Apply the next
   batch the same way: patch script → `python validate_spec.py` → RFC grep → changelog row.
5. **Answer the blocking open questions**: Q-14 (which cloud provider is the reference deployment target —
   reorders M8 and gates 1.0), Q-13 (`reply=allowed` as the edge default), and whether the company's git forge
   can issue per-repository short-lived write tokens (constrains M1 — the `git_credentials=read_write` grant
   assumes narrowly-scoped tokens).
6. **Pending git mutations, both needing explicit confirmation:** swap `LICENSE` from MIT
   (`Copyright (c) 2024 InterAgent Team`) to Apache-2.0 per `FR-CORE-005` — this affects v0.x too; and tag the
   final v0.x commit `v0.42.0` at `843e5d1` plus create `release/0.x` per `FR-MIG-003`.
7. **Only after approval, start M0** — T-003 (opencode capability inventory from docs, explicitly marked
   unverified), then T-008 (empirical flag matrix, run in both Windows/Docker Desktop and the Linux base image,
   verbatim output recorded under `specs/experiments/opencode/`), then T-009 (cloud target survey). Gate G0
   blocks all implementation and requires nine deliverables. After each M0 task, revise the spec and add a
   changelog row — `FR-META-001` and `FR-DEV-002` require it, and §5's Open Issue says §5 gets rewritten against
   verified behavior once T-008 lands.

## Open questions for the user

- **Q-14 — which cloud provider is the reference deployment target?** Decides which M8 provider task is built
  first; gates 1.0. The user may already know from their company's existing accounts.
- **Q-13 — keep `reply=allowed` as the edge default?** An earlier session softened the user's original "agent3
  can't communicate back" example. Reversible in one table row.
- **Can the company's git forge issue per-repository, short-lived write tokens?** If not, it constrains M1.
- **Is the `hop_limit`-as-edge-clamp design acceptable?** This deviates from the user's literal annotation
  ("hop budget should be a configuration of the edge"). Reasoning is in Key decisions #5; reversing it means
  editing `FR-GRAPH-009` and two rows in §4.4.2.
- **Should `validate_spec.py` be committed, and should `.claude/handoffs/` be gitignored?** `.claude/` is tracked
  in this repo, so handoffs currently show up in `git status` forever.
- **Should the pre-existing `specs/agentweave-spec.html` v0.x edits be committed, and by whom?**

## Read on resume

- `specs/agentweave-1.0-spec.html` — the deliverable, committed at `47ff679`. Read §0.5 changelog (6 revisions;
  the rev. 6 row is the authoritative summary of this session), then §15.2 backlog and §17 open questions. Do
  **not** read it whole — it is 3,877 lines.
- `validate_spec.py` (repo root) — run `python validate_spec.py` after every spec edit round. Pair it with
  `grep -c 'must not">must<\|must">must not<' specs/agentweave-1.0-spec.html`, which must return exactly 1.
- `.claude/handoffs/2026-07-25-1918-spec-rev5-review-pass.md` — rev. 5 detail (license, graph modes, provider
  egress, package continuity decisions).
- `.claude/handoffs/2026-07-25-1624-agentweave-1.0-spec.md` — the original chain root: full v1.0 vision, the four
  Kimi-locked decisions, and the earliest constraints.
- `kimi-export-session_-20260725-135928.md` (repo root, untracked) — the user's original vision statement
  (Turn 2) and the four AskUserQuestion decisions, verbatim.
- `CLAUDE.md` — project rules (validator, locking, templates, never-commit lists).
