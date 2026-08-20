# Handoff: four backlog items turned out to be one problem, and adoption is proposed

**Date:** 2026-08-20T17:23:32+01:00 · **Branch:** `master` · **HEAD:** `4314567`
**Agent:** Claude Opus 5 (1M context) (Claude Code, interactive)
**Previous handoff:** `.claude/handoffs/handoff-0063-2026-08-20-1543-the-suite-destroyed-the-operators-database-and-five-ui-fixes.md`
**Status:** chunk complete. Working tree clean. 23 commits unpushed. No PR.

## Goal

The operator asked, in order: open a simple openspec exploration page for every open backlog item;
merge the fixes into master; explore the connected items together; propose the first change; hand
off; clear; resume; start the next exploration.

Steps 1–5 are done. The remaining sequence — clear, resume, next exploration — is the operator's to
trigger.

The *why* governing judgement calls is unchanged from handoff 0063: this is the dogfooding
migration CLAUDE.md describes, so friction found while using the product is a **deliverable**, not
a distraction.

## Current state

### The backlog was opened as eight exploration stubs, then four were consolidated

`786c146` created eight stubs, one per open point. `89e5ad3` replaced four of them with a single
exploration once they turned out to be one problem. **Four stubs remain and are untouched:**

- `openspec/explorations/2026-08-20-showing-the-reasoning-chain.md` — item 1
- `openspec/explorations/2026-08-20-the-theme-does-not-survive-a-restart.md` — item 3
- `openspec/explorations/2026-08-20-how-long-an-open-document-should-follow-you.md` — item 7
- `openspec/explorations/2026-08-20-an-agent-messaging-its-other-conversation.md` — item 10

### The consolidated exploration is the main artefact

`openspec/explorations/2026-08-20-the-row-is-the-spine.md`. **Read this before anything else.**

Its finding: a document is a file plus a row. The read path already works from the file alone;
everything else is row-keyed. Adoption — minting a row from a file that exists — is the gate items
5, 9 and 11 all sit behind.

### Three corrections it makes to the previous handoffs

**1. The corpus is NOT invisible.** Handoffs 0062 (finding 17) and 0063 both state the Spec tab
shows nothing. **That is wrong, and I repeated it before checking.** `SpecPage` and `SpecRailNav`
use `useSpecList` → `GET /specs` → `spec_documents.compute_state()`
(`hub/hub/spec_documents.py:393-423`), which is **entirely disk-driven**. All 34 documents render,
with titles from `spec/index.json`. Rows contribute exactly two fields (`api/v1/spec.py:106-113`):
`phase` and `document_id`. The row-less case was designed for — `hub/tests/test_spec_archive.py:125`
says so, and `specNavigation.ts:135,178` falls back to `deriveTitle(entry.path)`.
**Accurate description: readable but inert.**

**2. The blocker is a weld, not a missing capability.** `POST /documents` fuses row-minting and
file-writing (`api/v1/spec.py:1131-1153`). `spec_lifecycle.create_document` (`:121`) is **pure
row-minting and takes no workspace, so it cannot touch disk**. The route welds
`save_document`'s placeholder write onto it.

**3. The row IS the filing.** `build_index` (`spec_documents.py:257`): *"Only documents that are
both on disk and known to the Hub are filed."* This is why `project-instructions` and `quiet-hours`
sit at `unfiled` permanently.

### Change #1 is proposed and validated

`openspec/changes/document-adoption/` — all four artifacts, `openspec validate document-adoption`
passes. **Not implemented. No code written.**

### Machine state, verified this session

| | |
|---|---|
| Port 8000 Hub | running. **One project only: `proj-adf8a200` "huida" → `C:\Users\huida`** |
| Port 8010 | running, untouched (standing prohibition) |
| Port 8020 | **killed this session** (PID 25200, confirmed gone) |
| This repo as a project | **NOT registered.** Operator said "Not yet" when asked |

`.migration/` (`authored/`, `payloads/`) is untracked scratch at the repo root, ignored by nothing.
Left alone; it will keep appearing in `git status`.

## Files touched

All committed; `git status --short` is empty.

**`786c146` — eight stubs**

