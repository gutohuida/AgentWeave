# Handoff: AgentWeave 1.0 spec — full consistency scan, 28 findings, rev. 9 applied and committed

**Date:** 2026-07-26T22:30+01:00 · **Branch:** `agentweave-1-0` · **HEAD:** `d60c1e3`
**Agent:** Claude Code (Opus 5, `claude-opus-5`)
**Previous handoff:** `.claude/handoffs/2026-07-26-2105-spec-rev8-runner-research.md`
(chain root: `.claude/handoffs/2026-07-25-1624-agentweave-1.0-spec.md`, original v1.0 vision + Kimi-locked decisions)
**Status:** chunk complete — Tier 1 findings fixed and committed; **22 findings remain unapplied** (Tiers 2–5,
listed in full below so they survive this window)

## Goal

Produce and refine `specs/agentweave-1.0-spec.html` — a single self-contained, "regeneration-grade"
target-state specification for **AgentWeave 1.0**, a hub-first re-architecture deployable company-wide with
real security. The user builds 1.0 with **multiple AI agents across separate token windows**, so the spec, its
requirements index, and its task backlog are the shared memory a successor agent reads instead of a previous
agent's conversation. Depth and traceability beat brevity.

## Current state

The spec is at **rev. 9**, committed as `d60c1e3`. Working tree is clean with respect to this file.

Revisions 7 and 8 were committed this session as `51c11e5` (they had been uncommitted at the previous
handoff; the user approved committing them via AskUserQuestion before the review work started).

This session's substance was a **full read of all 3,905 lines** plus a semantic consistency scan, which
produced **28 findings**. `validate_spec.py` passed before, during, and after — every finding is semantic
drift that tag balance, anchor resolution, and ID uniqueness cannot detect. The user chose "Tier 1 +
corruption first", so **6 of 28 are fixed**; 22 remain.

Current validator state:

```
tags balanced, 0 unclosed; anchors resolve; ids unique
FRs: body=118 index=118 (match)
h2 sections: [0..17]
tasks: 86 unique (T-001..T-111); Q rows: 17; knob-like rows: 175
```

Note: knob-like rows moved 167 → 175 purely because the new Question/ApprovalDecision field rows match
`validate_spec.py`'s loose knob regex. Not a real knob-count change; do not treat 175 as the §6.5 knob total.

No code has been written. Nothing in `src/` or `hub/` has been touched in any session.

### What rev. 9 changed (all in `specs/agentweave-1.0-spec.html`, 22 edits, 143 changed lines)

1. **`FR-GW-004`** gains four runtime control-plane tools — `get_agent_config`, `report_session`,
   `report_output`, `report_session_end` — in a labelled group inside the existing tool table. Restricted to
   **sandbox-bound gateway tokens**, rejected for external-agent tokens, and they take no agent/sandbox/session
   parameter (they act on the token's binding). Accompanied by a new Design Decision (why a second REST
   namespace was rejected) and a new Open Issue (whether MCP tool-call framing suits high-volume output
   streaming — scoped so T-004/T-008 can revise the transport in §7.1 without removing the tool).
2. **`FR-RUN-002`, `FR-RUN-007`, `FR-RUN-008`** now name those tools in their algorithm steps.
3. **`FR-HUB-008`** step 2: sender changed from `user` to `sender_kind=system` + `sender_ref=job:<job_id>`,
   cross-referenced to `FR-DOM-008`/`FR-DOM-009`.
4. **`FR-HUB-008`** tail: the hardcoded "at most one catch-up run" is replaced by explicit application of all
   four `FR-DOM-010` policies, each positioned in the algorithm (jitter before claiming, overlap before
   delivery, catch_up after downtime), with "no full backfill under any policy value" kept as an invariant.
5. **`Question` entity** (§4.5) gains `approver_set`, `quorum`, `allow_self_approval`, `deadline_at`,
   `escalation_target`.
6. **New `ApprovalDecision` entity** (§4.5, IDs `dec-…`) with `question_id`, `decider`/`decider_kind`,
   `decision`, `note`, `delegated_from`, `counted`, `created_at`.
7. **`FR-DOM-005`** and **`FR-HANDOFF-004`** made quorum-aware (task stays `under_review` until the
   quorum-completing decision; barred self-approvals stored `counted=false` rather than dropped).
