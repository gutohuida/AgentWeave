"""Schemas for the agent-facing document-creation route.

`create_spec_document` takes no `path` and no `kind` — deriving both from a
caller is exactly what the route must not offer (design D2, D3 of
`agent-created-documents`). What is left to accept is a plain optional title.
"""

from typing import Optional

from pydantic import BaseModel, Field


class SpecDocumentCreate(BaseModel):
    """What an agent may say when starting an exploration: nothing but a title.

    No `path`, `kind`, `actor`, `agent` or `run_id` field exists to declare —
    the route never reads the body for any of them, so a caller that sends one
    anyway is not rejected, it is simply not listened to (design D2, D3:
    unexpressible, not merely refused). `extra` is left at its pydantic
    default (ignore) rather than `"forbid"`, unlike this route's siblings —
    here the whole point is that stray identity or placement fields cost the
    caller nothing to send and gain them nothing either.

    So this model deliberately does **not** inherit `RequestModel`, and is the
    one named entry in `LAX_BY_DESIGN` (hub/tests/test_request_strictness.py).
    Two shipped requirements stand behind that: `agent-document-creation`'s
    "unexpressible rather than merely refused", and `spec-document-authority`'s
    *The payload contract is versioned and forward compatible* — "no validation
    error is raised on their account". Forbidding here would breach both.
    """

    title: Optional[str] = Field(default=None, max_length=256)


class SpecDocumentCreateResponse(BaseModel):
    """The minted placeholder: a path to rename later, and the phase it starts in."""

    path: str
    phase: str
