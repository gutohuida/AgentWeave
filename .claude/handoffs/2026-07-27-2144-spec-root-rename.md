# Handoff: Unify the spec root — `specs/` → `spec/` — and update the spec role template

**Date:** 2026-07-27T21:44+0100 · **Branch:** `master` · **HEAD:** `968b8db`
**Agent:** Claude Code (Opus 5, `claude-opus-5`)
**Previous handoff:** `.claude/handoffs/2026-07-26-2230-spec-rev9-consistency-pass.md`
(that is a **different, still-live work thread** — the AgentWeave 1.0 spec on branch `agentweave-1-0`,
with **22 unapplied findings**. This handoff does not supersede it. See "Parallel live thread" below.)
**Status:** chunk complete — rename done and committed on both branches; role template edited but **uncommitted**

## Goal

AgentWeave stored durable spec artifacts in `specs/` (plural) while every consumer — the `aw-spec-*` skill
templates and the Hub spec-sync code — resolved `spec/` (singular). The goal was to collapse that to one root
so `/aw-spec-propose` stops being able to silently start a second roadmap tree, and so the spec role template
tells agents the truth about where specs live.

The *why*: this started as a research question in the sibling repo `AICollective` — does
`AgentWeave/specs/` obey the spec-folder structure recommended in
`AICollective/ResearchClub/spec-driven-development/`? The structure itself does obey it (system map → epic
roadmap → feature specs, sliced vertically). The break was purely the directory name, plus two gaps listed
under "Open questions".

## Current state

**Done and committed:**

- `specs/` → `spec/` on `master` as commit `968b8db`, a pure 100%-similarity rename of the one tracked file.
- `agentweave-1-0` merged master (`21aeea0`). Git raised the expected `CONFLICT (file location)` and proposed
  relocating `agentweave-1.0-spec.html` into `spec/`; accepted after verifying byte-identical content
  (3,980 lines, `diff -q` clean against `HEAD:specs/agentweave-1.0-spec.html`).
- Neither branch has any path under `specs/` anymore — verified with
  `git ls-tree -r --name-only <branch> | grep -c "^specs/"` → `0` for both.

**Done but NOT committed:**

- The spec role template, edited in both of its two identical copies (see "Files touched").

**Deliberately untouched:** the ~455+/258− uncommitted content edits to `spec/agentweave-spec.html` (the v0.x
spec). The rename was staged as a *pure* rename via `git update-index --cacheinfo` against the HEAD blob, so
those edits stayed in the working tree and are still uncommitted, per the standing directive below.

The current `spec/` layout:

```
spec/
├─ README.md              (untracked)  navigation index, edited this session
├─ system-map.html        (untracked)  durable scope, domains, contracts
├─ roadmaps/              (untracked)  agentweave-reconstruction.html, slices R1–R6
├─ agentweave-spec.html   (tracked)    v0.x living baseline — has uncommitted edits
└─ agentweave-1.0-spec.html            tracked on `agentweave-1-0` only
```

## Files touched

Everything below is in `C:\Users\huida\Documents\projects\AgentWeave`.

**Committed (`968b8db` on master, `21aeea0` on agentweave-1-0):**
- `spec/agentweave-spec.html` — renamed from `specs/agentweave-spec.html`. Content unchanged by me. **Finished.**
- `spec/agentweave-1.0-spec.html` — renamed from `specs/agentweave-1.0-spec.html` in the merge commit on
  `agentweave-1-0` only. Content byte-identical to rev. 9. **Finished.**

**Edited by me, uncommitted:**
- `src/agentweave/templates/roles/spec.md` — spec role template. Four edits, all mine, all finished:
  (1) responsibilities now name the durable layer under `spec/` (system map, roadmaps, living spec) instead
  of `specs/*.html`; (2) session-start inventory names `spec/` as the single root and lists the real
  sub-paths, with one escape hatch for user projects that still have a legacy `specs/`; (3) new authoring
  rule covering system-map-by-ID reference, roadmap-before-epic, and staying inside a roadmap row's boundary;
  (4) two new anti-patterns — splitting by technical layer, and writing into a second tree.
