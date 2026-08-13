# Handoff: three stacked causes found and fixed; the spec flow completed end to end for the first time

**Date:** 2026-08-13T11:30+0100 · **Branch:** hub-native-experience · **HEAD:** `21124e7`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0038-2026-08-12-1940-the-hub-owns-the-spec-document-implemented.md`
**Status:** **chunk complete.** 11 commits, 0 pushed, working tree clean.

> **Updated after the suite finished.** `pytest hub/tests/ -q` came back **1630 passed, 10 skipped**
> and everything described below as uncommitted is now committed as `21124e7`. The Hub has been
> restarted onto it (health `ok`). Next steps 1 and 2 are therefore **done**; start at step 3.

## Goal

Make the Hub-owned specification flow actually work for a user, and fix what the operator hits while
using it. The governing lesson of the last two sessions, now proven three more times today: **a
claim of "done" that has not been observed is worth nothing, and a fixed bug frequently reveals
another that it was hiding.**

## Current state

### Committed and working (10 commits, none pushed)

1. `1baa957` + `e6cb919` — **a project that is not a git repository runs its agents in place.**
   Verified live. Also fixed a containment hole this exposed: `ProjectWorkspace.resolve_relative`
   accepted a leading `~`.
2. `acec101` — the shared-directory concurrency trade, settled by the operator and pinned.
3. `f3fc506` + `bb1bdce` + `84989b3` — **a batch of `ask_user` answers arrives as one turn**, not one
   per answer. Verified live on a real agent's own batch.
4. `3293633` — **the turn context states which specification procedure governs.**
5. `1219fed` — **`submit_spec_document` and `recall` added to the described tool surface**, plus
   `test_tool_surface_matches_server.py`, which fails the build when the described surface and the
   served surface disagree.
6. `32139b5` — **the exploration interview is a conversation again**, not an `ask_user` questionnaire.

### Uncommitted — implemented, tested, and driven live; needs the suite then one commit

Change directory `openspec/changes/2026-08-13-the-spec-tool-reaches-the-agent/` (proposal, two spec
deltas, tasks — all written, `openspec validate --changes --strict` passes 10/10).

- **`hub/hub/mcp_server.py`** — the `if __name__ == "__main__": main()` guard moved from line 775 to
  the end of the file. **This is the root cause of everything.** `mcp.run()` never returns, so a
  tool defined below the guard never registers when the server is spawned as a script — which is the
  only way the Hub spawns it. `submit_spec_document` was defined at line 791.
- **`hub/hub/launchability.py`** — new `spec_turn_notice(phase)`.
- **`hub/hub/api/v1/agent_trigger.py`** — new `_spec_phase_for()`; the notice is prepended to the
  turn prompt beside `access_path_notice`, never merged into the recorded message.
- **`hub/tests/test_mcp_server_stdio_surface.py`** — new. Spawns the server as a subprocess from a
  non-package directory and lists tools over the wire.
- **`hub/tests/test_spec_turn_notice.py`** — new. 6 tests.

### The three stacked causes, in the order they were peeled

Each was hiding the next, and each was previously filed as "verification not yet done":

1. **The document was created after the trigger** (fixed 2026-08-12, `1734027`). Held.
2. **`submit_spec_document` was missing from the `## Your tools` list** while the phase block
   instructed its use. The agent believed the inventory, said *"the required `submit_spec_document`
   capability was not exposed in this session"*, and stopped. Fixed in `1219fed`.
3. **The tool was not served at all.** Over stdio, spawned as the Hub spawns it: **15 tools, no
   `submit_spec_document`**. Imported: 16. Four tests asserted the schema of a tool no agent could
   see, because every test imports and an import runs the whole file.

### The other thing found live: prose guidance loses to an available mechanism

Iterations 1 and 2 of the loop had the precedence statement, the conversational floor and the tool
list **all verified present in the delivered context file** — and the agent announced *"I'll use the
OpenSpec exploration workflow"*, ran the questionnaire the floor forbade, and **invented answers**
when its questions went unanswered. Delivery was ruled out first: a probe confirmed
`model_instructions_file` reaches Codex (the model returned a passphrase that existed only in that
file, read-only sandbox, reading nothing).

