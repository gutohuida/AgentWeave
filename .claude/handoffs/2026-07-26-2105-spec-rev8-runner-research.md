# Handoff: AgentWeave 1.0 spec rev. 7 + rev. 8 applied — runner research folded into the spec

**Date:** 2026-07-26T21:05:37+01:00 · **Branch:** agentweave-1-0 · **HEAD:** 47ff679
**Previous handoff:** `.claude/handoffs/2026-07-25-2225-spec-rev6-committed.md` (chain root:
`.claude/handoffs/2026-07-25-1624-agentweave-1.0-spec.md`, original v1.0 vision + Kimi-locked decisions)
**Status:** chunk complete (rev. 7 and rev. 8 applied and validated; **uncommitted** — user has not yet said
to commit them)

## Goal

Produce and refine `specs/agentweave-1.0-spec.html` — a single self-contained, "regeneration-grade"
target-state specification for **AgentWeave 1.0**, a hub-first re-architecture deployable company-wide with
real security. The user builds 1.0 with **multiple AI agents across separate token windows**, so the spec, its
requirements index, and its task backlog are the shared memory a successor agent reads instead of a previous
agent's conversation. Depth and traceability beat brevity.

## Current state

`specs/agentweave-1.0-spec.html` is at **rev. 8** (rev. 6 was committed as `47ff679`; **rev. 7 and rev. 8 are
applied but uncommitted** — `git diff --stat` shows 52 changed lines in the file). Validator passes:
tags balanced, anchors resolve, ids unique, FRs 118 body = 118 index, sections 0–17, **86 tasks
(T-001…T-111, non-contiguous by design)**, **17 Q rows**, 167 knob-like rows. The RFC keyword/class grep
(`grep -c 'must not">must<\|must">must not<'`) returns exactly **1** (the legitimate §0.2 legend).

The document's status line still reads `Status: Draft — Target State`. §17: approval requires Q-1…Q-4 and Q-6
resolved plus explicit sign-off in the changelog; **implementation beyond M0 must not begin** until then.
No code has been written — nothing in `src/` or `hub/` touched.

### What happened this session

1. Resumed from the rev. 6 handoff; tree matched exactly (no drift). User deferred all pending housekeeping
   decisions ("nothing yet" / "leave as-is" for `validate_spec.py`, `.claude/handoffs/`, and the v0.x spec
   edits).
2. User asked for competitive research before reviewing §5: "Is Opencode the best fit for this? … come with a
   strong list of pros and cons of each approach and a recommendation." Research was done (web, July 2026
   sources) across opencode, Claude Code/Agent SDK, OpenAI Codex CLI, Gemini CLI, Goose, Aider, OpenHands,
   evaluated against FR-RUN-001…008 + the locked constraints. Conclusion delivered: **stay with opencode**,
   conditionally (see Key decisions).
3. User: "Make this change on the spec" → **rev. 7** applied (runner-selection Design Decision in §5, M0 task
   T-110 runner alternates spike, gate G0 nine→ten deliverables, changelog row). Also explained Goose and
   OpenHands in chat.
4. User asked what OpenHands offers / how it differs / what we can learn. Analysis delivered; two one-line
   spec edits offered.
5. User: "Apply both. Also apply all the discoveries and ideas in the spec." → **rev. 8** applied (15 edits,
   see below).

### What changed in rev. 7 (all in `specs/agentweave-1.0-spec.html`)

- §5 gained a second Design Decision block, "Runner selection: opencode, conditionally (evaluated 2026-07)":
  the competitive summary, why each alternative was rejected, three binding conditions (version pinned per
  image with deliberate upgrades; FR-RUN-001…008 held as a runner contract with opencode as the reference
  implementation behind `sandbox-init`; empirical comparative verification before M1). Codex CLI designated
  the fallback candidate.
- New M0 task **T-110** (runner alternates spike: same representative tasks headless under opencode, Codex
  CLI, Goose, verbatim logs → `specs/decisions/runner-selection.md`; deps T-003).
- Gate G0 text: "all nine deliverables — eight decision records…" → "all ten … nine decision records…".
- Changelog row rev. 7.

### What changed in rev. 8 (OpenHands competitive study applied)

