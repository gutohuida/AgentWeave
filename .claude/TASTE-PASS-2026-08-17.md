# Taste pass — 2026-08-17

## What a taste pass is

Six changes from the 2026-08-16 batch are code-complete. Every task an agent could verify is
ticked. What remains — 21 tasks — are the ones each spec deliberately marks **human-only**: not
"does the click work" (tests already prove that) but "does this *read* right, does this *feel*
proportionate." No test can answer them, and I can't either. They need your eye.

Ticking them closes six changes for archival, which is what gates the dogfooding trial.

Each item below is one open task. Answer the question, and either tick the task or write the
objection next to it. **A "no" is a better outcome than a reluctant yes** — that's the whole point
of parking these rather than letting the builder self-certify.

## The Hub is running

- **http://127.0.0.1:8010** — already started, on current `master` (`ff16a62` = the v1.0.0 tag).
- UI bundle verified current: zero UI source changes since it was built, so what you see is what
  shipped.
- Data: the trial Hub's DB, backed up first to `hub/data/agentweave.db.bak-pre-taste-1729`.
- Projects: **aw-loop10** (has the content) and **AgentWeave** (empty).

Stop it with: `powershell -Command "Stop-Process -Id 24788 -Force"` — or ask me.

> **Do not delete or modify `aw-loop10`.** The delete-project tasks explicitly say so; it holds
> parked judgement work.

---

## Part 1 — what you can judge right now

Grouped by screen so you aren't jumping around. ~15 minutes.

### Screen: the spec document
Open **aw-loop10 → Spec →** the one document
(`notify-window-graded-notification-urgency…`, phase `approved`).

- [ ] **Does it read as colourful and scannable, or still "texty"?** Look in **both light and
      dark**. *(spec-surface-legibility 7.1)*
- [ ] **Does the background actually match, to the eye?** Your original complaint was a felt
      mismatch, not a variable value — so judge it by looking, both themes.
      *(spec-surface-legibility 7.2)*
- [ ] **Does "Archive" read as final** — clearly a different kind of action from the reversible
      phase moves beside it? *(the-corpus-keeps-what-shipped 10.1)*

### Screen: the board
Open **aw-loop10 → Board**. Five tasks: 2 rejected, 2 approved, 1 completed.

- [ ] **Does the board read as tidy, not broken?** No empty-looking column or visual gap.
      *(the-board-scoped-by-document 5.1)*
- [ ] **Does the drawer feel like Jira, or like something else?** Open a task and read the panel.
      *(spec-surface-legibility 7.3)* — weaker than intended here: no task in this DB has a
      document link, so there are no requirement chips to judge. See Part 2.

### Screen: a conversation
Open **aw-loop10 → Agents → verifier** (or builder/speccer) and read a past turn.

- [ ] **Does rendered Markdown read better, or add visual noise?** Ideally a turn with a code
      block, a list and a link. Both themes. *(conversation-formatting 6.1)*
- [ ] **Regression check: does anything that used to read fine now read worse?** These
      conversations predate the change, which makes them the right test — they were recorded
      before `payload.tool`/`payload.input` had any reason to be read this way.
      *(conversation-formatting 6.5)*

### Anywhere: the command palette
Open it (Cmd/Ctrl-K).

- [ ] **Does it feel fast, and find the right things without exact-match typing?** Try an agent
      name, a partial task title, and the spec document. Compare against Cursor / Claude Code /
      Linear, which is the comparison the survey used. *(conversation-formatting 6.4)*
      — thin corpus here (5 tasks, 1 doc, 3 agents); judge responsiveness and matching, not recall.

### Screen: the board and document — a declaring task, rejected evidence, an archived doc
Seeded by the autonomous run (iteration 9, 2026-08-17T21:21+01:00) against the **live trial Hub
API**, in the empty **AgentWeave** project (`proj-5e960453`), never `aw-loop10`. The document is
`spec/changes/quiet-hours-for-agent-notifications/spec.html` — already `archived` from A2's own
fixture testing (iteration 2, untouched since). One task, `task-a4f8e3f4` ("Record a quiet window
per project"), was created against it with `requirement_ids: ["FR-1", "FR-5"]` and
`spec_document: <that path>`, then walked through the real transition machine to `approved`
(`pending → in_progress → completed → under_review → approved`, all via `PATCH .../tasks/{id}`).
One evidence row (`ev-5e7bd066`) was recorded against FR-1 and then rejected via
`POST .../spec/evidence/{id}/decision`.

Verified live, against the same endpoints the UI itself calls, before writing this section:
- `GET /tasks?exclude_archived_completed=true` → `[]` — the task is correctly excluded (its
  document is archived and its status, `approved`, is terminal). This is what "the board reads as
  tidy" (5.1) depends on.
- `GET /tasks?spec_document_id=spdoc-77157ff0` → `[task-a4f8e3f4]` — the document-scoped fetch that
  the "N tasks declared by this document" link (5.2) and board↔document navigation (7.4) use.
- `GET /project/spec/coverage?document=...` → FR-1 `state: "rejected"`, FR-5 `state: "in_progress"`
  — the two states 7.5 asks you to tell apart are genuinely different requirements in this fixture,
  not just different labels on the same one.

- [ ] **7.4** — open the document, find the "N tasks declared" link near the coverage detail
      (there should be exactly 1), click it, confirm the board switches to a filtered view showing
      `task-a4f8e3f4` with a "Showing N tasks…" banner. Does the navigation feel connected, or like
      two screens with a link between them? *(spec-surface-legibility 7.4)*
- [ ] **7.5** — on the document, find FR-1's coverage entry; confirm it reads `rejected` (not
      `in_progress` — compare against FR-5, which is `in_progress`). Then try proposing a document
      with an over-sized task (or reuse the existing over-sized-task refusal path from 5858014's
      work if still live) and confirm the refusal reads plainly. *(spec-surface-legibility 7.5)*
