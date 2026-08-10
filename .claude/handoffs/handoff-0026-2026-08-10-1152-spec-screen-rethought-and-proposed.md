# Handoff: the Spec screen diagnosed, redirected conversation-first, and proposed

**Date:** 2026-08-10T11:52 · **Branch:** hub-native-experience · **HEAD:** `b53ea7b`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0025-2026-08-10-0405-a1-shipped-and-verified-live.md`
**Status:** chunk complete. 2 commits, both pushed. **Working tree clean.**

## Goal

The operator woke up, looked at the Spec page A1 shipped overnight, and did not like it. They sent a
screenshot and a list of complaints, ending with *"But I don't even know where to begin."*

So this session was not implementation. It was: diagnose what is actually wrong, decide whether it
is a styling problem or a structural one, and — because the operator chose "explore and propose
only" — leave a proposal rather than code.

**The answer reached: it is structural.** Every visible defect traces to the Spec page having two
left rails, which traces to a specification being modelled as *a place you go* rather than *a thing
you work on with an agent*. The proposal inverts that.

## Current state

### Written, NOT implemented: `2026-08-10-conversation-first-spec-workspace` (`b53ea7b`)

`openspec/changes/2026-08-10-conversation-first-spec-workspace/` — proposal, design, tasks, and
deltas on **two** capabilities (`spec-chat-session`, `hub-workspace-shell`).
`npx openspec validate 2026-08-10-conversation-first-spec-workspace --strict` → valid.

**`proposal.md` ends with `**Approved:** _pending_`. Implementation must not begin until the
operator fills that in.** Same gate A1 had.

### The diagnosis, with the evidence

- **`App.tsx:361` passes `compact={activePage === 'spec'}`.** `Sidebar`'s compact mode gates *every*
  branch on `!compact` (lines 180, 217, 250) — it renders the "AW" avatar and **nothing else**. No
  projects, no agents, no conversations, no way back, and no way to undo it. It is not an icon rail;
  it is a blank 40px strip.
- That collapse exists to buy space for `SpecNavigator`, a second left column carrying the document
  library (Library/History) and the page outline.
- With two columns spent, the chat gets what is left (~360px). A1 mounted `AgentOutputPanel` there —
  a surface whose body is `max-w-[820px]`. At that width the composer control row overflows the
  right edge (`Permissions: Edit files` clipped mid-word), the header crowds and truncates, and
  `Jump to newest` lands on the run's completion line.
- **A1 introduced a defect of its own:** `SpecChat.tsx`'s agent `<select>` is the only raw select in
  the application and a *second way to choose an agent* when the rail already does that — the same
  "second application" mistake A1 existed to delete, one layer up. It is why the agent's name
  appears three times in one header.

### The shape proposed

- The open document becomes part of the conversation destination —
  `{ kind: 'conversation'; projectId; agent; conversationId; document }` — so **any** conversation
  can open a document beside it, and a reload restores both.
- `tab: 'spec'` **stays in `PROJECT_TABS`** but resolves *into* a conversation destination with the
  manifest home document open. It becomes a way in, not a second application.
- Proportions: rail (operator width) · conversation **420–560, default 480** · document takes the
  rest, minimum 560. **480 is measured, not chosen** — it is where the composer control row stops
  wrapping.
- `SpecNavigator`'s library column is deleted; `SpecDocumentPicker` (already a Ctrl+K search over
  the full inventory, archives included) is the picker. The outline moves inside the document panel.
- `SpecChat.tsx` is deleted with its `<select>`.
- The rail's automatic collapse is removed; a collapsed rail must stay navigable.

## Files touched

Everything **committed and pushed**; `git status --short` is empty and `git diff --stat HEAD` is
empty.

### New change (`b53ea7b`) — all files new

- `openspec/changes/2026-08-10-conversation-first-spec-workspace/proposal.md` — the diagnosis is the
  Why; ends with the pending approval gate.
- `openspec/changes/2026-08-10-conversation-first-spec-workspace/design.md` — seven decisions plus a
  verification note on why "it rendered" was not evidence.
- `openspec/changes/2026-08-10-conversation-first-spec-workspace/tasks.md` — **section 6
  agent-verifiable, section 7 the human guide**, per the standing directive.
- `openspec/changes/2026-08-10-conversation-first-spec-workspace/specs/spec-chat-session/spec.md` —
  2 ADDED, 2 MODIFIED requirements.
- `openspec/changes/2026-08-10-conversation-first-spec-workspace/specs/hub-workspace-shell/spec.md` —
  1 ADDED requirement (navigation collapses only when the operator asks).

### Handoff chain (`3d7dba4`, and this commit)

- `.claude/handoffs/handoff-0025-2026-08-10-0405-a1-shipped-and-verified-live.md` — written and
  committed earlier in this same session, covering the overnight A1 work.
- `.claude/handoffs/handoff-0026-2026-08-10-1152-spec-screen-rethought-and-proposed.md` — this file.
- `.claude/handoffs/LATEST.md` — **was stale, pointing at 0024.** Handoff 0025 did not update it, so
  `/resume` would have loaded a handoff two generations old. Now points at this one. **Updating
  `LATEST.md` is part of writing a handoff; 0025 missed it.**

**No source code was modified this session.** Not one file under `src/`, `hub/hub/`, or `hub/ui/`.

## Key decisions

1. **The problem is structural, not visual.** Re-proportioning the three columns was offered and the
   operator rejected it. It would have kept two left rails, two agent selectors, and a conversation
   surface rendered somewhere it was not designed for. The overflow is a symptom.
2. **Conversation-first: the conversation is the frame, the document opens beside it.** The
   operator's own instinct, from the T3 code-panel comparison. Chosen over "keep three columns, fix
   the widths" and over "fix only the bugs, decide layout later".
3. **The document lives in the *destination*, not in ephemeral UI state.** Rejected keeping it as
   component state: it could not be linked to, and the operator would lose their place on every
   reload. Rejected a separate `tab: 'spec'` page: that is the cause being preserved.
4. **The Spec tab survives as an entry point.** Rejected deleting it — without one, finding a
   specification would require already being in a conversation and knowing to press Ctrl+K.
   **This is the decision most worth the operator overruling; it is flagged as such in the
   summary they read, and they did not overrule it.**
5. **The document gets the *larger* share when open.** "Composer takes centre stage" is about which
   surface is the frame, not which is widest — a specification is a document to read, and a chat
   column that crowds it trades one unreadable pane for another.
6. **The library column is deleted, not moved.** `SpecDocumentPicker` already does the job better.
   Only the outline needed a home.
7. **Two separate rail faults, fixed separately:** *automatic* (removed outright — no destination
   may change what the operator can navigate to) and *blank* (a collapsed rail must remain
   navigable, with names and tooltips). A rail that renders no destinations is hidden, not collapsed.
8. **The composer control row wraps and truncates its *value*, keeping the control name.** Rejected
   an overflow menu: it would hide the permission posture, which is the one value that must be
   readable at a glance before sending.
9. **The iframe contract is carried across untouched**, with a test asserting `sandbox="allow-scripts"`
   without `allow-same-origin` — a layout change is exactly the kind of work that quietly relaxes a
   security boundary for convenience.
10. **Verification changes from presence to geometry.** A1 asserted the permission card existed in
    the DOM and reported the requirement verified. It existed inside an overflowing pane. Every live
    check in the new change measures `right <= host.right`, `scrollWidth <= clientWidth`, and
    pairwise non-overlap, at four widths, with screenshots. **A presence-only assertion does not
    close a task in that change.**
11. **No separate exploration document was written.** The reasoning lives in `proposal.md`'s Why and
    `design.md`'s decisions. Deliberate: 2026-08-10 spent a session collapsing four documents
    planning one territory into one, and adding a fifth describing the same thing would recreate it.
12. **The A1 `<select>` is recorded as a lesson, not a line.** `design.md` Decision 7 and task 5.5:
    the standing check is *"how many ways does the application offer to do this?"*

## Constraints and user directives (verbatim)

**From this session:**
- *"Don't like the fact that the left panel is collapsing automatically showing no icons there."*
- *"Should we have a collapsible mode for the left panel? Should we actually put the file navigation
  in the left panel? Should we leave the left panel untouched?"*
- *"The chat block have multiple problems. The agent selector on top looks outdated."*
- *"Depending on the size of the right box a lot of things overflow or disappear. You can see that on
  the bottom right corner the configs are overflowing and on the top some things disappear."*
- *"Maybe we have to find a different layout and approach for this screen. But I don't even know
  where to begin."*
- *"Should the composer take center stage and the spec be a side screen like t3 does with code? You
  can open code on the right side? What could we do?"*
- Chose **"Conversation-first, document beside it"** and **"Explore and propose only — don't build."**
- *"okay great looks good. do a handoff now"*

**Carried and still binding:**
- **STANDING DIRECTIVE:** *"when creating the spec we have to think how to manually test this. How
  the agent can test what's the expected behavior and what can only be done by the user to create a
  guide for the user to test."* — applied: `tasks.md` §6/§7.
- *"Wait. Are you already implementing? Should we dive in first…"* — **lay out the plan before
  building anything non-trivial.** This session was that, by explicit choice.
- *"Kind of lost"* — **the operator is sensitive to volume.** Answer briefly; point at one file.
- *"What is taking so long?"* — sensitive to wall-clock.
- *"The spec should still be generated as html"*; *"no need for backups everything is test env"*;
  *"B. fixed back to the agent's conversation. Yes, no agent deletion. Just archive."*;
  *"I don't want it to be colorful it should be like the chat box but maybe a little lighter"*;
  *"first I think we have to many we need to cut some of those"* (the 21 charters);
  *"the charter exists to give instructions so I can use agentweave for more then developing."*
- From `CLAUDE.md`: never create `.agentweave/`, `agentweave.yml` or `spec/` at the repo root; stage
  paths explicitly; openspec never aw-spec skills; `Icon` is the only icon system;
  `approve_tool_call` keeps **no return annotation**; `hub/hub/static/ui` is a committed artefact
  refreshed after `npm run build` and confirmed with `diff -rq`; never mark a task complete on the
  strength of a plan existing.
- From memory: commit each completed checkpoint without asking; live-verify prior claimed work on
  resume; ask the operator for agent + model choice when setting up agents.

## Dead ends

**New this session:**
- **The installed `openspec` CLI does not have the commands the `openspec-propose` skill calls.**
  `openspec new change`, `openspec status --change`, and `openspec instructions` do not exist in this
  version — `npx openspec --help` lists `init update list view change archive spec config schema
  workspace context-store initiative validate show feedback completion`. Those are the experimental
  `opsx:` schema workflow. **Create the change directory by hand, matching the shape of prior
  changes** (`proposal.md`, `design.md`, `tasks.md`, `specs/<capability>/spec.md`; no
  `.openspec.yaml` — A1 has none either). `npx openspec validate <name> --strict` does work.
- **`.claude/handoffs/LATEST.md` is not updated automatically.** It was two generations stale.
  Update it whenever a handoff is written.

**Carried and still true:**
- **The `t3-code` preview tools return a schema-validation error on every mutating call**
  (`preview_type`, `preview_click`, `preview_press`) — *and the action usually happened anyway.*
  Never trust the error; verify with `preview_evaluate` after. `type` and `click` work; **`press`
  does not** — a synthetic `Tab` from a focused text area left `activeElement` unmoved.
- **`preview_resize` times out** (15s and 40s both tried). Viewport stays 1280×800.
- **`preview_evaluate` must return an object**, not a bare array — wrap it: `{ hits: [...] }`.
- **Do not set `document.documentElement.dataset.mode` by hand to test light mode.** `App.tsx:92`
  owns it and the page ends up mixed — light text tokens over dark backgrounds, nonsense contrast
  numbers. Compute ramp ratios from `index.css` in Python instead.
- **PowerShell here-strings break on bash-style quote escaping.** Use the Write tool for a commit
  message file, then `git commit -F <file>`.
- **PowerShell cwd persists between calls.** `Set-Location` to the repo root first.
- **`cd hub/ui` fails from the Bash tool** even at the repo root — use the absolute path.
- **Do not put a filesystem-wide `find` in a compound Bash command** — it hits the 120s timeout.
- **The spec API is at `/api/v1/projects/{id}/project/specs`**, not `/api/v1/specs`.
- **`openspec validate` wants SHALL/MUST on the *first line* of a requirement body.**
- **`npm run lint` does not work at all** (ESLint 9 needs a flat config the repo lacks); `tsc` checks.
- **`pytest hub/tests/ tests/` together fails collection** — run separately.
- **The default `python` on PATH has no pytest** — use
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **The Hub API rejects `X-API-Key`** — use `Authorization: Bearer <key>`.
- **Adding a hook to a component breaks every test that mocks that api module.** For navigation
  tests, stub the chat component rather than adding a dozen api mocks.

## Verification

**Ran this session, with real output:**
- `npx openspec validate 2026-08-10-conversation-first-spec-workspace --strict` — **valid.**
- `npx openspec validate --specs --strict` — **27 passed, 0 failed.**
- `git status --short` — empty. `git diff --stat HEAD` — empty.
  `git log origin/hub-native-experience..HEAD` — empty.

**Not run this session, and deliberately so: no test suite, no build, no browser.** No source file
was modified. The suite results below were measured at `1b0b7cf`, the last commit that changed code;
`3d7dba4` and `b53ea7b` are documentation only, so they still describe this HEAD:
- `pytest hub/tests/` — 1280 passed, 10 skipped · `pytest tests/` — 372 passed, 3 skipped
- `npx vitest run` — 661 passed / 73 files · `npx tsc --noEmit` — clean
- `ruff` / `black` / `mypy src/` — clean · `hub/hub/static/ui` — `diff -rq` identical

**Explicitly NOT verified — do not assume:**
- **The proposed layout has never been built or seen.** Every number in it — 420/480/560, the
  document's 560 minimum, the overlay breakpoint — is reasoned from the current code, **not
  measured in a browser.** Task 3.3 must confirm 480 actually fits the control row before it is
  treated as settled.
- **All five human-only verification items remain UNRUN** across A1 and the two older changes
  (pointer feel, keyboard traversal, reduced motion, contrast decision). See handoff 0025.
- **CI has still never run on this branch.** `ci.yml` triggers only on push/PR to `master`. Now
  **330 commits** (measured: `git rev-list --count master..HEAD`) with no Linux, no macOS, and no
  Python 3.8/3.9/3.10/3.12.
- **Migration `0051` has only been applied to SQLite.**
- Carried: no live agent has called `submit_checkpoint_notes` or `recall`; `files_changed` has never
  been observed non-empty; the checkpoint final-warning banner has never been seen in a browser.

## Git state

Branch `hub-native-experience`, HEAD **`b53ea7b`**, **working tree clean, everything pushed**
(`git status --short` empty, `git diff --stat HEAD` empty, nothing unpushed).
**330 commits ahead of master, 0 behind** (`git rev-list --count master..HEAD`; handoff 0025's
"327" was arithmetic rather than measurement — trust the command, not the running total).

**2 commits this session**, `1b0b7cf..b53ea7b`:

| sha | what |
|---|---|
| `3d7dba4` | Handoff 0025: A1 shipped, demonstrated live, and four stuck tasks unstuck |
| `b53ea7b` | Propose: the conversation becomes the frame and the spec opens beside it |

(A third, this handoff, follows.)

## Next steps

1. **Ask the operator to approve or amend the proposal.** Edit the last line of
   `openspec/changes/2026-08-10-conversation-first-spec-workspace/proposal.md` from
   `**Approved:** _pending_` to `**Approved:** 2026-08-__`. **Nothing in that change may start
   first — including task 1.1.** If they want to reconsider one thing, make it `design.md`
   Decision 1: whether `tab: 'spec'` survives as an entry point.
2. **Once approved, start task 1.1:** add `document: string | null` to the `conversation` variant of
   `WorkspaceDestination` in `hub/ui/src/lib/navigation.ts` (the type union is at lines ~52–62), and
   carry it in the URL beside the conversation.
3. **Unblocked without approval, and worth ~20 minutes of operator time:** the contrast decision,
   `openspec/changes/2026-08-04-hub-charcoal-visual-refresh/tasks.md` task **8.11** — AA 4.5 and lose
   the third text level, 3.0 and keep it, or a recorded exemption. It is the only thing blocking that
   change from archiving.
4. **One reduced-motion sitting closes three tasks** — charcoal 8.10, contextual-navigation 7.7, and
   the new change's 7.5 are the same check. One keyboard sitting closes A1 6.3 and charcoal 8.8.
5. **Archive `2026-08-04-hub-contextual-navigation`** once 7.7 is run; 4.7 is already closed.
6. **The `ci.yml` branch trigger** — raised four times now, unanswered. One line adding
   `hub-native-experience` to `on.push.branches`.

## Open questions for the user

1. **Approve the conversation-first proposal?** Blocking next-step 2.
2. **Does `tab: 'spec'` survive as an entry point?** `design.md` Decision 1 says yes; flagged as the
   call most worth overruling.
3. **The contrast bar for 1.0** — AA 4.5 (loses the third text level), 3.0 (keeps it), or a recorded
   exemption. Blocks the charcoal archive.
4. **The `ci.yml` branch trigger** — yes or no.
5. **How many charters, and which non-software domains should the starter set demonstrate?**
   **Still blocks B0.**
6. **Is "explore" a phase, or just the absence of one?** Affects B5's phase model.
7. **Should the propose offer come from the agent mid-turn, or from the machine at a threshold?**
8. Carried and unanswered across eleven handoffs: **should `.claude/handoffs/` stay tracked?** It is
   not in `.gitignore` and is committed. Now 112 files.
9. Carried: the two model-less default runners on `proj-cddb0827`;
   `testbed/CHECKPOINT-TEST-GUIDE.md` still names the old project `proj-84d218db`; peer-thread
   grouping deferred 2026-08-08; titling should migrate onto the Worker.

## Read on resume

- `openspec/changes/2026-08-10-conversation-first-spec-workspace/proposal.md` — **read this first.**
  The diagnosis and the shape, in one page. `design.md` beside it for the seven decisions.
- `.claude/handoffs/handoff-0025-2026-08-10-0405-a1-shipped-and-verified-live.md` — what A1 actually
  shipped and how it was verified live. Needed to understand what the new change is changing.
- `hub/ui/src/components/layout/Sidebar.tsx` — the `!compact` gating at lines 180/217/250 that makes
  the collapsed rail blank. Task 2.2 rewrites it.
- `hub/ui/src/lib/navigation.ts` — the `WorkspaceDestination` union task 1.1 extends.
- `hub/ui/src/components/spec/SpecPage.tsx` and `SpecWorkspace.tsx` — the three-column structure the
  change dismantles.
- `openspec/explorations/2026-08-10-specification-and-surface-program-roadmap.md` — the orientation
  document. Program A is complete bar its human checks; this change is a correction to A1, and B is
  what follows.
