# Build retrospective of AgentWeave is its own app on Windows

Document: spec/changes/agentweave-is-its-own-app-on-windows/spec.json (spdoc-6e4ad341cf1b)
Made: 2026-11-05T16:29:59.809447+00:00

## Lessons

- Acceptance drives in this project must be repeatable. Each run should create fresh, per-run scratch profiles and clean them up afterwards, or leftover runs will queue agent turns. (cites: ttr-fdc05877c02d, ev-e7ec3e3ecc90)
- On this machine, a busy Hub can take more than 2–3 s to answer /health. Any stop or close logic must not treat a timeout as absence, and must never delete a PID file because of one. (cites: ttr-f83fbcd2d8b1, ev-4811a8a25ce0)
- When one task's drive depends on UI labels that a later task will build, such as the 'Stop it all' button, the spec should name those labels. (cites: ckpt-4ecf0f3fa6dd)
- A requirement that says the app is watched 'while a project is used' needs a drive step that actually runs an agent turn inside the watch window. (cites: evr-fdb674950303, ev-9b61b5b120d6)
- Drives must clean up every file the app writes, including window-<port>.json geometry files. (cites: evr-81345536af01)

## What to improve

- [tooling] Do not send a task back as a broken check when a check timed out after printing success. Treat that result as unjudged and retry it, as the per-task gate already does. (cites: ttr-e5d7fee3d342, evr-bf8d32cc320f)
- [staffing_and_running] Raise the 120 s check timeout, or limit how many checks and drives run at once on this machine. black, ruff and sweep repeatedly timed out from load alone. (cites: chk-17465d64bfd2, chk-62062f11c320, chk-d34dfc9a7cf6)
- [specs] Name the prompt button labels and say what a close during the splash screen should do in the close requirements, so drives and implementation agree from the start. (cites: ckpt-4ecf0f3fa6dd, ev-08c761ec9f52)
- [code_and_checks] Investigate why the launch registers no project on named profiles, then remove the drive's POST /projects/open fallback. (cites: ckpt-8d91c4d6090c)
- [code_and_checks] Make d1105_own_app.py delete the window-8171..8173.json geometry files it causes the app to write. (cites: evr-81345536af01)
- [tooling] Make sure the AgentWeave MCP server starts reliably for build runs. Its failure forced the aw-tool fallback in AWOAW-3. (cites: run-63c22edd2152)
