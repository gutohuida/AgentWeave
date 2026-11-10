# Build retrospective of Start a conversation from any checkpoint, with any agent

Document: spec/changes/start-a-conversation-from-any-checkpoint-with-any-agent/spec.json (spdoc-6fe8fb0c3c67)
Made: 2026-11-06T03:49:29.362792+00:00

## Lessons

- Write any browser contract that an acceptance drive depends on into the spec itself: test ids, element kinds such as a native select, and banner wording. A UI builder will not find it in the drive's docstring. (cites: ttr-86bcfcfa9a3d, ev-727337f67459)
- When a requirement says something runs on another agent's model, give the test agents different models. Otherwise the drive cannot show it. (cites: ev-2a33f7c4522f)
- Any new UI query call must surface its error. Otherwise test_surface_ceilings' ratchet fails the sweep. (cites: chk-7e20211e455a, ev-341685e48358)
- Name the migration number in the spec when a parallel slice may also add migrations. The head revision is hard-coded in test_migrations.py and test_project_persistence.py. (cites: ckpt-4df1c945fac3)
- UI tasks should be told to run the acceptance drive before completing. Evidence left partial for lack of a drive run cannot be upgraded by the reviewer. (cites: run-a58222b59cac, ev-e3c9d9275a8e)

## What to improve

- [code_and_checks] Make the sweep fit its 360s limit on this machine, or raise the limit. Two timed-out runs judged nothing and stalled SCACA-2. (cites: chk-2efc848858de, chk-89d51542acea, stall-34375675fefe)
- [code_and_checks] Stabilise the hub-ui vitest suite. Its worker timeouts fail it on main too, and its first-attempt failures force re-runs. (cites: chk-157db6979150, chk-758451f834d9)
- [specs] Specs with a browser acceptance drive should list the drive's selectors and wording as requirements of the UI task, and should give the drive's agents distinct models. (cites: ttr-86bcfcfa9a3d, ev-2a33f7c4522f)
- [staffing_and_running] Require the builder to run the acceptance drive, and record full evidence, before marking a UI task completed. (cites: run-076c50b26c9b, run-d671c4e6472a, run-a58222b59cac)
- [tooling] Make record_evidence's error say plainly that the document must be named. Also let a reviewer's passing drive upgrade partial evidence, or route it to the author automatically. (cites: run-ccb3737258a5, run-a58222b59cac)
