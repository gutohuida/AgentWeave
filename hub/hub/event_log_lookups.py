"""The event-log fields project screens filter by, in the form their indexes match.

`screens-stop-repeating-work-on-every-read`, task event-log-indexes (FR-5). A build's
retrospectives, a document's pre-mortems and answers, and a task's unstaffed review and held
send-back are found by a field inside `event_logs.data`. Migration 0194 indexes each of those
fields, partial on its event type, as `ix_event_logs_context_*` (migration 0144) do for readings.

SQLite uses a partial index only when the query's WHERE names the index's condition literally, and
an expression index only for the identical expression: a bound `?` for the event type or the JSON
path, or SQLAlchemy's `data["subject"]["document"]` (which nests a JSON_QUOTE), silently falls back
to searching every row of the event type. So a query names these, never `EventLog.data[...]`.
`hub/tests/test_event_log_json_indexes.py` checks the plans of the statements the routes issue.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, literal_column

from .db.models import EventLog

_EVENT_TYPE = re.compile(r"^[a-z_]+$")


def is_event(event_type: str) -> Any:
    """`event_type = '<event_type>'`, with the type as a literal so a partial index applies."""
    if not _EVENT_TYPE.match(event_type):
        raise ValueError(f"not an event type: {event_type!r}")
    return EventLog.event_type == literal_column(f"'{event_type}'")


def _field(path: str) -> Any:
    return func.json_extract(EventLog.data, literal_column(f"'{path}'"))


#: A `manager_job_fired` row's job and the document it was about.
fired_job = _field("$.job")
fired_document = _field("$.subject.document")
#: The task a `review_unstaffed` or `send_back_held` row is about.
event_task = _field("$.task_id")
#: The document a `pre_mortem_answered` row answers.
answer_document = _field("$.document")
