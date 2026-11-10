# Build retrospective of Failures already known are on a list, not re-argued

Document: spec/changes/failures-already-known-are-on-a-list-not-re-argued/spec.json (spdoc-e59b3e6d8f76)
Made: 2026-11-06T08:24:05.147039+00:00

## Lessons

- Specs that add an API should name the exact route path and response field names, so that acceptance drives written before the build can call the right endpoint. (cites: run-c086f1ffc37d, run-d12c6cea88b1)
- Before approval, check every acceptance criterion against the timing of the other requirements. A criterion that asks for an outcome after a send-back has already happened needs an explicit undo path in the design. (cites: spev-a46d63ca6e58, ttr-3890671b0804)
- Any spec that adds tables referencing tasks or projects should require deletion-cascade coverage for those tables. This project's hub-tests enforce it at landing. (cites: ttr-1ea9f8847044, chk-80ed2612960a)
- A new migration's revision number can collide with one landed on master in parallel without any textual git conflict. Check the alembic heads against current master before completing. (cites: ttr-1cd080200b55, ckpt-66217520623c)
- Acceptance-drive assertions should test what a criterion means, such as 'only listed tests fail' or 'the task is not revision_needed', rather than raw run state. They should build scenarios that a correct build's completion gate will not short-circuit. (cites: ttr-612ea34e97a5, ttr-0a26d8e85c3c)
- When one criterion is split between a unit test and a drive step, the spec should say which task records the full evidence. Otherwise partial evidence blocks landing. (cites: ev-31be688a408d, run-11445608e9a7)
- A drive that commits to main right after configuring checks must first wait for the main watch's first look, or the commit becomes the watch's baseline and is never raised. (cites: run-f24314235dc7, run-11445608e9a7)

## What to improve

- [code_and_checks] Stop committing ui-build-stamp.json as a hand-merged artifact. Regenerate it at landing or exclude it from merges, so that bundle rebuilds on parallel branches stop sending tasks back. (cites: ttr-9349842f6ece, chk-b036724d94be)
- [code_and_checks] Raise or rework the sweep check's 360s timeout. It timed out twice on an unchanged tree and stalled the gate. (cites: chk-d457d0832508, chk-0a2f71afbbac, stall-ecc0d8714685)
- [code_and_checks] Add a fast check, in the sweep or the completion gate, that fails when a branch's alembic revisions would give two heads once merged with current master. (cites: ttr-1cd080200b55)
- [code_and_checks] Run the deletion-coverage tests in the sweep set, so that missing cascade rows for new tables are caught before review instead of in a 30-minute landing run. (cites: chk-80ed2612960a, ttr-1ea9f8847044)
- [specs] Require each spec to list new routes with their exact paths and response fields, and new tables with their deletion semantics. (cites: run-c086f1ffc37d, ttr-1ea9f8847044)
- [specs] Before approval, review acceptance criteria for consistency across requirements, especially any outcome that depends on the order in which two gates run. (cites: spev-a46d63ca6e58)
- [staffing_and_running] Make sure a trial Hub is available, or have the task start a scratch Hub, for acceptance-drive tasks, and do not approve a drive that has not run past its first step. (cites: run-d12c6cea88b1, ttr-160c809ef5d7, run-f991c7e69067)
- [staffing_and_running] Start a dependent task only after its prerequisite has landed, or rebase it onto the prerequisite's final branch, to avoid duplicate fixes and the merge conflicts they cause. (cites: ttr-92965eac97dd, run-8d112f2a5e7f)
- [tooling] Carry forward held, unchanged evidence automatically at a new commit, instead of requiring authors to re-record every piece after each merge or landing return. (cites: ttr-0a26d8e85c3c, ev-808e1d7cf4e9, ev-155bef8088df)
- [tooling] Have record_evidence default to the task's own spec document, so it no longer fails when an FR id exists in several documents. (cites: run-d12c6cea88b1, run-206f23a19d09)
- [tooling] Provide a Hub-only way to undo a checks send-back, including releasing its held evidence, so that criteria like ac-twice can be satisfied. (cites: spev-a46d63ca6e58)
- [tooling] Keep the trial Hub from restarting mid-drive, or have drives survive a restart and clean up their leftover projects. (cites: run-f991c7e69067)