- **`FR-ARCH-007` amended in place: four → five instruction layers.** New layer 3 = **Repository
  instructions** (e.g. `AGENTS.md`, versioned in git, changed by any committer via code review), placed
  *between* project (2) and role (4); role→4, agent→5. Requirement now includes the trust note: repo layer
  is least-trusted (agent itself can edit it) so it sits below Hub-controlled layers; runner reads these
  files natively whether acknowledged or not. Index row and T-106 updated to "five-layer". (Changelog rows
  for revs ≤6 still say "four-layer" — historical, intentionally untouched.)
- **T-001** — sandbox survey now includes the OpenHands runtime as prior art (controller↔sandbox agent-server
  protocol, image management, pause/resume, action/observation event stream).
- **T-003** — inventory now includes lifecycle hooks / tool-call interception points (pre/post tool use).
- **T-006** — approval survey now includes OpenHands confirmation mode + LLM-based security risk classifier.
- **T-020** — event vocabulary must survey the OpenHands action/observation event stream before freezing.
- **T-110** — per-candidate record list gained "tool-call interception or lifecycle-hook capability".
- **T-111** (new, M7, deps T-075) — continuity evaluation harness: same tasks uninterrupted vs
  interrupted-with-checkpoint-resume, quality scored; metric + threshold recorded at
  `specs/decisions/continuity-eval.md`.
- **Q-17** (new) — event-triggered jobs (event-bus filters à la OpenHands automations) as a post-1.0
  candidate; 1.0 ships cron-only; T-020 keeps the vocabulary trigger-agnostic.
- Changelog row rev. 8.

## Files touched

