# Tasks — checkpoint configuration surface

## 1. Stop the settings panel discarding what it cannot see

- [x] 1.1 Regression test first, at the API boundary: configure checkpointing, then save a project
      setting that has nothing to do with it, and assert the checkpoint configuration survives.
      **It must fail against today's code**, or it is testing nothing
- [x] 1.2 `useProjectSettings(projectId)` reading `GET /settings`, so the panel holds the whole
      representation rather than the six fields `ProjectSummary` happens to carry
- [x] 1.3 The panel edits that representation and submits it whole. A field added to
      `ProjectSettings` later must be round-tripped by a panel that has never heard of it
- [x] 1.4 Record the hazard where it is created — `PUT /settings` replaces, and its defaults make a
      partial submission look like a deliberate reset rather than an omission

## 2. Project-level checkpoint controls

- [x] 2.1 Mode: off / offered / automatic, each described by what it actually does
- [x] 2.2 Threshold: proportion or thousands of tokens, stored canonically, entered in the
      operator's units
- [x] 2.3 Both readings where the window is known — `describe_threshold`'s output, on screen
- [x] 2.4 Notes point, refused unless below the threshold
- [x] 2.5 Generating runner and model, from the registered runners and the catalog
- [x] 2.6 Tests

## 3. Agent-level override

- [x] 3.1 The threshold override, presented as a whole threshold or none — never half
- [x] 3.2 The two access grants, closed by default and separately settable
- [x] 3.3 Tests, including that clearing the override returns the agent to the project's threshold

> **The fix is a merge, not a fuller form.** Making the panel round-trip everything fixes the
> panel; it leaves the trap for the next client. `PUT /settings` now merges with
> `exclude_unset=True`, so omission means unchanged and an explicit null still clears — which is
> what the note on `conversation_title_mode` ("defaulted so a client written before this field
> still round-trips") was reaching for and did not achieve. Validation runs against the **merged**
> state, not the fragment, or a lone notes value would be refused for wanting a threshold the
> project already has.

## 4. Verification

- [x] 4.1 `pytest hub/tests/`, `npx vitest run`, `npx tsc --noEmit`, `ruff check`
- [x] 4.2 `npm run build` + copy to `hub/hub/static/ui`, confirmed with `diff -rq`
- [x] 4.3 Live: configure checkpointing in the UI, save an unrelated setting, confirm it survives
