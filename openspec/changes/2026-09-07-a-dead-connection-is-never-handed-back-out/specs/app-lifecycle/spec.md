## ADDED Requirements

### Requirement: A shutting-down instance SHALL release its database connections before its event loop closes
A local AgentWeave instance SHALL, while its event loop is still running, settle the background run tasks it started and then release every database connection it holds, so that no connection outlives the loop that last queued work on it.

Order is part of the requirement, not an implementation choice. Releasing the connections while a
background run is still writing takes away the connection that run needs to finish, so it never
finishes; settling the runs after the connections are gone is the same mistake in the other
direction. Terminating the run *processes*, which shutdown already does first, does not settle the
in-process tasks that were driving them.

The instance SHALL also stop admitting new scheduled work before it settles, so that the settle is
not racing a scheduler that can still start a run. Stopping the scheduler does not wait for a job
already in flight, and such a job can start a run of its own, so a settle performed first is
settling a set that can be refilled behind it.

Settling SHALL tolerate a run that schedules a successor while it is being settled — releasing a
run's input can legitimately schedule the same agent again — and SHALL be bounded, so that a
repeatedly rescheduling agent cannot hold the instance open. Reaching that bound is a reportable
condition, not a fatal one: an instance that has been asked to stop SHALL stop.

#### Scenario: A run still writing when the instance is asked to stop

- **WHEN** the instance is shut down while a background run task is in flight
- **THEN** the run task is settled and every database connection is released before the event loop
  closes
- **AND** the shutdown produces no uncaught error from a database driver's worker thread

#### Scenario: A scheduled job fires as the instance is stopping

- **WHEN** the instance is shut down while a scheduled job is in flight
- **THEN** the scheduler stops admitting work before the background run tasks are settled
- **AND** any run that job started is settled with the rest

#### Scenario: A run reschedules while shutdown is settling it

- **WHEN** settling a background run task releases its input and that release schedules another run
- **THEN** shutdown settles the successor as well, up to a bounded number of passes

#### Scenario: Settling does not complete within the bound

- **WHEN** background run tasks are still being registered after the bounded number of passes
- **THEN** the instance records how many remain and completes its shutdown anyway

### Requirement: A database connection whose driver worker is gone SHALL be replaced, never reused
The instance SHALL NOT hand out a pooled database connection that can no longer complete work, and SHALL replace it with a new connection instead.

An asynchronous SQLite connection carries out every statement on one dedicated worker thread. If
that thread has ended, the connection is not slow and is not merely in an error state: it accepts
work, never answers, and cannot be closed, because closing is itself work for the thread that ended.
Anything that waits on it waits without bound, and cancelling the wait does not return either,
because unwinding the connection needs the same thread.

Detection therefore SHALL happen before the connection is handed out rather than after a statement
has already been issued on it, and discarding such a connection SHALL NOT require the connection to
answer — it is put beyond use first, then discarded, so that the instance's own cleanup cannot block
on it.

Replacement SHALL be transparent to the caller: work issued after a dead connection is discarded
completes against a fresh connection rather than failing.

This requirement holds wherever the condition arises. It is not conditional on the instance having
been shut down, and it applies to a connection whose worker was lost for any reason.

#### Scenario: A pooled connection whose worker thread has ended

- **WHEN** a database connection whose driver worker thread has ended is next taken from the pool
- **THEN** it is discarded without any statement being issued on it
- **AND** the request is served by a newly opened connection
- **AND** the statement completes

#### Scenario: Discarding does not wait on the dead connection

- **WHEN** such a connection is discarded
- **THEN** neither the discard nor any cleanup it triggers waits on the ended worker thread

#### Scenario: A healthy connection is unaffected

- **WHEN** a database connection whose driver worker thread is running is taken from the pool
- **THEN** it is used as-is and no reconnection occurs

#### Scenario: A driver that does not present a worker thread

- **WHEN** the instance is configured against a database driver that has no per-connection worker
  thread
- **THEN** connections are taken from the pool unchanged and the check does not fail the checkout