The fix that worked was moving the directive into the **turn prompt**, beside the operator's
message — the same channel a skill description is matched in. Standing context is read before the
operator's sentence exists.

## Files touched

Working tree has exactly six entries; all are listed here.

| path | what | done? |
|---|---|---|
| `hub/hub/mcp_server.py` | `__main__` guard moved to end of file, with a comment saying nothing may follow it | yes |
| `hub/hub/launchability.py` | **new** `spec_turn_notice(phase)` — returns `None` when no document is open | yes |
| `hub/hub/api/v1/agent_trigger.py` | **new** `_spec_phase_for()`; notice prepended to the prompt; import added | yes |
| `hub/tests/test_mcp_server_stdio_surface.py` | **new**, 3 tests — spawn-vs-import surface equality | yes |
| `hub/tests/test_spec_turn_notice.py` | **new**, 6 tests | yes |
| `openspec/changes/2026-08-13-the-spec-tool-reaches-the-agent/` | **new** — proposal, `specs/agent-tool-surface/spec.md`, `specs/spec-document-authority/spec.md`, tasks | yes |

**Also created, gitignored, not in git status:** `testbed/scratch/spec_loop.py` — the harness that
found all of this. Keep it; it is how the flow gets driven without clicking.

**Deleted, uncommitted, never in git:** `openspec/changes/2026-08-13-a-document-earns-its-name/` held
only a proposal for the random-placeholder naming work. I removed it because an incomplete change
fails `openspec validate`. Nothing in git was lost; it must be rewritten from the design below.

## Key decisions

1. **The `__main__` guard goes last, and a test spawns the process.** Moving the guard fixes today's
   bug; the stdio test is the change, because no importing test can ever see this class of mistake.
   Rejected: restructuring the module, or importing Hub code into the server — it is deliberately
   stdlib+fastmcp only, spawned from an arbitrary cwd.
2. **The phase directive travels with the turn, not only in standing context.** Rejected as
   insufficient (three live runs): more wording in the canonical context. A skill description is
   matched against the operator's message; the countermeasure must arrive in the same channel.
3. **Precedence names no product.** A blocklist dates the moment a different tool is installed and
   implies unnamed ones are fine. Pinned by a test asserting four product names are *absent*.
4. **Prose is the default interview medium; `ask_user` is for a genuine fork.** The charter already
   said "never run this as a questionnaire" — the floor's *"use `ask_user` for anything that changes
   scope"* plus a tool that requires 2–8 options per question overrode it. Rejected: making options
   optional (operator chose otherwise); reinstating skills per project — **Codex reads skills only
   from `~/.codex/skills`, which is global, so a project-folder install reaches Claude and never
   Codex**, the exact failure that removed them; per-project `AGENTS.md`/`CLAUDE.md` — portable but
   static, while turn context is rebuilt every turn.
5. **Answer batching fails toward duplication, not loss.** The completeness check runs against
   *committed* state; checking inside the answering transaction would let two concurrent resolutions
   each see the other outstanding and leave a complete batch delivered to nobody.
6. **Non-git projects run in place, but a *broken* repo still refuses.** A project that has isolation
   must not lose it silently.

## Constraints and user directives (verbatim)

**From this session:**
- *"the document naming can be random. Could be a color and a mythic animal. randomized each time and
  the agent needs to update this as soons as he gets information."*
- *"It's acceptable. The user has to deal with this."* — on two writing agents sharing one directory.
- *"I liked the aw-explore skill better. Now it just ask hard questions with limited amount of
  answers and does not show the architecture etc. Seems like less interactive."*
- *"Can you run a test loop and fix anything that you find with this spec phase?"*
- Chose **"Prose first, ask_user for real forks"** and **"Yes, and say so in the floor"** (sketching).
- Chose **"Move them aside for testing"** for the OpenSpec Codex skills — **they have since been
  restored to `~/.codex/skills/`** at the operator's instruction, and the backup directory
  `~/.codex/_disabled-for-agentweave-testing/` is now empty of them.

**Carried and still binding:**
- **The `ci.yml` question is settled** — *"just push the branch"*. **Do not raise it again.**
- **STANDING DIRECTIVE:** every `tasks.md` splits agent-verifiable from human-only and emits a user
  test guide.
