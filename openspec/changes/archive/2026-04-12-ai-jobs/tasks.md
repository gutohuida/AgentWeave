## 1. Dependencies & Project Setup

- [x] 1.1 Add `croniter` as optional extra `[jobs]` in `pyproject.toml` and as a hard dependency in `hub/requirements.txt`
- [x] 1.2 Add `apscheduler>=3.10` to `hub/requirements.txt`
- [x] 1.3 Add job directory constants to `src/agentweave/constants.py` (`JOBS_DIR`, `JOBS_HISTORY_DIR`)

## 2. Core Job Module (CLI)

- [x] 2.1 Create `src/agentweave/jobs.py` — `Job` dataclass with all fields (id, name, agent, message, cron, session_mode, enabled, created_at, last_run, next_run, run_count, source, synced)
- [x] 2.2 Implement `Job.validate_cron()` using croniter — raise `ValueError` on invalid expression
- [x] 2.3 Implement `Job.create()`, `Job.load()`, `Job.save()`, `Job.list_all()`, `Job.delete()` — file-based CRUD under `.agentweave/jobs/`
- [x] 2.4 Implement `Job.compute_next_run()` using `croniter.get_next(datetime)` and store on save
- [x] 2.5 Create `JobRun` dataclass with fields (id, job_id, fired_at, status, trigger, session_id)
- [x] 2.6 Implement `JobRun.save()` — write to `.agentweave/jobs/history/<job_id>/<timestamp>.json`
- [x] 2.7 Implement `JobRun.list_for_job(job_id, limit=100)` — read history files sorted by timestamp, prune oldest beyond limit

## 3. Transport Layer Extension (CLI)

- [x] 3.1 Add abstract job methods to `src/agentweave/transport/base.py`: `create_job`, `list_jobs`, `get_job`, `update_job`, `delete_job`, `fire_job`
- [x] 3.2 Implement job methods in `src/agentweave/transport/local.py` — delegate to `jobs.py` functions
- [x] 3.3 Implement job methods in `src/agentweave/transport/http.py` — HTTP calls to Hub `/api/v1/jobs` endpoints
- [x] 3.4 Implement local-to-Hub sync in `src/agentweave/transport/http.py` — `sync_local_jobs()`: read local jobs, POST each to Hub (skip on 409)
- [x] 3.5 Call `sync_local_jobs()` during `HttpTransport` initialization/connect

## 4. Watchdog Extension (CLI)

- [x] 4.1 Add `check_jobs()` method to `src/agentweave/watchdog.py` — iterate enabled local jobs, evaluate cron vs now using croniter
- [x] 4.2 Implement fire guard in `check_jobs()` — acquire `lock("job-<id>")`, skip if `last_run` within 50 seconds
- [x] 4.3 Fire job by calling `agentweave run <agent> "<message>"` subprocess with `--session` flag based on `session_mode`
- [x] 4.4 After fire, update `job.last_run`, `job.run_count`, `job.next_run` and write `JobRun` history entry
- [x] 4.5 Call `check_jobs()` in the Watchdog `run()` poll loop (after existing message/task checks)

## 5. CLI Commands

- [x] 5.1 Add `cmd_jobs_create()` to `src/agentweave/cli.py` — parse args, validate cron, call `transport.create_job()`
- [x] 5.2 Add `cmd_jobs_list()` — call `transport.list_jobs()`, print table with id, name, agent, cron, enabled, last_run, next_run
- [x] 5.3 Add `cmd_jobs_get()` — print full job details plus last 10 history entries
- [x] 5.4 Add `cmd_jobs_pause()` and `cmd_jobs_resume()` — call `transport.update_job(id, enabled=False/True)`
- [x] 5.5 Add `cmd_jobs_delete()` — call `transport.delete_job(id)` with confirmation prompt
- [x] 5.6 Add `cmd_jobs_run()` — call `transport.fire_job(id)` with `trigger="manual"`
- [x] 5.7 Add `jobs` subparser and routing in `create_parser()` and `main()` in `cli.py`

## 6. Hub Database Models

- [x] 6.1 Add `AIJob` SQLAlchemy model to `hub/hub/db/models.py` — all fields per design, indexes on `(project_id, agent)` and `(project_id, enabled)`
- [x] 6.2 Add `JobRun` SQLAlchemy model — fields: id, job_id, project_id, fired_at, status, trigger, session_id; index on `(job_id, fired_at)`
- [x] 6.3 Add table creation for `AIJob` and `JobRun` in `hub/hub/db/engine.py` (existing `create_all` pattern)

## 7. Hub REST API

