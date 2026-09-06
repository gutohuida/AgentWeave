## Why

The Instructions editor cannot tell the operator apart from itself. When the GET that loads a
project's instructions fails, the page renders the same thing it renders for a project that has
never had any: an empty textarea with an enabled Save button. One click on that page — with nothing
typed — replaces the project's instructions with the empty string, and nothing on screen says a load
failed before, during or after.

Driven live on 2026-09-02 against the served bundle (`F271`, severity A,
`scripts/drive/FINDINGS.md:18503`; harness `scripts/drive/t_d4_instructions_failed_load.py`, 19
assertions). Measured end to end, Hub reachable again, nothing typed:

```
stored before Save: 'ALPHA PROJECT RULES\n\n- Never force-push.\n- Every PR needs a test.\n'
stored after  Save: ''
```

| | load succeeds | GET aborted | GET answers 500 |
|---|---|---|---|
| skeleton | absent | absent | absent |
| textarea | present, holds the stored text | present, **empty** | present, **empty** |
| Save | enabled | **enabled** | **enabled** |
| `role="alert"` | none | **none** | **none** |

The page contains no occurrence of *error*, *failed*, *could not*, *unable* or *retry* in any of the
three columns.

## The mechanism, read out of the code

Three lines, none of which is wrong on its own:

1. `useInstructions()` is destructured as `{ data, isLoading }`
   (`hub/ui/src/components/instructions/InstructionsPage.tsx:9`). The query's error state is never
   read by anything.
2. The editor is seeded by `useEffect(() => { if (data) setContent(data.content) }, [data])`
   (`:14-18`). A failed load leaves `data` undefined, so `content` stays at its `useState('')`
   initial value — the same value a genuinely empty project produces.
3. The only branch that hides the editor is `isLoading` (`:45`), and
   `isLoading = isPending && isFetching` (`@tanstack/react-query` 5.62,
   `query-core/.../queryObserver.js:310`). After `retry: 1` (`hub/ui/src/main.tsx:12`) exhausts,
   the query is `error`/idle: `isLoading` is **false**. The skeleton branch is not taken and the
   textarea renders.

Save's `disabled` is `saveMutation.isPending` alone (`:39`). The PUT then sends `{"content": ""}`,
which `hub/hub/api/v1/instructions.py` accepts **deliberately** — its `InstructionsUpdate` docstring
records that the field was named precisely so that no mis-shaped body could blank the row by
accident. That server-side guard is intact and is not what failed here: the client walks past it
with a perfectly well-formed body carrying a legitimate value. `put_instructions` overwrites
`row.content` in place; there is no history, no undo and no confirmation.

## Why this is severity A

Project instructions are prepended to every agent's canonical turn context and to every charter the
Hub serves. Both consumers gate on the content being **non-empty**, so blanking the row does not
degrade the context — it removes the section entirely:

- the canonical context reads the row at `hub/hub/api/v1/agents.py:1127-1130` and emits
  `## Project Instructions` only `if project_instructions:` (`:1529-1533`);
- `get_charter_context` (`:2108`) prepends only `if instructions_row and instructions_row.content`
  (`:2119-2121`), so every charter silently reverts to its unprepended text.

Blanking therefore removes the operator's project-wide rules from every subsequent turn, with no
error at the moment of loss and no signal afterwards. The operator can still see the rules they
wrote — in their own memory, not in the product — while the agents quietly stop following them.

**Two of `F271`'s three references had drifted and are corrected here.** The finding cites
`agents.py:1486-1490` and `:2072-2078`, and names the second consumer `get_charter_content`; on
today's code the sites are `:1529-1533` and `:2119-2121`, and the function is `get_charter_context`.
The claim the finding drew from them survives the correction intact — this round re-derived it from
the current file rather than carrying the citation forward.

The empty editor alone would be a B: a misleading surface. What makes it an A is that the operator
*acts* on it, the act takes one click, and it is irreversible.

## What changes

The editor is rendered only when this project's stored instructions have actually been read. Not
"when the query has not errored" — **when `data` is present for the current query key**, which is
one condition instead of three and is the only condition that is true exactly when the textarea has
something truthful to show.

That single condition also closes two states the current code cannot distinguish from "the project
has no instructions":

- **the failed load** — the driven case;
- **the not-yet-enabled query** — `useInstructions` is `enabled: isConfigured && !!projectId`
  (`hub/ui/src/api/instructions.ts:14`), and a disabled query is `isPending && !isFetching`, so
  `isLoading` is false there too. Derived from the code; **its reachability in the running app is
  not driven** (see `design.md`), and no scenario below depends on it being reachable.

It closes the cross-project variant `F271` recorded as unfalsified in either direction — component
stays mounted, selected project changes, the new project's load fails, and `content` still holds the
previous project's text — because on the new project's failure there is no editor and no Save. A
scenario asserts that, so the fix cannot regress into it.

Three requirement changes, all in `project-instructions`:

- **MODIFIED** *Hub UI provides instructions editor* — its "pre-filled with the current saved
  content" scenario is unconditional today, which is precisely the promise the failed load breaks.
  Restated as conditional on the load having succeeded, with the success path otherwise unchanged.
- **ADDED** *A failed instructions load is stated, not rendered as an empty editor* — the failure is
  named in the section, in a live region, and the operator can retry in place.
- **ADDED** *Save is unavailable until the project's stored instructions have been read* — the gate,
  stated as an outcome (no PUT can be issued) rather than as a `disabled` attribute.

## What this deliberately does not change

**Whether a PUT should refuse to replace non-empty stored content with `""` without a confirmation
is an operator decision, not a bug fix.** The empty string is a value the route accepts on purpose,
and "clear my instructions" is a thing an operator is entitled to do. `F271` says so, and this
change keeps to that: it repairs the client that lied about what it was holding, and leaves the
product question open. It is carried on this cycle's review page as a question, not decided here.

**The capability-wide version of this requirement is rejected for now** — see `design.md`. Writing
"a configuration section that failed to load says so" into `project-environment-settings` would
oblige seven other pages that have never been measured for it.
