# The seams loop 7 found

## Why

Driving the product from zero on 2026-08-14
(`openspec/explorations/2026-08-14-loop7-evidence-drives-but-a-skipped-merge-is-terminal.md`) proved
that agents can now drive the evidence loop: a builder recorded evidence, a granted verifier accepted
it, approval merged, and coverage read `verified / integrated` — with no minted credential and no
`curl`. That was the point of `2026-08-14-the-loop-agents-can-drive`, and it holds.

The run still cost six extra agent runs and three operator interventions, to six defects that sit
**between** features rather than inside one. None was visible to 1949 passing tests.

Two of them are severe.

**Evidence is footprinted against the wrong commit, always.** An agent records evidence during its
turn; the commit containing that work is created by the Hub *after* the turn ends. So the footprint
names the commit the branch pointed at when the turn started. On a fresh project that is the `init`
commit, which is already on `master` — so the row is written `reachable_from_main=True`. Evidence
for code that does not exist reads as *already shipped*, and `integration_targets` merges on exactly
this field. This is a second, independent route into the failure
`2026-08-13-loop5-integration-reports-success-while-integrating-nothing.md` was written about. In
the run it was caught only because the verifier was strict enough to check the commit it was handed.

**A skipped merge is terminal.** Integration fires only on the transition *into* `approved`. Three of
the six skip reasons promise a remediation the state machine cannot deliver: `NO_MAIN_BRANCH` says
"choose one in the project's settings", and two others say "the next approval will merge" — from
`approved` there is no next approval. Following the instruction does nothing. Recovery took walking
`approved → revision_needed → in_progress → completed → under_review → approved` by hand, which no
agent can do and which falsifies the task's review history.

## What changes

1. **Evidence is footprinted against the commit that contains it.** After the turn's snapshot commit
   exists, the footprints that turn recorded are re-pointed at it.
2. **A skipped integration can be retried** — on the operator plane, on the agent plane, and
   automatically when the operator sets the main branch the skip asked for.
3. **A dead runtime says what happened.** `app-server process ended` gains the exit code, the
   in-flight method and a tail of the child's stderr — which is piped today and read by nobody.
4. **A failed run cannot wedge its agent.** Delivery attempts are counted; a twice-failed
   conversation gives up its provider thread so the next turn starts a fresh one; a third failure
   abandons the entry visibly instead of retrying forever.
5. **`requirement_ids` is readable.** It is accepted on create and update and appears on no response.
6. **The bundle staleness warning can be cleared** by a rebuild that produces an identical bundle.

## Archive ordering

This change **modifies** a `spec-document-authority` requirement that
`2026-08-14-what-the-product-actually-built` **adds** and that has not reached the main spec yet.
Archive that change first; applied in the other order the modification has nothing to modify. Full
order for the four now outstanding:

1. `2026-08-13-approved-means-it-is-in-the-product`
2. `2026-08-14-what-the-product-actually-built`
3. `2026-08-14-the-loop-agents-can-drive`
4. this change

## Non-goals

- **The interview backstop (G5).** The run's architect asked six substantive questions as prose,
  opened no question row, and the run completed with nothing pending. That is the standing operator
  decision — *"the AI should answer or not deliberately based on the test"* — and is not reopened.
- **Proving the bundle matches its source.** Only a rebuild can prove that. Item 6 records a dated,
  committed, attributable *assertion* that it does, which is the cheapest honest proxy in a source
  checkout. The proof is a CI job running `npm run build` and `diff -rq`, recommended as the
  follow-on and not built here.
- **Making `record_evidence` name a commit.** The tool cannot name a commit that does not exist yet,
  and the Hub's commit-on-delivery placement is load-bearing (D6 of the previous change). The
  footprint is corrected after the fact instead.
- **An MCP tool for integration retry.** Every skip reason except `NOTHING_TO_MERGE` names a
  remediation only the operator can perform, so a tool would invite a retry loop that changes
  nothing. The reversal condition is recorded in `design.md` D7.
