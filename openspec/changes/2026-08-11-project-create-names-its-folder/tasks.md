# Tasks — Creating a project takes a parent and a name

## 1. Check the premise before building on it

- [x] 1.1 Confirm against the running code that `POST` create already accepts a composed target and
      already defaults the project name to the folder name — `create_new(body.path, name=body.name)`
      with `name or canonical.path.name`. If either is false, the backend work is in scope and this
      task list is wrong. **This change exists because an unverified assumption about this flow
      shipped a control that could not work; do not repeat it.**
      **Confirmed:** `hub/hub/api/v1/projects.py:279` is `create_new(body.path, name=body.name)`;
      `create_new` delegates to `open_existing(target, name=name, ...)`, and
      `hub/hub/project_lifecycle.py:85` is `name=name or canonical.path.name`. Both premises
      hold, so no backend change. Corroborated by 4.8: the hub suite is unmoved at 1512.
- [x] 1.2 Confirm both browse affordances return an existing directory: the host folder dialog and
      the in-Hub `DirectoryPicker`. This is the fact that makes create mode's current field
      unusable, so it should be established rather than asserted.
- [x] 1.3 Confirm `canonicalize_project_directory` is applied to the composed target's parent on the
      Docker path, so workspace-root confinement is unaffected by composing client-side.
      **Confirmed:** `project_lifecycle.py:101-105` canonicalizes `target.parent` before creating,
      so the parent is what must lie beneath the mounted root — exactly as for a typed path.

## 2. Create mode takes a parent and a name

- [x] 2.1 `ProjectManagerModal.tsx` — in create mode, replace the single path field with a parent
      directory field and a project name field (design D1). Open mode keeps its directory field and
      its optional display-name override (D2).
- [x] 2.2 Point both Browse affordances at the parent field in create mode — the host dialog's
      `onSuccess` and the in-Hub picker's selection. Browsing must produce a directly usable value.
- [x] 2.3 Compose the submitted target as `<parent>/<name>` using the separator style of the parent
      the operator supplied (D4), and submit it as `path` with no `name`, so the backend's existing
      folder-name fallback supplies the project name.
- [x] 2.4 Drive the existing `data-testid="project-path-preview"` from the same composed value that is
      submitted — derived, never re-typed alongside it (D4).
- [x] 2.5 Remove the separate display-name field from create mode only (D2). It stays in open mode.
- [x] 2.6 Disable confirm until both a parent and a valid name are present.

## 3. Name validation

- [x] 3.1 Refuse a name that is empty or whitespace, contains `/` or `\`, or is `.` or `..` (D3).
- [x] 3.2 **Refuse, do not sanitise.** Rewriting `my/project` into `my-project` would create a
      directory the operator did not ask for at a path they did not see. The message names the
      problem.
- [x] 3.3 Leave the server as the authority on platform-specific rules — Windows reserved names,
      trailing dots, `<>:"|?*`. The client check is a fast message, not the gate (D3). Confirm the
      server's `project_create_failed` error still surfaces legibly in the form.

## 4. Tests — agent-verifiable

- [x] 4.1 Update `hub/ui/src/__tests__/projectManagerDirectoryPicker.test.tsx` for create mode: a
      browsed directory lands in the parent field, not the project path.
- [x] 4.2 Create mode submits `<parent>/<name>` as `path` — assert on the actual mutation payload,
      since the defect being fixed is that what the operator sees and what is sent had drifted apart.
- [x] 4.3 The preview shows the composed absolute path and matches the submitted payload.
- [x] 4.4 A name with a separator, a traversal name, and an empty name are each refused, and no
      mutation fires.
- [x] 4.5 Open mode is unchanged — its directory field and optional display name still behave as
      before. This is the regression most likely to be caused by editing a shared component.
- [x] 4.6 Windows-style and POSIX-style parents each compose with the separator the operator supplied.
- [x] 4.7 `npx vitest run` green; record against the 767 baseline. `npx tsc --noEmit` clean.
      **805 passed across 82 files** (784/81 at the start of this change; +21 in one new file).
- [x] 4.8 `pytest hub/tests/ -q` green — expected untouched, but 1.1 could have moved it into scope.
      **1512 passed, 10 skipped — identical to before this change**, which is the evidence that
      1.1's "no backend change" finding was right rather than merely asserted.
- [x] 4.9 Rebuild `hub/ui`, copy `dist` over `hub/hub/static/ui`, confirm with `diff -rq`.

## 5. Verification — human-only (the operator runs these)

The agent cannot open a host folder dialog or judge whether a form reads as obvious.

- [ ] 5.1 Does Browse now give you something you can use without editing it?
- [ ] 5.2 Is it obvious, before you confirm, where the project will be created?
- [ ] 5.3 Does removing the separate display name in create mode feel like a loss, or like one fewer
      thing to answer?

## 6. User test guide

**Setup.** A running Hub. You will create two throwaway projects and can delete their folders after.

1. **Browse works in create mode.** Choose Create a new project, click Browse, and pick any existing
   folder.
   *Expect:* the folder lands in the parent field, and a separate box asks for a project name.
   *Failure looks like:* being handed a full path you have to edit — the original defect.

2. **Name it once.** Type `aw-test-one` as the name.
   *Expect:* the preview shows the full absolute path ending in `aw-test-one`, in your platform's
   separator style.
   *Failure looks like:* no preview, a mixed-separator path, or a path that does not match what you
   typed.

3. **The project is named after the folder.** Confirm.
   *Expect:* the project is created at the previewed path and appears named `aw-test-one`.
   *Failure looks like:* a project named after the parent folder, or an untitled project.

4. **A name is a name, not a path.** Start another create, browse to a parent, and type
   `nested/thing` as the name.
   *Expect:* refused, with a message saying why.
   *Failure looks like:* it silently creates `nested/thing`, or quietly renames it to `nested-thing`
   without telling you.

5. **Opening still works the old way.** Choose Open an existing project and browse to the
   `aw-test-one` folder you just made — it is already registered, so try any other existing folder.
   *Expect:* the directory field takes the browsed path directly, and the optional display name is
   still there if you want to override it.
   *Failure looks like:* open mode asking you for a name, or rejecting a folder that exists.