- `specs/agentweave-1.0-spec.html` — rev. 7 (+4 edits) and rev. 8 (+15 edits) applied via Python patch
  scripts. **UNCOMMITTED** (` M` in git status). Patch scripts `patch_rev7.py` / `patch_rev8.py` were
  written to repo root, run, then deleted (same pattern as previous sessions' scratchpad scripts).
- `.claude/handoffs/2026-07-26-2105-spec-rev8-runner-research.md` — this file (new, untracked).
- `.claude/handoffs/LATEST.md` — overwritten to point at this file (untracked).

**Dirty/untracked but NOT touched by this session** — do not attribute to rev. 7/8:

- `specs/agentweave-spec.html` — ` M`, pre-existing v0.x edits from 2026-07-24, never reviewed.
  User decision 2026-07-26: **"Leave it."**
- `kimi-export-session_-20260725-135928.md` — `??`, pre-existing source material, deliberately uncommitted.
- `validate_spec.py` — `??`, the spec checker in repo root. User decision 2026-07-26: **"Nothing yet"** (not
  committed, not deleted). Run it after every spec edit round: `python validate_spec.py`.
- `.claude/handoffs/` — `??`. User decision 2026-07-26: **"Leave as-is"** (untracked, not gitignored;
  `.claude/` IS tracked in this repo so handoffs keep showing in `git status`).

## Key decisions

### Made this session

1. **Runner stays opencode, conditionally** (now §5 Design Decision, rev. 7). Research conclusion: no
   alternative combines provider-agnostic config (75+ providers via models.dev), first-class headless
   sessions (`--session`/`--continue`/`--fork`, `session export/import`), structured streaming
   (`run --format json` + SSE), and a server/SDK mode (`opencode serve`, JS/Python SDKs, `run --attach`)
   matching the Hub-driven control model — with an embeddable license (MIT). Three binding conditions:
   (1) pin the version per image, upgrades are deliberate validated events (opencode ships ~daily, 3.7k open
   issues); (2) FR-RUN-001…008 is a runner *contract* written against capabilities — a runner swap touches
   `sandbox-init` only; (3) verify empirically and comparatively before M1 (T-110), not from vendor docs.
2. **Codex CLI is the designated fallback** — Apache-2.0, Rust static binary, strong headless
   (`codex exec --json`, `exec resume`), OS-level sandbox; loses on multi-provider neutrality
   (OpenAI-first) and Hub-driven control surface (no server mode; app-server/JSON-RPC immature; no headless
   fork — openai/codex#11750).
3. **Rejected runners, with reasons** (do not re-propose without new evidence):
   - Claude Code / Agent SDK: closed source, Anthropic-only models (violates FR-RUN-004), ToS restricts
     embedding in third-party products. Keep as the *quality benchmark* only.
   - Gemini CLI: Gemini-first; provider-agnosticism is not a goal.
   - Goose (Block → Linux Foundation AAIF, Apr 2026; Apache-2.0, Rust, MCP-native,
     `goose run --output-format stream-json`): philosophically closest match (MCP is its extension model)
     but ~¼ of opencode's community, no server mode, recipe/session model needs adaptation. **Included in
     T-110 as the third candidate** — worth measuring, not betting on blind.
   - Aider: interactive pair-programmer, no server mode, no real MCP client, weak permission model. Not an
     unattended execution engine.
   - OpenHands: **not a runner — a competing architecture** (controller + per-task Docker sandbox + REST
     control plane ≈ AgentWeave's Hub + §6). Adopting it replaces §5/§6 rather than implementing them.
     Useful as prior art only (fed rev. 8).
4. **Repo-resident instruction layer added at position 3, below role/agent** (rev. 8, FR-ARCH-007). Reason:
   the spec's conflict rule is "more specific layer governs" — putting repo files innermost would let a
   committer-controlled (and agent-writable) file outrank operator-controlled instructions. **Flagged to the
   user as a judgment call** — reversible with a two-line reorder; user has not yet confirmed.
5. **Event-triggered jobs deferred to post-1.0** (Q-17). 1.0 ships cron-only; the event vocabulary is kept
   trigger-agnostic so the feature stays additive. OpenHands automations validate the demand.
6. **Continuity evaluation harness is a new M7 task** (T-111), not M0 — it needs the built system
   (deps T-075). It defines the metric G6's end-to-end handoff test only samples: uninterrupted vs
   checkpoint-resumed task completion quality.

### Locked earlier, still binding (do not re-litigate)

From the Kimi session: opencode-only runner (native CLIs and `claude_proxy` dropped; forking opencode is a
non-goal); orchestrator interface with a Docker backend, Kubernetes designed-for but out of scope;
single-user mode is the same Hub via docker-compose; graph = directed communication topology enforced at
send time, **no workflow engine**; stack stays Python/FastAPI + React/TS + Python CLI on PyPI, SQLite default,
PostgreSQL for company deployments; RBAC-ready granular model.

From rev. 5: Apache-2.0 for 1.0 artifacts (`FR-CORE-005`); per-project `open` (default) / `gated` graph mode
(`FR-GRAPH-007`); `provider_egress` per-profile knob, `direct` first (M2), `hub_proxy` later (T-087); PyPI
name stays `agentweave-ai` shipping 1.0.0 as semver major with a `release/0.x` maintenance branch
(`FR-MIG-003`).

From rev. 6: product name "the Weave" for the UI surface only (data model keeps graph/node/edge); subgraph =
named node subset, no edge namespace, no effect on reachability; `is_admin` removed (AccessRole /
RolePermission / RoleAssignment, nullable `project_id`, permissions recomputed per request); fine-grained
tokens only, never exceeding owner, intersected at use time, mandatory bounded expiry; hop budget stays on
the thread, edges carry stateless `hop_limit`/`max_depth` clamps (**flagged reversible**); "project" NOT
renamed to "workspace"; JSON columns, no second datastore; job-fired messages are `system`; approval
deadlines escalate, never auto-decide; externally-built images framed now (`FR-SBX-010`), built later;
`AccessRole` (authorization) and `RoleTemplate` (behavior) stay separate.

### Working agreement on review cadence (still in force)

Batch review findings at section boundaries or every ~8–10 findings; **except** premise-breaking structural
findings, which go immediately. Annotation format: section/FR-ID anchor, what is wrong, what is wanted
instead (say explicitly when you don't know — those get an AskUserQuestion, not a guess).

## Constraints and user directives (verbatim)

From this session:

- "Is Opencode the best fit for this? I want you to do a research on what is being used, what is good, what
  is not recommended and come with a strong list of pros and cons of each approach and a recommendation"
- "Make this change on the spec."
- "Apply both. Also apply all the discoveries and ideas in the spec."
- Housekeeping decisions via AskUserQuestion (2026-07-26): `validate_spec.py` → "Nothing yet";
  `.claude/handoffs/` → "Leave as-is"; `specs/agentweave-spec.html` v0.x edits → "Leave it"; next work →
  "nothing yet".
- "I'm about to review chapter 5 (Opencode)." — the user's review position at handoff time.

From earlier sessions (still binding):

- "we need a task to research everything from opencode to see every cli flag, how to use, anything that we
  can take advantage for implementation. We should also test all of those to see if they work and how they
  work in our environments. **Do not assume anything.**"
- "The same for coding we need to test things and not assume they just work, not only testing of wrinting
  test for code quality but also executing and seeing what happens"
- "I want to keep the nature of A2A communication and workflow I don't want it to become just another crewAI
  or n8n."
- "What kind of security knobs should we have? We should have a exhaustive list of those in the spec. Knobs
  for containers and users of the hub"
- "how to use machines from the main cloud services providers... this should be research for all the main
  cloud providers and **create a process for each one of those**"
- "I'll be using multiple agents to build this because I have token plans and they might run out and I need
  to delegate the work to other agents so we need a way to keep track of the work being done"
- "I want to be able to tune the security all sorts of ways of the images."
- "The company is very big. 800M in profits last year. But we can start small and expand but we will
  definetly need FULL RBAC in the future for sure. So we got prepare for that."
- "Feel free to disagree in some points and push back. But show me your resoning behind it."
- "commit this changes to the spec in this branch" (was the rev. 6 instruction — **does not automatically
  extend to rev. 7/8; ask before committing**)

Project rules from `CLAUDE.md`: templates via `get_template()`; all saves pass through `validator.py`; all
task modifications use `with lock("name"):`; never commit `.agentweave/tasks|messages|agents`,
`session.json`, `transport.json`, `kimichanges.md`, `kimiwork.md`.

Environment instruction: "Do not call the AgentTool unless the user requested it" — no subagents were
spawned this session, deliberately.

## Dead ends

- **G0 anchor mismatch in patch_rev7.py (one failed run).** The anchor "all nine deliverables — eight
  decision records plus the opencode empirical matrix" matched 0 times because the file text is "all nine
  deliverables **merged** — eight decision records plus the opencode empirical" **with a line wrap** before
  "matrix". The patch script exits before writing on any anchor failure, so no partial state resulted — that
  pattern (verify-then-write, single pass) is worth keeping. Lesson: grep the exact bytes (`| cat -A`) before
  writing anchors that span formatting.
- Carried from previous sessions, still true:
  - **Bash heredoc for large HTML payloads fails** (`unexpected EOF` despite quoted delimiter). Use a Python
    patch script written with `Write`, then `python <script>.py`.
  - **Python string-literal trap in patch scripts:** inside single-quoted literals, `''' + X + '''`
    terminates the string; concatenate with `' + X + '`. The SyntaxError location is nowhere near the cause.
  - **Entity vs literal characters in anchors:** the spec has literal UTF-8 em dashes (`—`) in prose but
    `&#8212;`/`&#8230;` entities in some table cells and changelog rows. Verify with `grep | cat -v`.
  - **RFC keyword/class inversion:** mechanical grep only catches class/text mismatches, not semantic double
    negatives. Read hand-edited normative sentences aloud.
  - **Whole-document generation in one subagent call** produced a truncated file. Section-at-a-time with
    validation between rounds is what works.

## Verification

**Ran and passed** — after each revision:

```
python patch_rev7.py   # OK: applied 4 edits
python patch_rev8.py   # OK: applied 15 edits
python validate_spec.py
# OK
#   tags balanced, 0 unclosed; anchors resolve; ids unique
#   FRs: body=118 index=118 (match)
#   h2 sections: [0..17]
#   tasks: 86 unique (T-001..T-111); Q rows: 17; knob-like rows: 167
grep -c 'must not">must<\|must">must not<' specs/agentweave-1.0-spec.html   # → 1 (the §0.2 legend)
```

Also spot-read the amended FR-ARCH-007 block: layer table renders 1–5 in order (platform, project,
repository, role, agent) with the trust note in place.

**NOT tested — do not claim otherwise:**

- The file has **never been opened in a browser** across any session. Rendering, sticky TOC, scrollspy,
  mobile drawer, dark mode, and specifically the new §5 Design Decision block, the five-layer FR-ARCH-007
  table, and the new M0/M7 task rows are visually unverified.
- No test suite, ruff, black, mypy, or pytest was run — nothing in `src/` or `hub/` was touched.
- The user has reviewed roughly §0–§4.6 across earlier rounds. **§5 onward has never been approver-reviewed**
  — and §5 now contains the rev. 7 runner-selection block the user has only seen summarized in chat.
- The competitive research (runner feature claims, star counts, license readings, Goose/OpenHands details)
  comes from secondary web sources dated 2026-05…07, not from running the tools. That is exactly what
  T-003/T-008/T-110 exist to verify. Per FR-DEV-002, none of it is "verified" until executed.

## Git state

- Branch: `agentweave-1-0` (main branch for PRs is `master`). HEAD: `47ff679` (rev. 6 commit).
- **No upstream configured** — nothing pushed.
- Working tree:
  - ` M specs/agentweave-1.0-spec.html` — **rev. 7 + rev. 8, uncommitted** (52 changed lines vs HEAD).
  - ` M specs/agentweave-spec.html` — pre-existing v0.x edits, not this session's, user said leave it.
  - `?? kimi-export-session_-20260725-135928.md` — source material, deliberately uncommitted.
  - `?? validate_spec.py` — the checker, user said "nothing yet".
  - `?? .claude/handoffs/` — user said "leave as-is".

## Next steps

1. **Ask the user whether to commit rev. 7 + rev. 8** (same pattern as rev. 6, which was committed on
   explicit instruction). Suggested message shape: "Apply runner-selection decision and OpenHands study to
   the 1.0 spec (draft, rev. 8)". Do not commit without explicit confirmation.
2. **User reviews §5 (their stated position: "I'm about to review chapter 5")** — now including the rev. 7
   runner-selection Design Decision. Apply their annotations as the next revision via patch script →
   `python validate_spec.py` → RFC grep → changelog row, per the batched-review working agreement.
3. When they reach §3.3, **flag the repo-layer precedence judgment call** (Key decisions #4 this session)
   for explicit confirmation or reversal.
4. Housekeeping remains deferred by user choice: `validate_spec.py` (nothing yet), `.claude/handoffs/`
   (leave as-is), v0.x `specs/agentweave-spec.html` edits (leave it). Do not re-ask unprompted.
5. Still-open user-level questions (unchanged from rev. 6 handoff, none answered yet): Q-14 (reference cloud
   provider — gates 1.0, reorders M8), Q-13 (`reply=allowed` edge default), whether the company's git forge
   issues per-repo short-lived write tokens (constrains M1), and the rev. 6 `hop_limit`-as-edge-clamp
   deviation (flagged reversible).
6. Pending git mutations, both needing explicit confirmation: swap `LICENSE` MIT → Apache-2.0 per
   `FR-CORE-005` (affects v0.x too); tag final v0.x commit `v0.42.0` at `843e5d1` + create `release/0.x`
   per `FR-MIG-003`.
7. Only after spec approval: start M0 — T-003, then T-008, then T-009, then the new T-110 (runner spike).
   Gate G0 requires ten deliverables (nine decision records + the opencode empirical matrix).

## Open questions for the user

- **Commit rev. 7 + rev. 8?** They are validated but uncommitted; rev. 6 was committed on explicit
  instruction and no equivalent instruction has been given for these.
- **Repo-layer precedence (rev. 8):** repository instructions sit at layer 3, below role (4) and agent (5),
  because they are the least-trusted, agent-writable source. Confirm or reverse.
- Carried unanswered from the rev. 6 handoff: Q-14 cloud provider; Q-13 edge default; git forge token
  capability; `hop_limit` clamp deviation; plus the three housekeeping items the user deferred on 2026-07-26
  ("nothing yet" / "leave as-is" — do not re-ask unprompted).

## Read on resume

- `specs/agentweave-1.0-spec.html` — the deliverable. Read §0.5 changelog (8 revisions; rev. 7 and rev. 8
  rows are the authoritative summary of this session), then §5 (runner selection + T-110 context) and §17.
  Do **not** read it whole — it is ~3,900 lines.
- `validate_spec.py` (repo root) — run `python validate_spec.py` after every spec edit round; pair with
  `grep -c 'must not">must<\|must">must not<' specs/agentweave-1.0-spec.html` (must return exactly 1).
- `.claude/handoffs/2026-07-25-2225-spec-rev6-committed.md` — rev. 6 detail (RBAC/tokens/subgraphs/Weave
  decisions, full verbatim constraint list).
- `.claude/handoffs/2026-07-25-1624-agentweave-1.0-spec.md` — chain root: original v1.0 vision and the four
  Kimi-locked decisions.
- `kimi-export-session_-20260725-135928.md` (repo root, untracked) — the user's original vision statement
  and the four AskUserQuestion decisions, verbatim.
- `CLAUDE.md` — project rules (validator, locking, templates, never-commit lists).
