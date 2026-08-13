# Tasks — The Hub's specification procedure outranks whatever else is installed

Three sentences of generated context, and one honest limit: no test here can show the agent obeys
them. Section 4 covers delivery; section 5 is the only place obedience can be established.

## 1. Establish what was actually observed

- [x] 1.1 Confirm the document reached the first turn. Without that, this is the already-fixed
      ordering bug rather than a new one.
      **Confirmed:** the queue entry for `run-3bf5d318` carries
      `spec_document = spec/changes/i-would-like-to-create-a-budget-web-app-for-my-home-and-my-usage/spec.html`.
- [x] 1.2 Confirm the phase block was in the delivered context file, not merely in the code that
      builds it.
      **Confirmed** by reading
      `quicktest/.agentweave/worktrees/new-spec/.agentweave/context/new-spec.md`: `### Open
      specification document`, `Phase: **exploring**`, the interview duty, `submit_spec_document`,
      and the no-propose-no-approve line.
- [x] 1.3 Confirm the agent *read* it, rather than the file being written somewhere it never looked.
      **Confirmed:** an earlier run in the same project said *"this workspace is a specification
      interview, not an implementation workspace, and the current spec is intentionally empty. I
      won't invent product scope"* and called `agentweave.ask_user` — both from the block.
- [x] 1.4 Identify the competing procedure and where it came from.
      **`~/.codex/skills/` held `openspec-propose`, `openspec-explore`, `openspec-apply-change`,
      `openspec-archive-change`, `openspec-sync-specs`, plus `~/.codex/prompts/opsx-*.md`.**
      `openspec-propose`'s description — *"Use when the user wants to quickly describe what they
      want to build"* — matches the operator's opening message almost exactly. Authored by
      `openspec`, installed by its CLI; nothing AgentWeave ships. Codex memory checked and clear;
      no `AGENTS.md` at user, project, or worktree level.
- [x] 1.5 Confirm AgentWeave installs nothing into `~/.codex/` or `~/.claude/`, so this is not
      self-inflicted. Carried from `2026-08-12-hub-owns-the-spec-document` task 1.3, which
      established that no code writes a skill directory.

## 2. State precedence in the floor (D1, D2, D3, D4, D5)

- [x] 2.1 Add to the `### Open specification document` block, inside the `phase` branch so it appears
      only where a document is open: the Hub's procedure governs this document, and no other
      specification workflow, skill, command or tool applies to it — including one installed on this
      machine and one the agent has used before.
- [x] 2.2 Direct the agent to tell the operator when it finds a competing workflow, rather than only
      forbidding its use (D2).
- [x] 2.3 Name no product (D5). "No other specification workflow" rather than "not OpenSpec", so a
      tool nobody has heard of is covered and the sentence does not date.
      Pinned as an *absence* by `test_it_names_no_product`, which checks four product names are not
      in the rendered context — so a later edit cannot quietly turn the floor into a blocklist.
- [x] 2.4 Keep it in the code-owned floor, not the charter (D3). It must be present with no charter
      bound.
- [x] 2.5 Do not read, enumerate or disable anything on the machine (D1). No filesystem lookup, no
      runner flag. The diff adds three `lines.append` calls and nothing else.

## 3. Do not overreach

- [x] 3.1 Check the wording against a project that legitimately contains an `openspec/` directory:
      the agent must stay free to *read* it as context about the project. The rule is about which
      authority governs the document, not about which files may be opened (design Risks).
      Handled by making it explicit rather than hoping the wording is read charitably: *"Reading
      such a workflow's files as context about the project is fine. What is not is authoring this
      document through anything but `submit_spec_document`."* `test_reading_a_competing_workflows_files_is_still_allowed`
      pins it. **Whether it lands with a real agent in a real openspec project is 5.4** — this
      repository is exactly such a project, so the case is not hypothetical.

## 4. Tests — agent-verifiable

**What these can and cannot show.** They establish that the sentences are delivered, to every runner,
with and without a charter. **No test here shows the agent obeys them** — that is 5.1, and it needs a
live run.

