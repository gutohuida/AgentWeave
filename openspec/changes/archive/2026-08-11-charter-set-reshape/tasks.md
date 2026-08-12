# Tasks — Charter set re-shape (B0)

## 1. Park what is being removed but not discarded

- [x] 1.1 Create `openspec/changes/2026-08-11-charter-set-reshape/parked-phase-guidance/` and move
      the verbatim text of `explorer.md`, `implementer.md`, `context_keeper.md` into it, plus the
      procedural sections cut from `spec.md` (the skill routing table, the `spec/` inventory rules,
      the `spec/index.json` manifest duties). One file each, unedited.
- [x] 1.2 Add a `README.md` to that directory stating what it is: reference material for the change
      that builds phase guidance, loaded by nothing, seeded by nothing. Name the requirement it is
      waiting on (`agent-charter` "A charter names an accountability, not an activity") so a reader
      arriving cold knows why the text was cut rather than deleted.
- [x] 1.3 Assert it is inert — no code path reads `parked-phase-guidance/`, and the charter glob in
      `hub/hub/data/charters/` cannot reach it.

## 2. Rewrite the six surviving charters

Each of 2.1–2.6: remove every escalation to a title, every absent file and command, and every
restatement of a coded rule. Escalation resolves to the operator via `ask_user`.

