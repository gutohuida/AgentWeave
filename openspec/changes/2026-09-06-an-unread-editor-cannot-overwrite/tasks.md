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
  (`isLoadingError` is the library's own name for `isError && !hasData` and is an equivalent
  spelling; R2.) Optional, not required: key the editor by project id so `content` cannot outlive a
  project switch — see the R2 residual in `design.md`.
  **R3: copy the shape from `components/environment/WorktreesPanel.tsx:44-62`**, which already renders
  these three branches in the same `SettingsSection` family — with the one deliberate divergence that
  it tests `error` first and this page tests `data` first, for the reason in the line above (its list
  is read-only; this one is typed into). Note also that the session disclaimer (`:63-74`) lives
  inside the block being gated, so it travels with the textarea and is correctly absent from the
  failure and loading states — the delta's "Disclaimer shown" scenario was conditioned on the read in
  R3 to match.
- [ ] 1.3 The failure block: a `role="alert"` region naming what could not be loaded, the sentence
  from `readableApiError(error, <fallback>)`, and a Retry control calling `refetch()`. The fallback
  string is what a dropped connection produces — no `ApiError`, so nothing to quote — and it must
  say that nothing stored has been changed.
- [ ] 1.4 **Gate the write, and note that 1.2 does not do it for you (R2).** Save is passed to
  `SettingsSection` as `actions` (`:36-43`) and rendered in the heading
  (`components/environment/SettingsSection.tsx:58`), a sibling of the `{children}` (`:60`) that holds
  the branch 1.2 rewrites — so the three-branch render leaves Save on screen in every state,
  including the skeleton, which is a live one-click blanking path today. Either move the control
  inside the gated region or make `actions` conditional on the same `data` test. Adding
  `|| isError` to `disabled` is **not** sufficient: it leaves both the `data === undefined` routes
  open, the in-flight one on every visit.
- [ ] 1.5 **Keep the failure inside `{children}`, not in place of the section (R3).**
  `project-environment-settings`'s *A configuration section states what it governs* requires every
  section to open with its title and a statement of what it governs. `SettingsSection` renders both
  in the heading, outside the branch — so replacing the branch is conforming and replacing the whole
  `<SettingsSection>` with a failure panel would breach a shipped requirement. Cheap to get wrong.
- [ ] 1.6 **Report a failed save, which this page does not do today (R3).** `saveMutation.isError`
  is never read: `:20-26` binds only `isSuccess`, so a rejected PUT re-enables the button, shows
  nothing, and leaves the operator believing the save landed.
  `project-environment-settings`'s *Saving reports its outcome* already requires that "a failure
  SHALL state why in the section rather than only in a log", so this is a **shipped requirement the
  component breaches today** — found by reading that spec in full, not created by this change, and
  no delta is needed because the requirement already binds. It is in scope because it is the same
  component and the same lie: a page that starts stating read failures while still swallowing save
  failures is *less* coherent than one that stated neither. Use `readableApiError(saveMutation.error,
  …)` in a `role="alert"` beside the button, as `ProjectSettingsPanel.tsx:319` does. Its unit test
  is 2.8.
- [ ] 1.7 Leave `hub/hub/api/v1/instructions.py` alone. The server-side guard is intact and the
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
- [ ] 2.3 **R2:** with the read still in flight (the query never settling), no PUT is issued by any
  interaction with the screen. This one fails against the pre-change component for a reason 2.2 does
  not cover — the skeleton is rendered and Save is enabled beside it.
- [ ] 2.4 Retry calls the query again and, on success, presents the pre-filled textarea.
- [ ] 2.5 A successful load followed by a failing refetch keeps the textarea and its content.
- [ ] 2.6 Project change with the new project's load failing presents no textarea holding the
  previous project's content.
- [ ] 2.7 The success path is unchanged: load, edit, Save, confirmation.
- [ ] 2.8 **R3:** a save that is rejected states the failure in the section. Fails against the
  pre-change component, which renders nothing at all on `saveMutation.isError`.

## 3. The bundle

- [ ] 3.1 `cd hub/ui && npm run build`, then `python scripts/refresh_ui_bundle.py`
  (`make ui` is unavailable in Git Bash on this machine). Commit `hub/ui/src` and
  `hub/hub/static/ui` together. The drive reads the **served** bundle; skipping this makes the drive
  re-measure the old page and report success.

## 4. The drive — this is what closes the change

- [ ] 4.1 Invert `scripts/drive/t_d4_instructions_failed_load.py`'s expectations for the two failure
  columns: textarea absent, Save absent-or-inert, a stated failure present. Its baseline column must
  keep passing **unchanged**.
- [ ] 4.1b **R2: add the in-flight column the harness does not have.** Hold the GET open rather than
  aborting it or answering 500 — the same route-interception the harness already uses for the other
  two columns — and assert, while the skeleton is on screen, that Save is absent or inert and that
  interacting with the screen issues no PUT. Then read the stored content back and assert it is
  byte-identical. This is the state `F271` never measured, and against the pre-change bundle it is a
  reproduction of a second destruction path, so run it once **before** the fix as well.
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
