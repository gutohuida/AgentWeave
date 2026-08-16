# Tasks — conversation formatting and quick navigation

Three independent pieces (`design.md`'s D1/D2/D3 do not depend on each other) — order below is
cheapest-and-most-evidenced first, matching `proposal.md`'s ranking, not a dependency chain.
No database migration, no backend route change.

## 1. Markdown rendering (D1) — agent-verifiable

- [ ] 1.1 `cd hub/ui && npm install react-markdown remark-gfm remark-breaks` (three packages, no
      transitive-dependency surprises expected from `react-markdown` v9's own peer set — confirm the
      installed version has no `rehype-raw`/`dangerouslySetInnerHTML` in its own default render path
      before relying on that as the security boundary D1 names).
- [ ] 1.2 New `hub/ui/src/components/agents/MarkdownMessage.tsx`: wraps `ReactMarkdown` with
      `remarkPlugins={[remarkGfm, remarkBreaks]}`, no `rehypePlugins`. Custom component overrides for
      `code`/`pre` (bounded block, `--font-mono`, `--surface`/`--border` — no per-token colour, per D1)
      and `a` (existing link styling, `target="_blank" rel="noreferrer"` since a link can originate
      from agent or peer content, not just the operator).
- [ ] 1.3 `AgentTimeline.tsx`'s `MessageEntry` renders `entry.content` through `MarkdownMessage`
      instead of the current `whitespace-pre-wrap` span, for `operator_input`, `agent_output` where
      `output_kind` is `'text'` or absent, `inbound_peer`, and `outbound_peer`. Leave `WorkRow`
      (tool_use/tool_result rendering, handled in section 2) and non-text `agent_output` kinds
      (`thinking`, `status`, `diagnostic`, `error`) untouched — D1 scopes this to message-level prose
      only.
- [ ] 1.4 Tests (`hub/ui/src/__tests__/` or co-located, matching this component's existing test
      location): a message containing `**bold**`, a fenced code block, and a bulleted list renders a
      real `<strong>`, a real `<code>`/`<pre>`, and a real `<ul>`/`<li>` — not the literal
      `**`/backtick/`-` characters. A message with two lines separated by a single `\n` (no blank line
      between them) renders both lines with a line break between them, not collapsed into one line —
      the `remark-breaks` regression this task exists to prevent. A message containing a literal
      `<script>` tag or an `<img onerror=...>` string renders it as inert visible text, never as a DOM
      element — the security property D1 is built around, asserted directly rather than trusted by
      inspection. Mutation-check the last one: temporarily add `rehypeRaw` to the plugin list, confirm
      the test fails, then remove it.

## 2. Tool-call icon and label (D2) — agent-verifiable

- [x] 2.1 `WorkRow` (`AgentTimeline.tsx`): add the `TOOL_ICON` lookup table from `design.md` D2,
      keyed on `entry.payload?.tool` (fall back to the existing generic label when `payload` is
      absent or `tool` is unmapped — do not assume every historical entry has a `payload.tool`, since
      this reads data recorded before this change too). Render the resolved `Icon` beside the
      existing label text, replacing the single shared fold icon that currently stands in for every
      tool type.
- [x] 2.2 Test: for each mapped tool name, `WorkRow` renders that tool's icon and label; for an
      unmapped name (e.g. a fixture tool `"SomeFutureTool"`), it renders the `Wrench`/"Tool call"
      fallback; for an entry with no `payload` at all, it renders the same fallback without throwing.
      Mutation-check: remove one table entry, confirm its test fails (falls back instead of matching),
      reapply.

## 3. Diff view for edit-shaped tool calls (D2) — agent-verifiable

- [ ] 3.1 `cd hub/ui && npm install diff` (jsdiff).
- [ ] 3.2 New `hub/ui/src/components/agents/ToolEditDiff.tsx`: given `payload.input` (a string),
      attempt `JSON.parse`; if it throws, or `payload.truncated === true`, or the parsed value lacks
      both `old_string` and `new_string` as string properties, return `null` (caller falls back to the
      existing raw-text rendering — see 3.3). Otherwise render `Diff.diffLines(old_string, new_string)`
      as a sequence of added/removed/unchanged lines, added lines on `--green`, removed on `--red`,
      unchanged neutral — no syntax highlighting (out of scope, per D1's deferral, which applies
      equally here).
- [ ] 3.3 `WorkRow`'s expanded state: when `entry.output_kind === 'tool_use'` and `ToolEditDiff`
      returns non-null content for `entry.payload`, render it instead of the current raw
      input/output text concatenation. Every other tool type, and every edit-shaped payload
      `ToolEditDiff` declines (malformed, truncated, non-edit-shaped), keeps today's raw-text
      rendering exactly as is.
- [ ] 3.4 Tests: a `payload.input` of `'{"old_string":"foo","new_string":"bar"}'` (well-formed JSON,
      the shape `tool_use_event` actually produces per D2) renders added/removed lines with the
      expected content and tone classes. A `payload.input` that is not valid JSON, one with
      `truncated: true`, one that parses but has only `old_string` and no `new_string` (a synthetic
      fixture for the "missing key" case, not any real tool's actual shape), and a real
      `MultiEdit`-shaped payload (`'{"file_path":"x","edits":[{"old_string":"foo","new_string":"bar"}]}'`
      — `old_string`/`new_string` nested inside `edits`, absent at the top level, per
      `hub/hub/runner_parsing.py:264-272` and design.md's documented limitation) all fall through to
      the unchanged raw-text rendering — four separate cases, not one collapsed test, since each is a
      distinct reason to decline. Mutation-check: comment out the `truncated` guard, confirm a
      truncated fixture wrongly attempts a diff on possibly-cut JSON (test fails), reinstate.

## 4. Command palette (D3) — agent-verifiable

- [ ] 4.1 `cd hub/ui && npm install cmdk`.
- [ ] 4.2 New `hub/ui/src/components/palette/CommandPalette.tsx` using `Command.Dialog`. Mounted once
      at the app-shell level (`App.tsx`), global `Cmd+K`/`Ctrl+K` listener guarded against firing
      while a text input, textarea, or the composer holds focus and the key event has no
      modifier-only intent (i.e. still respects the shortcut when a *non-text* element has focus, per
      D3).
- [ ] 4.3 Four action groups, each reading data the app already has loaded (no new fetch): open
      conversation (agent + conversation pairs from navigation's existing adapter), open agent (jumps
      to that agent's most recent conversation, matching the existing rail-name behaviour), open spec
      document (the project's already-loaded document list), open task (the project's already-loaded
      task list). Each selection calls the existing navigation function for that destination and
      closes the palette.
- [ ] 4.4 Tests: the palette opens on `Cmd+K`/`Ctrl+K` and closes on Escape; it does not open when a
      text input has focus and a literal "k" is typed without the modifier; each of the four action
      kinds is listed with fixture data and, on selection, calls the mocked navigation function with
      the expected destination (same testing pattern as `2026-08-16-spec-surface-legibility`'s F4
      chip-click tests — mock the resolver, assert the call).

## 5. Full-suite verification — agent-verifiable

- [ ] 5.1 `npx tsc --noEmit` clean.
- [ ] 5.2 `npm run lint` — no new warnings or errors beyond the 9 pre-existing `react-refresh/only-
      export-components` warnings already itemised in `STATE.json`'s `decisions_for_user` (unrelated
      files; do not fix them here, out of this change's scope).
- [ ] 5.3 `npm test -- --run` — full suite passes. If any file times out under full-suite resource
      contention (a documented, pre-existing flake in this repo's test environment — see `STATE.json`
      `dead_ends`), rerun that file alone before treating it as a regression.
- [ ] 5.4 `npm run build && python ../../scripts/refresh_ui_bundle.py` — bundle rebuilt and committed
      alongside the source, per CLAUDE.md's "commit `hub/ui/src` and `hub/hub/static/ui` together"
      rule.
- [ ] 5.5 No backend file changes in this change (D1–D3 are `hub/ui`-only); confirm with `git status`
      before committing that nothing under `hub/hub/` or `src/agentweave/` was touched.

## 6. Human-only verification

- [ ] 6.1 **D1 — does rendered Markdown actually read better, or does it introduce visual noise?**
      Taste. Open a conversation with an agent turn containing a fenced code block, a list, and at
      least one link; read it in both light and dark mode.
- [ ] 6.2 **D2 — do the per-tool icons actually help scan a long tool-call sequence?** Taste, per the
      operator's own T3 comparison. Drive a real agent turn that reads several files, runs a bash
      command, and edits one file; look at the resulting work block.
- [ ] 6.3 **D2 — does the edit diff read cleanly against a real file edit**, not just the synthetic
      fixture 3.4 exercises? Have an agent edit a real file with a non-trivial change (more than a
      one-line swap) and expand that tool call.
- [ ] 6.4 **D3 — does the palette feel fast and find the right things**, per the survey's comparison
      to Cursor/Claude Code/Linear's own palettes? Open it, search for a conversation by agent name, a
      task by partial title, and a spec document; confirm each is found without exact-match typing.
- [ ] 6.5 **Regression check — nothing that used to read fine now reads worse.** Open a few older
      conversations that predate this change (recorded before `payload.tool`/`payload.input` had any
      reason to be read this way) and confirm they still render sensibly under the new code paths,
      not just newly recorded ones.

## 7. User test guide

**Setup.** Any project with at least one agent conversation containing a tool call that reads a
file, one that edits a file, and one agent message that used Markdown formatting (a code block or a
list) at some point — `aw-loop10`'s existing history likely has all three; a fresh short exchange
with any agent will also produce them.

1. **Open a conversation with agent output that used formatting** (a code block, a list, bold
   text). — *Expect:* it renders as formatted text — a real code block, a real list — not the raw
   `**`/backtick/`-` characters.
2. **Find a tool-call work block and expand it.** — *Expect:* each tool call shows an icon and a
   short label specific to what it did (e.g. a pencil for an edit, a terminal for a bash command),
   not one generic icon repeated for everything.
3. **Find a file-edit tool call specifically, and expand it.** — *Expect:* the change is shown as a
   diff — additions and removals in distinct colours — not two blocks of raw text you have to
   compare by eye.
4. **Press Cmd+K (or Ctrl+K on Windows/Linux).** — *Expect:* a search overlay opens. Type part of a
   conversation's, task's, or spec document's name. — *Expect:* it appears in the results; selecting
   it navigates there and the overlay closes.
5. **Press Escape while the palette is open, or click outside it.** — *Expect:* it closes without
   navigating anywhere.

**Where it would go wrong:** if step 1 still shows raw Markdown syntax, or step 3's diff looks wrong
for a specific kind of edit (e.g. a multi-file edit, or one where old/new content is very large and
was truncated), say so with the tool call's shape (what kind of edit, how large) — that is exactly
the boundary `design.md` D2's truncation/parse-failure fallback is meant to catch, and if it did not
catch it that is a real bug, not a taste call.