- `openspec/explorations/2026-08-20-showing-the-reasoning-chain.md` — **kept**
- `openspec/explorations/2026-08-20-the-theme-does-not-survive-a-restart.md` — **kept**
- `openspec/explorations/2026-08-20-how-long-an-open-document-should-follow-you.md` — **kept**
- `openspec/explorations/2026-08-20-an-agent-messaging-its-other-conversation.md` — **kept**
- `…-adopting-documents-that-already-exist.md`, `…-the-spec-landing-page.md`,
  `…-agents-starting-their-own-documents.md`, `…-who-implements-this-spec.md` — **deleted in
  `89e5ad3`**, superseded. Recoverable via `git show 786c146:<path>`.

**`0ce2b31` — the merge**

Merge commit of `loop/2026-08-20-spec-corpus-migration` into `master`, `--no-ff`, matching the
repo's PR-merge history. Merged tree is byte-identical to the branch tip. The branch ref still
exists.

**`89e5ad3` — the consolidated exploration**

- `openspec/explorations/2026-08-20-the-row-is-the-spine.md` — **new**, ~250 lines. Finished.
- The four superseded stubs deleted.

**`fa5baff` — confirmations**

- `openspec/explorations/2026-08-20-the-row-is-the-spine.md` — §5 moved to DECIDED; §9 gained the
  file-authority principle, the collision it creates, and the proposed boundary resolution.

**`4314567` — the proposal**

- `openspec/changes/document-adoption/proposal.md` — **new**. Why, what changes, explicit
  Non-Goals, capabilities, impact.
- `openspec/changes/document-adoption/design.md` — **new**. Context, goals/non-goals, decisions
  D1–D7, risks, migration plan, three open questions.
- `openspec/changes/document-adoption/specs/spec-document-adoption/spec.md` — **new**. 8
  requirements, 24 scenarios.
- `openspec/changes/document-adoption/specs/spec-document-authority/spec.md` — **new**. 3 ADDED
  requirements (delta).
- `openspec/changes/document-adoption/tasks.md` — **new**. 9 groups, 38 tasks, split into
  agent-verifiable (§7), human-only (§8) and a user test guide (§9).

## Key decisions

Operator decisions from this session, all recorded in `the-row-is-the-spine.md`:

1. **Item 5 — home stays a document.** No new screen. `spec/agentweave.html` is opened by
   `SpecPage.tsx:41-50` as the manifest home; the operator found its *content* thin. Structure:
   authored narrative + a **map generated from `spec/index.json`** (which already holds `parent`
   and `order` that nothing renders). *Rejected:* a product landing screen — two orders of
   magnitude more expensive for the same want.
2. **Item 9 — agents create documents directly.** *Rejected:* request-and-accept (blocks the agent,
   fights the stated ask) and `unfiled` staging (**the gate is illusory** — the tree is disk-driven
   so unfiled documents are already visible, and a row gets filed on the next reindex).
   *Reason:* `spec_service.save_document:106` already refuses an agent writing a **capability**
   document, so the corpus with real value is protected one layer below the endpoint.
   **Requirement this carries:** restrict `kind` **at creation**, not just at write —
   `create_document` sets `phase=CURRENT` for capability (`spec_lifecycle.py:151`).
3. **Item 11 — complexity tiers, not agent names or model names.** *Rejected:* writing
   `claude-opus-5` into specs — couples a durable corpus to today's lineup. Tier in the spec,
   mapping in the project.
4. **The tier table maps one tier to MANY runners**, and points at **Runners, not model strings** —
   `Runner` already means "reusable execution capability", matching becomes a foreign key on
   `Agent.runner_id`, deletion fails loudly, and `Runner.flags` can carry `effort`.
5. **Parallelism comes from more agents.** *Rejected:* one agent across several conversations —
   `turn_scheduler.py:42` already refuses a second concurrent run per agent, and
   `Conversation.provider_session_id` (`models.py:416`) puts the session on the **conversation**, so
   it would be three sessions sharing no context under one name. Operator: *"it makes things even
   harder because it's hard to track which conversations are active."*