- [x] 7.1 Create `hub/hub/api/v1/jobs.py` — FastAPI router with all CRUD endpoints
- [x] 7.2 Implement `GET /jobs` — list all jobs for project, optional `?agent=` filter
- [x] 7.3 Implement `POST /jobs` — create job, validate cron with croniter, add to APScheduler, return job with 201
- [x] 7.4 Implement `GET /jobs/{id}` — return job details
- [x] 7.5 Implement `PATCH /jobs/{id}` — update fields (enabled, name, message, cron, session_mode); update APScheduler on enabled/cron change
- [x] 7.6 Implement `DELETE /jobs/{id}` — remove job and JobRun history from DB, remove from APScheduler
- [x] 7.7 Implement `GET /jobs/{id}/history` — return last N JobRun entries (default 100)
- [x] 7.8 Implement `POST /jobs/{id}/run` — fire immediately, create JobRun with `trigger="manual"`, broadcast SSE `job_fired` event
- [x] 7.9 Include jobs router in `hub/hub/api/v1/__init__.py`

## 8. Hub Scheduler

- [x] 8.1 Create `hub/hub/scheduler.py` — `JobScheduler` class wrapping `AsyncIOScheduler` with `SQLAlchemyJobStore`
- [x] 8.2 Implement `JobScheduler.start(db_session)` — load all enabled jobs from DB, schedule each with their cron
- [x] 8.3 Implement `JobScheduler.shutdown()` — call `scheduler.shutdown(wait=False)`
- [x] 8.4 Implement `JobScheduler.add_job(job)`, `update_job(job)`, `remove_job(job_id)` — for real-time sync with REST API changes
- [x] 8.5 Implement job fire callback — call agent trigger logic internally, create `JobRun` DB record, update `AIJob.last_run`/`run_count`/`next_run`, broadcast SSE `job_fired`
- [x] 8.6 Integrate `JobScheduler` into `hub/hub/main.py` FastAPI lifespan (`startup` → `start()`, `shutdown` → `shutdown()`)
- [x] 8.7 Pass `scheduler` instance to the jobs API router via app state or dependency injection

## 9. Hub MCP Tools

- [x] 9.1 Add `create_job`, `list_jobs`, `get_job`, `delete_job`, `toggle_job`, `run_job` to `hub/hub/mcp_server.py` using existing `_hub_request()` pattern
- [x] 9.2 Add same 6 tools to `src/agentweave/mcp/server.py` — route through `get_transport()` job methods

## 10. /aw-job Skill

- [ ] 10.1 Create skill file `.claude/skills/aw-job.md` — document subcommands: create, list, pause, resume, run, delete, history
- [ ] 10.2 Skill `create` subcommand: prompt for agent, message, cron, session_mode if not provided; call `create_job` MCP tool
- [ ] 10.3 Skill `list` subcommand: call `list_jobs`, render as formatted table
- [ ] 10.4 Skill `pause`/`resume` subcommands: call `toggle_job` with enabled=false/true
- [ ] 10.5 Skill `run` subcommand: call `run_job`, confirm execution
- [ ] 10.6 Skill `delete` subcommand: confirm before calling `delete_job`
- [ ] 10.7 Skill `history` subcommand: call `get_job`, render history entries

## 11. Hub UI — API Layer

- [ ] 11.1 Create `hub/ui/src/api/jobs.ts` — React Query hooks: `useJobs`, `useJob`, `useJobHistory`, `useCreateJob`, `useUpdateJob`, `useDeleteJob`, `useRunJob`
- [ ] 11.2 Add `job_created`, `job_updated`, `job_fired` SSE event handling in `hub/ui/src/hooks/useSSE.ts` — invalidate `['jobs']` query key

## 12. Hub UI — Components

- [ ] 12.1 Create `hub/ui/src/components/jobs/JobsPage.tsx` — page wrapper with "New Job" button and job list
- [ ] 12.2 Create `hub/ui/src/components/jobs/JobCard.tsx` — displays job fields, enable toggle, "Run Now" button, "History" expander, edit/delete actions
- [ ] 12.3 Create `hub/ui/src/components/jobs/JobForm.tsx` — create/edit modal with all fields; inline cron validation feedback
- [ ] 12.4 Create `hub/ui/src/components/jobs/JobRunHistory.tsx` — expandable list of last 10 runs with fired_at, status, trigger, session_id
- [ ] 12.5 Add Jobs page to `hub/ui/src/App.tsx` router
- [ ] 12.6 Add Jobs nav item to `hub/ui/src/components/layout/Sidebar.tsx` with enabled-job-count badge

## 13. Tests

- [ ] 13.1 Add unit tests for `jobs.py` — cron validation, CRUD, history pruning at 100 entries
- [ ] 13.2 Add unit tests for `watchdog.py` `check_jobs()` — fire guard, disabled job skip, cron match logic
- [ ] 13.3 Add API tests for Hub jobs endpoints in `hub/tests/` — CRUD, history, immediate run
- [ ] 13.4 Add MCP tool tests for `create_job`/`list_jobs`/`toggle_job`/`run_job` in both CLI and Hub servers

## 14. Documentation

- [ ] 14.1 Add "AI Jobs" section to docs — explain dual-mode, Watchdog requirement for local mode, cron syntax
- [ ] 14.2 Update `CLAUDE.md` — add `jobs.py` to architecture overview, note croniter dependency and APScheduler
- [ ] 14.3 Update Hub `docker-compose.yml` comments if needed (no new services required)
