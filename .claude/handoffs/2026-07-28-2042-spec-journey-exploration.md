# Handoff: Spec-journey exploration — 7 changes scoped, context-tracking measured across 5 runners

**Date:** 2026-07-28T20:42+0100 · **Branch:** `master` · **HEAD:** `968b8db`
**Agent:** Claude Code (Opus 5, `claude-opus-5`)
**Previous handoff:** `.claude/handoffs/2026-07-27-2238-repo-cleanup-sweep.md`
**Status:** chunk complete — exploration finished and recorded; next session starts proposing

> **This is a different work thread from the previous handoff.** The repo-cleanup sweep, the
> spec-root-rename thread, and the AgentWeave-1.0 consistency pass are all still live and
> untouched by this session. Their ~104 uncommitted files are still in the working tree — see
> "Files I did NOT touch". Do not attribute them to me.

> ⚠️ **`openspec/*` IS GITIGNORED** (`.gitignore:145`, only `openspec/config.yaml` is tracked).
> Almost everything this session produced lives under `openspec/` and is therefore **untracked
> and unbacked by git**. `git status` will never show it. A `git clean -fdx` would destroy all
> of it, including the exploration record that is this session's main deliverable.

## Goal

The user wants to improve the "spec journey" — how users author, navigate, and discuss project
specs in the AgentWeave Hub. Five threads were raised: (1) improved spec skills now generate a
file nesting the sync layer rejects, (2) navigation is a flat dropdown, (3) the agent chat pane
crushes the spec on small screens, (4) the chat is verbose and the agent inconsistently uses
responses vs AgentWeave messages, (5) no thinking/progress UI.

The *why*: the user is actively using the Spec tab to author specs with a spec agent, and each
of these frictions compounds. The session ran as exploration — deliberately **no implementation**
— to scope the work before proposing it.

## Current state

**Exploration complete. One change proposed. Nothing implemented. No application code changed.**

Done this session:

1. **Archived all 9 active OpenSpec changes.** Four completed ones (`add-trace-timeline`,
   `agent-context-onboarding`, `improve-runtime-diagnostics`, `project-wide-instructions`) were
   synced to main specs first — `openspec/specs/` now holds 7 capabilities. Five abandoned ones
   (`investigate-blockers`, `add-auto-reset-mode`, `add-durable-trigger-retry`,
   `fix-context-tracking`, `autonomous-dev-loop`) were archived **without** sync, because their
   delta specs describe behaviour that was never built.
2. **Documented the shelved autonomous-dev-loop idea** at
   `docs/archive/autonomous-dev-loop/index.md`, added to `mkdocs.yml` nav.
3. **Proposed `fix-spec-chat-session-resume`** — validates `--strict`, 4/4 artifacts. The only
   active change on the board (0/16 tasks).
4. **Wrote the exploration record** at `openspec/explorations/2026-07-28-spec-journey.md`
   (556 lines) — the session's main deliverable. Holds all decisions, measured evidence, open
   questions, execution order, and 7 change sketches.
5. **Empirically measured context-tracking across 5 runners** by actually running the CLIs.
   Found 5 confirmed bugs. This is the expensive part — re-deriving it costs real tokens.

## Files touched

**Untracked (gitignored under `openspec/*`) — created by me:**

- `openspec/explorations/2026-07-28-spec-journey.md` — NEW, 556 lines. **The main deliverable.**
  New directory; there was no prior `explorations/` convention. Complete.
- `openspec/changes/fix-spec-chat-session-resume/.openspec.yaml` — NEW. `schema: spec-driven`.
- `openspec/changes/fix-spec-chat-session-resume/proposal.md` — NEW. Complete.
- `openspec/changes/fix-spec-chat-session-resume/design.md` — NEW. Complete.
- `openspec/changes/fix-spec-chat-session-resume/specs/spec-chat-session/spec.md` — NEW. Complete.
- `openspec/changes/fix-spec-chat-session-resume/tasks.md` — NEW. 16 tasks, all unchecked.
- `openspec/specs/trace-timeline/spec.md` — NEW (synced from archived change).
- `openspec/specs/agent-context-onboarding/spec.md` — NEW (synced).
- `openspec/specs/runtime-diagnostics/spec.md` — NEW (synced).
- `openspec/specs/project-instructions/spec.md` — NEW (synced).
- `openspec/changes/archive/2026-07-28-*` — 9 directories moved here from `openspec/changes/`.