6. **Parallelism is opt-in** — a project setting, max concurrent runs, default 1.
7. **Catalog refresh is a button on the existing worker** (`hub/hub/worker.py`), not a scheduled
   job. *Reason:* a worker records **no `Run` row, deliberately** — one recorded under an agent's
   name makes that agent look busy and stalls its queue.
8. **Trust the file, including phase.** Operator's reason, recorded as a principle: *the file is
   committed and reproduces anywhere; the row never leaves the machine that made it.*
9. **Adoption is a separate route, not a flag** (design D1) — a flag leaves the destructive
   behaviour as the default, one missing parameter away.
10. **Adoption refuses an already-tracked path and reports the disagreement** (design D4) — delivers
    the comparison, stops short of the resolution, because resolution collides with the gate rule.

## Constraints and user directives (verbatim)

- *"I think it could be a table in the project and have a way to update this table."*
- *"Ah yesh one to many is best."*
- *"Was not talking about a schedule worker. But the background worker that we already use for
  checkpoints and naming for example. We could have a button that trigger a worker to do the quick
  research and update."*
- *"yes trust the file. I think we should take a approach of trust the file because this is
  something that gets comited and can be reproduced anywhere in any environment"*
- *"I was finding it thin. I expect to have a overview of the entire project there and the path to
  all other features and specs."*
- *"So each new spec created needs to reflect a little bit on the main spec."*
- *"It should look at the file but it should compare with the database. But it should trust what we
  have on the file."*
- *"Instead of an agent I think we could define which model can do each task."*
- *"We would need a step in the exploration to ask the user which models does he want to use."*
- *"Today we don't look at tasks that can be done in parallel. On the spec we should be able to show
  that as well."*
- *"Also doing work in parallel should be a decision from the user. He could be using a restricted
  tgoken plan and need to do things one at a time."*
- *"You can mark as confirmed."*
- Chosen via AskUserQuestion: **"Not yet"** (do not register the repo as a project), **"Kill the
  port-8020 throwaway Hub"**.
- Standing, from `CLAUDE.md`: never touch the Hub on **port 8010**; stage paths explicitly; never
  mark a task complete on the strength of a plan existing; `hub/hub/static/ui` is committed and must
  be refreshed with `scripts/refresh_ui_bundle.py`; keep the two `spec_manifest` twins in sync by
  hand.
- Standing, from memory: commit each completed checkpoint without asking first; specs must carry
  test guides split into agent-verifiable and human-only.

## Dead ends

- **The `unfiled` staging idea was proposed and withdrawn within one exchange.** It looked elegant —
  agent creates freely, operator "files" it — but `compute_state` is disk-driven so unfiled
  documents are **already visible**, and any created document needs a row (or `save_document`
  cannot write its file), and a row is filed by the next reindex. The gate does not exist. Do not
  re-propose it without inventing an explicit flag first.
- **I asserted "the Spec tab shows nothing" from the handoff without checking**, and had to correct
  it mid-exploration. The lesson is recorded because handoffs 0062 and 0063 both still contain the
  wrong claim: **`GET /specs` is disk-driven.**
- **`git merge -F -` does not read stdin** — `error: could not read file '-'`. Write the message to
  a temp file (`.git/MERGE_MSG_DRAFT.txt`) and pass the path.
- **PowerShell here-strings (`@'…'@`) fail in the Bash tool** — `syntax error near unexpected
  token '('`. Use a `<<'EOF'` heredoc for commit messages.
- **`grep -oP` fails on this machine** — *"-P supports only unibyte and UTF-8 locales"*.
- **Grepping for `aw-payload` found 0 of 34 files** and nearly produced a wrong claim in a stub. The
  real marker is `id="aw-spec-payload"`, which matches **34/34**.
- **`openspec validate --change <name>` is not a flag** — it is `openspec validate <name>`.

## Verification

**Ran, and passed:**

- `py -3.11 -m pytest hub/tests/ -q --ignore=hub/tests/browser` on the merged master →
  **2508 passed, 12 skipped, 1 xpassed, 0 failures** (12m39s).
- `py -3.11 -m pytest tests/ -q` on the merged master → **404 passed, 3 skipped** (13.4s).
- `git diff --stat loop/2026-08-20-spec-corpus-migration master` → **empty**; the merged tree is
  byte-identical to the branch tip, so handoff 0063's verification carries over.
