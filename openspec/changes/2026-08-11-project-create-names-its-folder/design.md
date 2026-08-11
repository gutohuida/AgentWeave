# Design — Creating a project takes a parent and a name

## Context

Two facts decide this change, and both are already in the tree:

1. `create_new` requires a **nonexistent** target and creates it
   (`hub/hub/project_lifecycle.py:99-108`).
2. Every browse affordance returns an **existing** directory.

A form that asks for "the directory path" cannot serve both. It is asking for a path that must not
exist, using a control that can only produce paths that do. The operator is left to bridge the gap by
editing a string, and the string they must edit is a filesystem path — the one kind of input where a
typo is least visible and most consequential.

The second fact is that the fallback the operator asked for already exists: `name or
canonical.path.name`. This change is mostly about making a correct behaviour visible, not about
adding one.

## Goals / Non-Goals

**Goals:**

- Browse produces a directly usable answer in the mode it was invoked from.
- The folder name and the project name are entered once, because they are one decision.
- The operator sees the absolute path that will be created before confirming.

**Non-Goals:**

- Changing open mode, creating parent chains, adding project rename, or altering registration.

## Decisions

### D1 — Create takes a parent plus a name; open keeps taking a directory

The two modes are asymmetric because the underlying operations are asymmetric. Open consumes a
directory that exists — exactly what a picker yields. Create produces one — so what it needs from the
operator is *where* (an existing parent, which a picker yields) and *what to call it* (a name, which
a picker cannot yield and a text field can).

Making both modes look identical is what created the defect: one shared "Directory path" field that
means "the thing you are opening" in one mode and "the thing that must not exist yet" in the other.

*Rejected: keeping one path field and making Browse fill the parent in create mode.* It removes the
typing but leaves a field whose meaning silently changes with the mode, and leaves the name still
being expressed as a path segment.

*Rejected: letting create accept an existing empty directory.* It would make Browse work by widening
what create accepts, and the current requirement — "MUST refuse an existing non-empty target",
"Creating MUST create exactly the requested new directory" — is a deliberate safety boundary. Widening
it to fix a form is the wrong trade, and it would not remove the second problem (the name is still
entered twice).

### D2 — The name field is the project name and the folder name, and there is no separate override in create mode

The operator's words were "make the project name be the folder name". A separate optional display
name in create mode would preserve the exact confusion being removed: two boxes, one decision, and no
statement of how they relate.

Open mode keeps its optional display-name override, because there the folder already exists and was
named by something other than this act — adopting a directory called `src-v2-final` and calling the
project something legible is a real need.

Allowing the two to diverge *later* is a rename feature, and a non-goal. Stated because "creation
sets them equal" and "they can never differ" are different claims and only the first is being made.

### D3 — The name is validated as a single path segment, and refused rather than sanitised

The field is labelled as a name, so it must behave like one. It is rejected when it is empty or
whitespace, contains `/` or `\`, is `.` or `..`, or is a name the host filesystem will not accept.

**Refused, not silently rewritten.** Rewriting `my/project` into `my-project` would create a
directory the operator did not ask for at a path they did not see, which is precisely the class of
surprise this change exists to remove. An error naming the problem is better than a correction that
looks like success.

The reserved-name and illegal-character set is genuinely platform-specific (Windows rejects `CON`,
`PRN`, trailing dots and spaces, and `<>:"|?*`; POSIX does not). The Hub already owns this knowledge
server-side, and `create_new` already surfaces a `project_create_failed` error from the `OSError`. So
the client validates the unambiguous, portable cases and **the server stays the authority** — the
client check exists to give a fast, clear message, not to be the gate. A client-side allowlist
pretending to be complete would be a fourth place for platform rules to drift.

### D4 — The composed target is previewed, and the preview is the truth

The form already has a preview element (`data-testid="project-path-preview"`). In create mode it
shows the composed `<parent>/<name>` as an absolute path.

It is derived from the same values that are submitted, not re-typed alongside them, so it cannot
disagree with what is sent. A preview that is assembled separately from the payload is worse than no
preview, because it is trusted.

Path joining uses the separator style of the parent the operator supplied, so a Windows operator who
browsed to `C:\Users\me\projects` sees `C:\Users\me\projects\my-app` and not a mixed-separator hybrid.
The backend normalises either way; this is about the operator recognising their own filesystem.

### D5 — The backend is expected to need no change, and that is verified first

`create_new(body.path, name=body.name)` already accepts the full target and already defaults the name
from the folder. The UI can therefore compose the path and send exactly the payload it sends today.

Task 1.1 confirms this against the running code before anything is built on it. This change exists
because an unverified assumption about this flow shipped a control that could not work; repeating the
pattern while fixing it would be its own punchline.

## Risks / Trade-offs

- **An operator who wants a project name different from its folder loses that at creation** → they
  keep it in open mode, and D2 records that a later rename is a separate feature rather than a denial.
- **Client-side name validation and the host filesystem can disagree** → D3 makes the server the
  authority and the client a fast message, so a disagreement is a slightly slower error, not a wrong
  outcome.
- **Two modes now look different** → deliberate (D1). They are different operations, and the previous
  visual symmetry is what made the create field unusable.
- **Docker deployments confine paths beneath the mounted workspace root** → the composed target is a
  path like any other and is checked by the same `canonicalize_project_directory` call; the parent is
  what must lie beneath the root, and the existing error surfaces if it does not.