**Tracked — changed by me:**

- `mkdocs.yml` — added 2 nav lines under `Archive:` for the autonomous-dev-loop page. Complete.
- `docs/archive/autonomous-dev-loop/index.md` — NEW, untracked (`??`). Complete.

**Files I did NOT touch** — the ~104 other entries in `git status --short` are from three prior
sessions (repo cleanup, spec-root rename, AgentWeave-1.0 consistency pass). I changed no file
under `src/`, `hub/hub/`, `hub/ui/`, `tests/`, or `.claude/skills/`. Everything I learned about
those files was read-only.

## Key decisions

**Thread 1 — spec path contract → manifest.** User chose a manifest (`spec/index.json`),
agent-generated and agent-maintained. *Rejected:* a shared constant (skills are markdown and
cannot import it) and loosening the Hub regex to a safety check (would mean the Hub can no longer
assume `spec/spec.html` is "the" spec). **Critical amendment I proposed and user accepted:** do
*not* rely on the manifest alone — the watchdog globs `spec/**/*.html` and anything on disk but
absent from the manifest is still synced, shown as "unfiled". Rationale: an LLM-maintained
manifest *will* drift, and a forgotten entry must degrade to bad navigation, never to an
invisible file.

**Thread 1b — drift repair is one-click.** User: "Let's go with 1 click solution." The Hub
computes the drift set and hands the user a prefilled "fix the manifest" message to the spec
agent. *Rejected:* a passive warning badge the user has to act on manually.

**Thread 2 — both navigations.** Shell tree *and* rich in-document links. *Rejected:* map-only
navigation, because the user correctly noted it traps you when you know the path but there is no
link. Added ⌘K path search for that case.

**Thread 2b — lean the spec role.** `hub/hub/data/roles/spec.md` line 31 points at
`html-spec-conventions.md`, then lines 34–44 restate those conventions inline. Two copies, will
drift. Split principle agreed: role = routing (always in context, decides *which skill*), skill =
procedure (loaded on demand). Expect ~91 lines → ~35.