- Handoff cadence: only when asked, or when an openspec change is done.
- *"by measuring pixels aren't you making things a little bit too catered to my monitor?"* — derive
  constants, do not tune them.
- Sensitive to volume and wall-clock; wants short prioritised answers and forward motion.
- From `CLAUDE.md`: never `.agentweave/` / `agentweave.yml` / `spec/` at the repo root; stage paths
  explicitly; openspec never aw-spec skills; `Icon` is the only icon system; `approve_tool_call`
  keeps **no return annotation**; migrations guard for a missing table and bump **both** head
  assertions; `hub/hub/static/ui` refreshed and confirmed with `diff -rq`; **never mark a task
  complete on the strength of a plan existing.**
- From memory: commit each completed checkpoint without asking; live-verify on resume.

## Dead ends

**New this session, most expensive first:**

- **Believing a tool is served because a test imported the module.** The single most costly mistake
  in this whole feature's history. `mcp.run()` does not return; anything below the guard is dead in
  production and alive in CI.
- **Fixing prose guidance by writing more prose in the same place.** Tried twice (precedence
  statement, then conversational floor). Both delivered, both verified present in the file, both
  ignored. Only the channel change worked.
- **Trusting an agent's account of why it failed** — *and also dismissing it.* It said the tool was
  unavailable; the described surface said otherwise; **the agent was right and the surface was
  lying.**
- **A harness that omits `conversation_id`** opens a new conversation per turn, so every turn is a
  cold start. It reads as continuity because the reply quotes the message it was just sent. Fixed in
  `spec_loop.py`; jobs and peer messages also trigger without one (open question 6.5).
- **`git add testbed/scratch`** — gitignored; `git add` fails the whole command.
- **Printing agent replies through a cp1252 console** — a sketch containing `→` crashes the harness.
  `spec_loop.py` reconfigures stdout to UTF-8.
- **`codex exec` outside a trusted dir** needs `--skip-git-repo-check`, and needs stdin closed
  (`$null |`) or it hangs reading stdin.
- **A ten-minute turn timeout kills a real interview.** One loop run died as
  `"turn timed out with no turn/completed notification"` while waiting on answers.

**Carried and still true:**
- **Start the Hub via WMI** so it survives session teardown:
  `Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "cd /d C:\Users\huida\Documents\projects\AgentWeave\hub && C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe -m uvicorn hub.main:app --host 127.0.0.1 --port 8010 > %TEMP%\agentweave-hub.log 2>&1"'}`
- **`openspec` CLI rejects change names starting with a digit** — create and archive by hand.
- **`pytest hub/tests/ tests/` together fails collection** — run separately, with
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **`npm run lint` does not work**; `npx tsc --noEmit` from `hub/ui` is the check.
- **The Hub API needs `Authorization: Bearer <AW_BOOTSTRAP_API_KEY from hub/.env>`.**
- **`git commit -m @'…'@` is PowerShell syntax and the Bash tool is Git Bash.** Use a heredoc into
  `git commit -F -`.

## Verification

**Ran, with real output:**
- `pytest hub/tests/ -q` — **1621 passed, 10 skipped**, at commit `32139b5`.
- `pytest tests/ -q` — **360 passed, 3 skipped**, after the uncommitted changes.
- `pytest` on the affected files after every edit — the last targeted run covering the uncommitted
  work: `test_mcp_server_stdio_surface.py` + `test_mcp_tool_schemas.py` = **21 passed**.
- `ruff check hub/ src/` and `black --check` on all five touched files — clean, after the
  uncommitted changes.
- `npx openspec validate --changes --strict` — **10 passed**; `--specs --strict` — **30 passed**.
- **Live, against the running Hub** (`aw-loop-4`, Codex `gpt-5.6-sol`, Spec Author charter, one
  conversation, two turns): prose interview with four directions and trade-offs, an ASCII sketch,
  four open questions, and it **stopped**. Second turn called `agentweave.submit_spec_document`,
  which **completed**, producing `spec/changes/amber-griffin/spec.html`, 29,997 bytes, title
  `Personal Houseplant Watering Tracker`, **nine requirements `FR-1`…`FR-9`**,
  `<meta name="aw-spec-status" content="exploring">`, the `aw-spec-payload` block, and **zero**
  external resource references. **This closes `2026-08-12-hub-owns-the-spec-document` task 17.6.**