- [x] 2.1 `tech_lead.md` — absorbs `architect`. Accountable for the technical call: architecture,
      tech-stack choices, and the decision when two approaches conflict. Remove the
      `.agentweave/shared/plan-[task-id].md` session-plan duty (absent file) and the task-assignment
      duties (the transition service's).
- [x] 2.2 `code_reviewer.md` — keep the zero-trust review sequence, which is genuine judgment and
      cites nothing absent. Remove the "Architect or Tech Lead decides" deferral.
- [x] 2.3 `verifier.md` — absorbs `qa_engineer`. Accountable for independent verification: that the
      thing does what was asked, tested against the requirement rather than against the
      implementation.
- [x] 2.4 `guardian.md` — accountable for the standards that outlive one change.
- [x] 2.5 `security_engineer.md` — accountable for the security review boundary.
- [x] 2.6 `spec.md` — the largest rewrite. Keep the judgment listed in design D7. Cut the six
      `aw-spec-*` citations, the `spec/` path inventory, the `spec/index.json` duties, the false
      "the Hub discovers every safe `spec/**/*.html`" claim, and the self-enforced approval gate.

## 3. Author the three new charters

- [x] 3.1 `developer.md` — replaces the six variants. Accountable for the code working: implemented
      from the agreed requirement, tested, and honest about what is not covered. Carries an explicit
      **Scope** line the operator fills in, and no "you are not responsible for" list that assumes a
      sibling agent exists to pick the work up.
- [x] 3.2 `underwriter.md` — assesses and prices the risk, states the basis, and refers anything above
      its authority. States plainly that it may not accept the risk itself.
- [x] 3.3 `underwriting_approver.md` — accepts or declines on the institution's behalf above the
      referral threshold. States plainly that it does not perform the assessment it is judging, and
      that a referral it wrote itself is not one it may approve.
- [x] 3.4 Confirm 3.2 and 3.3 read as a pair: each names the other's step as the one it may not
      perform, without naming the other as a party to *contact* — the separation is a constraint on
      itself, not an escalation route.

## 4. Re-key the manifest and delete the removed seeds

- [x] 4.1 Rewrite `hub/hub/data/charters/charters.json` to the nine entries with display names.
- [x] 4.2 Delete the 15 removed `.md` seeds (`architect`, `backend_dev`, `frontend_dev`,
      `fullstack_dev`, `devops_engineer`, `data_engineer`, `ml_engineer`, `qa_engineer`,
      `technical_writer`, `project_manager`, `coordinator`, `model_router`, `explorer`,
      `implementer`, `context_keeper`).
- [x] 4.3 Verify manifest and directory agree in both directions — every key has a file, every file
      has a key. A key with no file seeds an empty charter; a file with no key seeds nothing while
      still being scanned by `test_agent_facing_text.py`.

## 5. Close the test gap that let this through

- [x] 5.1 `hub/tests/test_agent_facing_text.py` — add the absent-participant assertion, per design D6:
      no seeded charter instructs the agent to contact, escalate to, hand off to, report to, or ask
      another charter's title. Assert on the directive shape, not on a list of titles (D6 records why
      a title list would pass on today's bug).
- [x] 5.2 Same file — add an assertion that no seeded charter names an `aw-*` skill, since nothing
      installs them. This is the specific needle that started B0.
- [x] 5.3 Same file — extend `REMOVED_SUBSYSTEMS` with the shared-file convention actually found in
      the tree: `shared/design-`, `shared/plan-`. The list currently has only `shared/context.md`,
      which is why four charters kept citing siblings of it.
- [x] 5.4 Prove each new assertion fails on the pre-change charter text before keeping it. An
      assertion that passes on the defect it was written for is worse than none.
- [x] 5.5 `hub/tests/test_agents_self_registered.py:91` — replace the `"Backend Developer"` lookup.
      Pick from the manifest rather than hardcoding another name, so the next set change does not
      break it again.
- [x] 5.6 Add a test that the starter set contains a non-software pair, per the new requirement —
      keyed to the manifest, so deleting the pair fails rather than silently narrowing the product's
      claim.

## 6. Verification — agent-verifiable

- [x] 6.1 `pytest hub/tests/ -q` green; record the count against the 1500 baseline.
      **1512 passed, 10 skipped.** Against the 1514 baseline: -24 (12 fewer charter files x 2
      parametrized honesty tests), +18 (9 files x 2 new parametrized assertions), +4 standalone.
- [x] 6.2 `pytest tests/ -q` green (372 baseline). **372 passed, 3 skipped** — no CLI code touched.
- [x] 6.3 `npx openspec validate --changes --strict` and `--specs --strict` pass. **4 and 31.**
- [x] 6.4 Seed a **fresh** project against a scratch database and read back
      `GET /api/v1/projects/<id>/charters`: exactly nine, names matching the manifest, content
      matching the files byte for byte.
- [x] 6.5 Seed a database that already holds the old 21 and confirm the Hub adds, removes, and
      rewrites nothing (the D8 asymmetry, and the one most likely to be "helpfully" broken later).
- [x] 6.6 Grep the nine shipped charters for the full defect inventory in the proposal's table —
      `aw-spec-`, `shared/`, `spec/index.json`, `agentweave.yml`, `roles.json`, `watchdog`,
      `principal`, and each removed charter's display title. Zero hits.
- [x] 6.7 Confirm no live database was written to by any of the above.

## 7. Verification — human-only (the operator runs these)

Closed on the operator's attestation of 2026-08-12, after they created a fresh project, read the
nine charters through the read view shipped by `2026-08-11-charter-read-view`, and answered:
**"No. That's enough."** — 7.4 answered No, nothing they used is among the fifteen removed.
Recorded as their attestation, not as a fresh run: the agent cannot judge whether a set reads as
one worth picking from, and did not.

- [x] 7.1 Does nine charters read as a set you would pick from, or as a set with something missing?
- [x] 7.2 Does `developer` with an empty scope line read as incomplete, or as inviting?
- [x] 7.3 Do the two underwriting charters make the point they are there to make, or read as noise in
      a software tool?
- [x] 7.4 Is anything you actually used among the fifteen removed?

## 8. User test guide

**Setup.** A **fresh** project — not Testbed. Seeding is once-per-project, so an existing project
will show you the old 21 and prove nothing. Create a new project in the Hub against an empty
directory.

1. **The starter set is nine.** Open the Charters screen on the new project.
   *Expect:* nine charters, including one plain `Developer` and two about underwriting.
   *Failure looks like:* twenty-one, or an empty list, or a charter with no content.

2. **Your existing project is untouched.** Switch to Testbed and open its Charters screen.
   *Expect:* everything exactly as you left it, including any charter you have edited.
   *Failure looks like:* charters missing, added, or your edits reverted.

3. **An agent is not sent after something that is not there.** In the new project, bind an agent to
   the `Spec Author` charter and ask it what its first step is on a new feature.
   *Expect:* it interviews you, or asks what you want specified. It does not announce it is running
   `aw-spec-explore`, and does not go looking for `spec/`.
   *Failure looks like:* the agent reporting it cannot find a skill or a directory — the original
   defect.

4. **Escalation reaches you.** Bind an agent to `Code Reviewer`, give it something with a genuine
   design question in it, and let it hit the ambiguity.
   *Expect:* it asks you.
   *Failure looks like:* it says it is escalating to the Tech Lead, or messages an agent that does
   not exist.

5. **The separation is real.** Bind one agent to `Underwriter`, another to `Underwriting Approver`,
   and give the underwriter a case above its authority.
   *Expect:* it assesses, states the basis, and refers rather than accepting.
   *Failure looks like:* it approves its own referral — the one thing the pair exists to prevent.