All in `hub/tests/test_spec_procedure_precedence.py`.

- [x] 4.1 The precedence statement appears in the rendered context when a document is open.
- [x] 4.2 It appears with no charter bound (D3).
      The assertion was first written as "`## Charter` is absent", which was wrong — the section is
      always rendered and says *"No charter is assigned to this agent."* Asserting the absence of
      the heading would have passed for the wrong reason the day the heading changed, so it now
      asserts the no-charter sentence is present alongside the precedence one.
- [x] 4.3 It is absent when no document is open (D4).
- [x] 4.4 It names no specific product (D5) — assert the absence of a product name, so a later edit
      cannot quietly reintroduce a blocklist.
- [x] 4.5 It tells the agent to raise the competing workflow with the operator (D2).
- [x] 4.5b Both runners get it. Added beyond the listed tasks because the live failure was on Codex
      and runner-agnostic delivery is the premise the skills' deletion rested on — asserting it
      costs nothing and assuming it is what produced this change.
- [x] 4.6 `pytest hub/tests/ -q` and `pytest tests/ -q` **run separately** — together they fail
      collection.
- [x] 4.7 `ruff check hub/ src/`, `black` on every file touched.
- [x] 4.8 `npx openspec validate --changes --strict` and `--specs --strict`.

**No UI change**, so no `vitest`, no `tsc`, and no `hub/hub/static/ui` rebuild. The diff is three
`lines.append` calls in `agents.py` and one new test file.

## 5. Verification — human-only (the operator runs these)

**5.1 is the whole change.** Everything above is delivery; this is whether it works.

- [ ] 5.1 **Restore the moved skills and run the flow again.** `~/.codex/_disabled-for-agentweave-testing/`
      holds the five OpenSpec skills and five `opsx-*` prompts; move them back, open a conversation,
      press Explore, and describe something vaguely. Does the agent still announce the OpenSpec
      workflow? **Until this is done, this change states precedence and is not known to achieve it.**
- [ ] 5.2 With the skills still moved aside, confirm the flow is clean — that the OpenSpec behaviour
      really was those skills and not a second cause hiding behind them, the way the ordering bug hid
      this one.
- [ ] 5.3 Run 5.1 with a **Claude** agent as well as a Codex one. The repo's own `.claude/skills/`
      carries the same OpenSpec skills, so a Claude agent working in this repository is exposed to
      the identical conflict.
- [ ] 5.4 In a project that genuinely has an `openspec/` directory, confirm the agent still reads it
      as context and does not refuse to look (3.1).
- [ ] 5.5 Judge whether the agent mentioning a competing workflow is useful or noise. It was added so
      the discovery reaches the operator; if it produces a paragraph every turn, it is worth cutting.

## 6. User test guide

**Setup.** The OpenSpec Codex skills are currently at
`C:\Users\huida\.codex\_disabled-for-agentweave-testing\`. The restore command is in the
`WHY-THESE-ARE-HERE.txt` beside them.

1. **Test clean first.** Leave the skills moved aside. Start an exploration, describe something
   half-formed. The agent should interview you and use `submit_spec_document` — no mention of any
   other workflow.
2. **Then put them back** and repeat. This is the real test: the agent now has a skill whose
   description matches your opening sentence, and the Hub's context says that skill does not apply
   here.
3. **Watch the first sentence.** That is where it went wrong before — *"I'm going to use the OpenSpec
   proposal workflow"* — and it is where you will see whether this worked.
4. **If it mentions OpenSpec but authors through the Hub anyway**, that is the intended outcome, not
   a failure: it found something and told you, which is what it was asked to do.
5. **If it uses OpenSpec anyway**, the stated precedence lost to the matched trigger, and the answer
   is not more wording. Say so and we will look at what the Hub can do that is not an instruction.

**What is deliberately absent:** the Hub does not look at what is installed on your machine, does not
disable your skills, and cannot. It states which procedure governs; the rest is the model's to
honour.