- `hub/hub/data/roles/spec.md` — **identical shipped twin** of the above, updated by `cp`. No test enforces
  that these two stay in sync; they must be edited together. **Finished.**
- `spec/README.md` — untracked. Tree diagram now says `spec/`, adds `changes/` and `discovery/` rows, and a
  note that `spec/` is the only root. **Finished.**

**Modified in the working tree but NOT BY ME — pre-existing uncommitted work from an earlier session.**
Do not attribute these to the rename, and do not commit them without asking:
- `docs/guides/aw-spec-workflow.md` (+20)
- `src/agentweave/templates/skills/aw-spec-apply.md` (+37/−)
- `src/agentweave/templates/skills/aw-spec-archive.md` (+27/−)
- `src/agentweave/templates/skills/aw-spec-explore.md` (+11/−)
- `src/agentweave/templates/skills/aw-spec-propose.md` (+87/−)
- `src/agentweave/templates/skills/aw-spec-technical-explore.md` (+13)
- `src/agentweave/templates/skills/references/html-spec-conventions.md` (+105/−)
- `tests/test_skill_templates.py` (+4)
- `spec/agentweave-spec.html` (+455/−258) — the v0.x edits under the standing "leave it" directive

`src/agentweave/templates/roles/spec.md` and `hub/hub/data/roles/spec.md` contain **both** my edits and that
earlier session's edits (evidence/coverage and spec-lifecycle language) interleaved. `git diff --stat` shows
32 changed lines each; roughly 20 are mine. They cannot be separated without hunk-level staging.

- `validate_spec.py` — untracked, belongs to the 1.0 thread. **Two-line fix by me**: line 1 docstring and
  line 18 `PATH` both said `specs/agentweave-1.0-spec.html`; the rename broke it, so both now say `spec/`.
  Uncommitted, and **unverified** — see "Parallel live thread". **Finished, pending a run.**

**Untracked, pre-existing, leave alone:** `kimi-export-session_-20260725-135928.md`, `.claude/handoffs/`.

## Key decisions

1. **Rename `specs/` → `spec/`, not the reverse.** Chosen because the shipped code already commits to
   `spec/`: `_discover_spec_files()` at `src/agentweave/watchdog.py:36-51` hardcodes `Path("spec")`, and all
   five `aw-spec-*` skill templates write `spec/changes/`, `spec/discovery/`, `spec/roadmaps/`.
   *Rejected:* editing the five skill templates to say `specs/` — larger blast radius, and it would have
   required also changing shipped Python. *Rejected:* leaving both roots — that is the bug.

2. **Rename on master AND propagate into `agentweave-1-0` immediately** (user chose this from three options).
   *Rejected:* master-only, fix at merge time — would have left a resurrected `specs/` for whoever merges the
   1.0 branch. *Rejected:* wait until 1.0 merges — leaves the break live and the skills writing to a second tree.

3. **Keep the v0.x content edits out of the rename commit** (user chose this). Implemented by resetting the
   index entry to the HEAD blob after `git mv`, so the commit is a pure rename and the edits stay unstaged.
   *Rejected:* committing rename + v0.x edits together — reverses a decision the user has re-affirmed across
   four prior sessions.

4. **Did not commit the role-template edits.** They are entangled with the earlier session's uncommitted
   changes in the same two files. Left for the user to decide whether to commit together or split.

5. **Wrote this handoff into AgentWeave's existing `.claude/handoffs/`** rather than the session's cwd
   (`AICollective`), because all the live state and next steps are in AgentWeave. Note the session's primary
   working directory was `C:\Users\huida\Documents\projects\AICollective` — **resume from AgentWeave.**

## Constraints and user directives (verbatim)

From this session:
- On the branch question: **"Rename both, merge master in"** — "Rename specs/ → spec/ on master, then merge
  master into agentweave-1-0 and move agentweave-1.0-spec.html to spec/ there too."
- On the v0.x edits: **"Rename, leave uncommitted"** — "Perform the rename; the v0.x content edits ride along
  and end up staged but uncommitted. Nothing is lost, and I commit only the rename-related changes — the v0.x
  edits stay for you to decide on later."
- **"Can you eddit the role to reflect all the changes as well?"** (the request that produced the role edits)

