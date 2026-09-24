# Bundles — R1 / R2 / R3 for every open spec track and operator decision

Opened 2026-09-23 night at the operator's request: *"do R1-R3 for everything and every decision
that we need to make"*, grouping *"decisions that might impact each other in one bundle"*. Each
bundle runs **R1 → R2 → R3 and parks there**. IMPL is not started until the operator approves
(`APPROVALS.md`); every decision a bundle reaches is a **recommendation** until the operator
records it in `DECISIONS.md`.

The rounds are run by separate subagents; an orchestrating session only launches them, commits
their output and updates `ROUNDS.md`.

| Bundle | Title | Absorbs (ROUNDS.md) | Findings |
|---|---|---|---|
| B1 | Attending a task, and a flow's review | S1, S13, D9 | F370 F371 F368 F361 F289 F158 · F327 · F374 |
| B2 | Runs: what a row is, and how a run presents | D1/S7, D11 | F121 F123 F147 F149 · F291 F42 F168 F235 F273 |
| B3 | Agent identity, control and actors | D3/S9, D10, D8 | F111 F136 F3 F378 · F15 F77 F139 F276 F366 F125 · F47 F120 |
| B4 | Permission judging | S3 + D5, D4/S10 | F362 F403 F402 F401 · F283 F230 F284 |
| B5 | Evidence, propose gates and merge truth | S5a, S6, S12, D12 | F215 · F207 F113 · F166 F358 F165 · F242 F141 |
| B6 | Spec-flow drift, corpus writes and audit reads | S5b, S5c, S5d, F213, F217 (from D13) | F129 F132 F216 F217 · F206 F208 F205 · F211 F169 · F213 |
| B7 | Models and budget | D2/S8, D7/S11 | F174 F267 F268 F221 · F240 F62 |
| B8 | Checkpoint cutover identity | S2 | F293 F294 |
| B9 | SSE tells the client what it lost | S4 | F251 F253 F335 |
| B10 | Dead surfaces: build or delete | D6 | F178 F225 F260 F263 F259 |
| B11 | The remainder decisions | D13 (less F217) | F308 F305 F354 F385 F20 F307 F349 F53 F281 F389 F146 F157 F134 F183 F177 F248 F133 F21 F382 F322 F339 F340 |
| B12 | Single-finding specs | the "remaining single-finding specs" row | F65 F130 F330 F363 F278 |

Not bundled, because each waits on work that is not built yet: F197 (after S5), F379 (after
UI-1's F237), F377/F336 (after S5).

## The record file contract — `spec-queue/tracks/Bn.md`

One file per bundle, appended to by each round, never rewritten by a later round except the
**Status** line. `scripts/rounds_page.py` renders it to `Bn.html`, so keep this shape exactly:

```markdown
# Bn — <title>

**Findings:** F…, F…
**Decisions:** D… (or "none")
**Changes:** `openspec/changes/<name>/`, … (or "none — decision only")
**Status:** R1 done | R2 done | R3 done — parked for operator
(after the operator's review: R3 done — operator review YYYY-MM-DD: N approved, M revising (…))

## R1 — explore and propose (YYYY-MM-DD)
…what the code showed, each finding re-verified (still open / already fixed / changed shape),
options for each decision with evidence, the recommendation, and what was written…

## R2 — independent comparison (YYYY-MM-DD)
…each claim re-derived from the code: what disagreed, what was changed in the proposal and why,
what stands…

## R3 — independent comparison (YYYY-MM-DD)
…same, fresh…

## Final — what the bundle reached, and why
### Decisions
| # | Question | Recommended answer | Why |
### Changes
| Change | Findings | What it does | Size |
### Open for the operator
…each question the operator must answer before IMPL, with the recommended answer first…
### Findings that did not need a change
…already fixed, retired, or duplicates, with evidence…
```

## Rules for every round

- Work only inside the worktree `.claude/worktrees/spec-tracks`. Never touch `:8000`; start no Hub.
- Do not edit product code, tests, `scripts/drive/FINDINGS.md`, `ROUNDS.md`, `APPROVALS.md` or
  `DECISIONS.md`. Do not commit. Write only your bundle's record file and your bundle's
  `openspec/changes/<name>/` directories.
- A change directory: `proposal.md`, `design.md`, `tasks.md`, `test-guide.md` (agent-verifiable vs
  human-only checks), `specs/<capability>/spec.md` deltas. `### Requirement:` blocks with a
  SHALL/MUST on the requirement's **first line**, `#### Scenario:` blocks.
  `openspec validate <name> --strict` must pass.
- A test the change plans for code that consumes an API payload uses the order the route really
  returns, and some test fails if that order is reversed (F190).
- Ask what each route **returns** when the function it calls raises.