- `openspec validate document-adoption` → **valid**. `openspec status` → **4/4 artifacts complete**.
- Every `file:line` citation in the exploration and the change artifacts was read before being
  cited, including the two block quotes re-checked at `api/v1/spec.py:1049-1053` and
  `spec_render.py:341-345`.
- Payload-block presence confirmed **34/34** in `spec/capabilities/*/spec.html`.
- Payload keys dumped from a real document, confirming **the payload carries no `status`/`phase`** —
  this shaped design D3.

**NOT tested — do not claim otherwise:**

- **No code was written this session.** The proposal is unimplemented; nothing in
  `openspec/changes/document-adoption/` has been executed.
- **Nothing was verified in a browser.** The five UI fixes from handoff 0063 remain jsdom-only and
  **have still not been seen working by a human.**
- **The browser suite was not run** (unchanged since handoff 0061).
- **Nothing pushed. CI has seen none of these 23 commits**, including the database-wipe fix.
- **Adoption's premise that `create_document` cannot touch disk was verified by reading its
  signature** (it takes no workspace), not by executing it.

## Git state

- **Branch:** `master`. **HEAD:** `4314567`. **Working tree clean.**
- **23 commits ahead of `origin/master`**, nothing pushed, no PR.
- `origin/master` remains at `63ef94e`.
- This session added **five commits**: `786c146`, `0ce2b31` (the merge), `89e5ad3`, `fa5baff`,
  `4314567`.
- The branch `loop/2026-08-20-spec-corpus-migration` still exists and is fully merged.
- Untracked and left alone: `.migration/`.

## Next steps

1. **Start the next exploration.** The operator's stated sequence ends here. The carve-up in
   `the-row-is-the-spine.md` §9 orders the remaining work: #2 spec landing page, #3 agent-created
   documents, #4 tiers/dependencies/routing, #5 catalog as data. **Ask which one** — the operator
   said "start the next exploration" without naming it.
2. **Or implement `document-adoption`** — `/openspec-apply-change document-adoption`. All four
   artifacts are ready; task 1.1 is immediately executable.
3. **Push the branch and open a PR.** 23 commits, including the database-wipe fix, unseen by CI.
   **The operator has been asked twice and has not answered.**
4. **Browser-verify the five UI fixes** from handoff 0063 — items 2, 4, 6, 7, 8, all jsdom-only.
5. **Decide `proj-adf8a200`** — the operator's home directory registered as a project.

## Open questions for the user

- **Which exploration next?** (#2–#5 in `the-row-is-the-spine.md` §9.)
- **Push to `origin/master`?** Asked twice, unanswered. 23 commits.
- **Register this repo as a project?** Answered "Not yet" this session; still not registered, and
  adoption's human verification (tasks §8) requires it.
- **Does "trust the file" extend past adoption to re-adoption?** The collision with *"a gate whose
  value lives where the gated party can write it is not a gate"* is recorded but not resolved. Does
  not block adoption.
- **`D-a13`'s shape appeared three times** this session — agent requests a task, agent requests a
  document, worker proposes a catalog entry. Probably one generic mechanism. Undecided.
- **Retire `openspec/specs/`?** Open since handoff 0062.
- **Delete `proj-adf8a200`?** Open since handoff 0063.

## Read on resume

- `openspec/explorations/2026-08-20-the-row-is-the-spine.md` — **first, and possibly the only thing
  needed.** The whole spine, every decision, every open question, with `file:line` for each claim.
- `openspec/changes/document-adoption/design.md` — decisions D1–D7 and the three open questions, if
  implementing rather than exploring.
- `openspec/changes/document-adoption/tasks.md` — task 1.1 is the first executable step.
- `hub/hub/api/v1/spec.py:1107-1157` — `POST /documents`, the weld adoption must not reuse.
- `hub/hub/spec_documents.py:245-273` — `build_index`, where "only documents both on disk and known
  to the Hub are filed" is stated.
- `openspec/explorations/2026-08-20-dogfooding-findings.md` — finding 18, the database destruction,
  still the most important thing in this repo's exploration history.