8. **Two truncated passages repaired** — see Dead ends for why they existed.
9. Five §14 index rows updated (`FR-RUN-002`, `FR-GW-004`, `FR-HUB-008`, `FR-HANDOFF-004`, `FR-DOM-005`) and a
   rev. 9 changelog row added.

## Files touched

- `specs/agentweave-1.0-spec.html` — rev. 9 applied via `patch_rev9.py`. **Committed** as `d60c1e3`. Clean.
- `.claude/handoffs/2026-07-26-2230-spec-rev9-consistency-pass.md` — this file (new, untracked).
- `.claude/handoffs/LATEST.md` — overwritten to point at this file (untracked).
- `patch_rev9.py` — written to repo root, run, **deleted** (same pattern as `patch_rev7.py`/`patch_rev8.py`).
- Scratchpad (outside the repo, safe to ignore):
  `C:\Users\huida\AppData\Local\Temp\claude\C--Users-huida-Documents-projects-AgentWeave\2f55514b-c5ae-4028-b46d-9a97d92c350b\scratchpad\`
  contains `deep_scan.py` (the semantic consistency scanner — **worth keeping/rerunning**, see Verification),
  `commitmsg.txt`, `commitmsg9.txt`.

**Dirty/untracked but NOT touched by this session** — do not attribute to rev. 9:

- `specs/agentweave-spec.html` — ` M`, pre-existing v0.x edits from 2026-07-24, never reviewed.
  User decision 2026-07-26: **"Leave it."**
- `kimi-export-session_-20260725-135928.md` — `??`, pre-existing source material, deliberately uncommitted.
- `validate_spec.py` — `??`, the structural checker in repo root. User decision 2026-07-26: **"Nothing yet."**
  Run `python validate_spec.py` after every spec edit round.
- `.claude/handoffs/` — `??`. User decision 2026-07-26: **"Leave as-is"** (untracked, not gitignored;
  `.claude/` IS tracked in this repo so handoffs keep appearing in `git status`).

## THE 22 REMAINING FINDINGS (unapplied — this list exists nowhere else)

Line numbers are **pre-rev-9** where noted; the file grew ~109 lines, mostly in §4.5 and §7.3, so anything
after §4.5 has shifted. Re-locate by `FR-ID` or by grep, not by line number.

### Tier 2 — contradictions and dead references (do these next)

1. **§1.2 non-goals vs `FR-UI-007`.** §1.2 says 1.0 ships "no custom-role editing surface"; `FR-UI-007` (rev. 6)
   requires an "Access roles" surface to "list, create, and edit AccessRole rows and their permission grants".
   The non-goal was never retired. Fix: amend or delete the non-goal bullet.
2. **Q-12 is resolved but sits in the open-questions table**, whose preamble says a reader "must not treat any
   of these as settled". Plus **three stale references treating it as open**: `FR-DEP-001` item 5 ("unless Q-12
   is resolved in favour of direct provider access"), the §16.4 closing note, and T-008's acceptance check
   ("Q-1, Q-7, and Q-12 resolved"). Fix: move/mark Q-12 as resolved and update all three.
3. **`max_token_ttl_days` does not exist.** Referenced as the binding ceiling in the APIKey entity (§4.2,
   `expires_at` row) and in `FR-AUTH-008` rule 3. The actual control in §8.7.2 is named **`apikey_max_ttl_days`**.
   Fix: pick one name, use it in all three places.
4. **`max_concurrent_sandboxes` is two different knobs.** §6.5(a): per **agent**, default `1`. §8.7.5: per
   **project**, default `5`. The §16.3 sizing example already has to disambiguate in prose. Fix: rename one
   (suggest `max_sandboxes_per_agent` for the §6.5 one).
5. **No SSE event exists for a refused interaction.** `FR-GRAPH-006` requires refusals as events feeding a live
   graph overlay; `FR-UI-003` item 6 and `FR-UI-008` item 4 require rendering and filtering them; `FR-GW-006`
   says a rejection "must emit an event". But `FR-HUB-007` declares the SSE vocabulary "must be exactly" its
   table, which contains no refusal event. Fix: add e.g. `interaction_refused` to the Work or Configuration
   group.
6. **§13.2 vs `FR-ARCH-007` layer 3.** §13.2 drops "Per-agent context files (`CLAUDE.md`/`AGENTS.md`/`GEMINI.md`
   generation) — no need to write files a specific vendor CLI reads", while rev. 8's layer 3 makes repo-resident
   `AGENTS.md` an instruction layer the runner reads natively. Reconcilable (we no longer *generate*; we do
   *read*) but the document never says so. Fix: one clarifying clause in the §13.2 row.

### Tier 4 — count and index drift

7. **§15.3 milestone table** says M0 delivers "**Eight** decision records plus the opencode empirical matrix";
   Gate G0 in §15.2 says "all ten deliverables merged — **nine** decision records plus…". Rev. 7 updated the
   gate and not the table.
8. **§14 index, `FR-GRAPH-003`** lists edge attributes as `reply, types, max_per_hour, label` — missing
   `hop_limit` and `max_depth`, added to the requirement in rev. 6.
9. **Glossary "Security Profile" entry and `SecurityProfile.knobs` (§4.6)** both summarize the knob set as
   ~5 items ("egress allowlist, CPU/memory, read-only rootfs, seccomp, additional MCP servers"). `FR-SBX-008`
   defines ~45 knobs across five tables.
10. **§17 Q rows are out of order**: Q-1…Q-12, then **Q-15, Q-16, Q-14, Q-13, Q-17**.
11. **§14, `FR-UI-008`** test path is `hub/ui/src/__tests__/weave.test.tsx`; every other UI row uses
    `ui/src/__tests__/`.
12. **§14, `FR-DEP-001`** summary covers 8 of the requirement's 11 items (omits "administrative access without
    open ports" and "logs off the host").

### Tier 5 — first-draft problems never addressed

13. **§0.2 conformance classes** (producer vs consumer) are defined at length and **then never used** — not one
    requirement anywhere is labelled either way. Either apply the taxonomy or drop the subsection.
14. **`FR-DOM-003`** says the Hub "**may** accept any valid status value" from any `task:write` caller, which
    makes the §4.5 lifecycle diagram decorative while the same requirement says approval-driven transitions
    "must follow the graph". Tension inherited from v0.x; needs a deliberate decision, not a wording fix.
15. **§2 Glossary has no entry for "Hub"** — the most-used term in the document. Also missing: Subgraph,
    Thread, Workspace, Artifact, ProjectResource, Weave.
16. **§2 Glossary uses `<dl>` containing `<p><dfn>`** instead of `<dt>`/`<dd>` — invalid HTML content model.
    Renders fine; structurally wrong. (This is also why `deep_scan.py` section 8 reports "glossary entries: 0" —
    the scanner looks for `<dt>`. Fix the markup and the scanner's orphan check starts working.)
17. **§0.2 legend** contains `<span class="rfc must">must not</span>` — a class/text mismatch. This is the
    single "legitimate" hit the `grep -c 'must not">must<\|must">must not<'` check tolerates. §0.3 gets the same
    thing right, so it is just a bug. **If you fix it, the expected grep count becomes 0, not 1** — update any
    instructions that assert 1.
18. **`FR-CLI-002`** command surface "must include" omits `import-v0` (required by `FR-MIG-002`), plus resources
    and subgraphs commands.
19. **`FR-GW-004` `get_checkpoint(agent?, task_id?)`** takes an arbitrary agent name — a potential end-run
    around `FR-GW-007`'s "no Agent MCP tool may reveal the existence of agents the caller cannot reach".
20. **`FR-GW-004` `log_event(event_type, data?, severity?)`** lets an agent write arbitrary events at any
    severity into the same stream `FR-GRAPH-006` relies on for refusal records.
21. **Subgraph** is the only entity defined inside requirement prose (`FR-GRAPH-008`) rather than in a §4 field
    table like every other entity.
22. **T-092 is missing** from the M8 table (runs T-090, T-091, T-093…T-097). Global task numbering is
    non-contiguous by design, so this may be intentional — but it is a gap between adjacent rows in one
    milestone, unlike the other gaps. Worth a one-line confirmation from the user.

## Key decisions

### Made this session

1. **Committed rev. 7 + rev. 8** (`51c11e5`) before starting the review, on explicit user approval via
   AskUserQuestion ("Commit now"). Gave the §5 review a clean baseline.
2. **`sandbox-init`'s control plane rides the Agent MCP, not a second REST surface** — user's explicit choice
   from AskUserQuestion ("Add control-plane tools to Agent MCP"). Rejected alternative: a
   `/api/v1/sandbox/*` REST namespace, which would have required relaxing `FR-AUTH-002`'s rule that agent
   tokens never authenticate against REST, and would have created a second agent-facing surface to
   authenticate, rate-limit, audit, and project-scope. Recorded as a Design Decision in §7.3 so it is not
   re-litigated.
3. **Control-plane tools are gateway-token-only and parameterless w.r.t. identity** — my addition, not
   specified by the user. Reason: without it, an external-agent token could call `report_output` to forge an
   agent's output or `report_session_end` to close another agent's session. Reversible but I would push back.
4. **`ApprovalDecision` as a separate entity** rather than more columns on `Question`. Reason: `FR-HANDOFF-005`
   requires "all decisions recorded individually, including the ones after the quorum was met" plus a
   delegation trail — a single `answer` string cannot hold that. The `counted` boolean (rather than deleting
   non-counting decisions) is what makes the trail complete.
5. **Scope: Tier 1 + corruption only** — user's choice ("Tier 1 + corruption first (Recommended)"), with
   Tiers 2–5 explicitly deferred to a second pass. **Do not treat the 22 above as rejected.**

### Locked earlier, still binding (do not re-litigate)

From the Kimi session: opencode-only runner (native CLIs and `claude_proxy` dropped; forking opencode is a
non-goal); orchestrator interface with a Docker backend, Kubernetes designed-for but out of scope; single-user
mode is the same Hub via docker-compose; graph = directed communication topology enforced at send time, **no
workflow engine**; stack stays Python/FastAPI + React/TS + Python CLI on PyPI, SQLite default, PostgreSQL for
company deployments; RBAC-ready granular model.

From rev. 5: Apache-2.0 for 1.0 artifacts (`FR-CORE-005`); per-project `open` (default) / `gated` graph mode
(`FR-GRAPH-007`); `provider_egress` per-profile knob, `direct` first (M2), `hub_proxy` later (T-087); PyPI name
stays `agentweave-ai` shipping 1.0.0 as semver major with a `release/0.x` maintenance branch (`FR-MIG-003`).

From rev. 6: product name "the Weave" for the UI surface only (data model keeps graph/node/edge); subgraph =
named node subset, no edge namespace, no effect on reachability; `is_admin` removed (AccessRole /
RolePermission / RoleAssignment, nullable `project_id`, permissions recomputed per request); fine-grained
tokens only, never exceeding owner, intersected at use time, mandatory bounded expiry; hop budget stays on the
thread, edges carry stateless `hop_limit`/`max_depth` clamps (**flagged reversible**); "project" NOT renamed to
"workspace"; JSON columns, no second datastore; job-fired messages are `system`; approval deadlines escalate,
never auto-decide; externally-built images framed now (`FR-SBX-010`), built later; `AccessRole` (authorization)
and `RoleTemplate` (behavior) stay separate.

From rev. 7: **runner stays opencode, conditionally** (version pinned per image; `FR-RUN-001…008` held as a
runner contract with `sandbox-init` as the adapter; empirical comparative verification before M1 via T-110).
**Codex CLI is the designated fallback.** Rejected with reasons — do not re-propose without new evidence:
Claude Code/Agent SDK (closed source, Anthropic-only, ToS bars embedding — keep as *quality benchmark* only);
Gemini CLI (single-vendor-first); Goose (Apache-2.0, MCP-native, philosophically closest, but ~¼ the community
and no server mode — **included in T-110 as third candidate**); Aider (interactive pair-programmer, not an
unattended engine); OpenHands (**not a runner — a competing architecture**; adopting it replaces §5/§6 rather
than implementing them; used as prior art only, which fed rev. 8).

From rev. 8: repository instructions are **layer 3** of five in `FR-ARCH-007`, below role (4) and agent (5),
because they are the least-trusted, agent-writable source. **Still flagged to the user as a judgment call and
still unconfirmed** — reversible with a two-line reorder.

### Working agreement on review cadence (still in force)

Batch review findings at section boundaries or every ~8–10 findings; **except** premise-breaking structural
findings, which go immediately. Annotation format: section/FR-ID anchor, what is wrong, what is wanted instead
(say explicitly when you don't know — those get an AskUserQuestion, not a guess).

## Constraints and user directives (verbatim)

From this session:

- "I want you to scan the entire spec to find problems in it and flag what needs to be worked on. Since we
  started adding things some drifts might happen and new things popped up. Also some old underlying problems
  might have been writen on the first draft that were never addressed."
- "commit then handoff"
- AskUserQuestion answers (2026-07-26): commit rev. 7+8 → **"Commit now"**; finding scope → **"Tier 1 +
  corruption first"**; sandbox-init transport → **"Add control-plane tools to Agent MCP"**.

From earlier sessions (still binding):

- "we need a task to research everything from opencode to see every cli flag, how to use, anything that we can
  take advantage for implementation. We should also test all of those to see if they work and how they work in
  our environments. **Do not assume anything.**"
- "The same for coding we need to test things and not assume they just work, not only testing of wrinting test
  for code quality but also executing and seeing what happens"
- "I want to keep the nature of A2A communication and workflow I don't want it to become just another crewAI
  or n8n."
- "What kind of security knobs should we have? We should have a exhaustive list of those in the spec. Knobs for
  containers and users of the hub"
- "how to use machines from the main cloud services providers... this should be research for all the main cloud
  providers and **create a process for each one of those**"
- "I'll be using multiple agents to build this because I have token plans and they might run out and I need to
  delegate the work to other agents so we need a way to keep track of the work being done"
- "I want to be able to tune the security all sorts of ways of the images."
- "The company is very big. 800M in profits last year. But we can start small and expand but we will definetly
  need FULL RBAC in the future for sure. So we got prepare for that."
- "Feel free to disagree in some points and push back. But show me your resoning behind it."
- Housekeeping decisions (2026-07-26, do not re-ask unprompted): `validate_spec.py` → "Nothing yet";
  `.claude/handoffs/` → "Leave as-is"; `specs/agentweave-spec.html` v0.x edits → "Leave it".

Project rules from `CLAUDE.md`: templates via `get_template()`; all saves pass through `validator.py`; all task
modifications use `with lock("name"):`; never commit `.agentweave/tasks|messages|agents`, `session.json`,
`transport.json`, `kimichanges.md`, `kimiwork.md`.

Environment instruction: "Do not call the AgentTool unless the user requested it" — no subagents were spawned
this session or any prior one, deliberately.

## Dead ends

**This session:**

- **Three anchor failures in `patch_rev9.py` on the first run**, all the same cause: I wrote `&#8212;` where
  the file has a **literal UTF-8 em dash** (`—`). Affected the `FR-ROLE-004` anchor, the `FR-HUB-008` catch-up
  anchor, and the rev. 8 changelog row. **The verify-then-write pattern caught all three before any write, so
  no partial state resulted** — keep that pattern. Lesson (a repeat of rev. 7's): dump `repr()` of the exact
  line before writing any anchor containing a dash, quote, or ellipsis.
- **`python - <<'PY'` heredocs crash on Windows console encoding** when printing spec text containing `—`, `→`,
  or `§`: `UnicodeEncodeError: 'charmap' codec can't encode character '\u2192'`. Fix that worked:
  `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` as the first statement.
- **The PowerShell here-string form `git commit -m @'...'@` silently corrupts the message when run through the
  Bash tool** — the Bash tool is Git Bash/POSIX sh, so `@` became a literal first character of the subject
  line. Had to `git commit --amend -F <file>`. **Use `-F <file>` for multi-line commit messages in the Bash
  tool**, or use the PowerShell tool if you want here-strings.
- **My first `deep_scan.py` task-ID regex produced 22 false positives** — `<td[^>]*>(T-\d{3})</td>` does not
  match rows like `<td>T-004 <span class="pill">P</span></td>`. Corrected pattern is in the scratchpad copy.
  Do not trust an unvalidated "referenced but not defined" list.

**Carried from previous sessions, still true:**

- **Bash heredoc for large HTML payloads fails** (`unexpected EOF` despite quoted delimiter). Use a Python
  patch script written with `Write`, then `python <script>.py`.
- **Python string-literal trap in patch scripts:** inside single-quoted literals, `''' + X + '''` terminates
  the string; concatenate with `' + X + '`. The SyntaxError location is nowhere near the cause.
- **Entity vs literal characters in anchors:** the spec mixes literal UTF-8 `—`/`→` in prose with
  `&#8212;`/`&#8230;`/`&#8594;` entities in table cells and changelog rows. Verify before writing.
- **RFC keyword/class inversion:** mechanical grep only catches class/text mismatches, not semantic double
  negatives. Read hand-edited normative sentences aloud.
- **Whole-document generation in one subagent call** produced a truncated file. Section-at-a-time with
  validation between rounds is what works. (Findings 11/12 this session — the two truncated passages — are
  almost certainly residue from that era or from a bad patch splice, and neither was catchable by the
  validator. Expect more of them; only a full read finds them.)

## Verification

**Ran and passed:**

```
python patch_rev9.py                      # OK: applied 22 edits (after 3 anchor fixes)
python validate_spec.py                   # OK — 118=118 FRs, sections 0..17, 86 tasks, 17 Q rows
grep -c 'must not">must<\|must">must not<' specs/agentweave-1.0-spec.html   # → 1 (§0.2 legend)
git commit                                # d60c1e3, 1 file changed, 109 insertions(+), 34 deletions(-)
```

Also spot-read and confirmed the rendered text of: the repaired reply-default note (§4.4.2), the repaired
`FR-ROLE-004` role list ("(AI-native roles) — twenty-one templates in total"), and the full rewritten
`FR-HUB-008` block. Confirmed by grep that all four new tool names, all five new Question fields, and
`ApprovalDecision` are present with the expected mention counts, and that the gateway-token-only restriction
text is in place.

**NOT tested — do not claim otherwise:**

- The file has **never been opened in a browser** across any session. Rendering, sticky TOC, scrollspy, mobile
  drawer, dark mode, and specifically the new `colspan="3"` group-header row inside the `FR-GW-004` table, the
  new `ApprovalDecision` table, and the new Design Decision / Open Issue blocks in §7.3 are **visually
  unverified**. The `colspan` row is the most likely thing to look wrong.
- No test suite, ruff, black, mypy, or pytest was run — nothing in `src/` or `hub/` was touched.
- **The 22 remaining findings are unverified as *fixes* because no fix was attempted** — but each was
  confirmed by direct reading of both sides of the contradiction, not inferred.
- The user has reviewed roughly **§0–§4.6** across earlier rounds. **§5 onward has never been
  approver-reviewed.** The user's stated position at the previous handoff was "I'm about to review chapter 5" —
  **that review has still not happened**; this session's scan interrupted it.
- All rev. 7 competitive research (runner feature claims, star counts, licenses, Goose/OpenHands details) comes
  from secondary web sources dated 2026-05…07, not from running the tools. Per `FR-DEV-002` none of it is
  "verified" until T-003/T-008/T-110 execute it.

## Git state

- Branch: `agentweave-1-0` (main branch for PRs is `master`). HEAD: `d60c1e3`.
- **No upstream configured** — nothing has ever been pushed.
- Recent commits: `d60c1e3` (rev. 9) ← `51c11e5` (rev. 7+8) ← `47ff679` (rev. 6) ← `843e5d1` (v0.42.0 bump).
- Working tree: `specs/agentweave-1.0-spec.html` is **clean/committed**. Remaining entries are all
  pre-existing and deliberately untouched: ` M specs/agentweave-spec.html`, `?? kimi-export-session_-20260725-135928.md`,
  `?? validate_spec.py`, `?? .claude/handoffs/`.

## Next steps

1. **Apply Tier 2 (findings 1–6 above) as rev. 10.** Start with finding 1: in
   `specs/agentweave-1.0-spec.html` §1.2 Non-goals, the bullet beginning
   `<strong>Granular RBAC management UI.</strong>` ends "…and no custom-role editing surface." — that clause
   contradicts `FR-UI-007`'s "Access roles" row, which requires listing, creating, and editing AccessRole rows.
   Amend the non-goal to scope it to what 1.0 actually withholds (suggest: 1.0 seeds exactly two roles and
   ships no *delegated administration*, while the AccessRole editor exists). Then findings 2–6 in the same
   patch script. Follow with `python validate_spec.py`, the RFC grep, and a rev. 10 changelog row.
2. **Then Tiers 4 and 5** (findings 7–22) as rev. 11, or fold into rev. 10 if the user prefers one pass.
   Note finding 17 changes the expected RFC grep result from 1 to 0.
3. **The user still owes §5 onward a review.** Their stated position two handoffs ago was "I'm about to review
   chapter 5". Offer it once the finding backlog is clear, or sooner if they ask.
4. **When they reach §3.3, flag the repo-layer precedence judgment call** (rev. 8: repository instructions at
   layer 3, below role and agent) for explicit confirmation or reversal. Still unconfirmed.
5. Housekeeping remains deferred by user choice: `validate_spec.py` (nothing yet), `.claude/handoffs/`
   (leave as-is), v0.x `specs/agentweave-spec.html` edits (leave it). **Do not re-ask unprompted.**
6. Pending git mutations, both needing explicit confirmation: swap `LICENSE` MIT → Apache-2.0 per
   `FR-CORE-005` (affects v0.x too); tag the final v0.x commit `v0.42.0` at `843e5d1` and create `release/0.x`
   per `FR-MIG-003`.
7. Only after spec approval: start M0 — T-003, then T-008, then T-009, then T-110. Gate G0 requires ten
   deliverables (nine decision records + the opencode empirical matrix).

## Open questions for the user

- **Finding 22:** is the missing **T-092** in the M8 table intentional? Global numbering is non-contiguous by
  design, but this is a gap between adjacent rows within one milestone.
- **Finding 14 (`FR-DOM-003`)** needs a decision, not a wording fix: should the Hub enforce the task transition
  graph, or keep the v0.x "accept any valid status from a `task:write` caller" behavior that makes the diagram
  decorative?
- **Repo-layer precedence (rev. 8)** — repository instructions at layer 3, below role (4) and agent (5).
  Confirm or reverse. Still unanswered across two handoffs.
- Carried unanswered: **Q-14** (reference cloud provider — gates 1.0, reorders M8); **Q-13** (`reply=allowed`
  edge default); whether the company's git forge issues per-repo short-lived write tokens (constrains M1); the
  rev. 6 `hop_limit`-as-edge-clamp deviation (flagged reversible).

## Read on resume

- `specs/agentweave-1.0-spec.html` — the deliverable, ~4,010 lines. Read §0.5 changelog (9 revisions; the rev. 9
  row is the authoritative summary of this session's edits), then §7.3 (`FR-GW-004`, the new control-plane
  tools) and §4.5 (Question + ApprovalDecision). **Do not read it whole** unless doing another full scan.
- `validate_spec.py` (repo root) — run `python validate_spec.py` after every spec edit round; pair with
  `grep -c 'must not">must<\|must">must not<' specs/agentweave-1.0-spec.html` (currently must return 1; becomes
  0 if finding 17 is fixed).
- `C:\Users\huida\AppData\Local\Temp\claude\C--Users-huida-Documents-projects-AgentWeave\2f55514b-c5ae-4028-b46d-9a97d92c350b\scratchpad\deep_scan.py`
  — the semantic consistency scanner written this session (task/Q/FR cross-references, numeric-claim drift,
  section-ref mismatches, glossary orphans, NEEDS-CLARIFICATION inventory). **Session-scoped temp directory —
  copy it into the repo if it should survive.** It found roughly a third of the 28 findings; the rest needed a
  full human-style read.
- `.claude/handoffs/2026-07-26-2105-spec-rev8-runner-research.md` — rev. 7/8 detail: the full runner
  competitive evaluation and the OpenHands study, with per-alternative rejection reasons.
- `.claude/handoffs/2026-07-25-2225-spec-rev6-committed.md` — rev. 6 detail (RBAC/tokens/subgraphs/Weave).
- `kimi-export-session_-20260725-135928.md` (repo root, untracked) — the user's original vision statement and
  the four Kimi-locked decisions, verbatim.
- `CLAUDE.md` — project rules (validator, locking, templates, never-commit lists).
