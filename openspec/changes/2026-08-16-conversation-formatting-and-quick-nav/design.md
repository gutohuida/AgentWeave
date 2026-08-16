# Design — conversation formatting and quick navigation

## D1. Markdown rendering — library choice, newline handling, and what is deliberately deferred

**Library: `react-markdown` + `remark-gfm` + `remark-breaks`.** No `rehype-raw`, no
`dangerouslySetInnerHTML` anywhere in this change. `react-markdown`'s default behaviour renders
Markdown syntax to React elements without ever parsing embedded raw HTML — that default is load-
bearing here, not incidental: conversation content includes agent output and peer-agent traffic,
neither of which is content the operator authored, so treating it as trusted enough to inject as
HTML would be a stored-XSS path from any agent (or, transitively, anything a tool call pulled from
the web) straight into the operator's browser. `remark-gfm` adds tables, strikethrough, and task
lists — all things a coding agent's output plausibly contains. `remark-breaks` treats a single
newline as a line break rather than requiring a blank line for a paragraph break, which is
Markdown's default and would otherwise be a visible regression from today's `whitespace-pre-wrap`,
where every newline a model actually sent is already preserved.

**Scope: message-level entries only, not tool-call rows.** `MessageEntry` (operator input, agent
text output, peer traffic) renders through the new renderer. `WorkRow`'s tool-call summary and
expanded input/output (D2) stay on literal text — tool payloads are data (a shell command, a file
path, a JSON blob), not prose, and Markdown-parsing them would be as wrong as it would be for a log
line.

**Deliberately deferred: syntax-highlighted code blocks.** The survey's cost estimate named a
highlighter (`rehype-highlight` or `shiki`) as part of "medium-low cost." Scoped out of this change:
a highlighter adds its own token-colour palette, which has to be built from the Hub's existing CSS
custom properties to satisfy the same "no colour scheme of its own" constraint
`2026-08-16-spec-surface-legibility` already established for the rendered spec document — that is
real design work, not a dependency add. V1 renders fenced code blocks as a bounded, monospace
(`--font-mono`, already loaded via `@fontsource/jetbrains-mono`) block using the existing
`--surface`/`--border` tokens, with no per-token colour — a strict improvement over today's
un-delimited raw-text rendering, and a smaller, lower-risk unit to review. Language-aware
highlighting is left as a follow-up, named so it is not silently forgotten.

**Fallback:** unrecognized or malformed input renders exactly as `react-markdown` renders any plain
text with no Markdown syntax in it — visually equivalent to today's `whitespace-pre-wrap` for
content that was never using Markdown syntax to begin with, so there is no regression case to
guard.

## D2. Tool-call formatting — icon lookup and the edit-tool diff view

**Icon lookup is a fixed table, not inferred.** Read `stream_events.py` (`tool_use_event`,
`src/agentweave/stream_events.py:475-503`) directly rather than guessing the payload shape:
`payload.tool` is the literal tool name string (`"Edit"`, `"Read"`, `"Write"`, `"Bash"`, `"Grep"`,
`"Glob"`, `"WebFetch"`, `"WebSearch"`, `"Task"`, `"TodoWrite"`, `"NotebookEdit"`, …) and
`payload.input` is `json.dumps(input_data, sort_keys=True)` — a JSON string of whatever the runner
passed as the tool's arguments, unless `payload.truncated` is `true`, in which case the string may
have been cut mid-value by `_enforce_payload_bound`. A small `TOOL_ICON: Record<string, {icon:
LucideIconName; label: string}>` map in `WorkRow`'s module, keyed on `payload.tool`, with a single
generic fallback (`Wrench`, "Tool call") for any name not in the table — new tool names introduced
by a future runner degrade to the fallback rather than throwing or rendering nothing.

| `payload.tool` | icon | label |
|---|---|---|
| `Read` | `FileText` | Read |
| `Write` | `FilePlus2` | Write |
| `Edit` / `MultiEdit` | `Pencil` | Edit |
| `Bash` | `Terminal` | Bash |
| `Grep` | `Search` | Search |
| `Glob` | `FolderSearch` | Find files |
| `WebFetch` | `Globe` | Fetch |
| `WebSearch` | `Search` | Web search |
| `Task` / `Agent` | `Users` | Subagent |
| `TodoWrite` | `ListChecks` | Plan |
| `NotebookEdit` | `NotebookPen` | Notebook |
| *(unmapped)* | `Wrench` | Tool call |