Carried forward from `.claude/handoffs/2026-07-26-2230-spec-rev9-consistency-pass.md`, still in force:
- `.claude/handoffs/` → **"Leave as-is"** (untracked, not gitignored).
- v0.x `specs/agentweave-spec.html` edits → **"Leave it"**. **"Do not re-ask unprompted."**
- `kimi-export-session_-20260725-135928.md` → leave.

Global (from this environment): commit or push only when the user asks. The user has **not** asked for a push;
`968b8db` is unpushed on master and `21aeea0` is unpushed on `agentweave-1-0`.

## Dead ends

- **First commit message came out mangled.** I used PowerShell here-string syntax (`@'...'@`) inside the
  **Bash** tool, which is Git Bash — the literal `@` characters ended up as the subject and body. Fixed with
  `git commit --amend -F -` and a real heredoc. In this repo, use `-F - <<'EOF'` for multi-line git messages
  from the Bash tool; `@'...'@` only works in the PowerShell tool.
- **`grep -rn "specs/"` across the whole repo timed out at 120s** (it walks `node_modules`, `.venv`, `site/`).
  Use the Grep tool scoped to `src/` and `hub/`, or add prunes.
- **Near-miss worth knowing:** the Hub API route `/project/specs/sync` (`src/agentweave/transport/http.py:481`,
  `hub/hub/api/v1/spec.py:42`) and the React query key `['specs']` all contain "specs" but are **unrelated to
  the filesystem directory**. Do not "fix" them.

## Verification

**Ran and passed:**
- `.venv/Scripts/python.exe -m pytest tests/test_roles.py tests/test_skill_templates.py -q` → **44 passed**
  in 0.74s, after the role edits. (Note: the repo venv is `.venv/`; the default `python` on PATH is a
  different interpreter with no pytest installed.)
- `git cat-file -p HEAD:specs/agentweave-1.0-spec.html | diff -q - spec/agentweave-1.0-spec.html` → identical.
- `git ls-tree -r --name-only master | grep -c "^specs/"` → `0`; same for `agentweave-1-0` → `0`.
- `git diff --cached --stat -M` before committing → `{specs => spec}/agentweave-spec.html | 0` (pure rename).
- `diff -q src/agentweave/templates/roles/spec.md hub/hub/data/roles/spec.md` → identical after the `cp`.

**NOT tested:**
- The **full test suite** was never run — only the two template/role test files.
- `_discover_spec_files()` was **not** exercised at runtime; the claim that it now resolves correctly is from
  reading `watchdog.py:36-51`, not from running Hub spec sync.
- The Hub Spec tab was **not** opened or visually checked.
- No linter (`ruff`) was run.
- Nothing on `agentweave-1-0` beyond the content diff was tested. **`validate_spec.py` was not run at all** —
  I repaired its hardcoded path but could not execute it, because its target file exists only on
  `agentweave-1-0` while this session ended on `master`. Treat the 1.0 spec as unvalidated since rev. 9.

## Git state

**AgentWeave** (`C:\Users\huida\Documents\projects\AgentWeave`):
- Branch `master`, HEAD `968b8db`, **dirty**. 1 unpushed commit (`968b8db`).
- Branch `agentweave-1-0`, HEAD `21aeea0` (merge), unpushed. Its 3 prior commits `d60c1e3`, `51c11e5`,
  `47ff679` are intact.
- Uncommitted modified: the 11 paths listed under "Files touched" (2 mine, 9 pre-existing).
- Untracked: `.claude/handoffs/`, `kimi-export-session_-20260725-135928.md`, `spec/README.md`,
  `spec/roadmaps/`, `spec/system-map.html`, `validate_spec.py`.

**AICollective** (`C:\Users\huida\Documents\projects\AICollective`, the session cwd):
- Branch `spec-research-validation`, HEAD `d60f299`, **clean**, no upstream. Untouched this session — it was
  read only, as the source of the spec-structure research.

## Parallel live thread — do not lose this

`.claude/handoffs/2026-07-26-2230-spec-rev9-consistency-pass.md` describes the AgentWeave 1.0 spec work on
branch `agentweave-1-0`, with **22 of 28 consistency findings still unapplied**. That thread is unfinished and
independent of this one.

