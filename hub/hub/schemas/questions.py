"""Question schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class QuestionOption(BaseModel):
    """One offered answer.

    `label` is what comes back when it is chosen; `description` is what lets an operator pick
    without already knowing the trade-off, and is the whole reason options beat a text box.
    """

    label: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=500)

    model_config = {"extra": "forbid"}


class QuestionCreate(BaseModel):
    from_agent: str = Field(max_length=64)
    question: str = Field(max_length=10000)
    blocking: bool = False
    # Offered answers. Empty means open-ended. Capped so one question cannot render an
    # unbounded wall of buttons in front of an operator deciding under a run's timeout.
    # Required, not optional. Teaching an agent to pass options is probabilistic — it forgets,
    # and the operator gets a text box for a decision that was always a choice. A schema it
    # cannot satisfy without them is not. This mirrors Claude Code's own AskUserQuestion, where
    # header/options/multiSelect are all mandatory and free text is the UI's escape, never a
    # missing-options case.
    options: List[QuestionOption] = Field(min_length=2, max_length=8)
    header: str = Field(min_length=1, max_length=64)
    multi_select: bool


class QuestionAnswer(BaseModel):
    """The operator's answer.

    `answer` is always the human-readable form. `labels` carries the structure when options were
    chosen, so a multi-select answer stays a list rather than a string someone has to re-split.
    """

    answer: str = Field(max_length=10000)
    labels: List[str] = Field(default_factory=list, max_length=8)


class QuestionResponse(BaseModel):
    id: str = Field(max_length=128)
    project_id: str = Field(max_length=128)
    from_agent: str = Field(max_length=64)
    question: str = Field(max_length=10000)
    answer: Optional[str] = Field(default=None, max_length=10000)
    answered: bool
    blocking: bool
    options: List[QuestionOption] = Field(default_factory=list)
    header: Optional[str] = None
    multi_select: bool = False

    answer_labels: List[str] = Field(default_factory=list)
    # Batch identity. A question asked on its own reports `batch_size == 1`, so a reader never has
    # to special-case the unbatched form. `batch_size` is what lets the panel say "2 of 3" while
    # holding only the unanswered rows.
    batch_id: Optional[str] = None
    batch_index: int = 0
    batch_size: int = 1
    created_at: datetime
    answered_at: Optional[datetime] = None
    # The operator closed this without answering. Distinct from `answered` on purpose: an empty
    # answer says they responded with nothing, this says they chose not to respond
    # (`2026-08-11-declining-a-question`, D1).
    declined: bool = False
    declined_at: Optional[datetime] = None
    # Whether anyone is still waiting on this question.
    #
    # Computed from the asking run rather than stored: the `runs` table already holds it, and a
    # stored copy would go stale at exactly the transition it exists to describe — the run ending.
    #
    # Defaults to `True` when the asking run is unknown, matching the answer path's presumption.
    # Guessing the other way would mark a live question inert and sort it behind dead ones, which is
    # the worse error of the two.
    asker_waiting: bool = True

    model_config = {"from_attributes": True}