All from `lucide-react` — the existing `Icon` component's only backing set, per CLAUDE.md. No new
icon dependency.

**Diff view: only for tools whose `payload.input` parses to an object carrying both `old_string`
and `new_string`** (`Edit`, `MultiEdit`'s per-edit entries) — this is a structural check on the
parsed JSON, not a tool-name allow-list, so it degrades correctly if a future tool reuses the same
shape or an existing one changes its schema. Parse `payload.input` with `JSON.parse` inside a
`try`/`catch`; on parse failure, on `payload.truncated === true` (a cut string is not valid JSON and
must not be diffed against a lie), or when the parsed object lacks both keys, render the existing
raw-text fallback unchanged — the diff view is additive, never a required path.

**Diff library: `diff` (jsdiff).** Chosen over hand-rolling a line/word diff because line-diff
correctness (matching common prefixes/suffixes, not just a naive split) is exactly the kind of
"well-known, small, easy to get subtly wrong" utility a dependency exists for, and `diff` has no
transitive dependencies of its own. `Diff.diffLines(old_string, new_string)` renders additions and
removals with the existing `--green`/`--red` status-hue tokens already used for task status
(`hub-workspace-shell`'s "hue is reserved for meaning" requirement — a diff is a canonical case of
meaningful hue, not decoration).

**Not built:** a full editor-style side-by-side diff, or a diff for tools other than the edit
family (e.g. structured `Bash` stdout/stderr formatting). Both are real but separate scope; only the
one gap the survey evidenced (no diff view for a file edit, T3/Cline's named comparison) is built.

## D3. Command palette — scope and library

**Library: `cmdk`.** The de facto standard for exactly this interaction (used by Linear, Vercel's
own dashboard, and named directly in the survey's Cursor/Claude Code comparisons) — unstyled,
composes with the Hub's own Tailwind classes and CSS variables rather than shipping a competing
visual language, and small (no runtime dependency beyond React).

**Scope: current project only, four action kinds.** Switch to an existing conversation (agent +
conversation pairs already loaded by navigation — no new fetch), open an agent's most recent
conversation, open a spec document (from the project's already-loaded document list), open a task
(from the already-loaded task board). Explicitly not in scope: cross-project search/switch (project
identity is a bigger structural question than this change should carry) and full-text search inside
conversation content (a different, much larger feature — indexing, not navigation).

**Keyboard and focus:** a single global `keydown` listener (mounted once, at the app shell level,
matching where `useDialogFocus.ts`'s pattern already lives) for `Cmd+K` / `Ctrl+K`, guarded so it
does not fire while a text input or the composer has focus and the user is plausibly typing a
literal "k" — `cmdk`'s own `Command.Dialog` wraps a Radix `Dialog` under the hood, so opening it
reuses the same focus-trap and Escape-to-close behaviour every other dialog in this codebase already
has, rather than introducing a second one.

## D4. Testing approach

Every new render path gets a component test asserting the specific claim: a message containing
Markdown syntax renders the expected DOM (a real `<strong>`, a real `<code>`, a real list), not the
literal characters; a `WorkRow` for each mapped tool name renders that tool's icon and label,
and an unmapped name renders the fallback; a `payload.input` shaped like an edit renders addition/
removal-styled lines, and one that fails to parse or carries `truncated: true` renders the existing
raw-text path unchanged; the command palette opens on the shortcut, lists the four action kinds,
and each selection navigates as expected (mocking the navigation function, matching this codebase's
existing pattern of testing navigation intent rather than the full route change, per
`2026-08-16-spec-surface-legibility`'s F4 tests). Every new assertion mutation-checked, per this
run's standing practice.

Visual and taste judgements (does the code block actually look right against both themes, does the
diff read cleanly, does the palette feel fast) are human-only — named explicitly in `tasks.md`
section 6, consistent with the standing limit on this driver assessing visual/taste work.
