"""D-2: write a machine-readable `**Status:**` line into each unclassified finding.

Run once per batch, from the repo root, under `py -3.11`. Idempotent by assertion: it refuses
to insert where a `**Status:**` line is already the first body line, so a second run is a no-op
rather than a duplicate.

The classification each line states was made by reading the section and its cross-references,
not by this file. This file only places the text.
"""

import importlib.util

spec = importlib.util.spec_from_file_location("cf", "scripts/classify_findings.py")
cf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cf)
lines = cf.load()
res = {r["num"]: r for r in cf.classify(lines)}

TAG = " [classified 2026-09-09, D-2]"

S = {
    109: """**Status:** fixed `d9ad1e0` (2026-09-04, by F285's change). The 2026-08-29 decision recorded
below was **reversed**: CI made the file-backed fixture unavoidable and the operator took it.
`hub/tests/conftest.py:22-36` now names F285 and states the same three candidates this entry
measured. *"Do not re-propose the file-backed fixture"* no longer applies -- it shipped.""",
    111: """**Status:** open. The wrong sentence still ships: `POST /agents/register` is live at
`hub/hub/api/v1/agents.py:2144` (verified 2026-09-09). The operator's 2026-08-29 decision settled
the *route* out -- delete self-registration, alongside F3 -- rather than taking it. That deletion
is unimplemented, and F3 is itself still open.""",
    119: """**Status:** open on the CLI half. The Hub half landed -- `hub/hub/scheduler.py:57`
`_safe_error_summary` calls `redact_secrets` (verified 2026-09-09). `src/agentweave/diagnostics.py`
keeps the broad pre-F31 third alternative deliberately, and the question this entry ends on --
should the CLI's catch-all be narrowed -- has never been put to the operator or answered.""",
    127: """**Status:** open. Reproduced deterministically (`t_run_while_busy2.py`, 7/7) and never
repaired: this entry's own *"shape of the fix (not implemented -- it wants a round)"* still
describes the code. No openspec change covers it; the only external mention is the 2026-08-30
release roadmap.""",
    129: """**Status:** open. Verified 2026-09-09: `hub/ui/src` contains no reference to `spec/drift`,
`drift/detect` or `requirement_drift`, so the detection route is still unreachable from the app.
Named in the 2026-08-30 release roadmap, never specced. F132 sharpens it -- read that entry's
*"what this changes about F129's fix"* before proposing one.""",
    136: """**Status:** open. This entry says so itself -- *"they are not fixed"* -- and it shares a root
with F111: the `self_registered` guard in `get_agent_config`. Both close by deleting
self-registration, which is unimplemented.""",
    138: """**Status:** open, with the larger half fixed. The three hard-wired harnesses were repaired in
the filing commit. The residual left for the operator is now half-closed too: `aw.py`'s `KEY`
default is gone (`scripts/drive/aw.py:18`, plus a `require_key()` that exits, 2026-09-07), but
`HUB` still defaults to `http://127.0.0.1:8010` -- the one instance a drive must not disturb.""",
    139: """**Status:** open. Non-deterministic and unfixed. The archived change
`2026-09-01-a-flow-briefing-names-its-contract` cites it in `design.md:35` as a reason its own
briefing cannot assume a tool call, and repairs nothing here.""",
    156: """**Status:** open, and twice declared out of scope by the changes nearest to it:
`2026-09-01-a-conflict-refusal-names-what-clears-it/proposal.md:116` (*"F156 is not in scope"*) and
`2026-09-01-a-loop-declares-whether-it-needs-evidence/design.md:403` (*"adjacent and is not fixed
here"*). `integration-preview` still answers `will_merge: true` for a task approval refuses.""",
    158: """**Status:** open. This entry says *"not fixed"*, and the change it was raised against agrees:
`2026-09-01-a-loop-declares-whether-it-needs-evidence/design.md:729` -- *"F158 stands, unfixed and
out of scope"*. The candidate repair is still the open decision that design names.""",
    159: """**Status:** fixed `eeab0d3` (2026-09-01), in the same change that introduced it -- it never
shipped as a defect. Verified 2026-09-09: `hub/hub/task_workspace.py:239-240` applies the
`approved` filter only where `task_integration.evidence_governs` is False, and both guards exist --
`test_an_unapproved_evidence_free_prerequisite_contributes_nothing` and the shipped
`test_a_prerequisites_accepted_commits_are_in_the_task_checkout`
(`hub/tests/test_turn_workspace.py:907` and `:547`). Kept for the transferable lesson at the end,
which is this entry's real value.""",
    167: """**Status:** open, and said so by the change that met it:
`2026-09-01-a-review-nobody-is-doing-is-named/proposal.md:119` -- *"it does not repair the
recovery's blindness, and F167 stays open"*. `spec-queue/ROADMAP.md:187` records it as a known
residual on the adjacent `wedged_review` path that does not reopen F142.""",
    171: """**Status:** open. Filed by the row-1 sweep (`3280f52`), never fixed and never specced. The
regression assertion in `t_sweep_row1_ui.py` asserts the defect's shape for a future fix; it is not
a fix.""",
    172: """**Status:** open. Deterministically reproduced
(`t_f172_relocate_onto_a_claimed_path.py`), filed by the row-1 sweep (`3280f52`), never fixed and
never specced.""",
    174: """**Status:** open. Filed by the row-2 sweep (`6908cfd`). The catalog drift is unrepaired; the
adjacent effort control was re-checked and holds, which is a vindication inside this entry rather
than a resolution of it. Reappears in the 2026-09-03 and 2026-09-04 research pages, still open.""",
    178: """**Status:** open, and sharper than filed. Verified 2026-09-09: `useAgentLaunchability`
(`hub/ui/src/api/agents.ts:376`) has **no non-test caller** anywhere in `hub/ui/src` -- its only
consumers are three `__tests__` mocks. So the report reaches no screen, and three tests mock a hook
no component renders.""",
    179: """**Status:** open. Filed by the row-3 sweep (`58bd3fd`) alongside F178, never fixed. Named in
the 2026-09-01 exploration `a-refusal-reaches-the-operator` and in `spec-queue/DECISIONS.md`;
neither repairs it.""",
    186: """**Status:** open. Filed by the row-4 sweep (`66e085f`), never fixed and never specced. No
external mention anywhere in `openspec/` or `spec-queue/`.""",
    189: """**Status:** open, and explicitly excluded by the nearest change:
`2026-09-04-a-blocked-agent-workspace-holds-its-input/design.md:44` -- *"not a fix for F189 (the
Workspace section's invented session path), which is adjacent in the ledger"*.""",
    193: """**Status:** open. `spec-queue/DECISIONS.md:540` does not resolve it -- it says the product
already made the analogous three-way choice for archiving a conversation with a live run, and that
F193 should follow that precedent. That is guidance for a fix, not a fix.""",
    196: """**Status:** open. `spec-queue/DECISIONS.md:825` carries the decided remedy -- *"F196 + F198 --
remove `PATCH /queue/settings`"* -- as queue work. It has not been specced or implemented.""",
    197: """**Status:** open, and sized. `spec-queue/DECISIONS.md:296` supersedes the original estimate
with a count taken by the night window on 2026-09-02 (N-11): 51 reachable MISREPORT sites of 107
call sites. `713544d` established it is F271 with a skeleton in front of it. Sized, not fixed.""",
    202: """**Status:** open. Filed by the row-8 sweep (`7e45a27`). `spec-queue/DECISIONS.md:530` records
the shape -- `GET /projects/{id}/tasks` defaults to `limit=100` with no `total`/`has_more`/`next` --
as undecided work, not as a repair.""",
    206: """**Status:** open. Filed by the row-9a sweep (`fce9f83`) and carried into the 2026-09-01
research page and review page. No change addresses it.""",
    215: """**Status:** open, and confirmed open by sampling. `spec-queue/ROADMAP.md` drew four
unclassified findings at random to test whether the population was noise; this was one of the four,
and all four were *"real, unfixed, and none is anywhere in this plan"*.""",
    222: """**Status:** open, and confirmed open by the same random sample as F215
(`spec-queue/ROADMAP.md`) -- an archived job switched back on with one PATCH, which this entry's own
docstring calls *"the exact governance failure loops exist to make impossible"*.""",
    227: """**Status:** open, and enlarged rather than repaired. The 2026-09-06 re-measurement appended
below reaches the same defect through a second door -- a race between decline and answer in
`AgentQuestionCard.tsx`, where the decline button is held during an in-flight answer but nothing
holds the answer path during an in-flight decline. Both doors close on the one fix this entry
already asked for: a `declined` guard on `PATCH /questions/{id}`. That guard is unwritten.""",
    237: """**Status:** open, and confirmed open by the same random sample as F215
(`spec-queue/ROADMAP.md`) -- two controls write `Project.token_budget` through different routes and
emit different events, and the one in Settings leaves every surface displaying it stale.""",
    240: """**Status:** open. Filed by the row-14 drive (`d68f39a`) and carried into the 2026-09-06 and
2026-09-07 research pages. F92 recorded the `worker_invocations` half as an operator question
rather than a defect; neither half has been repaired.""",
    241: """**Status:** open. Filed by the row-15 drive (`4488e8f`), never fixed and never specced. Its
only external mention is the 2026-09-01 review page.""",
    242: """**Status:** open. Filed by the row-15 drive (`4488e8f`), never fixed and never specced.""",
    245: """**Status:** open. Filed by the row-15 drive (`4488e8f`), never fixed and never specced.""",
    251: """**Status:** open. Filed by the row-16 drive (`00b5dd9`), never fixed and never specced.""",
    252: """**Status:** open. Filed by the row-16 drive (`00b5dd9`), never fixed and never specced.""",
    253: """**Status:** open. Filed by the row-16 drive (`00b5dd9`), never fixed and never specced.""",
    258: """**Status:** open. Filed by the row-17 drive (`78461c9`), never fixed and never specced.""",
    259: """**Status:** open in substance, with its headline struck. The amendment below (2026-09-02, D-5)
withdraws the consequence, not the finding: `StatusBar.tsx` is imported by nothing and absent from
the bundle, so no operator sees the chip. What survives is that nothing in the product ever marks a
message read while `GET /status` and `hub/hub/scheduler.py:420` both depend on the flag -- which is
where F264 picks it up. Read this entry as that sentence; the chip is gone.""",
    264: """**Status:** open, and half-driven. The code half is established: `_pending_loop_request`
(`hub/hub/scheduler.py:415`) has no project filter and depends on a flag nothing sets (F259). The
live pass of 2026-09-01 fired the branch but **did not reproduce the leak**, and this entry records
itself as inconclusive rather than negative. It names the drive still owed -- one pass in which the
foreign row is the newest at firing time -- and that pass has not been run.""",
    265: """**Status:** open. Filed by the row-14 drive, never fixed and never specced. The refused
`create_loop` still leaves a committed job **enabled** with a next firing stamped, which is the half
of this entry that costs something.""",
    268: """**Status:** open. Filed alongside F267 by the 2026-09-02 catalog drive (`7b7720d`), never
fixed and never specced.""",
}

