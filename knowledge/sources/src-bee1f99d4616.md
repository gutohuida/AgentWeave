# Build retrospective of A new project starts as a git repository with an AGENTS.md

Document: spec/changes/a-new-project-starts-as-a-git-repository-with-an-agents-md/spec.json (spdoc-47b5bc7c9e3a)
Made: 2026-11-10T14:24:39.144757+00:00

## Lessons

- Every folder the Hub has opened already contains .agentweave/project.json, so a spec rule that treats that marker as 'already an AgentWeave project' must say whether the Hub's own marker counts. This build settled it: only a marker carried in before opening (an adopted project) counts. (cites: q-2b0ba28173f1, ev-91aacfe883fb, spreq-4fcae4331cd7)
- Hubs may run without a git binary, for example in the Docker slim image. A spec that requires a git repository should say whether to refuse or fall back in that case. (cites: ckpt-6f2a4048a58d)
- Acceptance criteria that call for a real agent turn or an operator click-through were not carried out in this build. If such checks matter, the spec should say who runs them and when, or accept seam-level evidence explicitly. (cites: ev-9cb14d80bed1, ev-5f2861361638, evr-1363a87c5a4f)
- Specs for actions that commit an operator's existing folder should address nested git repositories, very large folders and pre-commit hooks, because none of these were covered here. (cites: ckpt-cd96d78cdf38, ckpt-6ff7f0cad051)
- Whether Codex and Copilot read AGENTS.md natively was taken from their documentation, not measured. Specs that rely on runner behaviour should name how it will be verified. (cites: ev-5f2861361638, spreq-89debc07b952)

## What to improve

- [code_and_checks] Document or opt out of the hub/tests autouse workspace fixture, which roots every project at tmp_path, so tests that need real per-project folders do not silently read the wrong one. (cites: ckpt-cd96d78cdf38)
- [code_and_checks] Investigate the intermittent test_migrations 0078/0105 failure under -n 4 and the aiosqlite 'Event loop is closed' thread exception in hub-tests. (cites: ckpt-6ff7f0cad051, chk-9a26f97a0c16)
- [code_and_checks] Replace the hand-written @/api/projects mocks in UI tests with a shared mock, so adding a hook does not break several unrelated tests. (cites: ckpt-cd96d78cdf38)
- [specs] When a spec rule depends on files the Hub itself writes, such as the project marker, state explicitly whether Hub-written copies count. (cites: q-2b0ba28173f1)
- [specs] For each acceptance criterion that requires a live agent turn or an operator click-through, say who performs it, or what evidence counts as enough. (cites: ev-9cb14d80bed1, ev-07aa52c6f7ac)
- [staffing_and_running] Configure a fast check at completion, and run hub-tests before review rather than after approval, so failures surface before QA signs off. (cites: ttr-d8a1b536cf35, chk-c0734a112cb1)
- [staffing_and_running] Avoid overlapping heavy gate runs on one machine, since the overlapping NPSAG-2 run slowed sweep and black noticeably. (cites: chk-f660bf952bca, chk-c0734a112cb1)
- [staffing_and_running] Make a scratch-Hub drive a standard part of review for tasks that touch git or the filesystem, as was done for NPSAG-3. (cites: evr-1363a87c5a4f, evr-7e5776462e2e)
- [tooling] Warn agents on Windows that writing files through Bash or Python write_text mangles newlines, and steer them to the Edit/Write tools or write_bytes. (cites: run-f6e0ae874b42, ckpt-cd96d78cdf38)
