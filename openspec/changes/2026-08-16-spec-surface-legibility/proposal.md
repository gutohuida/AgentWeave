# Fix the six things the operator found wrong looking at real spec surfaces

## Why

`.claude/autonomous/2026-08-16-operator-ux-findings.md` is the first time a person looked at the
spec document, coverage bar and task board with real content in them (`aw-loop10`, 9 requirements).
Every finding survived a code check — none was a misreading. Verbatim, with what was actually found:

1. *"It's readable but I think it's uglier... this one is much too 'texty'."* — the rendered
   document uses colour nowhere it could carry meaning.
2. *"the background is navy blue. I want it to match the background of the agentweave."* — checked
   against the code, not just eyeballed: `hub/ui/src/components/spec/SpecFrame.tsx`'s
   `themeOverride()` injects CSS custom properties named `--bg`, `--surface`, `--surface-2`,
   `--border`, `--fg`, `--muted` into the embedded document. `hub/hub/spec_render.py`'s stylesheet
   defines and reads a **disjoint** set — `--aw-bg`, `--aw-fg`, `--aw-muted`, `--aw-rule`,
   `--aw-accent`, `--aw-chip-bg`, `--aw-code-bg`. None of the six names the override writes appears
   anywhere in the renderer's CSS, so the override has nothing to affect and the document always
   falls back to its own baked-in dark default (`#0d1117` — the navy). This is a wiring bug, not a
   preference: two neutral palettes that were never meant to diverge (the override's comment block
   was written for the *older* skill-authored documents, which used `--bg`/`--surface` directly)
   drifted apart when `spec_render.py` was written for `2026-08-12-hub-owns-the-spec-document` under
   a different naming convention, and nothing asserts the two still agree.
3. *"on the spec screen is showing 4 in progress and 5 verified but I don't think that's true
   right?"* — counts are correct (`GET /project/spec/coverage`: 5 verified, 4 in\_progress, exactly
   matching 5 accepted / 4 rejected evidence rows), but `hub/hub/requirement_coverage.py`'s `_state()`
   checks only `accepted` and `awaiting` review states against the requirement's current digest — a
   requirement whose only current evidence was **rejected** falls through the same path as one with
   no evidence at all, landing on `in_progress` or `not_started` depending on whether a task happens
   to be linked. A refused claim and active work are indistinguishable on this screen.
4. *"it's hard to understand on the task board to which parts of the spec that relates too."* — the
   data already exists and already reaches the browser: `hub/hub/api/v1/tasks.py`'s
   `_attach_requirements()` populates `requirement_links`/`requirement_ids` (with statement, modal,
   and even a pre-computed `has_rejected_evidence` flag) on every task response, and
   `hub/ui/src/api/tasks.ts`'s `Task` type already declares all of it. `TaskCard.tsx` never renders
   any of it. Confirmed: `grep` for `has_rejected_evidence`/`requirement_links` under `hub/ui/src`
   outside the type declaration returns nothing.
5. *"the task is tough to check... expanding looks too narrow. Maybe we should be able to open the
   task like jira."* — `TaskCard.tsx` expands in place, inside a board column
   (`minmax(160px, 1fr)`, seven columns wide), so a task with real description, acceptance criteria
   and (after fixing #4) requirement chips has nowhere to put them.
6. *"are the tasks too condensed?... How does the ticket generation works?"* — validated against
   `task_requirement_links` in `proj-ff695d96`: one approved ticket carried 6 of 9 requirements on
   42 words, and it linked FR-9 whose evidence was rejected — invisible inside an approved ticket.
   `hub/hub/spec_tasks.py` mints exactly what the document's `tasks[]` array declares; nothing caps
   how many requirements one entry may claim, at either the charter (`hub/hub/data/charters/spec.md`)
   or validation (`hub/hub/spec_completeness.py`) layer.

## What Changes

- **F2 — realign the rendered document's neutral CSS variables with the six names
  `SpecFrame.tsx` already overrides** (`--bg`, `--fg`, `--muted`, `--border`, `--surface`,
  `--surface-2`), so the Hub's existing theme-injection mechanism actually reaches the document — no
  change to `SpecFrame.tsx` required. A new test pins the two lists together the same way
  `hubVisualLanguage.test.ts` already pins `HUB_NEUTRALS` against `index.css`, so they cannot drift
  apart silently a second time. Still no external resource reference — inherited custom properties
  only, per `2026-08-12-hub-owns-the-spec-document` 16.12.
- **F1 — give the document's own semantic hues (kept as the document's, not Hub-overridden, per the
  override's existing comment) somewhere to apply**: the MUST/SHOULD/MAY modal, the phase chip, and
  the acceptance table gain distinct, declared styling instead of uniform prose. Built on F2's
  corrected neutrals — doing this before F2 would recolour a document that is still the wrong
  background.
- **F3 — a `rejected` coverage state**, ranked in `requirement_coverage.py`'s precedence between
  `verified` and `in_progress`: current-digest evidence that was rejected, with nothing accepted and
  nothing awaiting, reads as `rejected`, not `in_progress`. `SpecCoverageBar.tsx` gets a matching
  entry. `hub/hub/api/v1/tasks.py`'s existing `has_rejected_evidence` computation is the direct
  precedent for the query shape (current-digest scoped, keyed by requirement) — this is not a new
  kind of query, the same signal reaching a second screen.
- **F6 — a ceiling on requirements per declared task**, enforced the same way `requirement_without_task`
  already is: `spec_completeness.check()` refuses a transition to `proposed` when a task names more
  requirements than the ceiling permits, and the Spec Author charter is told the number up front so
  the refusal is rare rather than the normal path. Derived from evidence, not guessed — see
  `design.md` D6.
- **F4 — requirement chips on `TaskCard.tsx`**, sourced from data the API already returns, each
  linking to its requirement's anchor in the Spec tab. The reverse direction (a coverage row's task
  count, already shown as text in `SpecCoverageBar.tsx`) becomes a link back to the board, filtered to
  that requirement's linked tasks.
- **F5 — task detail becomes a drawer**, not an in-column expansion — full width, holding
  everything the inline expansion held plus F4's requirement chips (statement, modal, rejection flag)
  with room to read them.

## Non-Goals

- **Not judging whether F1/F2/F5 look good.** Colour is applied, the background token is provably the
  Hub's own, the drawer opens and clips nothing — those are what this change can prove. Whether the
  result reads as "colourful" or "like Jira" is the operator's, per `tasks.md`'s human-only section
  and the standing limit on visual judgement (`STATE.json` `limits`).
- **Not rewriting `spec_tasks.py`'s materialisation** to split an over-sized declared task itself.
  F6 refuses the document until the *authoring agent* splits it — splitting automatically would be
  deciding, on the agent's behalf, how to divide work that only the agent (or its author) understands
  well enough to divide sensibly.
- **Not a second coverage precedence rework.** `drifting`, `stale`, `evidence_awaiting_review`,
  `not_started` and `unserved` are unchanged; F3 inserts one new state at one place.
- **Not deep-linking a coverage row to a specific task's drawer.** F4's reverse direction lands on the
  filtered board; opening a specific task from there is a second click, matching how the board's own
  filter chips already work.
- **Not `17.1`/`17.3`** (the authoring-flow and interview-feel judgements) — explicitly deferred by the
  operator in the findings document, unrelated to what was found here.
