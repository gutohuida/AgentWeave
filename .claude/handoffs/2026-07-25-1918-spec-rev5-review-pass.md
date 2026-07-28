# Handoff: AgentWeave 1.0 spec rev. 5 — first review pass (§0–§3.2) applied, uncommitted

**Date:** 2026-07-25T19:18:58+0100 · **Branch:** agentweave-1-0 · **HEAD:** 843e5d1
**Previous handoff:** `.claude/handoffs/2026-07-25-1624-agentweave-1.0-spec.md` (read it first for the full
spec history and the user's locked v1.0 decisions)
**Status:** chunk complete (rev. 5 edits applied and validated; not visually reviewed in a browser, not
committed, spec still unapproved draft)

## What happened this session

The user ran the "resume" flow (no `/resume` skill exists in `.claude/skills/` — the previous handoff was read
directly), then reported having read the spec **up to §3.2** and gave seven feedback points. Four required
decisions, which the user made via AskUserQuestion (all four took the recommended option):

1. **License:** Apache-2.0 replaces MIT for the 1.0 artifacts.
2. **Graph mode:** per-project `open` (default, v0.x free-form flow preserved) / `gated` (edge-enforced), opt-in.
3. **§3.2 provider-egress Open Issue (Q-12):** both designs, as a per-profile `provider_egress` knob —
   `direct` built first (M2), `hub_proxy` (Hub relay) later (new task T-087).
4. **Package:** keep PyPI name `agentweave-ai`, ship 1.0.0 as a semver major bump; tag the v0.x break-off and
   keep a `release/0.x` maintenance branch.

The other three points were applied directly: domain-neutral framing (roles beyond software work, e.g.
underwriting), a concept-evolution note answering "do messages/tasks/questions need rework" (no — evolution,
documented in §13.1), and a normative implementation protocol for LLM agents executing the spec (FR-DEV-003).

## What changed in the spec (rev. 5, all in `specs/agentweave-1.0-spec.html`)

- **New requirements (5):** `FR-CORE-005` (Apache-2.0), `FR-ARCH-006` (`provider_egress` knob + hub relay
  contract), `FR-GRAPH-007` (open/gated graph mode + switch semantics), `FR-MIG-003` (package continuity,
  v0.x tag + release/0.x branch), `FR-DEV-003` (implementation protocol: read order → task selection → FRs as
  contract → verify → revise → hand off).
- **Scoped to gated mode:** FR-GRAPH-002 (incl. "new node is mute" / "unreachable means invisible"),
  FR-ARCH-004 step 3, FR-GW-006 step 6, FR-GW-007 (`list_peers` = all project agents in open mode),
  the §7.5 design decision. Loop-damping limits (§4.4.3) explicitly apply in BOTH modes.
- **§3.2:** the provider-egress Open Issue is now a Design Decision + FR-ARCH-006. **Q-12 in §17 is marked
  resolved.** The hub_proxy relay only needs to be OpenAI-compatible (opencode's existing custom-provider
  surface); its feasibility is flagged `[NEEDS CLARIFICATION]` pending T-008 verification.
- **§1:** "software work" → "knowledge work" + a "Not software-only" note (roles/instructions specialize a
  deployment; §6.6 git substrate acknowledged as the code-shaped part). §10 got the matching "seed set is a
  starter kit" note. §13.1 got the concept-evolution note plus an open-flow continuity row.
- **§4.4.1:** new positioning note — n8n/Temporal sell deterministic execution, LangChain/CrewAI sell
  libraries, AgentWeave's lane is autonomous A2A collaboration with governance as deployed infrastructure.
- **§6.5:** `egress` row re-pointed at FR-ARCH-006; new `provider_egress` knob row in table (c) Network.
- **§9.2:** FR-UI-003 gained a mode-display/switching item (preview unreachable agents when gating).
- **Backlog:** T-065 now covers open/gated modes (satisfies FR-GRAPH-007 too); **T-087 added in M7** (Hub
  provider relay; deps T-034 + T-008; acceptance includes a hub_proxy sandbox making a model call with no
  credential in env). T-009's "feeds Q-12" re-pointed at T-087. M5 milestone row mentions open/gated modes.
- **§0.5 changelog:** rev. 5 row added recording all of the above.
- **§14 index:** rows added for the 5 new FRs; FR-ARCH-004, FR-GRAPH-002, FR-GW-007 summaries updated.

## Verification

**Ran and passed** — `validate_spec.py` (new, kept in the repo root, untracked; html.parser-based, rebuilt
this session because the previous validator lived in an ephemeral scratchpad):

- Tag balance: 0 errors, 0 unclosed at EOF; all `href="#…"` anchors resolve; 0 duplicate ids
- FR traceability: 103 defined in body = 103 in §14 index (was 98; +5 new)
- h2 sequence 0…17 intact; RFC keyword/class mismatches: 0 (excluding the §0.2 legend)
- Counts: 72 unique task IDs (was 71; +T-087), 16 Q rows

**NOT tested:** the file has still never been opened in a browser (rendering, TOC, scrollspy, dark mode all
unverified). No code was touched; no pytest/ruff/mypy run. The patch script (`patch_rev5.py`) was deleted
after use; `validate_spec.py` was kept for future revision rounds — delete it if unwanted.

## Git state

- Branch `agentweave-1-0`, HEAD `843e5d1`, nothing committed or pushed.
- ` M specs/agentweave-spec.html` — still the pre-existing v0.x edits, NOT from any 1.0 session.
- `?? specs/agentweave-1.0-spec.html` — the deliverable, now at rev. 5.
- `?? validate_spec.py`, `?? .claude/handoffs/`, `?? kimi-export-session_-20260725-135928.md` — untracked.

## Pending user actions (raised, not done)

- **Review continues:** the user has read §0–§3.2; §4 onward is still unreviewed by them. Expect more review
  feedback — apply it the same way (patch → validate → changelog row).
- **LICENSE file:** the repo's `LICENSE` is still MIT. FR-CORE-005 records the Apache-2.0 decision, but the
  actual license swap (affects v0.x too) awaits the user's go-ahead.
- **Git tag / release branch:** FR-MIG-003 requires tagging the final v0.x commit (`v0.42.0` at `843e5d1`)
  and creating `release/0.x`. Git mutations — not done, needs explicit confirmation.
- **Commits:** rev. 5 is uncommitted like the rest. The previous handoff's commit recommendation stands
  (1.0 spec alone on `agentweave-1-0`; v0.x spec edits separately; leave the Kimi transcript uncommitted).
- **Open questions still open for the user:** Q-14 (reference cloud provider), Q-13 (graph limit defaults /
  `reply=allowed` default), the git-forge short-lived-token question. Q-12 is now closed.

## Read on resume

- This file, then the previous handoff (2026-07-25-1624) for full context.
- `specs/agentweave-1.0-spec.html` §0.5 changelog rev. 5 row — the authoritative summary of what changed.
- `validate_spec.py` — run after every future spec edit round (usage: `python validate_spec.py`).