**Thread 3 — hoist the document TOC into the Hub shell.** Both sidebars are 220px; at 1280px
chrome eats 820px leaving 460px of content. *Rejected:* removing the chat (wrong pattern for
co-authoring), popup/modal (user's own instinct, confirmed by research as an anti-pattern),
floating bubble (explicit anti-pattern), and "just make both collapsible" (makes the user fix the
layout on every visit). The hoist is legal because the conventions' "TOC is load-bearing / renders
offline" requirement applies to *the file*, not to the Hub's rendering of it — the Hub injects CSS
hiding `nav.toc`, and **zero spec documents need to change.** User was enthusiastic: "Oh great on
the option c... I was going to propose this but I thought would complicate the managing of the nav
that is generated by the contract json."

**Thread 4 — structured `tool_use` payload.** User chose "The better UI ceiling" over a
pre-rendered string. Costs a JSON column; buys expandable diffs, file links, grouped calls.

**Thread 4b — reply channel is a framework invariant.** User: "Rule te framework guarantees...
this is not something that the user should be interested in configuring anyway." Route by trigger
origin (chat → stream, task/schedule/agent → `send_message`), with a carve-out that durable or
cross-agent facts always get a Message. *Rejected:* a project-level config knob (invites drift).

**Thread 4c — merge Questions into Messages, add threading.** User's idea, and the data model
already supports it: `Question` is a `Message` plus a `blocking` flag and an inline answer.
Decided it is **its own change**, not part of the spec work — it touches every surface.

**Change 0 — resume most recent session.** User: "It can be the resume the most recent sessions
and new if no session exists. This is good because I can get a agent that was working on something
recently into the spec page." So cross-context resume is a *feature*. *Rejected:* spec-scoped
sessions and a session picker in the Spec tab.

**Proposal cadence — just-in-time, not all at once.** User asked "should we create now all the
proposals?" I recommended against it: five of the nine changes archived today were proposals
written far ahead of the work, and several remaining changes have open questions that can only be
answered honestly at proposal time. User accepted by asking for the order to be recorded instead.

**Capture format — one exploration record, not six proposal stubs.** User picked this from three
options specifically to avoid putting six untouched changes back on a board they had just cleared.

## Constraints and user directives (verbatim)

- "I want to archive all of those" — on the four complete changes.
- "Oh okay. Archive all and add this to the documentation." — on the five abandoned changes;
  the idea was to be preserved in docs rather than as a stale change folder.
- "You can leave it there the investigation for now. I have no plans in the moment to comeback to
  that but it is a good reminder of a ideia that I had." — later superseded by "Archive all".
- "The agent should generate and maintain the manifest. We can create a simple skill that just
  tell which ever agent I'm on to fix the manifest if I feel somethings is wrong. But yeah we
  should not stick hard to the manifest and have a way to detect that something is wrong so I can
  tell the agents."
- "Let's go with 1 click solution."
- "Thread 2: Perfect." — on both-navigations plus the lean role.
- "Can you do a research on UI/UX to see how this is normaly solved? I'm open to even more drastic
  measures like removing the chat from there or just being a bubble or a pop up (pop up seems bad
  actually)."
- "Thread 4: The better UI ceiling."
- "Rule te framework guarantees. If it could be invisible to the users and avoid more configs it
  would be nice, because this is not something that the user should be interested in configuring
  anyway."
- "On the watchdog." — normalization lives in the watchdog, not the Hub.
- "Don't bother with version 1.x" — regarding Kimi.
- "I don't think the codex one means what you believe it means. Because it always shows 100% when
  I'm using codex." — user was right; see Dead ends.
- "no assistant.usage and it seems not context filling just the outputTokens" — user ran Copilot
  CLI at work and reported this.
- "Number 5 would be nice some reading of the documentation and testing to be 100% sure that
  you're not halucinating."
- "I want to make sure we do not forget everything that we discussed so far."

**Standing project rules that applied** (from `CLAUDE.md`): never commit `.agentweave/tasks/`,
`messages/`, `agents/`, `session.json`, `transport.json`; templates via `get_template()`, never
hardcoded in `cli.py`.

## Dead ends

- **I claimed Codex context tracking "works". It does not.** The user pushed back, and testing
  proved them right: `turn.completed.usage.input_tokens` is **cumulative across the thread**.
  Measured over three resumed turns: 18,860 → 37,736 → 56,628, while real context stayed ~18.9k.
  Pins at 100% within ~7 turns. Do not trust the code comment claiming it is correct.
- **I claimed Kimi "works via a context_usage ratio".** That path is v1.x wire mode only. The
  installed kimi (v0.29.1) emits **no usage on stdout at all** — verified by running it.
- **I first concluded Copilot context tracking was impossible.** Wrong — the data exists, just on
  an OTEL file channel that is off by default, not in the JSON stream.
- **`git mv` of `investigate-blockers` failed** with "Device or resource busy" because the Bash
  tool's working directory was still `cd`'d inside that folder from an earlier command. Moving
  from a different cwd worked. The Bash tool's cwd persists between calls — `cd` out before
  moving a directory you have entered.
- **`/tmp` paths fail** in this environment (Git Bash on Windows); Python cannot read them. Use
  the session scratchpad with a `C:/...` style path instead.

## Verification

**Ran and passed:**

- `openspec validate --specs` → 7 passed, 0 failed (after syncing 4 capabilities).
- `openspec validate fix-spec-chat-session-resume --strict` → valid.
- `openspec status --change fix-spec-chat-session-resume --json` → 4/4 artifacts `done`.
- `openspec list --json` → exactly one active change.
- mkdocs nav validation via a Python YAML walk → 35 nav entries, 0 missing pages.
- **Live CLI runs** producing the measured numbers: `claude --output-format stream-json --verbose`,
  `codex exec --json` (×3, including two `codex exec resume` on one thread), `opencode run
  --format json`, `kimi --output-format stream-json`.
- Python check of the Hub's `SPEC_PATH_RE` against 7 candidate spec paths.

**NOT tested / not run:**

- `mkdocs build` was never executed — only the nav structure was validated. A real build could
  still fail on the new page's content.
- No Python tests, no `pytest`, no `ruff`, no `mypy`, no TypeScript lint were run. **No source
  code was changed**, so nothing needed them, but equally nothing confirms the tree is green.
- Copilot CLI is **not installed on this machine**. Its field names come from GitHub's SDK docs
  plus the user's report from work — never observed here.
- Kimi v1.x wire mode — no v1.x binary available.
- The Hub-side context path (`_post_context_usage_to_hub` → storage → UI) was **never tested end
  to end for any runner**.
- The Hub itself was never started; no UI was viewed. Every UI claim is from reading source.

## Git state

- **Branch:** `master`
- **HEAD:** `968b8db` "Move specs/ to spec/ so the spec root matches the tooling"
- **Dirty:** yes — 104 tracked entries in `git status --short`, ~101 of which predate this session.
- **Unpushed:** `968b8db` (1 commit ahead of origin/master).
- **My tracked change:** `mkdocs.yml` only.
- **My untracked changes:** `docs/archive/autonomous-dev-loop/` and everything under `openspec/`
  (invisible to git — see the warning at the top).
- **Nothing was committed this session.** No branch was created.
- `.claude/handoffs/` is untracked (`??`) and **not** gitignored. It has been left that way by
  prior sessions; worth deciding once whether to gitignore it — session notes usually should be.

## Next steps

1. **Read `openspec/explorations/2026-07-28-spec-journey.md`** — start at the "Execution order"
   section (~line 485). It is the entry point and supersedes anything in this handoff on scope.
2. **Answer the open question for Change 1** before proposing it: should the manifest be
   *generated* (scan the tree and rewrite `spec/index.json` deterministically) or *hand-maintained
   incrementally* by the agent? Generated is more reliable; hand-maintained is the only way to
   capture `parent`, which is semantic. The document suggests a split — generate the file list,
   agent fills `parent` and `order`. **This is a user decision.**
3. **Write the proposal for `add-spec-manifest`** (Change 1) once #2 is answered. Follow the
   structure of `openspec/changes/fix-spec-chat-session-resume/` — `.openspec.yaml`
   (`schema: spec-driven`), `proposal.md`, `design.md`, `specs/<capability>/spec.md`, `tasks.md`.
   Validate with `openspec validate <name> --strict`.
4. Optionally implement Change 0 first — it is a one-word edit at
   `hub/ui/src/components/spec/SpecPage.tsx:119`, `session_mode: 'new'` → `'resume'`, plus a
   new-session control and a continuity indicator. 16 tasks in its `tasks.md`.
5. Consider whether the untracked `openspec/` tree should be backed up, given `git clean -fdx`
   would erase the exploration record and all 22 archived changes.

## Open questions for the user

1. **Change 1 manifest: generated or hand-maintained?** Blocks proposing Change 1. (See step 2.)
2. **Should `openspec/` really be gitignored?** The exploration record, all archived changes, and
   the synced capability specs are unbacked. This predates the session and may be deliberate, but
   the user should know the exploration doc is not in version control.
3. **Should `.claude/handoffs/` be gitignored?** Currently untracked but not ignored.

## Read on resume

- `openspec/explorations/2026-07-28-spec-journey.md` — **read this first.** All decisions,
  measured evidence, execution order, and the per-change open questions.
- `openspec/changes/fix-spec-chat-session-resume/` — the one proposed change, and the structural
  template for writing the next proposal.
- `hub/hub/api/v1/spec.py` — `SPEC_PATH_RE` at line 24; the path contract Change 1 replaces.
- `hub/hub/data/roles/spec.md` — the 91-line role guide Change 1 leans out; lines 31 and 34–44
  are the duplicated conventions.
- `hub/ui/src/components/spec/SpecPage.tsx` — line 119 is Change 0's one-word fix; line 244 is
  the hardcoded 380px chat pane; line 82 is the string-prefix filter Change 4 replaces.
- `src/agentweave/watchdog.py` — `_discover_spec_files()` at line 36 (Change 1);
  `_parse_claude_stream_line` ~2540 and `_write_context_usage` ~1953 (Changes 4 and 6).
- `docs/archive/autonomous-dev-loop/index.md` — prior investigation context, including two
  further confirmed defects not re-verified this session.