- `model_instructions_file` reaches Codex — probe returned a passphrase existing only in that file.

- `pytest hub/tests/ -q` at `21124e7` — **1630 passed, 10 skipped** (8m31s). This is the run the
  commit was gated on; an earlier attempt was stopped mid-flight and its result was never used.

**NOT run, and it matters:**
- **`npx vitest run` and `npx tsc --noEmit` have not been run since `32139b5`** — no UI file was
  touched after that, so they should be unaffected, but they were not re-run.
- **No Claude-runner agent has been through the spec flow.** Everything live today was Codex.
- **Nobody has read the generated document for quality** (task 17.2) — it is the first one to judge.
- **No document has been taken through `propose` → `approve`** with real content.

## Git state

Branch `hub-native-experience`, HEAD **`21124e7`**, **11 unpushed commits**, working tree **clean**
apart from this handoff. `.claude/handoffs/` is tracked.

**Live environment:** Hub on `:8010`, **PID 9012**, restarted onto `21124e7` and answering health
`ok` — so the `mcp_server.py` fix is live and `submit_spec_document` is served. It has been
restarted many times; find the real PID with
`Get-NetTCPConnection -LocalPort 8010 -State Listen`. Projects in the database:
`aw-testbed`, `newtest` (at `C:\Users\huida\Documents\quicktest`), and **`aw-loop-4`
(`proj-477dab47`, at `C:\Users\huida\Documents\aw-loop-4`) — the successful run; keep it until its
document has been read.**

## Next steps

1. ~~Run the suite, then commit the six paths.~~ **Done** — 1630 passed, committed as `21124e7`.
2. ~~Restart the Hub.~~ **Done** — PID 9012 on `21124e7`, health `ok`.
3. **Read the generated document** at
   `C:\Users\huida\Documents\aw-loop-4\spec\changes\amber-griffin\spec.html` — task 17.2, first
   agent-authored document ever produced.
4. **Rewrite the naming change** the operator asked for: new document paths get a random
   colour-plus-mythic-animal placeholder (`amber-griffin`), fresh each time, and **the agent renames
   the document as soon as the interview establishes what it is.** Identity is `SpecDocument.id`, and
   requirement identifiers, digests and events all hang off it, so a rename moves the file, the
   `path` column and the index entry and nothing else. Needs a rename operation, an MCP tool, and the
   open-document reference in the UI following it. Non-goals settled: not renaming existing
   documents; the agent supplies a subject and the Hub slugifies; no rename after approval.
5. **Run the spec flow with a Claude agent** (17.6 for the other runner).

## Open questions for the user

1. **The ten-minute turn timeout.** A multi-round interview plus operator thinking time exceeds it;
   one loop run died that way. The exploration flow is the feature that produces long turns.
2. **Should a trigger with no `conversation_id` open a new conversation every time?** The UI always
   sends one, so this is not reached from the app — but jobs and peer messages do not.
3. Carried: should `.claude/handoffs/` stay tracked (**125 files**)?

## Read on resume

- `openspec/changes/2026-08-13-the-spec-tool-reaches-the-agent/tasks.md` — sections 1 and 5 are the
  loop's findings and the live evidence; section 6 is what remains for the operator.
- `hub/hub/mcp_server.py` (last 20 lines) — the guard and the comment saying nothing may follow it.
  The easiest thing in this repo to undo by accident.
- `hub/hub/launchability.py` (`spec_turn_notice`) — the turn-prompt directive and why it exists.
- `hub/hub/api/v1/agents.py` (`SPEC_PHASE_DUTIES`, `UNDESCRIBED_TOOLS`, `_tool_surface_lines`) — the
  conversational floor and the described tool surface.
- `testbed/scratch/spec_loop.py` — the harness; gitignored, so it will not appear in a diff.
- `hub/hub/data/charters/spec.md` — the harvested interviewing craft, which was never the problem.
