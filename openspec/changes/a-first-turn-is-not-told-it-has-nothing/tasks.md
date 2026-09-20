# Tasks

**Cite symbols, not line numbers.** A legacy-annotation pass was editing
`hub/hub/launchability.py` in this tree on 2026-09-20 and has already moved the target string once.

## 1. Establish the blast radius before editing anything

- [ ] 1.1 `grep -rn "no MCP tools this turn" .` across the **whole repository** (excluding
  `node_modules/`, `.git/`, `hub/hub/static/ui/`) and write the file list into this file under the
  task. Docs, skill templates and charter text count — the clause may be quoted where no test runs.
- [ ] 1.2 Read all four test files that reference `access_path_notice` —
  `hub/tests/test_agent_trigger.py`, `hub/tests/test_agent_facing_text.py`,
  `hub/tests/test_launchability.py`, `hub/tests/test_tool_surface_matches_server.py` — and record
  for each whether it pins the removed clause, the surrounding text, or neither. A grep is not this
  task; the question is what each test would still prove after the edit.
- [ ] 1.3 Record the current no-MCP notice string verbatim in this file, so every later round can
  diff against what was actually there rather than against a remembered version.

## 2. The notice stops asserting

- [ ] 2.1 In `access_path_notice` (`hub/hub/launchability.py`), no-MCP branch: remove the clause
  claiming the run has no MCP tools this turn. Keep the base address, the route prefix, the
  credential variable name, its `Authorization: Bearer` presentation, the read-from-your-own-
  environment instruction, and the inbound-content sentence — each is required by the spec.
- [ ] 2.2 Leave the comment above that branch in place, including the paragraph prohibiting
  interpolation of the credential value. It explains a constraint the spec still carries.
- [ ] 2.3 Do not touch the MCP branch, `described_access_path`, `harness_has_honoured_mcp`,
  `resolve_access_path`, or anything in `agent_trigger.py`. Confirm with
  `git diff --stat` that exactly one product file changed.

## 3. The tests assert the absence of a claim

- [ ] 3.1 Restage `hub/tests/test_agent_trigger.py`'s two assertions (each currently
  `assert "no MCP tools this turn" in ...`) so each pairs a **negative** — no availability claim in
  the built prompt — with a **positive** on the plane content the requirement demands. Per design
  D5, a bare `not in` assertion passes against an empty prompt and is not acceptable.
- [ ] 3.2 Restage anything 1.2 found pinning the removed clause in the other three test files.
- [ ] 3.3 Add one test that fails on the defect itself: a turn built for an agent with **no prior
  run carrying `mcp_adapter_online_at`**, asserting the prompt makes no claim that the tool surface
  is unavailable. This is the scenario `A run holding the tools is not told it is empty`.
- [ ] 3.4 **Mutation check.** Restore the removed clause in `access_path_notice`, run the tests from
  3.1 and 3.3, and record here that they fail — with the count. Then revert and confirm
  `git diff hub/hub/launchability.py` shows only the intended edit. A test that passes both ways
  proves nothing.

## 4. The corpus

- [ ] 4.1 Apply the delta's two MODIFIED requirements to
  `openspec/specs/agent-capability-plane/spec.md` (via the normal sync at archive time, not by hand
  now). Confirm `openspec validate a-first-turn-is-not-told-it-has-nothing --strict` passes after
  every edit to the change.
- [ ] 4.2 Confirm the F301 prose correction carries **only** the mechanism, and that the
  requirement's conclusion (unreachable by the agent's own tools on the `cli` path) is unchanged and
  its SHALL is byte-identical to today's. `DECISIONS.md` 1d mandates the correction; it does not
  authorise reopening the conclusion.
- [ ] 4.3 Update **F302**'s entry in `scripts/drive/FINDINGS.md` to `fixed <sha>` only once 2.1, 3.1
  and 3.3 have all landed, and say in the same edit that `harness_has_honoured_mcp`'s
  permanent-positive latch (**F340**) is untouched.

## 5. Quality gates, over CI's exact paths

- [ ] 5.1 `ruff check src/ hub/ tests/` — clean.
- [ ] 5.2 `black --check src/ hub/hub/ hub/tests/ tests/ --target-version py311` — clean.
- [ ] 5.3 `mypy src/` — clean. (No `src/` file changes here; run it anyway, because CI does.)
- [ ] 5.4 `hub/ui` is not built or linted, because nothing under `hub/ui/` is touched. Confirm that
  claim with `git diff --name-only` rather than asserting it.

## 6. What must not move

- [ ] 6.1 `py -3.11 -m pytest hub/tests/test_launchability.py hub/tests/test_agent_trigger.py
  hub/tests/test_agent_facing_text.py hub/tests/test_tool_surface_matches_server.py -q` — **write
  the pass/fail counts inline in this task.**
- [ ] 6.2 `py -3.11 -m pytest hub/tests/ -q` in full — **write the actual counts and the duration
  inline in this task.** Per **F392**, a tick on this line citing a log entry that does not exist is
  the exact process defect that let a three-test regression reach `master`; if the number is not
  written here, this task is not done.
- [ ] 6.3 Confirm no permission posture changed: `grep -n "acceptEdits\|permission-prompt-tool"` in
  `hub/hub/runner_commands.py` is byte-identical to `master`, and `git diff` touches neither
  `runner_commands.py` nor `mcp_server.py`. The spec scenario *"A truer description does not
  silently widen permission"* is the requirement this guards.
- [ ] 6.4 Confirm nothing under `hub/ui/src/` or `hub/hub/static/ui/` is in the diff, so no bundle
  refresh is owed and nothing reaches the operator's live app on its next reload.