# Sections that already open with a prose `**Status:**` paragraph. The new line goes above it and
# the old one is relabelled, so a reader can tell a classification from the author's own words.
RELABEL = {
    109: (
        "**Status:** **the mechanism was already known",
        "**Status as filed:** **the mechanism was already known",
    ),
    111: (
        "**Status:** **superseded by an operator decision",
        "**Status as filed:** **overtaken by an operator decision",
    ),
    119: (
        "**Status:** Hub half fixed this session",
        "**Status as filed:** Hub half fixed this session",
    ),
}


def main():
    for num, (old, new) in RELABEL.items():
        lo, hi = next(rg for rg in res[num]["ranges"] if rg[0] == res[num]["line"] - 1)
        for i in range(lo, hi):
            if lines[i].startswith(old):
                lines[i] = new + lines[i][len(old) :]
                break
        else:
            raise SystemExit(f"relabel target not found for F{num}")

    edits = []
    for num, body in S.items():
        r = res[num]
        h = r["line"] - 1
        if not lines[h].lstrip().startswith("#"):
            raise SystemExit(f"F{num} does not anchor on a heading")
        j = h + 1
        while j < len(lines) and lines[j].strip() == "":
            j += 1
        if lines[j].startswith("**Status:**"):
            raise SystemExit(f"F{num} already carries a Status line at {j + 1}")
        edits.append((j, (body.rstrip() + TAG).split("\n")))

    for j, block in sorted(edits, reverse=True):
        lines[j:j] = block + [""]

    with open(cf.PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"inserted {len(edits)} status lines, relabelled {len(RELABEL)}")


if __name__ == "__main__":
    main()
