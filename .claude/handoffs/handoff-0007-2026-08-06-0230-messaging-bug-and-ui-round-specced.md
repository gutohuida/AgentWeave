# Handoff: Agent messaging bug root-caused, two changes specced and approved-pending, none implemented

**Date:** 2026-08-06T02:30 · **Branch:** hub-native-experience · **HEAD:** 4d76cdd
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** .claude/handoffs/handoff-0006-2026-08-06-0058-hub-charcoal-and-model-control-complete.md
**Status:** chunk complete — specification only. **No product code was written this session.**
Five commits, all under `openspec/changes/`.

## Goal

The operator reviewed the shipped charcoal refresh and reported eight problems — seven visual, one
functional ("Agentweave send message is failing. The agents tries to communicate with another agent
but fails"). This session was to **specify** the fixes, not implement them. The messaging failure
turned out to be the important one and consumed most of the session: it was root-caused empirically
against a real Codex CLI rather than reasoned about, and the answer changed the design twice.

The next session implements. Nothing here is built.

## Current state

**Three openspec changes exist, all `openspec validate --strict` clean, all `**Approved:** _pending_`,
none implemented:**

1. **`2026-08-06-agent-messaging-delivery`** — the bug. 8 sections, ~60 tasks. Section 1 is already
   `[x]` (the empirical investigation was done this session, results recorded).
2. **`2026-08-06-hub-composer-and-chrome-refinement`** — the UI round. 10 sections, ~80 tasks. All
   open. Independent of #1; can be worked in parallel.
3. **`2026-08-06-operator-in-the-loop-turns`** — **DEFERRED by operator decision, do not start.**
   Marked do-not-start in both `proposal.md` and `tasks.md`. Kept only because its research
   (the measured Codex elicitation limitation) is expensive to re-derive.

**A test environment was built and is live** — see "Live environment" below.

## Files touched

Every file this session is new, under `openspec/changes/`. Nothing in `src/`, `hub/hub/`, or
`hub/ui/` was modified. The two pre-existing dirty files (`M .claude/handoffs/handoff-0001-...md`,
`M Makefile`) are **not mine** — they have carried across every handoff since handoff-0001 and are
open question 2 below.

New, committed:

- `openspec/changes/2026-08-06-agent-messaging-delivery/proposal.md` — the three defects, complete.
- `openspec/changes/2026-08-06-agent-messaging-delivery/design.md` — Decision 1 (the `exec`
  measurement table), Decision 1a (the app-server finding), Decisions 2-5.
- `openspec/changes/2026-08-06-agent-messaging-delivery/implications-codex-appserver.md` — nine
  sections on what the transport change actually costs. **The most important file in this handoff.**
- `openspec/changes/2026-08-06-agent-messaging-delivery/tasks.md` — §1 checked, §2-8 open.
- `openspec/changes/2026-08-06-agent-messaging-delivery/specs/agent-tool-surface/spec.md`
- `openspec/changes/2026-08-06-agent-messaging-delivery/specs/runtime-diagnostics/spec.md`
- `openspec/changes/2026-08-06-hub-composer-and-chrome-refinement/proposal.md`
- `openspec/changes/2026-08-06-hub-composer-and-chrome-refinement/design.md`
- `openspec/changes/2026-08-06-hub-composer-and-chrome-refinement/tasks.md`
- `.../specs/agent-composer/spec.md`, `.../specs/hub-workspace-shell/spec.md`,
  `.../specs/local-project-workspace/spec.md`, `.../specs/operator-agent-creation/spec.md`
- `openspec/changes/2026-08-06-operator-in-the-loop-turns/` — proposal, design, tasks, and
  `specs/agent-tool-surface/spec.md`, `specs/agent-conversation-workspace/spec.md`. **Deferred.**

Also created: `testbed/two-codex-mini/workspace/` — a real git-initialised workspace backing the live
test project. It is inside the repo but **gitignored** (`testbed/.gitignore:3` is `*`), which is why
it does not appear in `git status`. Nothing to clean up.

## Key decisions

1. **Split into three changes rather than one.** A functional bug and a visual round have different
   risk, different reviewers, and different urgency. Rejected: one combined change, which would have
   made the UI work wait on a runner rearchitecture.
2. **Root-cause by experiment, not by reading code.** The first suspect (`approvals_reviewer = "user"`
   in `~/.codex/config.toml`) was **wrong** — `--ignore-user-config` still reproduced the failure.
   Had the spec been written from that suspicion it would have shipped a fix that did nothing.
3. **`codex exec` cannot grant MCP tool calls while keeping the sandbox** — measured, not inferred.
   `approval_policy="never"` means never *ask* (→ auto-deny), and `mcp_servers.<name>` accepts only
   `enabled` and `startup_timeout_sec` under `--strict-config`. The three settings that *do* permit
   the call (`auto_review`, `guardian_subagent`, `danger-full-access`) each also permitted a verified
   write outside the workspace.
4. **A requirement was written, invalidated by measurement, then restored.** "Collaboration does not
   cost the sandbox" → weakened to an operator-owned trade → **restored to the strong form** once
   app-server was found. The middle state is gone from the spec but is in commit `f204ade` if the
   reasoning is ever needed.
5. **Move the Codex runner from `codex exec` to `codex app-server`.** The operator proposed this
   ("t3 also calls codex... I believe they use a server approach"). Verified by driving the real
   JSON-RPC protocol. Rejected alternatives: `auto_review` (loses the sandbox), leaving it broken.
6. **Approve only `codex_approval_kind == "mcp_tool_call"` AND our own `serverName`** — both
   conditions. Rejected: approving all elicitations, which would grant any MCP server the Hub ever
   registers.
7. **Per-turn app-server process first, not per-agent long-lived.** Makes it a transport swap
   verifiable one-for-one against today. Long-lived is a follow-on with its own evidence.
8. **Keep the `exec` path alive** until app-server is proven equivalent. `app-server` is marked
   `[experimental]`.
9. **Land the `HUB_URL` fix (§3) before the transport rewrite (§2).** Independent, small, and it is
   what stops an agent's authenticated write reaching another Hub.
10. **Fix `ghost`'s hover border in the primitive, not in the composer.** One line in `button.tsx`
    with repo-wide effect; the alternative (restyling `ControlPill` in place) leaves every other
    quiet control still drawing a box on hover.
11. **Provider marks as inline SVG inside the existing `Icon` module.** `CLAUDE.md` forbids a second
    icon system; brand marks are not in lucide. Inline SVG adds no dependency, webfont, or network
    request — the exact failure the rule was written against.
12. **Native OS folder dialog from the Hub's Python process.** t3code uses Electron's
    `showOpenDialog`; the Hub has no Electron, and the browser's `showDirectoryPicker()` deliberately
    never returns a path. The Hub runs locally, so it can open a host dialog itself. Native mode
    only; Docker keeps the in-app browser.
13. **Block `ask_user` in the Hub, not via MCP elicitation** (deferred change). Elicitation was
    measured as declined by Codex. Blocking inside the tool call is provider-agnostic and needs no
    new UI protocol.
14. **Left the "Live Verify" project and its agents alone** — the Hub has no delete API for projects
    or agents (verified: `projects.py` has no DELETE route, `agents.py` has no DELETE route). The
    operator chose "create a new project" over deleting DB rows directly.

## Constraints and user directives (verbatim)

- **"Ohhh create a new project then"** — when told project/agent deletion doesn't exist, rather than
  editing the DB directly.
- **"Yeah add it for us too."** — the T3-style model picker (search / grouping / favourites) is in
  scope; it is now §4b of the UI change.
- **"I think operator in the loop we can wait on it... don't want to overload the dev. Maybe write
  the spec but revisit later it's not a priority for now I think. We have to finish this batch
  first."** — why change #3 is deferred rather than dropped.
- **"t3.code. It's a opensource project. It's installed here. But you can clone it if you would
  like https://github.com/pingdotgg/t3code"** — the named visual reference (MIT).
- **"Docker mode is a non issue because I think nobody will use it"** — carried forward from an
  earlier session; still honoured, Docker paths are not exercised.
- From `CLAUDE.md`, load-bearing throughout: never create `.agentweave/`, `agentweave.yml`, or
  `spec/` at the repo root; `Icon` wraps `lucide-react` and there must be exactly one icon system;
  **stage paths explicitly — `git add -A` sweeps in untracked `.claude/handoffs/` scratch** (every
  commit this session used an explicit path).
- From memory (`feedback_always_commit_checkpoints`): commit each completed checkpoint without
  asking. All five commits happened unprompted.
- From memory (`feedback_verify_on_resume`): live-verify prior claimed work on resume. Done at the
  start of this session — branch/HEAD/dirty state matched handoff-0006 exactly, and the dev server
  was confirmed still listening.

## Dead ends

- **`approvals_reviewer = "user"` is not the cause.** `--ignore-user-config` reproduces the
  cancellation. It is Codex's default behaviour, not a local misconfiguration. This was the leading
  hypothesis and it was wrong.
- **`approval_policy="never"` does not auto-approve.** It means never *ask*, which resolves an
  approval as denied. Recognised by `--strict-config`, and useless here.
- **`sandbox_workspace_write.network_access=true`** — no effect. MCP calls are not blocked by network
  policy.
- **Per-server MCP trust keys do not exist.** Tested against a *complete* server definition (an
  earlier test was invalid — omitting `command`/`args` produced a misleading "invalid transport"
  error that masked the real result). `mcp_servers.<name>` accepts `enabled` and
  `startup_timeout_sec`; rejects `tool_approval`, `auto_approve`, `trust`, `trusted`,
  `approval_policy`.
- **`approvals_reviewer="guardian_subagent"` does not protect the sandbox.** It permitted the same
  outside-workspace write `auto_review` did, while additionally spending model calls per approval.
- **MCP-server-initiated elicitation is declined by Codex.** A `ctx.elicit(...)` from a fastmcp
  server never reaches the app-server client; the tool got a declined result in every run. Declaring
  `mcpServerOpenaiFormElicitation: true` and `experimentalApi: true` in `initialize` changed nothing.
  Precise cause not established. **This is why the deferred change blocks in the Hub instead.**
- **`preview_snapshot` (t3-code MCP) returns an enormous payload** — one call consumed a large
  fraction of the window and was truncated. Use it at most once, or prefer reading source.
- **`git commit -m` with a heredoc inside a `bash -c` containing markdown backticks/quotes** failed
  twice with "unexpected EOF". Writing the body with the Write tool and appending it worked.

## Verification

**Ran, with real output:**
- `openspec validate <name> --strict` — all three changes **valid**. Re-run after every edit.
- Live reproduction of the messaging bug, twice, against real Codex agents through the Hub API.
- `codex exec` probe matrix with a throwaway one-tool MCP server — 8 configurations, table in
  `design.md` Decision 1.
- Sandbox breach test (agent told to write outside its workspace) under default / `auto_review` /
  `guardian_subagent` — default blocked it, the other two allowed it, file presence checked on disk.
- `codex app-server` driven directly over JSON-RPC: `initialize` → `thread/start` →
  `turn/start`, all server→client requests logged, approvals answered selectively. MCP tool executed
  while an outside-workspace write was refused **in the same turn**.
- `codex app-server generate-json-schema` — authoritative method list from the installed CLI.
- `codex exec --strict-config` key-recognition probes.

**Explicitly NOT run — do not assume:**
- **`pytest hub/tests` and the frontend suite were NOT run this session.** No product code changed,
  so nothing should have moved — but this is an assumption, not a measurement.
- No UI change was made, so none was visually verified.
- The app-server finding is from a **standalone probe script, not through the Hub.** It has never run
  inside `agent_trigger.py`.
- Codex version tested: **0.146.0 only**, on Windows 11.
- Claude's runner was **not** probed for the same MCP defect. This is task §2.15 and is open.
- Whether existing Codex session IDs resume through `thread/resume` is **unknown and unverified**.

## Git state

Branch `hub-native-experience`, HEAD `4d76cdd`, **no upstream configured — nothing has ever been
pushed on this branch.**

Five commits this session: `ab85527`, `f204ade`, `54e8275`, `bbeda13`, `4d76cdd`.

Uncommitted, all pre-existing and none from this session:
- `M .claude/handoffs/handoff-0001-...md`, `M Makefile` (12 insertions, 4 deletions total)
- `?? data/`, `?? scripts/`, `?? .claude/skills/{handoff,resume,review-iteration}/`,
  `?? .claude/handoffs/*.md`, `?? openspec/explorations/...`,
  `?? src/agentweave/templates/skills/{handoff,resume}.md`, `?? tests/test_handoff_resume_templates.py`

## Live environment

- **Hub dev server** on `127.0.0.1:8010` (`uvicorn hub.main:app`, no `--reload`, so it will not pick
  up code changes without a restart). API key `aw_live_58ab7d84a1bf7b34eb2d1b424875bacd`, from
  `hub/.env`. Disposable — kill it whenever.
- **`Two Codex Mini`** (`proj-d9b5ed67`) at `testbed/two-codex-mini/workspace`, agents
  `codex-mini-1` / `codex-mini-2`, both on `runner-f787147b` (`codex`, `gpt-5.4-mini`).
  **`codex-mini-1` has `config.yolo = true`** — set during debugging and deliberately left so the
  second failure mode is reproducible. Reset it before treating that agent as a default-config agent.
- **`Live Verify`** (`proj-de54b547`) — the previous session's claude test project, still present.
- **Port 8000 is occupied by an older Dockerised Hub** (serves the removed `cosmic` theme). This is
  not incidental — it is what made the `HUB_URL` bug produce a real mis-delivery. Useful to keep for
  reproducing task §3.8.
- `/tmp/t3code` — the cloned MIT reference repo (~301MB), outside the repo. Re-clone from
  `https://github.com/pingdotgg/t3code` if gone.

## Next steps

1. **Sync `2026-08-04-hub-model-control-and-provisioning` to the main specs** (`openspec-sync-specs`
   skill). The UI change's `local-project-workspace` delta extends "The operator can browse for a
   project directory", which that change introduced and which is **not yet in
   `openspec/specs/local-project-workspace/spec.md`**. Until it is synced, the UI change cannot be
   archived. This is the one hard ordering constraint in the batch.
2. Decide whether to archive the three implemented-but-unarchived 2026-08-04 changes
   (`hub-charcoal-visual-refresh` 39/3, `hub-contextual-navigation` 43/2,
   `hub-model-control-and-provisioning` 52/1 — the open boxes are the honestly-unverifiable ones).
3. **Implement `2026-08-06-agent-messaging-delivery` §3 first** — in
   `hub/hub/api/v1/agent_trigger.py` line ~357, replace
   `env["HUB_URL"] = os.environ.get("HUB_URL", f"http://{host}:{settings.aw_port}")` with a value
   derived from the address the Hub actually bound during lifespan startup. Small, independent, and
   it is what stops an agent's authenticated action reaching a different Hub.
4. Then §2 — the app-server transport. **Read `implications-codex-appserver.md` in full before
   starting.** §2 of that file (unanswered request ⇒ hung turn, no protocol timeout) is the thing
   most likely to cost a day.
5. Before writing §2 code, **verify whether existing Codex session IDs resume through
   `thread/resume`.** If they do not, every existing Codex conversation migrates or breaks — an
   operator-visible decision that must be made deliberately, not discovered.
6. The UI change can proceed in parallel by a different worker; it shares no files with the
   messaging change.

## Open questions for the user

Carried forward, untouched, across seven handoffs:
1. What should happen to untracked `data/agentweave.db` — gitignore, or commit?
2. `M .claude/handoffs/handoff-0001-...md` and `M Makefile` — intentional WIP, or commit/revert?
3. The `review-0002` agent-name uniqueness gap — still open, still not investigated.

Still open from handoff-0006:
4. `64dbb4b "Add harness-audit and harness-refresh skills"` was not written by the session that saw
   it appear. Expected, or worth investigating?
5. Should `Live Verify` (`proj-de54b547`) and its two claude agents be kept, or removed once
   deletion exists?

New this session:
6. Approve the two active changes for implementation? Both are `**Approved:** _pending_`.
7. Should `hub-native-experience` be pushed? It has no upstream and has never been pushed.
8. Should the Hub gain project/agent deletion? Its absence forced the "create a new project" route
   and will keep accumulating test projects. Not specced anywhere.

## Read on resume

- `openspec/changes/2026-08-06-agent-messaging-delivery/implications-codex-appserver.md` — the nine
  consequences of the transport change. Read before touching the Codex runner.
- `openspec/changes/2026-08-06-agent-messaging-delivery/design.md` — Decision 1's measurement table
  and Decision 1a's app-server verification, with the exact evidence.
- `openspec/changes/2026-08-06-agent-messaging-delivery/tasks.md` — the implementation ledger; §1 is
  done, start at §3.
- `openspec/changes/2026-08-06-hub-composer-and-chrome-refinement/tasks.md` — the UI ledger, all open.
- `hub/hub/api/v1/agent_trigger.py` — around line 357, for next step 3.
- `hub/hub/runner_commands.py` — `_build_codex_command` at line ~147, the site §2 replaces.
