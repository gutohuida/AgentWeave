"""How wide an id segment is, and why it is that wide.

Eight hex characters is 32 bits of entropy, which puts the birthday bound at roughly 77,000 rows
before a collision is more likely than not. `event_logs` and `agent_outputs` are both append-only
and nothing prunes either, so an ordinary week of driving the product crosses that
(`scripts/drive/FINDINGS.md`, S2). Twelve moves the bound to roughly 800 million.

No migration goes with this. Every id column is already `String(64)`, and the segment is only ever
generated, never parsed — so rows written at eight characters keep working alongside new ones, which
is the property the last test here pins.
"""

import string

from sqlalchemy import String

from hub.db.models import EventLog, RequirementEvidence, Task
from hub.utils import short_id

HEX = set(string.hexdigits.lower())


def test_a_segment_is_twelve_hex_characters():
    segment = short_id()
    assert len(segment) == 12
    assert set(segment) <= HEX, segment


def test_segments_do_not_repeat_across_a_large_sample():
    """Not a proof of the bound — a cheap guard against a truncation that silently drops entropy,
    which is what `str(uuid4())[:12]` would have done by including the hyphen at index 8."""
    assert len({short_id() for _ in range(20_000)}) == 20_000


def test_no_hyphen_survives_the_truncation():
    """`uuid4()`'s *string* form has a hyphen at index 8. Widening by slicing that instead of `.hex`
    would have produced ids like `1a2b3c4d-e5f`, which cost four characters of entropy and put a
    separator inside a segment that is already joined to its prefix by one."""
    assert all("-" not in short_id() for _ in range(1000))


def test_the_columns_ids_are_stored_in_have_room_to_spare():
    """What makes this a code change rather than a migration."""
    for model, column in (
        (Task, "id"),
        (EventLog, "id"),
        (RequirementEvidence, "id"),
    ):
        kind = model.__table__.columns[column].type
        assert isinstance(kind, String)
        assert kind.length >= 64, f"{model.__name__}.{column} is only {kind.length}"


def test_an_id_written_at_the_old_width_is_still_a_valid_id():
    """Nothing parses a segment, so the two widths coexist. If this ever stops being true the
    widening needs a migration and a backfill, and this test is where that is noticed."""
    from hub.schemas.tasks import _TASK_ID_RE

    assert _TASK_ID_RE.match("task-1a2b3c4d")
    assert _TASK_ID_RE.match(f"task-{short_id()}")
