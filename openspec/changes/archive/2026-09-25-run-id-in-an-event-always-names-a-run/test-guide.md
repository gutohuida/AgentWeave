# Test guide — `run_id` in an event always names a run

## Agent-verifiable

1. **Each job event names its record as `job_run_id`.** Tasks 1.1-1.3 and 1.5 fail before and pass
   after, for the SSE payload, the persisted payload and the route's answer.
2. **Every `run_id` on the stream is a run.** Task 1.4 fails before (the `job_fired` row names a
   `JobRun`) and passes after.
3. **Live.** Task 3.1, on a trial Hub.

## Human-only

1. Open the activity log for a project after a job fires. The firing's detail names `job_run_id`;
   the run that follows names `run_id`. Older rows keep their old key (design D2); that is expected.