- [ ] **5.1 (full form)** — on the **Board**, confirm `task-a4f8e3f4` does **not** appear in the
      default view (it's `approved`, from an archived document). Open the document and confirm the
      task is still reachable from there, and that clicking through shows it. *(the-board-scoped-by-document 5.1)*
- [ ] **5.2** — on the document panel, does the "tasks declared by this document" link read as the
      same kind of control as the coverage bar's per-requirement links (same panel, same visual
      language), or do they compete/look like two different features?
      *(the-board-scoped-by-document 5.2)*

### Screen: Projects — deleting one
A disposable project now exists in the trial Hub, seeded by the autonomous run
(`autonomous/2026-08-17-archive-and-hub-app`, iteration 8, 2026-08-17T21:08+01:00) via
`POST /api/v1/projects/create` against the live Hub — no direct DB write, no Hub restart.

- **`proj-b44fac0c`, "Throwaway (taste pass)"** — working directory
  `testbed/throwaway-taste-project/` (gitignored, real, exists, currently empty).

This unblocks the *disposable-project* half of 6.1 — it does not add an agent or a conversation to
it, which the task also asks for and is a normal few clicks in the UI, left for you:

- [ ] **6.1** — in the UI, add an agent and start a conversation on `proj-b44fac0c`, then delete it.
      Confirm it disappears from the rail and that `testbed/throwaway-taste-project/` is untouched
      on disk afterward. *(delete-project-api 6.1)*
- [ ] **6.2** — if the screenshot harness (`scripts/uishot.py`) is available, capture the
      confirmation dialog and resulting state, both themes. *(delete-project-api 6.2)*
- [ ] **6.3** — judge the confirmation's proportionality: does typing the project's name feel like
      the right amount of friction, or excessive/insufficient? *(delete-project-api 6.3)*

**6.4 is still blocked** — it needs the *last* project deleted on a **scratch Hub instance**, not
the live trial Hub (`proj-5e960453` and `proj-ff695d96` must stay). That's a separate throwaway Hub
process this driver did not start, since spinning up a second Hub instance is closer to
infrastructure than fixture seeding.

---

## Part 2 — blocked, and why

These need content this database doesn't have. I did not fake it, because judging seeded
content that doesn't resemble real use is worse than not judging.

| Task | Needs |
|---|---|
| corpus **10.2** (capability document's phase bar quiet?) | a `capability`-kind document — none exists |
| many-named-loops **7.1, 8.1, 8.2** | jobs and loops — none in this DB |
| delete-project **6.4** (empty-state after deleting the last project) | a *second, scratch* Hub instance to delete down to zero — not the live trial Hub |

**Two need live agent turns, which cost money:**

- conversation-formatting **6.2** — do per-tool icons help scan a long tool-call sequence? Needs a
  real turn that reads several files, runs a bash command, and edits one.
- conversation-formatting **6.3** — does the edit diff read cleanly against a *real* file edit, not
  the synthetic fixture?

That's a spend decision, so it's yours. A runner must be bound first.

---

## What I can set up next, if you want it

1. ~~A throwaway project~~ — **done** (iteration 8, see above): unblocks 6.1-6.3. 6.4 needs a
   second, scratch Hub instance, not more seeding on this one.
2. ~~Seed a declaring document + tasks + evidence, and archive one~~ — **done** (iteration 9, see
   above): unblocks 7.4, 7.5, 5.1, 5.2.
3. **A capability document and a job with a loop** — unblocks 10.2, 7.1, 8.1, 8.2 (~15 min).
4. **Bind a runner and drive one real agent turn** — unblocks 6.2, 6.3 (costs tokens).

Doing 3 would take the pass from 15 judgeable items to 18.
