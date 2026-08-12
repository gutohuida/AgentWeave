# Creating a project takes a parent and a name

## Why

**In create mode, the Browse button cannot produce a valid answer.** Not "usually does not" —
cannot, structurally:

- `ProjectLifecycleService.create_new` refuses a target that exists
  (`hub/hub/project_lifecycle.py:99-100`) and then creates it (`:108`). Creating requires a path to a
  directory that is **not there**.
- Both browse affordances return a directory that **is** there. The host folder dialog can only
  select an existing folder, and the in-Hub `DirectoryPicker` browses the filesystem.

So the operator clicks Browse, picks a folder, and gets a path that create will reject. The only way
through is to browse to the *parent* and then hand-type `/my-project` onto the end of the path in the
text field. The operator hit exactly this and reported it as *"you have to chose a folder then write
after /folder_name — this is bad practice"*.

The form makes it worse by presenting the two things that matter as unrelated fields:

- **Directory path** — a full absolute path, whose last segment is the folder that will be created.
- **Display name (optional)** — an empty box with no indication of what happens if it is left empty.

What actually happens is that the backend already falls back to the folder's own name
(`project_lifecycle.py:85`, `name or canonical.path.name`). So the correct behaviour the operator
asked for is *already implemented* and completely invisible: the form never says that leaving the
name blank names the project after the folder, so there is no reason to believe it.

The two fields are not independent. The last segment of the path and the project's name are the same
decision, and the form asks for it twice — once as path surgery and once as an optional box.

## What Changes

- **Create mode asks for a parent directory and a project name.** The parent is what Browse returns,
  which makes Browse useful in create mode for the first time. The name is a single word, not a path
  segment the operator has to splice.
- **The project is created at `<parent>/<name>` and is named `<name>`.** One decision, entered once.
  This makes the existing backend fallback visible rather than changing it.
- **The resulting absolute path is previewed** before the operator confirms, so "where did it go?" is
  answered on the form rather than after the fact.
- **The project name is validated as a directory name** — non-empty, a single path segment, no
  separators or traversal, and nothing the host filesystem will reject. Today the operator can type a
  path with separators into a field labelled as a path and get a surprising nesting; a field labelled
  as a name must refuse one.
- **Open mode is unchanged in shape.** It genuinely takes an existing directory, which is what Browse
  returns, so it keeps its directory field and its optional display-name override.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `local-project-workspace`: "Project creation and opening are explicit and bounded" gains the
  requirement that creation is expressed as an existing parent plus a new name, that the created
  directory is named by that name, and that the project takes the same name. "The operator can browse
  for a project directory" gains the requirement that what browsing returns is directly usable in the
  mode it was invoked from — which is the defect, stated as a rule.

## Impact

**UI** — `hub/ui/src/components/projects/ProjectManagerModal.tsx`: create mode gains a name field and
a computed target preview; its Browse affordances now fill the parent rather than the whole path. The
`DirectoryPicker` component itself is unchanged.

**Backend** — expected to be **no change**. `create_new` already takes the full target path and
already falls back to the folder name, so the UI composes `<parent>/<name>` and sends what it sends
today. Task 1.1 verifies that before anything is built on it, because "no backend change" is an
assumption and this change's whole premise is that an unverified assumption about this flow is what
produced the defect.

**Tests** — `hub/ui/src/__tests__/projectManagerDirectoryPicker.test.tsx` covers browse-into-the-form
behaviour and will need updating for create mode. `directoryPicker.test.tsx` should be unaffected.

## Non-Goals

- **Not changing open mode's shape**, which is already correct for what it does.
- **Not allowing creation inside a directory that does not exist** — the parent must exist. Creating
  a chain of directories is a different and more dangerous operation.
- **Not adding a rename-project affordance.** Whether a project's display name can later diverge from
  its folder is a separate question this change deliberately does not answer.
- **Not changing what registration does** — no git init, no agent start, per the existing
  requirement.
- **Not touching Docker workspace-root confinement**, which applies to the composed target exactly as
  it applies to a typed one.
