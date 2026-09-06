# Tasks — an unread editor cannot overwrite

Implementation is the night window's. Nothing here is complete on the strength of this plan
existing; only verified implementation closes a task.

## 1. The page

- [ ] 1.1 Read the query's full state in `hub/ui/src/components/instructions/InstructionsPage.tsx:9`
  — `data`, `isLoading`, `isError`, `error`, `refetch` — instead of `{ data, isLoading }`.
- [ ] 1.2 Replace the two-branch render at `:45` with three branches in this order: `data` present →
  the editor exactly as today; `isError` → the failure block; otherwise → the existing skeleton.
  The `data`-first ordering is load-bearing (see `design.md`) — an `isError`-first ordering would
  take a loaded editor away from an operator mid-edit on a background refetch failure.
- [ ] 1.3 The failure block: a `role="alert"` region naming what could not be loaded, the sentence
  from `readableApiError(error, <fallback>)`, and a Retry control calling `refetch()`. The fallback
  string is what a dropped connection produces — no `ApiError`, so nothing to quote — and it must
  say that nothing stored has been changed.
- [ ] 1.4 Gate the write: Save issues no PUT unless `data` is present. Not rendering Save in the
  failure block is an acceptable implementation of this; adding `|| isError` to `disabled` is not,
  because it leaves the `data === undefined` route open.
- [ ] 1.5 Leave `hub/hub/api/v1/instructions.py` alone. The server-side guard is intact and the
  empty string stays a legitimate value — whether a PUT should confirm before blanking non-empty
  stored content is the operator's open question, not part of this change.

## 2. Unit coverage — `hub/ui/src/__tests__/instructionsUnreadEditor.test.tsx`

Each of these must fail against the pre-change component. Mutation-check by reverting the guard, not
by reasoning about it.

- [ ] 2.1 Failed load renders no textarea and an announced failure.
- [ ] 2.2 **The assertion that carries the requirement:** with the load failed, no PUT is issued by
  any interaction with the screen. Assert on the mutation/fetch, not on the presence of a `disabled`
  attribute — a test that only asserts markup passes against a page that renders the error *and* the
  textarea.
- [ ] 2.3 Retry calls the query again and, on success, presents the pre-filled textarea.
- [ ] 2.4 A successful load followed by a failing refetch keeps the textarea and its content.
- [ ] 2.5 Project change with the new project's load failing presents no textarea holding the
  previous project's content.
- [ ] 2.6 The success path is unchanged: load, edit, Save, confirmation.

## 3. The bundle

- [ ] 3.1 `cd hub/ui && npm run build`, then `python scripts/refresh_ui_bundle.py`
  (`make ui` is unavailable in Git Bash on this machine). Commit `hub/ui/src` and
  `hub/hub/static/ui` together. The drive reads the **served** bundle; skipping this makes the drive
  re-measure the old page and report success.

## 4. The drive — this is what closes the change

- [ ] 4.1 Invert `scripts/drive/t_d4_instructions_failed_load.py`'s expectations for the two failure
  columns: textarea absent, Save absent-or-inert, a stated failure present. Its baseline column must
  keep passing **unchanged**.
- [ ] 4.2 Turn its end-to-end read-back from a destruction check into a preservation check: with the
  Hub reachable again, interact with the screen and assert the stored content is byte-identical to
  what it was before.
- [ ] 4.3 Run it against a fresh Hub on `:8011` started from source from `hub/`, on a throwaway
  project. Never `proj-5e960453` or `proj-18e5d4e0`; never `:8000`. No agent turn is needed, so
  nothing binds a model.
- [ ] 4.4 Drive the retry by hand as an operator would: stop the Hub, open the page, see the failure,
  start the Hub, press Retry, confirm the stored text appears. This is the half no unit test reaches.

## 5. Close it out

- [ ] 5.1 `cd hub/ui && npm run lint`. Python paths are untouched, so the Python lint set is not
  required — say so rather than skipping it silently.
- [ ] 5.2 Set `F271`'s `**Status:**` line in `scripts/drive/FINDINGS.md` to `fixed <sha>`, and record
  in it that the cross-project variant it left unfalsified is now closed by construction rather than
  by measurement.
- [ ] 5.3 `openspec-sync-specs` into `openspec/specs/project-instructions/spec.md`, then archive.
