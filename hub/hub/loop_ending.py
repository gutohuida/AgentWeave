"""What it means for a loop to end, stated once.

A loop can end two ways. Its own firing can hit a stop condition (`scheduler._loop_stop_reason` —
the stop time passed, the queue drained), or the operator can state a `stop_reason` on the job.
Both are endings and both must leave the same four facts behind:

* `stop_reason` — why;
* `stopped_at` — when;
* `ending_state` — `completed` if the queue drained, `stopped` otherwise;
* `job.enabled = False` — and this is the one that makes it true rather than merely reported.

The scheduler set all four. The operator's route set two, and the two it left out were the when and
the *stopping*. Measured on the trial Hub, 2026-08-28: a loop the operator stopped at 23:09 read
`ending_state: "stopped"` from that second onwards, refused new queue items with `"This loop
stopped … and its queue is closed"`, and went on firing once a minute — twelve more real agent
turns over the following seventeen minutes, every one recorded `completed`. Nothing anywhere said
the loop was still running, because as far as every reader was concerned it had stopped.

`stopped_at` being NULL had its own visible tail: the two refusals that quote it both fall back to
the literal string `"an unknown time"`, which the Hub was printing about an event it had itself
carried out a minute earlier.
"""

from datetime import datetime
from typing import Optional

from .db.models import AIJob, Loop

#: The one reason that means the loop finished its work rather than being stopped. `scheduler.
#: _loop_stop_reason` returns this exact string; it is a constant here so the comparison that turns
#: it into `ending_state` cannot drift from the thing it compares against.
QUEUE_DRAINED_REASON = "loop queue is empty"


def end_loop(job: AIJob, loop: Optional[Loop], *, reason: str, when: datetime) -> None:
    """Record that this loop has ended and take its job out of the schedule.

    Does not commit — this is meant to join the transaction its caller is already in, so a loop
    cannot be recorded as ended while its job is still enabled, and vice versa. The caller is also
    responsible for unregistering the job from the running scheduler; on both paths that already
    happens (`_hand_job_to_scheduler` in the route, the scheduler's own store on the firing side).

    `job.enabled` is cleared even when there is no `Loop` row, because a caller reaching here has
    decided this job stops. `ending_state` is written only if nothing recorded one already: the
    operator editing the prose after the fact must not overwrite a governance fact that a firing
    established first.
    """
    job.enabled = False
    if loop is None:
        return
    loop.stop_reason = reason
    loop.stopped_at = when
    if loop.ending_state is None:
        loop.ending_state = "completed" if reason == QUEUE_DRAINED_REASON else "stopped"