**My rename invalidated 12 path references in that handoff** — it says `specs/agentweave-1.0-spec.html`
throughout; the file is now `spec/agentweave-1.0-spec.html`. Anyone resuming the 1.0 thread must mentally
substitute `spec/` for `specs/`.

`validate_spec.py` **was** broken by the rename and I fixed it: `PATH` on line 18 and the module docstring on
line 1 both said `specs/agentweave-1.0-spec.html`, now `spec/`. This edit is **uncommitted** and the file is
untracked. **I could not run it to confirm** — `spec/agentweave-1.0-spec.html` exists only on branch
`agentweave-1-0`, and this session ended on `master`. Run `python validate_spec.py` from `agentweave-1-0`
before trusting it.

I overwrote `.claude/handoffs/LATEST.md` to point at this handoff, per the handoff skill. To resume the 1.0
thread instead, read the rev-9 file above directly rather than following `LATEST.md`.

## Next steps

1. **Decide what to do with the role-template edits.** Run
   `git diff src/agentweave/templates/roles/spec.md` and read the 32 changed lines. They mix my four edits
   with an earlier session's evidence/coverage and lifecycle language. Either commit both files together
   (`src/agentweave/templates/roles/spec.md` and `hub/hub/data/roles/spec.md` — they must move together), or
   split with `git add -p`. Nothing else in the tree needs to move with them.
2. **Fix `aw-spec-archive.md:81`**, which still offers to merge spec files into `spec/specs/` — a third
   location nothing else references. Change it to `spec/` or drop the prompt. That file already has
   pre-existing uncommitted edits, so fold it into whatever commit resolves step 1.
3. **Close the Hub-sync gap.** `_discover_spec_files()` (`src/agentweave/watchdog.py:36-51`) matches only
   `spec/spec.html` and `spec/changes/*/spec.html`, so `spec/agentweave-spec.html`, `spec/system-map.html`,
   and `spec/roadmaps/*.html` never reach the Hub Spec tab. Either rename the baseline to `spec/spec.html`
   (matches the CLI help text at `src/agentweave/cli.py:2735`) or widen the glob. The second is the better
   fix but changes shipped behavior — ask first.
4. **Decide whether to track the durable spec artifacts.** `spec/README.md`, `spec/system-map.html`, and
   `spec/roadmaps/` are untracked. The research in `AICollective/ResearchClub/spec-driven-development/` is
   explicit that spec artifacts belong in version control alongside code.
5. **Populate the feature-spec layer.** `spec/roadmaps/agentweave-reconstruction.html` declares slices R1–R6
   pointing at child specs under `spec/changes/<name>/spec.html`; zero exist. The hierarchy is declared but
   only two of three layers are populated.
6. **Push, if wanted.** `968b8db` (master) and `21aeea0` (agentweave-1-0) are both unpushed. Not yet requested.

## Open questions for the user

- Commit the role edits together with the earlier session's uncommitted skill-template changes, or split them?
- For the Hub-sync gap (step 3): rename the baseline to `spec/spec.html`, or widen `_discover_spec_files()` to
  include the system map and roadmaps? The latter changes shipped product behavior.
- Should `spec/README.md`, `spec/system-map.html`, and `spec/roadmaps/` be committed?
- Should `.claude/handoffs/` be gitignored? It is currently untracked but not ignored. Prior sessions said
  "leave as-is"; flagging once, not re-asking.

## Read on resume

- `.claude/handoffs/2026-07-26-2230-spec-rev9-consistency-pass.md` — the parallel 1.0 thread with 22 open
  findings; its `specs/` paths are stale.
- `src/agentweave/templates/roles/spec.md` — the file with uncommitted, entangled edits that step 1 resolves.
- `src/agentweave/watchdog.py` (lines 36–51) — `_discover_spec_files()`, the source of the step-3 gap.
- `spec/README.md` — the current spec-root layout and its stated rules.
- `src/agentweave/templates/skills/aw-spec-propose.md` — the decomposition/roadmap contract the role template
  now mirrors; also step 2's sibling file.
- `C:\Users\huida\Documents\projects\AICollective\ResearchClub\spec-driven-development\spec-decomposition.md`
  — the recommended structure this whole exercise was measured against.
