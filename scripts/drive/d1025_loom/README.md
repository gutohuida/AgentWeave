# Drive: the loom Thread page (task-231a74f0b9f7, spec the-thread-runs-left-to-right-as-a-wave-…)

Run on 2026-10-25 against this worktree's UI (Vite dev servers from `hub/ui`). State and screenshots go to
`testbed/drive-loom/` (ignored). Never :8000; :8010 is only read through a Vite proxy (`trial` section,
whose weave POST is intercepted, not sent).

1. Operator copy (17 chapters, the mock's data): `copy_op.py <abs op.db> <repo dir>` takes a read-only
   backup of `~/.agentweave/hub/data/agentweave.db`, deletes jobs/loops/queued input/keys, points the
   AgentWeave project at `<repo dir>` (a detached `git worktree add` of master **outside** any task
   checkout, with `.agentweave/project.json` copied in and `path_key` updated to match, or the Hub
   refuses the path and git-backed chapters read empty). Set any `running` run to `interrupted`, pid NULL.
2. Scale: fresh DB, `POST /projects/open` a folder outside the repo, `seed_scale.py <project>` (165
   documents, 1000 tasks, 3000 runs, 5835 messages = 10,000 items). Live: `seed_live.py <project>`
   and an agent bound to `claude-haiku-5-5`.
3. Hubs: `cd hub && DATABASE_URL=sqlite+aiosqlite:///<db> AW_BOOTSTRAP_API_KEY=<key> py -3.11 -m uvicorn
   hub.main:app --port 8020|8021`; key in `testbed/drive-loom/key.txt`.
4. UI: `AW_DEV_HUB=http://127.0.0.1:<port> npx vite --port 5191|5192|5193 --host 127.0.0.1` (8010, 8020,
   8021) and `npx vite --config vite.mock.config.ts --port 5199 --host 127.0.0.1`.
5. `py -3.11 scripts/drive/d1025_loom/drive.py [mock op motion scale trial]`, `live.py`, `even.py`.
